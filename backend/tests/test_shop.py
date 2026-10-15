"""Shop onboarding (E7.1): the shop profile and its settings per country, used by decisions and
calls."""

from datetime import timedelta

import pytest

from app.api.security import current_user
from app.auth import User
from app.calls.service import CallService
from app.data.shops import ShopStore
from app.risk import engine
from app.schemas.enums import Role
from tests.test_call_automation import body, owner  # noqa: F401 (pytest fixture)
from tests.test_calls import FakeCallStore, FakePublisher, order
from tests.test_intake import api, post  # noqa: F401 (pytest fixture)
from tests.test_lifecycle import scored_fields
from tests.test_pipeline import pipe  # noqa: F401 (pytest fixture)
from tests.test_policy import NOW


def by_country(shop: dict) -> dict:
    return {c["country"]: c for c in shop["countries"]}


def test_a_shop_starts_with_each_countrys_defaults(owner, shop_docs):  # noqa: F811
    shop = owner.get("/api/v1/shop")
    assert shop.status_code == 200, shop.text
    countries = by_country(shop.json())
    assert {c: v["currency"] for c, v in countries.items()} == {
        "VN": "VND",
        "SG": "SGD",
        "PH": "PHP",
    }
    assert countries["SG"]["failed_delivery_cost_vnd"] == 1200  # config/branches.yaml
    assert countries["VN"]["contact_hours"] == {"start": "08:00", "end": "21:00"}
    # The first read creates the shop; it keeps its creation time and stores no settings.
    assert shop_docs["shop_a"]["countries"] == {}
    assert owner.get("/api/v1/shop").json()["created_at"] == shop.json()["created_at"]


def test_the_owner_changes_the_name_and_one_countrys_settings(owner, shop_docs):  # noqa: F811
    change = {
        "name": "Lan Fashion",
        "countries": [
            {
                "country": "SG",
                "failed_delivery_cost_vnd": 1500,
                "contact_hours": {"start": "09:00", "end": "20:00"},
            }
        ],
    }
    saved = owner.patch("/api/v1/shop", json=change)
    assert saved.status_code == 200, saved.text
    countries = by_country(saved.json())
    assert saved.json()["name"] == "Lan Fashion"
    assert countries["SG"]["failed_delivery_cost_vnd"] == 1500
    assert countries["SG"]["ai_call_cost_vnd"] == 30  # unchanged default
    assert countries["VN"]["failed_delivery_cost_vnd"] == 60000
    # Only the change is stored, so a later change to a default still reaches the shop.
    assert shop_docs["shop_a"]["countries"] == {
        "SG": {
            "failed_delivery_cost_vnd": 1500,
            "contact_hours": change["countries"][0]["contact_hours"],
        }
    }
    assert owner.get("/api/v1/shop").json() == saved.json()


@pytest.mark.parametrize(
    "change",
    [
        {"countries": [{"country": "VN", "contact_hours": {"start": "07:00", "end": "21:00"}}]},
        {"countries": [{"country": "VN", "contact_hours": {"start": "20:00", "end": "09:00"}}]},
        {"countries": [{"country": "MY", "failed_delivery_cost_vnd": 1}]},
        {"countries": [{"country": "VN"}, {"country": "VN"}]},
        {"countries": [{"country": "VN", "ai_call_cost_vnd": -1}]},
    ],
)
def test_bad_settings_are_rejected(owner, change):  # noqa: F811
    assert owner.patch("/api/v1/shop", json=change).status_code == 422


def test_only_the_owner_changes_the_settings(owner):  # noqa: F811
    staff = User("usr_2", "staff", "staff@example.com", "Staff", Role.STAFF, "shop_a")
    owner.app.dependency_overrides[current_user] = lambda: staff
    assert owner.get("/api/v1/shop").status_code == 200
    assert owner.patch("/api/v1/shop", json={"name": "Other"}).status_code == 403


def test_saving_the_tiers_keeps_the_call_automation(owner):  # noqa: F811
    owner.put("/api/v1/shop/policy", json=body(mode="suggest"))
    tiers_only = {"tiers": body()["tiers"]}  # what the tier policy form sends
    saved = owner.put("/api/v1/shop/policy", json=tiers_only).json()
    assert saved["version"] == 3 and saved["automation"]["mode"] == "suggest"


# --- decisions and calls use the shop's settings -----------------------------------------------


def scored_with_cost(tier, action):
    fields = scored_fields(tier, action)
    fields["scoring"]["failed_delivery_cost_vnd"] = 60000  # the engine's country default
    return fields


def test_decisions_use_the_shops_costs(api, shop_docs, monkeypatch):  # noqa: F811
    client, store = api
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_with_cost("high", "call"))
    shop_docs["shop_a"] = {"name": "A", "created_at": NOW, "countries": {}}
    shop_docs["shop_a"]["countries"]["VN"] = {"failed_delivery_cost_vnd": 120000}
    doc = store.docs[post(client, "key-a").json()["order_id"]]
    assert doc["scoring"]["failed_delivery_cost_vnd"] == 120000
    assert doc["scoring"]["expected_loss_vnd"] == 72000  # 0.6 x the shop's 120,000
    assert doc["decision"]["expected_loss_vnd"] == 72000


def test_a_call_that_costs_more_than_the_risk_is_not_made(api, shop_docs, monkeypatch):  # noqa: F811
    client, store = api
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_with_cost("high", "call"))
    shop_docs["shop_a"] = {"name": "A", "created_at": NOW, "countries": {}}
    shop_docs["shop_a"]["countries"]["VN"] = {"ai_call_cost_vnd": 50000}  # above 36,000
    doc = store.docs[post(client, "key-a").json()["order_id"]]
    assert doc["decision"]["action"] == "ship_now"
    assert doc["decision"]["block_reasons"] == ["expected_loss_below_cost"]


@pytest.fixture
def shop_calls(pipe, shop_docs, monkeypatch):  # noqa: F811
    monkeypatch.delenv("CALL_TARGET_OVERRIDE", raising=False)
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    hours = {"start": "11:00", "end": "20:00"}
    shop_docs["shop_a"] = {"name": "Lan Fashion", "created_at": NOW, "countries": {}}
    shop_docs["shop_a"]["countries"]["VN"] = {"contact_hours": hours}
    return CallService(
        orders=pipe.store,
        calls=FakeCallStore(),
        log=pipe.log,
        publisher=FakePublisher(),
        shops=ShopStore(None),
    )


def test_calls_keep_to_the_shops_contact_hours(shop_calls):
    assert shop_calls.phone_blocks(order(shop_calls), NOW) == ["outside_contact_hours"]  # 10:00
    assert shop_calls.phone_blocks(order(shop_calls), NOW + timedelta(hours=1)) == []


def test_the_call_names_the_shop(shop_calls, monkeypatch):
    monkeypatch.setenv("CALL_TARGET_OVERRIDE", "sip:6001")
    shop_calls.start_for_shop("ord_test", "shop_a", "admin@gmail.com", NOW)
    assert shop_calls.publisher.jobs[0].shop_name == "Lan Fashion"
