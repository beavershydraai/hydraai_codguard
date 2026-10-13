"""Daily monitoring job (Cloud Run job `codguard-monitor`, Cloud Scheduler):

1. Evidently report: data quality and drift of recent scored orders vs the training features.
2. Performance of Model 1 on recent orders with a final state; a confident drop below the
   model's own validation PR-AUC is a retrain trigger (RETRAIN_MODE=auto starts codguard-train).
3. Tier check for Model 2 (docs/diagrams/action-decision.png, learning lane): doubly robust
   saving of "Model 2 picks" over "tier rule" on random-slice orders, switched on or off by an
   anytime-valid betting test, so checking every day does not inflate false switches.

Not in COD_Guard_Epics.md yet; see tasks/E2.3-risk-features.md, "Monitoring and retraining".
Run: python -m app.risk.jobs.monitor
"""

import io
import json
import os
import pickle
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from app.data.orders import final_state
from app.risk import artifacts
from app.risk.engine import TIER_OPTIONS, TIER_RULE
from app.risk.model import ACTION_COST, FAIL_COST, expected_cost, fit_model2

WINDOW = timedelta(days=30)
ALPHA = 0.05


def betting_test(x: np.ndarray, bound: float, alpha: float = ALPHA) -> bool:
    """Anytime-valid one-sided test of H0: mean(x) <= 0, for x in [-bound, bound].

    Bets a predictable fraction of wealth on each observation (Waudby-Smith & Ramdas, JRSSB
    2024). Under H0 wealth is a non-negative supermartingale, so by Ville's inequality it
    reaches 1/alpha with probability <= alpha, however often it is checked.
    """
    wealth, mean, sq, n = 1.0, 0.0, 0.0, 0
    for xi in np.asarray(x, dtype=float) / bound:
        var = sq / n - mean**2 if n else 0.25
        lam = min(max(mean / (var + mean**2) if var + mean**2 > 0 else 0.0, 0.0), 0.5)
        wealth *= 1 + lam * xi
        if wealth >= 1 / alpha:
            return True
        n, mean, sq = n + 1, mean + (xi - mean) / (n + 1), sq + xi**2
    return False


def tier_savings(random_rows: pd.DataFrame, cols: list[str], tier: str):
    """DR estimate per order of cost(tier rule) − cost(Model 2 picks), Model 2 trained on the
    older 60 % of the tier's random orders and judged on the newer 40 %."""
    rows = random_rows[random_rows["tier"] == tier].sort_values("final_at")
    options = TIER_OPTIONS[tier]
    if any(set(rows.loc[rows["contact_action"] == a, "is_failed"]) != {0, 1} for a in options):
        return None
    cut = int(len(rows) * 0.6)
    old, new = rows.iloc[:cut], rows.iloc[cut:]
    model2 = fit_model2(old, cols)
    q = pd.DataFrame({a: expected_cost(model2, new, a) for a in options}, index=new.index)
    picks = q.idxmin(axis=1)
    logged = new["contact_action"]
    real = new["is_failed"] * FAIL_COST + logged.map(ACTION_COST)
    q_logged = np.array([q.at[i, a] for i, a in logged.items()])
    k = len(options)

    def dr(policy: pd.Series) -> np.ndarray:
        q_policy = np.array([q.at[i, a] for i, a in policy.items()])
        return q_policy + (logged == policy).to_numpy() * k * (real.to_numpy() - q_logged)

    rule = pd.Series(TIER_RULE[tier], index=new.index)
    bound = (1 + 2 * k) * (FAIL_COST + max(ACTION_COST.values()))
    return dr(rule) - dr(picks), bound, picks.value_counts().to_dict()


def tier_check(random_rows: pd.DataFrame, cols: list[str], switched: set[str]):
    report = {}
    for tier in ("medium", "high", "very_high"):
        result = tier_savings(random_rows, cols, tier)
        if result is None:
            report[tier] = {"status": "waiting: an action lacks both outcomes"}
            continue
        savings, bound, picks = result
        if betting_test(savings, bound):
            switched.add(tier)
        elif betting_test(-savings, bound):
            switched.discard(tier)
        report[tier] = {
            "random_orders": int((random_rows["tier"] == tier).sum()),
            "saving_per_order": round(float(savings.mean())),
            "picks": picks,
            "switched": tier in switched,
        }
    return switched, report


def performance(recent: pd.DataFrame, validation_pr_auc: float, seed: int = 0) -> dict:
    """PR-AUC on recent orders with a 95 % bootstrap interval; degraded if it lies wholly below
    the model's validation PR-AUC."""
    y, p = recent["is_failed"].to_numpy(), recent["probability"].to_numpy()
    if len(set(y)) < 2:
        return {"status": "waiting: recent orders lack both outcomes"}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(200):
        i = rng.integers(0, len(y), len(y))
        if len(set(y[i])) == 2:
            boots.append(average_precision_score(y[i], p[i]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {
        "orders": len(y),
        "pr_auc": round(float(average_precision_score(y, p)), 4),
        "interval": [round(float(lo), 4), round(float(hi), 4)],
        "validation_pr_auc": validation_pr_auc,
        "degraded": bool(hi < validation_pr_auc),
    }


def drift_report(reference: pd.DataFrame, current: pd.DataFrame, cols: list[str]):
    from evidently import DataDefinition, Dataset, Report
    from evidently.presets import DataDriftPreset, DataSummaryPreset

    definition = DataDefinition(numerical_columns=cols)
    # Summary statistics go in the HTML report only: their default tests compare row counts and
    # quantiles with the training set, which always differ for a 30-day window.
    snapshot = Report([DataDriftPreset(), DataSummaryPreset()]).run(
        Dataset.from_pandas(current[cols], data_definition=definition),
        Dataset.from_pandas(reference[cols], data_definition=definition),
    )
    drift = Report([DataDriftPreset()], include_tests=True).run(
        Dataset.from_pandas(current[cols], data_definition=definition),
        Dataset.from_pandas(reference[cols], data_definition=definition),
    )
    tests = drift.dict().get("tests", [])
    drifted = [
        t["name"].removeprefix("Value Drift for column ")
        for t in tests
        if t["name"].startswith("Value Drift") and str(t.get("status")).endswith("FAIL")
    ]
    share_ok = all(
        str(t.get("status")).endswith("SUCCESS") for t in tests if t["name"].startswith("Share")
    )
    missing = {c: round(float(v), 4) for c, v in current[cols].isna().mean().items() if v > 0}
    alert = not share_ok or bool(missing)
    return snapshot, {
        "drifted_columns": drifted,
        "too_many_drifted": not share_ok,
        "missing_values": missing,
        "alert": alert,
    }


def scored_rows(docs: list[dict]) -> pd.DataFrame:
    """Orders scored live: the features they were scored with, their P and their final state."""
    rows = []
    for d in docs:
        scoring = d.get("scoring") or {}
        if not scoring.get("features"):
            continue
        label, at = final_state(d)
        rows.append(
            {
                "placed_at": d["placed_at"],
                "final_at": at,
                "is_failed": label,
                "tier": d.get("tier"),
                "contact_action": d.get("contact_action"),
                "random_slice": bool(d.get("random_slice")),
                "probability": scoring.get("probability"),
                **scoring["features"],
            }
        )
    return pd.DataFrame(rows)


def run_training_job() -> None:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    region = os.environ.get("REGION", "asia-southeast1")
    job = os.environ.get("TRAIN_JOB", "codguard-train")
    url = f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run"
    AuthorizedSession(creds).post(url).raise_for_status()


def main() -> None:
    from app.data.store import get_store

    raw = artifacts.read("latest/model1.pkl")
    if raw is None:
        print(json.dumps({"status": "no model yet: run codguard-train first"}))
        return
    model1 = pickle.loads(raw)
    metrics = json.loads(artifacts.read("latest/metrics.json"))
    reference = pd.read_parquet(io.BytesIO(artifacts.read("latest/features.parquet")))
    cols = model1["cols"]

    scored = scored_rows(get_store().all())
    end = scored["placed_at"].max() if len(scored) else datetime.now(UTC)
    recent = scored[scored["placed_at"] >= end - WINDOW]
    summary = {"model_version": model1["version"], "recent_orders": len(recent)}
    if len(recent):
        snapshot, summary["drift"] = drift_report(reference, recent, cols)
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        artifacts.write(
            f"monitoring/{day}/report.html", snapshot.get_html_str(as_iframe=False).encode()
        )
        labelled = recent.dropna(subset=["is_failed"])
        summary["performance"] = performance(labelled, metrics["validation_pr_auc"])

    random_rows = scored[scored["random_slice"] & scored["is_failed"].notna()]
    raw_switched = artifacts.read("latest/switched.json")
    switched = set(json.loads(raw_switched)) if raw_switched else set()
    switched, summary["tiers"] = tier_check(random_rows, cols, switched)
    if len(random_rows):
        artifacts.write("latest/model2.pkl", pickle.dumps(fit_model2(random_rows, cols)))
    artifacts.write("latest/switched.json", json.dumps(sorted(switched)).encode())

    degraded = summary.get("performance", {}).get("degraded", False)
    summary["retrain"] = (
        "started"
        if degraded and os.environ.get("RETRAIN_MODE") == "auto"
        else ("needed (RETRAIN_MODE=on_demand)" if degraded else "not needed")
    )
    if summary["retrain"] == "started":
        run_training_job()
    artifacts.write(
        f"monitoring/{datetime.now(UTC):%Y-%m-%d}/summary.json",
        json.dumps(summary, indent=1, default=str).encode(),
    )
    print(json.dumps(summary, default=str))


if __name__ == "__main__":
    main()
