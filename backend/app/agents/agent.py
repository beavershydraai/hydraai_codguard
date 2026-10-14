"""The ADK graphs that carry an order from intake to an action (E4.7, tasks/E4.7_ADK_pipeline.md).

Two workflows instead of one, because a buyer may answer hours later:

- `on_new_order`: load_order -> score -> assess_order -> decide -> one action branch.
  It ends after the action, so nothing holds state while waiting for a buyer.
- `on_contact_event`: load_event -> post_interaction -> one action branch. It runs the rule set's
  L4 table on what the buyer or the call reported; buyer edits retain lifecycle rescoring.

Only `decide` and `post_interaction` choose a branch, and both read the action from the
deterministic engine in app/decision. Two advisory agents assess evidence before the initial
decision is saved; their validated explanations never change score, tier or action.

Written for google-adk 2.x. The 1.x pattern (`SequentialAgent`, subclassing `BaseAgent` and
overriding `_run_async_impl`) is silently ignored by this version.
"""

import json
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

from google.adk import Event, Workflow
from google.adk.workflow import DEFAULT_ROUTE, RetryConfig, node
from google.api_core import exceptions as gcp
from google.genai import types

from app.agents import assessment, contact, routes
from app.agents.assessment import AssessmentResult
from app.agents.log import DecisionLog, entry
from app.data.store import OrderStore
from app.decision import lifecycle
from app.schemas.common import Address
from app.schemas.enums import BuyerAction, CallOutcome, DecisionAction
from app.schemas.orders import OrderUpdate
from app.schemas.scoring import Decision
from app.schemas.shops import Policy, ShopSettings

ON_NEW_ORDER = "cod_guard_on_new_order"
ON_CONTACT_EVENT = "cod_guard_on_contact_event"
# Branches that are not a Baseline A action. Everything else reaches DEFAULT_ROUTE, which
# holds the order for review: on an error or an unknown action nobody contacts the buyer.
UNSCORED = "UNSCORED"
CANCELLED = "CANCELLED"
UNCHANGED = "UNCHANGED"
# Only a transient failure is worth repeating. A data error (a missing field, a bad event) must
# fail on the first attempt and reach the review branch instead of being retried three times.
TRANSIENT = [OSError, TimeoutError, gcp.ServerError, gcp.TooManyRequests]
SCORE_RETRY = RetryConfig(max_attempts=3, initial_delay=1.0, exceptions=TRANSIENT)


@dataclass(frozen=True)
class Pipeline:
    """Everything the nodes need from the caller. `user_id` of an ADK session is the shop id, so
    one seller's orders never share a session with another's."""

    store: OrderStore
    log: DecisionLog
    settings: ShopSettings | None = None
    policy: Policy | None = None
    now: datetime | None = None


@dataclass
class _Run:
    """Shared by ADK child tasks for one invocation; never shared between intake requests."""

    pipeline: Pipeline
    committed_decision: dict | None = None


_current: ContextVar[_Run] = ContextVar("pipeline")


def use(pipeline: Pipeline):
    """Make `pipeline` the one the nodes of the current run use. Returns the context token."""
    return _current.set(_Run(pipeline))


def reset(token) -> None:
    _current.reset(token)


def current() -> Pipeline:
    return _current.get().pipeline


def committed_decision() -> dict | None:
    """The decision this invocation saved, used to guard its error fallback atomically."""
    return _current.get().committed_decision


class MissingOrder(LookupError):
    """The event names an order that is not stored. Not transient, so it is never retried."""


class AlreadyDecided(Exception):
    """This order already has a decision, so `on_new_order` has run for it. Rerunning would
    contact the buyer a second time, which the runner reports instead of doing."""


def load_order(node_input: types.Content) -> dict:
    """START: read the order the webhook named and stop a rerun before anything is sent."""
    request = json.loads(node_input.parts[0].text)
    order_id = request["order_id"]
    doc = current().store.get(order_id)
    if doc is None:
        raise MissingOrder(order_id)
    if doc.get("decision") is not None:
        raise AlreadyDecided(order_id)
    return doc


@node(retry_config=SCORE_RETRY)
def score(node_input: dict):
    """Prepare deterministic scoring without saving an action before advisory assessment.

    A transient model or storage failure is raised so ADK retries it up to three times. Catching
    it here would stop that, so nothing in this node is wrapped in `except`.
    """
    pipe = current()
    fields = lifecycle.prepare_score(pipe.store, node_input)
    scoring = (fields or {}).get("scoring") or {}
    yield Event(
        state={
            "risk": {
                "tier": (fields or {}).get("tier"),
                "failure_probability": scoring.get("probability"),
                "expected_loss_vnd": scoring.get("expected_loss_vnd"),
                "probs": scoring.get("outcome_probabilities") or {},
            }
        }
    )
    yield Event(output={"order": node_input, "fields": fields})


async def assess_order(node_input: dict) -> dict:
    """Assess a copy of the score and context; advisory code cannot mutate decision inputs."""
    fields = node_input["fields"]
    if fields is None:
        return node_input
    pipe = current()
    now = pipe.now or datetime.now(UTC)
    result = AssessmentResult.model_validate(
        await assessment.assess(deepcopy(node_input["order"] | fields), log=pipe.log, now=now)
    )
    if result.status == "quota_exhausted":
        raise ValueError("Assessment budget exhausted")
    fields = deepcopy(fields)
    fields["scoring"]["reasons"] = [reason.model_dump() for reason in result.reasons]
    fields["scoring"]["assessment"] = result.model_dump(exclude={"reasons"}, exclude_none=True)
    return node_input | {"fields": fields}


def decide(node_input: dict):
    """Commit the assessed score with deterministic policy guards, then log and route it."""
    pipe = current()
    fields = node_input["fields"]
    if fields is None:  # no model is trained yet (E2.4): the order waits, unscored
        yield Event(state={"decision": None})
        yield Event(output=node_input["order"], route=UNSCORED)
        return
    try:
        doc = lifecycle.commit_prepared_score(
            pipe.store,
            node_input["order"],
            fields,
            pipe.now or datetime.now(UTC),
            settings=pipe.settings,
            policy=pipe.policy,
        )
    except lifecycle.ExistingDecision as error:
        raise AlreadyDecided from error
    raw = doc["decision"]
    _current.get().committed_decision = deepcopy(raw)
    decision = Decision.model_validate(raw)
    row = entry(doc, decision, workflow=ON_NEW_ORDER, step="L3_initial_action")
    pipe.log.write(row)
    yield Event(state={"decision": _state(row)})
    yield Event(output=doc, route=routes.route_for(decision.action))


def load_event(node_input: types.Content) -> dict:
    """START of `on_contact_event`: the buyer's answer, a call outcome or an expired timer."""
    event = json.loads(node_input.parts[0].text)
    if current().store.get(event["order_id"]) is None:
        raise MissingOrder(event["order_id"])
    return event


def post_interaction(node_input: dict):
    """The rule set's L4 table: decide from what the buyer or the call reported, without running
    the risk model again (`AFTER_INTERACTION` carries `model_rerun: false`)."""
    pipe = current()
    before = _outcome(pipe.store.get(node_input["order_id"]) or {})
    doc = _apply(pipe, node_input)
    raw = doc.get("decision") or {}
    if not raw or _outcome(doc) == before:
        # L4 left the order alone: an early timer, or a repeat of an answer already recorded.
        yield Event(output=doc, route=UNCHANGED)
        return
    decision = Decision.model_validate(raw)
    row = entry(doc, decision, workflow=ON_CONTACT_EVENT, step=routes.POST_INTERACTION)
    pipe.log.write(row)
    yield Event(state={"decision": _state(row)})
    route = (
        CANCELLED if decision.action == DecisionAction.CANCEL else routes.route_for(decision.action)
    )
    yield Event(output=doc, route=route)


def _apply(pipe: Pipeline, event: dict) -> dict:
    """Hand the event to the E4.1 lifecycle, which applies it atomically."""
    order_id, kind = event["order_id"], event["type"]
    now = pipe.now or datetime.now(UTC)
    if kind == "buyer_response":
        address = event.get("address")
        return lifecycle.apply_buyer_response(
            pipe.store,
            order_id,
            BuyerAction(event["action"]),
            Address.model_validate(address) if address else None,
            now,
            settings=pipe.settings,
            policy=pipe.policy,
        )
    if kind == "call_outcome":
        update = event.get("update")
        return lifecycle.apply_call_outcome(
            pipe.store,
            order_id,
            CallOutcome(event["outcome"]),
            now,
            update=OrderUpdate.model_validate(update) if update else None,
            settings=pipe.settings,
            policy=pipe.policy,
        )
    if kind == "no_response":
        return lifecycle.on_no_response(
            pipe.store, order_id, now, settings=pipe.settings, policy=pipe.policy
        )
    raise ValueError(f"unknown contact event {kind!r}")


def _outcome(doc: dict) -> tuple:
    """What L4 may change about an order. Comparing it before and after tells a real decision
    from a timer that was not due, without relying on the clock moving between the two."""
    return doc.get("status"), json.dumps(doc.get("decision"), sort_keys=True, default=str)


def _state(row: dict) -> dict:
    """The part of a decision worth keeping in session state for `adk web` and debugging."""
    keys = ("action", "rule_id", "rule_set_version", "policy_version", "tier")
    return {k: row[k] for k in keys}


def ship(node_input: dict) -> dict:
    """ALLOW: tell the seller the order may go to the carrier. Nothing reaches the buyer."""
    return contact.notify_ship(node_input)


def send_confirm(node_input: dict) -> dict:
    """CONFIRM: one confirmation link per order (E5 sends it for real)."""
    pipe = current()
    return contact.contact(pipe.log, node_input, DecisionAction.SEND_CONFIRMATION_LINK, pipe.now)


def call_buyer(node_input: dict) -> dict:
    """CALL: hand the order to the voice agent (E5). The call itself is not placed here. The
    attempt is counted on the order, so the next unanswered timer knows how many calls were made."""
    pipe = current()
    result = contact.contact(pipe.log, node_input, DecisionAction.AI_CALL, pipe.now)
    if result["sent"]:
        lifecycle.record_call_attempt(
            pipe.store, node_input["order_id"], result["attempt"], result["sent_at"]
        )
    return result


def request_deposit(node_input: dict) -> dict:
    """DEPOSIT: ask for a deposit. The prototype never takes real money."""
    pipe = current()
    return contact.contact(pipe.log, node_input, DecisionAction.REQUIRE_DEPOSIT, pipe.now)


def review(node_input: dict) -> dict:
    """REVIEW and DEFAULT_ROUTE: a person decides. An action with no branch of its own lands
    here, so a new action in the rule set can never silently contact the buyer."""
    action = (node_input.get("decision") or {}).get("action")
    decided = action == DecisionAction.HOLD_FOR_REVIEW
    return contact.enqueue_review(node_input, "policy" if decided else f"unsupported:{action}")


def unscored(node_input: dict) -> dict:
    """No model is trained yet (E2.4). The order stays new and is scored again later."""
    return {
        "order_id": node_input["order_id"],
        "action": None,
        "status": node_input["status"],
        "reason": "not_scored",
    }


def record_cancel(node_input: dict) -> dict:
    """The buyer cancelled or said they did not order. Only they or the seller may cancel."""
    return {
        "order_id": node_input["order_id"],
        "action": DecisionAction.CANCEL.value,
        "status": node_input["status"],
        "cancel": node_input.get("cancel"),
    }


def unchanged(node_input: dict) -> dict:
    """L4 applied nothing: an early timer, or an answer that was already recorded."""
    return {
        "order_id": node_input["order_id"],
        "action": None,
        "status": node_input["status"],
        "reason": "no_change",
    }


_ACTION_BRANCHES = {
    routes.ALLOW: ship,
    routes.CONFIRM: send_confirm,
    routes.CALL: call_buyer,
    routes.DEPOSIT: request_deposit,
    DEFAULT_ROUTE: review,  # REVIEW, an action with no branch, or a route the engine never set
}

on_new_order = Workflow(
    name=ON_NEW_ORDER,
    description="Score a new COD order, apply the tier policy and carry out the chosen action.",
    edges=[
        ("START", load_order, score, assess_order, decide),
        (decide, _ACTION_BRANCHES | {UNSCORED: unscored}),
    ],
)

on_contact_event = Workflow(
    name=ON_CONTACT_EVENT,
    description="Apply the rule set's L4 table to a buyer answer, a call outcome or a timer.",
    edges=[
        ("START", load_event, post_interaction),
        (post_interaction, _ACTION_BRANCHES | {CANCELLED: record_cancel, UNCHANGED: unchanged}),
    ],
)

# `adk web` and `adk run` look for this name.
root_agent = on_new_order
