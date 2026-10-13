"""Contract between the backend and the call controller on the Asterisk VM.

See docs/call-controller.md. The backend publishes a CallJob to the Pub/Sub topic `call-jobs`;
the controller reports progress and the final result through the internal endpoints.
"""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from app.schemas.calls import CallChange
from app.schemas.common import ApiModel, Vnd
from app.schemas.enums import (
    CallAgent,
    CallFailureReason,
    CallInputMethod,
    CallLanguage,
    CallOutcome,
    CallTargetKind,
)

ControllerId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9-]+$",
        description="Which controller sent this. Set from CONTROLLER_ID.",
        examples=["codguard-asterisk"],
    ),
]


class CallTarget(ApiModel):
    """Where the controller dials."""

    kind: CallTargetKind
    address: str = Field(
        min_length=1,
        max_length=64,
        description="sip: extension. webrtc: browser session ID. pstn: E.164 number.",
        examples=["6001"],
    )


class CallBuyer(ApiModel):
    full_name: str = Field(max_length=100, description="Name on the order, for the identity check.")
    salutation: Literal["anh", "chị", ""] = Field(
        default="",
        description='"anh" or "chị" when the shop knows it; empty means "quý khách".',
    )


class CallItem(ApiModel):
    name: str = Field(max_length=200)
    variant: str = Field(default="", max_length=200)
    quantity: int = Field(ge=1)


class CallOrder(ApiModel):
    """One order on the call. `order_id` and the `_vnd` amounts are for the controller only and
    never go into the Gemini instruction; the `_spoken` fields are read out word for word."""

    order_id: str = Field(description="Internal ID. Used to map changes back; never spoken.")
    ref: str = Field(max_length=20, description="Short code the buyer can recognise.")
    placed_at_spoken: str = Field(max_length=100)
    items: list[CallItem] = Field(min_length=1)
    cod_amount_vnd: Vnd = Field(description="Amount still to collect.")
    cod_amount_spoken: str = Field(max_length=200)
    deposit_paid_vnd: Vnd = 0
    deposit_paid_spoken: str = Field(default="", max_length=200)
    recipient_name: str = Field(max_length=100)
    delivery_address: str = Field(max_length=500)
    is_gift: bool = False
    expected_delivery_spoken: str = Field(default="", max_length=100)


class CallJob(ApiModel):
    """Message on the Pub/Sub topic `call-jobs`: one per call attempt.

    Attributes on the message: `env`, `call_id`, `target_kind`, `agent`. Subscriptions filter on
    `env`. The controller claims the job with `report_call_status` (dialing) before it acks."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "call_id": "call_01",
                    "attempt": 1,
                    "env": "demo",
                    "target": {"kind": "sip", "address": "6001"},
                    "agent": "script",
                    "language": "vi",
                    "script": "confirm-v1",
                    "shop_name": "Tiệm Mẫu",
                    "buyer": {"full_name": "Nguyễn Thị B", "salutation": "chị"},
                    "orders": [
                        {
                            "order_id": "ord_01",
                            "ref": "4721",
                            "placed_at_spoken": "tối ngày 7 tháng 10",
                            "items": [
                                {
                                    "name": "Áo khoác gió",
                                    "variant": "màu đen, size M",
                                    "quantity": 1,
                                }
                            ],
                            "cod_amount_vnd": 450000,
                            "cod_amount_spoken": "bốn trăm năm mươi nghìn đồng",
                            "deposit_paid_vnd": 0,
                            "deposit_paid_spoken": "",
                            "recipient_name": "Nguyễn Thị B",
                            "delivery_address": "Số 12 ngõ 34 phố Mẫu, phường Thử Nghiệm, Hà Nội",
                            "is_gift": False,
                            "expected_delivery_spoken": "2 đến 3 ngày sau khi gửi hàng",
                        }
                    ],
                    "total_cod_amount_vnd": 450000,
                    "total_cod_amount_spoken": "bốn trăm năm mươi nghìn đồng",
                    "ring_timeout_seconds": 30,
                    "max_duration_seconds": 300,
                    "created_at": "2026-10-13T10:15:06+07:00",
                }
            ]
        }
    )

    call_id: str
    attempt: int = Field(ge=1, le=2)
    env: str = Field(
        pattern=r"^(demo|dev-[a-z0-9-]{1,30})$",
        description="Which controller takes the job: `demo` for the VM, `dev-<name>` for a "
        "developer's own controller.",
    )
    target: CallTarget
    agent: CallAgent
    language: CallLanguage
    script: str = Field(
        default="confirm-v1",
        pattern=r"^[a-z0-9-]+$",
        description="Script ID when agent is script (backend/voice/scripts/).",
    )
    shop_name: str = Field(max_length=100)
    buyer: CallBuyer
    orders: list[CallOrder] = Field(
        min_length=1, description="Orders to the same phone within 15 minutes share one call."
    )
    total_cod_amount_vnd: Vnd
    total_cod_amount_spoken: str = Field(max_length=200)
    ring_timeout_seconds: int = Field(default=30, ge=10, le=60)
    max_duration_seconds: int = Field(default=300, ge=60, le=600)
    created_at: datetime


class CallStatusUpdate(ApiModel):
    """Progress of a call. `dialing` claims the call; `in_progress` means the buyer answered."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "dialing",
                    "at": "2026-10-13T10:15:08+07:00",
                    "controller_id": "codguard-asterisk",
                }
            ]
        }
    )

    status: Literal["dialing", "in_progress"]
    at: datetime
    controller_id: ControllerId


class TranscriptTurn(ApiModel):
    speaker: Literal["agent", "buyer"]
    text: str = Field(max_length=2000)
    offset_ms: int = Field(ge=0, description="Milliseconds since the buyer answered.")


class CallResult(ApiModel):
    """Final result of a call, sent exactly once per call (repeats must be identical).

    The controller, not the model, sets `no_answer` and the `unclear` fallback."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "completed",
                    "outcome": "edited",
                    "failure_reason": None,
                    "controller_id": "codguard-asterisk",
                    "agent": "gemini_live",
                    "language": "vi",
                    "input_method": "voice",
                    "dial_started_at": "2026-10-13T10:15:08+07:00",
                    "answered_at": "2026-10-13T10:15:20+07:00",
                    "ended_at": "2026-10-13T10:16:31+07:00",
                    "dtmf": "",
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
                    "transcript": [
                        {"speaker": "agent", "text": "Dạ em chào chị…", "offset_ms": 400},
                        {"speaker": "buyer", "text": "Ừ chị nghe.", "offset_ms": 6200},
                    ],
                    "recording_uri": "gs://ai-codguard-call-recordings/calls/call_01.wav",
                },
                {
                    "status": "failed",
                    "outcome": None,
                    "failure_reason": "target_unreachable",
                    "controller_id": "codguard-asterisk",
                    "agent": "script",
                    "language": "vi",
                    "input_method": "none",
                    "dial_started_at": "2026-10-13T10:15:08+07:00",
                    "answered_at": None,
                    "ended_at": "2026-10-13T10:15:09+07:00",
                },
            ]
        }
    )

    status: Literal["completed", "failed"]
    outcome: CallOutcome | None = Field(default=None, description="Required when completed.")
    failure_reason: CallFailureReason | None = Field(
        default=None, description="Required when failed."
    )
    controller_id: ControllerId
    agent: CallAgent
    language: CallLanguage = Field(description="Language at the end, after any switch.")
    input_method: CallInputMethod
    dial_started_at: datetime
    answered_at: datetime | None = None
    ended_at: datetime
    dtmf: str = Field(
        default="", max_length=32, pattern=r"^[0-9*#]*$", description="Keys pressed, in order."
    )
    changes: list[CallChange] = Field(default_factory=list)
    cancel_reason: str | None = Field(default=None, max_length=500)
    human_callback_requested: bool = False
    buyer_requests: str | None = Field(default=None, max_length=1000)
    summary_vi: str | None = Field(default=None, max_length=1000)
    transcript: list[TranscriptTurn] = Field(
        default_factory=list, description="Personal data: store with the call, never log it."
    )
    recording_uri: str | None = Field(default=None, pattern=r"^gs://[a-z0-9._-]+/.+$")

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status == "completed" and (self.outcome is None or self.failure_reason):
            raise ValueError("a completed call needs an outcome and no failure_reason")
        if self.status == "failed" and (self.failure_reason is None or self.outcome):
            raise ValueError("a failed call needs a failure_reason and no outcome")
        if self.outcome == CallOutcome.EDITED and not self.changes:
            raise ValueError("outcome edited needs at least one change")
        if self.answered_at is None and self.outcome not in (None, CallOutcome.NO_ANSWER):
            raise ValueError("a call that was not answered can only end with no_answer")
        return self
