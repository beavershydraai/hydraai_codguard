"""What each branch of the pipeline does once the engine has decided (E4.7).

The real channels are E5. Until then a send is simulated and carries `mock: true`, which the UI
shows as the label "mock". The claim around every send is not a stub: an ADK retry, a redelivered
webhook or a second run of the pipeline for the same decision can never reach the buyer twice.

A confirmation link or a deposit request is sent at most once per order, so its claim is
`order_id:action`. An AI call has two attempts (E4.2), so each attempt has its own claim,
`order_id:ai_call:1` and `order_id:ai_call:2`, which records the decision it carries out. A rerun
of that decision finds its own claim and stops; the next decision takes the next number.
"""

from datetime import UTC, datetime

from app.agents.log import DecisionLog
from app.decision.policy import MAX_CALL_ATTEMPTS
from app.schemas.enums import ContactChannel, DecisionAction
from app.schemas.scoring import Decision

CHANNEL = {
    DecisionAction.SEND_CONFIRMATION_LINK: ContactChannel.CONFIRMATION_LINK,
    DecisionAction.AI_CALL: ContactChannel.AI_CALL,
    DecisionAction.REQUIRE_DEPOSIT: ContactChannel.DEPOSIT_REQUEST,
}


def _claim(log: DecisionLog, doc: dict, action: DecisionAction, now: datetime) -> tuple[dict, bool]:
    """Reserve this send, or find the claim that already made it. Returns the claim and whether
    this caller took it."""
    record = {
        "order_id": doc["order_id"],
        "shop_id": doc["shop_id"],
        "action": action.value,
        "channel": CHANNEL[action].value,
        "at": now,
    }
    if action != DecisionAction.AI_CALL:
        key = f"{doc['order_id']}:{action.value}"
        return (record, True) if log.claim(key, record) else (log.claimed(key), False)
    raw = doc.get("decision")
    decided_at = Decision.model_validate(raw).decided_at if raw else None
    for attempt in range(1, MAX_CALL_ATTEMPTS + 1):
        key = f"{doc['order_id']}:{action.value}:{attempt}"
        claim = record | {"attempt": attempt, "decided_at": decided_at}
        if log.claim(key, claim):
            return claim, True
        earlier = log.claimed(key)
        if earlier.get("decided_at") == decided_at:  # this decision already placed its call
            return earlier, False
    return earlier, False  # both attempts belong to earlier decisions: nobody is called again


def contact(log: DecisionLog, doc: dict, action: DecisionAction, now: datetime | None) -> dict:
    """Send one message, call or deposit request to the buyer, at most once per decision."""
    now = now or datetime.now(UTC)
    claim, sent = _claim(log, doc, action, now)
    result = {
        "order_id": doc["order_id"],
        "action": action.value,
        "channel": claim["channel"],
        "sent": sent,
        "sent_at": claim["at"],
        "mock": True,
    }
    if "attempt" in claim:
        result["attempt"] = claim["attempt"]
    return result


def notify_ship(doc: dict) -> dict:
    """Tell the seller the order may go to the carrier. Nothing reaches the buyer."""
    return {
        "order_id": doc["order_id"],
        "action": DecisionAction.SHIP_NOW.value,
        "status": doc["status"],
    }


def enqueue_review(doc: dict, reason: str) -> dict:
    """Put the order in the seller's review queue. Nothing reaches the buyer."""
    return {
        "order_id": doc["order_id"],
        "action": DecisionAction.HOLD_FOR_REVIEW.value,
        "status": doc["status"],
        "reason": reason,
    }
