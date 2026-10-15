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

from app.risk import artifacts
from app.risk.model import fit_model1, predict1
from app.risk.snapshot import build_table, feature_columns, fit_encodings, labelled


def _metrics(model: dict, hold: pd.DataFrame) -> dict:
    X = hold.assign(
        province_fail_rate_te=[
            model["enc"]["province"].get(p, model["enc"]["p0"]) for p in hold["province"]
        ]
    )
    p, y = predict1(model, X), hold["is_failed"].to_numpy()
    top = p >= np.quantile(p, 0.8)
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
    cut = int(len(table) * 0.8)
    fit, hold = table.iloc[:cut], table.iloc[cut:]
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


def main() -> None:
    from app.data.store import get_store

    raw = artifacts.read("latest/model1.pkl")
    current = pickle.loads(raw) if raw else None
    candidate, report, table = train(get_store().all(), datetime.now(UTC), current)
    version = report["version"]
    buf = io.BytesIO()
    table.to_parquet(buf)
    files = {
        "model1.pkl": pickle.dumps(candidate),
        "features.parquet": buf.getvalue(),
        "metrics.json": json.dumps(report, indent=1).encode(),
    }
    for name, data in files.items():
        artifacts.write(f"{version}/{name}", data)
        if report["promoted"]:
            artifacts.write(f"latest/{name}", data)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
