"""Views of stored order documents for the shop API contract."""

from app.data import branches
from app.data.phone import decrypt_phone
from app.decision.lifecycle import allowed_overrides
from app.schemas.enums import (
    CallOutcome,
    ContactBlockReason,
    HardRule,
    OrderStatus,
    ReviewReason,
)
from app.schemas.orders import OrderDetail, OrderEvent, OrderSummary
from app.schemas.scoring import RiskScore

_ENGINE_HARD_RULES = {
    "hard rule: fully prepaid": HardRule.PREPAID_SKIP,
    "hard rule: invalid phone": HardRule.INVALID_PHONE,
    "hard rule: ≥ 75 % returns": HardRule.HIGH_RETURN_PHONE,
}


def _hard_rules(raw: dict) -> list[HardRule]:
    rule = _ENGINE_HARD_RULES.get(raw.get("chosen_by"))
    return raw.get("hard_rules", [rule] if rule else [])


# The order's first contact (`intervention`) when the buyer never answered it.
_NO_ANSWER = {
    "link": ReviewReason.NO_ANSWER_LINK,
    "call": ReviewReason.NO_ANSWER_CALL,
    "deposit": ReviewReason.DEPOSIT_UNPAID,
}


def review_reason(doc: dict) -> ReviewReason | None:
    """Why the order waits in Pending review, from what is stored on it: the decision, the hard
    rule, the last AI call and the contacts made. Null for an order in any other status."""
    if doc.get("status") != OrderStatus.PENDING_REVIEW:
        return None
    decision = doc.get("decision") or {}
    if decision.get("suggested_action"):
        return ReviewReason.SUGGESTED
    if decision.get("decided_by") == "staff":
        return ReviewReason.STAFF
    if (doc.get("scoring") or {}).get("chosen_by") == "hard rule: invalid phone":
        return ReviewReason.INVALID_PHONE
    if ContactBlockReason.ATTEMPTS_EXHAUSTED in (decision.get("block_reasons") or []):
        return ReviewReason.ATTEMPTS_USED
    calls = doc.get("calls") or []
    outcome = calls[-1].get("outcome") if calls else None
    if outcome == CallOutcome.UNCLEAR:
        return ReviewReason.CALL_UNCLEAR
    if outcome == CallOutcome.EDITED:  # an edited call that left the order here changed items
        return ReviewReason.ITEMS_CHANGED
    if outcome == CallOutcome.WRONG_PERSON:
        return ReviewReason.WRONG_PERSON
    if (doc.get("attempts") or {}).get("ai_call"):  # the last contact was an AI call
        return ReviewReason.NO_ANSWER_CALL
    first = (doc.get("intervention") or {}).get("contact_action")
    return _NO_ANSWER.get(first, ReviewReason.OTHER)


def contact_summary(doc: dict) -> str | None:
    """The summary of the latest AI call that has one."""
    calls = reversed(doc.get("calls") or [])
    return next((c["summary_vi"] for c in calls if c.get("summary_vi")), None)


def _review_fields(doc: dict) -> dict:
    return {
        "review_reason": review_reason(doc),
        "hard_rules": _hard_rules(doc.get("scoring") or {}),
        "contact_summary": contact_summary(doc),
    }


def _risk_score(order_id: str, raw: dict, fail_cost: int) -> RiskScore:
    """Expose scoring inputs only through the API's signal and reason fields."""
    hard_rules = _hard_rules(raw)
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
        failed_delivery_cost_vnd=raw.get("failed_delivery_cost_vnd", fail_cost),
        hard_rules=hard_rules,
        top_signals=raw.get("top_signals", []),
        reasons=raw.get("reasons", []),
        model_version=raw.get("model_version"),
    )


def _fail_cost(doc: dict) -> int:
    """The cost the latest score used: the shop's own (E7.1) or its country's default."""
    stored = (doc.get("scoring") or {}).get("failed_delivery_cost_vnd")
    return stored or branches.country_of(doc).costs["failed_delivery"]


def _current_score(doc: dict) -> RiskScore | None:
    if not doc.get("scoring"):
        return None
    return _risk_score(doc["order_id"], doc["scoring"], _fail_cost(doc))


def _total_vnd(doc: dict) -> int:
    return (
        sum(item["quantity"] * item["unit_price_vnd"] for item in doc["items"])
        - doc["discount_vnd"]
        + doc["shipping_fee_vnd"]
    )


def _readable(doc: dict) -> dict:
    """The order with its phones decrypted: stored encrypted, shown in full to the shop."""
    phones = {k: decrypt_phone(doc.get(k)) for k in ("buyer_phone", "recipient_phone") if k in doc}
    return doc | phones


def order_summary(doc: dict) -> OrderSummary:
    """Inbox row: the same figures as order_detail, without histories."""
    doc = _readable(doc)
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
        suggested_action=(decision or {}).get("suggested_action"),
        **_review_fields(doc),
    )


_SUMMARY_FIELDS = (
    "external_id",
    "branch_id",
    "country",
    "currency",
    "channel",
    "buyer_name",
    "buyer_phone",
    "is_gift",
    "status",
    "placed_at",
    "updated_at",
)


# What order_summary reads: the inbox loads only these fields of every order.
SUMMARY_PROJECTION = (
    "order_id",
    *_SUMMARY_FIELDS,
    "items",
    "discount_vnd",
    "shipping_fee_vnd",
    "prepaid_vnd",
    "decision",
    "calls",
    "attempts",
    "intervention.contact_action",
    *(
        f"scoring.{name}"
        for name in (
            "id",
            "scored_at",
            "status",
            "skipped_reason",
            "probability",
            "risk_score",
            "tier",
            "expected_loss_vnd",
            "failed_delivery_cost_vnd",
            "chosen_by",
            "hard_rules",
        )
    ),
)


def order_detail(doc: dict) -> OrderDetail:
    """Current score and every earlier run, without changing the stored document."""
    doc = _readable(doc)
    current = _current_score(doc)
    runs = [
        _risk_score(doc["order_id"], run, _fail_cost(doc)) for run in doc.get("score_history", [])
    ]
    if current:
        runs.append(current)
    total = _total_vnd(doc)
    decision = doc.get("decision")
    fields = {
        name: doc[name]
        for name in (
            "external_id",
            "branch_id",
            "country",
            "currency",
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
        suggested_action=(decision or {}).get("suggested_action"),
        **_review_fields(doc),
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
        allowed_overrides=allowed_overrides(doc),
    )
