"""Model 1 (risk) and Model 2 (S-learner): fitting and prediction (tasks/E2.3-risk-features.md).

ponytail: sklearn HistGradientBoosting instead of LightGBM; same family (histogram gradient
boosting), no extra native dependency. Swap if validation shows a gap.
"""

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

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
