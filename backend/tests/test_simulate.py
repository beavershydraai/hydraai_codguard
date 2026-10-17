"""The demo world, the history seed and the live simulator (app/demo/)."""

import collections
import random
import re
from datetime import UTC, datetime

import pytest

from app.data import branches
from app.data.orders import final_state
from app.data.phone import to_e164
from app.demo.seed import stored_doc
from app.demo.simulate import branch_keys, schedule
from app.demo.world import BRANCH_REGIONS, CODE, World
from app.schemas.orders import OrderCreate

START = datetime(2026, 9, 1)


@pytest.fixture(scope="module")
def history():
    return World(seed=3, buyers_per_branch=200).history(START, 7)


def test_every_branch_sells_valid_orders_in_its_currency_and_regions(history):
    seen = collections.Counter(o.branch_id for o in history)
    assert set(seen) == set(BRANCH_REGIONS)
    for order in history:
        payload = order.payload
        OrderCreate.model_validate(payload)
        country = branches.country(branches.branches()[order.branch_id])
        assert payload["currency"] == country.currency
        assert to_e164(payload["buyer_phone"], country.calling_code) == payload["buyer_phone"]
        assert payload["address"]["province"] in BRANCH_REGIONS[order.branch_id]
        assert re.fullmatch(rf"{CODE[payload['channel']]}-\d{{8}}-\d{{6}}", payload["external_id"])


def test_outcomes_cover_buyer_failures_and_issues_training_leaves_out(history, monkeypatch):
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    from app.data.store import phone_key

    labels = collections.Counter()
    for order in history:
        doc = stored_doc(order, phone_key())
        assert doc["branch_id"] == order.branch_id and doc["scoring"] is None
        labels[(order.outcome, final_state(doc)[0])] += 1
    assert labels[("delivered", 0)] and labels[("refused", 1)] and labels[("cancelled", 1)]
    assert labels[("carrier_issue", None)]  # not the buyer's fault: left out of training


def test_live_orders_come_from_the_history_buyers():
    history_world, world = (
        World(seed=3, buyers_per_branch=200),
        World(seed=3, buyers_per_branch=200),
    )
    phones = {b.phone for b in history_world.buyers["branch_PH"]}
    assert phones == {b.phone for b in world.buyers["branch_PH"]}  # same seed, same buyers
    live = [world.live_order("branch_PH", datetime(2026, 9, 9, 6, tzinfo=UTC)) for _ in range(20)]
    assert all(o.payload["buyer_phone"] in phones for o in live)
    assert all(o.payload["placed_at"].endswith("+08:00") for o in live)


def test_the_history_is_the_same_for_the_same_seed():
    one = World(seed=5, buyers_per_branch=50).history(START, 2)
    two = World(seed=5, buyers_per_branch=50).history(START, 2)
    assert [o.payload for o in one] == [o.payload for o in two]
    assert [o.outcome for o in one] == [o.outcome for o in two]


def test_the_agents_switch_picks_each_branch_s_normal_or_noagents_key():
    env = "k1:shop_demo:branch_SG,k2:shop_demo:branch_SG:noagents,k3:shop_demo,k4:other:branch_PH"
    # A key without a branch is the default branch's (branch_VN_HCM).
    assert branch_keys(env, agents=True) == {"branch_SG": "k1", "branch_VN_HCM": "k3"}
    assert branch_keys(env, agents=False) == {"branch_SG": "k2"}
    assert branch_keys("k9:shop_new:branch_PH:noagents," + env, False, "shop_new") == {
        "branch_PH": "k9"
    }


def test_each_country_gets_exactly_its_orders_within_the_window():
    keys = {"branch_VN_HCM": "a", "branch_VN_HN": "b", "branch_SG": "c", "branch_PH": "d"}
    plan = schedule(["VN", "SG", "PH"], keys, 60, 10, random.Random(1))
    per_country = collections.Counter(branches.branches()[b] for _, b in plan)
    assert per_country == {"VN": 60, "SG": 60, "PH": 60}
    assert all(0 <= at <= 600 for at, _ in plan) and plan == sorted(plan)
    assert {b for _, b in plan if branches.branches()[b] == "VN"} == {
        "branch_VN_HCM",
        "branch_VN_HN",
    }
    only_sg = schedule(["SG"], keys, 5, 1, random.Random(1))
    assert [b for _, b in only_sg] == ["branch_SG"] * 5
    with pytest.raises(SystemExit):
        schedule(["PH"], {"branch_SG": "c"}, 1, 1, random.Random(1))


def test_a_sale_day_brings_more_orders():
    world = World(seed=1, buyers_per_branch=300)
    normal = len(world.day("branch_VN_HN", datetime(2026, 9, 8)))
    sale = len(world.day("branch_VN_HN", datetime(2026, 9, 9)))
    assert sale > normal * 1.2
