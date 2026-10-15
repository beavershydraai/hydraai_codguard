"""Views of stored order documents for the shop API contract."""

from app.risk.model import FAIL_COST
from app.schemas.enums import HardRule
from app.schemas.orders import OrderDetail, OrderEvent, OrderSummary
from app.schemas.scoring import RiskScore

_ENGINE_HARD_RULES = {
    "hard rule: fully prepaid": HardRule.PREPAID_SKIP,
    "hard rule: invalid phone": HardRule.INVALID_PHONE,
    "hard rule: ≥ 75 % returns": HardRule.HIGH_RETURN_PHONE,
}


def _risk_score(order_id: str, raw: dict) -> RiskScore:
    """Expose scoring inputs only through the API's signal and reason fields."""
    rule = _ENGINE_HARD_RULES.get(raw.get("chosen_by"))
    hard_rules = raw.get("hard_rules", [rule] if rule else [])
    skipped = raw.get("status") == "skipped" or HardRule.PREPAID_SKIP in hard_rules
    return RiskScore(
        id=raw.get("id") or f"scr_{order_id}_{raw['scored_at']}",
        scored_at=raw["scored_at"],
        status="skipped" if skipped else "scored",
        skipped_reason=raw.get("skipped_reason") or (HardRule.PREPAID_SKIP if skipped else None),
        probability=None if skipped else raw.get("probability"),
        risk_score=None if skipped else raw.get("risk_score"),
        tier=None if skipped else raw.get("tier"),
        expected_loss_vnd=None if skipped else raw.get("expected_loss_vnd"),
        failed_delivery_cost_vnd=raw.get("failed_delivery_cost_vnd", FAIL_COST),
        hard_rules=hard_rules,
        top_signals=raw.get("top_signals", []),
        reasons=raw.get("reasons", []),
        model_version=raw.get("model_version"),
    )


def _current_score(doc: dict) -> RiskScore | None:
    return _risk_score(doc["order_id"], doc["scoring"]) if doc.get("scoring") else None


def _total_vnd(doc: dict) -> int:
    return (
        sum(item["quantity"] * item["unit_price_vnd"] for item in doc["items"])
        - doc["discount_vnd"]
        + doc["shipping_fee_vnd"]
    )


def order_summary(doc: dict) -> OrderSummary:
    """Inbox row: the same figures as order_detail, without histories."""
    current = _current_score(doc)
    total = _total_vnd(doc)
    decision = doc.get("decision")
    return OrderSummary(
        **{name: doc[name] for name in _SUMMARY_FIELDS if name in doc},
        id=doc["order_id"],
        total_vnd=total,
        cod_amount_vnd=max(total - doc["prepaid_vnd"], 0),
        tier=current.tier if current else None,
        risk_score=current.risk_score if current else None,
        current_action=decision["action"] if decision else None,
    )


_SUMMARY_FIELDS = (
    "external_id",
    "channel",
    "buyer_name",
    "buyer_phone",
    "is_gift",
    "status",
    "placed_at",
    "updated_at",
)


def order_detail(doc: dict) -> OrderDetail:
    """Current score and every earlier run, without changing the stored document."""
    current = _current_score(doc)
    runs = [_risk_score(doc["order_id"], run) for run in doc.get("score_history", [])]
    if current:
        runs.append(current)
    total = _total_vnd(doc)
    decision = doc.get("decision")
    fields = {
        name: doc[name]
        for name in (
            "external_id",
            "channel",
            "buyer_name",
            "buyer_phone",
            "is_gift",
            "recipient_name",
            "recipient_phone",
            "address",
            "items",
            "shipping_fee_vnd",
            "discount_vnd",
            "prepaid_vnd",
            "note",
            "status",
            "placed_at",
            "updated_at",
        )
        if name in doc
    }
    return OrderDetail(
        **fields,
        id=doc["order_id"],
        total_vnd=total,
        cod_amount_vnd=max(total - doc["prepaid_vnd"], 0),
        tier=current.tier if current else None,
        risk_score=current.risk_score if current else None,
        current_action=decision["action"] if decision else None,
        current_score=current,
        score_history=sorted(runs, key=lambda run: run.scored_at, reverse=True),
        decision=decision,
        contacts=doc.get("contacts", []),
        calls=doc.get("calls", []),
        timeline=sorted(
            (OrderEvent.model_validate(event) for event in doc.get("timeline", [])),
            key=lambda event: event.at,
            reverse=True,
        ),
        allowed_overrides=doc.get("allowed_overrides", []),
    )
