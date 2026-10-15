"""The demo order simulator (app/demo/simulate.py)."""

import random
import re
from datetime import UTC, datetime

from app.demo.simulate import BRANCHES, CHANNELS, CODE, SHORT, make_order, shop_key
from app.risk.features import has_house_number
from app.schemas.orders import OrderCreate

NOW = datetime(2026, 10, 15, 14, 0, tzinfo=UTC)


def test_simulated_orders_are_valid_intake_orders_from_a_branch():
    rng = random.Random(1)
    for _ in range(300):
        order = make_order(rng, NOW)
        OrderCreate.model_validate(order)
        assert re.fullmatch(rf"{CODE[order['channel']]}-20261015-\d{{6}}", order["external_id"])
        assert order["address"]["province"] in BRANCHES[order["note"]][1]
        assert order["address"]["raw"].endswith(SHORT[order["address"]["province"]])
        assert order["channel"] in CHANNELS
        assert order["buyer_phone"].startswith("+84000")


def test_the_address_text_still_shows_a_missing_house_number():
    rng = random.Random(3)
    flags = {has_house_number(make_order(rng, NOW)["address"]) for _ in range(100)}
    assert flags == {0, 1}


def test_the_agents_switch_picks_the_normal_or_the_noagents_key():
    env = "k1:shop_la_vang,k2:shop_demo,k3:shop_demo:noagents,broken"
    assert shop_key(env, agents=True) == "k2"
    assert shop_key(env, agents=False) == "k3"
    assert shop_key("k2:shop_demo", agents=False) is None
