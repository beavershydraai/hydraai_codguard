"""Automation off (the default): every contact the engine picks waits for the shop, which accepts
it; and the no-response timers that Cloud Scheduler fires (app/decision/timers.py)."""

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.agents.log import get_decision_log
from app.data.policies import get_policy_store
from app.data.shops import get_shop_store
from app.data.store import get_store
from app.decision import timers
from app.main import create_app
from app.risk import engine
from tests.test_pipeline import pipe, run, scorer  # noqa: F401 (pytest fixture)

pytestmark = pytest.mark.default_automation


@pytest.fixture
def shop(pipe, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ADMIN_USERNAME", "admin@gmail.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin12345")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-at-least-32-bytes-long")
    monkeypatch.setenv("ADMIN_SHOP_ID", "shop_a")
    monkeypatch.delenv("CALL_JOBS_TOPIC", raising=False)
    app = create_app()
    app.dependency_overrides[get_store] = lambda: pipe.store
    app.dependency_overrides[get_decision_log] = lambda: pipe.log
    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/login", json={"username": "admin@gmail.com", "password": "admin12345"}
    ).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def accept(client):
    return client.post("/api/v1/orders/ord_test/suggestion/accept")


@pytest.mark.parametrize(
    "tier,action,status",
    [
        ("medium", "send_confirmation_link", "awaiting_confirmation"),
        ("high", "ai_call", "awaiting_confirmation"),
        ("very_high", "require_deposit", "awaiting_deposit"),
    ],
)
async def test_the_shop_accepts_the_suggested_contact(
    pipe,  # noqa: F811
    shop,
    monkeypatch,
    tier,
    action,
    status,
):
    monkeypatch.setattr(engine, "score", scorer(tier, action.split("_")[-1]))
    await run(pipe)
    held = pipe.store.get("ord_test")
    assert held["status"] == "pending_review" and held["decision"]["suggested_action"] == action
    assert pipe.log.claims == {}  # nothing reached the buyer

    accepted = accept(shop)
    assert accepted.status_code == 200, accepted.text
    doc = pipe.store.get("ord_test")
    assert doc["status"] == status and doc["decision"]["action"] == action
    assert doc["decision"]["decided_by"] == "staff"
    assert doc["timeline"][0]["actor"] == "admin@gmail.com"
    assert len(pipe.log.claims) == 1  # sent once (simulated)
    assert accept(shop).status_code == 409  # nothing left to accept


async def test_a_due_timer_moves_an_unanswered_link_on(pipe, shop, monkeypatch):  # noqa: F811
    monkeypatch.setattr(engine, "score", scorer("medium", "link"))
    await run(pipe)
    accept(shop)
    due_at = pipe.store.get("ord_test")["decision"]["next_action_at"]
    args = (pipe.store, pipe.log, get_shop_store(), get_policy_store())

    async def run_due(now):  # in a worker thread, like the sync endpoint
        return await asyncio.to_thread(timers.run_due, *args, now)

    assert await run_due(due_at - timedelta(minutes=1)) == 0
    assert pipe.store.get("ord_test")["status"] == "awaiting_confirmation"

    assert await run_due(due_at) == 1
    doc = pipe.store.get("ord_test")
    # The link went unanswered: the policy's AI call follows, suggested since automation is off.
    assert doc["status"] == "pending_review" and doc["decision"]["suggested_action"] == "ai_call"
    assert await run_due(due_at + timedelta(hours=1)) == 0  # nothing waits any more


def test_the_timer_endpoint_needs_the_scheduler_identity(shop, monkeypatch):
    monkeypatch.delenv("INTERNAL_AUTH", raising=False)
    del shop.headers["Authorization"]
    assert shop.post("/api/v1/internal/timers/run").status_code == 401
