"""Small synthetic order documents for the risk tests: risky phones refuse often and leave out the
house number; actions lower the failure rate. Numbers are test fixtures, not data."""

import random
from datetime import UTC, datetime, timedelta

START = datetime(2026, 5, 1, tzinfo=UTC)
OPTIONS = {"medium": ["none", "link", "call"], "high": ["link", "call"]}


def orders(n_phones: int = 300, days: int = 120, seed: int = 3) -> list[dict]:
    rng, docs = random.Random(seed), []
    for i in range(n_phones):
        risky = rng.random() < 0.2
        for _ in range(rng.randint(1, 6)):
            t = START + timedelta(days=rng.uniform(0, days), hours=rng.uniform(0, 24))
            tier = rng.choice(["medium", "high"])
            action = rng.choice(OPTIONS[tier])
            p = (0.6 if risky else 0.05) * {"none": 1.0, "link": 0.8, "call": 0.5}[action]
            failed = rng.random() < p
            street = None if risky else f"Số {rng.randint(1, 99)} đường A"
            docs.append(
                {
                    "order_id": f"o{len(docs)}",
                    "shop_id": f"shop_{rng.randint(0, 2)}",
                    "placed_at": t,
                    "channel": "facebook",
                    "is_gift": False,
                    "items": [{"name": "x", "quantity": 1, "unit_price_vnd": 300_000}],
                    "discount_vnd": 0,
                    "shipping_fee_vnd": 30_000,
                    "prepaid_vnd": 0,
                    "address": {
                        "raw": f"{street or 'gần chợ'}, Phường 5, Hà Nội",
                        "street": street,
                        "ward": "Phường 5",
                        "province": rng.choice(["Hà Nội", "Đà Nẵng"]),
                    },
                    "buyer_phone_hash": f"h{i}",
                    "tier": tier,
                    "contact_action": action,
                    "random_slice": True,
                    "action_probability": 1 / len(OPTIONS[tier]),
                    "delivery": {
                        "result": "refused" if failed else "delivered",
                        "occurred_at": t + timedelta(days=3),
                    },
                    "status": "new",
                }
            )
    return docs
