"""Explanation evidence refers to the calibrated probability, without training labels."""

import math

import numpy as np
import pandas as pd
import pytest
from sklearn.isotonic import IsotonicRegression

from app.risk import model as risk_model


class LinearRisk:
    """Two independent risk inputs with a hand-calculable probability."""

    def predict_proba(self, X):
        p = 0.1 + 0.2 * X["phone_failed_all"] + 0.1 * X["cod_amount_vnd"]
        return np.column_stack([1 - p, p])


def calibrated_model():
    return {
        "clf": LinearRisk(),
        "iso": IsotonicRegression(out_of_bounds="clip").fit([0, 0.5, 1], [0, 0.8, 1]),
        "cols": ["phone_failed_all", "cod_amount_vnd"],
        "shap_background": [{"phone_failed_all": 0, "cod_amount_vnd": 0}],
    }


def test_explanation_contributions_use_the_calibrated_failure_probability():
    model = calibrated_model()
    row = pd.DataFrame([{"cod_amount_vnd": 1, "phone_failed_all": 1}])

    explanation = risk_model.explain1(model, row)

    assert explanation["available"] is True
    assert explanation["method"] == "permutation_shap"
    assert explanation["approximate"] is True
    assert explanation["output"] == "calibrated_failure_probability"
    # Raw probabilities are 0.1 and 0.4; isotonic calibration multiplies these by 1.6.
    assert explanation["base_value"] == pytest.approx(0.16)
    assert explanation["prediction"] == pytest.approx(0.64)
    assert explanation["contributions"] == pytest.approx(
        {"phone_failed_all": 0.32, "cod_amount_vnd": 0.16}
    )
    assert explanation["base_value"] + sum(explanation["contributions"].values()) == (
        pytest.approx(risk_model.predict1(model, row)[0])
    )
    assert all(math.isfinite(value) for value in explanation["contributions"].values())


@pytest.mark.parametrize("background", [None, []])
def test_legacy_models_without_a_background_report_unavailable(background):
    model = {} if background is None else {"shap_background": background}

    assert risk_model.explain1(model, pd.DataFrame([{"phone_failed_all": 1}])) == {
        "available": False,
        "method": "permutation_shap",
        "contributions": {},
    }


def test_training_background_contains_only_real_older_training_feature_rows():
    table = pd.DataFrame(
        {
            "placed_at": pd.date_range("2026-01-01", periods=100, tz="UTC"),
            "order_id": [f"synthetic_{i}" for i in range(100)],
            "is_failed": [i % 2 for i in range(100)],
            "phone_failed_all": [i % 3 for i in range(100)],
            "cod_amount_vnd": [i * 10_000 for i in range(100)],
        }
    )
    cols = ["phone_failed_all", "cod_amount_vnd"]

    model = risk_model.fit_model1(table, cols)

    background = model["shap_background"]
    assert len(background) == 4
    older = table.iloc[:80][cols].to_dict(orient="records")
    assert all(row in older for row in background)
    assert all(set(row) == set(cols) for row in background)
    assert all(isinstance(value, (float, int)) for row in background for value in row.values())


def test_explanation_rejects_nonfinite_probability_evidence(monkeypatch):
    monkeypatch.setattr(risk_model, "predict1", lambda model, X: np.full(len(X), float("nan")))

    with pytest.raises(ValueError, match="finite"):
        risk_model.explain1(
            calibrated_model(), pd.DataFrame([{"cod_amount_vnd": 1, "phone_failed_all": 1}])
        )
