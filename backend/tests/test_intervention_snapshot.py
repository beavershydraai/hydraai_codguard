"""Completed contact assignments survive lifecycle release for Model 2 learning."""

import pytest

from app.data.orders import final_state, snapshot_row
from app.risk.jobs.monitor import scored_rows
from app.risk.snapshot import build_table, feature_columns
from tests.risk_data import orders

ENC = {"p0": 0.1, "province": {}}


def _released_order():
    return orders(n_phones=1)[0] | {
        "status": "cleared_to_ship",
        "tier": "low",
        "contact_action": "none",
        "random_slice": False,
        "action_probability": 1.0,
        "intervention": {
            "tier": "high",
            "contact_action": "call",
            "random_slice": True,
            "action_probability": 0.5,
        },
        "scoring": {"probability": 0.1, "features": {"cod_amount_vnd": 330000}},
    }


def _training_table(doc):
    label, at = final_state(doc)
    return build_table([doc], [(doc, label, at)], ENC)


def test_training_keeps_the_completed_randomized_contact_after_release():
    table = _training_table(_released_order())
    row = table.iloc[0]
    assert row["tier"] == "high"
    assert row["contact_action"] == "call"
    assert bool(row["random_slice"]) is True
    assert row["action_probability"] == 0.5
    assert row["cod_amount_vnd"] == 330000
    assert "intervention" not in table.columns
    assert {"tier", "contact_action", "random_slice", "action_probability"}.isdisjoint(
        feature_columns(table)
    )


def test_monitoring_keeps_the_completed_randomized_contact_after_release():
    rows = scored_rows([_released_order()])
    assert rows.loc[0, "tier"] == "high"
    assert rows.loc[0, "contact_action"] == "call"
    assert bool(rows.loc[0, "random_slice"]) is True
    assert rows.loc[0, "cod_amount_vnd"] == 330000
    assert "intervention" not in rows.columns


@pytest.mark.parametrize("explicit_null", [False, True])
def test_historical_documents_without_interventions_keep_existing_training_metadata(explicit_null):
    doc = orders(n_phones=1)[0] | {
        "tier": "medium",
        "contact_action": "link",
        "random_slice": True,
        "action_probability": 1 / 3,
        "scoring": {"probability": 0.2, "features": {"cod_amount_vnd": 330000}},
    }
    if explicit_null:
        doc["intervention"] = None
    table = _training_table(doc)
    assert table.loc[0, "tier"] == "medium"
    assert table.loc[0, "contact_action"] == "link"
    assert bool(table.loc[0, "random_slice"]) is True
    assert table.loc[0, "action_probability"] == pytest.approx(1 / 3)
    monitoring = scored_rows([doc])
    assert monitoring.loc[0, "tier"] == "medium"
    assert monitoring.loc[0, "contact_action"] == "link"
    assert bool(monitoring.loc[0, "random_slice"]) is True


def test_flat_snapshot_excludes_the_intervention_record():
    row = snapshot_row(_released_order())
    assert row["is_failed"] in {0, 1}
    assert "intervention" not in row
