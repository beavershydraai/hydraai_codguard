"""Model 1 (risk) and Model 2 (S-learner): fitting and prediction (tasks/E2.3-risk-features.md).

ponytail: sklearn HistGradientBoosting instead of LightGBM; same family (histogram gradient
boosting), no extra native dependency. Swap if validation shows a gap.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

from app.risk.features import CHANNELS, SIGNALS

ACTIONS = ["none", "link", "call", "deposit"]


def costs_of(country) -> dict:
    """{'fail', and each action} in the country's currency (config/branches.yaml)."""
    c = country.costs
    return {
        "fail": c["failed_delivery"],
        "none": 0,
        "link": c["confirmation_link"],
        "call": c["ai_call"],
        "deposit": c["deposit_request"],
    }


KEY_COLUMNS = [
    "order_id",
    "placed_at",
    "final_at",
    "province",
    "tier",
    "contact_action",
    "action_probability",
    "random_slice",
    "is_failed",
]


def _gbm(iterations: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=iterations, learning_rate=0.05, min_samples_leaf=40, random_state=0
    )


def fit_model1(df: pd.DataFrame, cols: list[str]) -> dict:
    """Train on the older 80 %, calibrate (isotonic) on the newer 20 %: P is used for money."""
    df = df.sort_values("placed_at")
    cut = int(len(df) * 0.8)
    fit, cal = df.iloc[:cut], df.iloc[cut:]
    clf = _gbm(300).fit(fit[cols], fit["is_failed"])
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(clf.predict_proba(cal[cols])[:, 1], cal["is_failed"])
    return {"clf": clf, "iso": iso, "cols": cols}


def predict1(model: dict, X: pd.DataFrame):
    return model["iso"].predict(model["clf"].predict_proba(X[model["cols"]])[:, 1])


def explainer1(model: dict):
    """SHAP TreeExplainer for model 1 (exact for HistGradientBoosting, log-odds scale)."""
    import shap  # imported here: slow to load and only the scoring path needs it

    return shap.TreeExplainer(model["clf"])


def explain1(model: dict, explainer, features: dict) -> dict:
    """Exact TreeSHAP contributions of every feature to this order's risk (E2.4).

    SHAP values are in log-odds. They are rescaled so they add up to the change in the model's
    probability from the average order (`base_value`) to this one (`prediction`): positive raises
    risk. This is the boosted model's probability before calibration; calibration is monotone,
    so it keeps their order and sign.
    """
    x = pd.DataFrame([features])[model["cols"]]
    phi = explainer.shap_values(x)[0]
    base, logit = float(np.ravel(explainer.expected_value)[0]), float(phi.sum())
    before, after = 1 / (1 + np.exp(-base)), 1 / (1 + np.exp(-(base + logit)))
    scale = (after - before) / logit if abs(logit) > 1e-9 else 0.0
    return {
        "available": True,
        "method": "tree_shap",
        "approximate": False,
        "output": "model_failure_probability",
        "base_value": round(float(before), 4),
        "prediction": round(float(after), 4),
        "contributions": {
            c: round(float(v * scale), 4) for c, v in zip(model["cols"], phi, strict=True)
        },
    }


def top_signals(features: dict, contributions: dict, top: int = 5) -> list[dict]:
    """The `top` largest contributions as API Signal dicts (key, group, label_vi, value)."""
    signals = []
    for key in sorted(contributions, key=lambda k: -abs(contributions[k]))[:top]:
        group, label = SIGNALS[key]
        value, contribution = features[key], contributions[key]
        signals.append(
            {
                "key": key,
                "group": group,
                "label_vi": label,
                "value": CHANNELS[int(value)] if key == "channel" else round(value, 4),
                "contribution": contribution,
            }
        )
    return signals


def with_action(X: pd.DataFrame, actions) -> pd.DataFrame:
    X = X.copy()
    for a in ACTIONS:
        X[f"action_{a}"] = [int(x == a) for x in actions]
    return X


def fit_model2(df: pd.DataFrame, cols: list[str]) -> dict:
    """S-learner: one model, the action as one more input. Trained on random-slice orders only."""
    clf = _gbm(200).fit(with_action(df[cols], df["contact_action"]), df["is_failed"])
    return {"clf": clf, "cols": cols}


def expected_cost(model2: dict, X: pd.DataFrame, action: str, costs: dict):
    """P(fail | x, action) × failed-delivery cost + action cost, per row (costs: costs_of)."""
    p = model2["clf"].predict_proba(with_action(X[model2["cols"]], [action] * len(X)))[:, 1]
    return p * costs["fail"] + costs[action]
