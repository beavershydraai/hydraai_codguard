"""Backtest (E9.1): app/risk/backtest.py and GET /api/v1/dashboard/backtest."""

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.risk import artifacts
from app.risk.backtest import backtest, lift
from app.risk.jobs.train import _predict, holdout, train
from app.schemas.dashboard import BacktestResult
from tests.risk_data import orders
from tests.test_orders_api import api  # noqa: F401
from tests.test_risk import NOW

AT = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def _hold(n=1000, seed=0):
    rng = np.random.default_rng(seed)
    y = rng.random(n) < 0.15
    return pd.DataFrame(
        {
            "is_failed": y.astype(int),
            "cod_amount_vnd": 300_000,
            "phone_outcomes_all": 1,
            "phone_failed_all": (y & (rng.random(n) < 0.4)).astype(int),
            "phone_fail_rate_smoothed_all": rng.random(n) * 0.2 + 0.3 * y,
        }
    )


def test_lift_starts_at_zero_ends_at_one_and_never_falls():
    points = lift([0.9, 0.1, 0.8, 0.2], [1, 0, 1, 0], steps=4)
    shares = [p["failures_caught_share"] for p in points]
    assert shares[0] == 0 and shares[-1] == 1 and shares == sorted(shares)
    assert points[2] == {"contacted_share": 0.5, "failures_caught_share": 1.0}


def test_a_good_score_beats_the_diagonal_and_every_policy_is_compared():
    hold = _hold()
    p = np.clip(hold["is_failed"] * 0.5 + np.random.default_rng(1).random(len(hold)) * 0.2, 0, 1)
    result = BacktestResult.model_validate(backtest(p.to_numpy(), hold, AT))
    curves = {s.policy: s.points for s in result.lift}
    at_20 = {
        name: next(pt for pt in pts if pt.contacted_share == 0.2) for name, pts in curves.items()
    }
    assert (
        at_20["cod_guard"].failures_caught_share
        > at_20["call_everyone"].failures_caught_share
        == 0.2
    )
    rows = {c.policy: c for c in result.comparison}
    assert set(rows) == {
        "cod_guard",
        "phone_history_only",
        "call_everyone",
        "deposit_all",
        "do_nothing",
    }
    assert rows["do_nothing"].contact_rate == 0 and rows["do_nothing"].monthly_savings_vnd == 0
    assert rows["call_everyone"].contact_rate == 1
    assert rows["cod_guard"].monthly_savings_vnd > rows["call_everyone"].monthly_savings_vnd


def test_the_training_job_backtest_on_real_held_out_orders_matches_the_contract():
    docs = orders()
    model, _, table = train(docs, NOW, None)
    hold = holdout(table)
    result = BacktestResult.model_validate(backtest(_predict(model, hold), hold, AT))
    assert result.orders == len(hold) and result.orders_per_day == 300


def test_the_api_returns_the_stored_backtest(api, monkeypatch):  # noqa: F811
    stored = backtest(np.linspace(0, 1, 1000), _hold(), AT)
    monkeypatch.setattr(artifacts, "read", lambda path, country="VN": json.dumps(stored).encode())
    response = api.get("/api/v1/dashboard/backtest")
    assert response.status_code == 200, response.text
    assert response.json()["orders"] == 1000


def test_the_api_reports_no_backtest_before_a_training_run(api, monkeypatch):  # noqa: F811
    monkeypatch.setattr(artifacts, "read", lambda path, country="VN": None)
    assert api.get("/api/v1/dashboard/backtest").status_code == 404
    del api.headers["Authorization"]
    assert api.get("/api/v1/dashboard/backtest").status_code == 401
