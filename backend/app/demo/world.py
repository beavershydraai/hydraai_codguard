"""Synthetic orders of the demo shop's branches in Vietnam, Singapore and the Philippines.

The training history (app/demo/seed.py) and the live simulator (app/demo/simulate.py) both draw
from this one world, so live orders come from the same buyers, with the same behaviour, as the
history their country's model was trained on.

How a failed delivery happens here, and which of it the model can see:
- Every buyer has a hidden type: reliable, impulsive or serial refuser.
- Each type leaves observable traces: serial refusers order in bursts, buy more units, leave out
  the house number more often and order at any hour; impulsive buyers order more at night and on
  sale days; reliable buyers come back more often, so they build a history.
- The type's base failure probability is raised by a missing house number, a large first order,
  a night order (impulsive buyers), a sale day and the region.
- Outcomes: delivered, refused, unreachable, cancelled by the buyer before shipping (all buyer
  caused except delivered), plus carrier and shop issues, which training leaves out.

Every rate, share and price below is an assumption for the simulation, not market data. Amounts
are integers in the currency's minor unit (VND has none; SGD and PHP are in cents).
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.data import branches

SHOP_ID = "shop_demo"
TYPES = {  # base failure probability, orders a buyer places relative to others, burst chance
    "reliable": {"p": 0.02, "rate": 1.6, "burst": 0.0},
    "impulsive": {"p": 0.10, "rate": 1.0, "burst": 0.05},
    "serial": {"p": 0.60, "rate": 1.3, "burst": 0.35},
}
PACKS = {
    "VN": {
        "mix": {"reliable": 80, "impulsive": 13, "serial": 7},
        "regions": {  # region -> (extra failure probability, streets)
            "TP Hồ Chí Minh": (0.0, ["Nguyen Trai", "Le Loi", "hem 12 Cach Mang Thang 8"]),
            "Cần Thơ": (0.03, ["30 Thang 4", "Nguyen Van Cu"]),
            "Hà Nội": (0.0, ["ngo 34 Lang Ha", "Kim Ma", "ngach 5 Doi Can"]),
            "Hải Phòng": (0.01, ["Lach Tray", "To Hieu"]),
            "Đà Nẵng": (0.0, ["Nguyen Van Linh", "Hai Phong"]),
        },
        "short": {
            "TP Hồ Chí Minh": "TP HCM",
            "Cần Thơ": "Can Tho",
            "Hà Nội": "Ha Noi",
            "Hải Phòng": "Hai Phong",
            "Đà Nẵng": "Da Nang",
        },
        "house": "So {n} {street}",
        "vague": ["gan cho", "dau hem", "canh truong hoc"],
        "channels": {"facebook": 40, "tiktok": 25, "zalo": 20, "website": 10, "other": 5},
        "price": (129_000, 599_000),
        "step": 1_000,
        "shipping": 30_000,
        "prepaid": 0.05,
        "sale_days": {(7, 7), (8, 8), (9, 9)},
    },
    "SG": {
        "mix": {"reliable": 90, "impulsive": 7, "serial": 3},
        "regions": {
            "Central": (0.0, ["Orchard Rd", "Bukit Timah Rd"]),
            "East": (0.0, ["Tampines St 21", "Bedok North Ave 1"]),
            "North": (0.02, ["Woodlands Ave 3", "Yishun Ring Rd"]),
            "North-East": (0.0, ["Sengkang East Way", "Punggol Field"]),
            "West": (0.01, ["Jurong West Ave 1", "Clementi Ave 2"]),
        },
        "short": {},
        "house": "Blk {n} {street}",
        "vague": ["near the MRT", "opposite the hawker centre"],
        "channels": {"website": 45, "facebook": 25, "tiktok": 20, "other": 10},
        "price": (1_500, 7_900),
        "step": 10,
        "shipping": 400,
        "prepaid": 0.6,
        "sale_days": {(7, 7), (8, 8), (9, 9)},
    },
    "PH": {
        "mix": {"reliable": 72, "impulsive": 18, "serial": 10},
        "regions": {
            "Metro Manila": (0.0, ["Rizal Ave, Brgy San Isidro", "Mabini St, Brgy Malate"]),
            "Cebu": (0.02, ["Osmena Blvd, Brgy Capitol Site", "Colon St, Brgy Kalubihan"]),
            "Davao": (0.04, ["Roxas Ave, Brgy 2-A", "Quirino Ave, Brgy 19-B"]),
        },
        "short": {},
        "house": "{n} {street}",
        "vague": ["near the church", "beside the sari-sari store"],
        "channels": {"facebook": 50, "tiktok": 35, "other": 15},
        "price": (29_900, 149_900),
        "step": 100,
        "shipping": 10_000,
        "prepaid": 0.1,
        "sale_days": {(7, 7), (8, 8), (9, 9)},
    },
}
BRANCH_REGIONS = {  # the regions each branch ships to
    "branch_VN_HCM": ["TP Hồ Chí Minh", "Cần Thơ"],
    "branch_VN_HN": ["Hà Nội", "Hải Phòng", "Đà Nẵng"],
    "branch_SG": ["Central", "East", "North", "North-East", "West"],
    "branch_PH": ["Metro Manila", "Cebu", "Davao"],
}
ORDERS_PER_DAY = {"branch_VN_HCM": 55, "branch_VN_HN": 45, "branch_SG": 60, "branch_PH": 80}
CODE = {"facebook": "FB", "tiktok": "TT", "zalo": "ZL", "website": "WEB", "other": "OTH"}
ITEMS = [
    "Cotton T-shirt",
    "Floral dress",
    "Wide-leg jeans",
    "Windbreaker jacket",
    "Canvas tote bag",
    "White sneakers",
    "Silk pyjama set",
]
SURNAMES = {
    "VN": ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi"],
    "SG": ["Tan", "Lim", "Lee", "Ng", "Wong", "Kumar", "Ong"],
    "PH": ["Santos", "Reyes", "Cruz", "Bautista", "Garcia", "Mendoza"],
}
GIVEN = {
    "VN": ["Thị Lan", "Văn Hùng", "Minh Anh", "Thu Trang", "Đức Huy", "Ngọc Hà"],
    "SG": ["Wei Ling", "Jun Jie", "Priya", "Hui Min", "Daniel"],
    "PH": ["Maria", "Jose", "Angelica", "Mark", "Kristine"],
}


def pick(rng: random.Random, weights: dict):
    return rng.choices(list(weights), list(weights.values()))[0]


@dataclass
class Buyer:
    phone: str
    name: str
    kind: str
    region: str
    house: bool
    orders: int = 0


@dataclass
class Order:
    """An intake payload, the branch that takes it and, once known, its outcome."""

    branch_id: str
    payload: dict
    p_fail: float  # the true failure probability, for checking a model against the best possible
    outcome: str = ""
    outcome_after: timedelta = field(default_factory=timedelta)


class World:
    def __init__(self, seed: int = 7, buyers_per_branch: int = 1500):
        self.rng = random.Random(seed)
        self.buyers: dict[str, list[Buyer]] = {}
        serial = 0
        for branch, regions in BRANCH_REGIONS.items():
            code = branches.branches()[branch]
            calling, digits = (
                branches.country(code).calling_code,
                {"VN": 9, "SG": 8, "PH": 10}[code],
            )
            pack, people = PACKS[code], []
            for _ in range(buyers_per_branch):
                kind = pick(self.rng, pack["mix"])
                serial += 1
                # `000` after the calling code: no carrier issues these numbers
                phone = f"+{calling}000{serial:0{digits - 3}d}"
                name = f"{self.rng.choice(SURNAMES[code])} {self.rng.choice(GIVEN[code])}"
                house = self.rng.random() > (0.45 if kind == "serial" else 0.08)
                people.append(Buyer(phone, name, kind, self.rng.choice(regions), house))
            self.buyers[branch] = people

    def day(self, branch: str, day: datetime) -> list[Order]:
        """Every order of one branch on one local day, in time order, outcomes included."""
        rng, code = self.rng, branches.branches()[branch]
        pack, tz = PACKS[code], branches.country(code).tz
        sale = (day.month, day.day) in pack["sale_days"]
        weights = {
            i: TYPES[b.kind]["rate"] * (1.8 if sale and b.kind == "impulsive" else 1)
            for i, b in enumerate(self.buyers[branch])
        }
        n = int(ORDERS_PER_DAY[branch] * (1.6 if sale else 1) * rng.uniform(0.8, 1.2))
        orders = []
        for _ in range(n):
            buyer = self.buyers[branch][pick(rng, weights)]
            hour = rng.choice(range(24)) if buyer.kind != "reliable" else rng.choice(range(8, 23))
            if buyer.kind == "impulsive" and rng.random() < 0.4:
                hour = rng.choice([22, 23, 0, 1])
            at = day.replace(tzinfo=tz) + timedelta(hours=hour, minutes=rng.randrange(60))
            orders.append(self._order(branch, code, pack, buyer, at, sale))
            if rng.random() < TYPES[buyer.kind]["burst"]:  # the same buyer again within the hour
                again = at + timedelta(minutes=rng.randint(3, 50))
                orders.append(self._order(branch, code, pack, buyer, again, sale))
        return sorted(orders, key=lambda o: datetime.fromisoformat(o.payload["placed_at"]))

    def live_order(self, branch: str, at: datetime) -> Order:
        """One order for the branch at `at` (aware), from the same buyers as the history."""
        code = branches.branches()[branch]
        pack = PACKS[code]
        local = at.astimezone(branches.country(code).tz)
        sale = (local.month, local.day) in pack["sale_days"]
        people = self.buyers[branch]
        buyer = people[pick(self.rng, {i: TYPES[b.kind]["rate"] for i, b in enumerate(people)})]
        return self._order(branch, code, pack, buyer, local, sale)

    def _order(self, branch, code, pack, buyer, at, sale) -> Order:
        rng = self.rng
        low, high = pack["price"]
        qty_max = 5 if buyer.kind == "serial" else 3
        items = [
            {
                "name": rng.choice(ITEMS),
                "quantity": rng.randint(1, qty_max),
                "unit_price_vnd": rng.randint(low, high) // pack["step"] * pack["step"],
            }
            for _ in range(rng.choice([1, 1, 2]))
        ]
        total = sum(i["quantity"] * i["unit_price_vnd"] for i in items) + pack["shipping"]
        prepaid = (
            total if rng.random() < pack["prepaid"] * (0.3 if buyer.kind == "serial" else 1) else 0
        )
        street = rng.choice(pack["regions"][buyer.region][1])
        line = pack["house"].format(n=rng.randint(1, 300), street=street) if buyer.house else None
        region_text = pack["short"].get(buyer.region, buyer.region)
        channel = pick(rng, pack["channels"])
        payload = {
            "external_id": f"{CODE[channel]}-{at:%Y%m%d}-{rng.randrange(10**6):06d}",
            "channel": channel,
            "buyer_name": buyer.name,
            "buyer_phone": buyer.phone,
            "is_gift": rng.random() < 0.04,
            "address": {
                "raw": f"{line or rng.choice(pack['vague'])}, {region_text}",
                "street": line,
                "ward": None,
                "province": buyer.region,
            },
            "items": items,
            "shipping_fee_vnd": pack["shipping"],
            "discount_vnd": 0,
            "prepaid_vnd": prepaid,
            "placed_at": at.isoformat(),
            "currency": branches.country(code).currency,
        }
        p = self._p_fail(code, buyer, at, total - prepaid, sale)
        buyer.orders += 1
        return Order(branch, payload, p)

    def _p_fail(self, code, buyer, at, cod, sale) -> float:
        if cod == 0:
            return 0.0  # fully prepaid: nothing to refuse at the door
        p = TYPES[buyer.kind]["p"]
        local_hour = at.hour
        if buyer.kind == "impulsive" and (local_hour >= 22 or local_hour < 6):
            p += 0.20
        if sale and buyer.kind != "reliable":
            p += 0.05
        p += 0.10 * (not buyer.house)
        p += 0.08 * (buyer.orders == 0 and cod > PACKS[code]["price"][1] * 1.5)
        p += PACKS[code]["regions"][buyer.region][0]
        return min(p, 0.95)

    def outcome(self, order: Order) -> None:
        """Draw the outcome: buyer-caused failure, carrier or shop issue, or delivered."""
        rng = self.rng
        if rng.random() < order.p_fail:
            order.outcome = pick(rng, {"refused": 50, "unreachable": 35, "cancelled": 15})
        else:
            order.outcome = pick(rng, {"delivered": 96, "carrier_issue": 3, "shop_issue": 1})
        order.outcome_after = (
            timedelta(hours=rng.randint(2, 12))
            if order.outcome == "cancelled"
            else timedelta(days=rng.randint(2, 5))
        )

    def history(self, start: datetime, days: int) -> list[Order]:
        """`days` of orders for every branch from local midnight of `start`, with outcomes."""
        orders = []
        for branch in BRANCH_REGIONS:
            for d in range(days):
                orders += self.day(branch, start + timedelta(days=d))
        orders.sort(key=lambda o: datetime.fromisoformat(o.payload["placed_at"]))
        for order in orders:
            self.outcome(order)
        return orders
