"""A shop's past orders with their delivery results, from a CSV file: onboarding's
`POST /shop/history`, so a new shop's history joins what the risk models learn from.

Columns are those of the order import (app/data/order_csv.py), plus:
- `branch_id`: the branch that took the order (config/branches.yaml);
- `delivery_result`: delivered, refused, unreachable, carrier_issue, shop_issue, or cancelled
  (the buyer cancelled before shipping);
- `outcome_at`: when the result became known (ISO 8601; without a zone, the branch's local time).

`external_id` is required, so uploading the same file again replaces the same orders. Each row
becomes a finished, unscored order of the shop; `codguard-train` learns from it.
"""

from datetime import datetime

from app.data import branches, order_csv
from app.data.orders import order_document, to_utc
from app.data.store import order_id_for
from app.schemas.orders import ImportRowError, OrderCreate

MAX_ROWS = 20_000
MAX_BYTES = 20 * 1024 * 1024
COLUMNS = ("external_id", "branch_id", "delivery_result", "outcome_at")
STATUS = {
    "delivered": "delivered",
    "refused": "delivery_failed",
    "unreachable": "delivery_failed",
    "carrier_issue": "delivery_failed",
    "shop_issue": "delivery_failed",
    "cancelled": "cancelled",
}


def finished_doc(
    order: OrderCreate,
    *,
    shop_id: str,
    branch_id: str,
    outcome: str,
    outcome_at: datetime,
    key: bytes,
) -> dict:
    """The Firestore document of a finished order: delivered, failed or cancelled by the buyer."""
    tz = branches.country(branches.branches()[branch_id]).tz
    doc = order_document(
        order,
        order_id=order_id_for(shop_id, order.external_id),
        shop_id=shop_id,
        phone_key=key,
        now=to_utc(order.placed_at, tz),
        branch_id=branch_id,
    )
    at = to_utc(outcome_at, tz)
    if outcome == "cancelled":
        doc["cancel"] = {"reason": "cancelled", "at": at, "by": "buyer"}
    else:
        doc["delivery"] = {
            "result": outcome,
            "carrier": "other",
            "tracking_code": None,
            "occurred_at": at,
        }
    doc["status"], doc["updated_at"] = STATUS[outcome], at
    return doc


def _row(number: int, row: dict, shop_id: str, key: bytes, now: datetime) -> dict | ImportRowError:
    def error(field: str, message: str) -> ImportRowError:
        return ImportRowError(row=number, field=field, message=message)

    order = order_csv.parse_row(number, row, now)
    if isinstance(order, ImportRowError):
        return order
    if not order.external_id:
        return error("external_id", "Each past order needs its shop order ID.")
    branch_id = row.get("branch_id", "")
    if branch_id not in branches.branches():
        return error("branch_id", f"Unknown branch {branch_id!r}.")
    currency = branches.country(branches.branches()[branch_id]).currency
    if order.currency and order.currency != currency:
        return error("currency", f"This branch takes orders in {currency}.")
    outcome = row.get("delivery_result", "")
    if outcome not in STATUS:
        return error("delivery_result", f"Use one of: {', '.join(STATUS)}.")
    try:
        outcome_at = datetime.fromisoformat(row.get("outcome_at", ""))
    except ValueError:
        return error("outcome_at", "Use a date and time in ISO 8601, e.g. 2026-10-01T15:30:00.")
    tz = branches.country(branches.branches()[branch_id]).tz
    if to_utc(outcome_at, tz) < to_utc(order.placed_at, tz):
        return error("outcome_at", "The result cannot come before the order was placed.")
    return finished_doc(
        order, shop_id=shop_id, branch_id=branch_id, outcome=outcome, outcome_at=outcome_at, key=key
    )


def parse(
    data: bytes, shop_id: str, key: bytes, now: datetime
) -> tuple[list[dict], list[ImportRowError], int]:
    """The finished orders of a history file, the rows rejected, and the rows read.
    Raises order_csv.BadFile for a file that cannot be read at all."""
    rows = order_csv.read_rows(data, max_rows=MAX_ROWS, max_bytes=MAX_BYTES)
    missing = [name for name in COLUMNS if rows and name not in rows[0]]
    if missing:
        raise order_csv.BadFile(f"CSV header is missing: {', '.join(missing)}.")
    docs, rejected, seen = [], [], set()
    for number, row in enumerate(rows, start=1):
        parsed = _row(number, row, shop_id, key, now)
        if isinstance(parsed, ImportRowError):
            rejected.append(parsed)
        elif parsed["order_id"] not in seen:  # the same order twice in one file counts once
            seen.add(parsed["order_id"])
            docs.append(parsed)
    return docs, rejected, len(rows)
