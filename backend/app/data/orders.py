"""The Firestore order document and the training row built from it (docs/data-model.md)."""

from datetime import UTC, datetime, timedelta, timezone

from app.data.phone import phone_hash, to_e164
from app.schemas.delivery import DeliveryOutcome
from app.schemas.enums import DeliveryResult, OrderStatus
from app.schemas.orders import OrderCreate

VN_TIME = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh has no daylight saving
BUYER_FAILURES = {DeliveryResult.REFUSED, DeliveryResult.UNREACHABLE}
NOT_IN_SNAPSHOT = {"buyer_name", "recipient_name", "buyer_phone", "recipient_phone", "scoring"}


def to_utc(at: datetime) -> datetime:
    """A time without a zone is Vietnam time."""
    return (at if at.tzinfo else at.replace(tzinfo=VN_TIME)).astimezone(UTC)


def _phone(raw: str | None, key: bytes) -> tuple[str | None, str | None]:
    """(phone to store, its hash). An invalid phone is kept as received, with no hash."""
    if raw is None:
        return None, None
    e164 = to_e164(raw)
    return (e164, phone_hash(e164, key)) if e164 else (raw, None)


def order_document(
    order: OrderCreate, *, order_id: str, shop_id: str, phone_key: bytes, now: datetime
) -> dict:
    """Firestore `orders/{order_id}` for a new order."""
    buyer, buyer_hash = _phone(order.buyer_phone, phone_key)
    recipient, recipient_hash = _phone(order.recipient_phone, phone_key)
    return {
        **order.model_dump(mode="json"),
        "order_id": order_id,
        "shop_id": shop_id,
        "placed_at": to_utc(order.placed_at),
        "buyer_phone": buyer,
        "buyer_phone_hash": buyer_hash,
        "recipient_phone": recipient,
        "recipient_phone_hash": recipient_hash,
        "status": OrderStatus.NEW.value,
        "scoring": None,
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
    """One flat training row without names, raw phones or the old score; None if unlabelled."""
    delivery = doc.get("delivery") or {}
    label, _ = final_state(doc)
    if label is None:
        return None
    row = {k: v for k, v in doc.items() if k not in NOT_IN_SNAPSHOT | {"address", "delivery"}}
    row |= {f"address_{k}": v for k, v in doc["address"].items()}
    row |= {f"delivery_{k}": v for k, v in delivery.items()}
    row["is_failed"] = label
    return row
