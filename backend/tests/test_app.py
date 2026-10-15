from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())
PROBLEM = "application/problem+json"


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_contract_stub_returns_501_problem() -> None:
    response = client.get("/api/v1/shop")
    assert response.status_code == 501
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == "not_implemented"
    assert "get_shop" in body["detail"]


def test_validation_error_is_problem_json() -> None:
    response = client.post("/api/v1/orders", json={"buyer_phone": "not-a-phone"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == "validation_error"
    assert any(e["loc"] == ["body", "buyer_phone"] for e in body["errors"])


def test_unknown_route_is_problem_json() -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "not_found"
