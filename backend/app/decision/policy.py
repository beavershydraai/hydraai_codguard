"""Tier policy (E4.2): the action for each risk tier, the expected-loss gate, what follows
when the buyer does not respond, and the shop's call automation: which AI calls the agent places
by itself and which it only suggests to the shop.

The default policy is the `tier_policy` section of config/cod_guard_rules_apac.yaml, validated
with the API's Policy model; a shop's own versions are stored by app/data/policies.py. Contact
protection beyond the call attempt limit (contact hours, one call per phone per day, batching)
is E4.3 and applies to every call, automatic or confirmed by the shop.
"""

from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from app.data import branches
from app.risk.features import cod_amount
from app.schemas.enums import (
    CallAutomationMode,
    ContactBlockReason,
    DecisionAction,
    RiskTier,
    Weekday,
)
from app.schemas.scoring import Decision
from app.schemas.shops import CallAutomation, Policy, ShopSettings, TierPolicy

RULES_FILE = Path(__file__).resolve().parents[2] / "config" / "cod_guard_rules_apac.yaml"
MAX_CALL_ATTEMPTS = 2  # contact protection: no order is called more often, whoever asks
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
    rule: TierPolicy,
    action: DecisionAction,
    calls_made: int,
    automation: CallAutomation | None = None,
) -> tuple[DecisionAction | None, int | None]:
    """What to do, and after how many minutes, if the buyer does not respond to `action`."""
    auto = automation or CallAutomation()
    if action == DecisionAction.AI_CALL and calls_made < auto.max_attempts:
        return DecisionAction.AI_CALL, auto.retry_after_minutes
    if action == rule.action:
        return rule.if_no_response, rule.no_response_after_minutes
    if action in CONTACT_COST_FIELD:  # the escalation went unanswered too: a person decides
        wait = (
            auto.retry_after_minutes
            if action == DecisionAction.AI_CALL
            else rule.no_response_after_minutes or auto.retry_after_minutes
        )
        return DecisionAction.HOLD_FOR_REVIEW, wait
    return None, None


def automation_blocks(
    automation: CallAutomation, order: dict | None, now: datetime, tier: RiskTier
) -> list[ContactBlockReason]:
    """Why the agent may not place an AI call for `order` (risk `tier`) by itself now; empty
    when it may. Without an order (a bare policy check) nothing blocks."""
    if order is None:
        return []
    auto, reason, blocks = automation, ContactBlockReason, []
    if auto.mode == CallAutomationMode.SUGGEST:
        blocks.append(reason.MANUAL_APPROVAL)
    tiers = list(RiskTier)
    if auto.min_tier is not None and tiers.index(tier) < tiers.index(auto.min_tier):
        blocks.append(reason.BELOW_AUTO_CALL_TIER)
    currency = order.get("currency") or branches.country_of(order).currency
    cod = cod_amount(order)
    for r in auto.cod_ranges:
        if r.currency == currency and not (
            (r.min_cod is None or cod >= r.min_cod) and (r.max_cod is None or cod <= r.max_cod)
        ):
            blocks.append(reason.COD_OUT_OF_RANGE)
    if auto.channels is not None and order.get("channel") not in auto.channels:
        blocks.append(reason.CHANNEL_NOT_AUTOMATED)
    window = auto.call_window
    if window:
        local = now.astimezone(branches.country_of(order).tz)
        day = list(Weekday)[local.weekday()]
        if day not in window.days or not window.start <= local.strftime("%H:%M") < window.end:
            blocks.append(reason.OUTSIDE_CALL_WINDOW)
    return blocks


def decide(
    tier: RiskTier,
    expected_loss_vnd: int,
    now: datetime,
    *,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
    confirmed: bool = False,
    action: DecisionAction | None = None,
    order: dict | None = None,
) -> Decision:
    """The decision for a scored order, preserving an action selected by a scoring hard rule.

    A confirmed buyer is never contacted again, even after the order is rescored. With the
    `order`, the shop's call automation applies: an AI call outside its rules becomes a
    suggestion for the shop.
    """
    if action == DecisionAction.CANCEL:
        raise ValueError("only the buyer or the shop cancels an order")
    policy = policy or default_policy()
    action = action or tier_rule(policy, tier).action
    return _decision(
        action,
        tier,
        expected_loss_vnd,
        now,
        0,
        settings or ShopSettings(),
        policy,
        confirmed=confirmed,
        order=order,
    )


def escalate(
    tier: RiskTier,
    expected_loss_vnd: int,
    now: datetime,
    *,
    unanswered: DecisionAction,
    call_attempts: int = 0,
    settings: ShopSettings | None = None,
    policy: Policy | None = None,
    confirmed: bool = False,
    action: DecisionAction | None = None,
    order: dict | None = None,
) -> Decision | None:
    """The decision when the buyer did not respond to `unanswered` in time, or None when nothing
    follows. `call_attempts` counts the AI calls already made for this order. A saved scheduled
    `action` survives a later policy change; the new decision's follow-up uses today's policy,
    and so does the call automation (with the `order`).
    """
    if action == DecisionAction.CANCEL:
        raise ValueError("only the buyer or the shop cancels an order")
    if confirmed:
        return None
    policy = policy or default_policy()
    if action is None:
        action, _ = follow_up(tier_rule(policy, tier), unanswered, call_attempts, policy.automation)
    if action is None:
        return None
    return _decision(
        action,
        tier,
        expected_loss_vnd,
        now,
        call_attempts,
        settings or ShopSettings(),
        policy,
        order=order,
    )


def _decision(
    action: DecisionAction,
    tier: RiskTier,
    expected_loss_vnd: int,
    now: datetime,
    call_attempts: int,
    settings: ShopSettings,
    policy: Policy,
    *,
    confirmed: bool = False,
    order: dict | None = None,
) -> Decision:
    auto = policy.automation
    cost = contact_cost(action, settings)
    blocks, suggested = [], None
    if confirmed and cost is not None:
        action, cost = DecisionAction.SHIP_NOW, None
        blocks = [ContactBlockReason.ALREADY_CONFIRMED]
    elif action == DecisionAction.AI_CALL and call_attempts >= auto.max_attempts:
        action, cost = DecisionAction.HOLD_FOR_REVIEW, None
        blocks = [ContactBlockReason.ATTEMPTS_EXHAUSTED]
    elif cost is not None and expected_loss_vnd <= cost:  # contact only when it pays for itself
        action, cost = DecisionAction.SHIP_NOW, None
        blocks = [ContactBlockReason.EXPECTED_LOSS_BELOW_COST]
    elif action == DecisionAction.AI_CALL and (blocks := automation_blocks(auto, order, now, tier)):
        # Outside the shop's call automation: suggest the call, a person starts it.
        action, cost, suggested = DecisionAction.HOLD_FOR_REVIEW, None, DecisionAction.AI_CALL
    calls_made = call_attempts + (action == DecisionAction.AI_CALL)
    next_action, wait = follow_up(tier_rule(policy, tier), action, calls_made, auto)
    return Decision(
        decided_at=now,
        action=action,
        policy_version=policy.version,
        expected_loss_vnd=expected_loss_vnd,
        contact_cost_vnd=cost,
        block_reasons=blocks,
        next_action=next_action,
        next_action_at=now + timedelta(minutes=wait) if next_action else None,
        suggested_action=suggested,
    )
