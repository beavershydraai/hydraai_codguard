"""GET /orders (inbox) and GET /orders/{id}, scoped to the signed-in user's shop."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.data.backfill_orders import changes
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
    name="Demo buyer",
    phone="+84000000001",
    external_id=None,
    price=300_000,
    status=None,
    tier=None,
    score=None,
    branch_id=None,
):
    order = OrderCreate(
        external_id=external_id,
        channel="facebook",
        buyer_name=name,
        buyer_phone=phone,
        address={"raw": "Số 1 đường mẫu, phường mẫu, tỉnh mẫu"},
        items=[{"name": "Sample product", "quantity": 1, "unit_price_vnd": price}],
        placed_at=T0 + timedelta(minutes=minutes),
    )
    doc = order_document(
        order,
        order_id=order_id,
        shop_id=shop_id,
        phone_key=b"test-key",
        now=T0 + timedelta(minutes=minutes),
        branch_id=branch_id,
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
            # A full run also has these: the inbox never reads them (it reads a projection).
            "features": {"phone_orders_24h": 1},
            "shap": {"available": True},
        }
        doc["tier"], doc["risk_score"] = tier, score
    return doc


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin@gmail.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin12345")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-at-least-32-bytes-long")
    monkeypatch.setenv("ADMIN_SHOP_ID", "shop_a")
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    store = FakeStore()
    for doc in (
        make("ord_1", minutes=1, name="Nguyễn Văn An", external_id="FB-1", tier="low", score=10),
        make(
            "ord_2",
            minutes=2,
            name="Trần Thị Bình",
            phone="0000000002",
            price=900_000,
            status="pending_review",
            tier="high",
            score=70,
        ),
        make("ord_3", minutes=3, name="Lê Đức", tier="very_high", score=95, branch_id="branch_SG"),
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
        ("ord_3", ["ord_3"]),  # order ID
        ("FB-1", ["ord_1"]),  # the shop's order ID
        ("0000000002", ["ord_2"]),  # full phone, local form of +84000000002
        ("+84 000 000 002", ["ord_2"]),
        ("000002", []),  # part of a phone: phones are stored encrypted, matched by hash
        ("Nguyễn Văn An", []),  # no text search in Firestore
        ("ord_b", []),  # another shop's order
    ],
)
def test_search_finds_exact_values(api, q, expected):
    assert ids(api.get("/api/v1/orders", params={"q": q})) == expected


def test_search_keeps_the_other_filters(api):
    params = {"q": "0000000002", "status": "new"}
    assert ids(api.get("/api/v1/orders", params=params)) == []


def test_filters_by_branch(api):
    assert ids(api.get("/api/v1/orders", params={"branch": "branch_SG"})) == ["ord_3"]
    both = [("branch", "branch_SG"), ("branch", "branch_VN_HCM")]
    assert ids(api.get("/api/v1/orders", params=both)) == ["ord_4", "ord_3", "ord_2", "ord_1"]


@pytest.mark.parametrize(
    "params",
    [
        {"branch": "branch_XX"},
        [("status", s) for s in ("new", "pending_review", "shipped", "delivered")]
        + [("tier", t) for t in ("low", "medium", "high")]
        + [("branch", b) for b in ("branch_SG", "branch_PH", "branch_VN_HN")],  # 36 > 30
        {"placed_from": T0.isoformat(), "sort": "-risk_score"},
    ],
)
def test_queries_firestore_cannot_serve_are_rejected(api, params):
    response = api.get("/api/v1/orders", params=params)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


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


@pytest.mark.parametrize("cursor", ["garbage", "MzpmYWtl", "eyJhZnRlciI6ICJvcmRfMSJ9"])
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
    assert body["buyer_phone"] == "+84000000002"


@pytest.mark.parametrize("order_id", ["ord_b", "ord_missing"])
def test_other_shops_and_missing_orders_are_not_found(api, order_id):
    response = api.get(f"/api/v1/orders/{order_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_sort_fields_are_stored_at_the_top_level():
    doc = make("ord_x", price=200_000)
    assert doc["cod_amount_vnd"] == 200_000 and doc["risk_score"] is None


def test_the_backfill_adds_only_missing_sort_fields():
    old = make("ord_y", price=150_000, tier="high", score=40)
    del old["cod_amount_vnd"], old["risk_score"]
    assert changes(old) == {"cod_amount_vnd": 150_000, "risk_score": 40}
    unscored = make("ord_z")
    del unscored["risk_score"]
    assert changes(unscored) == {"risk_score": None}
    assert changes(make("ord_w")) == {}
