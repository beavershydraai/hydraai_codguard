"""Order simulator for demos: `python -m app.demo.simulate --minutes 60 --orders-per-hour 30`.

Posts random orders of the demo shop (`shop_demo`, shown as "Sample Fashion Shop" in the app) from
its three branches to the live intake API at random (exponential) intervals until the time is up,
so the order list and the dashboard keep moving. In the cloud it is the Cloud Run job
`codguard-simulate`, which costs nothing while it is not running.

- By default every order has an `external_id` starting with `SIM-`: the pipeline scores and
  decides it but skips the Gemini assessment, which keeps the daily quota for people trying the
  app. `--agents` uses `SIMAI-` instead, so the two agents run (and use the quota).
- The branch is in the order note (`branch_1 HCM`, shown on the order page) and the external_id.
- Most phones reuse the +84000 range of the vn-synthetic history, so buyers arrive with past
  orders, some of them at other shops.
- The shop's API key comes from INTAKE_API_KEYS (`key:shop_id,...`), the secret the service reads.

Every share and price below is a simulation assumption, not data from shops.
"""

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime

from app.data.orders import VN_TIME

SHOP_ID = "shop_demo"  # the shop of the app's sign-in account (ADMIN_SHOP_ID)
# label in the order note -> (share of orders, provinces it ships to with their shares)
BRANCHES = {
    "branch_1 HCM": (45, {"TP Hồ Chí Minh": 75, "Cần Thơ": 25}),
    "branch_2 HN": (40, {"Hà Nội": 75, "Hải Phòng": 25}),
    "branch_3 DN": (15, {"Đà Nẵng": 100}),
}
CHANNELS = {"facebook": 40, "tiktok": 25, "zalo": 15, "website": 15, "other": 5}
ITEMS = [  # name, price range in thousand VND
    ("Cotton T-shirt", 159, 219),
    ("Floral dress", 289, 369),
    ("Wide-leg jeans", 319, 399),
    ("Windbreaker jacket", 389, 469),
    ("Canvas tote bag", 129, 179),
    ("White sneakers", 499, 599),
    ("Silk pyjama set", 249, 309),
]
# `province` keeps the names the model was trained on (its encoding); the address text is short.
SHORT = {
    "Hà Nội": "Ha Noi",
    "TP Hồ Chí Minh": "TP HCM",
    "Đà Nẵng": "Da Nang",
    "Hải Phòng": "Hai Phong",
    "Cần Thơ": "Can Tho",
}
SURNAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Ngô"]
GIVEN = [
    "Thị Lan",
    "Văn Hùng",
    "Thị Mai",
    "Minh Anh",
    "Quốc Bảo",
    "Thu Trang",
    "Đức Huy",
    "Ngọc Hà",
]
STREETS = ["Le Loi", "ngo 34 Lang Ha", "hem 12 Nguyen Trai", "Tran Phu", "ngach 5 Kim Ma"]
VAGUE = ["gan cho", "dau hem", "canh truong tieu hoc", "sau nha van hoa"]
CHATS = [
    "Khách: còn hàng không shop? Shop: còn ạ. Khách: chốt nhé.",
    "Khách: ship nhanh giúp em. Shop: dạ 2-3 ngày ạ. Khách: ok lên đơn.",
    "Khách: giá vậy ship luôn đi.",
    "Khách: có đổi size không? Shop: được ạ. Khách: lấy cho em 1 cái.",
]


def pick(rng: random.Random, weights: dict) -> str:
    return rng.choices(list(weights), list(weights.values()))[0]


def make_order(rng: random.Random, now: datetime, agents: bool = False) -> dict:
    """One random order of the demo shop, valid against the intake schema (OrderCreate)."""
    branch = pick(rng, {name: share for name, (share, _) in BRANCHES.items()})
    province = pick(rng, BRANCHES[branch][1])
    known = rng.random() < 0.85  # a buyer from the vn-synthetic history, or a new phone
    phone = f"+84000{rng.randrange(10_000) if known else 10_000 + rng.randrange(90_000):06d}"
    ward = f"P. {rng.randint(1, 20)}"
    street = f"So {rng.randint(1, 200)} {rng.choice(STREETS)}" if rng.random() < 0.75 else None
    items = []
    for name, low, high in rng.sample(ITEMS, k=rng.choice([1, 1, 2])):
        items.append(
            {
                "name": name,
                "quantity": rng.randint(1, 3),
                "unit_price_vnd": rng.randint(low, high) * 1000,
            }
        )
    total = sum(i["quantity"] * i["unit_price_vnd"] for i in items) + 30_000
    prepaid = rng.choices([0, 50_000, total], [90, 5, 5])[0]  # COD, small deposit, fully prepaid
    tag = uuid.UUID(int=rng.getrandbits(128)).hex[:12]
    return {
        "external_id": f"{'SIMAI' if agents else 'SIM'}-{branch.split()[0]}-{tag}",
        "channel": pick(rng, CHANNELS),
        "buyer_name": f"{rng.choice(SURNAMES)} {rng.choice(GIVEN)}",
        "buyer_phone": phone,
        "is_gift": rng.random() < 0.04,
        "address": {
            "raw": f"{street or rng.choice(VAGUE)}, {ward}, {SHORT[province]}",
            "street": street,
            "ward": ward,
            "province": province,
        },
        "items": items,
        "shipping_fee_vnd": 30_000,
        "discount_vnd": rng.choice([0, 0, 0, 0, 20_000]),
        "prepaid_vnd": min(prepaid, total),
        "placed_at": now.astimezone(VN_TIME).isoformat(),
        "conversation_text": rng.choice(CHATS) if rng.random() < 0.5 else None,
        "note": branch,
    }


def shop_key(env: str) -> str | None:
    """The demo shop's key in INTAKE_API_KEYS (`key:shop,...`)."""
    pairs = (p.split(":", 1) for p in env.split(",") if ":" in p)
    return next((key for key, shop in pairs if shop == SHOP_ID), None)


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
    key = shop_key(os.environ["INTAKE_API_KEYS"])
    if key is None:
        raise SystemExit(f"INTAKE_API_KEYS has no key for {SHOP_ID}")
    rng = random.Random(args.seed)
    deadline = time.monotonic() + args.minutes * 60
    sent = 0
    while (wait := rng.expovariate(args.orders_per_hour / 3600)) < deadline - time.monotonic():
        time.sleep(wait)
        order = make_order(rng, datetime.now(UTC), args.agents)
        try:
            result = post(url, key, order)
        except (
            urllib.error.URLError,
            TimeoutError,
        ) as error:  # one failed post never stops the run
            result = {"error": str(error)}
        sent += 1
        print(
            json.dumps({"n": sent, "branch": order["note"], "channel": order["channel"]} | result),
            flush=True,
        )
    print(json.dumps({"done": True, "orders": sent, "minutes": args.minutes}), flush=True)


if __name__ == "__main__":
    main()
