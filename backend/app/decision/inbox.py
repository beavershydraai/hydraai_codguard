"""The order inbox: filter, search, sort and page a shop's orders (E7.2).

Firestore does the work, so a page costs the same whatever the shop's size: it filters by branch,
status, tier and placing time, sorts, and returns one page of `limit` orders after a cursor, with
only the fields a row needs. The total comes from a count aggregation. Each combination of
filters and sort has its composite index in infra/firestore.indexes.json.

Search finds orders by an exact value: the order ID, the shop's order ID (`external_id`) or the
buyer's full phone number (matched by its keyed hash, since phones are stored encrypted). Firestore
has no text search, so there is no search by part of a name or number.
"""

import base64
import json
import re

from app.data import branches
from app.data.phone import phone_hash, to_e164
from app.data.store import OrderFilters, OrderStore, phone_key
from app.decision.views import SUMMARY_PROJECTION, order_summary
from app.schemas.enums import OrderStatus, RiskTier
from app.schemas.orders import OrderPage, OrderSummary

# API sort -> stored field (top level, so Firestore can sort on it).
SORTS = {
    "-placed_at": "-placed_at",
    "placed_at": "placed_at",
    "-updated_at": "-updated_at",
    "-risk_score": "-risk_score",
    "-cod_amount_vnd": "-cod_amount_vnd",
}
MAX_DISJUNCTIONS = 30  # Firestore: `in` filters together may expand to at most 30 combinations
_DIGITS = re.compile(r"\D")


class InvalidQuery(ValueError):
    """The filters, sort or cursor cannot be served. The message is safe to show."""


class InvalidCursor(InvalidQuery):
    """The cursor is malformed or belongs to a different query."""


def _encode_cursor(after: str, query: dict) -> str:
    raw = json.dumps({"after": after, "query": query}, sort_keys=True, default=str)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str, query: dict) -> str:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        after, found = raw["after"], raw["query"]
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursor("The cursor is not valid.") from exc
    if found != json.loads(json.dumps(query, sort_keys=True, default=str)):
        raise InvalidCursor("The cursor belongs to a different query. Start from the first page.")
    return after


def _narrow(values: list, every: list) -> tuple:
    """The filter values, or none when they cover every value (the same as no filter)."""
    return () if set(values) >= set(every) else tuple(sorted(set(values)))


def filters_for(
    *, statuses: list, tiers: list, branch_ids: list, placed_from, placed_to, sort: str
) -> OrderFilters:
    known = branches.branches()
    unknown = sorted(set(branch_ids) - set(known))
    if unknown:
        raise InvalidQuery(f"Unknown branch: {', '.join(unknown)}.")
    filters = OrderFilters(
        branches=_narrow(branch_ids, list(known)),
        statuses=_narrow([str(s) for s in statuses], [s.value for s in OrderStatus]),
        tiers=_narrow([str(t) for t in tiers], [t.value for t in RiskTier]),
        placed_from=placed_from,
        placed_to=placed_to,
    )
    combinations = 1
    for values in (filters.branches, filters.statuses, filters.tiers):
        combinations *= max(len(values), 1)
    if combinations > MAX_DISJUNCTIONS:
        raise InvalidQuery(
            f"Too many filter values together ({combinations}, at most {MAX_DISJUNCTIONS}). "
            "Pick fewer branches, statuses or tiers."
        )
    if (placed_from or placed_to) and sort.lstrip("-") != "placed_at":
        raise InvalidQuery("A placing-time range works only with sorting by placing time.")
    return filters


def _phone_hashes(q: str) -> list[str]:
    """Hashes of `q` read as a full phone number of each country where the shop sells."""
    if len(_DIGITS.sub("", q)) < 8:
        return []
    codes = {branches.country(code).calling_code for code in branches.countries()}
    numbers = {e164 for code in codes if (e164 := to_e164(q, code))}
    return sorted(phone_hash(number, phone_key()) for number in numbers)


def _sort_key(sort: str):
    """Key for sorting search results like Firestore sorts a page; ties fall back to the id."""
    field = sort.lstrip("-")
    if field == "risk_score":  # unscored orders sort last
        return lambda o: (o.risk_score is not None, o.risk_score or 0, o.id)
    return lambda o: (getattr(o, field), o.id)


def _matches(order: OrderSummary, filters: OrderFilters) -> bool:
    return (
        (not filters.branches or order.branch_id in filters.branches)
        and (not filters.statuses or order.status in filters.statuses)
        and (not filters.tiers or order.tier in filters.tiers)
        and (filters.placed_from is None or order.placed_at >= filters.placed_from)
        and (filters.placed_to is None or order.placed_at <= filters.placed_to)
    )


def search(store: OrderStore, shop_id: str, q: str, filters: OrderFilters, sort: str, limit: int):
    """Orders whose ID, shop order ID or full phone number is `q`. Few orders match, so the other
    filters and the sort run here, on them."""
    q = q.strip()
    found: dict[str, dict] = {}
    for field, values in (
        ("order_id", [q]),
        ("external_id", [q]),
        ("buyer_phone_hash", _phone_hashes(q)),
    ):
        if values:
            for doc in store.find(shop_id, field, values, SUMMARY_PROJECTION):
                found[doc["order_id"]] = doc
    rows = [o for o in map(order_summary, found.values()) if _matches(o, filters)]
    rows.sort(key=_sort_key(sort), reverse=sort.startswith("-"))
    return OrderPage(items=rows[:limit], next_cursor=None, total=len(rows))


def order_page(
    store: OrderStore,
    shop_id: str,
    *,
    statuses: list[OrderStatus],
    tiers: list[RiskTier],
    branch_ids: list[str],
    q: str | None,
    placed_from,
    placed_to,
    sort: str,
    cursor: str | None,
    limit: int,
) -> OrderPage:
    sort = SORTS[sort]
    filters = filters_for(
        statuses=statuses,
        tiers=tiers,
        branch_ids=branch_ids,
        placed_from=placed_from,
        placed_to=placed_to,
        sort=sort,
    )
    if q and q.strip():
        return search(store, shop_id, q, filters, sort, limit)
    query = {"filters": filters.__dict__, "sort": sort}
    after = _decode_cursor(cursor, query) if cursor else None
    try:
        docs, more = store.page(
            shop_id, filters, sort=sort, after=after, limit=limit, fields=SUMMARY_PROJECTION
        )
    except LookupError as exc:
        raise InvalidCursor(
            "The cursor's order no longer exists. Start from the first page."
        ) from exc
    items = [order_summary(doc) for doc in docs]
    return OrderPage(
        items=items,
        next_cursor=_encode_cursor(items[-1].id, query) if more and items else None,
        total=store.count(shop_id, filters),
    )
