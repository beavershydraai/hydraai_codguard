"""Receive one new order and run the pipeline on it (E4.7).

Shared by the intake API, the shop app's "create order" and its CSV import, so an order runs
`on_new_order` the same way whichever door it came in by.
"""

import logging
from datetime import UTC, datetime

from app.agents.agent import Pipeline
from app.agents.runner import run_new_order_sync
from app.data.orders import order_document
from app.data.store import order_id_for, phone_key
from app.schemas.orders import OrderCreate

log = logging.getLogger(__name__)


def receive(
    body: OrderCreate,
    shop_id: str,
    *,
    pipeline: Pipeline,
    actor: str = "system",
    message: str = "Order created.",
    now: datetime | None = None,
) -> tuple[dict, bool]:
    """Store the order and decide it. Returns the stored order and whether it was a duplicate:
    the same `external_id` at the same shop returns the existing order, unchanged."""
    now = now or datetime.now(UTC)
    order_id = order_id_for(shop_id, body.external_id)
    doc = order_document(body, order_id=order_id, shop_id=shop_id, phone_key=phone_key(), now=now)
    doc["timeline"][0] |= {"actor": actor, "message_vi": message}
    existing = pipeline.store.create(doc)
    if existing:
        return existing, True
    try:  # a pipeline problem must never lose the order: it stays stored, for review or unscored
        run_new_order_sync(order_id, shop_id, pipeline=pipeline)
        doc = pipeline.store.get(order_id) or doc
    except Exception:
        log.exception("The pipeline failed for %s", order_id)
    return doc, False
