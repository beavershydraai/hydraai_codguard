"""Risk score, signals, reasons and decisions."""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.common import ApiModel, Vnd
from app.schemas.enums import ContactBlockReason, DecisionAction, HardRule, RiskTier, SignalGroup


class Signal(ApiModel):
    """One input signal and its contribution to this order's score (model explanation)."""

    key: str = Field(examples=["phone_return_rate"])
    group: SignalGroup
    label_vi: str = Field(examples=["Return rate of the phone"])
    value: str | float | int | bool = Field(examples=[0.5])
    contribution: float = Field(
        description="Signed contribution to the failure probability. Positive raises risk.",
        examples=[0.18],
    )


class Reason(ApiModel):
    """A plain-English reason written by Gemini. Each reason cites the signals it is based on;
    reasons that do not match a real signal are rejected before they reach the API."""

    text_vi: str = Field(max_length=200, examples=["This phone returned 2 of its 4 past orders."])
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
                            "label_vi": "Return rate of the phone",
                            "value": 0.5,
                            "contribution": 0.18,
                        },
                        {
                            "key": "address_missing_house_number",
                            "group": "address_quality",
                            "label_vi": "Address missing a house number",
                            "value": True,
                            "contribution": 0.07,
                        },
                    ],
                    "reasons": [
                        {
                            "text_vi": "This phone returned 2 of its 4 past orders.",
                            "signal_keys": ["phone_return_rate"],
                        },
                        {
                            "text_vi": "The address is missing a house number.",
                            "signal_keys": ["address_missing_house_number"],
                        },
                    ],
                    "model_version": "v20261015173450",
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
    suggested_action: DecisionAction | None = Field(
        default=None,
        description="An AI call the engine chose but the shop's call automation leaves to the "
        "shop: the order waits in review, and `block_reasons` say why it was not placed.",
    )
    decided_by: Literal["engine", "staff"] = "engine"
