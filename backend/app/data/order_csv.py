"""Order rows from a CSV file (E7.2): `POST /orders/import`.

Columns are the fields of OrderCreate. Two shorthands keep the file easy to fill in a
spreadsheet, and they are what the shop app's template uses:

- `address` holds the address as the buyer wrote it (or an Address as JSON); `address_street`,
  `address_ward` and `address_province` add the parsed parts.
- `items` holds the items as JSON. Without it, one row is one item: `item_name`, `quantity`,
  `unit_price_vnd`, and optionally `sku` and `variant`.

An empty `channel` means `other` and an empty `placed_at` means the time of the import.
"""

import csv
import io
import json
from datetime import datetime

from pydantic import ValidationError

from app.schemas.orders import ImportRowError, OrderCreate

MAX_ROWS = 1000
MAX_BYTES = 5 * 1024 * 1024
REQUIRED = ("buyer_name", "buyer_phone", "address")
ITEM_COLUMNS = ("item_name", "quantity", "unit_price_vnd")
_TRUE = {"1", "true", "yes", "y", "x"}
_TEXT = (
    "external_id",
    "recipient_name",
    "recipient_phone",
    "conversation_text",
    "note",
    "buyer_name",
    "buyer_phone",
)
_AMOUNTS = ("shipping_fee_vnd", "discount_vnd", "prepaid_vnd")
_PHONES = ("buyer_phone", "recipient_phone")


class BadFile(ValueError):
    """The file as a whole cannot be read: not UTF-8, too big, too many rows or missing columns.
    Answered with 400; a bad row is reported in `rejected` instead."""


def read_rows(data: bytes) -> list[dict[str, str]]:
    """Data rows keyed by lower-case column name; blank rows are dropped."""
    if len(data) > MAX_BYTES:
        raise BadFile(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise BadFile("The file is not UTF-8 text.") from error
    reader = csv.reader(io.StringIO(text))
    header = [name.strip().lower() for name in next(reader, [])]
    missing = [name for name in REQUIRED if name not in header]
    if "items" not in header:
        missing += [name for name in ITEM_COLUMNS if name not in header]
    if missing:
        raise BadFile(f"CSV header is missing: {', '.join(missing)}.")
    rows = []
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue
        cells += [""] * (len(header) - len(cells))
        rows.append({name: cells[i].strip() for i, name in enumerate(header)})
        if len(rows) > MAX_ROWS:
            raise BadFile(f"The file has more than {MAX_ROWS:,} orders.")
    return rows


def _json(value: str, field: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise _RowError(field, f"{field} is not valid JSON.") from error


class _RowError(Exception):
    def __init__(self, field: str, message: str):
        self.field, self.message = field, message


def _order_fields(row: dict[str, str], now: datetime) -> dict:
    fields: dict = {name: row[name] or None for name in _TEXT if name in row}
    fields["channel"] = row.get("channel") or "other"
    fields["is_gift"] = row.get("is_gift", "").lower() in _TRUE
    for name in _AMOUNTS:
        if row.get(name):
            fields[name] = row[name]
    fields["placed_at"] = row.get("placed_at") or now
    address = row["address"]
    fields["address"] = _json(address, "address") if address.startswith("{") else {"raw": address}
    if isinstance(fields["address"], dict):
        for part in ("street", "ward", "province"):
            if row.get(f"address_{part}"):
                fields["address"][part] = row[f"address_{part}"]
    if row.get("items"):
        fields["items"] = _json(row["items"], "items")
    else:
        item = {name: row.get(name) or None for name in ("sku", "variant")}
        item |= {
            "name": row.get("item_name"),
            "quantity": row.get("quantity"),
            "unit_price_vnd": row.get("unit_price_vnd"),
        }
        fields["items"] = [item]
    return fields


def parse_row(number: int, row: dict[str, str], now: datetime) -> OrderCreate | ImportRowError:
    """One row as an order, or the first problem found in it. `number` is 1-based, header
    excluded."""
    try:
        return OrderCreate.model_validate(_order_fields(row, now))
    except _RowError as error:
        return ImportRowError(row=number, field=error.field, message=error.message)
    except ValidationError as error:
        first = error.errors()[0]
        loc = [str(part) for part in first["loc"]]
        field = loc[0] if loc else None
        if field == "items" and len(loc) == 3 and "items" not in row:
            field = {"name": "item_name"}.get(loc[2], loc[2])  # the one-item-per-row columns
        elif field == "address" and len(loc) == 2 and loc[1] != "raw":
            field = f"address_{loc[1]}"
        message = first["msg"]
        if first["type"] == "string_pattern_mismatch" and field in _PHONES:
            message = "Invalid phone number."
        return ImportRowError(row=number, field=field, message=message)
