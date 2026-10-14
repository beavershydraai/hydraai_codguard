"""Completed contact assignments survive lifecycle release for Model 2 learning."""

import pytest

from app.data.orders import final_state, snapshot_row
from app.risk.features import compute_features
from app.risk.jobs.monitor import scored_rows
from app.risk.snapshot import build_table, feature_columns, fit_encodings
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


def _edited_after_assignment():
    doc = _released_order()
    doc["address"] = {
        "raw": "Số 12 đường mẫu, Hà Nội",
        "street": "Số 12 đường mẫu",
        "ward": "Phường mẫu",
        "province": "Hà Nội",
    }
    original_features = compute_features(doc, [], doc["placed_at"], ENC)
    doc["intervention"].update(features=original_features, probability=0.3)
    doc["prepaid_vnd"] = 30000
    doc["address"] = {
        "raw": "Gần chợ, Đà Nẵng",
        "street": None,
        "ward": "Phường mẫu",
        "province": "Đà Nẵng",
    }
    doc["scoring"] = {
        "features": compute_features(doc, [], doc["placed_at"], ENC),
        "probability": 0.1,
    }
    return doc


def test_training_pairs_a_completed_assignment_with_its_original_order_features():
    doc = _edited_after_assignment()
    table = _training_table(doc)
    assert table.loc[0, "cod_amount_vnd"] == 330000
    assert table.loc[0, "address_missing_house_number"] == 0
    assert set(feature_columns(table)) == set(doc["intervention"]["features"])
    for name, value in doc["intervention"]["features"].items():
        assert table.loc[0, name] == value


@pytest.mark.parametrize("current_scoring_missing", [False, True])
def test_monitoring_uses_original_assignment_features_and_probability(current_scoring_missing):
    doc = _edited_after_assignment()
    if current_scoring_missing:
        doc["scoring"] = None
    rows = scored_rows([doc])
    assert len(rows) == 1
    assert rows.loc[0, "cod_amount_vnd"] == 330000
    assert rows.loc[0, "address_missing_house_number"] == 0
    assert rows.loc[0, "probability"] == 0.3
    for name, value in doc["intervention"]["features"].items():
        assert rows.loc[0, name] == value


def test_monitoring_keeps_a_captured_zero_probability():
    doc = _edited_after_assignment()
    doc["intervention"]["probability"] = 0.0
    assert scored_rows([doc]).loc[0, "probability"] == 0.0


def _assignment_with_old_encodings():
    doc = _edited_after_assignment()
    original = doc | {
        "prepaid_vnd": 0,
        "address": {
            "raw": "Số 12 đường mẫu, Hà Nội",
            "street": "Số 12 đường mẫu",
            "ward": "Phường mẫu",
            "province": "Hà Nội",
        },
    }
    original_features = compute_features(
        original, [], original["placed_at"], {"p0": 0.1, "province": {"Hà Nội": 0.2}}
    )
    doc["intervention"].update(province="Hà Nội", features=original_features)
    return doc, original


def test_training_reencodes_frozen_features_with_the_current_training_encodings():
    doc, original = _assignment_with_old_encodings()
    current_enc = {"p0": 0.9, "province": {"Hà Nội": 0.8, "Đà Nẵng": 0.4}}
    label, at = final_state(doc)
    table = build_table([doc], [(doc, label, at)], current_enc)
    assert table.loc[0, "province"] == "Hà Nội"
    assert table.loc[0, "cod_amount_vnd"] == 330000
    assert table.loc[0, "address_missing_house_number"] == 0
    assert table.loc[0, "province_fail_rate_te"] == 0.8
    assert table.loc[0, "phone_fail_rate_smoothed_all"] == 0.9
    serving_features = compute_features(original, [], original["placed_at"], current_enc)
    for name, value in serving_features.items():
        assert table.loc[0, name] == value
    assert doc["intervention"]["features"]["province_fail_rate_te"] == 0.2
    assert doc["intervention"]["features"]["phone_fail_rate_smoothed_all"] == 0.1


def test_training_reencodes_from_frozen_phone_counts_instead_of_new_order_inputs():
    doc, _ = _assignment_with_old_encodings()
    doc["intervention"]["features"].update(phone_outcomes_all=3, phone_failed_all=2)
    label, at = final_state(doc)
    table = build_table([doc], [(doc, label, at)], {"p0": 0.9, "province": {}})
    assert table.loc[0, "phone_outcomes_all"] == 3
    assert table.loc[0, "phone_failed_all"] == 2
    assert table.loc[0, "phone_fail_rate_smoothed_all"] == pytest.approx(0.8125)


def test_encoding_fit_groups_outcomes_by_the_captured_province():
    captured, _ = _assignment_with_old_encodings()
    legacy = orders(n_phones=1)[0] | {
        "order_id": "legacy",
        "address": {"raw": "Địa chỉ mẫu", "province": "Đà Nẵng"},
    }
    enc = fit_encodings([(captured, 1, None), (legacy, 0, None)])
    assert enc["p0"] == 0.5
    assert enc["province"]["Hà Nội"] == pytest.approx(3.5 / 6)
    assert enc["province"]["Đà Nẵng"] == pytest.approx(2.5 / 6)


def test_monitoring_preserves_the_original_feature_encodings():
    doc, _ = _assignment_with_old_encodings()
    rows = scored_rows([doc])
    assert rows.loc[0, "province_fail_rate_te"] == 0.2
    assert rows.loc[0, "phone_fail_rate_smoothed_all"] == 0.1
    assert rows.loc[0, "probability"] == 0.3
