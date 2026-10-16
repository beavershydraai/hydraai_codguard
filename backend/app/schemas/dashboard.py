"""ROI dashboard and backtest results. Predicted figures are estimates (UI label: "estimated")."""

from datetime import date, datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.common import ApiModel, Currency, Vnd
from app.schemas.enums import DecisionAction


class ActionCount(ApiModel):
    action: DecisionAction
    count: int = Field(ge=0)


class DashboardSummary(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "period_from": "2026-10-01",
                    "period_to": "2026-10-09",
                    "orders_screened": 2700,
                    "actions": [
                        {"action": "ship_now", "count": 2150},
                        {"action": "send_confirmation_link", "count": 320},
                        {"action": "ai_call", "count": 180},
                        {"action": "require_deposit", "count": 30},
                        {"action": "hold_for_review", "count": 20},
                    ],
                    "cancelled_before_ship": 64,
                    "delivered": 2410,
                    "delivery_failed": 96,
                    "estimated_savings_vnd": 3840000,
                    "good_orders_contacted_rate": 0.12,
                }
            ]
        }
    )

    period_from: date
    period_to: date
    orders_screened: int = Field(ge=0)
    actions: list[ActionCount]
    cancelled_before_ship: int = Field(ge=0)
    delivered: int = Field(ge=0)
    delivery_failed: int = Field(ge=0, description="Buyer-caused failures only.")
    estimated_savings_vnd: int = Field(
        description="Estimate (UI label 'estimated'). May be negative."
    )
    good_orders_contacted_rate: float = Field(
        ge=0, le=1, description="Share of orders that were delivered fine but still contacted."
    )


PolicyName = Literal[
    "cod_guard", "phone_history_only", "call_everyone", "do_nothing", "deposit_all"
]


class LiftPoint(ApiModel):
    contacted_share: float = Field(ge=0, le=1, description="Share of orders contacted (x).")
    failures_caught_share: float = Field(
        ge=0, le=1, description="Share of failed deliveries among contacted orders (y)."
    )


class LiftSeries(ApiModel):
    policy: PolicyName
    points: list[LiftPoint]


class PolicyComparison(ApiModel):
    policy: PolicyName
    contact_rate: float = Field(ge=0, le=1)
    failures_caught_rate: float = Field(ge=0, le=1)
    monthly_savings_vnd: int = Field(
        description="Estimate (UI label 'estimated') for orders_per_day."
    )


class BacktestResult(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "generated_at": "2026-10-15T20:00:00+07:00",
                    "dataset": "public-ecommerce-cod-sample",
                    "orders": 48000,
                    "orders_per_day": 300,
                    "failed_delivery_cost_vnd": 60000,
                    "lift": [
                        {
                            "policy": "cod_guard",
                            "points": [
                                {"contacted_share": 0.1, "failures_caught_share": 0.42},
                                {"contacted_share": 0.2, "failures_caught_share": 0.63},
                            ],
                        },
                        {
                            "policy": "phone_history_only",
                            "points": [
                                {"contacted_share": 0.1, "failures_caught_share": 0.21},
                                {"contacted_share": 0.2, "failures_caught_share": 0.33},
                            ],
                        },
                    ],
                    "comparison": [
                        {
                            "policy": "do_nothing",
                            "contact_rate": 0,
                            "failures_caught_rate": 0,
                            "monthly_savings_vnd": 0,
                        },
                        {
                            "policy": "call_everyone",
                            "contact_rate": 1,
                            "failures_caught_rate": 0.7,
                            "monthly_savings_vnd": 9100000,
                        },
                        {
                            "policy": "cod_guard",
                            "contact_rate": 0.2,
                            "failures_caught_rate": 0.63,
                            "monthly_savings_vnd": 18300000,
                        },
                    ],
                }
            ]
        }
    )

    generated_at: datetime
    country: str = Field(default="VN", description="Country of the model (VN, SG, PH).")
    currency: Currency = Field(default="VND", description="Currency of every amount.")
    dataset: str
    orders: int = Field(ge=0)
    orders_per_day: int = Field(ge=1, description="Shop size used for the savings estimate.")
    failed_delivery_cost_vnd: Vnd
    lift: list[LiftSeries]
    comparison: list[PolicyComparison]


class ModelHealth(ApiModel):
    """How a country's risk model is doing, in plain words for the shop owner (app/risk/health.py).
    "Update" means the model learns again from all orders with a delivery result."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "country": "VN",
                    "status": "update_recommended",
                    "reasons": ["1,240 orders got a delivery result since it last learned."],
                    "trained_at": "2026-10-15T17:34:50Z",
                    "training_orders": 7677,
                    "lift_top20": 3.33,
                    "checked_at": "2026-10-16T19:00:30Z",
                    "new_outcomes": 1240,
                    "updating": False,
                }
            ]
        }
    )

    country: Literal["VN", "SG", "PH"]
    status: Literal["up_to_date", "update_recommended", "no_model"]
    reasons: list[str] = Field(default_factory=list, description="Why an update is recommended.")
    trained_at: datetime | None = Field(default=None, description="When the model last learned.")
    training_orders: int | None = Field(default=None, description="Orders it learned from.")
    lift_top20: float | None = Field(
        default=None,
        description="Among the 20 % riskiest orders it flags, how many times more failed "
        "deliveries than in a random 20 % (on orders it did not learn from).",
    )
    checked_at: datetime | None = Field(default=None, description="Last daily check.")
    new_outcomes: int | None = Field(
        default=None, description="Orders with a delivery result since it last learned."
    )
    updating: bool = Field(default=False, description="An update is running.")
