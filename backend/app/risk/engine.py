"""Scoring a new order (docs/diagrams/action-decision.png, top lane):
features → Model 1 → hard rules → random slice → Model 2 in switched tiers → tier policy
(app/decision/policy.py: the tier's action, unless the expected loss does not cover its cost).

The models are loaded from the bucket on first use; until a model exists, orders are stored
unscored and the load is retried every few minutes.
"""

import json
import logging
import pickle
import random
import time
from datetime import UTC, datetime

import pandas as pd

from app.data import branches
from app.decision import policy
from app.risk import artifacts
from app.risk.features import compute_features
from app.risk.model import (
    costs_of,
    expected_cost,
    explain1,
    explainer1,
    predict1,
    top_signals,
)
from app.schemas.enums import DecisionAction, RiskTier

log = logging.getLogger(__name__)
TIER_OPTIONS = {
    "low": ["none"],
    "medium": ["none", "link", "call"],
    "high": ["link", "call"],
    "very_high": ["call", "deposit"],
}
ACTION_NAME = {  # DecisionAction → the name stored in contact_action and used by Model 2
    DecisionAction.SHIP_NOW: "none",
    DecisionAction.SEND_CONFIRMATION_LINK: "link",
    DecisionAction.AI_CALL: "call",
    DecisionAction.REQUIRE_DEPOSIT: "deposit",
    DecisionAction.HOLD_FOR_REVIEW: "hold",
}
TIER_RULE = {t.tier.value: ACTION_NAME[t.action] for t in policy.default_policy().tiers}
RANDOM_SLICE = 0.12  # team decision: 10–15 %
RETRY_SECONDS = 300
_rng = random.Random()
_cache: dict = {}  # country -> {"at": last load attempt, "models": ...}


def tier_of(p: float) -> str:
    """ponytail: fixed cut-offs until E2.5 sets them from the shop's costs."""
    return "low" if p < 0.08 else "medium" if p < 0.20 else "high" if p < 0.40 else "very_high"


def expected_loss(p: float, failed_cost: int, prepaid: int = 0) -> int:
    """P(failed) × what a failed delivery still costs the shop: the cost of one failed delivery
    less what the buyer already paid, which the shop keeps when the buyer refuses (E2.5)."""
    return round(p * max(failed_cost - prepaid, 0))


HIGH = ("high", "very_high")


def location_only(features: dict, model1: dict) -> bool:
    """Whether the province alone lifts the order to High or Very High: scored with the average
    province (`p0`, what an unknown province gets), it would be below High. Location may raise a
    score but is never the only reason for High or Very High (AGENTS.md)."""
    neutral = features | {"province_fail_rate_te": model1["enc"]["p0"]}
    return tier_of(float(predict1(model1, pd.DataFrame([neutral]))[0])) not in HIGH


def load_models(code: str = "VN") -> dict | None:
    """The country's {'model1', 'model2', 'switched'}, or None while it has no trained model."""
    cache = _cache.setdefault(code, {"at": 0.0, "models": None})
    if cache["models"] is None and time.time() - cache["at"] > RETRY_SECONDS:
        cache["at"] = time.time()
        try:
            raw1 = artifacts.read("latest/model1.pkl", code)
            if raw1:
                raw2, switched = (
                    artifacts.read("latest/model2.pkl", code),
                    artifacts.read("latest/switched.json", code),
                )
                cache["models"] = {
                    "model1": pickle.loads(raw1),
                    "model2": pickle.loads(raw2) if raw2 else None,
                    "switched": set(json.loads(switched)) if switched else set(),
                }
        except Exception:  # never let a storage problem break order intake
            log.exception("Could not load the risk models for %s", code)
    return cache["models"]


def decide(
    features: dict,
    p: float,
    phone_valid: bool,
    models: dict,
    rng=_rng,
    country: branches.Country | None = None,
    loss: int | None = None,
) -> dict:
    """Tier and action for one order, with the path that chose it, at the country's costs.
    `loss` is the order's expected loss (default: with nothing prepaid)."""
    country = country or branches.country("VN")
    if loss is None:
        loss = expected_loss(p, country.costs["failed_delivery"])
    if features["cod_amount_vnd"] == 0:
        return {"tier": None, "action": "none", "chosen_by": "hard rule: fully prepaid"}
    if not phone_valid:
        return {"tier": tier_of(p), "action": "hold", "chosen_by": "hard rule: invalid phone"}
    outcomes, failed = features["phone_outcomes_all"], features["phone_failed_all"]
    if outcomes >= 3 and failed / outcomes >= 0.75:
        return {"tier": "very_high", "action": "deposit", "chosen_by": "hard rule: ≥ 75 % returns"}
    tier, capped = tier_of(p), False
    if tier in HIGH and "model1" in models and location_only(features, models["model1"]):
        tier, capped = "medium", True
    options = TIER_OPTIONS[tier]
    if len(options) > 1 and rng.random() < RANDOM_SLICE:
        return {
            "tier": tier,
            "action": rng.choice(options),
            "chosen_by": "random slice",
            "random_slice": True,
            "action_probability": 1 / len(options),
        }
    if tier in models["switched"] and models["model2"]:
        X = pd.DataFrame([features])
        costs = {
            a: float(expected_cost(models["model2"], X, a, costs_of(country))[0]) for a in options
        }
        return {"tier": tier, "action": min(costs, key=costs.get), "chosen_by": "model 2"}
    decision = policy.decide(
        RiskTier(tier), loss, datetime.now(UTC), settings=country.settings
    )
    chosen_by = "tier rule: expected loss ≤ contact cost" if decision.block_reasons else "tier rule"
    if capped:
        chosen_by += ", capped at medium: location was the only reason for high"
    return {"tier": tier, "action": ACTION_NAME[decision.action], "chosen_by": chosen_by}


def score(doc: dict, history: list[dict]) -> dict | None:
    """Fields to add to the order document, or None when its country has no model yet."""
    country = branches.country_of(doc)
    models = load_models(country.code)
    if models is None:
        return None
    model1 = models["model1"]
    features = compute_features(doc, history, doc["placed_at"], model1["enc"])
    p = float(predict1(model1, pd.DataFrame([features]))[0])
    try:
        if "explainer" not in models:  # built once per loaded model
            models["explainer"] = explainer1(model1)
        shap = explain1(model1, models["explainer"], features)
        signals = top_signals(features, shap["contributions"])
    except Exception:  # an explanation problem must not stop the order being scored
        log.exception("Could not explain the score of %s", doc.get("order_id"))
        shap, signals = {"available": False, "method": "tree_shap", "contributions": {}}, []
    loss = expected_loss(p, country.costs["failed_delivery"], doc.get("prepaid_vnd", 0))
    decision = {"random_slice": False, "action_probability": 1.0} | decide(
        features, p, doc["buyer_phone_hash"] is not None, models, country=country, loss=loss
    )
    return {
        "tier": decision["tier"],
        "contact_action": decision["action"],
        "random_slice": decision["random_slice"],
        "action_probability": decision["action_probability"],
        "scoring": {
            "probability": round(p, 4),
            "risk_score": round(p * 100),
            "tier": decision["tier"],
            "expected_loss_vnd": loss,
            "failed_delivery_cost_vnd": country.costs["failed_delivery"],
            "chosen_by": decision["chosen_by"],
            "features": features,
            "shap": shap,
            "top_signals": signals,
            "model_version": model1["version"],
            "scored_at": datetime.now(UTC),
        },
    }
