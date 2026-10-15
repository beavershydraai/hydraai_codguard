"""Shop app order writes (E7.2, E4.5): create, CSV import, edit and staff override."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.agents.log import get_decision_log
from app.calls.service import get_call_service
from app.data import order_csv
from app.data.store import get_store
from app.main import create_app
from app.risk import engine
from app.schemas.orders import OrderCreate
from tests.test_intake import FakeDecisionLog, FakeStore
from tests.test_lifecycle import scored_fields

ORDER = OrderCreate.model_config["json_schema_extra"]["examples"][0]
ADMIN = "admin@gmail.com"
TEMPLATE_HEADER = (
    "external_id,channel,buyer_name,buyer_phone,address,item_name,quantity,unit_price_vnd,"
    "shipping_fee_vnd,prepaid_vnd"
)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", ADMIN)
    monkeypatch.setenv("ADMIN_PASSWORD", "admin12345")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-at-least-32-bytes-long")
    monkeypatch.setenv("ADMIN_SHOP_ID", "shop_a")
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    store, decisions = FakeStore(), FakeDecisionLog()
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_decision_log] = lambda: decisions
    app.dependency_overrides[get_call_service] = lambda: None
    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/login", json={"username": ADMIN, "password": "admin12345"}
    ).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client, store, decisions


def create(client, **fields):
    return client.post("/api/v1/orders", json=ORDER | fields)


def upload(client, text: str):
    files = {"file": ("orders.csv", text.encode(), "text/csv")}
    return client.post("/api/v1/orders/import", files=files)


# ---------------------------------------------------------------- create


def test_create_needs_a_token(api):
    client, _, _ = api
    del client.headers["Authorization"]
    assert create(client).status_code == 401


def test_create_runs_the_pipeline_and_records_who_created_it(api):
    client, store, decisions = api
    response = create(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "awaiting_confirmation"
    assert body["tier"] == "high" and body["current_action"] == "ai_call"
    doc = store.docs[body["id"]]
    assert doc["shop_id"] == "shop_a"
    created = doc["timeline"][-1]
    assert created["type"] == "created" and created["actor"] == ADMIN
    assert created["message_vi"] == "Shop created the order manually."
    assert decisions.for_order(body["id"])


def test_create_rejects_a_repeated_external_id(api):
    client, store, _ = api
    assert create(client).status_code == 201
    response = create(client)
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"
    assert len(store.docs) == 1


def test_create_without_external_id_always_creates(api):
    client, store, _ = api
    assert create(client, external_id=None).status_code == 201
    assert create(client, external_id=None).status_code == 201
    assert len(store.docs) == 2


def test_create_validates_the_body(api):
    client, _, _ = api
    response = create(client, buyer_phone="not-a-phone")
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


# ---------------------------------------------------------------- import


def test_import_reads_the_shop_app_template(api, monkeypatch):
    client, store, _ = api
    monkeypatch.setenv("GEMINI_MODEL", "must-not-be-called")
    assert create(client, external_id="FB-OLD").status_code == 201
    fb1 = "FB-1,facebook,Nguyễn Văn Mẫu,0000000001,Số 1 ngõ 2 Hà Nội,Áo,1,189000,30000,0"
    text = "\n".join(
        [
            TEMPLATE_HEADER,
            fb1,
            "FB-2,,Trần Thị Mẫu,+84000000002,Số 3 đường Láng Hà Nội,Quần,2,150000,,",
            fb1,
            "FB-OLD,zalo,Lê Văn Mẫu,0000000003,Số 5 phố Huế Hà Nội,Mũ,1,99000,0,0",
            ",,,,,,,,,",
            "FB-3,zalo,Phạm Mẫu,12345,Số 7 phố Huế Hà Nội,Mũ,1,99000,0,0",
            "FB-4,zalo,Phạm Mẫu,0000000004,Số 7 phố Huế Hà Nội,Mũ,0,99000,0,0",
        ]
    )
    response = upload(client, text)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["received"] == 6
    assert body["imported"] == 2
    assert body["duplicates"] == 2
    assert [(r["row"], r["field"]) for r in body["rejected"]] == [
        (5, "buyer_phone"),
        (6, "quantity"),
    ]
    assert body["rejected"][0]["message"] == "Invalid phone number."
    imported = [d for d in store.docs.values() if d["external_id"] in {"FB-1", "FB-2"}]
    assert len(imported) == 2
    for doc in imported:
        assert doc["status"] == "awaiting_confirmation"
        assert doc["scoring"]["assessment"]["status"] == "skipped"
        assert doc["timeline"][-1]["message_vi"] == "Order imported from a CSV file."
    fb2 = next(d for d in imported if d["external_id"] == "FB-2")
    assert fb2["channel"] == "other"
    assert fb2["buyer_phone"] == "+84000000002"
    assert fb2["items"][0] == {
        "sku": None,
        "name": "Quần",
        "variant": None,
        "quantity": 2,
        "unit_price_vnd": 150000,
    }


def test_imported_orders_never_place_real_calls(api):
    client, store, _ = api

    class NoCalls:
        def __getattr__(self, name):
            raise AssertionError(f"An import must not use the call service ({name})")

    client.app.dependency_overrides[get_call_service] = NoCalls
    row = "FB-9,facebook,Mẫu,0000000009,Số 9 ngõ 2 Hà Nội,Áo,1,189000,30000,0"
    body = upload(client, f"{TEMPLATE_HEADER}\n{row}").json()
    assert body["imported"] == 1
    doc = next(iter(store.docs.values()))
    assert doc["decision"]["action"] == "ai_call"


def test_import_accepts_items_and_address_as_json(api):
    client, store, _ = api
    text = (
        "external_id,channel,buyer_name,buyer_phone,address,items,placed_at\n"
        'W-1,website,Mẫu,0000000005,"{""raw"": ""Số 9 phố Huế"", ""province"": ""Hà Nội""}",'
        '"[{""name"": ""Áo"", ""quantity"": 1, ""unit_price_vnd"": 100000},'
        ' {""name"": ""Quần"", ""quantity"": 1, ""unit_price_vnd"": 200000}]",'
        "2026-10-09T10:15:00+07:00\n"
        'W-2,website,Mẫu,0000000006,Số 9 phố Huế,"[not json",\n'
    )
    body = upload(client, text).json()
    assert body["imported"] == 1
    assert body["rejected"] == [{"row": 2, "field": "items", "message": "items is not valid JSON."}]
    doc = next(iter(store.docs.values()))
    assert doc["address"]["province"] == "Hà Nội"
    assert len(doc["items"]) == 2
    assert doc["placed_at"] == datetime(2026, 10, 9, 3, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("buyer_name,address\nA,B\n", "missing: buyer_phone, item_name"),
        (b"\xff\xfe".decode("latin-1"), "UTF-8"),
    ],
)
def test_import_rejects_an_unreadable_file(api, text, message):
    client, _, _ = api
    files = {"file": ("orders.csv", text.encode("latin-1"), "text/csv")}
    response = client.post("/api/v1/orders/import", files=files)
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_import_caps_the_number_of_rows(api, monkeypatch):
    client, store, _ = api
    monkeypatch.setattr(order_csv, "MAX_ROWS", 3)
    row = ",facebook,Mẫu,0000000001,Số 1 ngõ 2 Hà Nội,Áo,1,100000,0,0"
    response = upload(client, "\n".join([TEMPLATE_HEADER, *[row] * 4]))
    assert response.status_code == 400
    assert "more than 3" in response.json()["detail"]
    assert store.docs == {}


# ---------------------------------------------------------------- edit


def test_edit_rescores_and_records_the_editor(api):
    client, store, _ = api
    order_id = create(client).json()["id"]
    address = {"raw": "Số 15 ngõ 34, phường Láng, Hà Nội"}
    response = client.patch(f"/api/v1/orders/{order_id}", json={"address": address})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["address"]["raw"] == address["raw"]
    assert len(body["score_history"]) == 2
    edited = next(e for e in body["timeline"] if e["type"] == "edited")
    assert edited["actor"] == ADMIN


def test_edit_answers_404_for_another_shop_and_409_once_shipped(api):
    client, store, _ = api
    order_id = create(client).json()["id"]
    store.docs[order_id]["shop_id"] = "shop_b"
    assert client.patch(f"/api/v1/orders/{order_id}", json={"note": "x"}).status_code == 404
    store.docs[order_id] |= {"shop_id": "shop_a", "status": "shipped"}
    response = client.patch(f"/api/v1/orders/{order_id}", json={"note": "x"})
    assert response.status_code == 409
    assert response.json()["code"] == "order_not_editable"
    assert client.patch("/api/v1/orders/ord_missing", json={"note": "x"}).status_code == 404


def test_edit_rejects_null_required_fields(api):
    client, _, _ = api
    order_id = create(client).json()["id"]
    response = client.patch(f"/api/v1/orders/{order_id}", json={"buyer_name": None})
    assert response.status_code == 422


# ---------------------------------------------------------------- override


def test_order_lists_the_overrides_it_allows(api):
    client, store, _ = api
    order_id = create(client).json()["id"]
    detail = client.get(f"/api/v1/orders/{order_id}").json()
    assert detail["allowed_overrides"] == [
        "ship_now",
        "require_deposit",
        "hold_for_review",
        "cancel",
    ]
    store.docs[order_id]["status"] = "shipped"
    assert client.get(f"/api/v1/orders/{order_id}").json()["allowed_overrides"] == []


def test_override_records_who_when_and_why(api):
    client, store, decisions = api
    order_id = create(client).json()["id"]
    reason = "Regular buyer, confirmed on Zalo."
    response = client.post(
        f"/api/v1/orders/{order_id}/override", json={"action": "ship_now", "reason": reason}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cleared_to_ship"
    assert body["decision"]["action"] == "ship_now"
    assert body["decision"]["decided_by"] == "staff"
    assert "ship_now" not in body["allowed_overrides"]
    event = body["timeline"][0]
    assert (event["type"], event["actor"], event["reason"]) == ("override", ADMIN, reason)
    audit = decisions.for_order(order_id)[-1]
    assert (audit["workflow"], audit["action"], audit["actor"], audit["reason"]) == (
        "staff",
        "ship_now",
        ADMIN,
        reason,
    )


def test_a_staff_decision_survives_a_rescore(api):
    client, _, _ = api
    order_id = create(client).json()["id"]
    client.post(
        f"/api/v1/orders/{order_id}/override",
        json={"action": "require_deposit", "reason": "Large order."},
    )
    body = client.patch(f"/api/v1/orders/{order_id}", json={"note": "Call after 6pm"}).json()
    assert body["status"] == "awaiting_deposit"
    assert body["decision"]["decided_by"] == "staff"


def test_override_cancel_is_a_shop_cancellation(api):
    client, store, _ = api
    order_id = create(client).json()["id"]
    response = client.post(
        f"/api/v1/orders/{order_id}/override", json={"action": "cancel", "reason": "Out of stock."}
    )
    assert response.json()["status"] == "cancelled"
    assert response.json()["allowed_overrides"] == []
    assert store.docs[order_id]["cancel"]["reason"] == "shop"  # never a "failed" training label
    again = client.post(
        f"/api/v1/orders/{order_id}/override", json={"action": "ship_now", "reason": "Oops."}
    )
    assert again.status_code == 409
    assert again.json()["code"] == "order_not_editable"


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"action": "ai_call", "reason": "Call them."}, 409),
        ({"action": "ship_now", "reason": "x"}, 422),
        ({"action": "ship_now"}, 422),
    ],
)
def test_override_rejects_actions_staff_cannot_choose(api, body, status):
    client, store, _ = api
    order_id = create(client).json()["id"]
    before = store.docs[order_id]["decision"]
    response = client.post(f"/api/v1/orders/{order_id}/override", json=body)
    assert response.status_code == status
    assert store.docs[order_id]["decision"] == before


def test_override_of_the_action_in_force_is_rejected(api):
    client, _, _ = api
    order_id = create(client).json()["id"]
    path = f"/api/v1/orders/{order_id}/override"
    client.post(path, json={"action": "hold_for_review", "reason": "Check stock."})
    response = client.post(path, json={"action": "hold_for_review", "reason": "Again."})
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"
