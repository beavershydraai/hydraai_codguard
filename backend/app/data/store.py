"""Firestore access for orders (docs/data-model.md). Settings come from the environment:

- FIRESTORE_DATABASE: database id, `(default)` when unset (the demo uses `vn-synthetic`)
- PHONE_HASH_KEY: secret key for phone hashing (Secret Manager)
- INTAKE_API_KEYS: `key:shop_id` pairs separated by commas, one key per shop (Secret Manager)
"""

import hashlib
import os
import uuid
from collections.abc import Callable
from functools import lru_cache

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


@lru_cache
def _client() -> firestore.Client:
    return firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", "(default)"))


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

    def all(self) -> list[dict]:
        return [d.to_dict() for d in self.orders.stream()]


def get_store() -> OrderStore:
    return OrderStore(_client())


def phone_key() -> bytes:
    return os.environ["PHONE_HASH_KEY"].encode()


def shop_for_key(api_key: str | None) -> str | None:
    pairs = (p.split(":", 1) for p in os.environ.get("INTAKE_API_KEYS", "").split(",") if ":" in p)
    return dict(pairs).get(api_key) if api_key else None


def order_id_for(shop_id: str, external_id: str | None) -> str:
    """Same shop + external_id → same id, which makes intake idempotent."""
    if external_id is None:
        return f"ord_{uuid.uuid4().hex[:20]}"
    return "ord_" + hashlib.sha256(f"{shop_id}|{external_id}".encode()).hexdigest()[:20]
