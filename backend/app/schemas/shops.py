"""Current user, shop settings and tier policy."""

from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.common import ApiModel, Vnd
from app.schemas.enums import DecisionAction, RiskTier, Role

_HHMM = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class Me(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "usr_01",
                    "email": "owner@example.com",
                    "display_name": "Chủ shop",
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
                    "name": "Shop Thời Trang Mẫu",
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
                }
            ]
        }
    )

    version: int = Field(ge=1)
    effective_from: datetime
    updated_by: str
    tiers: list[TierPolicy] = Field(min_length=4, max_length=4)


class PolicyUpdate(ApiModel):
    """Owner only. Must list all four tiers."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"tiers": _DEFAULT_TIERS}]}
    )

    tiers: list[TierPolicy] = Field(min_length=4, max_length=4)


ShopUpdate.model_rebuild()
