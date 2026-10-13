"""Independent lifecycle regressions for payment edits and concurrent outcomes."""

from copy import deepcopy
from datetime import timedelta

import pytest

from app.api.errors import ApiError
from app.data.orders import order_document
from app.data.store import OrderStore
from app.decision import lifecycle
from app.risk import engine
from app.schemas.enums import BuyerAction
from app.schemas.orders import OrderCreate, OrderUpdate
from tests.test_intake import FakeStore
from tests.test_lifecycle import scored_fields
from tests.test_order_store import MemoryClient
from tests.test_policy import NOW


@pytest.fixture
def edge_store(monkeypatch):
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    store = FakeStore()
    order = OrderCreate.model_validate(OrderCreate.model_config["json_schema_extra"]["examples"][0])
    store.create(
        order_document(order, order_id="ord_edge", shop_id="shop_a", phone_key=b"test-key", now=NOW)
    )
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields())
    return store


@pytest.mark.parametrize("new_tier", [None, "medium", "high"])
def test_paid_deposit_releases_after_an_unavailable_or_contact_requiring_rescore(
    edge_store, monkeypatch, new_tier
):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("very_high", "deposit"))
    lifecycle.score_order(edge_store, edge_store.docs["ord_edge"], NOW)

    def rescore(doc, history):
        if new_tier is None:
            return None
        return scored_fields(new_tier, "link" if new_tier == "medium" else "call")

    monkeypatch.setattr(engine, "score", rescore)
    result = lifecycle.edit_order(
        edge_store, "ord_edge", "shop_a", OrderUpdate(prepaid_vnd=30000), NOW
    )
    assert result["prepaid_vnd"] == 30000
    assert result["status"] == "cleared_to_ship"
    assert result["confirmation"] is None
    assert result["decision"]["action"] == "ship_now"
    assert result["decision"]["next_action"] is None
    assert result["contact_action"] == "none"


def test_paid_deposit_edit_preserves_a_staff_decision_and_its_status(edge_store, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("very_high", "deposit"))
    lifecycle.score_order(edge_store, edge_store.docs["ord_edge"], NOW)
    doc = edge_store.docs["ord_edge"]
    doc["decision"]["decided_by"] = "staff"
    previous_decision = deepcopy(doc["decision"])
    result = lifecycle.edit_order(
        edge_store, "ord_edge", "shop_a", OrderUpdate(prepaid_vnd=30000), NOW
    )
    assert result["status"] == "awaiting_deposit"
    assert result["decision"] == previous_decision
    assert result["prepaid_vnd"] == 30000
    assert len(result["score_history"]) == 1


def test_confirmed_order_with_a_new_invalid_phone_is_held_without_contact(edge_store, monkeypatch):
    lifecycle.score_order(edge_store, edge_store.docs["ord_edge"], NOW)
    lifecycle.apply_buyer_response(edge_store, "ord_edge", BuyerAction.CONFIRM, None, NOW)
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "hold"))
    result = lifecycle.edit_order(
        edge_store, "ord_edge", "shop_a", OrderUpdate(buyer_phone="+8400000000"), NOW
    )
    assert result["confirmation"] == {"at": NOW, "via": "link"}
    assert result["status"] == "pending_review"
    assert result["decision"]["action"] == "hold_for_review"
    assert result["decision"]["next_action"] is None
    assert result["contact_action"] == "hold"


def test_edit_retry_observes_concurrent_shipping_and_does_not_commit_the_edit(
    edge_store, monkeypatch
):
    lifecycle.score_order(edge_store, edge_store.docs["ord_edge"], NOW)

    def ship(docs):
        docs["ord_edge"]["status"] = "shipped"

    client = MemoryClient(edge_store.docs, conflict=ship)
    store = OrderStore(client)
    monkeypatch.setattr(store, "history", lambda phone_hash, before: [])
    with pytest.raises(ApiError) as error:
        lifecycle.edit_order(store, "ord_edge", "shop_a", OrderUpdate(note="Địa chỉ mẫu"), NOW)
    assert error.value.problem.code == "order_not_editable"
    assert client.docs["ord_edge"]["status"] == "shipped"
    assert client.docs["ord_edge"]["note"] is None
    assert client.docs["ord_edge"]["score_history"] == []


def test_edit_retry_preserves_a_concurrent_confirmation_without_duplicate_scoring_history(
    edge_store, monkeypatch
):
    lifecycle.score_order(edge_store, edge_store.docs["ord_edge"], NOW)
    confirmed_at = NOW + timedelta(minutes=1)

    def confirm(docs):
        doc = docs["ord_edge"]
        doc["confirmation"] = {"at": confirmed_at, "via": "call"}
        doc["status"] = "cleared_to_ship"

    client = MemoryClient(edge_store.docs, conflict=confirm)
    store = OrderStore(client)
    monkeypatch.setattr(store, "history", lambda phone_hash, before: [])
    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    result = lifecycle.edit_order(
        store, "ord_edge", "shop_a", OrderUpdate(note="Ghi chú mẫu"), NOW + timedelta(minutes=2)
    )
    assert result["confirmation"] == {"at": confirmed_at, "via": "call"}
    assert result["status"] == "cleared_to_ship"
    assert result["decision"]["action"] == "ship_now"
    assert result["decision"]["next_action"] is None
    assert result["contact_action"] == "none"
    assert [score["tier"] for score in result["score_history"]] == ["low"]
    assert [event["type"] for event in result["timeline"]].count("edited") == 1
