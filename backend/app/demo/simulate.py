"""Order simulator for demos: `python -m app.demo.simulate --minutes 60 --orders-per-hour 30`.

Posts live orders of the demo shop's branches (VN, SG, PH) to the intake API at random
(exponential) intervals until the time is up, so the order list and the dashboard keep moving. In
the cloud it is the Cloud Run job `codguard-simulate`, which costs nothing while it is not running.

- Orders come from the same world as the training history (app/demo/world.py, same seed): the
  same buyers, with their past orders and behaviour, so each country's model scores them as it
  would score real orders of that branch.
- Each branch posts with its own key, so intake knows the branch, country and currency.
- By default it uses the branches' `noagents` test keys: the pipeline scores and decides every
  order but skips the Gemini assessment, which keeps the daily quota for people trying the app.
  `--agents` uses the normal keys, so the two agents run (and use the quota).
- Keys come from INTAKE_API_KEYS (`key:shop:branch[:noagents],...`), the secret the service reads.
"""

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from app.demo.world import ORDERS_PER_DAY, SHOP_ID, World


def branch_keys(env: str, agents: bool) -> dict[str, str]:
    """{branch: key} of the demo shop: the normal keys, or the `noagents` test keys."""
    keys = {}
    for entry in env.split(","):
        key, *rest = entry.split(":")
        branch = next((t for t in rest[1:] if t != "noagents"), None)
        if rest[:1] == [SHOP_ID] and branch and ("noagents" in rest[1:]) != agents:
            keys[branch] = key
    return keys


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
    parser.add_argument("--orders-per-hour", type=float, default=30)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--agents", action="store_true", help="run the Gemini agents (uses quota)")
    args = parser.parse_args()
    url = os.environ["INTAKE_URL"].rstrip("/")
    keys = branch_keys(os.environ["INTAKE_API_KEYS"], args.agents)
    if not keys:
        kind = "normal" if args.agents else "noagents test"
        raise SystemExit(f"INTAKE_API_KEYS has no {kind} branch key for {SHOP_ID}")
    world = World()  # the history's seed: the same buyers
    rng = random.Random(args.seed)
    shares = {b: ORDERS_PER_DAY[b] for b in keys}
    deadline = time.monotonic() + args.minutes * 60
    sent = 0
    while (wait := rng.expovariate(args.orders_per_hour / 3600)) < deadline - time.monotonic():
        time.sleep(wait)
        branch = rng.choices(list(shares), list(shares.values()))[0]
        order = world.live_order(branch, datetime.now(UTC)).payload
        try:
            result = post(url, keys[branch], order)
        except (urllib.error.URLError, TimeoutError) as error:  # never stop the run
            result = {"error": str(error)}
        sent += 1
        line = {"n": sent, "branch": branch, "channel": order["channel"]} | result
        print(json.dumps(line), flush=True)
    print(json.dumps({"done": True, "orders": sent, "minutes": args.minutes}), flush=True)


if __name__ == "__main__":
    main()
