"""GET /dashboard/summary: one country's orders in a period, counted (app/decision/dashboard.py)."""

from datetime import date

from app.data import branches
from app.data.store import get_store
from app.decision import dashboard
from tests.test_orders_api import api, make  # noqa: F401  (api is a fixture)

VN = branches.country("VN").settings  # link 300, call 1500, deposit 5000


def doc(action=None, result=None, status="shipped", loss=10_000):
    return {
        "status": status,
        "decision": {"action": action} if action else None,
        "scoring": {"expected_loss_vnd": loss} if action else None,
        "delivery": {"result": result} if result else None,
    }


def test_summary_counts_and_estimates_savings():
    docs = [
        doc("ship_now", "delivered"),
        doc("send_confirmation_link", "delivered"),  # a good order contacted
        doc("ai_call", "refused"),
        doc("require_deposit", status="cancelled"),
        doc(None, "delivered"),  # seeded history: never screened
        doc(None, "carrier_issue"),  # not the buyer's fault: not a failure
    ]
    s = dashboard.summarize(docs, VN, "VN", date(2026, 10, 1), date(2026, 10, 7))
    assert s.orders_screened == 4
    assert {a.action: a.count for a in s.actions} == {
        "ship_now": 1,
        "send_confirmation_link": 1,
        "ai_call": 1,
        "require_deposit": 1,
    }
    assert (s.delivered, s.delivery_failed, s.cancelled_before_ship) == (3, 1, 1)
    assert s.good_orders_contacted_rate == 0.5
    # 0.4*10000-300 + 0.6*10000-1500 + 0.85*10000-5000
    assert s.estimated_savings_vnd == 3700 + 4500 + 3500
    assert s.currency == "VND"


def test_an_order_counts_as_the_contact_it_got_not_where_it_ended():
    # A link went unanswered, the AI call too: the order now waits for review.
    escalated = doc("hold_for_review") | {"intervention": {"contact_action": "link"}}
    s = dashboard.summarize([escalated], VN, "VN", date(2026, 10, 1), date(2026, 10, 7))
    assert [(a.action, a.count) for a in s.actions] == [("send_confirmation_link", 1)]
    assert s.estimated_savings_vnd == 3700  # 0.4*10000-300


def test_period_is_local_days_of_the_country():
    f = dashboard.filters("VN", date(2026, 10, 1), date(2026, 10, 1))
    assert f.placed_from.isoformat() == "2026-09-30T17:00:00+00:00"
    assert f.placed_to.isoformat().startswith("2026-10-01T16:59:59")
    assert all(branches.branches()[b] == "VN" for b in f.branches)


def test_api_counts_only_the_shops_orders_of_the_country(api):  # noqa: F811
    store = api.app.dependency_overrides[get_store]()
    for order_id in ("ord_1", "ord_3", "ord_b"):  # VN, SG, another shop's VN order
        store.update(order_id, {"decision": {"action": "ship_now"}, "status": "delivered"})
        store.update(order_id, {"delivery": {"result": "delivered"}})
    r = api.get("/api/v1/dashboard/summary", params={"from": "2026-10-13", "to": "2026-10-13"})
    assert r.status_code == 200, r.text
    assert (r.json()["orders_screened"], r.json()["delivered"]) == (1, 1)
    assert r.json()["currency"] == "VND"
    sg = api.get(
        "/api/v1/dashboard/summary",
        params={"from": "2026-10-13", "to": "2026-10-13", "country": "SG"},
    )
    assert sg.json()["currency"] == "SGD"
    bad = api.get("/api/v1/dashboard/summary", params={"from": "2026-10-13", "to": "2026-10-01"})
    assert bad.status_code == 422
