"""Checks the model's record_call_outcome call against the call's orders and turns it into the
fields of a CallResult. See docs/gemini-live.md, section "The outcome tool"."""

from dataclasses import dataclass, field

from app.schemas.calls import CallChange
from app.schemas.enums import CallChangeField, CallOutcome
from app.schemas.telephony import CallJob

MODEL_OUTCOMES = ("CONFIRMED", "EDITED", "CANCELLED", "NOT_ORDERED", "WRONG_PERSON", "UNCLEAR")
ITEM_FIELDS = (CallChangeField.ITEM_VARIANT, CallChangeField.ITEM_QUANTITY)


class OutcomeError(ValueError):
    """The call is invalid; the message tells the model how to fix it."""


@dataclass
class Decision:
    outcome: CallOutcome
    summary: str
    changes: list[CallChange] = field(default_factory=list)
    cancel_reason: str | None = None
    human_callback_requested: bool = False
    buyer_requests: str | None = None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_outcome(args: dict, job: CallJob) -> Decision:
    outcome = _text(args.get("outcome")).upper()
    if outcome not in MODEL_OUTCOMES:
        raise OutcomeError(f"outcome must be one of {', '.join(MODEL_OUTCOMES)}. Call again.")
    summary = _text(args.get("summary"))
    if not summary:
        raise OutcomeError("summary is empty. Add one or two sentences on what the buyer said.")
    raw_changes = args.get("changes") or []
    if not isinstance(raw_changes, list):
        raise OutcomeError("changes must be a list.")
    if outcome == "EDITED" and not raw_changes:
        raise OutcomeError(
            "EDITED needs at least one entry in changes. Add the changes you read "
            "back, then call again."
        )
    if outcome != "EDITED" and raw_changes:
        raise OutcomeError(
            f"{outcome} takes no changes. Leave changes empty, or use EDITED if "
            "the buyer confirmed after a change."
        )

    orders = {order.ref: order for order in job.orders}
    changes = []
    for raw in raw_changes:
        if not isinstance(raw, dict):
            raise OutcomeError("Each change must be an object.")
        order = orders.get(_text(raw.get("order_ref")))
        if order is None:
            raise OutcomeError(f"order_ref must be one of {', '.join(orders)}.")
        try:
            change_field = CallChangeField(_text(raw.get("field")))
        except ValueError:
            names = ", ".join(f.value for f in CallChangeField)
            raise OutcomeError(f"field must be one of {names}.") from None
        new_value = _text(raw.get("new_value"))
        if not new_value:
            raise OutcomeError("new_value is empty. Use the value the buyer confirmed.")
        item_name = _text(raw.get("item_name")) or None
        if change_field in ITEM_FIELDS:
            names = [item.name for item in order.items]
            if item_name not in names:
                raise OutcomeError(
                    f"item_name must name an item of order {order.ref}: {', '.join(names)}."
                )
        changes.append(
            CallChange(
                order_id=order.order_id,
                field=change_field,
                item_name=item_name,
                new_value=new_value,
            )
        )

    return Decision(
        outcome=CallOutcome(outcome.lower()),
        summary=summary,
        changes=changes,
        cancel_reason=_text(args.get("cancel_reason")) or None,
        human_callback_requested=bool(args.get("human_callback_requested")),
        buyer_requests=_text(args.get("buyer_requests")) or None,
    )


def closing_instruction(decision: Decision) -> str:
    return f"Saved. Say one closing line for {decision.outcome.name}, then stop."


def fallback_outcome(buyer_spoke: bool, keys_pressed: bool) -> CallOutcome:
    """Without an accepted record_call_outcome: no_answer if the buyer never spoke or pressed a
    key, unclear otherwise. The controller sets these, never the model."""
    return CallOutcome.UNCLEAR if buyer_spoke or keys_pressed else CallOutcome.NO_ANSWER
