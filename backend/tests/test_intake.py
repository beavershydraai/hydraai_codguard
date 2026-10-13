import pickle
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

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

    def update(self, order_id, fields):
        self.docs[order_id].update(fields)

    def history(self, phone_hash, before):
        return [
            d
            for d in self.docs.values()
            if d["buyer_phone_hash"] == phone_hash and d["placed_at"] < before
        ]


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("INTAKE_API_KEYS", "key-a:shop_a,key-b:shop_b")
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))  # no model yet
    engine._cache.update(at=0.0, models=None)
    store = FakeStore()
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
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
