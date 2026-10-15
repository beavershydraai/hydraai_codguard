"""Build the CallJob for an order (docs/call-controller.md). Settings from the environment:

- CALL_ENV: `env` of published jobs, `demo` (the VM) or `dev-<name>` (default `demo`)
- CALL_TARGET_OVERRIDE: `<kind>:<address>`, e.g. `sip:6001` or `pstn:<team phone, E.164>`. Demo
  and testing only: every call rings this target instead of the buyer's phone. Deployed from
  Secret Manager (`call-target-override`), so a real number never lands in the repo.
- CALL_DIAL_BUYERS: `on` lets a call without the override dial the buyer's phone. Off by default:
  with the Twilio trunk up, a missing override must not ring the made-up buyers of demo data.
- CALL_AGENT: `gemini_live` (default) or `script`
- CALL_LANGUAGE: `vi` (default) or `en`
"""

import os
import re
from datetime import datetime

from app.calls import spoken
from app.data import branches
from app.data.shops import default_name
from app.schemas.enums import CallAgent, CallLanguage, CallTargetKind
from app.schemas.telephony import CallBuyer, CallItem, CallJob, CallOrder, CallTarget

RING_TIMEOUT_SECONDS = 30
MAX_DURATION_SECONDS = 300
_REF = re.compile(r"^[A-Za-z0-9-]{1,12}$")


class NoTarget(ValueError):
    """The call has nothing it may dial; the message says why."""


def target_override() -> CallTarget | None:
    value = os.environ.get("CALL_TARGET_OVERRIDE", "").strip()
    if not value:
        return None
    kind, _, address = value.partition(":")
    return CallTarget(kind=CallTargetKind(kind), address=address)


def dial_buyers() -> bool:
    return os.environ.get("CALL_DIAL_BUYERS", "").strip().lower() == "on"


def target_for(doc: dict) -> CallTarget:
    """The override when set, otherwise the buyer's phone if CALL_DIAL_BUYERS is on. A phone that
    failed validation at intake has no hash and is never dialled."""
    override = target_override()
    if override:
        return override
    if not dial_buyers():
        raise NoTarget("calls to buyers' phones are turned off on this server")
    if not doc.get("buyer_phone_hash") or not str(doc.get("buyer_phone", "")).startswith("+"):
        raise NoTarget("the order has no valid phone number")
    return CallTarget(kind=CallTargetKind.PSTN, address=doc["buyer_phone"])


def order_ref(doc: dict) -> str:
    """A short code the buyer may recognise: the shop's own order number when it is short,
    otherwise the end of our order ID."""
    external = doc.get("external_id") or ""
    return external if _REF.match(external) else doc["order_id"][-6:].upper()


def total_vnd(doc: dict) -> int:
    items = sum(item["quantity"] * item["unit_price_vnd"] for item in doc["items"])
    return items - doc.get("discount_vnd", 0) + doc.get("shipping_fee_vnd", 0)


def cod_amount_vnd(doc: dict) -> int:
    return max(total_vnd(doc) - doc.get("prepaid_vnd", 0), 0)


def call_order(doc: dict, now: datetime, language: CallLanguage) -> CallOrder:
    cod = cod_amount_vnd(doc)
    prepaid = doc.get("prepaid_vnd", 0)
    return CallOrder(
        order_id=doc["order_id"],
        ref=order_ref(doc),
        placed_at_spoken=spoken.placed_at(
            doc["placed_at"], now, language, branches.country_of(doc).tz
        ),
        items=[
            CallItem(name=i["name"], variant=i.get("variant") or "", quantity=i["quantity"])
            for i in doc["items"]
        ],
        cod_amount_vnd=cod,
        cod_amount_spoken=spoken.amount(cod, language),
        deposit_paid_vnd=prepaid,
        deposit_paid_spoken=spoken.amount(prepaid, language) if prepaid else "",
        recipient_name=doc.get("recipient_name") or doc["buyer_name"],
        delivery_address=doc["address"]["raw"],
        is_gift=bool(doc.get("is_gift")),
    )


def build_job(
    doc: dict, call_id: str, attempt: int, now: datetime, shop_name: str | None = None
) -> CallJob:
    """One call about one order, introduced with the shop's name (its profile, E7.1). Batching
    several orders to the same phone into one call (contact protection, E4.3) is not done
    yet."""
    language = CallLanguage(os.environ.get("CALL_LANGUAGE", CallLanguage.VI.value))
    order = call_order(doc, now, language)
    return CallJob(
        call_id=call_id,
        attempt=attempt,
        env=os.environ.get("CALL_ENV", "demo"),
        target=target_for(doc),
        agent=CallAgent(os.environ.get("CALL_AGENT", CallAgent.GEMINI_LIVE.value)),
        language=language,
        shop_name=shop_name or default_name(doc["shop_id"]),
        buyer=CallBuyer(full_name=doc["buyer_name"]),
        orders=[order],
        total_cod_amount_vnd=order.cod_amount_vnd,
        total_cod_amount_spoken=order.cod_amount_spoken,
        ring_timeout_seconds=RING_TIMEOUT_SECONDS,
        max_duration_seconds=MAX_DURATION_SECONDS,
        created_at=now,
    )
