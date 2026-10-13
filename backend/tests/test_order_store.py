"""Order updates run through the SDK's retrying transaction decorator, without RPCs."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import Aborted
from google.cloud.firestore_v1.transaction import Transaction

from app.data.store import OrderStore


class Document:
    def __init__(self, client, order_id):
        self.client = client
        self.order_id = order_id

    def get(self, *, transaction):
        assert transaction.in_progress
        doc = deepcopy(self.client.docs.get(self.order_id))
        return SimpleNamespace(exists=doc is not None, to_dict=lambda: doc)


class MemoryTransaction(Transaction):
    """Keep SDK retry behavior; replace only database reads and writes."""

    def __init__(self, client):
        super().__init__(client)
        self.pending = None

    def _begin(self, retry_id=None):
        self._id = b"memory-transaction"
        self.pending = None

    def set(self, ref, doc):
        self.pending = (ref.order_id, deepcopy(doc))

    def _commit(self):
        if self._client.conflict is not None:
            conflict, self._client.conflict = self._client.conflict, None
            conflict(self._client.docs)
            raise Aborted("Concurrent update")
        if self.pending is not None:
            order_id, doc = self.pending
            self._client.docs[order_id] = doc
        self._clean_up()
        return []

    def _rollback(self):
        self.pending = None
        self._clean_up()


class MemoryClient:
    def __init__(self, docs, conflict=None):
        self.docs = deepcopy(docs)
        self.conflict = conflict

    def collection(self, name):
        assert name == "orders"
        return self

    def document(self, order_id):
        return Document(self, order_id)

    def transaction(self):
        return MemoryTransaction(self)


def test_order_transaction_returns_and_commits_the_complete_order():
    client = MemoryClient({"ord_01": {"status": "new", "note": "keep"}})
    store = OrderStore(client)
    result = store.transact("ord_01", lambda doc: {**doc, "status": "cleared_to_ship"})
    assert result == {"status": "cleared_to_ship", "note": "keep"}
    assert client.docs["ord_01"] == result


def test_order_transaction_retries_against_the_latest_document():
    def concurrent_update(docs):
        docs["ord_01"].update(status="cleared_to_ship", note="concurrent edit")

    client = MemoryClient({"ord_01": {"status": "new", "note": "old"}}, concurrent_update)
    seen = []

    def ship(doc):
        seen.append(doc["status"])
        return {**doc, "status": "shipped" if doc["status"] == "cleared_to_ship" else "new"}

    result = OrderStore(client).transact("ord_01", ship)
    assert seen == ["new", "cleared_to_ship"]
    assert result == {"status": "shipped", "note": "concurrent edit"}
    assert client.docs["ord_01"] == result


def test_order_transaction_propagates_callback_errors_without_writing():
    client = MemoryClient({"ord_01": {"status": "shipped"}})

    def invalid_edit(doc):
        doc["status"] = "new"
        raise ValueError("order_not_editable")

    with pytest.raises(ValueError, match="order_not_editable"):
        OrderStore(client).transact("ord_01", invalid_edit)
    assert client.docs["ord_01"] == {"status": "shipped"}


def test_order_transaction_rejects_missing_orders():
    client = MemoryClient({})
    with pytest.raises(ValueError, match="order_not_found"):
        OrderStore(client).transact("missing", lambda doc: doc)
    assert client.docs == {}
