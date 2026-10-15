"""Baseline A names for the workflow branches and the decision log (E4.7).

The rule set is the source of truth. `baseline_alignment.api_actions` maps every DecisionAction
to the Baseline A action the graph branches on, and `enums.outcomes` lists the seven outcomes the
risk model predicts. Reading them keeps the pipeline aligned when the owner edits the rule set.
"""

from functools import lru_cache

import yaml

from app.decision.policy import RULES_FILE
from app.schemas.enums import DecisionAction

ALLOW, CONFIRM, CALL, DEPOSIT, REVIEW = "ALLOW", "CONFIRM", "CALL", "DEPOSIT", "REVIEW"
# One ADK route per Baseline A action. Anything else reaches DEFAULT_ROUTE, which is REVIEW:
# an unmapped or disabled action must never contact the buyer.
BRANCHES = (ALLOW, CONFIRM, CALL, DEPOSIT, REVIEW)
# engine.score reports the path that chose the action; the rule set gives each path an id.
RULE_ID = {
    "hard rule: fully prepaid": "D01_prepaid",
    "hard rule: invalid phone": "D03_invalid_phone",
    "hard rule: ≥ 75 % returns": "D08_phone_history_high_risk",
    "random slice": "L3_initial_action#exploration",
    "model 2": "L3_initial_action#ev_argmax",
    "tier rule": "L3_initial_action#tier_action",
    "tier rule: expected loss ≤ contact cost": "L3_initial_action#cost_gate",
}
POST_INTERACTION = "L4_post_interaction_table"


@lru_cache
def rules() -> dict:
    return yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))


@lru_cache
def rule_set_version() -> str:
    return rules()["metadata"]["rule_set_version"]


@lru_cache
def outcomes() -> tuple[str, ...]:
    return tuple(rules()["enums"]["outcomes"])


@lru_cache
def _by_action() -> dict[str, str]:
    mapping = rules()["baseline_alignment"]["api_actions"]
    missing = {a for a in DecisionAction if a != DecisionAction.CANCEL} - mapping.keys()
    if missing:
        raise ValueError(f"the rule set maps no Baseline A action to {sorted(missing)}")
    return mapping


def route_for(action: DecisionAction | str | None) -> str:
    """The branch for a decided action. An unknown or missing action holds the order for review."""
    name = _by_action().get(action)
    return name if name in BRANCHES else REVIEW


def rule_id(chosen_by: str | None) -> str:
    return RULE_ID.get(chosen_by, "L3_initial_action")
