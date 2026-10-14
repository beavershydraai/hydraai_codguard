import json
import pickle
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from app.risk import artifacts, engine
from app.risk.features import compute_features, has_house_number
from app.risk.jobs import monitor
from app.risk.jobs.train import train
from app.risk.model import explain1, explainer1
from app.schemas.scoring import Signal
from tests.risk_data import START, orders

NOW = START + timedelta(days=200)
ENC = {"p0": 0.1, "province": {}}


def test_house_number_ignores_digits_in_the_ward():
    assert has_house_number({"street": "Số 12 đường A", "raw": "x"}) == 1
    assert has_house_number({"street": None, "raw": "gần chợ, Phường 5, Hà Nội"}) == 0
    assert has_house_number({"street": None, "raw": "12/3 hẻm B, Phường 5, Hà Nội"}) == 1


def test_outcomes_known_after_the_order_are_not_used():
    past = orders(n_phones=1, seed=1)[0]
    new = orders(n_phones=1, seed=2)[0] | {"order_id": "new"}
    soon = past["placed_at"] + timedelta(hours=1)  # past's result arrives 3 days later
    f = compute_features(new | {"placed_at": soon}, [past], soon, ENC)
    assert f["phone_orders_all"] == 1 and f["phone_outcomes_all"] == 0
    later = past["delivery"]["occurred_at"] + timedelta(hours=1)
    f = compute_features(new | {"placed_at": later}, [past], later, ENC)
    assert f["phone_outcomes_all"] == 1


class Rng:
    def __init__(self, value, choice=None):
        self.value, self.pick = value, choice

    def random(self):
        return self.value

    def choice(self, options):
        return self.pick or options[0]


BASE = {"cod_amount_vnd": 300_000, "phone_outcomes_all": 0, "phone_failed_all": 0}
MODELS = {"model2": None, "switched": set()}


def test_hard_rules_come_first():
    no_rng = Rng(0.99)
    assert (
        engine.decide(BASE | {"cod_amount_vnd": 0}, 0.9, True, MODELS, no_rng)["action"] == "none"
    )
    assert engine.decide(BASE, 0.9, False, MODELS, no_rng)["action"] == "hold"
    returns = BASE | {"phone_outcomes_all": 4, "phone_failed_all": 3}
    assert engine.decide(returns, 0.01, True, MODELS, no_rng)["action"] == "deposit"


def test_random_slice_then_tier_rule():
    d = engine.decide(BASE, 0.30, True, MODELS, Rng(0.01, "link"))
    assert (d["tier"], d["action"], d["random_slice"], d["action_probability"]) == (
        "high",
        "link",
        True,
        0.5,
    )
    d = engine.decide(BASE, 0.30, True, MODELS, Rng(0.99))
    assert (d["action"], d["chosen_by"]) == ("call", "tier rule")
    assert engine.decide(BASE, 0.01, True, MODELS, Rng(0.01))["chosen_by"] == "tier rule"  # low


def test_tier_rule_follows_the_policy_and_its_cost_gate(monkeypatch):
    assert engine.TIER_RULE == {
        "low": "none",
        "medium": "link",
        "high": "call",
        "very_high": "deposit",
    }
    no_rng = Rng(0.99)
    actions = [
        engine.decide(BASE, p, True, MODELS, no_rng)["action"] for p in (0.01, 0.1, 0.3, 0.5)
    ]
    assert actions == ["none", "link", "call", "deposit"]
    monkeypatch.setattr(engine, "FAIL_COST", 2_000)  # 0.1 × 2,000 = 200, less than a link (300)
    d = engine.decide(BASE, 0.1, True, MODELS, no_rng)
    assert (d["action"], d["chosen_by"]) == ("none", "tier rule: expected loss ≤ contact cost")


@pytest.fixture(scope="module")
def trained():
    docs = orders()
    model, report, table = train(docs, NOW, None)
    return docs, model, report, table


def test_training_learns_and_promotes_the_first_model(trained):
    _, model, report, table = trained
    assert report["promoted"] is True
    assert report["candidate"]["roc_auc"] > 0.7
    assert {"is_failed", "placed_at"} <= set(table.columns)
    assert model["version"].startswith("v")


def test_candidate_must_beat_the_current_model(trained):
    docs, model, _, _ = trained
    _, report, _ = train(docs, NOW, model)
    assert report["promoted"] is False  # same data, same score: not better


def test_engine_scores_with_the_latest_model(trained, tmp_path, monkeypatch):
    docs, model, report, _ = trained
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    artifacts.write("latest/model1.pkl", pickle.dumps(model))
    engine._cache.update(at=0.0, models=None)
    doc = docs[0] | {"placed_at": NOW, "order_id": "new"}
    fields = engine.score(
        doc, [d for d in docs if d["buyer_phone_hash"] == doc["buyer_phone_hash"]]
    )
    engine._cache.update(at=0.0, models=None)
    assert 0 <= fields["scoring"]["probability"] <= 1
    assert fields["scoring"]["model_version"] == report["version"]
    assert fields["contact_action"] in {"none", "link", "call", "deposit", "hold"}
    scoring = fields["scoring"]
    assert scoring["expected_loss_vnd"] == pytest.approx(scoring["probability"] * 60_000, abs=4)
    signals = [Signal.model_validate(s) for s in scoring["top_signals"]]
    assert len(signals) == 5
    sizes = [abs(s.contribution) for s in signals]
    assert sizes == sorted(sizes, reverse=True) and sizes[0] > 0
    assert all(
        s.value == pytest.approx(scoring["features"][s.key], abs=1e-4)
        for s in signals
        if s.key in scoring["features"] and s.key != "channel"
    )


def test_the_house_number_signal_uses_the_api_key(trained):
    _, model, _, table = trained
    features = table[model["cols"]].iloc[0].to_dict() | {"address_has_house_number": 0}
    signals = explain1(model, explainer1(model), features, top=len(model["cols"]))
    (house,) = [s for s in signals if "house_number" in s["key"]]
    assert (house["key"], house["value"]) == ("address_missing_house_number", 1)


def test_top_signals_add_up_to_the_change_from_the_average_order(trained):
    docs, model, _, table = trained
    explainer = explainer1(model)
    features = table[model["cols"]].iloc[0].to_dict()
    signals = explain1(model, explainer, features, top=len(model["cols"]))
    raw = model["clf"].predict_proba(table[model["cols"]].iloc[[0]])[0, 1]
    base = 1 / (1 + np.exp(-np.ravel(explainer.expected_value)[0]))
    assert sum(s["contribution"] for s in signals) == pytest.approx(raw - base, abs=1e-3)


def test_engine_without_a_model_leaves_the_order_unscored(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    engine._cache.update(at=0.0, models=None)
    assert engine.score({}, []) is None


def test_betting_test_controls_false_switches_and_finds_real_savings():
    rng = np.random.default_rng(0)
    false_switches = sum(monitor.betting_test(rng.uniform(-1, 1, 2000), 1.0) for _ in range(100))
    assert false_switches <= 10  # alpha = 5 %, checked after every observation
    assert monitor.betting_test(rng.uniform(-0.6, 1, 2000), 1.0)


def test_performance_flags_a_confident_drop():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 500)
    noise = pd.DataFrame({"is_failed": y, "probability": rng.random(500)})
    assert monitor.performance(noise, validation_pr_auc=0.9)["degraded"] is True
    good = pd.DataFrame({"is_failed": y, "probability": y * 0.8 + 0.1})
    assert monitor.performance(good, validation_pr_auc=0.9)["degraded"] is False


def test_tier_check_and_drift_report_run_on_scored_orders(trained):
    _, model, _, table = trained
    cols = model["cols"]
    _, report = monitor.tier_check(table[table["random_slice"]], cols, set())
    assert set(report) == {"medium", "high", "very_high"}
    assert report["very_high"]["status"].startswith("waiting")
    _, drift = monitor.drift_report(table, table.sample(frac=0.5, random_state=0), cols)
    assert drift["too_many_drifted"] is False and drift["missing_values"] == {}
    json.dumps(report, default=str)


def test_scored_rows_reads_live_scoring():
    doc = orders(n_phones=1)[0] | {"scoring": {"probability": 0.2, "features": {"a": 1}}}
    rows = monitor.scored_rows([doc, orders(n_phones=1)[0]])
    assert len(rows) == 1 and rows.loc[0, "a"] == 1 and rows.loc[0, "probability"] == 0.2
