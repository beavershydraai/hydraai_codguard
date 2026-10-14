"""compute_features(order, history, at, enc): the one function training and serving share
(tasks/E2.3-risk-features.md, catalog subset).

history = earlier orders of the same buyer phone. Activity features use placed_at < at; outcome
features use only final states known before `at`. enc = encodings fitted on the training snapshot.
"""

import math
import re
from datetime import timedelta

from app.data.orders import VN_TIME, final_state
from app.signals.address import address_features

M_SMOOTH = 5  # E2.3 rule 7
CHANNELS = ["facebook", "zalo", "tiktok", "website", "instagram", "other"]
_DIGIT = re.compile(r"\d")


def has_house_number(address: dict) -> int:
    """A number before the ward ('Số 12 ...', '12/3 ...'). Digits in 'Phường 5' do not count."""
    head = address.get("street") or address["raw"].split(",")[0]
    return int(bool(_DIGIT.search(head)))


def cod_amount(order: dict) -> int:
    subtotal = sum(i["quantity"] * i["unit_price_vnd"] for i in order["items"])
    total = subtotal - order["discount_vnd"] + order["shipping_fee_vnd"]
    return max(total - order["prepaid_vnd"], 0)


def compute_features(order: dict, history: list[dict], at, enc: dict) -> dict:
    items = order["items"]
    subtotal = sum(i["quantity"] * i["unit_price_vnd"] for i in items)
    cod = cod_amount(order)
    local = order["placed_at"].astimezone(VN_TIME)
    p0 = enc["p0"]

    prior = [h for h in history if h["placed_at"] < at and h["order_id"] != order["order_id"]]
    known = [(lbl, t) for h in prior for lbl, t in [final_state(h)] if lbl is not None and t < at]
    failed = [t for lbl, t in known if lbl == 1]
    cods = [cod_amount(h) for h in prior]
    last = prior[-1]["placed_at"] if prior else None

    def within(span):
        return sum(h["placed_at"] >= at - span for h in prior)

    return {
        # payment
        "cod_amount_vnd": cod,
        "log_cod_amount": math.log1p(cod),
        "cod_vs_phone_avg_ratio": cod / (sum(cods) / len(cods)) if cods and sum(cods) else 1.0,
        # order behaviour
        "n_lines": len(items),
        "total_qty": sum(i["quantity"] for i in items),
        "discount_ratio": order["discount_vnd"] / subtotal if subtotal else 0.0,
        "placed_hour_vn": local.hour,
        "placed_dow": local.weekday(),
        "is_night": int(local.hour >= 22 or local.hour < 6),
        # address quality
        "address_has_house_number": has_house_number(order["address"]),
        "address_parts_filled": sum(
            order["address"].get(k) is not None for k in ("street", "ward", "province")
        ),
        **address_features(order["address"]),  # E3.1, rules only
        "province_fail_rate_te": enc["province"].get(order["address"].get("province"), p0),
        # context
        "is_gift": int(order["is_gift"]),
        "channel": CHANNELS.index(order["channel"]) if order["channel"] in CHANNELS else 5,
        # phone history: outcomes
        "phone_outcomes_all": len(known),
        "phone_failed_all": len(failed),
        "phone_fail_rate_smoothed_all": (len(failed) + M_SMOOTH * p0) / (len(known) + M_SMOOTH),
        "phone_days_since_last_failure": (at - max(failed)).days if failed else -1,
        # phone history and velocity: activity
        "phone_is_new": int(not prior),
        "phone_orders_1h": within(timedelta(hours=1)),
        "phone_orders_24h": within(timedelta(hours=24)),
        "phone_orders_30d": within(timedelta(days=30)),
        "phone_orders_all": len(prior),
        "phone_minutes_since_prev_order": (at - last).total_seconds() / 60 if last else -1,
        "phone_distinct_shops_all": len({h["shop_id"] for h in prior}),
    }
