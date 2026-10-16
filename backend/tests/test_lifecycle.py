"""E4.1 lifecycle: legal transitions and atomic scoring, edits and buyer outcomes."""

from copy import deepcopy
from datetime import timedelta

import pytest

from app.api.errors import ApiError
from app.data.orders import order_document, training_label
from app.data.phone import decrypt_phone
from app.decision import lifecycle, policy
from app.risk import engine
from app.risk.features import compute_features
from app.schemas.common import Address
from app.schemas.delivery import DeliveryOutcome
from app.schemas.enums import BuyerAction, CallOutcome, DecisionAction, OrderStatus
from app.schemas.orders import OrderCreate, OrderUpdate
from tests.test_intake import FakeStore
from tests.test_policy import NOW

A = DecisionAction
S = OrderStatus
EDITABLE = {S.NEW, S.CLEARED_TO_SHIP, S.AWAITING_CONFIRMATION, S.AWAITING_DEPOSIT, S.PENDING_REVIEW}


def test_all_nine_order_states_are_available():
    assert {s.value for s in S} == {
        "new",
        "cleared_to_ship",
        "awaiting_confirmation",
        "awaiting_deposit",
        "pending_review",
        "cancelled",
        "shipped",
        "delivered",
        "delivery_failed",
    }
    assert lifecycle.EDITABLE == EDITABLE
    assert {S.CANCELLED, S.DELIVERED, S.DELIVERY_FAILED} == lifecycle.TERMINAL


ACTION_STATES = [
    (A.SHIP_NOW, S.CLEARED_TO_SHIP),
    (A.SEND_CONFIRMATION_LINK, S.AWAITING_CONFIRMATION),
    (A.AI_CALL, S.AWAITING_CONFIRMATION),
    (A.REQUIRE_DEPOSIT, S.AWAITING_DEPOSIT),
    (A.HOLD_FOR_REVIEW, S.PENDING_REVIEW),
]


@pytest.mark.parametrize(("action", "target"), ACTION_STATES)
@pytest.mark.parametrize("status", list(S))
@pytest.mark.parametrize("event", ["decided", "rescored"])
def test_decisions_only_move_unshipped_nonterminal_orders(status, event, action, target):
    if status in EDITABLE:
        assert lifecycle.transition(status, event, action=action) == target
    else:
        with pytest.raises(lifecycle.InvalidTransition):
            lifecycle.transition(status, event, action=action)


EVENT_STATES = [
    ("score_unavailable", EDITABLE, S.NEW),
    ("buyer_confirmed", EDITABLE, S.CLEARED_TO_SHIP),
    ("buyer_cancelled", EDITABLE | {S.CANCELLED}, S.CANCELLED),
    ("buyer_not_ordered", EDITABLE | {S.CANCELLED}, S.CANCELLED),
    ("deposit_paid", {S.AWAITING_DEPOSIT, S.CLEARED_TO_SHIP}, S.CLEARED_TO_SHIP),
    ("shipped", {S.CLEARED_TO_SHIP, S.SHIPPED}, S.SHIPPED),
    ("delivered", {S.SHIPPED, S.DELIVERED}, S.DELIVERED),
    ("delivery_failed", {S.SHIPPED, S.DELIVERY_FAILED}, S.DELIVERY_FAILED),
    ("call_needs_review", EDITABLE, S.PENDING_REVIEW),
]


@pytest.mark.parametrize(("event", "allowed", "target"), EVENT_STATES)
@pytest.mark.parametrize("status", list(S))
def test_buyer_payment_shipping_and_delivery_transitions(status, event, allowed, target):
    if status in allowed:
        assert lifecycle.transition(status, event) == target
    else:
        with pytest.raises(lifecycle.InvalidTransition):
            lifecycle.transition(status, event)


@pytest.mark.parametrize("status", list(S))
@pytest.mark.parametrize(("action", "target"), ACTION_STATES)
def test_no_response_only_escalates_waiting_orders(status, action, target):
    if status in {S.AWAITING_CONFIRMATION, S.AWAITING_DEPOSIT}:
        assert lifecycle.transition(status, "no_response", action=action) == target
    else:
        with pytest.raises(lifecycle.InvalidTransition):
            lifecycle.transition(status, "no_response", action=action)


@pytest.mark.parametrize("status", list(S))
@pytest.mark.parametrize(
    ("action", "target"),
    [
        (A.SHIP_NOW, S.CLEARED_TO_SHIP),
        (A.REQUIRE_DEPOSIT, S.AWAITING_DEPOSIT),
        (A.HOLD_FOR_REVIEW, S.PENDING_REVIEW),
        (A.CANCEL, S.CANCELLED),
    ],
)
def test_staff_override_targets_do_not_schedule_contacts(status, action, target):
    if status in EDITABLE:
        assert lifecycle.transition(status, "staff_override", action=action) == target
    else:
        with pytest.raises(lifecycle.InvalidTransition):
            lifecycle.transition(status, "staff_override", action=action)


@pytest.mark.parametrize("event", ["decided", "rescored", "staff_override", "no_response"])
def test_a_decision_event_requires_an_allowed_action(event):
    for action in (None, A.CANCEL if event != "staff_override" else A.AI_CALL):
        with pytest.raises(lifecycle.InvalidTransition):
            lifecycle.transition(S.NEW, event, action=action)


def test_unknown_events_are_rejected():
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.transition(S.NEW, "unknown")


def scored_fields(tier="low", action="none"):
    return {
        "tier": tier,
        "contact_action": action,
        "random_slice": False,
        "action_probability": 1.0,
        "scoring": {
            "probability": 0.6,
            "risk_score": 60,
            "tier": tier,
            "expected_loss_vnd": 36000,
            "chosen_by": "hard rule: invalid phone" if action == "hold" else "tier rule",
            "features": {},
            "model_version": "test-v1",
            "scored_at": NOW,
        },
    }


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    store = FakeStore()
    order = OrderCreate.model_validate(OrderCreate.model_config["json_schema_extra"]["examples"][0])
    store.create(
        order_document(order, order_id="ord_test", shop_id="shop_a", phone_key=b"test-key", now=NOW)
    )
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields())
    return store


@pytest.mark.parametrize(
    ("tier", "action", "status"),
    [
        ("low", "none", "cleared_to_ship"),
        ("medium", "link", "awaiting_confirmation"),
        ("high", "call", "awaiting_confirmation"),
        ("very_high", "deposit", "awaiting_deposit"),
        ("high", "hold", "pending_review"),
    ],
)
def test_scoring_writes_the_action_score_and_status_together(
    store, monkeypatch, tier, action, status
):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields(tier, action))
    result = lifecycle.score_order(store, store.docs["ord_test"], NOW)
    assert result["status"] == status
    assert result["decision"]["decided_at"] == NOW
    assert result["contact_action"] == action
    assert result["score_history"] == []
    assert [e["type"] for e in result["timeline"]] == ["decided", "scored", "created"]


def test_no_model_keeps_an_intake_order_new_and_unscored(store, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: None)
    before = deepcopy(store.docs["ord_test"])
    assert lifecycle.score_order(store, before, NOW) == before


def test_late_intake_scoring_does_not_overwrite_a_shipped_order(store):
    stale = deepcopy(store.docs["ord_test"])
    store.docs["ord_test"]["status"] = "shipped"
    with pytest.raises(ApiError) as error:
        lifecycle.score_order(store, stale, NOW)
    assert error.value.problem.code == "order_not_editable"
    assert store.docs["ord_test"]["status"] == "shipped"


def test_an_address_edit_rescores_once_and_preserves_prior_runs(store, monkeypatch):
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    update = OrderUpdate(address=Address(raw="Địa chỉ mẫu chưa đủ số nhà"))
    result = lifecycle.edit_order(store, "ord_test", "shop_a", update, NOW + timedelta(minutes=1))
    assert result["status"] == "awaiting_confirmation"
    assert result["scoring"]["tier"] == "high"
    assert [s["tier"] for s in result["score_history"]] == ["low"]
    assert [e["type"] for e in result["timeline"][:3]] == ["decided", "scored", "edited"]
    assert (
        lifecycle.edit_order(store, "ord_test", "shop_a", update, NOW + timedelta(minutes=2))
        == result
    )


@pytest.mark.parametrize("status", ["shipped", "cancelled", "delivered", "delivery_failed"])
def test_edits_after_shipping_or_cancellation_are_rejected(store, status):
    store.docs["ord_test"]["status"] = status
    before = deepcopy(store.docs["ord_test"])
    with pytest.raises(ApiError) as error:
        lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(note="Ghi chú mẫu"), NOW)
    assert error.value.problem.status == 409 and error.value.problem.code == "order_not_editable"
    assert store.docs["ord_test"] == before


def test_cross_shop_and_missing_order_edits_are_not_found(store):
    for order_id, shop_id in [("ord_test", "shop_b"), ("missing", "shop_a")]:
        with pytest.raises(ApiError) as error:
            lifecycle.edit_order(store, order_id, shop_id, OrderUpdate(note="Mẫu"), NOW)
        assert error.value.problem.status == 404


def test_edit_rehashes_a_new_phone_and_uses_its_history_at_placement(store, monkeypatch):
    old = deepcopy(store.docs["ord_test"])
    earlier = old | {
        "order_id": "earlier",
        "buyer_phone": "+84000000002",
        "buyer_phone_hash": "unused",
        "placed_at": old["placed_at"] - timedelta(days=1),
    }
    from app.data.phone import phone_hash

    earlier["buyer_phone_hash"] = phone_hash("+84000000002", b"test-key")
    store.create(earlier)

    def score(doc, history):
        assert decrypt_phone(doc["buyer_phone"]) == "+84000000002"
        assert doc["placed_at"] == old["placed_at"]
        assert [d["order_id"] for d in history] == ["earlier"]
        return scored_fields()

    monkeypatch.setattr(engine, "score", score)
    result = lifecycle.edit_order(
        store, "ord_test", "shop_a", OrderUpdate(buyer_phone="+84000000002"), NOW
    )
    assert result["buyer_phone_hash"] == earlier["buyer_phone_hash"]
    assert result["buyer_phone_hash"] != old["buyer_phone_hash"]


def test_staff_decision_is_preserved_while_the_score_is_updated(store, monkeypatch):
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    doc = store.docs["ord_test"]
    doc["status"] = "pending_review"
    doc["decision"].update(
        action="hold_for_review", decided_by="staff", next_action=None, next_action_at=None
    )
    doc["contact_action"] = "hold"
    staff_decision = deepcopy(doc["decision"])
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    result = lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(note="Ghi chú mẫu"), NOW)
    assert result["status"] == "pending_review" and result["scoring"]["tier"] == "high"
    assert result["decision"] == staff_decision and result["contact_action"] == "hold"


def test_confirmed_orders_are_rescored_without_contact_or_followups(store, monkeypatch):
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    confirmed = lifecycle.apply_buyer_response(store, "ord_test", BuyerAction.CONFIRM, None, NOW)
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    result = lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(note="Ghi chú mới"), NOW)
    assert result["status"] == "cleared_to_ship" and result["scoring"]["tier"] == "high"
    assert result["confirmation"] == confirmed["confirmation"] == {"at": NOW, "via": "link"}
    assert result["decision"]["action"] == "ship_now"
    assert result["decision"]["block_reasons"] == ["already_confirmed"]
    assert result["decision"]["next_action_at"] is None and result["contact_action"] == "none"
    assert lifecycle.on_no_response(store, "ord_test", NOW + timedelta(days=1)) == result


def test_confirmation_immediately_clears_pending_contact_decisions(store, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    result = lifecycle.apply_call_outcome(store, "ord_test", CallOutcome.CONFIRMED, NOW)
    assert result["confirmation"] == {"at": NOW, "via": "call"}
    assert result["decision"]["action"] == "ship_now"
    assert result["decision"]["next_action"] is None and result["contact_action"] == "none"
    assert (
        lifecycle.apply_call_outcome(
            store, "ord_test", CallOutcome.CONFIRMED, NOW + timedelta(minutes=1)
        )
        == result
    )


def test_buyer_address_correction_rescores_and_confirms_atomically(store, monkeypatch):
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    address = Address(raw="Số 15, địa chỉ tổng hợp mẫu")
    result = lifecycle.apply_buyer_response(
        store, "ord_test", BuyerAction.EDIT_ADDRESS, address, NOW
    )
    assert result["address"]["raw"] == address.raw and result["status"] == "cleared_to_ship"
    assert result["confirmation"]["via"] == "link" and len(result["score_history"]) == 1
    assert result["decision"]["action"] == "ship_now"
    assert (
        lifecycle.apply_buyer_response(store, "ord_test", BuyerAction.EDIT_ADDRESS, address, NOW)
        == result
    )


def test_call_correction_requires_and_applies_the_confirmed_changes(store):
    with pytest.raises(ValueError, match="update"):
        lifecycle.apply_call_outcome(store, "ord_test", CallOutcome.EDITED, NOW)
    result = lifecycle.apply_call_outcome(
        store,
        "ord_test",
        CallOutcome.EDITED,
        NOW,
        update=OrderUpdate(address=Address(raw="Số 15, địa chỉ mẫu")),
    )
    assert result["status"] == "cleared_to_ship" and result["confirmation"]["via"] == "call"
    assert result["address"]["raw"] == "Số 15, địa chỉ mẫu"


@pytest.mark.parametrize(
    ("action", "reason"),
    [(BuyerAction.CANCEL, "cancelled"), (BuyerAction.NOT_ORDERED, "not_ordered")],
)
def test_buyer_cancellation_records_the_failure_label_once(store, action, reason):
    result = lifecycle.apply_buyer_response(store, "ord_test", action, None, NOW)
    assert result["status"] == "cancelled"
    assert result["cancel"] == {"reason": reason, "at": NOW, "by": "buyer"}
    assert result["confirmation"] is None
    assert (
        lifecycle.apply_buyer_response(store, "ord_test", action, None, NOW + timedelta(minutes=1))
        == result
    )


@pytest.mark.parametrize("outcome", [CallOutcome.WRONG_PERSON, CallOutcome.UNCLEAR])
def test_wrong_person_and_unclear_calls_need_review(store, outcome):
    result = lifecycle.apply_call_outcome(store, "ord_test", outcome, NOW)
    assert result["status"] == "pending_review" and result["confirmation"] is None
    assert result["decision"]["action"] == "hold_for_review"


def test_no_response_waits_until_due_and_exhausted_calls_go_to_review(store, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("medium", "link"))
    first = lifecycle.score_order(store, store.docs["ord_test"], NOW)
    assert lifecycle.on_no_response(store, "ord_test", NOW + timedelta(minutes=119)) == first
    called = lifecycle.on_no_response(store, "ord_test", NOW + timedelta(minutes=120))
    assert called["status"] == "awaiting_confirmation" and called["decision"]["action"] == "ai_call"
    assert lifecycle.on_no_response(store, "ord_test", NOW + timedelta(minutes=120)) == called
    held = lifecycle.on_no_response(
        store, "ord_test", NOW + timedelta(minutes=180), call_attempts=2
    )
    assert held["status"] == "pending_review" and held["decision"]["next_action"] is None


def test_an_edit_uses_the_current_policy_without_changing_past_decisions(store):
    first = lifecycle.score_order(store, store.docs["ord_test"], NOW)
    revised = policy.default_policy().model_copy(deep=True, update={"version": 2})
    result = lifecycle.edit_order(
        store, "ord_test", "shop_a", OrderUpdate(note="Mẫu"), NOW, policy=revised
    )
    assert first["decision"]["policy_version"] == 1
    assert result["decision"]["policy_version"] == 2


def test_scoring_failure_rolls_back_an_edit(store, monkeypatch):
    before = deepcopy(store.docs["ord_test"])

    def fail(doc, history):
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(engine, "score", fail)
    with pytest.raises(RuntimeError):
        lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(note="Mẫu"), NOW)
    assert store.docs["ord_test"] == before


def test_an_edit_without_a_model_does_not_keep_a_stale_score(store, monkeypatch):
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    monkeypatch.setattr(engine, "score", lambda doc, history: None)
    result = lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(note="Mẫu"), NOW)
    assert result["scoring"] is None and result["decision"] is None and result["tier"] is None
    assert result["status"] == "new" and len(result["score_history"]) == 1


def test_deposit_increase_rescores_and_releases_an_awaiting_deposit_order(store, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("very_high", "deposit"))
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    result = lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(prepaid_vnd=30000), NOW)
    assert result["prepaid_vnd"] == 30000 and result["status"] == "cleared_to_ship"
    assert result["confirmation"] is None and result["decision"]["next_action"] is None


@pytest.mark.parametrize(
    ("result", "status", "label"),
    [
        ("delivered", "delivered", 0),
        ("refused", "delivery_failed", 1),
        ("unreachable", "delivery_failed", 1),
        ("carrier_issue", "delivery_failed", None),
        ("shop_issue", "delivery_failed", None),
    ],
)
def test_delivery_results_pass_through_shipped_and_are_idempotent(store, result, status, label):
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    outcome = DeliveryOutcome(order_id="ord_test", carrier="ghn", result=result, occurred_at=NOW)
    final = lifecycle.apply_delivery(store, "ord_test", outcome, NOW)
    assert final["status"] == status
    assert training_label(final["delivery"]["result"]) == label
    assert [e["type"] for e in final["timeline"][:2]] == ["delivery_result", "status_changed"]
    assert lifecycle.apply_delivery(store, "ord_test", outcome, NOW + timedelta(minutes=1)) == final


def test_mark_shipped_locks_the_order_and_is_idempotent(store):
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    result = lifecycle.mark_shipped(store, "ord_test", NOW)
    assert result["status"] == "shipped"
    assert lifecycle.mark_shipped(store, "ord_test", NOW + timedelta(minutes=1)) == result


def test_delivery_cannot_skip_confirmation_or_rewrite_a_terminal_result(store):
    outcome = DeliveryOutcome(
        order_id="ord_test", carrier="ghn", result="delivered", occurred_at=NOW
    )
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.apply_delivery(store, "ord_test", outcome, NOW)
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    lifecycle.apply_delivery(store, "ord_test", outcome, NOW)
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.apply_delivery(
            store, "ord_test", outcome.model_copy(update={"tracking_code": "changed"}), NOW
        )


def test_a_repeated_intake_scoring_event_does_not_create_an_extra_run(store):
    result = lifecycle.score_order(store, store.docs["ord_test"], NOW)
    assert lifecycle.score_order(store, result, NOW + timedelta(minutes=1)) == result


def test_changed_policy_actions_apply_to_rescores_but_not_existing_decisions(store, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("medium", "link"))
    old = lifecycle.score_order(store, store.docs["ord_test"], NOW)
    revised = policy.default_policy().model_copy(deep=True, update={"version": 2})
    policy.tier_rule(revised, "medium").action = A.AI_CALL
    assert store.docs["ord_test"]["decision"]["action"] == "send_confirmation_link"
    updated = lifecycle.edit_order(
        store, "ord_test", "shop_a", OrderUpdate(note="Mẫu"), NOW, policy=revised
    )
    assert updated["decision"]["action"] == "ai_call" and updated["decision"]["policy_version"] == 2
    assert old["decision"]["policy_version"] == 1


def test_pending_timer_obeys_its_saved_next_action_when_policy_changes(store, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("medium", "link"))
    old_policy = policy.default_policy().model_copy(deep=True, update={"version": 2})
    policy.tier_rule(old_policy, "medium").if_no_response = A.HOLD_FOR_REVIEW
    first = lifecycle.score_order(store, store.docs["ord_test"], NOW, policy=old_policy)
    assert first["decision"]["next_action"] == "hold_for_review"
    revised = policy.default_policy().model_copy(deep=True, update={"version": 3})
    result = lifecycle.on_no_response(store, "ord_test", NOW + timedelta(hours=2), policy=revised)
    assert result["status"] == "pending_review" and result["contact_action"] == "hold"


@pytest.mark.parametrize("field", ["buyer_name", "buyer_phone", "address", "items", "prepaid_vnd"])
def test_null_required_order_fields_cannot_corrupt_an_order(store, field):
    before = deepcopy(store.docs["ord_test"])
    with pytest.raises(ApiError) as error:
        lifecycle.edit_order(
            store, "ord_test", "shop_a", OrderUpdate.model_validate({field: None}), NOW
        )
    assert error.value.problem.status == 422 and store.docs["ord_test"] == before


def test_nullable_fields_can_be_cleared_and_empty_updates_do_nothing(store):
    first = lifecycle.edit_order(
        store, "ord_test", "shop_a", OrderUpdate(note="Mẫu", recipient_name="Người mẫu"), NOW
    )
    assert lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(), NOW) == first
    cleared = lifecycle.edit_order(
        store, "ord_test", "shop_a", OrderUpdate(note=None, recipient_name=None), NOW
    )
    assert cleared["note"] is None and cleared["recipient_name"] is None
    assert len(cleared["score_history"]) == 1


@pytest.mark.parametrize("action", ["link", "call", "deposit"])
def test_randomized_contacts_are_blocked_after_confirmation(store, monkeypatch, action):
    lifecycle.apply_buyer_response(store, "ord_test", BuyerAction.CONFIRM, None, NOW)

    def randomized(doc, history):
        fields = scored_fields("high", action)
        fields.update(random_slice=True, action_probability=0.5)
        fields["scoring"]["chosen_by"] = "random slice"
        return fields

    monkeypatch.setattr(engine, "score", randomized)
    result = lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(note="Mẫu"), NOW)
    assert result["contact_action"] == "none" and result["decision"]["block_reasons"] == [
        "already_confirmed"
    ]
    assert result["random_slice"] is False and result["action_probability"] == 1.0


@pytest.mark.parametrize(
    ("random_tests", "action"), [(True, "send_confirmation_link"), (False, "ai_call")]
)
def test_the_shop_can_turn_random_tests_off(store, monkeypatch, random_tests, action):
    """A random link for a High order stands while random tests are on; turned off (a demo), the
    tier policy decides and the order is no random sample."""

    def randomized(doc, history):
        fields = scored_fields("high", "link")
        fields.update(random_slice=True, action_probability=0.5)
        fields["scoring"]["chosen_by"] = "random slice"
        return fields

    monkeypatch.setattr(engine, "score", randomized)
    shop_policy = policy.default_policy().model_copy(update={"random_tests": random_tests})
    result = lifecycle.score_order(store, store.docs["ord_test"], NOW, policy=shop_policy)
    assert result["decision"]["action"] == action
    assert result["random_slice"] is random_tests


def test_the_expected_loss_gate_applies_to_a_model_selected_contact(store, monkeypatch):
    def model_choice(doc, history):
        fields = scored_fields("high", "call")
        fields["scoring"].update(chosen_by="model 2", expected_loss_vnd=1000)
        return fields

    monkeypatch.setattr(engine, "score", model_choice)
    result = lifecycle.score_order(store, store.docs["ord_test"], NOW)
    assert result["status"] == "cleared_to_ship" and result["contact_action"] == "none"
    assert result["decision"]["block_reasons"] == ["expected_loss_below_cost"]


@pytest.mark.parametrize(
    ("call", "reason"),
    [(CallOutcome.CANCELLED, "cancelled"), (CallOutcome.NOT_ORDERED, "not_ordered")],
)
def test_call_cancellations_record_the_same_label_fields(store, call, reason):
    result = lifecycle.apply_call_outcome(store, "ord_test", call, NOW)
    assert result["cancel"]["reason"] == reason and result["status"] == "cancelled"
    assert result["decision"]["next_action"] is None


def test_no_answer_call_and_expired_deposit_use_the_no_response_hook(store, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("very_high", "deposit"))
    first = lifecycle.score_order(store, store.docs["ord_test"], NOW)
    result = lifecycle.apply_call_outcome(
        store, "ord_test", CallOutcome.NO_ANSWER, first["decision"]["next_action_at"]
    )
    assert result["status"] == "pending_review"


def test_staff_decision_does_not_inherit_randomized_model_action_metadata(store, monkeypatch):
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    doc = store.docs["ord_test"]
    doc["status"] = "pending_review"
    doc["decision"].update(
        action="hold_for_review", decided_by="staff", next_action=None, next_action_at=None
    )
    doc["contact_action"] = "hold"

    def randomized(doc, history):
        fields = scored_fields("high", "call")
        fields.update(random_slice=True, action_probability=0.5)
        fields["scoring"]["chosen_by"] = "random slice"
        return fields

    monkeypatch.setattr(engine, "score", randomized)
    result = lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(note="Mẫu"), NOW)
    assert result["contact_action"] == "hold" and result["decision"]["decided_by"] == "staff"
    assert result["random_slice"] is False and result["action_probability"] == 1.0


@pytest.mark.parametrize("verified_by", ["confirmation", "deposit"])
def test_an_invalid_phone_edit_is_held_even_when_the_model_is_unavailable(
    store, monkeypatch, verified_by
):
    if verified_by == "deposit":
        monkeypatch.setattr(
            engine, "score", lambda doc, history: scored_fields("very_high", "deposit")
        )
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    if verified_by == "confirmation":
        lifecycle.apply_buyer_response(store, "ord_test", BuyerAction.CONFIRM, None, NOW)
    monkeypatch.setattr(engine, "score", lambda doc, history: None)
    result = lifecycle.edit_order(
        store, "ord_test", "shop_a", OrderUpdate(buyer_phone="+8400000000", prepaid_vnd=30000), NOW
    )
    assert result["buyer_phone_hash"] is None and result["scoring"] is None
    assert result["status"] == "pending_review"
    assert result["decision"]["action"] == "hold_for_review"
    assert result["decision"]["next_action"] is None and result["contact_action"] == "hold"


@pytest.mark.parametrize(
    "response", [CallOutcome.CONFIRMED, CallOutcome.CANCELLED, CallOutcome.NOT_ORDERED]
)
def test_completed_randomized_calls_keep_their_training_intervention(store, monkeypatch, response):
    def randomized(doc, history):
        fields = scored_fields("high", "call")
        fields.update(random_slice=True, action_probability=0.5)
        fields["scoring"]["chosen_by"] = "random slice"
        return fields

    monkeypatch.setattr(engine, "score", randomized)
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    result = lifecycle.apply_call_outcome(store, "ord_test", response, NOW)
    assert result["decision"]["next_action"] is None
    assert result["intervention"] == {
        "tier": "high",
        "contact_action": "call",
        "random_slice": True,
        "action_probability": 0.5,
    }
    if response == CallOutcome.CONFIRMED:
        updated = lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(note="Mẫu"), NOW)
        assert updated["intervention"] == result["intervention"]
        assert updated["contact_action"] == "none"


def test_answered_links_and_paid_deposits_preserve_the_completed_contact(store, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("medium", "link"))
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    answered = lifecycle.apply_buyer_response(store, "ord_test", BuyerAction.CONFIRM, None, NOW)
    assert answered["intervention"]["contact_action"] == "link"
    store.docs["ord_test"].pop("intervention")
    store.docs["ord_test"].pop("confirmation")
    store.docs["ord_test"]["scoring"] = None
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("very_high", "deposit"))
    lifecycle.score_order(store, store.docs["ord_test"], NOW)
    paid = lifecycle.edit_order(store, "ord_test", "shop_a", OrderUpdate(prepaid_vnd=30000), NOW)
    assert paid["intervention"]["contact_action"] == "deposit"
    assert paid["decision"]["action"] == "ship_now"


def test_escalation_keeps_the_original_randomized_contact_assignment(store, monkeypatch):
    def randomized(doc, history):
        fields = scored_fields("medium", "link")
        fields.update(random_slice=True, action_probability=1 / 3)
        fields["scoring"]["chosen_by"] = "random slice"
        return fields

    monkeypatch.setattr(engine, "score", randomized)
    first = lifecycle.score_order(store, store.docs["ord_test"], NOW)
    call = lifecycle.on_no_response(store, "ord_test", first["decision"]["next_action_at"])
    assert call["contact_action"] == "call"
    assert call["intervention"] == {
        "tier": "medium",
        "contact_action": "link",
        "random_slice": True,
        "action_probability": 1 / 3,
    }
    confirmed = lifecycle.apply_call_outcome(
        store, "ord_test", CallOutcome.CONFIRMED, NOW + timedelta(hours=3)
    )
    assert confirmed["intervention"] == call["intervention"]


@pytest.mark.parametrize("correction", ["deposit", "address"])
def test_contact_training_inputs_are_frozen_before_a_buyer_correction(
    store, monkeypatch, correction
):
    def randomized(doc, history):
        fields = scored_fields(
            "very_high" if correction == "deposit" else "high",
            "deposit" if correction == "deposit" else "call",
        )
        fields.update(random_slice=True, action_probability=0.5)
        fields["scoring"].update(
            chosen_by="random slice",
            features=compute_features(doc, history, doc["placed_at"], {"p0": 0.2, "province": {}}),
        )
        return fields

    monkeypatch.setattr(engine, "score", randomized)
    first = lifecycle.score_order(store, store.docs["ord_test"], NOW)
    if correction == "deposit":
        result = lifecycle.edit_order(
            store, "ord_test", "shop_a", OrderUpdate(prepaid_vnd=30000), NOW
        )
        assert result["scoring"]["features"]["cod_amount_vnd"] == 300000
    else:
        result = lifecycle.apply_call_outcome(
            store,
            "ord_test",
            CallOutcome.EDITED,
            NOW,
            update=OrderUpdate(address=Address(raw="Địa chỉ mẫu chưa có số nhà")),
        )
        assert result["scoring"]["features"]["address_missing_house_number"] == 1
    assert result["intervention"]["features"] == first["scoring"]["features"]
    assert result["intervention"]["probability"] == first["scoring"]["probability"]
    assert result["intervention"]["features"]["cod_amount_vnd"] == 330000
    assert result["intervention"]["features"]["address_missing_house_number"] == 0
    assert result["intervention"]["province"] == "Hà Nội"
