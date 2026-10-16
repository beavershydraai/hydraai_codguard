"""Onboarding a new shop: its own sign-in, and its past orders imported from a CSV file."""

import csv
import io
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.data.store import get_store
from app.demo.history_csv import COLUMNS, rows
from app.main import create_app
from tests.test_intake import FakeStore

ACCOUNT = {
    "username": "fashion_store@example.com",
    "password_hash": hash_password("a-test-password"),
    "shop_id": "shop_fashion",
    "name": "Fashion Store",
}


@pytest.fixture
def new_shop(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin@gmail.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin12345")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-at-least-32-bytes-long")
    monkeypatch.setenv("SHOP_ACCOUNTS", json.dumps([ACCOUNT]))
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    store = FakeStore()
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    client.store = store
    return client


def sign_in(client, username="fashion_store@example.com", password="a-test-password"):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if response.status_code == 200:
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return response


def history_file(days=2) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows(days, datetime(2026, 10, 15, tzinfo=UTC), seed=11))
    return out.getvalue().encode()


def upload(client, data: bytes):
    return client.post("/api/v1/shop/history", files={"file": ("history.csv", data, "text/csv")})


def test_a_shop_account_signs_in_to_its_own_shop(new_shop):
    response = sign_in(new_shop)
    assert response.status_code == 200
    assert response.json()["user"]["shop_id"] == "shop_fashion"
    assert new_shop.get("/api/v1/me").json()["shop_id"] == "shop_fashion"
    assert sign_in(new_shop, password="wrong").status_code == 401
    assert sign_in(new_shop, "admin@gmail.com", "admin12345").json()["user"]["shop_id"] == (
        "shop_demo"
    )


def test_the_password_is_never_stored():
    stored = hash_password("a-test-password")
    assert "a-test-password" not in stored and stored.startswith("pbkdf2_sha256$")
    assert hash_password("a-test-password") != stored  # a new salt each time


def test_the_exported_history_imports_without_rejected_rows(new_shop):
    sign_in(new_shop)
    data = history_file()
    response = upload(new_shop, data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rejected_count"] == 0 and body["imported"] == body["received"] > 0
    assert {c["country"] for c in body["countries"]} == {"VN", "SG", "PH"}
    docs = list(new_shop.store.docs.values())
    assert all(d["shop_id"] == "shop_fashion" and d["scoring"] is None for d in docs)
    assert all(d["status"] in {"delivered", "delivery_failed", "cancelled"} for d in docs)
    # The same file again replaces the same orders.
    assert upload(new_shop, data).json()["imported"] == body["imported"]
    assert len(new_shop.store.docs) == body["imported"]


def test_bad_rows_are_reported_and_the_rest_imported(new_shop):
    sign_in(new_shop)
    lines = history_file(days=1).decode().splitlines()
    header = lines[0].split(",")
    cells = next(csv.reader([lines[1]]))
    bad = dict(zip(header, cells, strict=True)) | {"delivery_result": "lost"}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=header)
    writer.writeheader()
    writer.writerow(bad)
    for line in lines[2:4]:
        out.write(line + "\r\n")
    body = upload(new_shop, out.getvalue().encode()).json()
    assert body["rejected"][0]["field"] == "delivery_result" and body["imported"] == 2


def test_a_file_without_the_history_columns_is_refused(new_shop):
    sign_in(new_shop)
    data = (
        b"buyer_name,buyer_phone,address,item_name,quantity,unit_price_vnd\nA,0000000001,x,y,1,1\n"
    )
    assert upload(new_shop, data).status_code == 400
