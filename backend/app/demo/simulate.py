"""Order simulator for demos: `python -m app.demo.simulate --minutes 60 --orders-per-hour 30`.

Posts random orders from five fictional shops to the live intake API at random (exponential)
intervals until the time is up, so the order list and the dashboard keep moving. In the cloud it is
the Cloud Run job `codguard-simulate`, which costs nothing while it is not running.

- Every order has an `external_id` starting with `SIM-`: the pipeline scores and decides it but
  skips the Gemini assessment, which keeps the daily quota for people trying the app.
- Most phones reuse the +84000 range of the vn-synthetic history, so buyers arrive with past
  orders, some of them at other shops.
- API keys come from INTAKE_API_KEYS (`key:shop_id,...`), the same secret the service reads.

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

SHOPS = {
    "shop_la_vang": {
        "name": "Lá Vàng Studio",
        "share": 40,
        "channels": {"facebook": 50, "tiktok": 30, "website": 20},
        "items": [
            ("Váy hoa nhí", 259, 459),
            ("Áo sơ mi lụa", 199, 349),
            ("Chân váy xếp ly", 179, 299),
        ],
    },
    "shop_meo_mun": {
        "name": "Mèo Mun Accessories",
        "share": 15,
        "channels": {"tiktok": 50, "facebook": 30, "zalo": 20},
        "items": [
            ("Ốp lưng silicon", 49, 129),
            ("Cáp sạc nhanh", 59, 159),
            ("Tai nghe bluetooth", 199, 590),
        ],
    },
    "shop_song_xanh": {
        "name": "Sông Xanh Beauty",
        "share": 15,
        "channels": {"facebook": 40, "zalo": 30, "website": 30},
        "items": [("Sữa rửa mặt", 129, 259), ("Kem chống nắng", 189, 390), ("Son kem lì", 99, 249)],
    },
    "shop_go_moc": {
        "name": "Gỗ Mộc Home",
        "share": 15,
        "channels": {"website": 40, "facebook": 30, "other": 30},
        "items": [("Thớt gỗ me tây", 149, 299), ("Kệ gia vị", 199, 459), ("Bộ đũa gỗ", 89, 159)],
    },
    "shop_bep_nam": {
        "name": "Bếp Nấm Snacks",
        "share": 15,
        "channels": {"zalo": 50, "facebook": 40, "other": 10},
        "items": [
            ("Khô gà lá chanh", 89, 159),
            ("Bánh tráng trộn", 35, 69),
            ("Hạt điều rang muối", 159, 289),
        ],
    },
}
PROVINCES = [
    "Hà Nội",
    "TP Hồ Chí Minh",
    "Đà Nẵng",
    "Hải Phòng",
    "Cần Thơ",
]  # as in the training data
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
STREETS = [
    "đường Lê Lợi",
    "ngõ 34 Láng Hạ",
    "hẻm 12 Nguyễn Trãi",
    "đường Trần Phú",
    "ngách 5 Kim Mã",
]
VAGUE = ["gần chợ", "đầu hẻm", "cạnh trường tiểu học", "sau nhà văn hoá"]
CHATS = [
    "Khách: còn hàng không shop? Shop: còn ạ. Khách: chốt nhé.",
    "Khách: ship nhanh giúp em. Shop: dạ 2-3 ngày ạ. Khách: ok lên đơn.",
    "Khách: giá vậy ship luôn đi.",
    "Khách: có đổi size không? Shop: được ạ. Khách: lấy cho em 1 cái.",
]


def make_order(rng: random.Random, shop_id: str, now: datetime) -> dict:
    """One random order for `shop_id`, valid against the intake schema (OrderCreate)."""
    shop = SHOPS[shop_id]
    known = rng.random() < 0.85  # a buyer from the vn-synthetic history, or a new phone
    phone = f"+84000{rng.randrange(10_000) if known else 10_000 + rng.randrange(90_000):06d}"
    province, ward = rng.choice(PROVINCES), f"Phường {rng.randint(1, 20)}"
    street = f"Số {rng.randint(1, 200)} {rng.choice(STREETS)}" if rng.random() < 0.75 else None
    items = []
    for name, low, high in rng.sample(shop["items"], k=rng.choice([1, 1, 2])):
        items.append(
            {
                "name": name,
                "quantity": rng.randint(1, 3),
                "unit_price_vnd": rng.randint(low, high) * 1000,
            }
        )
    total = sum(i["quantity"] * i["unit_price_vnd"] for i in items) + 30_000
    prepaid = rng.choices([0, 50_000, total], [90, 5, 5])[0]  # COD, small deposit, fully prepaid
    return {
        "external_id": f"SIM-{shop_id}-{uuid.UUID(int=rng.getrandbits(128)).hex[:12]}",
        "channel": rng.choices(list(shop["channels"]), list(shop["channels"].values()))[0],
        "buyer_name": f"{rng.choice(SURNAMES)} {rng.choice(GIVEN)}",
        "buyer_phone": phone,
        "is_gift": rng.random() < 0.04,
        "address": {
            "raw": f"{street or rng.choice(VAGUE)}, {ward}, {province}",
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
    }


def keys_by_shop(env: str) -> dict[str, str]:
    """INTAKE_API_KEYS (`key:shop,...`) as {shop: key}, for the simulated shops only."""
    pairs = (p.split(":", 1) for p in env.split(",") if ":" in p)
    return {shop: key for key, shop in pairs if shop in SHOPS}


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
    args = parser.parse_args()
    url = os.environ["INTAKE_URL"].rstrip("/")
    keys = keys_by_shop(os.environ["INTAKE_API_KEYS"])
    if not keys:
        raise SystemExit("INTAKE_API_KEYS has no key for any simulated shop")
    rng = random.Random(args.seed)
    shops = list(keys)
    weights = [SHOPS[s]["share"] for s in shops]
    deadline = time.monotonic() + args.minutes * 60
    sent = 0
    while (wait := rng.expovariate(args.orders_per_hour / 3600)) < deadline - time.monotonic():
        time.sleep(wait)
        shop = rng.choices(shops, weights)[0]
        order = make_order(rng, shop, datetime.now(UTC))
        try:
            result = post(url, keys[shop], order)
        except (
            urllib.error.URLError,
            TimeoutError,
        ) as error:  # one failed post never stops the run
            result = {"error": str(error)}
        sent += 1
        print(
            json.dumps({"n": sent, "shop": shop, "channel": order["channel"]} | result), flush=True
        )
    print(json.dumps({"done": True, "orders": sent, "minutes": args.minutes}), flush=True)


if __name__ == "__main__":
    main()
