import pickle
from copy import deepcopy
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.agents.log import get_decision_log
from app.data.store import get_store
from app.main import create_app
from app.risk import artifacts, engine
from app.risk.jobs.train import train
from app.schemas.orders import OrderCreate
from tests.risk_data import START, orders

ORDER = OrderCreate.model_config["json_schema_extra"]["examples"][0]


class FakeStore:
    def __init__(self):
        self.docs = {}

    def create(self, doc):
        if doc["order_id"] in self.docs:
            return self.docs[doc["order_id"]]
        self.docs[doc["order_id"]] = doc
        return None

    def get(self, order_id):
        doc = self.docs.get(order_id)
        return deepcopy(doc) if doc else None

    def update(self, order_id, fields):
        self.docs[order_id].update(fields)

    def transact(self, order_id, fn):
        if order_id not in self.docs:
            raise ValueError("order_not_found")
        result = fn(deepcopy(self.docs[order_id]))
        self.docs[order_id] = deepcopy(result)
        return result

    def for_shop(self, shop_id, placed_from=None, placed_to=None):
        docs = [
            deepcopy(d)
            for d in self.docs.values()
            if d["shop_id"] == shop_id
            and (placed_from is None or d["placed_at"] >= placed_from)
            and (placed_to is None or d["placed_at"] <= placed_to)
        ]
        return sorted(docs, key=lambda d: d["placed_at"], reverse=True)

    def history(self, phone_hash, before):
        return [
            d
            for d in self.docs.values()
            if d["buyer_phone_hash"] == phone_hash and d["placed_at"] < before
        ]


class FakeDecisionLog:
    """In-memory stand-in for app.agents.log.DecisionLog, with the same atomic claim."""

    def __init__(self):
        self.rows = {}
        self.claims = {}

    def write(self, row):
        self.rows[row["order_id"], row["decided_at"]] = deepcopy(row)

    def for_order(self, order_id):
        rows = [r for r in self.rows.values() if r["order_id"] == order_id]
        return sorted(rows, key=lambda r: r["decided_at"])

    def claim(self, key, record):
        if key in self.claims:
            return False
        self.claims[key] = deepcopy(record)
        return True

    def claimed(self, key):
        return self.claims.get(key)


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("INTAKE_API_KEYS", "key-a:shop_a,key-b:shop_b")
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))  # no model yet
    engine._cache.update(at=0.0, models=None)
    store, decisions = FakeStore(), FakeDecisionLog()
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_decision_log] = lambda: decisions
    return TestClient(app), store


def post(client, key, body=ORDER):
    headers = {"X-Api-Key": key} if key else {}
    return client.post("/api/v1/intake/orders", json=body, headers=headers)


def test_intake_rejects_missing_or_unknown_key(api):
    client, _ = api
    for key in (None, "nope"):
        response = post(client, key)
        assert response.status_code == 401
        assert response.json()["code"] == "unauthorized"


def test_intake_stores_a_normalised_order(api):
    client, store = api
    response = post(client, "key-a")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "new" and body["duplicate"] is False
    doc = store.docs[body["order_id"]]
    assert doc["shop_id"] == "shop_a"
    assert doc["buyer_phone"] == "+84000000001"
    assert doc["buyer_phone_hash"]


def test_intake_is_idempotent_on_external_id_per_shop(api):
    client, store = api
    first = post(client, "key-a").json()
    again = post(client, "key-a").json()
    other_shop = post(client, "key-b").json()
    assert again == {"order_id": first["order_id"], "status": "new", "duplicate": True}
    assert other_shop["order_id"] != first["order_id"]
    assert len(store.docs) == 2


def test_intake_without_a_model_stores_the_order_unscored(api):
    client, store = api
    doc = store.docs[post(client, "key-a").json()["order_id"]]
    assert doc["scoring"] is None


def test_intake_scores_the_order_when_a_model_exists(api):
    client, store = api
    model, _, _ = train(orders(), START + timedelta(days=200), None)
    artifacts.write("latest/model1.pkl", pickle.dumps(model))
    engine._cache.update(at=0.0, models=None)
    doc = store.docs[post(client, "key-a").json()["order_id"]]
    engine._cache.update(at=0.0, models=None)
    assert 0 <= doc["scoring"]["probability"] <= 1
    assert doc["scoring"]["chosen_by"] and doc["contact_action"]
    assert doc["scoring"]["features"]["address_has_house_number"] == 1


def test_intake_returns_the_decided_status_and_duplicate_preserves_it(api, monkeypatch):
    client, store = api
    from tests.test_lifecycle import scored_fields

    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    first = post(client, "key-a").json()
    assert first["status"] == "awaiting_confirmation"
    again = post(client, "key-a").json()
    assert again == {
        "order_id": first["order_id"],
        "status": "awaiting_confirmation",
        "duplicate": True,
    }
    doc = store.docs[first["order_id"]]
    assert doc["decision"]["action"] == "ai_call"
    assert [e["type"] for e in doc["timeline"]] == ["decided", "scored", "created"]


def test_scoring_failure_holds_an_intake_order_for_review(api, monkeypatch):
    """E4.7: a pipeline that keeps failing hands the order to a person, never to the buyer."""
    client, store = api

    def fail(doc, history):
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(engine, "score", fail)
    response = post(client, "key-a")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending_review"
    doc = store.docs[body["order_id"]]
    assert doc["scoring"] is None
    assert doc["decision"]["action"] == "hold_for_review"
