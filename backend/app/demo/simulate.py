"""Order simulator for demos: `python -m app.demo.simulate --minutes 10 --orders 60`.

Posts `--orders` live orders for each country in `--countries` (default VN, SG and PH) to the
intake API, at random times spread over `--minutes`, so the order list and the dashboard keep
moving. In the cloud it is the Cloud Run job `codguard-simulate`, which costs nothing while it is
not running.

- Orders come from the same world as the training history (app/demo/world.py, same seed): the
  same buyers, with their past orders and behaviour, so each country's model scores them as it
  would score real orders of that branch. Within a country, its branches share the orders by
  their usual volume.
- Each branch posts with its own key, so intake knows the branch, country and currency. A key
  without a branch belongs to the default branch.
- By default it uses the branches' `noagents` test keys: the pipeline scores and decides every
  order but skips the Gemini assessment, which keeps the daily quota for people trying the app.
  `--agents` uses the normal keys, so the two agents run (and use the quota).
- Keys come from INTAKE_API_KEYS (`key:shop[:branch][:noagents],...`), the secret the service
  reads; the simulator picks the ones it needs, nobody passes keys by hand.
"""

import argparse
import collections
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from app.data import branches
from app.demo.world import ORDERS_PER_DAY, SHOP_ID, World


def branch_keys(env: str, agents: bool) -> dict[str, str]:
    """{branch: key} of the demo shop: the normal keys, or the `noagents` test keys."""
    keys = {}
    for entry in env.split(","):
        key, *rest = entry.split(":")
        if rest[:1] != [SHOP_ID] or ("noagents" in rest[1:]) == agents:
            continue
        branch = next((t for t in rest[1:] if t != "noagents"), branches.default_branch())
        keys[branch] = key
    return keys


def schedule(countries: list[str], keys: dict, orders: int, minutes: float, rng) -> list:
    """[(seconds from start, branch)]: `orders` per country at random times, sorted."""
    of_country = branches.branches()
    plan = []
    for country in countries:
        own = {b: ORDERS_PER_DAY[b] for b in keys if of_country[b] == country}
        if not own:
            raise SystemExit(f"INTAKE_API_KEYS has no key for a branch in {country}")
        for _ in range(orders):
            branch = rng.choices(list(own), list(own.values()))[0]
            plan.append((rng.uniform(0, minutes * 60), branch))
    return sorted(plan)


def post(url: str, key: str, order: dict) -> dict:
    request = urllib.request.Request(
        f"{url}/api/v1/intake/orders",
        data=json.dumps(order, ensure_ascii=False).encode(),
        headers={"X-Api-Key": key, "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutes", type=float, default=60)
    parser.add_argument("--orders", type=int, default=10, help="orders per country")
    parser.add_argument("--countries", default="VN,SG,PH", help="comma-separated")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--agents", action="store_true", help="run the Gemini agents (uses quota)")
    args = parser.parse_args()
    url = os.environ["INTAKE_URL"].rstrip("/")
    keys = branch_keys(os.environ["INTAKE_API_KEYS"], args.agents)
    rng = random.Random(args.seed)
    plan = schedule(args.countries.split(","), keys, args.orders, args.minutes, rng)
    world = World()  # the history's seed: the same buyers
    start = time.monotonic()
    sent = collections.Counter()
    for n, (at, branch) in enumerate(plan, 1):
        time.sleep(max(0.0, at - (time.monotonic() - start)))
        order = world.live_order(branch, datetime.now(UTC)).payload
        try:
            result = post(url, keys[branch], order)
        except (urllib.error.URLError, TimeoutError) as error:  # never stop the run
            result = {"error": str(error)}
        country = branches.branches()[branch]
        sent[country] += 1
        line = {"n": n, "country": country, "branch": branch, "channel": order["channel"]}
        print(json.dumps(line | result), flush=True)
    print(json.dumps({"done": True, "orders": sent, "minutes": args.minutes}), flush=True)


if __name__ == "__main__":
    main()
