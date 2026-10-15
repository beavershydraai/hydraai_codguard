"""Training job (Cloud Run job `codguard-train`): Firestore → snapshot → features → Model 1 →
evaluate against the current model → promote (docs/diagrams/order-data-flow.png, steps 8–12).

Run: python -m app.risk.jobs.train   (env: FIRESTORE_DATABASE, MODEL_BUCKET or MODEL_DIR)
"""

import io
import json
import pickle
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from app.data import branches
from app.risk import artifacts
from app.risk.backtest import backtest
from app.risk.model import fit_model1, predict1
from app.risk.snapshot import build_table, feature_columns, fit_encodings, labelled


def holdout(table: pd.DataFrame) -> pd.DataFrame:
    """The newest 20 %, never trained on: validation, promotion and the backtest use it."""
    return table.iloc[int(len(table) * 0.8) :]


def _encoded(model: dict, hold: pd.DataFrame) -> pd.DataFrame:
    enc = model["enc"]
    return hold.assign(
        province_fail_rate_te=[enc["province"].get(p, enc["p0"]) for p in hold["province"]]
    )


def _predict(model: dict, hold: pd.DataFrame):
    """Model 1 on held-out rows, with the province encoding that model was trained with."""
    return predict1(model, _encoded(model, hold))


def _metrics(model: dict, hold: pd.DataFrame) -> dict:
    p, y = _predict(model, hold), hold["is_failed"].to_numpy()
    # the 20 % ranked highest: calibrated scores tie a lot, so a quantile cut would take more
    top = np.argsort(-model["clf"].predict_proba(_encoded(model, hold)[model["cols"]])[:, 1])
    top = top[: max(1, int(len(p) * 0.2))]
    return {
        "pr_auc": round(float(average_precision_score(y, p)), 4),
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "lift_top20": round(float(y[top].mean() / y.mean()), 2),
    }


def train(docs: list[dict], now: datetime, current: dict | None):
    """Returns (candidate model, report, table). The newest 20 % is held out from training."""
    rows = labelled(docs, now)
    enc = fit_encodings(rows)
    table = build_table(docs, rows, enc)
    cols = feature_columns(table)
    hold = holdout(table)
    fit = table.iloc[: len(table) - len(hold)]
    version = now.strftime("v%Y%m%d%H%M%S")
    candidate = fit_model1(fit, cols) | {"enc": enc, "version": version}
    report = {
        "version": version,
        "rows": len(table),
        "failure_rate": round(float(table["is_failed"].mean()), 4),
        "candidate": _metrics(candidate, hold),
    }
    if current and not set(current["cols"]) <= set(hold.columns):
        current = None  # the features changed (e.g. a renamed column): nothing to compare against
    if current:
        report["current"] = {"version": current["version"]} | _metrics(current, hold)
    better = not current or report["candidate"]["pr_auc"] > report["current"]["pr_auc"]
    report["promoted"] = bool(better)
    report["validation_pr_auc"] = report["candidate"]["pr_auc"]
    return candidate, report, table


def country_docs(docs: list[dict], code: str) -> list[dict]:
    """Orders taken by a branch of the country; older orders without a branch are left out."""
    return [d for d in docs if branches.branches().get(d.get("branch_id")) == code]


def main() -> None:
    import argparse

    from app.data.store import get_store

    parser = argparse.ArgumentParser()
    parser.add_argument("--country", choices=branches.countries(), help="default: every country")
    args = parser.parse_args()
    docs = get_store().all()
    for code in [args.country] if args.country else branches.countries():
        subset = country_docs(docs, code)
        if not subset:
            print(json.dumps({"country": code, "status": "no orders"}))
            continue
        train_country(subset, code)


def train_country(docs: list[dict], code: str) -> None:
    raw = artifacts.read("latest/model1.pkl", code)
    current = pickle.loads(raw) if raw else None
    now = datetime.now(UTC)
    candidate, report, table = train(docs, now, current)
    report["country"] = code
    version = report["version"]
    served = candidate if report["promoted"] else current  # the model latest/ holds after this run
    hold = holdout(table)
    result = backtest(_predict(served, hold), hold, now, code)
    buf = io.BytesIO()
    table.to_parquet(buf)
    files = {
        "model1.pkl": pickle.dumps(candidate),
        "features.parquet": buf.getvalue(),
        "metrics.json": json.dumps(report, indent=1).encode(),
    }
    for name, data in files.items():
        artifacts.write(f"{version}/{name}", data, code)
        if report["promoted"]:
            artifacts.write(f"latest/{name}", data, code)
    # GET /dashboard/backtest: always for the model now in latest/ (E9.1)
    artifacts.write("latest/backtest.json", json.dumps(result, indent=1).encode(), code)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
