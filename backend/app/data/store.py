"""Firestore access for orders (docs/data-model.md). Settings come from the environment:

- FIRESTORE_DATABASE: database id, `(default)` when unset (the demo uses `vn-synthetic`)
- PHONE_HASH_KEY: secret key for phone hashing (Secret Manager)
- INTAKE_API_KEYS: `key:shop_id` pairs separated by commas, one key per shop (Secret Manager)
"""

import hashlib
import os
import uuid
from functools import lru_cache

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore


@lru_cache
def _client() -> firestore.Client:
    return firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", "(default)"))


class OrderStore:
    def __init__(self, client):
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
