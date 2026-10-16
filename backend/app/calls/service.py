"""Create calls, publish their jobs and apply what the call controller reports
(docs/call-controller.md). Environment:

- CALL_JOBS_TOPIC: `projects/<project>/topics/call-jobs`. Unset: calls are not configured, the
  shop app's call endpoints answer 501 and the pipeline keeps its simulated ("mock") call.
- CALL_ALLOWED_PHONES, CALL_TARGET_OVERRIDE, CALL_DIAL_BUYERS, CALL_ENV, CALL_AGENT,
  CALL_LANGUAGE: see app/calls/jobs.py.

Contact protection (AGENTS.md) checked here: a confirmed order and an order whose two attempts
are used are never called; a phone gets at most one AI call per 24 hours (retries for the same
order excepted), none for 30 days after "I didn't order this", and only within the shop's
contact hours for the order's country (its local time; default 08:00-21:00).
The phone rules protect a real buyer, so they are skipped for a test target: the team's phones on
CALL_ALLOWED_PHONES, and CALL_TARGET_OVERRIDE, which takes every other call. Batching orders
to the same phone into one call is not done yet.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Protocol

from app.agents.log import DecisionLog, get_decision_log
from app.api.errors import ApiError
from app.calls import jobs
from app.calls.pubsub import PubSubPublisher
from app.calls.store import CallNotFound, CallStore, get_call_store
from app.data import branches
from app.data.phone import decrypt_phone, encrypt_phone
from app.data.policies import PolicyStore, get_policy_store
from app.data.shops import ShopStore, get_shop_store, settings_for
from app.data.store import OrderStore, get_store
from app.decision import lifecycle
from app.decision.policy import MAX_CALL_ATTEMPTS
from app.schemas.calls import Call
from app.schemas.common import Address
from app.schemas.enums import (
    CallChangeField,
    CallFailureReason,
    CallOutcome,
    CallStatus,
    CallTargetKind,
    ContactBlockReason,
    ContactChannel,
    DecisionAction,
    ErrorCode,
)
from app.schemas.orders import OrderUpdate
from app.schemas.shops import Policy
from app.schemas.telephony import CallJob, CallResult, CallStatusUpdate

log = logging.getLogger(__name__)

ACTIVE = {CallStatus.QUEUED, CallStatus.DIALING, CallStatus.IN_PROGRESS}
FINISHED = {CallStatus.COMPLETED, CallStatus.FAILED}
DAILY_WINDOW = timedelta(hours=24)
BLOCK_WINDOW = timedelta(days=30)
CLAIM_GRACE = timedelta(minutes=10)  # a job nobody claimed by then is treated as lost
REPORT_GRACE = timedelta(minutes=2)  # docs/call-controller.md: max duration + 2 minutes


class Publisher(Protocol):
    def publish(self, job: CallJob) -> str: ...


def call_id_for(order_id: str, attempt: int) -> str:
    """One ID per order and attempt, so a retry or a double click finds the call it made."""
    return f"call_{order_id.removeprefix('ord_')}_{attempt}"


def mask_phone(phone: str | None) -> str:
    """+84000000001 -> +84******001."""
    phone = phone or ""
    if len(phone) < 7:
        return "*" * len(phone) or "***"
    return phone[:3] + "*" * (len(phone) - 6) + phone[-3:]


def stored_job(job: CallJob) -> dict:
    """The job as kept on the call: the number it dials is encrypted like every stored phone. The
    job published to the controller carries it in clear, because the controller dials it."""
    data = job.model_dump(mode="json")
    if data["target"]["kind"] == CallTargetKind.PSTN:
        data["target"]["address"] = encrypt_phone(data["target"]["address"])
    return data


def call_view(doc: dict) -> Call:
    """The public view of a stored call (the order page and GET /calls/{id})."""
    ended, start = doc.get("ended_at"), doc.get("answered_at") or doc.get("started_at")
    return Call(
        id=doc["call_id"],
        order_ids=doc["order_ids"],
        phone_masked=doc["phone_masked"],
        status=doc["status"],
        attempt=doc["attempt"],
        queued_at=doc["queued_at"],
        started_at=doc.get("started_at"),
        ended_at=ended,
        duration_seconds=int((ended - start).total_seconds()) if ended and start else None,
        outcome=doc.get("outcome"),
        changes=doc.get("changes", []),
        cancel_reason=doc.get("cancel_reason"),
        human_callback_requested=doc.get("human_callback_requested", False),
        buyer_requests=doc.get("buyer_requests"),
        summary_vi=doc.get("summary_vi"),
    )


def _at(value) -> datetime | None:
    """Stored times come back from Firestore as datetimes; tolerate ISO strings too."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def order_update(doc: dict, changes: list[dict]) -> OrderUpdate | None:
    """The order edit a call confirmed, from its read-back changes. None when nothing changed."""
    fields: dict = {}
    items = [dict(item) for item in doc["items"]]
    items_changed = False
    for change in changes:
        field, value = CallChangeField(change["field"]), change["new_value"]
        if field == CallChangeField.DELIVERY_ADDRESS:
            fields["address"] = Address(raw=value)
        elif field == CallChangeField.RECIPIENT_NAME:
            fields["recipient_name"] = value
        elif field == CallChangeField.DELIVERY_NOTE:
            fields["note"] = value
        elif field in {CallChangeField.ITEM_VARIANT, CallChangeField.ITEM_QUANTITY}:
            name = (change.get("item_name") or "").casefold()
            for item in items:
                if item["name"].casefold() != name:
                    continue
                items_changed = True
                if field == CallChangeField.ITEM_VARIANT:
                    item["variant"] = value
                else:
                    item["quantity"] = int(value)
    if items_changed:
        kept = [item for item in items if item["quantity"] > 0]
        if kept:
            fields["items"] = kept
    return OrderUpdate(**fields) if fields else None


@dataclass
class CallService:
    orders: OrderStore
    calls: CallStore
    log: DecisionLog
    publisher: Publisher
    policies: PolicyStore | None = None  # None: the default policy
    shops: ShopStore | None = None  # None: the country defaults of config/branches.yaml

    def settings(self, shop_id: str) -> dict | None:
        return self.shops.settings(shop_id) if self.shops else None

    def policy(self, shop_id: str) -> Policy | None:
        return self.policies.current(shop_id) if self.policies else None

    # ------------------------------------------------------------------ starting a call

    def start_for_shop(self, order_id: str, shop_id: str, actor: str, now: datetime) -> Call:
        """POST /orders/{id}/calls: the shop asks for a call now, or confirms the call the engine
        suggested (call automation). Returns the call, or the one already running for the
        order."""
        doc = self.orders.get(order_id)
        if doc is None or doc.get("shop_id") != shop_id:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Not found", f"Order {order_id} not found.")
        for call in doc.get("calls", []):
            stored = self.calls.get(call["id"])
            if stored and CallStatus(self.expire_if_stale(stored, now)["status"]) in ACTIVE:
                return call_view(self.calls.get(call["id"]))
        if doc["status"] not in lifecycle.EDITABLE:
            raise ApiError(
                409, ErrorCode.ORDER_NOT_EDITABLE, "Conflict", "The order has shipped or is closed."
            )
        blocks = self.order_blocks(doc) + self.phone_blocks(doc, now)
        if blocks:
            raise _blocked(blocks)
        attempt = self._claim(doc, now, actor)
        if attempt is None:
            raise _blocked([ContactBlockReason.ATTEMPTS_EXHAUSTED])
        try:
            call = self._place(doc, attempt, now, actor)
        except jobs.NoTarget as reason:
            raise ApiError(
                409,
                ErrorCode.CONTACT_BLOCKED,
                "Contact blocked",
                f"The call was not placed: {reason}.",
                block_reasons=[],
            ) from None
        if call.status != CallStatus.FAILED:  # a call that never started confirms nothing
            lifecycle.accept_suggested_call(
                self.orders,
                order_id,
                actor,
                now,
                settings=self.settings(shop_id),
                policy=self.policy(shop_id),
            )
        return call

    def start_for_pipeline(self, order_id: str, attempt: int, now: datetime) -> dict:
        """The pipeline's `call_buyer` node claimed attempt `attempt`; place it for real. A phone
        rule that blocks the call is noted on the order, which then waits for its timer."""
        doc = self.orders.get(order_id)
        blocks = self.phone_blocks(doc, now)
        reasons = ", ".join(blocks)
        if not blocks:
            try:
                call = self._place(doc, attempt, now, "system")
                return {"mock": False, "call_id": call.id, "call_status": call.status.value}
            except jobs.NoTarget as reason:
                reasons = str(reason)
        lifecycle.record_note(self.orders, order_id, now, f"AI call not placed: {reasons}.")
        return {"mock": False, "call_id": None, "blocked": [b.value for b in blocks]}

    def order_blocks(self, doc: dict) -> list[ContactBlockReason]:
        if doc.get("confirmation"):
            return [ContactBlockReason.ALREADY_CONFIRMED]
        if lifecycle.calls_made(doc) >= MAX_CALL_ATTEMPTS:
            return [ContactBlockReason.ATTEMPTS_EXHAUSTED]
        return []

    def phone_blocks(self, doc: dict, now: datetime) -> list[ContactBlockReason]:
        if jobs.skips_phone_rules(doc):
            return []
        blocks = []
        hours = settings_for(doc, self.settings(doc["shop_id"])).contact_hours
        local = now.astimezone(branches.country_of(doc).tz).strftime("%H:%M")
        if not hours.start <= local < hours.end:
            blocks.append(ContactBlockReason.OUTSIDE_CONTACT_HOURS)
        phone_hash = doc.get("buyer_phone_hash")
        if phone_hash:
            for call in self.calls.for_phone(phone_hash):
                if set(call["order_ids"]) & {doc["order_id"]}:
                    continue  # the retry of this order's own call is not a second contact
                ended, started = _at(call.get("ended_at")), _at(call.get("started_at"))
                if call.get("outcome") == CallOutcome.NOT_ORDERED and ended > now - BLOCK_WINDOW:
                    blocks.append(ContactBlockReason.PHONE_BLOCKED)
                elif started and started > now - DAILY_WINDOW:
                    blocks.append(ContactBlockReason.DAILY_CALL_LIMIT)
        return sorted(set(blocks), key=list(ContactBlockReason).index)

    def _claim(self, doc: dict, now: datetime, actor: str) -> int | None:
        """Take the next free attempt under the pipeline's claim keys (`order:ai_call:N`), so the
        shop's call and the pipeline's calls share the two attempts and never double up."""
        record = {
            "order_id": doc["order_id"],
            "shop_id": doc["shop_id"],
            "action": DecisionAction.AI_CALL.value,
            "channel": ContactChannel.AI_CALL.value,
            "at": now,
            "decided_at": None,
            "by": actor,
        }
        for attempt in range(lifecycle.calls_made(doc) + 1, MAX_CALL_ATTEMPTS + 1):
            key = f"{doc['order_id']}:{DecisionAction.AI_CALL.value}:{attempt}"
            if self.log.claim(key, record | {"attempt": attempt}):
                return attempt
        return None

    def _place(self, doc: dict, attempt: int, now: datetime, actor: str) -> Call:
        call_id = call_id_for(doc["order_id"], attempt)
        name = self.shops.name(doc["shop_id"]) if self.shops else None
        # NoTarget: the caller says why
        job = jobs.build_job(doc, call_id, attempt, now, shop_name=name)
        stored = {
            "call_id": call_id,
            "shop_id": doc["shop_id"],
            "order_ids": [doc["order_id"]],
            "phone_hash": doc.get("buyer_phone_hash"),
            "phone_masked": mask_phone(decrypt_phone(doc.get("buyer_phone"))),
            "attempt": attempt,
            "status": CallStatus.QUEUED.value,
            "requested_by": actor,
            "queued_at": now,
            "job": stored_job(job),
        }
        existing = self.calls.create(stored)
        if existing:
            return call_view(existing)
        who = "the shop" if actor != "system" else "the decision engine"
        self._mirror(stored, now, ("contact_started", f"AI call {attempt} requested by {who}."))
        try:
            self.publisher.publish(job)
        except Exception:
            log.exception("Could not publish the job for %s", call_id)
            stored = self._fail(call_id, now, publish_failed=True)
            self._mirror(stored, now, ("call_completed", "The AI call could not be started."))
        return call_view(stored)

    # ------------------------------------------------------------------ controller reports

    def record_status(self, call_id: str, update: CallStatusUpdate) -> Call:
        """`dialing` claims a queued call; `in_progress` marks the answer. Anything else is
        409 `call_not_active`, which tells the controller to drop the job."""
        changed = []

        def apply(doc):
            changed.clear()
            status, owner = CallStatus(doc["status"]), doc.get("controller_id")
            same = owner == update.controller_id
            if update.status == "dialing":
                if status == CallStatus.QUEUED:
                    changed.append(True)
                    return doc | {
                        "status": CallStatus.DIALING.value,
                        "controller_id": update.controller_id,
                        "started_at": update.at,
                    }
                if status in {CallStatus.DIALING, CallStatus.IN_PROGRESS} and same:
                    return doc
            else:
                if status == CallStatus.DIALING and same:
                    changed.append(True)
                    return doc | {"status": CallStatus.IN_PROGRESS.value, "answered_at": update.at}
                if status == CallStatus.IN_PROGRESS and same:
                    return doc
            raise ApiError(
                409,
                ErrorCode.CALL_NOT_ACTIVE,
                "Call not active",
                f"Call {call_id} is {status.value}. Ack the job and drop it.",
            )

        doc = self._transact(call_id, apply)
        if changed:
            self._mirror(doc, update.at)
        return call_view(doc)

    def record_result(self, call_id: str, result: CallResult) -> Call:
        """Store the final result once and apply it to the orders. An identical repeat returns
        the call again; a different result is 409. A call the backend gave up on (no report in
        time) still takes the controller's late result."""
        payload = result.model_dump(mode="json")
        fresh = []

        def apply(doc):
            fresh.clear()
            if CallStatus(doc["status"]) in FINISHED and not doc.get("expired"):
                if doc.get("result") == payload:
                    return doc
                raise ApiError(
                    409, ErrorCode.CONFLICT, "Conflict", f"Call {call_id} has a different result."
                )
            fresh.append(True)
            return doc | {
                "status": result.status,
                "outcome": result.outcome.value if result.outcome else None,
                "failure_reason": result.failure_reason.value if result.failure_reason else None,
                "controller_id": result.controller_id,
                "started_at": doc.get("started_at") or result.dial_started_at,
                "answered_at": result.answered_at,
                "ended_at": result.ended_at,
                "changes": payload["changes"],
                "cancel_reason": result.cancel_reason,
                "human_callback_requested": result.human_callback_requested,
                "buyer_requests": result.buyer_requests,
                "summary_vi": result.summary_vi,
                "transcript": payload["transcript"],
                "recording_uri": result.recording_uri,
                "result": payload,
                "expired": False,
            }

        doc = self._transact(call_id, apply)
        if fresh:
            self._apply_to_orders(doc, result)
        return call_view(doc)

    def _apply_to_orders(self, doc: dict, result: CallResult) -> None:
        if result.status == "failed":
            message = f"The AI call failed ({result.failure_reason.value})."
        else:
            message = f"AI call ended: {result.outcome.value}."
            if result.summary_vi:
                message += f" {result.summary_vi}"
        self._mirror(doc, result.ended_at, ("call_completed", message))
        if result.status != "completed":
            return  # nobody was reached: the order keeps waiting for its no-response timer
        for order_id in doc["order_ids"]:
            changes = [c for c in doc["changes"] if c["order_id"] == order_id]
            outcome = result.outcome
            if any(c["field"] == CallChangeField.CANCEL_ORDER for c in changes):
                outcome = CallOutcome.CANCELLED
            order = self.orders.get(order_id)
            update = order_update(order, changes) if outcome == CallOutcome.EDITED else None
            if outcome == CallOutcome.EDITED and update is None:
                outcome = CallOutcome.CONFIRMED  # the only change was to another order
            event = {
                "order_id": order_id,
                "type": "call_outcome",
                "outcome": outcome.value,
                "update": update.model_dump(mode="json", exclude_none=True) if update else None,
            }
            self.run_event(event, doc["shop_id"])

    def run_event(self, event: dict, shop_id: str) -> None:
        """The rule set's L4 table for the call outcome (the pipeline's `on_contact_event`)."""
        from app.agents.agent import Pipeline  # the pipeline imports this module
        from app.agents.runner import run_contact_event

        pipeline = Pipeline(
            store=self.orders,
            log=self.log,
            calls=self,
            settings=self.settings(shop_id),
            policy=self.policy(shop_id),
        )
        asyncio.run(run_contact_event(event, shop_id, pipeline=pipeline))

    # ------------------------------------------------------------------ reading and expiry

    def get_for_shop(self, call_id: str, shop_id: str, now: datetime) -> Call:
        doc = self.calls.get(call_id)
        if doc is None or doc.get("shop_id") != shop_id:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Not found", f"Call {call_id} not found.")
        return call_view(self.expire_if_stale(doc, now))

    def expire_if_stale(self, doc: dict, now: datetime) -> dict:
        """A call the controller stopped reporting on fails with `controller_error`, so a
        crashed controller never leaves a call open (docs/call-controller.md)."""
        status = CallStatus(doc["status"])
        if status not in ACTIVE:
            return doc
        if status == CallStatus.QUEUED:
            deadline = _at(doc["queued_at"]) + CLAIM_GRACE
        else:
            job = doc["job"]
            limit = job["ring_timeout_seconds"] + job["max_duration_seconds"]
            deadline = _at(doc["started_at"]) + timedelta(seconds=limit) + REPORT_GRACE
        if now <= deadline:
            return doc
        doc = self._fail(doc["call_id"], now)
        self._mirror(doc, now, ("call_completed", "The AI call did not report back in time."))
        return doc

    def _fail(self, call_id: str, now: datetime, *, publish_failed: bool = False) -> dict:
        def apply(doc):
            if CallStatus(doc["status"]) in FINISHED:
                return doc
            return doc | {
                "status": CallStatus.FAILED.value,
                "failure_reason": CallFailureReason.CONTROLLER_ERROR.value,
                "ended_at": now,
                "expired": not publish_failed,
            }

        return self._transact(call_id, apply)

    def _transact(self, call_id: str, fn) -> dict:
        try:
            return self.calls.transact(call_id, fn)
        except CallNotFound:
            raise ApiError(
                404, ErrorCode.NOT_FOUND, "Not found", f"Call {call_id} not found."
            ) from None

    def _mirror(self, doc: dict, now: datetime, event: tuple[str, str] | None = None) -> None:
        view = call_view(doc).model_dump(mode="json")
        for order_id in doc["order_ids"]:
            lifecycle.record_call(self.orders, order_id, view, now, event=event)


def _blocked(reasons: list[ContactBlockReason]) -> ApiError:
    details = {
        ContactBlockReason.ALREADY_CONFIRMED: "The order is confirmed, so it is not called again.",
        ContactBlockReason.ATTEMPTS_EXHAUSTED: "Both call attempts have been used.",
        ContactBlockReason.OUTSIDE_CONTACT_HOURS: "Outside contact hours.",
        ContactBlockReason.PHONE_BLOCKED: "This phone said it did not place an order.",
        ContactBlockReason.DAILY_CALL_LIMIT: "This phone had an AI call in the last 24 hours.",
    }
    return ApiError(
        409,
        ErrorCode.CONTACT_BLOCKED,
        "Contact blocked",
        " ".join(details.get(r, r.value) for r in reasons),
        block_reasons=[r.value for r in reasons],
    )


@lru_cache
def _publisher(topic: str) -> PubSubPublisher:
    return PubSubPublisher(topic)


def get_call_service() -> CallService | None:
    """None when CALL_JOBS_TOPIC is unset: calls are not configured on this instance. Nothing
    touches Firestore until calls are configured."""
    topic = os.environ.get("CALL_JOBS_TOPIC")
    if not topic:
        return None
    return CallService(
        orders=get_store(),
        calls=get_call_store(),
        log=get_decision_log(),
        publisher=_publisher(topic),
        policies=get_policy_store(),
        shops=get_shop_store(),
    )
