from fastapi.testclient import TestClient

from app.agents.log import get_decision_log
from app.data.store import get_store
from app.main import create_app
from tests.test_intake import FakeDecisionLog, FakeStore

client = TestClient(create_app())
PROBLEM = "application/problem+json"


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_contract_stub_returns_501_problem() -> None:
    response = client.get("/api/v1/dashboard/summary?from=2026-10-01&to=2026-10-15")
    assert response.status_code == 501
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == "not_implemented"
    assert "get_dashboard_summary" in body["detail"]


def test_validation_error_is_problem_json() -> None:
    app = create_app()
    app.dependency_overrides[get_store] = FakeStore
    app.dependency_overrides[get_decision_log] = FakeDecisionLog
    response = TestClient(app).post("/api/v1/intake/orders", json={"buyer_phone": "not-a-phone"})
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
