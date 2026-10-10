"""Deterministic shape, citation, numeric and policy checks for E3.3.

These checks cannot prove unrestricted natural-language claims. The 30-order
evaluation still requires a second reader to inspect every final reason.
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from app.schemas.enums import RiskTier
from app.schemas.scoring import Reason, Signal

# E2 must extend this explicit list when adding a location feature. CONTEXT also
# contains non-location features (category, season), so its group is not enough.
LOCATION_SIGNAL_KEYS = frozenset(
    {
        "province",
        "region",
        "delivery_area",
        "province_failure_rate",
        "province_return_rate",
        "region_failure_rate",
        "region_return_rate",
        "delivery_area_failure_rate",
        "delivery_area_return_rate",
        "location_failure_rate",
        "location_return_rate",
    }
)

_NUMBER = re.compile(
    r"(?<!\d)(?:\d{1,2}(?::|[hH])\d{2}|\d{1,2}[hH](?!\w)|"
    r"[+-]?\d+(?:[.,]\d+|[ \u00a0\u202f]\d{3})*)(?:\s*%)?(?!\d)"
)
_TIME = re.compile(r"(\d{1,2})(?::|[hH])(\d{2})?")
_DECISION_LANGUAGE = re.compile(
    r"\b(?:risk|score|probability|tier|high|medium|low|ship|shipping|deposit|"
    r"cancel|hold|review|call|contact|confirmation|recommend|should|must)\b|"
    r"\b(?:rui ro|nguy co|xac suat|kha nang|diem|phan tang|xep hang|"
    r"muc (?:rat )?(?:cao|thap|trung binh)|goi|coc|huy|gui|xac nhan|"
    r"cho duyet|nen|yeu cau|de nghi)\b"
)

# Recognition of concrete claims reduces obvious semantic contradictions. It
# does not replace the human evaluation of synonyms or unfamiliar feature keys.
_BOOLEAN_CLAIMS = {
    "address_missing_house_number": "thieu so nha",
    "address_missing_ward": "thieu phuong",
    "address_vague": "mo ho",
    "address_legacy_admin_names": "dia gioi cu",
    "conversation_asked_details": "hoi ky",
    "conversation_rushed_close": "chot don voi",
    "conversation_name_mismatch": "khac ten",
    "payment_no_deposit": "chua co tien tra truoc",
}


@dataclass
class CheckResult:
    reasons: list[Reason] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    rejection_notes: list[str] = field(default_factory=list)


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(unaccented.split())


def _numeric_value(token: str) -> tuple[str, Decimal] | None:
    token = token.strip()
    time = _TIME.fullmatch(token)
    if time:
        hour, minute = int(time[1]), int(time[2] or 0)
        if hour < 24 and minute < 60:
            return "time", Decimal(hour * 60 + minute)
        return None
    percent = token.endswith("%")
    token = token.removesuffix("%").strip()
    token = re.sub(r"[ \u00a0\u202f]", "", token)
    # Repeated groups, or a single three-digit suffix, are thousands separators.
    # All other single separators are decimal marks (Vietnamese comma included).
    if re.fullmatch(r"[+-]?[1-9]\d{0,2}(?:[.,]\d{3})+", token):
        token = token.replace(".", "").replace(",", "")
    elif "," in token and "." in token:
        token = token.replace(".", "").replace(",", ".")
    else:
        token = token.replace(",", ".")
    try:
        number = Decimal(token)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return "number", number / 100 if percent else number


def numeric_fact(value: str | int | float | bool) -> tuple[str, Decimal] | None:
    """Only complete numeric/time strings count; never extract numbers from prose."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return ("number", parsed) if parsed.is_finite() else None
    if _NUMBER.fullmatch(value.strip()):
        return _numeric_value(value)
    return None


def _has_contradiction(text: str, keys: list[str], signals: dict[str, Signal]) -> bool:
    plain = _plain(text)
    for key, claim in _BOOLEAN_CLAIMS.items():
        if claim not in plain:
            continue
        # A familiar claim cannot borrow another feature's citation, even when
        # its own feature is present elsewhere on the order.
        if key not in keys:
            return True
        value = signals[key].value
        if not isinstance(value, bool):
            return True
        preceding = plain[: plain.index(claim)].split()[-3:]
        negated = "khong" in preceding or "chua" in preceding
        if key == "payment_no_deposit":
            negated = False  # The registered claim already contains its negative.
        if (not value and not negated) or (value and negated):
            return True
    return False


def check_reasons(
    candidates: list[dict | Reason],
    signals: list[Signal],
    *,
    tier: RiskTier | None = None,
    facts: dict[str, dict[str, str | int | float]] | None = None,
) -> CheckResult:
    """Drop invalid reasons; keep at most three in contribution order.

    Rejection notes contain rule IDs only, so retry prompts and logs never copy
    a model response that could contain personal information or instructions.
    """
    by_key = {
        signal.key: signal
        for signal in signals
        if signal.contribution > 0 and math.isfinite(signal.contribution)
    }
    kept: list[Reason] = []
    seen: set[frozenset[str]] = set()
    dropped: Counter[str] = Counter()

    def reject(rule: str, count: int = 1) -> None:
        if count:
            dropped[rule] += count

    for candidate in candidates:
        try:
            reason = (
                candidate if isinstance(candidate, Reason) else Reason.model_validate(candidate)
            )
        except (ValidationError, TypeError):
            reject("shape")
            continue
        if not reason.text_vi.strip() or not all(key.strip() for key in reason.signal_keys):
            reject("shape")
            continue
        if any(key not in by_key for key in reason.signal_keys):
            reject("unknown_signal")
            continue
        if _DECISION_LANGUAGE.search(_plain(reason.text_vi)):
            reject("decision_language")
            continue
        if _has_contradiction(reason.text_vi, reason.signal_keys, by_key):
            reject("contradicted_signal")
            continue
        allowed = set()
        for key in reason.signal_keys:
            values = [by_key[key].value, *(facts or {}).get(key, {}).values()]
            allowed.update(
                parsed for value in values if (parsed := numeric_fact(value)) is not None
            )
            if "hour" in key and isinstance(by_key[key].value, (int, float)):
                allowed.add(("time", Decimal(str(by_key[key].value)) * 60))
        if any(
            _numeric_value(match[0]) not in allowed for match in _NUMBER.finditer(reason.text_vi)
        ):
            reject("unsupported_number")
            continue
        cited = frozenset(reason.signal_keys)
        if cited in seen:
            reject("duplicate_signals")
            continue
        seen.add(cited)
        kept.append(reason)

    def contribution(reason: Reason) -> float:
        return sum(by_key[key].contribution for key in set(reason.signal_keys))

    kept.sort(key=contribution, reverse=True)
    if tier in (RiskTier.HIGH, RiskTier.VERY_HIGH):
        non_location = [
            reason
            for reason in kept
            if any(key not in LOCATION_SIGNAL_KEYS for key in reason.signal_keys)
        ]
        if not non_location:
            reject("location_only", len(kept))
            kept = []
        elif not any(reason in non_location for reason in kept[:3]):
            kept = [*kept[:2], non_location[0], *[r for r in kept[2:] if r != non_location[0]]]
    if len(kept) > 3:
        reject("count", len(kept) - 3)
    return CheckResult(kept[:3], dict(dropped), list(dropped))
