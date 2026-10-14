"""Risk score, signals, reasons and decisions."""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.common import ApiModel, Vnd
from app.schemas.enums import (
    AddressFlag,
    ContactBlockReason,
    DecisionAction,
    HardRule,
    RiskTier,
    SignalGroup,
)


class AddressCheck(ApiModel):
    """Address quality (E3.1), stored on the order as `signals.address`. Code computes the score
    from verified flags; Gemini only reads the text, and every unit it names is checked against
    the official 2025 tables. Not part of the API responses yet."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "score": 0.95,
                    "flags": ["old_admin_name"],
                    "admin_format": "old",
                    "province": "Hồ Chí Minh",
                    "ward": "Phường Chợ Quán",
                    "old_province": None,
                    "old_district": "Quận 5",
                    "old_ward": "Phường 2",
                    "ward_candidates": [],
                    "suggested_raw": "12 Nguyễn Trãi, Phường Chợ Quán, Thành phố Hồ Chí Minh",
                    "source": "rules",
                    "version": "rules-1",
                }
            ]
        }
    )

    score: float = Field(ge=0, le=1, description="Completeness, 1 = complete.")
    flags: list[AddressFlag] = Field(default_factory=list, description="Heaviest first.")
    admin_format: Literal["new", "old", "mixed", "unknown"] = Field(
        description="Unit system the text uses: after the 1 July 2025 merger, before it, or both."
    )
    province: str | None = Field(default=None, description="Current province, when resolved.")
    ward: str | None = Field(default=None, description="Current ward, when it resolves to one.")
    old_province: str | None = Field(default=None, description="Merged-away province written.")
    old_district: str | None = Field(default=None, description="Old district written.")
    old_ward: str | None = Field(default=None, description="Pre-2025 ward written.")
    ward_candidates: list[str] = Field(
        default_factory=list,
        description="Current wards a split old ward went into; ask the buyer which one.",
    )
    suggested_raw: str | None = Field(
        default=None,
        description="The address in the current units, only when the mapping is unambiguous. "
        "A suggestion: only the buyer or staff changes the address.",
    )
    source: Literal["rules", "rules+gemini"] = "rules"
    version: str = Field(description="Rules and prompt version, to invalidate cached results.")


class Signal(ApiModel):
    """One input signal and its contribution to this order's score (model explanation)."""

    key: str = Field(examples=["phone_return_rate"])
    group: SignalGroup
    label_vi: str = Field(examples=["Tỷ lệ hoàn của SĐT"])
    value: str | float | int | bool = Field(examples=[0.5])
    contribution: float = Field(
        description="Signed contribution to the failure probability. Positive raises risk.",
        examples=[0.18],
    )


class Reason(ApiModel):
    """A plain-Vietnamese reason written by Gemini. Each reason cites the signals it is based on;
    reasons that do not match a real signal are rejected before they reach the API."""

    text_vi: str = Field(max_length=200, examples=["SĐT này đã hoàn 2 trên 4 đơn trước đây."])
    signal_keys: list[str] = Field(min_length=1, examples=[["phone_return_rate"]])


class RiskScore(ApiModel):
    """One scoring run. Editing an order before it ships creates a new run."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "scr_01",
                    "scored_at": "2026-10-09T10:15:04+07:00",
                    "status": "scored",
                    "skipped_reason": None,
                    "probability": 0.41,
                    "risk_score": 41,
                    "tier": "high",
                    "expected_loss_vnd": 24600,
                    "failed_delivery_cost_vnd": 60000,
                    "hard_rules": [],
                    "top_signals": [
                        {
                            "key": "phone_return_rate",
                            "group": "phone_history",
                            "label_vi": "Tỷ lệ hoàn của SĐT",
                            "value": 0.5,
                            "contribution": 0.18,
                        },
                        {
                            "key": "address_missing_house_number",
                            "group": "address_quality",
                            "label_vi": "Địa chỉ thiếu số nhà",
                            "value": True,
                            "contribution": 0.07,
                        },
                    ],
                    "reasons": [
                        {
                            "text_vi": "SĐT này đã hoàn 2 trên 4 đơn trước đây.",
                            "signal_keys": ["phone_return_rate"],
                        },
                        {
                            "text_vi": "Địa chỉ thiếu số nhà.",
                            "signal_keys": ["address_missing_house_number"],
                        },
                    ],
                    "model_version": "bqml-2026-10-09",
                }
            ]
        }
    )

    id: str
    scored_at: datetime
    status: Literal["scored", "skipped"] = Field(
        description="skipped when a hard rule ends scoring early (e.g. fully prepaid order)."
    )
    skipped_reason: HardRule | None = None
    probability: float | None = Field(
        default=None, ge=0, le=1, description="Probability of failed delivery."
    )
    risk_score: int | None = Field(default=None, ge=0, le=100, description="probability × 100.")
    tier: RiskTier | None = None
    expected_loss_vnd: Vnd | None = Field(
        default=None, description="probability × failed_delivery_cost_vnd, in VND."
    )
    failed_delivery_cost_vnd: Vnd = Field(
        description="Cost of one failed delivery used for this run (shop setting at the time)."
    )
    hard_rules: list[HardRule] = Field(default_factory=list)
    top_signals: list[Signal] = Field(default_factory=list, max_length=5)
    reasons: list[Reason] = Field(default_factory=list, max_length=3)
    model_version: str | None = None


class Decision(ApiModel):
    """What the decision engine chose for the current score, under the policy version in force."""

    decided_at: datetime
    action: DecisionAction
    policy_version: int = Field(ge=1)
    expected_loss_vnd: Vnd | None = None
    contact_cost_vnd: Vnd | None = Field(
        default=None, description="Cost of the chosen contact action, if any."
    )
    block_reasons: list[ContactBlockReason] = Field(
        default_factory=list, description="Why a contact was skipped or delayed."
    )
    next_action: DecisionAction | None = Field(
        default=None, description="Escalation if the buyer does not respond."
    )
    next_action_at: datetime | None = None
    decided_by: Literal["engine", "staff"] = "engine"
