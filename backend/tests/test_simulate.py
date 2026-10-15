"""The demo order simulator (app/demo/simulate.py)."""

import random
from datetime import UTC, datetime

from app.demo.simulate import BRANCHES, CHANNELS, SHORT, make_order, shop_key
from app.risk.features import has_house_number
from app.schemas.orders import OrderCreate

NOW = datetime(2026, 10, 15, 14, 0, tzinfo=UTC)


def test_simulated_orders_are_valid_intake_orders_from_a_branch():
    rng = random.Random(1)
    for _ in range(300):
        order = make_order(rng, NOW)
        OrderCreate.model_validate(order)
        branch = order["note"]
        assert order["external_id"].startswith(f"SIM-{branch.split()[0]}-")
        assert order["address"]["province"] in BRANCHES[branch][1]
        assert order["address"]["raw"].endswith(SHORT[order["address"]["province"]])
        assert order["channel"] in CHANNELS
        assert order["buyer_phone"].startswith("+84000")


def test_the_address_text_still_shows_a_missing_house_number():
    rng = random.Random(3)
    flags = {has_house_number(make_order(rng, NOW)["address"]) for _ in range(100)}
    assert flags == {0, 1}


def test_only_the_demo_shop_key_is_used():
    assert shop_key("k1:shop_la_vang,k2:shop_demo") == "k2"
    assert shop_key("k1:shop_la_vang,broken") is None


def test_agents_switch_picks_the_prefix_the_assessment_checks():
    rng = random.Random(2)
    assert make_order(rng, NOW)["external_id"].startswith("SIM-")
    with_agents = make_order(rng, NOW, agents=True)["external_id"]
    assert with_agents.startswith("SIMAI-") and not with_agents.startswith("SIM-")
