"""Orders: create, list, detail, edit, override, import."""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.calls import Call, ContactAttempt
from app.schemas.common import Address, ApiModel, Currency, Phone, Vnd
from app.schemas.enums import DecisionAction, OrderStatus, RiskTier, SalesChannel
from app.schemas.scoring import Decision, RiskScore

_ITEM_EXAMPLE = {
    "sku": "AT-123-M",
    "name": "Basic T-shirt",
    "variant": "Size M, black",
    "quantity": 2,
    "unit_price_vnd": 150000,
}

_CREATE_EXAMPLE = {
    "external_id": "FB-20261009-0042",
    "channel": "facebook",
    "buyer_name": "Nguyễn Văn A",
    "buyer_phone": "+84000000001",
    "is_gift": False,
    "recipient_name": None,
    "recipient_phone": None,
    "address": {
        "raw": "Số 12 ngõ 34, phường Láng, Hà Nội",
        "street": "Số 12 ngõ 34",
        "ward": "Phường Láng",
        "province": "Hà Nội",
    },
    "items": [_ITEM_EXAMPLE],
    "shipping_fee_vnd": 30000,
    "discount_vnd": 0,
    "prepaid_vnd": 0,
    "placed_at": "2026-10-09T10:15:00+07:00",
    "conversation_text": "Buyer: do you still have size M in black? Shop: yes. Buyer: I'll take 2.",
    "note": None,
}


class OrderItem(ApiModel):
    sku: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    variant: str | None = Field(default=None, max_length=100)
    quantity: int = Field(ge=1, le=999)
    unit_price_vnd: Vnd


class OrderCreate(ApiModel):
    """New COD order, from the web app, a file import row or the intake API."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [_CREATE_EXAMPLE]})

    external_id: str | None = Field(
        default=None,
        max_length=100,
        description="Order ID in the seller's system. Unique per shop; repeats are ignored.",
    )
    channel: SalesChannel
    buyer_name: str = Field(min_length=1, max_length=100)
    buyer_phone: Phone
    is_gift: bool = Field(
        default=False, description="Gift orders are verified with the buyer, never the recipient."
    )
    recipient_name: str | None = Field(default=None, max_length=100)
    recipient_phone: Phone | None = Field(default=None, description="Never contacted.")
    address: Address
    items: list[OrderItem] = Field(min_length=1, max_length=50)
    shipping_fee_vnd: Vnd = 0
    discount_vnd: Vnd = 0
    prepaid_vnd: Vnd = Field(default=0, description="Amount already paid (deposit or prepaid).")
    placed_at: datetime
    conversation_text: str | None = Field(
        default=None, max_length=5000, description="Sales chat that closed the order, if any."
    )
    note: str | None = Field(default=None, max_length=500)
    currency: Currency | None = Field(
        default=None,
        description="Currency of every amount in the order. Defaults to the branch's currency "
        "(set by the intake key); a different one is rejected.",
    )


class OrderUpdate(ApiModel):
    """Edit before shipping. Any change triggers a new scoring run."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "address": {
                        "raw": "Số 15 ngõ 34, phường Láng, Hà Nội",
                        "street": "Số 15 ngõ 34",
                        "ward": "Phường Láng",
                        "province": "Hà Nội",
                    }
                }
            ]
        },
    )

    buyer_name: str | None = Field(default=None, min_length=1, max_length=100)
    buyer_phone: Phone | None = None
    recipient_name: str | None = Field(default=None, max_length=100)
    address: Address | None = None
    items: list[OrderItem] | None = Field(default=None, min_length=1, max_length=50)
    prepaid_vnd: Vnd | None = None
    note: str | None = Field(default=None, max_length=500)


class OrderSummary(ApiModel):
    """Row in the order inbox."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "ord_01",
                    "external_id": "FB-20261009-0042",
                    "channel": "facebook",
                    "buyer_name": "Nguyễn Văn A",
                    "buyer_phone": "+84000000001",
                    "is_gift": False,
                    "total_vnd": 330000,
                    "cod_amount_vnd": 330000,
                    "status": "awaiting_confirmation",
                    "tier": "high",
                    "risk_score": 41,
                    "current_action": "ai_call",
                    "placed_at": "2026-10-09T10:15:00+07:00",
                    "updated_at": "2026-10-09T10:16:31+07:00",
                }
            ]
        }
    )

    id: str
    external_id: str | None = None
    branch_id: str | None = Field(default=None, description="Branch that took the order.")
    country: str | None = Field(default=None, description="Country of the branch (VN, SG, PH).")
    currency: Currency = Field(default="VND", description="Currency of every amount.")
    channel: SalesChannel
    buyer_name: str
    buyer_phone: Phone
    is_gift: bool
    total_vnd: Vnd = Field(description="Items − discount + shipping fee.")
    cod_amount_vnd: Vnd = Field(description="Amount still to collect: total − prepaid.")
    status: OrderStatus
    tier: RiskTier | None = Field(default=None, description="Null until scored or when skipped.")
    risk_score: int | None = Field(default=None, ge=0, le=100)
    current_action: DecisionAction | None = None
    suggested_action: DecisionAction | None = Field(
        default=None,
        description="An AI call waiting for the shop to confirm it (call automation).",
    )
    placed_at: datetime
    updated_at: datetime


class OrderEvent(ApiModel):
    """Timeline entry on the order page. Overrides and policy-driven decisions also go to the
    audit log."""

    at: datetime
    type: Literal[
        "created",
        "scored",
        "decided",
        "contact_started",
        "call_completed",
        "buyer_responded",
        "edited",
        "override",
        "status_changed",
        "delivery_result",
    ]
    actor: str = Field(
        description="system, buyer, or the staff member's email.", examples=["system"]
    )
    message_vi: str = Field(examples=["Scored 41/100 (High)."])
    reason: str | None = Field(default=None, description="Required reason for overrides.")


def _detail_example() -> dict:
    score = RiskScore.model_config["json_schema_extra"]["examples"][0]
    call = Call.model_config["json_schema_extra"]["examples"][0]
    return {
        **OrderSummary.model_config["json_schema_extra"]["examples"][0],
        "recipient_name": None,
        "recipient_phone": None,
        "address": _CREATE_EXAMPLE["address"],
        "items": [_ITEM_EXAMPLE],
        "shipping_fee_vnd": 30000,
        "discount_vnd": 0,
        "prepaid_vnd": 0,
        "note": None,
        "current_score": score,
        "score_history": [score],
        "decision": {
            "decided_at": "2026-10-09T10:15:05+07:00",
            "action": "ai_call",
            "policy_version": 1,
            "expected_loss_vnd": 24600,
            "contact_cost_vnd": 1500,
            "block_reasons": [],
            "next_action": "hold_for_review",
            "next_action_at": "2026-10-09T10:45:05+07:00",
            "decided_by": "engine",
        },
        "contacts": [
            {
                "id": "cnt_01",
                "channel": "ai_call",
                "created_at": "2026-10-09T10:15:06+07:00",
                "call_id": "call_01",
                "link_expires_at": None,
                "responded_at": "2026-10-09T10:16:31+07:00",
                "result": "edited",
            }
        ],
        "calls": [call],
        "timeline": [
            {
                "at": "2026-10-09T10:16:31+07:00",
                "type": "call_completed",
                "actor": "system",
                "message_vi": "AI call: address changed.",
                "reason": None,
            },
            {
                "at": "2026-10-09T10:15:05+07:00",
                "type": "decided",
                "actor": "system",
                "message_vi": "Decision: confirm by AI call.",
                "reason": None,
            },
            {
                "at": "2026-10-09T10:15:04+07:00",
                "type": "scored",
                "actor": "system",
                "message_vi": "Scored 41/100 (High).",
                "reason": None,
            },
        ],
        "allowed_overrides": ["ship_now", "require_deposit", "hold_for_review", "cancel"],
    }


class OrderDetail(OrderSummary):
    """Everything the order page shows."""

    model_config = ConfigDict(json_schema_extra={"examples": [_detail_example()]})

    recipient_name: str | None = None
    recipient_phone: Phone | None = None
    address: Address
    items: list[OrderItem]
    shipping_fee_vnd: Vnd
    discount_vnd: Vnd
    prepaid_vnd: Vnd
    note: str | None = None
    current_score: RiskScore | None = None
    score_history: list[RiskScore] = Field(
        default_factory=list, description="All scoring runs, newest first."
    )
    decision: Decision | None = None
    contacts: list[ContactAttempt] = Field(default_factory=list)
    calls: list[Call] = Field(default_factory=list)
    timeline: list[OrderEvent] = Field(default_factory=list, description="Newest first.")
    allowed_overrides: list[DecisionAction] = Field(
        default_factory=list, description="Actions staff may apply now, given the status."
    )


class TimersRun(ApiModel):
    """What one run of the no-response timers did (app/decision/timers.py)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"handled": 3}]})

    handled: int = Field(ge=0, description="Orders whose timer was due and ran.")


class OrdersChange(ApiModel):
    """When the shop's orders last changed: the inbox polls it and reloads only on a change."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"updated_at": "2026-10-16T13:05:12+07:00"}]}
    )

    updated_at: datetime | None = Field(description="Null while the shop has no orders.")


class OrderPage(ApiModel):
    items: list[OrderSummary]
    next_cursor: str | None = Field(default=None, description="Pass as `cursor` for the next page.")
    total: int = Field(ge=0, description="Orders matching the filters.")


class OverrideRequest(ApiModel):
    """Staff decision that replaces the engine's. Recorded in the audit log."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"action": "ship_now", "reason": "Regular buyer, confirmed by phone on Zalo."}
            ]
        },
    )

    action: DecisionAction
    reason: str = Field(min_length=3, max_length=500)


class ImportRowError(ApiModel):
    row: int = Field(ge=1, description="1-based row number in the file, header excluded.")
    field: str | None = None
    message: str


class ImportResult(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "received": 1000,
                    "imported": 996,
                    "duplicates": 2,
                    "rejected": [
                        {"row": 17, "field": "buyer_phone", "message": "Invalid phone number"}
                    ],
                }
            ]
        }
    )

    received: int = Field(ge=0)
    imported: int = Field(ge=0)
    duplicates: int = Field(ge=0, description="Rows whose external_id already exists.")
    rejected: list[ImportRowError] = Field(default_factory=list)


class IntakeAccepted(ApiModel):
    """Order accepted from an external sales tool, with its current lifecycle status.

    Scoring and the first decision are saved when a model is available. Otherwise the
    order remains new and unscored.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"order_id": "ord_01", "status": "new", "duplicate": False}]
        }
    )

    order_id: str
    status: OrderStatus
    duplicate: bool = Field(description="True if this external_id was already received.")
