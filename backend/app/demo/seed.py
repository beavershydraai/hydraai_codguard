"""Load the demo shop's training history: `python -m app.demo.seed --days 90 [--apply]`.

Generates `--days` of orders for every branch (app/demo/world.py) with a fixed seed, so a reset
gives the same demo (E1.3), and writes them to Firestore FIRESTORE_DATABASE as finished orders:
delivered, failed, cancelled by the buyer, or held up by the carrier or the shop. They carry no
score: `codguard-train` learns from them. Without --apply it only prints what it would write.
"""

import argparse
import collections
from datetime import UTC, datetime, timedelta

from app.data.orders import order_document
from app.data.store import order_id_for, phone_key
from app.demo.world import SHOP_ID, Order, World
from app.schemas.orders import OrderCreate

STATUS = {
    "delivered": "delivered",
    "refused": "delivery_failed",
    "unreachable": "delivery_failed",
    "carrier_issue": "delivery_failed",
    "shop_issue": "delivery_failed",
    "cancelled": "cancelled",
}


def stored_doc(order: Order, key: bytes) -> dict:
    """The Firestore document of a finished history order."""
    payload = OrderCreate.model_validate(order.payload)
    doc = order_document(
        payload,
        order_id=order_id_for(SHOP_ID, payload.external_id),
        shop_id=SHOP_ID,
        phone_key=key,
        now=payload.placed_at.astimezone(UTC),
        branch_id=order.branch_id,
    )
    at = doc["placed_at"] + order.outcome_after
    if order.outcome == "cancelled":
        doc["cancel"] = {"reason": "cancelled", "at": at, "by": "buyer"}
    else:
        doc["delivery"] = {
            "result": order.outcome,
            "carrier": "other",
            "tracking_code": None,
            "occurred_at": at,
        }
    doc["status"], doc["updated_at"] = STATUS[order.outcome], at
    return doc


def history_docs(days: int, end: datetime, seed: int = 7) -> list[dict]:
    """`days` of finished orders ending `end` (orders newer than 14 days still lack outcomes
    for training, as in a real shop)."""
    start = (end - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    key = phone_key()
    return [stored_doc(o, key) for o in World(seed).history(start.replace(tzinfo=None), days)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--apply", action="store_true", help="write to Firestore")
    args = parser.parse_args()
    docs = history_docs(args.days, datetime.now(UTC))
    counts = collections.Counter((d["branch_id"], d["status"]) for d in docs)
    for (branch, status), n in sorted(counts.items()):
        print(f"{branch:15s} {status:16s} {n:6d}")
    print(f"{len(docs)} orders")
    if not args.apply:
        print("Dry run: nothing written. Add --apply to write to Firestore.")
        return
    from app.data.store import get_store

    db = get_store().client
    orders = get_store().orders
    for i in range(0, len(docs), 400):
        batch = db.batch()
        for doc in docs[i : i + 400]:
            batch.set(orders.document(doc["order_id"]), doc)
        batch.commit()
    print(f"Wrote {len(docs)} orders.")


if __name__ == "__main__":
    main()
