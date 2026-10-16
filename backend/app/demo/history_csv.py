"""Write a shop's past orders as a CSV for onboarding's history upload (`POST /shop/history`):

    python -m app.demo.history_csv --days 30 --out fashion_store_history.csv [--seed 11]

The orders come from the same synthetic world as the demo shop (app/demo/world.py: every branch,
fixed seed, outcomes included), ending yesterday. Phones are synthetic (`+84000…`). The columns
are the ones app/data/history.py reads, so the file imports without rejected rows.
"""

import argparse
import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.demo.world import World

COLUMNS = [
    "external_id",
    "branch_id",
    "channel",
    "buyer_name",
    "buyer_phone",
    "is_gift",
    "address",
    "items",
    "shipping_fee_vnd",
    "discount_vnd",
    "prepaid_vnd",
    "currency",
    "placed_at",
    "delivery_result",
    "outcome_at",
]


def rows(days: int, end: datetime, seed: int) -> list[dict]:
    start = (end - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for order in World(seed).history(start.replace(tzinfo=None), days):
        p = order.payload
        placed = datetime.fromisoformat(p["placed_at"])
        out.append(
            {
                "external_id": p["external_id"],
                "branch_id": order.branch_id,
                "channel": p["channel"],
                "buyer_name": p["buyer_name"],
                "buyer_phone": p["buyer_phone"],
                "is_gift": "true" if p["is_gift"] else "",
                "address": json.dumps(p["address"], ensure_ascii=False),
                "items": json.dumps(p["items"], ensure_ascii=False),
                "shipping_fee_vnd": p["shipping_fee_vnd"],
                "discount_vnd": p["discount_vnd"],
                "prepaid_vnd": p["prepaid_vnd"],
                "currency": p["currency"],
                "placed_at": p["placed_at"],
                "delivery_result": order.outcome,
                "outcome_at": (placed + order.outcome_after).isoformat(),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=11, help="another seed than the demo shop's")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    end = datetime.now(UTC) - timedelta(days=1)
    data = rows(args.days, end, args.seed)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(data)
    print(f"{len(data)} orders → {args.out}")


if __name__ == "__main__":
    main()
