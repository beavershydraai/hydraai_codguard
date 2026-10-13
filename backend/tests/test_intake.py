import pytest
from fastapi.testclient import TestClient

from app.data.store import get_store
from app.main import create_app
from app.schemas.orders import OrderCreate

ORDER = OrderCreate.model_config["json_schema_extra"]["examples"][0]


class FakeStore:
    def __init__(self):
        self.docs = {}

    def create(self, doc):
        if doc["order_id"] in self.docs:
            return self.docs[doc["order_id"]]
        self.docs[doc["order_id"]] = doc
        return None


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("INTAKE_API_KEYS", "key-a:shop_a,key-b:shop_b")
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
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
