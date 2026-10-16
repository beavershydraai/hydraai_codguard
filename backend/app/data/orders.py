"""The Firestore order document and the training row built from it (docs/data-model.md)."""

from datetime import UTC, datetime, timedelta, timezone

from app.data import branches
from app.data.phone import encrypt_phone, phone_hash, to_e164
from app.schemas.delivery import DeliveryOutcome
from app.schemas.enums import DeliveryResult, OrderStatus
from app.schemas.orders import OrderCreate

VN_TIME = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh has no daylight saving
BUYER_FAILURES = {DeliveryResult.REFUSED, DeliveryResult.UNREACHABLE}
NOT_IN_SNAPSHOT = {
    "buyer_name",
    "recipient_name",
    "buyer_phone",
    "recipient_phone",
    "scoring",
    "status",
    "decision",
    "score_history",
    "timeline",
    "confirmation",
    "cancel",
    "intervention",
    "attempts",
}


def to_utc(at: datetime, tz: timezone = VN_TIME) -> datetime:
    """A time without a zone is in `tz`, the branch's local time (default Vietnam)."""
    return (at if at.tzinfo else at.replace(tzinfo=tz)).astimezone(UTC)


def stored_phone(raw: str | None, key: bytes, calling_code: str) -> tuple[str | None, str | None]:
    """(phone as stored, its hash): E.164, encrypted. An invalid phone is kept as received, also
    encrypted, with no hash."""
    if raw is None:
        return None, None
    e164 = to_e164(raw, calling_code)
    return encrypt_phone(e164 or raw), phone_hash(e164, key) if e164 else None


def order_document(
    order: OrderCreate,
    *,
    order_id: str,
    shop_id: str,
    phone_key: bytes,
    now: datetime,
    branch_id: str | None = None,
) -> dict:
    """Firestore `orders/{order_id}` for a new order of `branch_id` (default: config default)."""
    branch_id = branch_id or branches.default_branch()
    country = branches.country(branches.branches()[branch_id])
    buyer, buyer_hash = stored_phone(order.buyer_phone, phone_key, country.calling_code)
    recipient, recipient_hash = stored_phone(order.recipient_phone, phone_key, country.calling_code)
    return {
        **order.model_dump(mode="json"),
        "currency": country.currency,
        "order_id": order_id,
        "shop_id": shop_id,
        "branch_id": branch_id,
        "country": country.code,
        "placed_at": to_utc(order.placed_at, country.tz),
        "buyer_phone": buyer,
        "buyer_phone_hash": buyer_hash,
        "recipient_phone": recipient,
        "recipient_phone_hash": recipient_hash,
        "status": OrderStatus.NEW.value,
        "scoring": None,
        "decision": None,
        "score_history": [],
        "confirmation": None,
        "cancel": None,
        "timeline": [
            {
                "at": now,
                "type": "created",
                "actor": "system",
                "message_vi": "Order created.",
                "reason": None,
            }
        ],
        "delivery": None,
        "created_at": now,
        "updated_at": now,
    }


def delivery_fields(outcome: DeliveryOutcome, *, now: datetime) -> dict:
    """Fields to merge into the order document when the carrier reports a result."""
    return {
        "delivery": {
            "result": outcome.result.value,
            "carrier": outcome.carrier.value,
            "tracking_code": outcome.tracking_code,
            "occurred_at": to_utc(outcome.occurred_at),
        },
        "updated_at": now,
    }


def training_label(result: str | None) -> int | None:
    """1 = buyer-caused failure, 0 = delivered, None = not used for training."""
    if result == DeliveryResult.DELIVERED:
        return 0
    return 1 if result in BUYER_FAILURES else None


BUYER_CANCELS = {"not_ordered", "cancelled"}  # tasks/E2.3: a buyer cancellation is a failure


def final_state(doc: dict) -> tuple[int | None, datetime | None]:
    """(label, when it became known): a buyer cancellation before shipping, else the delivery."""
    cancel = doc.get("cancel")
    if cancel and cancel["reason"] in BUYER_CANCELS:
        return 1, cancel["at"]
    delivery = doc.get("delivery") or {}
    return training_label(delivery.get("result")), delivery.get("occurred_at")


def snapshot_row(doc: dict) -> dict | None:
    """One flat training row without personal data or lifecycle state; None if unlabelled."""
    delivery = doc.get("delivery") or {}
    label, _ = final_state(doc)
    if label is None:
        return None
    row = {k: v for k, v in doc.items() if k not in NOT_IN_SNAPSHOT | {"address", "delivery"}}
    row |= {f"address_{k}": v for k, v in doc["address"].items()}
    row |= {f"delivery_{k}": v for k, v in delivery.items()}
    row["is_failed"] = label
    return row
