from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import authenticate, issue_token
from app.main import create_app

PROBLEM = "application/problem+json"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin1234")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret")
    monkeypatch.delenv("ADMIN_SHOP_ID", raising=False)
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    return TestClient(create_app())


def login(client, username="admin", password="admin1234"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_login_returns_a_token_that_opens_me(client):
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"] == {
        "user_id": "usr_admin",
        "email": "admin@codguard.local",
        "display_name": "Admin",
        "role": "owner",
        "shop_id": "shop_demo",
    }
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(hours=11) < expires_at - datetime.now(UTC) <= timedelta(hours=12)

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json() == body["user"]


@pytest.mark.parametrize(
    ("username", "password"),
    [("admin", "wrong"), ("Admin", "admin1234"), ("root", "admin1234"), ("admin", "admin1234 ")],
)
def test_login_rejects_wrong_credentials(client, username, password):
    response = login(client, username, password)
    assert response.status_code == 401
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "unauthorized"
    assert response.json()["detail"] == "Wrong username or password."


def test_login_is_disabled_without_configuration(client, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD")
    response = login(client)
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign-in is not configured on this server."


def test_empty_fields_are_validation_errors(client):
    response = login(client, "", "")
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_me_needs_a_valid_token(client):
    assert client.get("/api/v1/me").status_code == 401
    garbage = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-token"})
    assert garbage.status_code == 401
    assert garbage.json()["detail"] == "The access token is not valid."


def test_me_rejects_a_token_signed_with_another_secret(client, monkeypatch):
    token = login(client).json()["access_token"]
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "rotated-secret")
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_rejects_an_expired_token(client):
    user = authenticate("admin", "admin1234")
    token, _ = issue_token(user, now=datetime.now(UTC) - timedelta(hours=13))
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "The access token has expired. Sign in again."
