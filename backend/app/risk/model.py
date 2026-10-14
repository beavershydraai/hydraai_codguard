"""Model 1 (risk) and Model 2 (S-learner): fitting and prediction (tasks/E2.3-risk-features.md).

ponytail: sklearn HistGradientBoosting instead of LightGBM; same family (histogram gradient
boosting), no extra native dependency. Swap if validation shows a gap.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

from app.risk.features import CHANNELS, SIGNALS

FAIL_COST = 60_000  # ShopSettings.failed_delivery_cost_vnd default
ACTION_COST = {"none": 0, "link": 300, "call": 1_500, "deposit": 0}  # ShopSettings; deposit unset
ACTIONS = list(ACTION_COST)
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


def explain1(model: dict, explainer, features: dict, top: int = 5) -> list[dict]:
    """The `top` features that moved this order's risk most, as Signal dicts (E2.4).

    SHAP values are in log-odds. They are rescaled so they add up to the change in the model's
    probability from the average order to this one: positive raises risk, negative lowers it.
    Calibration is monotone, so it keeps their order and sign.
    """
    x = pd.DataFrame([features])[model["cols"]]
    phi = explainer.shap_values(x)[0]
    base, logit = float(np.ravel(explainer.expected_value)[0]), float(phi.sum())
    change = 1 / (1 + np.exp(-(base + logit))) - 1 / (1 + np.exp(-base))
    scale = change / logit if abs(logit) > 1e-9 else 0.0
    signals = []
    for i in np.argsort(-np.abs(phi))[:top]:
        key = model["cols"][i]
        group, label = SIGNALS[key]
        value = features[key]
        if key == "address_has_house_number":  # the API has named the inverse flag since 8 Oct
            key, value = "address_missing_house_number", 1 - value
        signals.append(
            {
                "key": key,
                "group": group,
                "label_vi": label,
                "value": CHANNELS[int(value)] if key == "channel" else round(value, 4),
                "contribution": round(float(phi[i] * scale), 4),
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


def expected_cost(model2: dict, X: pd.DataFrame, action: str):
    """P(fail | x, action) × failed-delivery cost + action cost, per row."""
    p = model2["clf"].predict_proba(with_action(X[model2["cols"]], [action] * len(X)))[:, 1]
    return p * FAIL_COST + ACTION_COST[action]
