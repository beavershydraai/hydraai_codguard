"""The demo order simulator (app/demo/simulate.py)."""

import random
from datetime import UTC, datetime

from app.demo.simulate import SHOPS, keys_by_shop, make_order
from app.schemas.orders import OrderCreate


def test_simulated_orders_are_valid_intake_orders_from_their_shop():
    rng = random.Random(1)
    now = datetime(2026, 10, 15, 14, 0, tzinfo=UTC)
    for _ in range(300):
        shop = rng.choice(list(SHOPS))
        order = make_order(rng, shop, now)
        OrderCreate.model_validate(order)
        assert order["external_id"].startswith(f"SIM-{shop}-")
        assert order["channel"] in SHOPS[shop]["channels"]
        assert order["buyer_phone"].startswith("+84000")


def test_only_keys_of_simulated_shops_are_used():
    keys = keys_by_shop("k1:shop_la_vang,k2:shop_demo,k3:shop_bep_nam,broken")
    assert keys == {"shop_la_vang": "k1", "shop_bep_nam": "k3"}
