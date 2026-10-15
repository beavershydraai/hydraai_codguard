"""Firestore `calls/{call_id}`: one document per call attempt, with the job that was published,
the controller's progress and the final result (transcript included, so it never goes to logs).
The orders on the call keep a copy of the public `Call` view for the order page."""

from collections.abc import Callable

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.data.store import _client


class CallNotFound(LookupError):
    pass


class CallStore:
    def __init__(self, client):
        self.client = client
        self.calls = client.collection("calls")

    def create(self, doc: dict) -> dict | None:
        """Write a new call, or return the existing one if the id is taken."""
        ref = self.calls.document(doc["call_id"])
        try:
            ref.create(doc)
            return None
        except AlreadyExists:
            return ref.get().to_dict()

    def get(self, call_id: str) -> dict | None:
        snapshot = self.calls.document(call_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def transact(self, call_id: str, fn: Callable[[dict], dict]) -> dict:
        """Read, change and write one call atomically. The callback may run again after a
        conflict, so it must have no side effects. A missing call raises CallNotFound."""
        ref = self.calls.document(call_id)

        @firestore.transactional
        def apply(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                raise CallNotFound(call_id)
            updated = fn(snapshot.to_dict())
            transaction.set(ref, updated)
            return updated

        return apply(self.client.transaction())

    def for_phone(self, phone_hash: str) -> list[dict]:
        """Every call to a phone, all shops. A single equality filter needs no composite index;
        callers filter by time in Python."""
        query = self.calls.where(filter=FieldFilter("phone_hash", "==", phone_hash))
        return [d.to_dict() for d in query.stream()]


def get_call_store() -> CallStore:
    return CallStore(_client())
