"""What each branch of the pipeline does once the engine has decided (E4.7).

The real channels are E5. Until then a send is simulated and carries `mock: true`, which the UI
shows as the label "mock". The claim around every send is not a stub: it is taken under
`order_id + action`, so an ADK retry, a redelivered webhook or a second run of the pipeline for
the same order can never reach the buyer twice.
"""

from datetime import UTC, datetime

from app.agents.log import DecisionLog
from app.schemas.enums import ContactChannel, DecisionAction

CHANNEL = {
    DecisionAction.SEND_CONFIRMATION_LINK: ContactChannel.CONFIRMATION_LINK,
    DecisionAction.AI_CALL: ContactChannel.AI_CALL,
    DecisionAction.REQUIRE_DEPOSIT: ContactChannel.DEPOSIT_REQUEST,
}


def _claim(log: DecisionLog, doc: dict, action: DecisionAction, now: datetime) -> dict | None:
    """Reserve one contact of this kind for this order, or return the record of the earlier one."""
    key = f"{doc['order_id']}:{action.value}"
    record = {
        "order_id": doc["order_id"],
        "shop_id": doc["shop_id"],
        "action": action.value,
        "channel": CHANNEL[action].value,
        "at": now,
    }
    return None if log.claim(key, record) else log.claimed(key)


def contact(log: DecisionLog, doc: dict, action: DecisionAction, now: datetime | None) -> dict:
    """Send one message, call or deposit request to the buyer, at most once per order."""
    now = now or datetime.now(UTC)
    earlier = _claim(log, doc, action, now)
    if earlier:
        return {
            "order_id": doc["order_id"],
            "action": action.value,
            "channel": earlier["channel"],
            "sent": False,
            "sent_at": earlier["at"],
            "mock": True,
        }
    return {
        "order_id": doc["order_id"],
        "action": action.value,
        "channel": CHANNEL[action].value,
        "sent": True,
        "sent_at": now,
        "mock": True,
    }


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
