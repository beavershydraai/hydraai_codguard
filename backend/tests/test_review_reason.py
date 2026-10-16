"""Why an order waits in Pending review, as the shop sees it (app/decision/views.py)."""

import pytest

from app.decision.views import contact_summary, review_reason

HELD = {"status": "pending_review", "decision": {"action": "hold_for_review"}}


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"decision": {"suggested_action": "ai_call"}}, "suggested"),
        ({"decision": {"action": "hold_for_review", "decided_by": "staff"}}, "staff"),
        ({"scoring": {"chosen_by": "hard rule: invalid phone"}}, "invalid_phone"),
        ({"decision": {"block_reasons": ["attempts_exhausted"]}}, "attempts_used"),
        ({"calls": [{"outcome": "unclear"}], "attempts": {"ai_call": 1}}, "call_unclear"),
        ({"calls": [{"outcome": "wrong_person"}]}, "wrong_person"),
        ({"calls": [{"outcome": "edited"}], "attempts": {"ai_call": 1}}, "items_changed"),
        ({"calls": [{"outcome": "no_answer"}], "attempts": {"ai_call": 2}}, "no_answer_call"),
        (
            {"attempts": {"ai_call": 1}, "intervention": {"contact_action": "link"}},
            "no_answer_call",
        ),
        ({"intervention": {"contact_action": "link"}}, "no_answer_link"),
        ({"intervention": {"contact_action": "deposit"}}, "deposit_unpaid"),
        ({}, "other"),
    ],
)
def test_the_review_reason_comes_from_what_is_stored(changes, reason):
    assert review_reason(HELD | changes) == reason


def test_only_orders_in_review_have_a_review_reason():
    assert review_reason(HELD | {"status": "awaiting_confirmation"}) is None


def test_the_contact_summary_is_the_latest_call_that_has_one():
    calls = [{"summary_vi": "First call."}, {"summary_vi": "Second call."}, {"outcome": None}]
    assert contact_summary({"calls": calls}) == "Second call."
    assert contact_summary({}) is None


def test_a_random_test_order_is_flagged_for_the_shop():
    from app.decision.views import _review_fields

    assert _review_fields({"random_slice": True})["random_test"] is True
    assert _review_fields({})["random_test"] is False
