"""The rule set (config/cod_guard_rules_apac.yaml) agrees with AGENTS.md, ShopSettings and the code.

Only `tier_policy` is executed today. These checks keep the rest of the file from drifting, and run
the file's own test cases for tiers, escalation and phone history through the real engines.
"""

import ast
import re
from datetime import datetime, timedelta

import pytest
import yaml

from app.data.orders import VN_TIME
from app.data.phone import to_e164
from app.decision import policy
from app.risk import engine
from app.schemas.enums import DecisionAction, RiskTier
from app.schemas.shops import ShopSettings

RULES = yaml.safe_load(policy.RULES_FILE.read_text(encoding="utf-8"))
VN = RULES["country_packs"]["VN"]
TO_RULES = RULES["baseline_alignment"]["api_actions"]  # ship_now → ALLOW, …
TO_API = {name: DecisionAction(action) for action, name in TO_RULES.items()}
STATE = RULES["state_machine"]["no_response"]["state_by_action"]  # CALL → AWAIT_CALL, …
FAIL = sum(
    VN["costs"][k] for k in ("shipping_out", "return_fee", "packaging", "handling_per_return")
)
LOSS_OUTCOMES = [o for o, meta in RULES["enums"]["outcomes"].items() if meta["in_loss_gate"]]
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=VN_TIME)
EXPRESSION_KEYS = {"when", "guard", "expr", "to_expr"}


def expressions(node, path="rules"):
    """(where, text) for every expression: `when`, `guard`, `expr`, `to_expr` and `*_expr` keys."""
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{path}.{key}"
            if isinstance(value, str) and (key in EXPRESSION_KEYS or str(key).endswith("_expr")):
                yield where, value
            else:
                yield from expressions(value, where)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from expressions(value, f"{path}[{i}]")


def rule(layer_id, rule_id):
    layer = next(x for x in RULES["layers"] if x["id"] == layer_id)
    return next(r for r in layer["rules"] if r["id"] == rule_id)


def cases(test):
    return [pytest.param(c, id=c["id"]) for c in RULES["test_cases"] if test(c["input"])]


def block_reasons(expected):
    return [expected["block_reason"]] if "block_reason" in expected else []


def settings_for(given):
    """ShopSettings with the case's `tenant_costs.action_cost` overrides (rule-file names)."""
    overrides = given.get("tenant_costs", {}).get("action_cost", {})
    fields = {policy.CONTACT_COST_FIELD[TO_API[a]]: cost for a, cost in overrides.items()}
    return ShopSettings(**fields)


def test_every_expression_is_valid_python():
    found = list(expressions(RULES))
    bad = []
    for where, text in found:
        try:
            ast.parse(text, mode="eval")
        except SyntaxError as e:
            bad.append(f"{where}: {e.msg}")
    assert len(found) > 100 and bad == []


def test_the_default_phase_offers_every_tier_action():
    """High → AI call and Very High → deposit happen by default, not through a demo exception."""
    phase = RULES["metadata"]["phase"]
    independent = next(
        r for r in RULES["sales_channel_gate"]["rules"] if r["id"] == "G02_independent"
    )
    offered = set(RULES["phase_capabilities"][phase]["actions"])
    offered &= set(independent["then"]["allowed_actions"])
    tiers = policy.default_policy().tiers
    used = {t.action for t in tiers} | {t.if_no_response for t in tiers if t.if_no_response}
    assert {TO_RULES[a] for a in used} <= offered
    assert RULES["core_parameters"]["ai_call_enabled"] is True


def test_l3_takes_the_action_from_the_tier_policy():
    l3 = next(x for x in RULES["layers"] if x["id"] == "L3_initial_action")
    assert l3["selection"][0]["expr"] == "tier_rule.action"
    assert not any("action" in r["then"] for r in l3["rules"])  # causes pick variants and alerts


def test_no_response_does_not_depend_on_the_cause():
    """Medium escalates to an AI call after 2 hours, whatever the dominant cause is."""
    escalations = [
        t for t in RULES["state_machine"]["transitions"] if t["event"] == "TIMER_NO_RESPONSE"
    ]
    texts = [text for _, text in expressions([RULES["state_machine"]["no_response"], escalations])]
    assert escalations and not any("dominant_cause" in text for text in texts)
    assert "confirm_reminder_after_minutes" not in RULES["core_parameters"]["timeouts"]


def test_vn_contact_rules_match_agents_md():
    hours = ShopSettings().contact_hours
    window = [{"days": "ALL", "start": hours.start, "end": hours.end}]
    contact, timeouts = VN["contact"], RULES["core_parameters"]["timeouts"]
    assert VN["timezone_default"] == "Asia/Ho_Chi_Minh"
    assert contact["message_window"]["slots"] == window
    assert contact["call_window"]["slots"] == window
    assert contact["max_calls_per_phone_24h"] == 1
    assert timeouts["call_max_attempts_per_order"] == policy.MAX_CALL_ATTEMPTS
    assert timeouts["call_retry_gap_minutes"] == policy.CALL_RETRY_GAP_MINUTES
    assert timeouts["order_merge_window_minutes"] == 15
    assert (timeouts["not_ordered_block_days"], timeouts["trust_after_confirm_days"]) == (30, 7)


def test_call_cap_block_and_history_count_every_shop():
    """AGENTS.md: the daily call cap, the 30-day block and the ≥75% rule use all shops' history;
    only the 7-day trust stays within one shop."""
    shared = [
        rule("L1_compliance_contact_protection", "C04_call_frequency")["when"],
        rule("L2_deterministic_checks", "D04_not_ordered_block")["when"],
        rule("L2_deterministic_checks", "D08_phone_history_high_risk")["when"],
    ]
    trusted = rule("L2_deterministic_checks", "D07_tenant_trusted")["when"]
    assert all("phone_history." in w and "tenant_history" not in w for w in shared)
    assert "tenant_history.trusted_until" in trusted
    features = RULES["data_isolation"]["features"]
    assert features["cross_tenant_phone_history"]["enabled"] is True
    assert features["cross_tenant_not_ordered_block"]["enabled"] is True


def test_one_phone_hash_key_for_all_shops():
    phone_hash = RULES["data_isolation"]["phone_hash"]
    assert "PHONE_HASH_KEY" in phone_hash and "tenant_secret" not in phone_hash


@pytest.mark.parametrize("raw", ["+84000000001", "0000000001", "+840000000001", "+8412345", "000"])
def test_vn_phone_pattern_matches_the_app(raw):
    e164 = to_e164(raw)
    assert (e164 is not None) == bool(re.fullmatch(VN["phone"]["mobile_regex"], e164 or raw))


def test_vn_costs_match_shop_settings():
    settings, costs = ShopSettings(), VN["costs"]
    assert settings.failed_delivery_cost_vnd == FAIL
    for action, field in policy.CONTACT_COST_FIELD.items():
        assert costs["action_cost"][TO_RULES[action]] == getattr(settings, field)
    assert costs["contact"]["AI_CALL"] == settings.ai_call_cost_vnd
    first_channel = VN["channels"]["confirm_priority"][0]
    assert costs["contact"][first_channel] == settings.confirmation_link_cost_vnd


def test_every_pack_prices_each_action():
    for code, pack in RULES["country_packs"].items():
        if "costs" in pack:
            assert set(pack["costs"]["action_cost"]) == {"CONFIRM", "CALL", "DEPOSIT", "REVIEW"}, (
                code
            )
            assert "friction_good_customer" not in pack["costs"], code


def test_tier_cut_offs_match_the_engine():
    tiers = list(RiskTier)
    for tier, cut_off in RULES["core_parameters"]["thresholds"]["tier_cut_offs"].items():
        assert engine.tier_of(cut_off) == tier
        assert engine.tier_of(cut_off - 1e-9) == tiers[tiers.index(RiskTier(tier)) - 1]


@pytest.mark.parametrize(
    "case", cases(lambda given: set(given) <= {"probs", "total", "tenant_costs"})
)
def test_rule_file_first_decisions_match_the_policy_engine(case):
    given, expected = case["input"], case["expect"]
    p_failed = sum(given["probs"][o] for o in LOSS_OUTCOMES)
    expected_loss = round(p_failed * FAIL)
    tier = RiskTier(engine.tier_of(p_failed))
    d = policy.decide(tier, expected_loss, NOW, settings=settings_for(given))
    assert p_failed == pytest.approx(expected["p_failed"])
    assert (tier, expected_loss) == (expected["tier"], expected["expected_loss"])
    assert TO_RULES[d.action] == expected["action"]
    assert STATE[expected["action"]] == expected["state"]
    if "action_cost" in expected:
        assert d.contact_cost_vnd == expected["action_cost"]
    if "no_response_after_minutes" in expected:
        assert d.next_action_at - NOW == timedelta(minutes=expected["no_response_after_minutes"])
    assert [r.name for r in d.block_reasons] == block_reasons(expected)


@pytest.mark.parametrize("case", cases(lambda given: "unanswered" in given))
def test_rule_file_escalations_match_the_policy_engine(case):
    given, expected = case["input"], case["expect"]
    tier, unanswered = RiskTier(given["tier"]), TO_API[given["unanswered"]]
    attempts = given.get("call_attempts_order", 0)
    d = policy.escalate(
        tier,
        given["expected_loss"],
        NOW,
        unanswered=unanswered,
        call_attempts=attempts,
        settings=settings_for(given),
    )
    assert TO_RULES[d.action] == expected["no_response_action"]
    assert STATE[expected["no_response_action"]] == expected["state"]
    if "retry_after_minutes" in expected:
        tier_rule = policy.tier_rule(policy.default_policy(), tier)
        assert (
            policy.follow_up(tier_rule, unanswered, attempts)[1] == expected["retry_after_minutes"]
        )
    assert [r.name for r in d.block_reasons] == block_reasons(expected)


@pytest.mark.parametrize(
    "case", cases(lambda given: "phone_orders_n" in given and "sales_channel" not in given)
)
def test_rule_file_history_rule_matches_the_risk_engine(case):
    given, expected = case["input"], case["expect"]
    features = {
        "cod_amount_vnd": 300_000,
        "phone_outcomes_all": given["phone_orders_n"],
        "phone_failed_all": round(given["phone_orders_n"] * given["phone_buyer_fail_rate"]),
    }
    d = engine.decide(features, 0.01, True, {"model2": None, "switched": set()})
    assert d["tier"] == expected["tier"]
    assert d["action"] == engine.ACTION_NAME[TO_API[expected["action"]]]
