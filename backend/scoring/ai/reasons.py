"""Optional Gemini prose with code-owned grounding, retry and safe templates."""

import logging
import math
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel
from app.schemas.enums import RiskTier
from app.schemas.scoring import Reason, Signal
from scoring.ai.privacy import mask_phone_numbers
from scoring.ai.reason_check import LOCATION_SIGNAL_KEYS, CheckResult, check_reasons, numeric_fact

PROMPT_VERSION = "reasons.v1.md"
logger = logging.getLogger(__name__)

# Labels and templates are trusted code. E2 feature additions should extend
# these maps rather than copy arbitrary signal labels into fallback prose.
_LABELS = {
    "phone_return_rate": "Tỷ lệ hoàn của SĐT",
    "address_completeness": "Mức đầy đủ của địa chỉ",
    "address_missing_house_number": "Địa chỉ thiếu số nhà",
    "address_missing_ward": "Địa chỉ thiếu phường/xã",
    "address_vague": "Địa chỉ mơ hồ",
    "address_legacy_admin_names": "Địa chỉ dùng tên địa giới cũ",
    "conversation_asked_details": "Khách có hỏi kỹ về sản phẩm",
    "conversation_rushed_close": "Khách chốt đơn vội",
    "conversation_name_mismatch": "Tên trong hội thoại khác tên người đặt",
    "phone_order_count_24h": "Số đơn của SĐT trong khoảng thời gian ghi nhận",
    "order_value_vnd": "Giá trị đơn hàng",
    "order_cod_amount_vnd": "Số tiền COD của đơn hàng",
    "payment_no_deposit": "Đơn hàng chưa có tiền trả trước",
}
_BOOLEAN_TEMPLATES = {
    "address_missing_house_number": ("Địa chỉ có số nhà.", "Địa chỉ thiếu số nhà."),
    "address_missing_ward": ("Địa chỉ có phường/xã.", "Địa chỉ thiếu phường/xã."),
    "address_vague": ("Địa chỉ không mơ hồ.", "Địa chỉ mơ hồ."),
    "address_legacy_admin_names": (
        "Địa chỉ không dùng tên địa giới cũ.",
        "Địa chỉ dùng tên địa giới cũ.",
    ),
    "conversation_asked_details": (
        "Khách chưa hỏi kỹ về sản phẩm.",
        "Khách có hỏi kỹ về sản phẩm.",
    ),
    "conversation_rushed_close": ("Khách không chốt đơn vội.", "Khách chốt đơn vội."),
    "conversation_name_mismatch": (
        "Tên trong hội thoại trùng tên người đặt.",
        "Tên trong hội thoại khác tên người đặt.",
    ),
    "payment_no_deposit": ("Đơn hàng có tiền trả trước.", "Đơn hàng chưa có tiền trả trước."),
}
# This is an explicit input vocabulary, not a blacklist of possible PII names.
# E2 additions must register safe scalar features and their scoped fact names.
REASON_SIGNAL_KEYS = frozenset(_LABELS) | LOCATION_SIGNAL_KEYS
REASON_FACT_KEYS = {
    "phone_return_rate": frozenset({"past_orders", "returned_orders"}),
    "phone_order_count_24h": frozenset({"time_window_hours"}),
}


class GeminiGenerator(Protocol):
    async def generate(
        self, prompt_name: str, payload: dict, response_schema: type[BaseModel]
    ) -> BaseModel | None: ...


class ReasonsResponse(ApiModel):
    reasons: list[Reason] = Field(max_length=3)


def _safe_facts(
    facts: dict[str, dict[str, str | int | float]] | None, keys: set[str]
) -> dict[str, dict[str, str | int | float]]:
    return {
        key: {
            name: value
            for name, value in values.items()
            if name in REASON_FACT_KEYS.get(key, frozenset()) and numeric_fact(value) is not None
        }
        for key, values in (facts or {}).items()
        if key in keys
    }


def _format_number(value: int | float | Decimal) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _template(signal: Signal) -> Reason | None:
    key, value = signal.key, signal.value
    text = None
    if key in _BOOLEAN_TEMPLATES and isinstance(value, bool):
        text = _BOOLEAN_TEMPLATES[key][int(value)]
    elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        formatted = _format_number(value)
        if key == "phone_return_rate" and 0 <= value <= 1:
            percent = _format_number(Decimal(str(value)) * 100)
            text = f"SĐT này có tỷ lệ hoàn đơn trước đây là {percent}%."
        elif key == "address_completeness" and 0 <= value <= 1:
            text = f"Mức đầy đủ của địa chỉ được ghi nhận là {formatted}."
        elif key in {"order_value_vnd", "order_cod_amount_vnd"}:
            label = "COD của đơn" if key == "order_cod_amount_vnd" else "đơn hàng"
            text = f"Giá trị {label} là {formatted}đ."
        elif key == "phone_order_count_24h":
            text = f"SĐT này có {formatted} đơn trong khoảng thời gian ghi nhận."
        elif (
            key in LOCATION_SIGNAL_KEYS
            and key.endswith(("return_rate", "failure_rate"))
            and 0 <= value <= 1
        ):
            percent = _format_number(Decimal(str(value)) * 100)
            outcome = "giao thất bại" if key.endswith("failure_rate") else "hoàn đơn"
            text = f"Tỷ lệ {outcome} của khu vực là {percent}%."
    return Reason(text_vi=text, signal_keys=[key]) if text else None


async def generate_reasons(
    client: GeminiGenerator,
    signals: list[Signal],
    *,
    tier: RiskTier | None = None,
    facts: dict[str, dict[str, str | int | float]] | None = None,
    on_check: Callable[[CheckResult], None] | None = None,
) -> list[Reason]:
    """Retry dropped reasons once, preserving accepted text; fallback only if empty."""
    positive = sorted(
        [
            signal
            for signal in signals
            if signal.contribution > 0 and math.isfinite(signal.contribution)
        ],
        key=lambda signal: signal.contribution,
        reverse=True,
    )
    if not positive:
        return []
    safe_signals = [
        signal
        for signal in positive
        if signal.key in REASON_SIGNAL_KEYS
        and isinstance(signal.value, (int, float, bool))
        and (not isinstance(signal.value, float) or math.isfinite(signal.value))
    ]
    safe_facts = _safe_facts(facts, {signal.key for signal in safe_signals})
    if not safe_signals:
        return []
    payload = {
        "signals": [
            {
                "key": signal.key,
                "label_vi": mask_phone_numbers(_LABELS.get(signal.key, "Tín hiệu đã ghi nhận")),
                "value": signal.value,
            }
            for signal in safe_signals
        ],
        "facts": safe_facts,
    }

    def inspect(candidates: list[dict | Reason]) -> CheckResult:
        result = check_reasons(candidates, safe_signals, tier=tier, facts=safe_facts)
        logger.info("reason_check prompt=%s dropped=%s", PROMPT_VERSION, result.dropped)
        if on_check:
            on_check(result)
        return result

    response = await client.generate(PROMPT_VERSION, payload, ReasonsResponse)
    checked = inspect(response.reasons if isinstance(response, ReasonsResponse) else [])
    if checked.dropped:
        response = await client.generate(
            PROMPT_VERSION,
            {**payload, "rejection_notes": checked.rejection_notes},
            ReasonsResponse,
        )
        candidates = response.reasons if isinstance(response, ReasonsResponse) else []
        checked = inspect([*checked.reasons, *candidates])
    if checked.reasons:
        return checked.reasons
    templates = [reason for signal in safe_signals if (reason := _template(signal)) is not None]
    return inspect(templates).reasons
