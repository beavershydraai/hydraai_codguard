"""No-response timers (E4.2): what happens when the buyer does not answer a link, a call or a
deposit request in time.

Every decision that waits for the buyer saves `next_action` and `next_action_at`. Cloud Scheduler
calls POST /internal/timers/run every 5 minutes (job `codguard-timers`); each due order runs the
pipeline's `on_contact_event` with a `no_response` event, exactly as a real timer would: the
second AI call after the shop's gap, the call after an unanswered link, review after the last
attempt. A timer that fires early or for an order that moved on changes nothing.
"""

import asyncio
from datetime import datetime

from app.agents.log import DecisionLog
from app.data.policies import PolicyStore
from app.data.shops import ShopStore
from app.data.store import OrderStore
from app.decision.lifecycle import WAITING

BATCH = 50  # orders per run; the next run picks up the rest


def run_due(
    store: OrderStore,
    log: DecisionLog,
    shops: ShopStore,
    policies: PolicyStore,
    now: datetime,
    calls=None,
) -> int:
    """Fire the timers due at `now`, oldest first. Returns how many orders were handled."""
    from app.agents.agent import Pipeline  # the pipeline imports the decision modules
    from app.agents.runner import run_contact_event

    pipelines: dict[str, Pipeline] = {}
    due = store.due(tuple(WAITING), now, BATCH)
    for doc in due:
        shop_id = doc["shop_id"]
        if shop_id not in pipelines:
            pipelines[shop_id] = Pipeline(
                store=store,
                log=log,
                calls=calls,
                settings=shops.settings(shop_id),
                policy=policies.current(shop_id),
                now=now,
            )
        event = {"order_id": doc["order_id"], "type": "no_response"}
        asyncio.run(run_contact_event(event, shop_id, pipeline=pipelines[shop_id]))
    return len(due)
