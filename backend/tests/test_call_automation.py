"""Call automation: which AI calls the agent places by itself and which it only suggests to the
shop, the policy routes that store it, and the shop confirming a suggested call."""

import dataclasses
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.security import current_user
from app.auth import User
from app.data.orders import order_document
from app.decision import policy
from app.main import create_app
from app.risk import engine
from app.schemas.enums import ContactBlockReason, DecisionAction, RiskTier, Role
from app.schemas.orders import OrderCreate
from app.schemas.shops import CallAutomation, CallWindow, CodRange, Policy
from tests.test_calls import calls, order  # noqa: F401 (pytest fixture)
from tests.test_intake import api, post  # noqa: F401 (pytest fixture)
from tests.test_lifecycle import scored_fields
from tests.test_pipeline import pipe, run  # noqa: F401 (pytest fixture)
from tests.test_policy import NOW, at

A, B = DecisionAction, ContactBlockReason
EXAMPLE = OrderCreate.model_config["json_schema_extra"]["examples"][0]


def scored(branch_id=None, risk_score=60, **changes) -> dict:
    """A scored order: COD 330,000 VND, Facebook, branch_VN_HCM unless told otherwise. NOW is a
    Wednesday, 10:00 in Vietnam."""
    doc = order_document(
        OrderCreate.model_validate(EXAMPLE | changes),
        order_id="ord_x",
        shop_id="shop_a",
        phone_key=b"test-key",
        now=NOW,
        branch_id=branch_id,
    )
    doc.update(scored_fields("high", "call"))
    doc["scoring"]["risk_score"] = risk_score
    return doc


def automated(**fields) -> Policy:
    return policy.default_policy().model_copy(update={"automation": CallAutomation(**fields)})


def decide(p: Policy, doc: dict, tier=RiskTier.HIGH, loss=36_000):
    return policy.decide(tier, loss, NOW, policy=p, order=doc)


# --- which calls the agent places by itself ------------------------------------------------


def test_the_default_automation_places_every_call_the_engine_picks():
    d = decide(policy.default_policy(), scored())
    assert d.action == A.AI_CALL and d.block_reasons == [] and d.suggested_action is None
    assert d.next_action == A.AI_CALL and d.next_action_at == at(30)


def test_suggest_mode_leaves_every_call_to_the_shop():
    d = decide(automated(mode="suggest"), scored())
    assert d.action == A.HOLD_FOR_REVIEW and d.suggested_action == A.AI_CALL
    assert d.block_reasons == [B.MANUAL_APPROVAL]
    assert d.contact_cost_vnd is None and d.next_action is None


@pytest.mark.parametrize(
    ("rules", "reason"),
    [
        ({"min_tier": "very_high"}, B.BELOW_AUTO_CALL_TIER),
        ({"cod_ranges": [{"currency": "VND", "max_cod": 300_000}]}, B.COD_OUT_OF_RANGE),
        ({"cod_ranges": [{"currency": "VND", "min_cod": 500_000}]}, B.COD_OUT_OF_RANGE),
        ({"channels": ["tiktok", "website"]}, B.CHANNEL_NOT_AUTOMATED),
        ({"call_window": {"start": "11:00", "end": "20:00"}}, B.OUTSIDE_CALL_WINDOW),
        ({"call_window": {"days": ["sat", "sun"]}}, B.OUTSIDE_CALL_WINDOW),
    ],
)
def test_a_call_outside_the_rules_is_only_suggested(rules, reason):
    d = decide(automated(**rules), scored())
    assert d.action == A.HOLD_FOR_REVIEW and d.suggested_action == A.AI_CALL
    assert d.block_reasons == [reason]


def test_a_call_inside_every_rule_is_placed():
    rules = automated(
        min_tier="high",
        cod_ranges=[{"currency": "VND", "min_cod": 330_000, "max_cod": 330_000}],
        channels=["facebook"],
        call_window={"start": "10:00", "end": "10:01", "days": ["wed"]},
    )
    assert decide(rules, scored()).action == A.AI_CALL


def test_a_range_in_another_currency_does_not_limit_the_order():
    rules = automated(cod_ranges=[{"currency": "SGD", "max_cod": 1}])
    assert decide(rules, scored()).action == A.AI_CALL


def test_the_call_window_is_the_branchs_local_time():
    rules = automated(call_window={"start": "10:30", "end": "21:00"})  # NOW: 10:00 VN, 11:00 SG
    assert decide(rules, scored()).block_reasons == [B.OUTSIDE_CALL_WINDOW]
    singapore = scored(branch_id="branch_SG", currency="SGD")
    assert decide(rules, singapore).action == A.AI_CALL


def test_without_the_order_nothing_blocks():
    """A bare policy check (no order) keeps the tier policy, as before automation existed."""
    d = policy.decide(RiskTier.HIGH, 36_000, NOW, policy=automated(mode="suggest"))
    assert d.action == A.AI_CALL


# --- the lowest tier the agent calls by itself --------------------------------------------


def test_auto_calls_start_at_the_shops_tier():
    rules = automated(min_tier="high")
    assert decide(rules, scored()).action == A.AI_CALL
    model_call = policy.decide(
        RiskTier.VERY_HIGH, 36_000, NOW, policy=rules, order=scored(), action=A.AI_CALL
    )
    assert model_call.action == A.AI_CALL  # a call the model picked for Very High
    escalated = policy.escalate(
        RiskTier.MEDIUM,
        36_000,
        at(120),
        unanswered=A.SEND_CONFIRMATION_LINK,
        policy=rules,
        order=scored(),
    )
    assert escalated.action == A.HOLD_FOR_REVIEW and escalated.suggested_action == A.AI_CALL
    assert escalated.block_reasons == [B.BELOW_AUTO_CALL_TIER]


def test_the_tier_rule_still_picks_the_action():
    """Automation only holds calls back: it never turns a link or a deposit into a call."""
    rules = automated(min_tier="medium")
    assert decide(rules, scored(), tier=RiskTier.MEDIUM).action == A.SEND_CONFIRMATION_LINK
    assert decide(rules, scored(), tier=RiskTier.VERY_HIGH).action == A.REQUIRE_DEPOSIT


# --- follow-ups --------------------------------------------------------------------------


def test_an_unanswered_link_escalates_to_a_suggested_call():
    d = policy.escalate(
        RiskTier.MEDIUM,
        36_000,
        at(120),
        unanswered=A.SEND_CONFIRMATION_LINK,
        policy=automated(mode="suggest"),
        order=scored(),
    )
    assert d.action == A.HOLD_FOR_REVIEW and d.suggested_action == A.AI_CALL


def test_the_shop_sets_the_attempts_and_the_gap_between_calls():
    one = decide(automated(max_attempts=1), scored())
    assert one.next_action == A.HOLD_FOR_REVIEW and one.next_action_at == at(30)
    after_one = policy.escalate(
        RiskTier.HIGH,
        36_000,
        at(30),
        unanswered=A.AI_CALL,
        call_attempts=1,
        policy=automated(max_attempts=1),
        order=scored(),
    )
    assert after_one.action == A.HOLD_FOR_REVIEW
    slow = decide(automated(retry_after_minutes=90), scored())
    assert slow.next_action == A.AI_CALL and slow.next_action_at == at(90)


@pytest.mark.parametrize(
    "build",
    [
        lambda: CallWindow(start="07:00"),  # contact hours start at 08:00
        lambda: CallWindow(end="21:30"),
        lambda: CallWindow(start="12:00", end="12:00"),
        lambda: CallWindow(days=[]),
        lambda: CodRange(currency="VND", min_cod=2, max_cod=1),
        lambda: CallAutomation(cod_ranges=[{"currency": "VND"}, {"currency": "VND"}]),
        lambda: CallAutomation(max_attempts=3),  # contact protection: 2 calls per order
        lambda: CallAutomation(retry_after_minutes=10),  # at least 30 minutes apart
        lambda: CallAutomation(min_tier="extreme"),
    ],
)
def test_rules_that_break_contact_protection_are_rejected(build):
    with pytest.raises(ValidationError):
        build()


# --- the policy routes -------------------------------------------------------------------


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin@gmail.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin12345")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-at-least-32-bytes-long")
    monkeypatch.setenv("ADMIN_SHOP_ID", "shop_a")
    client = TestClient(create_app())
    token = client.post(
        "/api/v1/auth/login", json={"username": "admin@gmail.com", "password": "admin12345"}
    ).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def body(**automation) -> dict:
    tiers = [t.model_dump(mode="json") for t in policy.default_policy().tiers]
    return {"tiers": tiers, "automation": automation}


def test_a_shop_starts_with_the_default_policy(owner):
    got = owner.get("/api/v1/shop/policy")
    assert got.status_code == 200, got.text
    assert got.json()["version"] == 1
    assert got.json()["automation"] == CallAutomation().model_dump(mode="json")


def test_the_owner_saves_a_new_version(owner, policy_versions):
    rules = {"mode": "suggest", "min_tier": "high", "channels": ["facebook"]}
    saved = owner.put("/api/v1/shop/policy", json=body(**rules))
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 2 and saved.json()["updated_by"] == "admin@gmail.com"
    assert owner.get("/api/v1/shop/policy").json() == saved.json()
    versions = owner.get("/api/v1/shop/policy/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert policy_versions["shop_a"][0].automation.mode == "suggest"


@pytest.mark.parametrize(
    "bad",
    [
        body(min_tier="extreme"),
        body(call_window={"start": "06:00", "end": "22:00"}),
        {"tiers": [t | {"action": "cancel"} for t in body()["tiers"]]},
    ],
)
def test_a_bad_policy_is_rejected(owner, bad):
    response = owner.put("/api/v1/shop/policy", json=bad)
    assert response.status_code == 422, response.text


def test_only_the_owner_changes_the_policy(owner):
    """Sign-in has one owner account until E7.1 adds staff, so the staff user is injected."""
    staff = User("usr_2", "staff", "staff@example.com", "Staff", Role.STAFF, "shop_a")
    owner.app.dependency_overrides[current_user] = lambda: staff
    assert owner.get("/api/v1/shop/policy").status_code == 200
    assert owner.put("/api/v1/shop/policy", json=body()).status_code == 403


# --- the shop's policy runs at intake, and the shop confirms the suggestion -------------------


def test_intake_decides_with_the_shops_policy(api, policy_versions, monkeypatch):  # noqa: F811
    client, store = api
    policy_versions["shop_a"] = [automated(mode="suggest").model_copy(update={"version": 2})]
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    accepted = post(client, "key-a").json()
    assert accepted["status"] == "pending_review"
    decision = store.docs[accepted["order_id"]]["decision"]
    assert decision["suggested_action"] == A.AI_CALL and decision["policy_version"] == 2


async def test_the_shop_confirms_a_suggested_call(pipe, calls):  # noqa: F811
    await run(dataclasses.replace(pipe, policy=automated(mode="suggest")))
    held = order(calls)
    assert held["status"] == "pending_review" and calls.publisher.jobs == []

    call = calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    assert call.status.value == "queued" and len(calls.publisher.jobs) == 1
    doc = order(calls)
    assert doc["status"] == "awaiting_confirmation"
    assert doc["decision"]["action"] == A.AI_CALL and doc["decision"]["decided_by"] == "staff"
    confirmed = next(e for e in doc["timeline"] if e["type"] == "override")
    assert confirmed["actor"] == "admin@gmail.com"
    assert confirmed["message_vi"] == "Shop confirmed the suggested AI call."
    assert doc["decision"]["next_action_at"] == NOW + timedelta(minutes=30)
