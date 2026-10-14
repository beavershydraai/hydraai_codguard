"""How the backend runs the ADK graphs (E4.7).

`run_new_order` is what the intake endpoint and the demo scripts call. It owns the two guarantees
the graph cannot give on its own:

- a run that still fails after its retries holds the order for review, so a broken model or a
  storage outage never leaves an order contacted or lost;
- a rerun for an order that already has a decision reports it instead of deciding again.

`InMemorySessionService` keeps nothing across a restart. That costs us no business data, because
the decision log is a Firestore collection of our own rather than ADK session state. A deployment
that wants the per-node history of past runs should pass `DatabaseSessionService` instead.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from google.adk import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from app.agents import agent
from app.agents.agent import AlreadyDecided, Pipeline
from app.agents.log import entry
from app.decision import lifecycle
from app.schemas.enums import DecisionAction
from app.schemas.scoring import Decision

APP_NAME = "codguard"
log = logging.getLogger(__name__)


async def _run(workflow, payload: dict, shop_id: str, session_service) -> dict:
    """Drive one workflow to its last node and return what that node produced.

    The ADK session's `user_id` is the shop id, so one seller's runs are never mixed with
    another's.
    """
    session = await session_service.create_session(app_name=APP_NAME, user_id=shop_id)
    message = types.Content(role="user", parts=[types.Part(text=json.dumps(payload, default=str))])
    runner = Runner(app_name=APP_NAME, node=workflow, session_service=session_service)
    result: dict = {}
    async for event in runner.run_async(
        user_id=shop_id, session_id=session.id, new_message=message
    ):
        if event.output is not None:
            result = event.output
    return result


async def run_new_order(
    order_id: str,
    shop_id: str,
    *,
    pipeline: Pipeline,
    session_service: BaseSessionService | None = None,
) -> dict:
    """Run `load_order -> score -> decide -> act` for one new order.

    Returns what the action branch produced, `{"duplicate": True}` for an order that already has
    a decision, or the result of holding the order for review when the run failed.
    """
    token = agent.use(pipeline)
    try:
        return await _run(
            agent.on_new_order,
            {"order_id": order_id},
            shop_id,
            session_service or InMemorySessionService(),
        )
    except AlreadyDecided:
        return {"order_id": order_id, "action": None, "duplicate": True}
    except Exception:
        log.exception("on_new_order failed for %s", order_id)
        return hold_for_review(order_id, pipeline, agent.ON_NEW_ORDER)
    finally:
        agent.reset(token)


def run_new_order_sync(order_id: str, shop_id: str, *, pipeline: Pipeline) -> dict:
    """`run_new_order` for a caller that is not async. The intake route is a sync endpoint, so
    FastAPI runs it in a worker thread that has no event loop of its own."""
    return asyncio.run(run_new_order(order_id, shop_id, pipeline=pipeline))


async def run_contact_event(
    event: dict,
    shop_id: str,
    *,
    pipeline: Pipeline,
    session_service: BaseSessionService | None = None,
) -> dict:
    """Run the rule set's L4 table for one buyer answer, call outcome or expired timer."""
    token = agent.use(pipeline)
    try:
        return await _run(
            agent.on_contact_event, event, shop_id, session_service or InMemorySessionService()
        )
    except Exception:
        log.exception("on_contact_event failed for %s", event.get("order_id"))
        return hold_for_review(event["order_id"], pipeline, agent.ON_CONTACT_EVENT)
    finally:
        agent.reset(token)


def hold_for_review(order_id: str, pipeline: Pipeline, workflow: str) -> dict:
    """The fallback for a failed run: a person looks at the order and nobody is contacted."""
    now = pipeline.now or datetime.now(UTC)
    try:
        doc = lifecycle.hold_for_review(
            pipeline.store, order_id, now, settings=pipeline.settings, policy=pipeline.policy
        )
    except Exception:
        log.exception("Could not hold %s for review", order_id)
        return {"order_id": order_id, "action": None, "reason": "pipeline_failed"}
    decision = doc.get("decision")
    if decision:
        row = entry(doc, Decision.model_validate(decision), workflow=workflow, step="fallback")
        row["fallback_reason"] = "pipeline_failed"
        pipeline.log.write(row)
    return {
        "order_id": order_id,
        "action": DecisionAction.HOLD_FOR_REVIEW.value,
        "status": doc["status"],
        "reason": "pipeline_failed",
    }
