"""Model health for the shop owner and the Update model button (app/risk/health.py)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.security import current_user
from app.auth import User
from app.main import create_app
from app.risk import artifacts, health
from app.schemas.enums import Role

NOW = datetime(2026, 10, 16, 8, tzinfo=UTC)


@pytest.fixture
def models(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))

    def put(code, path, data):
        artifacts.write(path, json.dumps(data).encode(), code)

    started, marker = [], {}
    monkeypatch.setattr(health, "start_training", lambda: started.append(True))
    monkeypatch.setattr(health, "requested_at", lambda: marker.get("at"))
    monkeypatch.setattr(health, "mark_requested", lambda now: marker.update(at=now))
    return put, started


def metrics(rows=8000):
    return {"version": "v20261015173450", "rows": rows, "candidate": {"lift_top20": 3.33}}


def test_a_country_without_a_model(models):
    assert health.country_health("SG", NOW).status == "no_model"


def test_up_to_date_and_the_three_reasons_to_update(models):
    put, _ = models
    put("VN", "latest/metrics.json", metrics())
    put("VN", "latest/monitor.json", {"new_outcomes": 300, "checked_at": NOW.isoformat()})
    ok = health.country_health("VN", NOW)
    assert ok.status == "up_to_date" and ok.lift_top20 == 3.33 and ok.training_orders == 8000
    assert ok.trained_at == datetime(2026, 10, 15, 17, 34, 50, tzinfo=UTC)
    put(
        "VN",
        "latest/monitor.json",
        {"new_outcomes": 2000, "drift": {"alert": True}, "performance": {"degraded": True}},
    )
    stale = health.country_health("VN", NOW)
    assert stale.status == "update_recommended" and len(stale.reasons) == 3
    assert "2,000 orders got a delivery result" in stale.reasons[2]


def test_an_update_starts_once_and_shows_as_running(models):
    put, started = models
    for code in ("VN", "SG", "PH"):
        put(code, "latest/metrics.json", metrics())
    assert all(h.updating for h in health.request_update(NOW))
    with pytest.raises(health.UpdateRunning):
        health.request_update(NOW + timedelta(minutes=5))
    assert started == [True]
    later = NOW + timedelta(hours=1)
    assert not health.country_health("VN", later, health.requested_at()).updating  # gave up


def test_only_the_owner_updates_the_model(models, monkeypatch):
    app = create_app()
    staff = User("u2", "staff", "staff@example.com", "Staff", Role.STAFF, "shop_a")
    app.dependency_overrides[current_user] = lambda: staff
    client = TestClient(app)
    assert client.get("/api/v1/dashboard/model-health").status_code == 200
    assert client.post("/api/v1/dashboard/model-health/update").status_code == 403
