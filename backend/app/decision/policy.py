"""Tier policy (E4.2): the action for each risk tier, the expected-loss gate, and what follows
when the buyer does not respond.

The default policy is the `tier_policy` section of config/cod_guard_rules_apac.yaml, validated
with the API's Policy model. Contact protection beyond the call attempt limit (contact hours,
one call per phone per day, batching) is E4.3.
"""

from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from app.schemas.enums import ContactBlockReason, DecisionAction, RiskTier
from app.schemas.scoring import Decision
from app.schemas.shops import Policy, ShopSettings, TierPolicy

RULES_FILE = Path(__file__).resolve().parents[2] / "config" / "cod_guard_rules_apac.yaml"
MAX_CALL_ATTEMPTS = 2
CALL_RETRY_GAP_MINUTES = 30
CONTACT_COST_FIELD = {  # the ShopSettings field that prices each way of contacting the buyer
    DecisionAction.SEND_CONFIRMATION_LINK: "confirmation_link_cost_vnd",
    DecisionAction.AI_CALL: "ai_call_cost_vnd",
    DecisionAction.REQUIRE_DEPOSIT: "deposit_request_cost_vnd",
}


def check(policy: Policy) -> Policy:
    """Each tier once; an escalation only after a contact, always with its wait; never cancel."""
    tiers = [t.tier for t in policy.tiers]
    if sorted(tiers) != sorted(RiskTier):
        raise ValueError(f"the policy must list each tier once, got {tiers}")
    for t in policy.tiers:
        if DecisionAction.CANCEL in (t.action, t.if_no_response):
            raise ValueError(f"{t.tier}: only the buyer or the shop cancels an order")
        if (t.if_no_response is None) != (t.no_response_after_minutes is None):
            raise ValueError(f"{t.tier}: if_no_response and no_response_after_minutes go together")
        if t.if_no_response and t.action not in CONTACT_COST_FIELD:
            raise ValueError(f"{t.tier}: {t.action} contacts nobody, so nothing can follow it")
    return policy


def load_policy(path: Path = RULES_FILE) -> Policy:
    section = yaml.safe_load(path.read_text(encoding="utf-8"))["tier_policy"]
    return check(Policy.model_validate(section))


@lru_cache
def default_policy() -> Policy:
    return load_policy()


def tier_rule(policy: Policy, tier: RiskTier) -> TierPolicy:
    return next(t for t in policy.tiers if t.tier == tier)


def contact_cost(action: DecisionAction, settings: ShopSettings) -> int | None:
    """Cost of one contact of this kind; None for actions that contact nobody."""
    field = CONTACT_COST_FIELD.get(action)
    return getattr(settings, field) if field else None


def follow_up(
    rule: TierPolicy, action: DecisionAction, calls_made: int
) -> tuple[DecisionAction | None, int | None]:
    """What to do, and after how many minutes, if the buyer does not respond to `action`."""
    if action == DecisionAction.AI_CALL and calls_made < MAX_CALL_ATTEMPTS:
        return DecisionAction.AI_CALL, CALL_RETRY_GAP_MINUTES
    if action == rule.action:
        return rule.if_no_response, rule.no_response_after_minutes
    if action in CONTACT_COST_FIELD:  # the escalation went unanswered too: a person decides
        wait = (
            CALL_RETRY_GAP_MINUTES
            if action == DecisionAction.AI_CALL
            else rule.no_response_after_minutes
        )
        return DecisionAction.HOLD_FOR_REVIEW, wait
    return None, None


def decide(
    tier: RiskTier,
    expected_loss_vnd: int,
    now: datetime,
    *,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
) -> Decision:
    """The first decision for a scored order."""
    policy = policy or default_policy()
    action = tier_rule(policy, tier).action
    return _decision(action, tier, expected_loss_vnd, now, 0, settings or ShopSettings(), policy)


def escalate(
    tier: RiskTier,
    expected_loss_vnd: int,
    now: datetime,
    *,
    unanswered: DecisionAction,
    call_attempts: int = 0,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
) -> Decision | None:
    """The decision when the buyer did not respond to `unanswered` in time, or None when nothing
    follows. `call_attempts` counts the AI calls already made for this order."""
    policy = policy or default_policy()
    action, _ = follow_up(tier_rule(policy, tier), unanswered, call_attempts)
    if action is None:
        return None
    return _decision(
        action, tier, expected_loss_vnd, now, call_attempts, settings or ShopSettings(), policy
    )


def _decision(
    action: DecisionAction,
    tier: RiskTier,
    expected_loss_vnd: int,
    now: datetime,
    call_attempts: int,
    settings: ShopSettings,
    policy: Policy,
) -> Decision:
    cost = contact_cost(action, settings)
    blocks = []
    if action == DecisionAction.AI_CALL and call_attempts >= MAX_CALL_ATTEMPTS:
        action, cost = DecisionAction.HOLD_FOR_REVIEW, None
        blocks = [ContactBlockReason.ATTEMPTS_EXHAUSTED]
    elif cost is not None and expected_loss_vnd <= cost:  # contact only when it pays for itself
        action, cost = DecisionAction.SHIP_NOW, None
        blocks = [ContactBlockReason.EXPECTED_LOSS_BELOW_COST]
    calls_made = call_attempts + (action == DecisionAction.AI_CALL)
    next_action, wait = follow_up(tier_rule(policy, tier), action, calls_made)
    return Decision(
        decided_at=now,
        action=action,
        policy_version=policy.version,
        expected_loss_vnd=expected_loss_vnd,
        contact_cost_vnd=cost,
        block_reasons=blocks,
        next_action=next_action,
        next_action_at=now + timedelta(minutes=wait) if next_action else None,
    )
