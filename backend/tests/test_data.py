from datetime import UTC, datetime

import pytest

from app.data.orders import (
    delivery_fields,
    order_document,
    snapshot_row,
    to_utc,
    training_label,
)
from app.data.phone import decrypt_phone, phone_hash, to_e164
from app.schemas.delivery import DeliveryOutcome
from app.schemas.orders import OrderCreate, OrderEvent

KEY = b"test-key"
NOW = datetime(2026, 10, 12, 1, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "raw", ["0000000001", "000 000 0001", "000.000.0001", "84000000001", "+84 000 000 001"]
)
def test_to_e164_accepts_common_formats(raw):
    assert to_e164(raw) == "+84000000001"


@pytest.mark.parametrize("raw", ["", "12345", "000000001", "+1 000 000 0001", "0000000000001"])
def test_to_e164_rejects_wrong_shapes(raw):
    assert to_e164(raw) is None


@pytest.mark.parametrize(
    ("raw", "code", "e164"),
    [
        ("+84 000 000 001", "65", "+84000000001"),  # a Vietnamese buyer of the Singapore branch
        ("+65 0000 0001", "84", "+6500000001"),
        ("+63 000 000 0001", "65", "+630000000001"),
        ("84000000001", "65", None),  # without "+" the number belongs to the order's country
        ("+84 000 001", "65", None),  # too short for Vietnam
        ("+1 000 000 0001", "65", None),  # a country the shop does not serve
    ],
)
def test_a_number_in_international_form_may_be_of_another_country(raw, code, e164):
    assert to_e164(raw, code) == e164


def test_phone_hash_is_stable_and_keyed():
    assert phone_hash("+84000000001", KEY) == phone_hash("+84000000001", KEY)
    assert phone_hash("+84000000001", KEY) != phone_hash("+84000000002", KEY)
    assert phone_hash("+84000000001", KEY) != phone_hash("+84000000001", b"other-key")


def test_to_utc_treats_naive_time_as_vietnam_time():
    assert to_utc(datetime(2026, 10, 9, 10, 15)) == datetime(2026, 10, 9, 3, 15, tzinfo=UTC)


def _order(**changes) -> OrderCreate:
    example = OrderCreate.model_config["json_schema_extra"]["examples"][0]
    return OrderCreate.model_validate({**example, **changes})


def _doc(**changes) -> dict:
    return order_document(
        _order(**changes), order_id="ord_01", shop_id="shop_01", phone_key=KEY, now=NOW
    )


def test_order_document_normalises_and_hashes_phones():
    doc = _doc(buyer_phone="0000000001", recipient_phone="+84000000002")
    assert decrypt_phone(doc["buyer_phone"]) == "+84000000001"
    # Stored encrypted, with a fresh nonce: the same number never gives the same ciphertext.
    assert doc["buyer_phone"].startswith("enc:v1:") and "000000001" not in doc["buyer_phone"]
    assert doc["buyer_phone"] != _doc(buyer_phone="0000000001")["buyer_phone"]
    assert decrypt_phone(doc["recipient_phone"]) == "+84000000002"
    assert doc["buyer_phone_hash"] == phone_hash("+84000000001", KEY)
    assert doc["recipient_phone_hash"] == phone_hash("+84000000002", KEY)
    assert (doc["order_id"], doc["shop_id"], doc["status"]) == ("ord_01", "shop_01", "new")
    assert doc["placed_at"] == datetime(2026, 10, 9, 3, 15, tzinfo=UTC)
    assert doc["channel"] == "facebook"
    assert doc["scoring"] is None and doc["delivery"] is None


def test_order_document_keeps_an_invalid_phone_without_hash():
    doc = _doc(buyer_phone="123456789")
    assert decrypt_phone(doc["buyer_phone"]) == "123456789"
    assert doc["buyer_phone_hash"] is None


def test_order_document_initialises_lifecycle_state():
    doc = _doc()
    assert doc["decision"] is None
    assert doc["score_history"] == []
    assert doc["confirmation"] is None
    assert doc["cancel"] is None
    assert len(doc["timeline"]) == 1
    event = OrderEvent.model_validate(doc["timeline"][0])
    assert (event.type, event.at, event.actor) == ("created", NOW, "system")


@pytest.mark.parametrize(
    ("result", "label"),
    [
        ("delivered", 0),
        ("refused", 1),
        ("unreachable", 1),
        ("carrier_issue", None),
        ("shop_issue", None),
        (None, None),
    ],
)
def test_training_label_counts_buyer_failures_only(result, label):
    assert training_label(result) == label


def _delivered(result: str) -> dict:
    outcome = DeliveryOutcome(
        order_id="ord_01", carrier="ghn", result=result, occurred_at="2026-10-12T15:30:00+07:00"
    )
    return {**_doc(), **delivery_fields(outcome, now=NOW)}


def test_snapshot_row_is_flat_labelled_and_has_no_personal_data():
    row = snapshot_row(_delivered("refused"))
    assert row["is_failed"] == 1
    assert row["address_ward"] == "Phường Láng"
    assert row["delivery_occurred_at"] == datetime(2026, 10, 12, 8, 30, tzinfo=UTC)
    for field in ("buyer_name", "buyer_phone", "recipient_phone", "scoring", "address"):
        assert field not in row
    assert row["buyer_phone_hash"]


def test_snapshot_row_drops_orders_without_a_buyer_label():
    assert snapshot_row(_doc()) is None
    assert snapshot_row(_delivered("carrier_issue")) is None


def test_snapshot_row_excludes_lifecycle_outcomes_but_keeps_the_label():
    doc = {
        **_delivered("delivered"),
        "status": "delivered",
        "decision": {"action": "ship_now"},
        "score_history": [{"probability": 0.9}],
        "confirmation": {"at": NOW, "via": "link"},
        "cancel": None,
        "attempts": {"ai_call": 2},
    }
    row = snapshot_row(doc)
    assert row["is_failed"] == 0
    for field in (
        "status",
        "decision",
        "score_history",
        "timeline",
        "confirmation",
        "cancel",
        "attempts",
    ):
        assert field not in row


def test_snapshot_row_labels_a_buyer_cancellation_without_exposing_it():
    doc = {**_doc(), "cancel": {"reason": "not_ordered", "at": NOW, "by": "buyer"}}
    row = snapshot_row(doc)
    assert row["is_failed"] == 1
    assert "cancel" not in row


@pytest.mark.parametrize(
    ("raw", "code", "e164"),
    [
        ("+65 0000 0042", "65", "+6500000042"),
        ("00000042", "65", "+6500000042"),
        ("+63 000 000 0066", "63", "+630000000066"),
        ("0000 000 0066", "63", "+630000000066"),
    ],
)
def test_to_e164_accepts_singapore_and_philippine_numbers(raw, code, e164):
    assert to_e164(raw, code) == e164


def test_a_national_number_of_another_country_is_invalid_for_the_branch():
    assert to_e164("0000 000 001", "65") is None  # a Vietnamese national form, on a SG order
    assert to_e164("6500000042", "84") is None
