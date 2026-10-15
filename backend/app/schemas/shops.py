"""Current user, shop settings and tier policy."""

from datetime import datetime

from pydantic import ConfigDict, Field, model_validator

from app.schemas.common import ApiModel, Currency, Vnd
from app.schemas.enums import (
    CallAutomationMode,
    DecisionAction,
    RiskTier,
    Role,
    SalesChannel,
    Weekday,
)

_HHMM = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class Me(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "usr_01",
                    "email": "owner@example.com",
                    "display_name": "Shop owner",
                    "role": "owner",
                    "shop_id": "shp_01",
                }
            ]
        }
    )

    user_id: str
    email: str
    display_name: str | None = None
    role: Role
    shop_id: str


class ContactHours(ApiModel):
    """Window when the buyer may be contacted, Vietnam time (Asia/Ho_Chi_Minh)."""

    start: str = Field(default="08:00", pattern=_HHMM)
    end: str = Field(default="21:00", pattern=_HHMM)


class ShopSettings(ApiModel):
    """Costs used for expected-loss decisions, and contact rules the shop can tune."""

    failed_delivery_cost_vnd: Vnd = Field(
        default=60000, description="Cost of one failed delivery: two-way shipping plus handling."
    )
    ai_call_cost_vnd: Vnd = Field(default=1500, description="Cost of one AI call.")
    confirmation_link_cost_vnd: Vnd = Field(default=300, description="Cost of sending one link.")
    deposit_request_cost_vnd: Vnd = Field(
        default=5000, description="Estimated cost of asking for a deposit (lost conversions)."
    )
    contact_hours: ContactHours = Field(default_factory=ContactHours)


class Shop(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "shp_01",
                    "name": "Sample Fashion Shop",
                    "created_at": "2026-10-09T09:00:00+07:00",
                    "settings": {
                        "failed_delivery_cost_vnd": 60000,
                        "ai_call_cost_vnd": 1500,
                        "confirmation_link_cost_vnd": 300,
                        "deposit_request_cost_vnd": 5000,
                        "contact_hours": {"start": "08:00", "end": "21:00"},
                    },
                    "intake_api_key_last4": "a1b2",
                }
            ]
        }
    )

    id: str
    name: str
    created_at: datetime
    settings: ShopSettings
    intake_api_key_last4: str | None = Field(
        default=None, description="Last 4 characters of the intake API key."
    )


class ShopUpdate(ApiModel):
    """Owner only. Fields left out are unchanged."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"settings": {"failed_delivery_cost_vnd": 65000}}]},
    )

    name: str | None = Field(default=None, min_length=1, max_length=100)
    settings: "ShopSettingsUpdate | None" = None


class ShopSettingsUpdate(ApiModel):
    failed_delivery_cost_vnd: Vnd | None = None
    ai_call_cost_vnd: Vnd | None = None
    confirmation_link_cost_vnd: Vnd | None = None
    deposit_request_cost_vnd: Vnd | None = None
    contact_hours: ContactHours | None = None


class TierPolicy(ApiModel):
    tier: RiskTier
    action: DecisionAction
    if_no_response: DecisionAction | None = Field(
        default=None, description="Escalation when the buyer does not respond."
    )
    no_response_after_minutes: int | None = Field(default=None, ge=1, le=2880)


_DEFAULT_AUTOMATION = {
    "mode": "auto",
    "min_risk_score": None,
    "cod_ranges": [],
    "channels": None,
    "branches": None,
    "call_window": None,
    "max_attempts": 2,
    "retry_after_minutes": 30,
}

_DEFAULT_TIERS = [
    {
        "tier": "low",
        "action": "ship_now",
        "if_no_response": None,
        "no_response_after_minutes": None,
    },
    {
        "tier": "medium",
        "action": "send_confirmation_link",
        "if_no_response": "ai_call",
        "no_response_after_minutes": 120,
    },
    {
        "tier": "high",
        "action": "ai_call",
        "if_no_response": "hold_for_review",
        "no_response_after_minutes": 30,
    },
    {
        "tier": "very_high",
        "action": "require_deposit",
        "if_no_response": "hold_for_review",
        "no_response_after_minutes": 1440,
    },
]


class CallWindow(ApiModel):
    """When the agent may start an AI call by itself, in the branch's local time. It must lie
    inside the contact hours every call obeys (08:00-21:00)."""

    start: str = Field(default="08:00", pattern=_HHMM)
    end: str = Field(default="21:00", pattern=_HHMM, description="Exclusive.")
    days: list[Weekday] = Field(default_factory=lambda: list(Weekday), min_length=1)

    @model_validator(mode="after")
    def _inside_contact_hours(self):
        if not "08:00" <= self.start < self.end <= "21:00":
            raise ValueError("the call window must lie inside 08:00-21:00, start before end")
        return self


class CodRange(ApiModel):
    """Auto-call only orders whose amount to collect is in this range, for one currency. Amounts
    in the currency's minor unit; a missing bound is open."""

    currency: Currency
    min_cod: Vnd | None = None
    max_cod: Vnd | None = None

    @model_validator(mode="after")
    def _ordered(self):
        if self.min_cod is not None and self.max_cod is not None and self.min_cod > self.max_cod:
            raise ValueError("min_cod must not be above max_cod")
        return self


class CallAutomation(ApiModel):
    """When the agent places an AI call by itself. The engine still scores every order and picks
    the action; an AI call outside these rules is not placed but suggested: the order waits in
    review with `suggested_action: ai_call` until the shop confirms the call
    (`POST /orders/{id}/calls`) or chooses something else. The defaults are the tier policy as it
    was: every call the engine picks is placed. Contact protection (contact hours, one call per
    phone per day, blocked phones) applies to every call on top of these rules."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "mode": "auto",
                    "min_risk_score": 60,
                    "cod_ranges": [{"currency": "VND", "min_cod": 200000, "max_cod": 5000000}],
                    "channels": ["facebook", "tiktok", "zalo"],
                    "branches": None,
                    "call_window": {
                        "start": "09:00",
                        "end": "20:00",
                        "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
                    },
                    "max_attempts": 2,
                    "retry_after_minutes": 45,
                }
            ]
        }
    )

    mode: CallAutomationMode = CallAutomationMode.AUTO
    min_risk_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Auto-call orders scoring at least this (0-100): a ship-now or link decision "
        "becomes an AI call when the call pays for itself, and an AI call below it is only "
        "suggested. Null keeps the tier policy.",
    )
    cod_ranges: list[CodRange] = Field(
        default_factory=list,
        description="Per currency; a currency without a range is not limited.",
    )
    channels: list[SalesChannel] | None = Field(
        default=None, description="Sales channels to auto-call. Null: all."
    )
    branches: list[str] | None = Field(
        default=None,
        description="Branch IDs to auto-call (config/branches.yaml). Null: all.",
    )
    call_window: CallWindow | None = Field(
        default=None, description="Null: whenever contact hours allow."
    )
    max_attempts: int = Field(
        default=2, ge=1, le=2, description="AI calls the agent makes per order (at most 2)."
    )
    retry_after_minutes: int = Field(
        default=30, ge=30, le=1440, description="Wait before the next call (at least 30)."
    )

    @model_validator(mode="after")
    def _one_range_per_currency(self):
        currencies = [r.currency for r in self.cod_ranges]
        if len(currencies) != len(set(currencies)):
            raise ValueError("cod_ranges lists a currency twice")
        return self


class Policy(ApiModel):
    """Tier policy. A change creates a new version that applies only to decisions made after
    `effective_from`."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "version": 1,
                    "effective_from": "2026-10-09T09:00:00+07:00",
                    "updated_by": "owner@example.com",
                    "tiers": _DEFAULT_TIERS,
                    "automation": _DEFAULT_AUTOMATION,
                }
            ]
        }
    )

    version: int = Field(ge=1)
    effective_from: datetime
    updated_by: str
    tiers: list[TierPolicy] = Field(min_length=4, max_length=4)
    automation: CallAutomation = Field(default_factory=CallAutomation)


class PolicyUpdate(ApiModel):
    """Owner only. Must list all four tiers; `automation` left out means the defaults."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tiers": _DEFAULT_TIERS,
                    "automation": CallAutomation.model_config["json_schema_extra"]["examples"][0],
                }
            ]
        },
    )

    tiers: list[TierPolicy] = Field(min_length=4, max_length=4)
    automation: CallAutomation = Field(default_factory=CallAutomation)


ShopUpdate.model_rebuild()
