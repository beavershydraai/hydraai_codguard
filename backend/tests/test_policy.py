"""E4.2 policy engine: the default tier policy, the expected-loss gate and the escalation chain."""

from datetime import datetime, timedelta

import pytest
import yaml

from app.data.orders import VN_TIME
from app.decision import policy
from app.schemas.enums import ContactBlockReason, DecisionAction, RiskTier
from app.schemas.shops import Policy, ShopSettings

A = DecisionAction
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=VN_TIME)


def at(minutes: int) -> datetime:
    return NOW + timedelta(minutes=minutes)


def test_default_policy_is_read_from_the_rules_file():
    p = policy.load_policy()
    assert p.version == 1
    assert [t.tier for t in p.tiers] == list(RiskTier)


def test_default_policy_matches_the_api_example():
    """The Prism mock serves the contract example, so the frontend sees the same defaults."""
    example = Policy.model_config["json_schema_extra"]["examples"][0]["tiers"]
    assert [t.model_dump(mode="json") for t in policy.default_policy().tiers] == example


@pytest.mark.parametrize(
    ("tier", "expected_loss", "action", "next_action", "wait"),
    [
        (RiskTier.LOW, 3_000, A.SHIP_NOW, None, None),
        (RiskTier.MEDIUM, 9_000, A.SEND_CONFIRMATION_LINK, A.AI_CALL, 120),
        (RiskTier.HIGH, 24_600, A.AI_CALL, A.AI_CALL, 30),  # second attempt, 30 minutes later
        (RiskTier.VERY_HIGH, 30_000, A.REQUIRE_DEPOSIT, A.HOLD_FOR_REVIEW, 1440),
    ],
)
def test_default_action_per_tier(tier, expected_loss, action, next_action, wait):
    d = policy.decide(tier, expected_loss, NOW)
    assert d.action == action and d.block_reasons == []
    assert d.next_action == next_action
    assert d.next_action_at == (at(wait) if wait else None)
    assert d.policy_version == 1 and d.expected_loss_vnd == expected_loss


@pytest.mark.parametrize("tier", [RiskTier.MEDIUM, RiskTier.HIGH, RiskTier.VERY_HIGH])
@pytest.mark.parametrize("expected_loss", [0, 30_000])
def test_a_confirmed_order_is_not_contacted_again(tier, expected_loss):
    d = policy.decide(tier, expected_loss, NOW, confirmed=True)
    assert d.action == A.SHIP_NOW
    assert d.block_reasons == [ContactBlockReason.ALREADY_CONFIRMED]
    assert d.contact_cost_vnd is None
    assert d.next_action is None and d.next_action_at is None
    assert d.expected_loss_vnd == expected_loss and d.policy_version == 1


def test_confirmation_does_not_block_a_noncontact_decision():
    d = policy.decide(RiskTier.LOW, 3_000, NOW, confirmed=True)
    assert d.action == A.SHIP_NOW and d.block_reasons == []
    d = policy.decide(RiskTier.HIGH, 30_000, NOW, confirmed=True, action=A.HOLD_FOR_REVIEW)
    assert d.action == A.HOLD_FOR_REVIEW and d.block_reasons == []


@pytest.mark.parametrize("confirmed", [False, True])
def test_hard_rule_actions_are_preserved(confirmed):
    d = policy.decide(RiskTier.LOW, 0, NOW, confirmed=confirmed, action=A.HOLD_FOR_REVIEW)
    assert d.action == A.HOLD_FOR_REVIEW
    assert d.contact_cost_vnd is None and d.next_action is None


@pytest.mark.parametrize("expected_loss", [300, 301])
@pytest.mark.parametrize("tier", [RiskTier.LOW, RiskTier.HIGH])
def test_an_engine_contact_action_obeys_the_contact_cost_gate(tier, expected_loss):
    d = policy.decide(tier, expected_loss, NOW, action=A.SEND_CONFIRMATION_LINK)
    assert d.action == (A.SHIP_NOW if expected_loss == 300 else A.SEND_CONFIRMATION_LINK)
    assert d.block_reasons == (
        [ContactBlockReason.EXPECTED_LOSS_BELOW_COST] if expected_loss == 300 else []
    )


@pytest.mark.parametrize("action", [A.SEND_CONFIRMATION_LINK, A.REQUIRE_DEPOSIT])
def test_a_contact_override_has_a_review_deadline_when_the_tier_has_no_wait(action):
    d = policy.decide(RiskTier.LOW, 30_000, NOW, action=action)
    assert d.action == action
    assert d.next_action == A.HOLD_FOR_REVIEW
    assert d.next_action_at == at(30)


def test_an_engine_contact_action_obeys_confirmation():
    d = policy.decide(RiskTier.LOW, 30_000, NOW, action=A.AI_CALL, confirmed=True)
    assert d.action == A.SHIP_NOW
    assert d.block_reasons == [ContactBlockReason.ALREADY_CONFIRMED]
    assert d.contact_cost_vnd is None and d.next_action is None


def test_the_engine_cannot_cancel_an_order():
    with pytest.raises(ValueError, match="cancels"):
        policy.decide(RiskTier.HIGH, 30_000, NOW, action=A.CANCEL)


@pytest.mark.parametrize(
    ("tier", "unanswered", "call_attempts"),
    [
        (RiskTier.MEDIUM, A.SEND_CONFIRMATION_LINK, 0),
        (RiskTier.HIGH, A.AI_CALL, 1),
        (RiskTier.HIGH, A.AI_CALL, 2),
        (RiskTier.VERY_HIGH, A.REQUIRE_DEPOSIT, 0),
    ],
)
def test_confirmation_stops_pending_escalations(tier, unanswered, call_attempts):
    assert (
        policy.escalate(
            tier,
            30_000,
            at(120),
            unanswered=unanswered,
            call_attempts=call_attempts,
            confirmed=True,
        )
        is None
    )


def test_unconfirmed_orders_still_contact_and_escalate():
    first = policy.decide(RiskTier.HIGH, 30_000, NOW, confirmed=False)
    assert first.action == A.AI_CALL and first.block_reasons == []
    assert first.contact_cost_vnd == 1_500
    next_decision = policy.escalate(
        RiskTier.HIGH,
        30_000,
        at(30),
        unanswered=A.AI_CALL,
        call_attempts=1,
        confirmed=False,
    )
    assert next_decision.action == A.AI_CALL
    assert next_decision.next_action == A.HOLD_FOR_REVIEW


def test_a_saved_escalation_action_is_preserved_after_a_policy_change():
    revised = policy.default_policy().model_copy(deep=True, update={"version": 2})
    d = policy.escalate(
        RiskTier.MEDIUM,
        30_000,
        at(120),
        unanswered=A.SEND_CONFIRMATION_LINK,
        policy=revised,
        action=A.HOLD_FOR_REVIEW,
    )
    assert d.action == A.HOLD_FOR_REVIEW
    assert d.policy_version == 2
    assert d.next_action is None and d.next_action_at is None


@pytest.mark.parametrize("expected_loss", [300, 301])
def test_a_saved_contact_escalation_obeys_the_contact_cost_gate(expected_loss):
    d = policy.escalate(
        RiskTier.HIGH,
        expected_loss,
        at(120),
        unanswered=A.AI_CALL,
        action=A.SEND_CONFIRMATION_LINK,
    )
    assert d.action == (A.SHIP_NOW if expected_loss == 300 else A.SEND_CONFIRMATION_LINK)
    assert d.block_reasons == (
        [ContactBlockReason.EXPECTED_LOSS_BELOW_COST] if expected_loss == 300 else []
    )


def test_confirmation_stops_a_saved_escalation_action():
    assert (
        policy.escalate(
            RiskTier.MEDIUM,
            30_000,
            at(120),
            unanswered=A.SEND_CONFIRMATION_LINK,
            action=A.AI_CALL,
            confirmed=True,
        )
        is None
    )


def test_a_saved_escalation_never_makes_a_third_call():
    d = policy.escalate(
        RiskTier.HIGH,
        30_000,
        at(60),
        unanswered=A.AI_CALL,
        action=A.AI_CALL,
        call_attempts=2,
    )
    assert d.action == A.HOLD_FOR_REVIEW
    assert d.block_reasons == [ContactBlockReason.ATTEMPTS_EXHAUSTED]


def test_a_saved_escalation_cannot_cancel_an_order():
    with pytest.raises(ValueError, match="cancels"):
        policy.escalate(
            RiskTier.HIGH,
            30_000,
            at(120),
            unanswered=A.AI_CALL,
            action=A.CANCEL,
        )


def test_medium_calls_when_the_link_gets_no_response_in_two_hours():
    first = policy.decide(RiskTier.MEDIUM, 9_000, NOW)
    assert first.contact_cost_vnd == 300
    call = policy.escalate(RiskTier.MEDIUM, 9_000, first.next_action_at, unanswered=first.action)
    assert call.action == A.AI_CALL and call.decided_at == at(120)
    assert call.contact_cost_vnd == 1500
    assert call.next_action == A.AI_CALL  # second attempt


def test_high_holds_for_review_after_the_last_call():
    first = policy.decide(RiskTier.HIGH, 24_600, NOW)
    second = policy.escalate(RiskTier.HIGH, 24_600, at(30), unanswered=A.AI_CALL, call_attempts=1)
    assert second.action == A.AI_CALL
    assert (second.next_action, second.next_action_at) == (A.HOLD_FOR_REVIEW, at(60))
    held = policy.escalate(RiskTier.HIGH, 24_600, at(60), unanswered=A.AI_CALL, call_attempts=2)
    assert held.action == A.HOLD_FOR_REVIEW and held.next_action is None
    assert first.action == A.AI_CALL


def test_an_unanswered_escalation_call_ends_in_review():
    d = policy.escalate(RiskTier.MEDIUM, 9_000, at(180), unanswered=A.AI_CALL, call_attempts=2)
    assert d.action == A.HOLD_FOR_REVIEW and d.next_action is None


def test_unpaid_deposit_goes_to_review():
    d = policy.escalate(RiskTier.VERY_HIGH, 30_000, at(1440), unanswered=A.REQUIRE_DEPOSIT)
    assert d.action == A.HOLD_FOR_REVIEW


def test_nothing_follows_a_shipped_order():
    assert policy.escalate(RiskTier.LOW, 3_000, at(60), unanswered=A.SHIP_NOW) is None


@pytest.mark.parametrize(
    ("tier", "expected_loss", "action"),
    [
        (RiskTier.MEDIUM, 300, A.SHIP_NOW),  # equal to the link cost: not higher, so no contact
        (RiskTier.MEDIUM, 301, A.SEND_CONFIRMATION_LINK),
        (RiskTier.HIGH, 1_500, A.SHIP_NOW),
        (RiskTier.HIGH, 1_501, A.AI_CALL),
        (RiskTier.VERY_HIGH, 4_999, A.SHIP_NOW),
        (RiskTier.VERY_HIGH, 5_001, A.REQUIRE_DEPOSIT),
    ],
)
def test_no_contact_when_the_expected_loss_does_not_cover_its_cost(tier, expected_loss, action):
    d = policy.decide(tier, expected_loss, NOW)
    assert d.action == action
    if action == A.SHIP_NOW:
        assert d.block_reasons == [ContactBlockReason.EXPECTED_LOSS_BELOW_COST]
        assert d.contact_cost_vnd is None and d.next_action is None


def test_the_gate_uses_the_shop_costs():
    pricey_calls = ShopSettings(ai_call_cost_vnd=30_000)
    assert policy.decide(RiskTier.HIGH, 24_600, NOW, settings=pricey_calls).action == A.SHIP_NOW


def test_the_gate_also_applies_to_the_escalation():
    first = policy.decide(RiskTier.MEDIUM, 1_000, NOW)  # covers a link (300), not a call (1500)
    assert first.action == A.SEND_CONFIRMATION_LINK
    d = policy.escalate(RiskTier.MEDIUM, 1_000, at(120), unanswered=first.action)
    assert d.action == A.SHIP_NOW
    assert d.block_reasons == [ContactBlockReason.EXPECTED_LOSS_BELOW_COST]


def test_never_a_third_call():
    calls_again = policy.default_policy().model_copy(deep=True)
    policy.tier_rule(calls_again, RiskTier.HIGH).if_no_response = A.AI_CALL
    d = policy.escalate(
        RiskTier.HIGH, 24_600, at(60), unanswered=A.AI_CALL, call_attempts=2, policy=calls_again
    )
    assert d.action == A.HOLD_FOR_REVIEW
    assert d.block_reasons == [ContactBlockReason.ATTEMPTS_EXHAUSTED]


def test_a_shop_policy_applies_with_its_own_version():
    calls_medium = policy.default_policy().model_copy(deep=True, update={"version": 2})
    policy.tier_rule(calls_medium, RiskTier.MEDIUM).action = A.AI_CALL
    d = policy.decide(RiskTier.MEDIUM, 9_000, NOW, policy=calls_medium)
    assert (d.action, d.policy_version) == (A.AI_CALL, 2)


def _rules_file(tmp_path, tiers):
    section = policy.default_policy().model_dump(mode="json") | {"tiers": tiers}
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({"tier_policy": section}), encoding="utf-8")
    return path


def _tiers(**changes):
    tiers = [t.model_dump(mode="json") for t in policy.default_policy().tiers]
    for tier, fields in changes.items():
        next(t for t in tiers if t["tier"] == tier).update(fields)
    return tiers


@pytest.mark.parametrize(
    ("tiers", "message"),
    [
        (_tiers(high={"tier": "medium"}), "each tier once"),
        (_tiers(medium={"no_response_after_minutes": None}), "go together"),
        (_tiers(very_high={"action": "cancel"}), "cancels"),
        (_tiers(low={"if_no_response": "ai_call", "no_response_after_minutes": 60}), "nobody"),
    ],
)
def test_invalid_policies_are_rejected(tmp_path, tiers, message):
    with pytest.raises(ValueError, match=message):
        policy.load_policy(_rules_file(tmp_path, tiers))
