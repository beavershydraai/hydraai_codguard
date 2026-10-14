"""E3.1 address quality: admin-unit data, name matching, flags and score, Gemini verification and
cache, and where the check runs. Addresses are synthetic: fictional house numbers on real unit
names, which are not personal data."""

import json
from collections import defaultdict
from types import SimpleNamespace

import pytest

from app.data.orders import order_document, snapshot_row
from app.data.store import FirestoreCache
from app.decision import lifecycle
from app.risk.features import compute_features
from app.schemas.common import Address
from app.schemas.enums import AddressFlag as F
from app.schemas.orders import OrderUpdate
from app.signals import address as addr
from app.signals.address import AddressReading, address_key, check_address, score
from app.signals.admin_units import DATA_FILE, normalise, resolve_units, tables
from app.signals.gemini import Gemini, get_gemini
from tests.test_intake import ORDER, api, post  # noqa: F401  (api is a fixture)
from tests.test_lifecycle import store  # noqa: F401  (fixture)
from tests.test_policy import NOW


def check(raw: str, **kwargs):
    return check_address({"raw": raw}, **kwargs)


# --- Admin-unit data ---------------------------------------------------------------------------

MERGED = {  # tasks/E3.1-address-quality.md, from Resolution 202/2025/QH15
    "Tuyên Quang": {"Tuyên Quang", "Hà Giang"},
    "Lào Cai": {"Lào Cai", "Yên Bái"},
    "Thái Nguyên": {"Thái Nguyên", "Bắc Kạn"},
    "Phú Thọ": {"Phú Thọ", "Vĩnh Phúc", "Hòa Bình"},
    "Bắc Ninh": {"Bắc Ninh", "Bắc Giang"},
    "Hưng Yên": {"Hưng Yên", "Thái Bình"},
    "Hải Phòng": {"Hải Phòng", "Hải Dương"},
    "Ninh Bình": {"Ninh Bình", "Hà Nam", "Nam Định"},
    "Quảng Trị": {"Quảng Trị", "Quảng Bình"},
    "Đà Nẵng": {"Đà Nẵng", "Quảng Nam"},
    "Quảng Ngãi": {"Quảng Ngãi", "Kon Tum"},
    "Gia Lai": {"Gia Lai", "Bình Định"},
    "Khánh Hòa": {"Khánh Hòa", "Ninh Thuận"},
    "Lâm Đồng": {"Lâm Đồng", "Đắk Nông", "Bình Thuận"},
    "Đắk Lắk": {"Đắk Lắk", "Phú Yên"},
    "Hồ Chí Minh": {"Hồ Chí Minh", "Bình Dương", "Bà Rịa - Vũng Tàu"},
    "Đồng Nai": {"Đồng Nai", "Bình Phước"},
    "Tây Ninh": {"Tây Ninh", "Long An"},
    "Cần Thơ": {"Cần Thơ", "Sóc Trăng", "Hậu Giang"},
    "Vĩnh Long": {"Vĩnh Long", "Bến Tre", "Trà Vinh"},
    "Đồng Tháp": {"Đồng Tháp", "Tiền Giang"},
    "Cà Mau": {"Cà Mau", "Bạc Liêu"},
    "An Giang": {"An Giang", "Kiên Giang"},
}
UNCHANGED = [
    "Hà Nội", "Huế", "Lai Châu", "Điện Biên", "Sơn La", "Lạng Sơn", "Quảng Ninh", "Thanh Hóa",
    "Nghệ An", "Hà Tĩnh", "Cao Bằng",
]  # fmt: skip


def test_data_file_has_the_2025_units_and_records_its_source():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    assert "vietnamadminunits" in data["source"] and data["licence"].startswith("MIT")
    assert data["built"]
    t = tables()
    assert len(t.of("province")) == 34
    assert len(t.of("ward")) == 3321
    assert len(t.of("old_province")) == 63
    assert all(t.get("province", u.parent) for u in t.of("old_province"))
    for old_ward in t.of("old_ward"):
        assert old_ward.wards and all(("ward", code) in t.units for code in old_ward.wards)


def test_old_provinces_map_to_their_merged_province():
    t = tables()
    merged = defaultdict(set)
    for old in t.of("old_province"):
        merged[t.get("province", old.parent).short].add(old.short)
    assert merged == MERGED | {name: {name} for name in UNCHANGED}


# --- Name matching -----------------------------------------------------------------------------


def test_matching_ignores_case_diacritics_prefixes_and_leading_zeros():
    assert normalise("12 Nguyễn Trãi, P.2, Q.5, TP.HCM") == normalise(
        "12 nguyen trai, phuong 02, QUAN 5, thanh pho hcm"
    )
    assert normalise("F2, Q10") == "phuong 2, quan 10"


@pytest.mark.parametrize(
    "written", ["TP.HCM", "TPHCM", "Tp HCM", "HCM", "SG", "Sài Gòn", "Hồ Chí Minh", "ho chi minh"]
)
def test_aliases_of_ho_chi_minh_city(written):
    assert (
        resolve_units(f"Số 1 Lê Lợi, phường Bến Thành, {written}").province.short == "Hồ Chí Minh"
    )


@pytest.mark.parametrize("written", ["BRVT", "Vũng Tàu", "Bà Rịa - Vũng Tàu", "tỉnh Bà Rịa"])
def test_aliases_of_ba_ria_vung_tau_map_to_ho_chi_minh_city(written):
    res = resolve_units(f"Số 1 Lê Lợi, {written}")
    assert (res.old_province.short, res.province.short) == ("Bà Rịa - Vũng Tàu", "Hồ Chí Minh")


def test_hanoi_alias():
    assert resolve_units("Số 1, phường Láng, HN").province.short == "Hà Nội"


def test_accents_tell_apart_two_wards_of_one_province():
    for name in ("Xã Cẩm Giang", "Xã Cẩm Giàng"):
        assert resolve_units(f"Thôn 2, {name}, Hải Phòng").ward.name == name


def test_a_street_named_like_a_ward_is_not_the_ward():
    res = resolve_units("Số 12 ngõ 34 Láng, Hà Nội")
    assert res.ward is None and res.street_parts == ["Số 12 ngõ 34 Láng"]


# --- Plan test cases ----------------------------------------------------------------------------


def test_complete_new_format_address():
    result = check("Số 12 ngõ 34 Láng, phường Láng, Hà Nội")
    assert result.score >= 0.9 and result.flags == [] and result.admin_format == "new"
    assert (result.province, result.ward, result.source) == ("Hà Nội", "Phường Láng", "rules")


def test_old_ward_and_district_map_to_the_current_ward():
    result = check("12 Nguyễn Trãi, P.2, Q.5, TP.HCM")
    assert result.flags == [F.OLD_ADMIN_NAME] and result.admin_format == "old"
    assert (result.old_district, result.old_ward) == ("Quận 5", "Phường 2")
    assert (result.province, result.ward) == ("Hồ Chí Minh", "Phường Chợ Quán")
    assert result.suggested_raw == "12 Nguyễn Trãi, Phường Chợ Quán, Thành phố Hồ Chí Minh"


def test_merged_away_province_maps_to_the_new_one():
    result = check("Thôn 3, xã X, huyện Y, tỉnh Hà Giang")
    assert F.OLD_ADMIN_NAME in result.flags
    assert (result.old_province, result.province) == ("Hà Giang", "Tuyên Quang")


def test_old_city_district_and_province():
    result = check("25 Trần Phú, Thủ Dầu Một, Bình Dương")
    assert F.OLD_ADMIN_NAME in result.flags
    assert (result.province, result.old_province) == ("Hồ Chí Minh", "Bình Dương")
    assert result.old_district == "Thành phố Thủ Dầu Một"


def test_landmark_only_address_is_vague():
    result = check("gần chợ Tân Bình, gọi trước khi giao")
    assert {F.VAGUE_LANDMARK, F.MISSING_HOUSE_NUMBER} <= set(result.flags)
    assert result.score < 0.6


@pytest.mark.parametrize("raw", ["abc", "123", "ko có", "xxx", "..."])
def test_placeholder_text_scores_zero(raw):
    result = check(raw)
    assert (result.flags, result.score, result.admin_format) == (
        [F.PLACEHOLDER_TEXT],
        0.0,
        "unknown",
    )


def test_ward_of_another_province():
    result = check("phường Láng, TP Hồ Chí Minh")
    assert F.WARD_PROVINCE_MISMATCH in result.flags and result.ward is None


def test_text_without_diacritics_resolves_like_the_accented_form():
    assert check("Phuong Lang Ha Noi") == check("Phường Láng Hà Nội")
    assert check("Phuong Lang Ha Noi").ward == "Phường Láng"


def test_unknown_ward():
    result = check("Số 5, phường Không Tồn Tại, Hà Nội")
    assert result.flags == [F.UNKNOWN_WARD] and result.ward is None


# --- Further rules ------------------------------------------------------------------------------


def test_split_old_ward_lists_the_candidates_and_suggests_nothing():
    result = check("Ấp 1, xã An Phú Tây, huyện Bình Chánh, TP.HCM")
    assert result.flags == [F.AMBIGUOUS_NEW_WARD, F.OLD_ADMIN_NAME]
    assert result.ward is None and result.suggested_raw is None
    assert result.ward_candidates == ["Phường Bình Đông", "Xã Bình Chánh"]


def test_bare_district_name_next_to_a_ward_is_the_old_district():
    result = check("17 Quang Trung, F.5, Gò Vấp, SG")
    assert (result.old_district, result.old_ward) == ("Quận Gò Vấp", "Phường 5")
    assert result.ward == "Phường An Nhơn"


def test_bare_name_of_a_current_ward_is_the_ward():
    result = check("12 Hàng Bạc, Hoàn Kiếm, Hà Nội")
    assert (result.ward, result.admin_format, result.flags) == ("Phường Hoàn Kiếm", "new", [])


def test_island_district_becomes_its_special_zone():
    result = check("Số 9 Lý Thường Kiệt, Côn Đảo, Bà Rịa - Vũng Tàu")
    assert (result.ward, result.province) == ("Đặc khu Côn Đảo", "Hồ Chí Minh")


def test_missing_province_costs_nothing_when_the_ward_resolves_to_one():
    result = check("Số 3, phường Láng")
    assert result.flags == [F.MISSING_PROVINCE] and result.score == 1.0
    assert result.province == "Hà Nội"


def test_delivery_instructions_are_not_part_of_the_address():
    result = check("Số 8 Lê Lợi, phường Bến Thành, TP.HCM, gọi trước khi giao")
    assert result.flags == [] and result.score == 1.0


def test_a_number_in_a_landmark_is_not_a_house_number():
    result = check("đối diện trường cấp 2, phường Láng, Hà Nội")
    assert result.flags == [F.MISSING_HOUSE_NUMBER, F.VAGUE_LANDMARK]


def test_shop_fields_complete_the_raw_text():
    address = Address(raw="Số 12 ngõ 34 Láng", ward="Phường Láng", province="Hà Nội")
    result = check_address(address)
    assert (result.ward, result.province, result.flags) == ("Phường Láng", "Hà Nội", [])


def test_score_subtracts_penalties_and_clamps():
    assert score({F.MISSING_WARD, F.OLD_ADMIN_NAME}, province_resolved=True) == 0.6
    assert score({F.MISSING_PROVINCE}, province_resolved=False) == 0.9
    assert score({F.MISSING_PROVINCE}, province_resolved=True) == 1.0
    assert score(set(F) - {F.PLACEHOLDER_TEXT}, province_resolved=False) == 0.0
    assert score({F.PLACEHOLDER_TEXT}, province_resolved=True) == 0.0


def test_every_flag_has_a_penalty_and_a_vietnamese_label():
    assert set(addr.PENALTY) == set(addr.LABEL_VI) == set(F)


# Hardest addresses so far, to copy into the E3.4 evaluation set when it exists.
HARD_CASES = [
    ("Phuong Lang Ha Noi", {"ward": "Phường Láng", "province": "Hà Nội"}),
    ("12 Lê Lợi - P. Bến Thành - Q1 - HCM", {"ward": "Phường Bến Thành", "old_district": "Quận 1"}),
    ("17 Quang Trung, F.5, Gò Vấp, SG", {"ward": "Phường An Nhơn", "old_ward": "Phường 5"}),
    ("Số 12, Phường Láng Hạ, Đống Đa, Hà Nội", {"old_ward": "Phường Láng Hạ", "ward": None}),
    ("12 Hàng Bạc, Hoàn Kiếm, Hà Nội", {"ward": "Phường Hoàn Kiếm", "old_district": None}),
    ("25 Trần Phú, Thủ Dầu Một, Bình Dương", {"old_district": "Thành phố Thủ Dầu Một"}),
    ("Số 9 Lý Thường Kiệt, Côn Đảo, Bà Rịa - Vũng Tàu", {"ward": "Đặc khu Côn Đảo"}),
    ("Thôn 2, xã Cẩm Giàng, Hải Phòng", {"ward": "Xã Cẩm Giàng"}),
    ("12 Trần Phú, phường Chợ Quán, quận 5, TP HCM", {"admin_format": "mixed"}),
    ("phường Láng, TP Hồ Chí Minh", {"ward": None, "province": "Hồ Chí Minh"}),
]


@pytest.mark.parametrize(("raw", "expected"), HARD_CASES)
def test_hard_cases(raw, expected):
    result = check(raw).model_dump()
    assert {k: result[k] for k in expected} == expected


# --- Gemini -------------------------------------------------------------------------------------


class FakeGemini:
    model = "fake-model"

    def __init__(self, reading=None, error=None):
        self.reading, self.error, self.calls = reading, error, 0

    def generate(self, instruction, text, schema):
        self.calls += 1
        assert "Vietnamese delivery address" in instruction and schema is AddressReading
        if self.error:
            return None  # what Gemini.generate returns on any error
        return self.reading


class DictCache:
    def __init__(self):
        self.docs = {}

    def get(self, key):
        return self.docs.get(key)

    def set(self, key, value):
        self.docs[key] = value


def test_gemini_fills_a_ward_written_in_the_text():
    gemini = FakeGemini(AddressReading(ward="Láng", province="Hà Nội", house_number="12"))
    result = check("Số 12 ngõ 34 Láng, Hà Nội", gemini=gemini)
    assert (result.ward, result.source) == ("Phường Láng", "rules+gemini")
    assert F.MISSING_WARD not in result.flags
    assert result.version == f"{addr.RULES_VERSION}+{addr.prompt()[1]}"


@pytest.mark.parametrize(
    "ward",
    [
        "Phường Không Có",  # written, but not in the tables
        "Phường Giảng Võ",  # in the tables, but not written in the text
    ],
)
def test_unverifiable_gemini_ward_is_dropped(ward):
    raw = "Số 12 ngõ Không Có, Hà Nội"
    rules = check(raw)
    result = check(raw, gemini=FakeGemini(AddressReading(ward=ward, house_number="12")))
    assert result.source == "rules+gemini"
    assert (result.ward, result.flags) == (None, rules.flags)
    assert F.UNKNOWN_WARD not in result.flags and F.WARD_PROVINCE_MISMATCH not in result.flags


def test_gemini_wording_flags_are_kept_only_when_consistent():
    raw = "Thôn 3, xã Cẩm Giàng, Hải Phòng"
    reading = AddressReading(street="Thôn 3", missing_house_number=True, placeholder_text=True)
    result = check(raw, gemini=FakeGemini(reading))
    assert result.flags == [F.MISSING_HOUSE_NUMBER]  # a real ward is never a placeholder


def test_gemini_failure_leaves_the_rules_result():
    raw = "Số 12 ngõ 34 Láng, phường Láng, Hà Nội"
    assert check(raw, gemini=FakeGemini(error=True)) == check(raw)


def test_same_address_is_read_once_through_the_cache():
    gemini, cache = FakeGemini(AddressReading(house_number="12")), DictCache()
    raw = "Số 12 ngõ 34 Láng, phường Láng, Hà Nội"
    first = check(raw, gemini=gemini, cache=cache)
    second = check("so 12 ngo 34 lang, PHUONG LANG, ha noi", gemini=gemini, cache=cache)
    assert gemini.calls == 1 and first.source == second.source == "rules+gemini"
    assert list(cache.docs) == [address_key(raw)]
    cache.docs[address_key(raw)]["version"] = "address-0"  # older prompt: read again
    check(raw, gemini=gemini, cache=cache)
    assert gemini.calls == 2


def test_placeholder_is_not_sent_to_gemini():
    gemini = FakeGemini(AddressReading())
    assert check("abc", gemini=gemini).flags == [F.PLACEHOLDER_TEXT] and gemini.calls == 0


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def generate_content(self, *, model, contents, config):
        self.calls.append((model, contents, config))
        if self.error:
            raise self.error
        return self.response


def test_gemini_wrapper_returns_the_structured_reading():
    models = FakeModels(SimpleNamespace(parsed=AddressReading(ward="P.2"), text=""))
    reading = Gemini(SimpleNamespace(models=models), "m").generate("i", "t", AddressReading)
    assert reading == AddressReading(ward="P.2")
    _, _, config = models.calls[0]
    assert config.temperature == 0 and config.response_schema is AddressReading
    assert config.http_options.timeout == 3000


def test_gemini_wrapper_parses_text_when_the_sdk_did_not():
    models = FakeModels(SimpleNamespace(parsed=None, text='{"ward": "P.2"}'))
    reading = Gemini(SimpleNamespace(models=models), "m").generate("i", "t", AddressReading)
    assert reading.ward == "P.2"


@pytest.mark.parametrize("error", [TimeoutError("slow"), RuntimeError("quota")])
def test_gemini_wrapper_returns_none_on_errors(error):
    models = FakeModels(error=error)
    assert Gemini(SimpleNamespace(models=models), "m").generate("i", "t", AddressReading) is None


def test_gemini_cap_skips_the_call():
    models = FakeModels()
    gemini = Gemini(SimpleNamespace(models=models), "m", allow=lambda: False)
    assert gemini.generate("i", "t", AddressReading) is None and models.calls == []


def test_gemini_is_off_without_a_model(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    get_gemini.cache_clear()
    assert get_gemini() is None


def test_cache_errors_count_as_a_miss():
    def broken(*args, **kwargs):
        raise RuntimeError("firestore down")

    doc = SimpleNamespace(get=broken, set=broken)
    client = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: doc))
    cache = FirestoreCache(client, "address_checks")
    assert cache.get("k") is None
    cache.set("k", {})  # no exception


def test_prompt_file_has_a_version():
    instruction, version = addr.prompt()
    assert version == "address-1" and "never infer a ward" in instruction


# --- Where the check runs -----------------------------------------------------------------------


def test_intake_stores_the_address_signals(api):  # noqa: F811
    client, orders = api
    body = post(client, "key-a").json()
    signals = orders.docs[body["order_id"]]["signals"]["address"]
    assert signals["ward"] == "Phường Láng" and signals["source"] == "rules"


def test_intake_uses_gemini_and_survives_its_failure(api):  # noqa: F811
    client, orders = api

    def provide(gemini):
        return lambda: gemini

    for gemini, source in ((FakeGemini(AddressReading()), "rules+gemini"), (None, "rules")):
        client.app.dependency_overrides[get_gemini] = provide(gemini)
        body = ORDER | {"external_id": f"ext-{source}"}
        response = post(client, "key-a", body)
        assert response.status_code == 202
        assert orders.docs[response.json()["order_id"]]["signals"]["address"]["source"] == source


def test_intake_survives_a_broken_address_check(api, monkeypatch):  # noqa: F811
    client, orders = api
    monkeypatch.setattr(addr, "check_address", lambda *a, **k: 1 / 0)
    response = post(client, "key-a")
    assert response.status_code == 202
    assert orders.docs[response.json()["order_id"]]["signals"] == {"address": None}


def test_address_edit_rechecks_the_address(store):  # noqa: F811
    update = OrderUpdate(address=Address(raw="12 Nguyễn Trãi, P.2, Q.5, TP.HCM"))
    doc = lifecycle.edit_order(store, "ord_test", "shop_a", update, NOW)
    assert doc["signals"]["address"]["ward"] == "Phường Chợ Quán"
    assert doc["signals"]["address"]["flags"] == ["old_admin_name"]


def test_other_edits_keep_the_address_signals(store):  # noqa: F811
    before = store.docs["ord_test"]["signals"]
    doc = lifecycle.edit_order(
        store, "ord_test", "shop_a", OrderUpdate(note="Giao giờ hành chính"), NOW
    )
    assert doc["signals"] == before


def test_features_come_from_the_rules_only(monkeypatch):
    monkeypatch.setattr(addr, "read_address", lambda *a, **k: 1 / 0)  # never called
    order = {
        "order_id": "o1",
        "placed_at": NOW,
        "items": [{"quantity": 1, "unit_price_vnd": 100_000}],
        "discount_vnd": 0,
        "shipping_fee_vnd": 0,
        "prepaid_vnd": 0,
        "is_gift": False,
        "channel": "facebook",
        "shop_id": "s",
        "address": {"raw": "gần chợ, Thủ Dầu Một, Bình Dương", "street": None},
    }
    features = compute_features(order, [], NOW, {"p0": 0.1, "province": {}})
    expected = check(order["address"]["raw"])
    assert features["address_quality_score"] == expected.score
    assert features["address_old_admin_name"] == 1 and features["address_vague"] == 1


def test_order_document_has_rules_signals_that_stay_out_of_the_snapshot():
    from app.schemas.orders import OrderCreate

    doc = order_document(
        OrderCreate.model_validate(ORDER),
        order_id="o1",
        shop_id="s",
        phone_key=b"k",
        now=NOW,
    )
    assert doc["signals"]["address"]["source"] == "rules"
    doc["delivery"] = {"result": "delivered", "occurred_at": NOW}
    assert "signals" not in snapshot_row(doc)
