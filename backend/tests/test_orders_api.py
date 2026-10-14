"""GET /orders (inbox) and GET /orders/{id}, scoped to the signed-in user's shop."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.data.orders import order_document
from app.data.store import get_store
from app.main import create_app
from app.schemas.orders import OrderCreate
from tests.test_intake import FakeStore

T0 = datetime(2026, 10, 13, 3, tzinfo=UTC)


def make(
    order_id,
    *,
    shop_id="shop_a",
    minutes=0,
    name="Khách demo",
    phone="+84000000001",
    external_id=None,
    price=300_000,
    status=None,
    tier=None,
    score=None,
):
    order = OrderCreate(
        external_id=external_id,
        channel="facebook",
        buyer_name=name,
        buyer_phone=phone,
        address={"raw": "Số 1 đường mẫu, phường mẫu, tỉnh mẫu"},
        items=[{"name": "Sản phẩm mẫu", "quantity": 1, "unit_price_vnd": price}],
        placed_at=T0 + timedelta(minutes=minutes),
    )
    doc = order_document(
        order,
        order_id=order_id,
        shop_id=shop_id,
        phone_key=b"test-key",
        now=T0 + timedelta(minutes=minutes),
    )
    if status:
        doc["status"] = status
    if tier:
        doc["scoring"] = {
            "scored_at": T0 + timedelta(minutes=minutes),
            "probability": score / 100,
            "risk_score": score,
            "tier": tier,
            "expected_loss_vnd": 1000,
            "chosen_by": "tier rule",
            "model_version": "test",
        }
    return doc


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin@gmail.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin12345")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-at-least-32-bytes-long")
    monkeypatch.setenv("ADMIN_SHOP_ID", "shop_a")
    store = FakeStore()
    for doc in (
        make("ord_1", minutes=1, name="Nguyễn Văn An", external_id="FB-1", tier="low", score=10),
        make(
            "ord_2",
            minutes=2,
            name="Trần Thị Bình",
            phone="0900000002",
            price=900_000,
            status="pending_review",
            tier="high",
            score=70,
        ),
        make("ord_3", minutes=3, name="Lê Đức", tier="very_high", score=95),
        make("ord_4", minutes=4, name="Phạm Unscored"),
        make("ord_b", shop_id="shop_b", minutes=5, name="Other shop", tier="high", score=80),
    ):
        store.create(doc)
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/login", json={"username": "admin@gmail.com", "password": "admin12345"}
    ).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def ids(response):
    assert response.status_code == 200, response.text
    return [o["id"] for o in response.json()["items"]]


def test_inbox_needs_a_token(api):
    del api.headers["Authorization"]
    assert api.get("/api/v1/orders").status_code == 401
    assert api.get("/api/v1/orders/ord_1").status_code == 401


def test_inbox_lists_only_the_users_shop_newest_first(api):
    response = api.get("/api/v1/orders")
    assert ids(response) == ["ord_4", "ord_3", "ord_2", "ord_1"]
    body = response.json()
    assert body["total"] == 4
    assert body["next_cursor"] is None
    row = body["items"][2]
    assert row["tier"] == "high"
    assert row["risk_score"] == 70
    assert row["status"] == "pending_review"
    assert row["cod_amount_vnd"] == 900_000
    assert body["items"][0]["tier"] is None


def test_filters_by_status_and_tier(api):
    assert ids(api.get("/api/v1/orders", params={"status": "pending_review"})) == ["ord_2"]
    assert ids(api.get("/api/v1/orders", params=[("tier", "high"), ("tier", "very_high")])) == [
        "ord_3",
        "ord_2",
    ]


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("nguyen", ["ord_1"]),  # without diacritics
        ("ĐỨC", ["ord_3"]),
        ("fb-1", ["ord_1"]),
        ("0900000002", ["ord_2"]),  # local form of +84900000002
        ("+84 900 000 002", ["ord_2"]),
        ("000002", ["ord_2"]),  # part of a phone
        ("zzz", []),
    ],
)
def test_search(api, q, expected):
    assert ids(api.get("/api/v1/orders", params={"q": q})) == expected


def test_sorts(api):
    assert ids(api.get("/api/v1/orders", params={"sort": "placed_at"})) == [
        "ord_1",
        "ord_2",
        "ord_3",
        "ord_4",
    ]
    # Unscored orders go last.
    assert ids(api.get("/api/v1/orders", params={"sort": "-risk_score"})) == [
        "ord_3",
        "ord_2",
        "ord_1",
        "ord_4",
    ]
    assert ids(api.get("/api/v1/orders", params={"sort": "-cod_amount_vnd"}))[0] == "ord_2"


def test_placed_range(api):
    params = {
        "placed_from": (T0 + timedelta(minutes=2)).isoformat(),
        "placed_to": (T0 + timedelta(minutes=3)).isoformat(),
    }
    assert ids(api.get("/api/v1/orders", params=params)) == ["ord_3", "ord_2"]


def test_cursor_pages_through_all_orders(api):
    seen, cursor = [], None
    while True:
        params = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        body = api.get("/api/v1/orders", params=params).json()
        assert body["total"] == 4
        seen += [o["id"] for o in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == ["ord_4", "ord_3", "ord_2", "ord_1"]


@pytest.mark.parametrize("cursor", ["garbage", "MzpmYWtl"])
def test_bad_or_foreign_cursor_is_a_validation_error(api, cursor):
    response = api.get("/api/v1/orders", params={"cursor": cursor})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_cursor_from_another_query_is_rejected(api):
    cursor = api.get("/api/v1/orders", params={"limit": 1}).json()["next_cursor"]
    response = api.get("/api/v1/orders", params={"limit": 1, "cursor": cursor, "tier": "high"})
    assert response.status_code == 422


def test_order_detail(api):
    response = api.get("/api/v1/orders/ord_2")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "ord_2"
    assert body["current_score"]["tier"] == "high"
    assert body["buyer_phone"] == "+84900000002"


@pytest.mark.parametrize("order_id", ["ord_b", "ord_missing"])
def test_other_shops_and_missing_orders_are_not_found(api, order_id):
    response = api.get(f"/api/v1/orders/{order_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
