"""The order inbox: filter, search, sort and page a shop's orders.

The shop's orders come from one Firestore query (shop and placing time). Status, tier, search and
sorting run here, because the tier lives inside `scoring` and the COD amount is derived, so
Firestore cannot filter or sort on them. Fine for demo-sized shops (a few thousand orders).
"""

import base64
import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime

from app.data.phone import to_e164
from app.decision.views import order_summary
from app.schemas.enums import OrderStatus, RiskTier
from app.schemas.orders import OrderPage, OrderSummary

_NON_DIGITS = re.compile(r"\D")


class InvalidCursor(ValueError):
    """The cursor is malformed or belongs to a different query."""


def _fold(text: str) -> str:
    """Lower case without Vietnamese diacritics, so "nguyen" finds "Nguyễn"."""
    text = text.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def _phone_forms(phone: str | None) -> tuple[str, ...]:
    """Digits of a stored phone in international (84…) and local (0…) form."""
    digits = _NON_DIGITS.sub("", phone or "")
    if digits.startswith("84"):
        return digits, "0" + digits[2:]
    return (digits,)


def _matches(order: OrderSummary, q: str) -> bool:
    needle = _fold(q.strip())
    if not needle:
        return True
    text = " ".join(_fold(v) for v in (order.id, order.external_id or "", order.buyer_name))
    if needle in text:
        return True
    digits = _NON_DIGITS.sub("", q)
    if len(digits) < 3:
        return False
    e164 = to_e164(q)
    if e164:
        return order.buyer_phone == e164
    return any(digits in form for form in _phone_forms(order.buyer_phone))


def _sort_key(sort: str):
    """Key for `sorted`; ties fall back to the order id so pages are stable."""
    match sort:
        case "placed_at" | "-placed_at":
            return lambda o: (o.placed_at, o.id)
        case "-updated_at":
            return lambda o: (o.updated_at, o.id)
        case "-cod_amount_vnd":
            return lambda o: (o.cod_amount_vnd, o.id)
        case "-risk_score":
            # Unscored orders sort last.
            return lambda o: (o.risk_score is not None, o.risk_score or 0, o.id)
    raise ValueError(sort)


def _fingerprint(**query) -> str:
    raw = json.dumps(query, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _encode_cursor(offset: int, fingerprint: str) -> str:
    return base64.urlsafe_b64encode(f"{offset}:{fingerprint}".encode()).decode().rstrip("=")


def _decode_cursor(cursor: str, fingerprint: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        offset, found = raw.split(":", 1)
        offset = int(offset)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursor("The cursor is not valid.") from exc
    if found != fingerprint or offset < 0:
        raise InvalidCursor("The cursor belongs to a different query. Start from the first page.")
    return offset


def order_page(
    docs: Iterable[dict],
    *,
    statuses: list[OrderStatus],
    tiers: list[RiskTier],
    q: str | None,
    placed_from: datetime | None,
    placed_to: datetime | None,
    sort: str,
    cursor: str | None,
    limit: int,
) -> OrderPage:
    fingerprint = _fingerprint(
        statuses=sorted(statuses),
        tiers=sorted(tiers),
        q=q,
        placed_from=placed_from,
        placed_to=placed_to,
        sort=sort,
    )
    offset = _decode_cursor(cursor, fingerprint) if cursor else 0

    rows = [
        order
        for order in map(order_summary, docs)
        if (not statuses or order.status in statuses)
        and (not tiers or order.tier in tiers)
        and (not q or _matches(order, q))
    ]
    rows.sort(key=_sort_key(sort), reverse=sort.startswith("-"))

    page = rows[offset : offset + limit]
    more = offset + limit < len(rows)
    return OrderPage(
        items=page,
        next_cursor=_encode_cursor(offset + limit, fingerprint) if more else None,
        total=len(rows),
    )
