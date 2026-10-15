"""Order-detail API values derived from the stored order and scoring runs."""

from datetime import UTC, datetime, timedelta

import pytest

from app.data.orders import order_document
from app.decision.views import order_detail
from app.schemas.enums import DecisionAction, HardRule, OrderStatus, RiskTier
from app.schemas.orders import OrderCreate

NOW = datetime(2026, 10, 13, 3, tzinfo=UTC)


def document() -> dict:
    order = OrderCreate(
        channel="website",
        buyer_name="Demo buyer",
        buyer_phone="+84000000001",
        address={"raw": "Số 1 đường mẫu, phường mẫu, tỉnh mẫu"},
        items=[{"name": "Sample product", "quantity": 2, "unit_price_vnd": 150_000}],
        discount_vnd=20_000,
        shipping_fee_vnd=30_000,
        prepaid_vnd=50_000,
        placed_at=NOW,
    )
    return order_document(
        order, order_id="ord_demo", shop_id="shop_demo", phone_key=b"demo-key", now=NOW
    )


def scoring(at: datetime, probability: float, tier: str, chosen_by="tier rule") -> dict:
    return {
        "scored_at": at,
        "probability": probability,
        "risk_score": round(probability * 100),
        "tier": tier,
        "expected_loss_vnd": round(probability * 60_000),
        "chosen_by": chosen_by,
        "features": {"cod_amount_vnd": 260_000},
        "model_version": "demo-v1",
    }


def test_order_detail_exposes_current_and_prior_scores_newest_first():
    doc = document()
    doc |= {
        "status": "awaiting_confirmation",
        "scoring": scoring(NOW + timedelta(minutes=3), 0.25, "high"),
        "score_history": [
            scoring(NOW + timedelta(minutes=1), 0.05, "low"),
            scoring(NOW + timedelta(minutes=2), 0.12, "medium"),
        ],
        "decision": {
            "decided_at": NOW + timedelta(minutes=3),
            "action": "ai_call",
            "policy_version": 2,
            "expected_loss_vnd": 15_000,
            "contact_cost_vnd": 1_500,
        },
    }

    detail = order_detail(doc)

    assert detail.id == "ord_demo"
    assert detail.total_vnd == 310_000
    assert detail.cod_amount_vnd == 260_000
    assert detail.status == OrderStatus.AWAITING_CONFIRMATION
    assert detail.tier == RiskTier.HIGH
    assert detail.risk_score == 25
    assert detail.current_action == DecisionAction.AI_CALL
    assert detail.decision.policy_version == 2
    assert [run.risk_score for run in detail.score_history] == [25, 12, 5]
    assert detail.current_score == detail.score_history[0]
    assert len({run.id for run in detail.score_history}) == 3
    assert detail.current_score.id == order_detail(doc).current_score.id
    assert detail.current_score.failed_delivery_cost_vnd == 60_000
    assert detail.current_score.model_version == "demo-v1"
    assert detail.current_score.top_signals == []
    assert detail.current_score.reasons == []
    assert detail.contacts == []
    assert detail.calls == []
    assert "features" not in detail.current_score.model_dump()


def test_unscored_order_has_no_risk_or_action_and_clamps_cod_at_zero():
    doc = document()
    doc["prepaid_vnd"] = 400_000

    detail = order_detail(doc)

    assert detail.status == OrderStatus.NEW
    assert detail.cod_amount_vnd == 0
    assert detail.current_score is None
    assert detail.score_history == []
    assert detail.risk_score is None
    assert detail.tier is None
    assert detail.current_action is None
    assert detail.decision is None


@pytest.mark.parametrize(
    ("chosen_by", "tier", "rule"),
    [
        ("hard rule: invalid phone", "high", HardRule.INVALID_PHONE),
        ("hard rule: ≥ 75 % returns", "very_high", HardRule.HIGH_RETURN_PHONE),
    ],
)
def test_engine_hard_rule_is_visible_without_exposing_internal_fields(chosen_by, tier, rule):
    doc = document()
    doc["scoring"] = scoring(NOW, 0.25, tier, chosen_by)

    detail = order_detail(doc)

    assert detail.current_score.status == "scored"
    assert detail.current_score.hard_rules == [rule]
    assert detail.current_score.skipped_reason is None


def test_fully_prepaid_score_is_marked_skipped():
    doc = document()
    doc["scoring"] = scoring(NOW, 0.25, None, "hard rule: fully prepaid")

    detail = order_detail(doc)

    assert detail.current_score.status == "skipped"
    assert detail.current_score.skipped_reason == HardRule.PREPAID_SKIP
    assert detail.current_score.hard_rules == [HardRule.PREPAID_SKIP]
    assert detail.current_score.tier is None
    assert detail.risk_score is None


def test_detail_preserves_existing_api_score_fields_and_timeline_order():
    doc = document()
    doc["scoring"] = {
        **scoring(NOW, 0.25, "high"),
        "id": "scr_saved",
        "failed_delivery_cost_vnd": 70_000,
        "hard_rules": ["invalid_phone"],
        "top_signals": [
            {
                "key": "address_missing_house_number",
                "group": "address_quality",
                "label_vi": "Address missing a house number",
                "value": True,
                "contribution": 0.07,
            }
        ],
        "reasons": [
            {
                "text_vi": "The address is missing a house number.",
                "signal_keys": ["address_missing_house_number"],
            }
        ],
    }
    doc["timeline"] = [
        {"at": NOW, "type": "created", "actor": "system", "message_vi": "Order created."},
        {
            "at": NOW + timedelta(minutes=1),
            "type": "scored",
            "actor": "system",
            "message_vi": "Order scored.",
        },
    ]

    detail = order_detail(doc)

    assert detail.current_score.id == "scr_saved"
    assert detail.current_score.failed_delivery_cost_vnd == 70_000
    assert detail.current_score.hard_rules == [HardRule.INVALID_PHONE]
    assert detail.current_score.top_signals[0].key == "address_missing_house_number"
    assert detail.current_score.reasons[0].signal_keys == ["address_missing_house_number"]
    assert [event.type for event in detail.timeline] == ["scored", "created"]
