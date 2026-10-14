"""Order lifecycle (E4.1): shared transitions and transactional order services."""

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime

from app.api.errors import ApiError
from app.data.orders import delivery_fields
from app.data.phone import phone_hash, to_e164
from app.data.store import OrderStore, phone_key
from app.decision import policy as decisions
from app.risk import engine
from app.risk.features import cod_amount
from app.schemas.common import Address
from app.schemas.delivery import DeliveryOutcome
from app.schemas.enums import (
    BuyerAction,
    CallOutcome,
    ContactBlockReason,
    DecisionAction,
    DeliveryResult,
    ErrorCode,
    OrderStatus,
    RiskTier,
)
from app.schemas.orders import OrderUpdate
from app.schemas.scoring import Decision
from app.schemas.shops import Policy, ShopSettings

STATUS_FOR_ACTION = {
    DecisionAction.SHIP_NOW: OrderStatus.CLEARED_TO_SHIP,
    DecisionAction.SEND_CONFIRMATION_LINK: OrderStatus.AWAITING_CONFIRMATION,
    DecisionAction.AI_CALL: OrderStatus.AWAITING_CONFIRMATION,
    DecisionAction.REQUIRE_DEPOSIT: OrderStatus.AWAITING_DEPOSIT,
    DecisionAction.HOLD_FOR_REVIEW: OrderStatus.PENDING_REVIEW,
}
EDITABLE = frozenset(
    {
        OrderStatus.NEW,
        OrderStatus.CLEARED_TO_SHIP,
        OrderStatus.AWAITING_CONFIRMATION,
        OrderStatus.AWAITING_DEPOSIT,
        OrderStatus.PENDING_REVIEW,
    }
)
TERMINAL = frozenset({OrderStatus.CANCELLED, OrderStatus.DELIVERED, OrderStatus.DELIVERY_FAILED})
WAITING = frozenset({OrderStatus.AWAITING_CONFIRMATION, OrderStatus.AWAITING_DEPOSIT})


class InvalidTransition(ValueError):
    """An event cannot be applied in the order's current state."""


class ExistingDecision(ValueError):
    """Another run or a person decided the order while its assessment was running."""


class StaleAssessment(ValueError):
    """The order changed after scoring; its assessment must not authorize a contact."""


def transition(
    status: OrderStatus | str, event: str, *, action: DecisionAction | str | None = None
) -> OrderStatus:
    """Return the next status; repeats of completed discrete events are harmless.

    Decision events require an action. Services check event payloads before treating a
    repeated cancellation or delivery result as the same event.
    """
    status = OrderStatus(status)
    if event in {"decided", "rescored", "no_response", "staff_override"}:
        allowed = WAITING if event == "no_response" else EDITABLE
        targets = STATUS_FOR_ACTION
        if event == "staff_override":
            targets = {
                a: STATUS_FOR_ACTION[a]
                for a in (
                    DecisionAction.SHIP_NOW,
                    DecisionAction.REQUIRE_DEPOSIT,
                    DecisionAction.HOLD_FOR_REVIEW,
                )
            } | {DecisionAction.CANCEL: OrderStatus.CANCELLED}
        if status in allowed and action in targets:
            return targets[action]
    else:
        events = {
            "score_unavailable": (EDITABLE, OrderStatus.NEW),
            "buyer_confirmed": (EDITABLE, OrderStatus.CLEARED_TO_SHIP),
            "buyer_cancelled": (EDITABLE | {OrderStatus.CANCELLED}, OrderStatus.CANCELLED),
            "buyer_not_ordered": (EDITABLE | {OrderStatus.CANCELLED}, OrderStatus.CANCELLED),
            "deposit_paid": (
                {OrderStatus.AWAITING_DEPOSIT, OrderStatus.CLEARED_TO_SHIP},
                OrderStatus.CLEARED_TO_SHIP,
            ),
            "shipped": ({OrderStatus.CLEARED_TO_SHIP, OrderStatus.SHIPPED}, OrderStatus.SHIPPED),
            "delivered": ({OrderStatus.SHIPPED, OrderStatus.DELIVERED}, OrderStatus.DELIVERED),
            "delivery_failed": (
                {OrderStatus.SHIPPED, OrderStatus.DELIVERY_FAILED},
                OrderStatus.DELIVERY_FAILED,
            ),
            "call_needs_review": (EDITABLE, OrderStatus.PENDING_REVIEW),
        }
        if event in events:
            allowed, target = events[event]
            if status in allowed:
                return target
    raise InvalidTransition(f"{status}: cannot apply {event} ({action})")


def _transact(store: OrderStore, order_id: str, fn: Callable[[dict], dict]) -> dict:
    try:
        return store.transact(order_id, fn)
    except ValueError as error:
        if str(error) == "order_not_found":
            raise ApiError(404, ErrorCode.NOT_FOUND, "Not found", "Order not found.") from error
        raise


def _editable(doc: dict) -> None:
    if doc["status"] not in EDITABLE:
        raise ApiError(
            409, ErrorCode.ORDER_NOT_EDITABLE, "Conflict", "Order is no longer editable."
        )


def _event(doc: dict, event_type: str, now: datetime, message: str, actor="system") -> None:
    doc.setdefault("timeline", []).insert(
        0,
        {
            "at": now,
            "type": event_type,
            "actor": actor,
            "message_vi": message,
            "reason": None,
        },
    )
    doc["updated_at"] = now


def _move(doc: dict, event: str, action: DecisionAction | None = None) -> None:
    doc["status"] = transition(doc["status"], event, action=action).value


def _set_decision(doc: dict, decision: Decision) -> None:
    previous_action = doc.get("contact_action")
    doc["decision"] = decision.model_dump()
    doc["contact_action"] = engine.ACTION_NAME.get(decision.action, "none")
    # Randomized training metadata must describe the action that survived policy guards.
    if doc.get("random_slice") and (
        previous_action != doc["contact_action"]
        or decision.block_reasons
        or decision.decided_by == "staff"
    ):
        doc.update(random_slice=False, action_probability=1.0)


def _record_intervention(doc: dict, action: str) -> None:
    """Keep the first completed contact assignment for training after decisions change."""
    if not doc.get("intervention"):
        assigned = doc.get("contact_action") == action
        doc["intervention"] = {
            "tier": doc.get("tier"),
            "contact_action": action,
            "random_slice": bool(doc.get("random_slice")) and assigned,
            "action_probability": doc.get("action_probability", 1.0) if assigned else 1.0,
        }
        scoring = doc.get("scoring") or {}
        if scoring.get("features"):
            doc["intervention"]["features"] = dict(scoring["features"])
            doc["intervention"]["probability"] = scoring.get("probability")
            doc["intervention"]["province"] = doc["address"].get("province")


def _score(
    store: OrderStore,
    doc: dict,
    now: datetime,
    *,
    settings: ShopSettings | None,
    policy: Policy | None,
) -> bool:
    history = (
        store.history(doc["buyer_phone_hash"], doc["placed_at"]) if doc["buyer_phone_hash"] else []
    )
    fields = engine.score(doc, history)
    if fields is None:
        return False
    _apply_score(doc, fields, now, settings=settings, policy=policy)
    return True


def _apply_score(
    doc: dict,
    fields: dict,
    now: datetime,
    *,
    settings: ShopSettings | None,
    policy: Policy | None,
) -> None:
    """Apply deterministic score fields and choose the final action under current guards."""
    previous = doc.get("scoring")
    if previous:
        doc.setdefault("score_history", []).insert(0, previous)
    staff = doc.get("decision") and doc["decision"]["decided_by"] == "staff"
    staff_decision = doc.get("decision")
    doc.update(fields)
    doc["scoring"]["scored_at"] = now
    _event(
        doc, "scored", now, "Đã chấm điểm lại đơn hàng." if previous else "Đã chấm điểm đơn hàng."
    )
    if staff:
        _set_decision(doc, Decision.model_validate(staff_decision))
        return
    raw = fields["scoring"]
    action = next(a for a, name in engine.ACTION_NAME.items() if name == fields["contact_action"])
    # Model/random choices and hard rules are retained; ordinary tier rules use today's policy.
    if raw["chosen_by"].startswith("tier rule"):
        action = None
    decision = decisions.decide(
        RiskTier(fields["tier"] or RiskTier.LOW),
        raw["expected_loss_vnd"],
        now,
        settings=settings,
        policy=policy,
        confirmed=bool(doc.get("confirmation")),
        action=action,
    )
    _move(doc, "rescored" if previous else "decided", decision.action)
    _set_decision(doc, decision)
    _event(doc, "decided", now, "Đã cập nhật quyết định cho đơn hàng.")


def prepare_score(store: OrderStore, doc: dict) -> dict | None:
    """Compute intake scoring outside a transaction, without saving a decision.

    ADK can assess these immutable inputs before the final transaction. Model calls must
    never run inside a Firestore callback that may be replayed after a conflict.
    """
    _editable(doc)
    history = (
        store.history(doc["buyer_phone_hash"], doc["placed_at"]) if doc["buyer_phone_hash"] else []
    )
    return engine.score(deepcopy(doc), history)


def commit_prepared_score(
    store: OrderStore,
    before: dict,
    fields: dict,
    now: datetime,
    *,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
) -> dict:
    """Validate the assessed snapshot, then save score and deterministic decision atomically."""

    def apply(current):
        if current.get("decision") is not None:
            raise ExistingDecision("The order already has a decision")
        if current != before:
            raise StaleAssessment("The order changed during assessment")
        _editable(current)
        _apply_score(current, deepcopy(fields), now, settings=settings, policy=policy)
        return current

    return _transact(store, before["order_id"], apply)


def score_order(
    store: OrderStore,
    doc: dict,
    now: datetime | None = None,
    *,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
) -> dict:
    """Score the stored order, then atomically save its decision and lifecycle state."""
    now = now or datetime.now(UTC)

    def apply(current):
        _editable(current)
        if current.get("scoring") is None:
            _score(store, current, now, settings=settings, policy=policy)
        return current

    return _transact(store, doc["order_id"], apply)


def _release(doc: dict, now: datetime, *, confirmed=False) -> None:
    """Clear pending contacts; an invalid COD phone still requires manual review."""
    previous = doc.get("decision") or {}
    invalid_phone = doc.get("buyer_phone_hash") is None and cod_amount(doc) > 0
    action = DecisionAction.HOLD_FOR_REVIEW if invalid_phone else DecisionAction.SHIP_NOW
    _move(doc, "rescored", action)
    _set_decision(
        doc,
        Decision(
            decided_at=now,
            action=action,
            policy_version=previous.get("policy_version", decisions.default_policy().version),
            expected_loss_vnd=(doc.get("scoring") or {}).get("expected_loss_vnd"),
            block_reasons=[ContactBlockReason.ALREADY_CONFIRMED]
            if confirmed and not invalid_phone
            else [],
        ),
    )


def _edit(
    store: OrderStore,
    doc: dict,
    update: OrderUpdate,
    now: datetime,
    *,
    settings: ShopSettings | None,
    policy: Policy | None,
    actor="system",
) -> bool:
    _editable(doc)
    fields = update.model_dump(mode="json", exclude_unset=True)
    required = {"buyer_name", "buyer_phone", "address", "items", "prepaid_vnd"}
    if any(fields[name] is None for name in fields.keys() & required):
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Validation error",
            "Required order fields cannot be null.",
        )
    if "buyer_phone" in fields:
        normalised = to_e164(fields["buyer_phone"])
        fields["buyer_phone"] = normalised or fields["buyer_phone"]
        fields["buyer_phone_hash"] = phone_hash(normalised, phone_key()) if normalised else None
    changed = {k: v for k, v in fields.items() if doc.get(k) != v}
    if not changed:
        return False
    deposit_paid = (
        doc["status"] == OrderStatus.AWAITING_DEPOSIT
        and fields.get("prepaid_vnd", doc["prepaid_vnd"]) > doc["prepaid_vnd"]
    )
    staff = doc.get("decision") and doc["decision"]["decided_by"] == "staff"
    if deposit_paid:
        _record_intervention(doc, "deposit")
    doc.update(changed)
    _event(doc, "edited", now, "Đã sửa đơn hàng.", actor)
    scored = _score(store, doc, now, settings=settings, policy=policy)
    if not scored:
        if doc.get("scoring"):
            doc.setdefault("score_history", []).insert(0, doc["scoring"])
        doc.update(scoring=None, tier=None)
        if not staff:
            doc.update(
                decision=None, contact_action="none", random_slice=False, action_probability=1.0
            )
            _move(doc, "score_unavailable")
            if doc.get("buyer_phone_hash") is None and cod_amount(doc) > 0:
                _release(doc, now)
    if not staff:
        if doc.get("confirmation") and not scored:
            _move(doc, "buyer_confirmed")
            _release(doc, now, confirmed=bool(doc.get("confirmation")))
        elif (
            deposit_paid
            and (doc.get("scoring") or {}).get("chosen_by") != "hard rule: invalid phone"
        ):
            # The deposit was paid in the previous awaiting_deposit state. The rescore
            # may change its tier; the resolved deposit request must not start a new contact.
            _move(doc, "rescored", DecisionAction.SHIP_NOW)
            _release(doc, now)
    return True


def edit_order(
    store: OrderStore,
    order_id: str,
    shop_id: str,
    update: OrderUpdate,
    now: datetime,
    *,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
) -> dict:
    """Edit an unshipped order owned by the shop; a changed input causes one rescore."""

    def apply(doc):
        if doc["shop_id"] != shop_id:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Not found", "Order not found.")
        _edit(store, doc, update, now, settings=settings, policy=policy)
        return doc

    return _transact(store, order_id, apply)


def _confirm(doc: dict, via: str, now: datetime) -> None:
    _move(doc, "buyer_confirmed")
    if not doc.get("confirmation"):
        doc["confirmation"] = {"at": now, "via": via}
        _release(doc, now, confirmed=True)
        _event(doc, "buyer_responded", now, "Người mua đã xác nhận đơn hàng.", "buyer")


def _cancel(doc: dict, reason: str, now: datetime) -> None:
    if doc["status"] == OrderStatus.CANCELLED:
        if (doc.get("cancel") or {}).get("reason") == reason:
            return
        raise InvalidTransition("Cannot change the reason for a cancelled order")
    _move(doc, "buyer_not_ordered" if reason == "not_ordered" else "buyer_cancelled")
    doc["cancel"] = {"reason": reason, "at": now, "by": "buyer"}
    previous = doc.get("decision") or {}
    _set_decision(
        doc,
        Decision(
            decided_at=now,
            action=DecisionAction.CANCEL,
            policy_version=previous.get("policy_version", decisions.default_policy().version),
            expected_loss_vnd=previous.get("expected_loss_vnd"),
        ),
    )
    _event(doc, "buyer_responded", now, "Người mua đã hủy hoặc báo không đặt đơn hàng.", "buyer")


def apply_buyer_response(
    store: OrderStore,
    order_id: str,
    action: BuyerAction,
    new_address: Address | None,
    now: datetime,
    *,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
) -> dict:
    """Apply a response after the confirmation-link owner has verified its token."""
    action = BuyerAction(action)
    if action == BuyerAction.EDIT_ADDRESS and new_address is None:
        raise ValueError("new_address is required for edit_address")

    def apply(doc):
        if action in {BuyerAction.CONFIRM, BuyerAction.EDIT_ADDRESS}:
            if doc.get("confirmation"):
                return doc
            _editable(doc)
            _record_intervention(doc, "link")
            if action == BuyerAction.EDIT_ADDRESS:
                doc["confirmation"] = {"at": now, "via": "link"}
                _edit(
                    store,
                    doc,
                    OrderUpdate(address=new_address),
                    now,
                    settings=settings,
                    policy=policy,
                    actor="buyer",
                )
                _move(doc, "buyer_confirmed")
                _release(doc, now, confirmed=True)
                _event(
                    doc, "buyer_responded", now, "Người mua đã sửa và xác nhận đơn hàng.", "buyer"
                )
            else:
                _confirm(doc, "link", now)
        else:
            if doc["status"] != OrderStatus.CANCELLED:
                _record_intervention(doc, "link")
            _cancel(doc, "not_ordered" if action == BuyerAction.NOT_ORDERED else "cancelled", now)
        return doc

    return _transact(store, order_id, apply)


def calls_made(doc: dict) -> int:
    """AI calls already placed for the order: the attempts the pipeline recorded when it claimed
    them (E4.7), or the call records E5 keeps, whichever counts more."""
    started = sum(c.get("started_at") is not None for c in doc.get("calls", []))
    return max((doc.get("attempts") or {}).get("ai_call", 0), started)


def _no_response(
    doc: dict,
    now: datetime,
    *,
    call_attempts: int | None,
    settings: ShopSettings | None,
    policy: Policy | None,
) -> None:
    previous = doc.get("decision")
    if doc.get("confirmation") or doc["status"] not in WAITING or not previous:
        return
    previous = Decision.model_validate(previous)
    if not previous.next_action_at or now < previous.next_action_at or not doc.get("tier"):
        return
    if call_attempts is None:
        call_attempts = calls_made(doc)
    _record_intervention(doc, engine.ACTION_NAME[previous.action])
    decision = decisions.escalate(
        RiskTier(doc["tier"]),
        previous.expected_loss_vnd or 0,
        now,
        unanswered=previous.action,
        call_attempts=call_attempts,
        settings=settings,
        policy=policy,
        confirmed=bool(doc.get("confirmation")),
        action=previous.next_action,
    )
    if decision:
        _move(doc, "no_response", decision.action)
        _set_decision(doc, decision)
        _event(doc, "decided", now, "Đã xử lý đơn hàng chưa được phản hồi.")


def on_no_response(
    store: OrderStore,
    order_id: str,
    now: datetime,
    *,
    call_attempts: int | None = None,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
) -> dict:
    """Timer hook; an early or obsolete timer leaves the order unchanged."""

    def apply(doc):
        _no_response(doc, now, call_attempts=call_attempts, settings=settings, policy=policy)
        return doc

    return _transact(store, order_id, apply)


def apply_call_outcome(
    store: OrderStore,
    order_id: str,
    outcome: CallOutcome,
    now: datetime,
    *,
    update: OrderUpdate | None = None,
    call_attempts: int | None = None,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
) -> dict:
    """Apply one validated call outcome; corrected fields must have been read back."""
    outcome = CallOutcome(outcome)
    if outcome == CallOutcome.EDITED and update is None:
        raise ValueError("update is required for an edited call")

    def apply(doc):
        if doc["status"] in EDITABLE and not doc.get("confirmation"):
            _record_intervention(doc, "call")
        if outcome in {CallOutcome.CONFIRMED, CallOutcome.EDITED}:
            if doc.get("confirmation"):
                return doc
            _editable(doc)
            if outcome == CallOutcome.EDITED:
                doc["confirmation"] = {"at": now, "via": "call"}
                _edit(store, doc, update, now, settings=settings, policy=policy, actor="buyer")
                _move(doc, "buyer_confirmed")
                _release(doc, now, confirmed=True)
                _event(
                    doc,
                    "buyer_responded",
                    now,
                    "Người mua đã sửa và xác nhận qua cuộc gọi.",
                    "buyer",
                )
            else:
                _confirm(doc, "call", now)
        elif outcome in {CallOutcome.CANCELLED, CallOutcome.NOT_ORDERED}:
            _cancel(doc, "not_ordered" if outcome == CallOutcome.NOT_ORDERED else "cancelled", now)
        elif outcome == CallOutcome.NO_ANSWER:
            _no_response(doc, now, call_attempts=call_attempts, settings=settings, policy=policy)
        elif not doc.get("confirmation"):
            _move(doc, "call_needs_review")
            if (doc.get("decision") or {}).get("action") != DecisionAction.HOLD_FOR_REVIEW:
                decision = decisions.decide(
                    RiskTier(doc.get("tier") or RiskTier.LOW),
                    (doc.get("scoring") or {}).get("expected_loss_vnd", 0),
                    now,
                    settings=settings,
                    policy=policy,
                    action=DecisionAction.HOLD_FOR_REVIEW,
                )
                _set_decision(doc, decision)
                _event(doc, "call_completed", now, "Cuộc gọi chưa xác nhận được người mua.")
        return doc

    return _transact(store, order_id, apply)


def hold_for_review(
    store: OrderStore,
    order_id: str,
    now: datetime,
    *,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
    guard_decision: bool = False,
    expected_decision: dict | None = None,
) -> dict:
    """Put an unshipped order in the seller's review queue; a shipped or finished one is left
    alone. The ADK pipeline (E4.7) calls this when a run fails, so a broken model or a storage
    outage ends with a person deciding instead of the buyer being contacted.
    """

    def apply(doc):
        if guard_decision and doc.get("decision") != expected_decision:
            raise ExistingDecision("A different invocation or a person decided this order")
        if doc["status"] not in EDITABLE:
            return doc
        decision = decisions.decide(
            RiskTier(doc.get("tier") or RiskTier.LOW),
            (doc.get("scoring") or {}).get("expected_loss_vnd") or 0,
            now,
            settings=settings,
            policy=policy,
            action=DecisionAction.HOLD_FOR_REVIEW,
        )
        _move(doc, "decided" if doc.get("decision") is None else "rescored", decision.action)
        _set_decision(doc, decision)
        _event(doc, "decided", now, "Đã chuyển đơn hàng cho người bán duyệt.")
        return doc

    return _transact(store, order_id, apply)


def record_call_attempt(store: OrderStore, order_id: str, attempt: int, now: datetime) -> dict:
    """Count AI call number `attempt` as placed, so the next unanswered timer moves on to the
    second attempt or to review (E4.7). Recording the same attempt again changes nothing."""

    def apply(doc):
        attempts = doc.get("attempts") or {}
        if attempt > attempts.get("ai_call", 0):
            doc["attempts"] = attempts | {"ai_call": attempt}
            doc["updated_at"] = now
        return doc

    return _transact(store, order_id, apply)


def mark_shipped(store: OrderStore, order_id: str, now: datetime) -> dict:
    """Record the handover to the carrier, locking further input edits."""

    def apply(doc):
        if doc["status"] != OrderStatus.SHIPPED:
            _move(doc, "shipped")
            _event(doc, "status_changed", now, "Đã gửi đơn hàng cho hãng vận chuyển.")
        return doc

    return _transact(store, order_id, apply)


def apply_delivery(
    store: OrderStore,
    order_id: str,
    outcome: DeliveryOutcome,
    now: datetime,
) -> dict:
    """Save the parcel result; only buyer-caused failures become positive training labels."""
    if outcome.order_id and outcome.order_id != order_id:
        raise ValueError("Delivery outcome order_id does not match the order")
    fields = delivery_fields(outcome, now=now)

    def apply(doc):
        if doc["status"] in TERMINAL:
            if doc.get("delivery") == fields["delivery"]:
                return doc
            raise InvalidTransition("Cannot replace a terminal delivery result")
        if doc["status"] == OrderStatus.CLEARED_TO_SHIP:
            _move(doc, "shipped")
            _event(doc, "status_changed", now, "Đã gửi đơn hàng cho hãng vận chuyển.")
        event = "delivered" if outcome.result == DeliveryResult.DELIVERED else "delivery_failed"
        _move(doc, event)
        doc.update(fields)
        _event(doc, "delivery_result", now, "Đã ghi nhận kết quả giao hàng.")
        return doc

    return _transact(store, order_id, apply)
