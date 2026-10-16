"""ROI dashboard (E9.2): one country's orders placed in a period, counted from Firestore.

- orders_screened: orders the decision engine decided (seeded history orders were never screened).
- actions: the decision in force on each screened order.
- delivered / delivery_failed: delivery results; failures are buyer-caused only.
- good_orders_contacted_rate: among screened orders that were delivered, the share contacted.
- estimated_savings_vnd: per contacted order, the share of failed deliveries its action prevents
  times the order's expected loss, minus the contact's cost (the shop's cost for the country).

Assumptions to verify (the UI labels the savings "estimated"): PREVENTS in app/risk/backtest.py
is set by hand, not measured.
"""

from datetime import UTC, date, datetime, time

from app.data import branches
from app.data.orders import training_label
from app.data.store import OrderFilters
from app.risk.backtest import PREVENTS
from app.schemas.dashboard import ActionCount, DashboardSummary
from app.schemas.enums import DecisionAction, OrderStatus
from app.schemas.shops import ShopSettings

FIELDS = ("status", "decision.action", "scoring.expected_loss_vnd", "delivery.result")

# Contact action -> (PREVENTS key, cost field of ShopSettings).
CONTACTS = {
    DecisionAction.SEND_CONFIRMATION_LINK: ("link", "confirmation_link_cost_vnd"),
    DecisionAction.AI_CALL: ("call", "ai_call_cost_vnd"),
    DecisionAction.REQUIRE_DEPOSIT: ("deposit", "deposit_request_cost_vnd"),
}


def filters(code: str, start: date, end: date) -> OrderFilters:
    """The country's branches, placed from `start` to `end` inclusive in its local time."""
    tz = branches.country(code).tz
    return OrderFilters(
        branches=tuple(b for b, c in branches.branches().items() if c == code),
        placed_from=datetime.combine(start, time.min, tz).astimezone(UTC),
        placed_to=datetime.combine(end, time.max, tz).astimezone(UTC),
    )


def summarize(
    docs: list[dict], settings: ShopSettings, code: str, start: date, end: date
) -> DashboardSummary:
    actions: dict[str, int] = {}
    screened = delivered = failed = cancelled = good = good_contacted = 0
    savings = 0.0
    for doc in docs:
        action = (doc.get("decision") or {}).get("action")
        result = training_label((doc.get("delivery") or {}).get("result"))
        delivered += result == 0
        failed += result == 1
        cancelled += doc.get("status") == OrderStatus.CANCELLED
        if action is None:
            continue
        screened += 1
        actions[action] = actions.get(action, 0) + 1
        contact = CONTACTS.get(action)
        if result == 0:
            good += 1
            good_contacted += contact is not None
        if contact:
            loss = (doc.get("scoring") or {}).get("expected_loss_vnd") or 0
            savings += PREVENTS[contact[0]] * loss - getattr(settings, contact[1])
    return DashboardSummary(
        period_from=start,
        period_to=end,
        country=code,
        currency=branches.country(code).currency,
        orders_screened=screened,
        actions=[ActionCount(action=a, count=n) for a, n in actions.items()],
        cancelled_before_ship=cancelled,
        delivered=delivered,
        delivery_failed=failed,
        estimated_savings_vnd=round(savings),
        good_orders_contacted_rate=good_contacted / good if good else 0,
    )
