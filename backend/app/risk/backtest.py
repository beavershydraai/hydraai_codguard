"""Backtest (E9.1): COD Guard against simpler policies on orders the model never saw.

The training job runs it on the held-out newest 20 % of labelled orders and stores the result as
`latest/backtest.json`, which GET /api/v1/dashboard/backtest returns (BacktestResult).

- Lift: contact orders from the highest score down; y is the share of failed deliveries among the
  orders contacted so far. COD Guard ranks by Model 1, "phone history only" by the phone's
  smoothed failure rate, "call everyone" has no ranking (the diagonal).
- Comparison: what each policy would have done to every held-out order, the share of failed
  deliveries it prevents and the monthly saving for a shop of ORDERS_PER_DAY orders:
  (failures prevented x failed-delivery cost - contact costs) per order x ORDERS_PER_DAY x 30.

Assumptions to verify (estimates; the UI labels them "estimated"):
- PREVENTS: share of the failed deliveries an action stops when it reaches the order. Set by hand,
  not measured; the random-slice orders (app/risk/jobs/monitor.py) can measure them per tier.
- ORDERS_PER_DAY = 300, the shop size in E9.3. Costs are the country's (config/branches.yaml).
"""

import numpy as np
import pandas as pd

from app.data import branches
from app.risk.engine import TIER_RULE, tier_of
from app.risk.model import costs_of

ORDERS_PER_DAY = 300
PREVENTS = {"none": 0.0, "link": 0.4, "call": 0.6, "deposit": 0.85}


def lift(score, y, steps: int = 20) -> list[dict]:
    """Share of failed deliveries caught when contacting the top x % by `score`."""
    y = np.asarray(y)[np.argsort(-np.asarray(score), kind="stable")]
    caught = np.concatenate([[0], np.cumsum(y)]) / max(y.sum(), 1)
    points = []
    for k in range(steps + 1):
        share = k / steps
        points.append(
            {
                "contacted_share": round(share, 4),
                "failures_caught_share": round(float(caught[round(share * len(y))]), 4),
            }
        )
    return points


def cod_guard_actions(p, hold: pd.DataFrame, costs: dict) -> list[str]:
    """The engine's choice without the random slice: hard rules, the tier rule, the cost gate."""
    actions = []
    for prob, row in zip(p, hold.itertuples(), strict=True):
        outcomes, failed = row.phone_outcomes_all, row.phone_failed_all
        if row.cod_amount_vnd == 0:
            action = "none"  # fully prepaid
        elif outcomes >= 3 and failed / outcomes >= 0.75:
            action = "deposit"  # hard rule: phone with >= 75 % returns
        else:
            action = TIER_RULE[tier_of(prob)]
            if prob * costs["fail"] <= costs[action]:
                action = "none"  # expected loss does not cover the contact
        actions.append(action)
    return actions


def compare(actions: list[str], y, costs: dict) -> dict:
    y = np.asarray(y)
    prevented = sum(fail * PREVENTS[a] for a, fail in zip(actions, y, strict=True))
    cost = sum(costs[a] for a in actions)
    per_order = (prevented * costs["fail"] - cost) / len(actions)
    return {
        "contact_rate": round(sum(a != "none" for a in actions) / len(actions), 4),
        "failures_caught_rate": round(float(prevented / max(y.sum(), 1)), 4),
        "monthly_savings_vnd": round(per_order * ORDERS_PER_DAY * 30),
    }


def backtest(p, hold: pd.DataFrame, generated_at, code: str = "VN") -> dict:
    """A BacktestResult dict for the country's model probabilities `p` on held-out orders."""
    country = branches.country(code)
    costs = costs_of(country)
    y, n = hold["is_failed"].to_numpy(), len(hold)
    policies = {
        "cod_guard": cod_guard_actions(p, hold, costs),
        "phone_history_only": ["call" if f >= 1 else "none" for f in hold["phone_failed_all"]],
        "call_everyone": ["call"] * n,
        "deposit_all": ["deposit"] * n,
        "do_nothing": ["none"] * n,
    }
    return {
        "generated_at": generated_at.isoformat(),
        "country": code,
        "currency": country.currency,
        "dataset": f"{code}: newest 20 % of labelled orders, held out from training ({n})",
        "orders": n,
        "orders_per_day": ORDERS_PER_DAY,
        "failed_delivery_cost_vnd": costs["fail"],
        "lift": [
            {"policy": "cod_guard", "points": lift(p, y)},
            {
                "policy": "phone_history_only",
                "points": lift(hold["phone_fail_rate_smoothed_all"], y),
            },
            {
                "policy": "call_everyone",
                "points": [
                    {
                        "contacted_share": x["contacted_share"],
                        "failures_caught_share": x["contacted_share"],
                    }
                    for x in lift(p, y)
                ],
            },
        ],
        "comparison": [{"policy": name} | compare(a, y, costs) for name, a in policies.items()],
    }
