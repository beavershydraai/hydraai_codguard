"""Training table from order documents: one row per labelled order, features as of placed_at
(tasks/E2.3-risk-features.md: label, point-in-time rules, encodings)."""

from collections import defaultdict
from datetime import timedelta

import pandas as pd

from app.data.orders import final_state
from app.risk.features import compute_features, upgrade
from app.risk.model import KEY_COLUMNS

MATURITY = timedelta(days=14)  # E2.3 rule 5: outcomes of the last 14 days may still be missing
M_SMOOTH = 5


def labelled(docs: list[dict], now) -> list[tuple[dict, int, object]]:
    """(doc, label, when known) for orders old enough and with a final state known before now."""
    out = []
    for d in docs:
        label, at = final_state(d)
        if label is not None and at < now and d["placed_at"] < now - MATURITY:
            out.append((d, label, at))
    return out


def fit_encodings(rows: list[tuple[dict, int, object]]) -> dict:
    """Smoothed failure rate per province (E2.3 rule 7), shipped with the model."""
    p0 = sum(lbl for _, lbl, _ in rows) / len(rows)
    by = defaultdict(lambda: [0, 0])
    for d, lbl, _ in rows:
        assignment = d.get("intervention") or {}
        province = assignment.get("province", d["address"].get("province"))
        by[province][0] += lbl
        by[province][1] += 1
    return {
        "p0": p0,
        "province": {k: (f + M_SMOOTH * p0) / (n + M_SMOOTH) for k, (f, n) in by.items()},
    }


def build_table(docs: list[dict], rows, enc: dict) -> pd.DataFrame:
    by_phone = defaultdict(list)
    for d in docs:
        if d.get("buyer_phone_hash"):
            by_phone[d["buyer_phone_hash"]].append(d)
    table = []
    for d, label, at in rows:
        history = by_phone.get(d.get("buyer_phone_hash"), [])
        assignment = d.get("intervention") or d
        province = assignment.get("province", d["address"].get("province"))
        frozen = assignment.get("features")
        if frozen:
            features = upgrade(frozen)
            features["province_fail_rate_te"] = enc["province"].get(province, enc["p0"])
            features["phone_fail_rate_smoothed_all"] = (
                features["phone_failed_all"] + M_SMOOTH * enc["p0"]
            ) / (features["phone_outcomes_all"] + M_SMOOTH)
        else:
            features = compute_features(d, history, d["placed_at"], enc)
        table.append(
            {
                "order_id": d["order_id"],
                "placed_at": d["placed_at"],
                "final_at": at,
                "province": province,
                "tier": assignment.get("tier"),
                "contact_action": assignment.get("contact_action", "none"),
                "action_probability": assignment.get("action_probability", 1.0),
                "random_slice": bool(assignment.get("random_slice")),
                "is_failed": label,
                **features,
            }
        )
    df = pd.DataFrame(table)
    return df.sort_values("placed_at").reset_index(drop=True)


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in KEY_COLUMNS]
