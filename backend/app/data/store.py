"""Firestore access for orders (docs/data-model.md). Settings come from the environment:

- FIRESTORE_DATABASE: database id, `(default)` when unset (the demo uses `vn-synthetic`)
- PHONE_HASH_KEY: secret key for phone hashing (Secret Manager)
- INTAKE_API_KEYS: `key:shop_id` pairs separated by commas, one key per shop (Secret Manager)
"""

import hashlib
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


@lru_cache
def _client() -> firestore.Client:
    return firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", "(default)"))


@dataclass(frozen=True)
class OrderFilters:
    """What the inbox filters on in Firestore. Empty tuples filter nothing."""

    branches: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    tiers: tuple[str, ...] = ()
    placed_from: datetime | None = None
    placed_to: datetime | None = None


class OrderStore:
    def __init__(self, client):
        self.client = client
        self.orders = client.collection("orders")

    def create(self, doc: dict) -> dict | None:
        """Write a new order, or return the existing one if the id is taken. The write is atomic,
        so two requests with the same external_id cannot both create an order."""
        ref = self.orders.document(doc["order_id"])
        try:
            ref.create(doc)
            return None
        except AlreadyExists:
            return ref.get().to_dict()

    def get(self, order_id: str) -> dict | None:
        snapshot = self.orders.document(order_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def update(self, order_id: str, fields: dict) -> None:
        self.orders.document(order_id).update(fields)

    def transact(self, order_id: str, fn: Callable[[dict], dict]) -> dict:
        """Read, transform and write one order atomically, retrying concurrent updates.

        The callback runs again with the latest document after a conflict, so it must
        not perform external side effects. Missing orders raise `order_not_found`.
        """
        ref = self.orders.document(order_id)

        @firestore.transactional
        def apply(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                raise ValueError("order_not_found")
            updated = fn(snapshot.to_dict())
            transaction.set(ref, updated)
            return updated

        return apply(self.client.transaction())

    def history(self, phone_hash: str, before) -> list[dict]:
        """Earlier orders of a phone, all shops (composite index: buyer_phone_hash, placed_at)."""
        query = (
            self.orders.where(filter=FieldFilter("buyer_phone_hash", "==", phone_hash))
            .where(filter=FieldFilter("placed_at", "<", before))
            .order_by("placed_at")
        )
        return [d.to_dict() for d in query.stream()]

    def _filtered(self, shop_id: str, filters: OrderFilters):
        """The query for one shop's orders matching `filters`. Each list filter is an `in` (one
        value: `==`); the placing-time range needs the placing time as the sort."""
        query = self.orders.where(filter=FieldFilter("shop_id", "==", shop_id))
        for field, values in (
            ("branch_id", filters.branches),
            ("status", filters.statuses),
            ("tier", filters.tiers),
        ):
            if len(values) == 1:
                query = query.where(filter=FieldFilter(field, "==", values[0]))
            elif values:
                query = query.where(filter=FieldFilter(field, "in", list(values)))
        if filters.placed_from is not None:
            query = query.where(filter=FieldFilter("placed_at", ">=", filters.placed_from))
        if filters.placed_to is not None:
            query = query.where(filter=FieldFilter("placed_at", "<=", filters.placed_to))
        return query

    def page(
        self,
        shop_id: str,
        filters: OrderFilters,
        *,
        sort: str,
        after: str | None,
        limit: int,
        fields: tuple[str, ...],
    ) -> tuple[list[dict], bool]:
        """Up to `limit` orders after the order `after`, sorted by `sort` (a field, `-` for
        descending), with only `fields`, and whether more follow (composite indexes:
        infra/firestore.indexes.json). Raises LookupError when `after` is not an order."""
        direction = (
            firestore.Query.DESCENDING if sort.startswith("-") else firestore.Query.ASCENDING
        )
        query = (
            self._filtered(shop_id, filters)
            .order_by(sort.lstrip("-"), direction=direction)
            .order_by("__name__", direction=direction)
            .select(list(fields))
        )
        if after:
            snapshot = self.orders.document(after).get()
            if not snapshot.exists:
                raise LookupError(after)
            query = query.start_after(snapshot)
        docs = [d.to_dict() for d in query.limit(limit + 1).stream()]
        return docs[:limit], len(docs) > limit

    def count(self, shop_id: str, filters: OrderFilters) -> int:
        """Orders matching `filters` (a count aggregation: no order is read)."""
        result = self._filtered(shop_id, filters).count(alias="n").get()
        return int(result[0][0].value)

    def select(self, shop_id: str, filters: OrderFilters, fields: tuple[str, ...]) -> list[dict]:
        """Every order matching `filters`, with only `fields` (the dashboard counts them)."""
        query = self._filtered(shop_id, filters).select(list(fields))
        return [d.to_dict() for d in query.stream()]

    def last_change(self, shop_id: str) -> datetime | None:
        """When one of the shop's orders last changed (one document read)."""
        query = (
            self.orders.where(filter=FieldFilter("shop_id", "==", shop_id))
            .order_by("updated_at", direction=firestore.Query.DESCENDING)
            .select(["updated_at"])
            .limit(1)
        )
        latest = next(iter(query.stream()), None)
        return latest.to_dict().get("updated_at") if latest else None

    def find(self, shop_id: str, field: str, values: list[str], fields: tuple[str, ...]):
        """A shop's orders whose `field` is one of `values` (search by an exact value)."""
        query = (
            self.orders.where(filter=FieldFilter("shop_id", "==", shop_id))
            .where(filter=FieldFilter(field, "in", values))
            .select(list(fields))
        )
        return [d.to_dict() for d in query.stream()]

    def all(self) -> list[dict]:
        return [d.to_dict() for d in self.orders.stream()]


def get_store() -> OrderStore:
    return OrderStore(_client())


def phone_key() -> bytes:
    return os.environ["PHONE_HASH_KEY"].encode()


def _intake_keys() -> dict[str, tuple[str, str | None, bool]]:
    """INTAKE_API_KEYS entries `key:shop[:branch][:noagents]`: the branch that sends with the key
    (default: config/branches.yaml), and `noagents` for a test key whose orders skip the Gemini
    agents (the order simulator's default)."""
    keys = {}
    for entry in os.environ.get("INTAKE_API_KEYS", "").split(","):
        key, *rest = entry.split(":")
        if rest:
            branch = next((t for t in rest[1:] if t != "noagents"), None)
            keys[key] = (rest[0], branch, "noagents" in rest[1:])
    return keys


def shop_for_key(api_key: str | None) -> str | None:
    entry = _intake_keys().get(api_key) if api_key else None
    return entry[0] if entry else None


def branch_for_key(api_key: str | None) -> str | None:
    """The branch of the key; None means the default branch."""
    entry = _intake_keys().get(api_key) if api_key else None
    return entry[1] if entry else None


def agents_for_key(api_key: str | None) -> bool:
    """False for a `noagents` test key: its orders are scored and decided without Gemini."""
    entry = _intake_keys().get(api_key) if api_key else None
    return not (entry and entry[2])


def order_id_for(shop_id: str, external_id: str | None) -> str:
    """Same shop + external_id → same id, which makes intake idempotent."""
    if external_id is None:
        return f"ord_{uuid.uuid4().hex[:20]}"
    return "ord_" + hashlib.sha256(f"{shop_id}|{external_id}".encode()).hexdigest()[:20]
