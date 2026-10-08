"""AI confirmation calls and other contact attempts."""

from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.common import ApiModel, MaskedPhone
from app.schemas.enums import CallChangeField, CallOutcome, CallStatus, ContactChannel


class CallChange(ApiModel):
    """A change the buyer confirmed during the read-back."""

    order_id: str
    field: CallChangeField
    item_name: str | None = Field(default=None, description="Required for item_* fields.")
    new_value: str = Field(examples=["Số 15 ngõ 34, phường Láng, Hà Nội"])


class Call(ApiModel):
    """One AI confirmation call. Orders to the same phone within 15 minutes share one call."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "call_01",
                    "order_ids": ["ord_01"],
                    "phone_masked": "+84******001",
                    "status": "completed",
                    "attempt": 1,
                    "queued_at": "2026-10-09T10:15:06+07:00",
                    "started_at": "2026-10-09T10:15:20+07:00",
                    "ended_at": "2026-10-09T10:16:31+07:00",
                    "duration_seconds": 71,
                    "outcome": "edited",
                    "changes": [
                        {
                            "order_id": "ord_01",
                            "field": "delivery_address",
                            "item_name": None,
                            "new_value": "Số 15 ngõ 34, phường Láng, Hà Nội",
                        }
                    ],
                    "cancel_reason": None,
                    "human_callback_requested": False,
                    "buyer_requests": None,
                    "summary_vi": "Người mua nghe máy, xác nhận đơn và sửa số nhà từ 12 thành 15.",
                }
            ]
        }
    )

    id: str
    order_ids: list[str] = Field(min_length=1)
    phone_masked: MaskedPhone
    status: CallStatus
    attempt: int = Field(ge=1, le=2)
    queued_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    outcome: CallOutcome | None = Field(default=None, description="Set when status is completed.")
    changes: list[CallChange] = Field(default_factory=list)
    cancel_reason: str | None = None
    human_callback_requested: bool = False
    buyer_requests: str | None = Field(
        default=None, description="Requests the call could not handle, for the shop to follow up."
    )
    summary_vi: str | None = Field(default=None, description="One or two sentences for the shop.")


class ContactAttempt(ApiModel):
    """Any contact with the buyer about an order: call, confirmation link or deposit request."""

    id: str
    channel: ContactChannel
    created_at: datetime
    call_id: str | None = Field(default=None, description="Set when channel is ai_call.")
    link_expires_at: datetime | None = Field(
        default=None, description="Set when channel is confirmation_link (48 hours)."
    )
    responded_at: datetime | None = None
    result: str | None = Field(
        default=None,
        description="CallOutcome or BuyerAction value, depending on the channel.",
        examples=["confirmed"],
    )
