"""E4.7 ADK pipeline: a new order runs load_order -> score -> decide -> act on its own, and no
failure or unknown action can make it contact the buyer.

The tests drive the real `google.adk` graphs. Only the risk model is replaced, so the routing,
the retries, the DEFAULT_ROUTE fallback and the decision log are the ones that run in production.
"""

from copy import deepcopy
from datetime import timedelta

import pytest

from app.agents import agent, contact, routes
from app.agents.agent import Pipeline
from app.agents.runner import run_contact_event, run_new_order
from app.data.orders import order_document
from app.risk import engine
from app.schemas.enums import DecisionAction, OrderStatus
from app.schemas.orders import OrderCreate
from app.schemas.scoring import Decision
from tests.test_intake import FakeDecisionLog, FakeStore
from tests.test_lifecycle import scored_fields
from tests.test_policy import NOW

SHOP = "shop_a"
EXAMPLE = OrderCreate.model_config["json_schema_extra"]["examples"][0]


def _order(store: FakeStore, order_id: str) -> dict:
    order = OrderCreate.model_validate(EXAMPLE)
    doc = order_document(order, order_id=order_id, shop_id=SHOP, phone_key=b"test-key", now=NOW)
    store.create(doc)
    return doc


@pytest.fixture
def pipe(monkeypatch):
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields())
    store, log = FakeStore(), FakeDecisionLog()
    _order(store, "ord_test")
    return Pipeline(store=store, log=log, now=NOW)


def scorer(tier, action, calls=None):
    """A stand-in risk model that records how often the pipeline asked it to score."""

    def score(doc, history):
        if calls is not None:
            calls.append(doc["order_id"])
        return scored_fields(tier, action)

    return score


async def run(pipe, order_id="ord_test"):
    return await run_new_order(order_id, SHOP, pipeline=pipe)


# --- 1 and 2: the two branches a new order normally takes -------------------------------------


@pytest.mark.asyncio
async def test_a_low_risk_order_ships_without_contacting_the_buyer(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", scorer("low", "none"))
    result = await run(pipe)
    assert result["action"] == DecisionAction.SHIP_NOW
    assert pipe.store.get("ord_test")["status"] == OrderStatus.CLEARED_TO_SHIP
    assert pipe.log.claims == {}  # nothing was sent to the buyer


@pytest.mark.asyncio
async def test_a_medium_risk_order_sends_one_confirmation_link(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", scorer("medium", "link"))
    result = await run(pipe)
    assert result["action"] == DecisionAction.SEND_CONFIRMATION_LINK
    assert result["sent"] is True and result["mock"] is True
    assert pipe.store.get("ord_test")["status"] == OrderStatus.AWAITING_CONFIRMATION
    assert list(pipe.log.claims) == ["ord_test:send_confirmation_link"]


# --- 3: a transient failure is retried, a data error is not -----------------------------------


@pytest.mark.asyncio
async def test_a_transient_scoring_failure_is_retried_until_it_succeeds(pipe, monkeypatch):
    attempts = []

    def flaky(doc, history):
        attempts.append(doc["order_id"])
        if len(attempts) < 3:
            raise ConnectionError("the model endpoint is unreachable")
        return scored_fields("low", "none")

    monkeypatch.setattr(engine, "score", flaky)
    monkeypatch.setattr(agent.SCORE_RETRY, "initial_delay", 0.01)
    result = await run(pipe)
    assert len(attempts) == 3
    assert result["action"] == DecisionAction.SHIP_NOW
    assert pipe.store.get("ord_test")["status"] == OrderStatus.CLEARED_TO_SHIP


@pytest.mark.asyncio
async def test_scoring_that_keeps_failing_holds_the_order_for_review(pipe, monkeypatch):
    attempts = []

    def broken(doc, history):
        attempts.append(doc["order_id"])
        raise ConnectionError("the model endpoint is unreachable")

    monkeypatch.setattr(engine, "score", broken)
    monkeypatch.setattr(agent.SCORE_RETRY, "initial_delay", 0.01)
    result = await run(pipe)
    assert len(attempts) == 3  # the three attempts E4.7 asks for, then the fallback
    assert result["action"] == DecisionAction.HOLD_FOR_REVIEW
    assert result["reason"] == "pipeline_failed"
    assert pipe.store.get("ord_test")["status"] == OrderStatus.PENDING_REVIEW
    assert pipe.log.claims == {}  # a failure never reaches the buyer


@pytest.mark.asyncio
async def test_a_data_error_is_not_retried_and_holds_the_order_for_review(pipe, monkeypatch):
    attempts = []

    def bad_data(doc, history):
        attempts.append(doc["order_id"])
        raise KeyError("buyer_phone")

    monkeypatch.setattr(engine, "score", bad_data)
    result = await run(pipe)
    assert len(attempts) == 1
    assert result["action"] == DecisionAction.HOLD_FOR_REVIEW
    assert pipe.store.get("ord_test")["status"] == OrderStatus.PENDING_REVIEW


# --- 4: an action with no branch of its own falls back to review ------------------------------


@pytest.mark.asyncio
async def test_an_action_without_a_branch_reaches_review_through_default_route(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", scorer("high", "hold"))
    result = await run(pipe)
    assert result["action"] == DecisionAction.HOLD_FOR_REVIEW
    assert result["reason"] == "policy"
    assert pipe.store.get("ord_test")["status"] == OrderStatus.PENDING_REVIEW
    assert pipe.log.claims == {}


def test_every_decided_action_has_a_branch_and_an_unknown_one_lands_on_review():
    for action in DecisionAction:
        if action == DecisionAction.CANCEL:
            continue
        assert routes.route_for(action) in routes.BRANCHES
    assert routes.route_for("teleport_the_parcel") == routes.REVIEW
    assert routes.route_for(None) == routes.REVIEW


@pytest.mark.asyncio
async def test_an_action_the_graph_cannot_perform_does_not_contact_the_buyer(pipe, monkeypatch):
    """A new Baseline A action in the rule set must reach review, not a buyer."""
    monkeypatch.setattr(engine, "score", scorer("medium", "link"))
    monkeypatch.setattr(routes, "route_for", lambda action: "NUDGE_PREPAID")
    result = await run(pipe)
    assert result["action"] == DecisionAction.HOLD_FOR_REVIEW
    assert result["reason"].startswith("unsupported:")
    assert pipe.log.claims == {}


# --- 5: running the same order twice never sends a second message -----------------------------


@pytest.mark.asyncio
async def test_rerunning_the_same_order_does_not_send_a_second_message(pipe, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "score", scorer("medium", "link", calls))
    first = await run(pipe)
    again = await run(pipe)
    assert first["sent"] is True
    assert again == {"order_id": "ord_test", "action": None, "duplicate": True}
    assert len(calls) == 1  # the order was not scored again either
    assert list(pipe.log.claims) == ["ord_test:send_confirmation_link"]


def test_a_repeated_send_reports_the_first_one_instead_of_sending_again(pipe):
    """The claim, not the duplicate check, is what makes a send idempotent under an ADK retry."""
    doc = pipe.store.get("ord_test")
    action = DecisionAction.SEND_CONFIRMATION_LINK
    first = contact.contact(pipe.log, doc, action, NOW)
    again = contact.contact(pipe.log, doc, action, NOW + timedelta(minutes=5))
    assert first["sent"] is True
    assert again["sent"] is False and again["sent_at"] == NOW
    assert len(pipe.log.claims) == 1


def _call_decided(doc: dict, at) -> dict:
    decision = Decision(decided_at=at, action=DecisionAction.AI_CALL, policy_version=1)
    return doc | {"decision": decision.model_dump()}


def test_each_call_attempt_is_claimed_once_by_its_own_decision(pipe):
    """A rerun of a decision finds its own attempt, even after a later decision took the next
    one, and a decision beyond the two attempts reaches nobody."""
    doc = pipe.store.get("ord_test")
    first, second, third = (_call_decided(doc, NOW + timedelta(minutes=30 * i)) for i in range(3))
    action = DecisionAction.AI_CALL
    results = [
        contact.contact(pipe.log, first, action, NOW),
        contact.contact(pipe.log, second, action, NOW + timedelta(minutes=30)),
        contact.contact(pipe.log, first, action, NOW + timedelta(minutes=31)),  # a late rerun
        contact.contact(pipe.log, third, action, NOW + timedelta(minutes=60)),
    ]
    assert [(r["sent"], r.get("attempt")) for r in results] == [
        (True, 1),
        (True, 2),
        (False, 1),
        (False, 2),
    ]
    assert sorted(pipe.log.claims) == ["ord_test:ai_call:1", "ord_test:ai_call:2"]


@pytest.mark.asyncio
async def test_an_order_that_is_not_stored_is_held_for_nobody(pipe):
    result = await run(pipe, "ord_missing")
    assert result == {"order_id": "ord_missing", "action": None, "reason": "order_not_found"}


# --- 6: the decision log ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_decision_log_records_the_rule_and_the_rule_set_version(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", scorer("medium", "link"))
    await run(pipe)
    (row,) = pipe.log.for_order("ord_test")
    assert row["order_id"] == "ord_test" and row["shop_id"] == SHOP
    assert row["action"] == DecisionAction.SEND_CONFIRMATION_LINK
    assert row["rule_id"] == "L3_initial_action#tier_action"
    assert row["rule_set_version"] == routes.rule_set_version()
    assert row["workflow"] == agent.ON_NEW_ORDER
    assert row["tier"] == "medium" and row["policy_version"] >= 1
    assert row["failure_probability"] == 0.6


@pytest.mark.asyncio
async def test_a_hard_rule_is_logged_with_its_own_rule_id(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", scorer("high", "hold"))
    await run(pipe)
    (row,) = pipe.log.for_order("ord_test")
    assert row["rule_id"] == "D03_invalid_phone"


@pytest.mark.asyncio
async def test_the_log_carries_the_seven_outcome_probabilities_once_the_model_reports_them(
    pipe, monkeypatch
):
    """E2.5 will replace the binary model. The log already passes its distribution through."""
    probs = {name: round(1 / len(routes.outcomes()), 4) for name in routes.outcomes()}

    def seven_outcomes(doc, history):
        fields = scored_fields("medium", "link")
        fields["scoring"]["outcome_probabilities"] = probs
        return fields

    monkeypatch.setattr(engine, "score", seven_outcomes)
    await run(pipe)
    (row,) = pipe.log.for_order("ord_test")
    assert row["probs"] == probs
    assert len(routes.outcomes()) == 7


# --- the second workflow: what the buyer or the call reported ---------------------------------


@pytest.mark.asyncio
async def test_a_confirmed_order_ships_without_being_scored_again(pipe, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "score", scorer("medium", "link", calls))
    await run(pipe)
    result = await run_contact_event(
        {"order_id": "ord_test", "type": "buyer_response", "action": "confirm"},
        SHOP,
        pipeline=pipe,
    )
    assert result["action"] == DecisionAction.SHIP_NOW
    assert pipe.store.get("ord_test")["status"] == OrderStatus.CLEARED_TO_SHIP
    assert len(calls) == 1  # L4 decides from the answer, it never reruns the model


@pytest.mark.asyncio
async def test_a_buyer_cancellation_is_recorded_and_contacts_nobody(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", scorer("medium", "link"))
    await run(pipe)
    before = deepcopy(pipe.log.claims)
    result = await run_contact_event(
        {"order_id": "ord_test", "type": "buyer_response", "action": "not_ordered"},
        SHOP,
        pipeline=pipe,
    )
    assert result["action"] == DecisionAction.CANCEL
    assert pipe.store.get("ord_test")["status"] == OrderStatus.CANCELLED
    assert pipe.log.claims == before


@pytest.mark.asyncio
async def test_an_unanswered_link_escalates_to_a_call_and_is_logged(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", scorer("medium", "link"))
    await run(pipe)
    due = Decision.model_validate(pipe.store.get("ord_test")["decision"]).next_action_at
    later = Pipeline(store=pipe.store, log=pipe.log, now=due)
    result = await run_contact_event(
        {"order_id": "ord_test", "type": "no_response"}, SHOP, pipeline=later
    )
    assert result["action"] == DecisionAction.AI_CALL
    assert sorted(pipe.log.claims) == ["ord_test:ai_call:1", "ord_test:send_confirmation_link"]
    assert [r["workflow"] for r in pipe.log.for_order("ord_test")] == [
        agent.ON_NEW_ORDER,
        agent.ON_CONTACT_EVENT,
    ]


def next_action_at(pipe):
    return Decision.model_validate(pipe.store.get("ord_test")["decision"]).next_action_at


async def no_response(pipe, at):
    """Fire the order's no-response timer at `at`."""
    later = Pipeline(store=pipe.store, log=pipe.log, now=at)
    event = {"order_id": "ord_test", "type": "no_response"}
    return await run_contact_event(event, SHOP, pipeline=later)


@pytest.mark.asyncio
async def test_second_call_is_placed_then_review(pipe, monkeypatch):
    """Two call attempts 30 minutes apart (E4.2), then a person decides. The second attempt used
    to hit the first one's claim, and every later timer chose a call that was never placed."""
    monkeypatch.setattr(engine, "score", scorer("high", "call"))
    first = await run(pipe)
    retry_at = next_action_at(pipe)
    second = await no_response(pipe, retry_at)
    replay = await no_response(pipe, retry_at)  # the same timer delivered again
    last = await no_response(pipe, next_action_at(pipe))

    assert first["sent"] is True
    assert second["action"] == DecisionAction.AI_CALL and second["sent"] is True
    assert replay["reason"] == "no_change"
    assert last["action"] == DecisionAction.HOLD_FOR_REVIEW
    order = pipe.store.get("ord_test")
    assert order["status"] == OrderStatus.PENDING_REVIEW
    assert sorted(pipe.log.claims) == ["ord_test:ai_call:1", "ord_test:ai_call:2"]
    assert (first["attempt"], second["attempt"], order["attempts"]) == (1, 2, {"ai_call": 2})


@pytest.mark.asyncio
async def test_a_timer_that_is_not_due_yet_changes_nothing(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", scorer("medium", "link"))
    await run(pipe)
    result = await run_contact_event(
        {"order_id": "ord_test", "type": "no_response"}, SHOP, pipeline=pipe
    )
    assert result["reason"] == "no_change"
    assert pipe.store.get("ord_test")["status"] == OrderStatus.AWAITING_CONFIRMATION
    assert len(pipe.log.for_order("ord_test")) == 1


@pytest.mark.asyncio
async def test_an_unknown_contact_event_holds_the_order_for_review(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", scorer("medium", "link"))
    await run(pipe)
    result = await run_contact_event(
        {"order_id": "ord_test", "type": "carrier_sneezed"}, SHOP, pipeline=pipe
    )
    assert result["action"] == DecisionAction.HOLD_FOR_REVIEW
    assert pipe.store.get("ord_test")["status"] == OrderStatus.PENDING_REVIEW
