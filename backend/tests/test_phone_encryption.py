"""Phones are stored encrypted and shown in full: the order API, calls, edits and the migration of
phones stored before encryption."""

from app.calls import jobs
from app.calls.service import stored_job
from app.data.encrypt_phones import changes
from app.data.phone import decrypt_phone, encrypt_phone
from app.decision import lifecycle
from app.decision.views import order_detail, order_summary
from app.schemas.orders import OrderUpdate
from tests.test_calls import calls, order  # noqa: F401 (pytest fixture)
from tests.test_lifecycle import store  # noqa: F401 (pytest fixture)
from tests.test_pipeline import pipe  # noqa: F401 (pytest fixture)
from tests.test_policy import NOW


def test_a_phone_round_trips_and_plain_values_pass_through():
    sealed = encrypt_phone("+84000000001")
    assert sealed.startswith("enc:v1:") and decrypt_phone(sealed) == "+84000000001"
    assert encrypt_phone(sealed) == sealed  # never encrypted twice
    assert decrypt_phone("+84000000001") == "+84000000001"  # stored before encryption
    assert encrypt_phone(None) is None and decrypt_phone(None) is None


def test_the_shop_sees_the_full_number(store):  # noqa: F811
    doc = store.get("ord_test")
    assert doc["buyer_phone"].startswith("enc:v1:")
    assert order_summary(doc).buyer_phone == "+84000000001"
    assert order_detail(doc).buyer_phone == "+84000000001"


def test_an_edit_with_the_same_number_changes_nothing(store):  # noqa: F811
    before = store.get("ord_test")
    after = lifecycle.edit_order(
        store, "ord_test", "shop_a", OrderUpdate(buyer_phone="0000000001"), NOW, actor="a"
    )
    assert after["buyer_phone"] == before["buyer_phone"]  # same ciphertext: not rewritten
    assert after["timeline"] == before["timeline"]


def test_calls_dial_the_real_number_but_store_it_encrypted(calls, monkeypatch):  # noqa: F811
    monkeypatch.delenv("CALL_TARGET_OVERRIDE")
    monkeypatch.setenv("CALL_DIAL_BUYERS", "on")
    doc = order(calls)
    job = jobs.build_job(doc, "call_1", 1, NOW)
    assert job.target.address == "+84000000001"  # what the controller dials
    kept = stored_job(job)["target"]["address"]
    assert kept.startswith("enc:v1:") and decrypt_phone(kept) == "+84000000001"


def test_the_migration_encrypts_plain_phones_once():
    old = {"buyer_phone": "+84000000001", "recipient_phone": None}
    update = changes("orders", old)
    assert (
        list(update) == ["buyer_phone"] and decrypt_phone(update["buyer_phone"]) == "+84000000001"
    )
    assert changes("orders", {"buyer_phone": update["buyer_phone"]}) == {}
    call = {"job": {"target": {"kind": "pstn", "address": "+84000000001"}}}
    assert list(changes("calls", call)) == ["job.target.address"]
    assert changes("calls", {"job": {"target": {"kind": "sip", "address": "sip:6001"}}}) == {}
