"""Offline address extraction and conservative administrative normalization."""

import asyncio

import pytest
from pydantic import ValidationError

from app.schemas.common import Address
from app.schemas.enums import SignalGroup
from scoring.ai.address import AddressParts, analyze_address, extract_address


def values(result):
    return {signal.key: signal.value for signal in result.signals}


def complete_parts(**overrides):
    return AddressParts(
        **{
            "house_number": "12",
            "street": "Đường Mẫu",
            "ward": "Phường Sài Gòn",
            "province": "Hồ Chí Minh",
            **overrides,
        }
    )


def test_complete_address_returns_features_without_risk_decisions():
    address = Address(raw="12 Đường Mẫu, Phường Sài Gòn, Hồ Chí Minh")
    result = analyze_address(address, complete_parts())

    assert values(result) == {
        "address_completeness": 1.0,
        "address_missing_house_number": False,
        "address_missing_ward": False,
        "address_vague": False,
        "address_legacy_admin_names": False,
    }
    assert all(signal.group == SignalGroup.ADDRESS_QUALITY for signal in result.signals)
    assert all("contribution" not in signal.model_dump() for signal in result.signals)
    assert result.normalized == Address(
        raw=address.raw,
        street="12 Đường Mẫu",
        ward="Phường Sài Gòn",
        province="Hồ Chí Minh",
    )
    assert result.admin_unresolved is False


@pytest.mark.parametrize(
    ("old_ward", "district", "province", "new_ward", "new_province"),
    [
        ("Bến Nghé", "Quận 1", "TP.HCM", "Phường Sài Gòn", "Hồ Chí Minh"),
        ("P.1", "Q.3", "TP HCM", "Phường Bàn Cờ", "Hồ Chí Minh"),
        ("Hàng Bạc", "Hoàn Kiếm", "Hà Nội", "Phường Hoàn Kiếm", "Hà Nội"),
        ("Phú Cường", "Thủ Dầu Một", "Bình Dương", "Phường Thủ Dầu Một", "Hồ Chí Minh"),
    ],
)
def test_old_and_new_names_have_identical_completeness_and_missing_flags(
    old_ward, district, province, new_ward, new_province
):
    old_address = Address(raw=f"12 Đường Mẫu, {old_ward}, {district}, {province}")
    new_address = Address(raw=f"12 Đường Mẫu, {new_ward}, {new_province}")
    old = analyze_address(
        old_address, complete_parts(ward=old_ward, district=district, province=province)
    )
    new = analyze_address(new_address, complete_parts(ward=new_ward, province=new_province))

    assert values(old) == {**values(new), "address_legacy_admin_names": True}
    assert old.normalized.ward == new.normalized.ward == new_ward
    assert old.normalized.province == new.normalized.province == new_province
    assert old.admin_unresolved is False


def test_no_diacritics_abbreviations_and_parts_in_any_order_resolve():
    address = Address(raw="TP.HCM, P. Ben Nghe, Q.1, 12 hem Mau")
    result = analyze_address(
        address,
        complete_parts(street="hem Mau", ward="P. Ben Nghe", district="Q.1", province="TP.HCM"),
    )

    assert result.normalized.ward == "Phường Sài Gòn"
    assert result.normalized.province == "Hồ Chí Minh"
    assert values(result)["address_completeness"] == 1.0


def test_unknown_name_keeps_original_address_and_does_not_guess():
    address = Address(raw="12 Đường Mẫu, Phường Thử Nghiệm, Hồ Chí Minh")
    result = analyze_address(address, complete_parts(ward="Phường Thử Nghiệm"))

    assert result.normalized is None
    assert result.admin_unresolved is True
    assert address.ward is None
    assert values(result)["address_completeness"] == 1.0


@pytest.mark.parametrize("ward", ["Đa Kao", "Nguyễn Thái Bình"])
def test_split_old_wards_are_unresolved_even_with_district(ward):
    result = analyze_address(
        Address(raw=f"12 Đường Mẫu, {ward}, Quận 1, Hồ Chí Minh"),
        complete_parts(ward=ward, district="Quận 1"),
    )
    assert result.normalized is None
    assert result.admin_unresolved is True
    assert values(result)["address_legacy_admin_names"] is True


def test_numeric_old_ward_needs_district_to_disambiguate():
    result = analyze_address(Address(raw="12 Đường Mẫu, P.1, TP.HCM"), complete_parts(ward="P.1"))
    assert result.normalized is None
    assert result.admin_unresolved is True


def test_conflicting_district_is_not_ignored():
    result = analyze_address(
        Address(raw="12 Đường Mẫu, Bến Nghé, Quận 3, Hồ Chí Minh"),
        complete_parts(ward="Bến Nghé", district="Quận 3"),
    )
    assert result.normalized is None
    assert result.admin_unresolved is True


def test_name_shared_with_split_old_ward_is_unresolved_without_version_context():
    old = analyze_address(
        Address(raw="12 Phố Mẫu, Phường Cửa Nam, Quận Hoàn Kiếm, Hà Nội"),
        complete_parts(ward="Cửa Nam", district="Hoàn Kiếm", province="Hà Nội"),
    )
    current = analyze_address(
        Address(raw="12 Phố Mẫu, Phường Cửa Nam, Hà Nội"),
        complete_parts(ward="Cửa Nam", province="Hà Nội"),
    )
    assert old.normalized is None
    assert old.admin_unresolved is True
    assert current.normalized is None
    assert current.admin_unresolved is True
    assert values(current)["address_completeness"] == 1.0
    assert values(current)["address_legacy_admin_names"] is False


def test_current_name_that_survived_merger_is_not_flagged_as_legacy():
    result = analyze_address(
        Address(raw="12 Đường Mẫu, Phường Tân Định, Hồ Chí Minh"),
        complete_parts(ward="Phường Tân Định"),
    )
    assert result.normalized.ward == "Phường Tân Định"
    assert values(result)["address_legacy_admin_names"] is False


def test_long_extracted_street_does_not_break_optional_address_analysis():
    address = Address(raw="12 " + "M" * 200 + ", Phường Sài Gòn, Hồ Chí Minh")
    result = analyze_address(address, complete_parts(street="M" * 200))
    assert values(result)["address_completeness"] == 1.0
    assert result.normalized.raw == address.raw
    assert result.normalized.street is None


@pytest.mark.parametrize(
    ("overrides", "completeness", "missing_house", "missing_ward"),
    [
        ({"house_number": None}, 0.65, True, False),
        ({"ward": None}, 0.75, False, True),
        ({"province": None}, 0.85, False, False),
        ({"house_number": "   ", "ward": "   "}, 0.4, True, True),
    ],
)
def test_missing_components_reduce_completeness(
    overrides, completeness, missing_house, missing_ward
):
    result = analyze_address(Address(raw="Địa chỉ mẫu"), complete_parts(**overrides))
    assert values(result)["address_completeness"] == completeness
    assert values(result)["address_missing_house_number"] is missing_house
    assert values(result)["address_missing_ward"] is missing_ward


def test_landmark_only_does_not_count_landmark_digits_as_house_number():
    result = analyze_address(
        Address(raw="đối diện trường cấp 2, Hà Nội"),
        AddressParts(
            house_number="2", street="trường cấp 2", province="Hà Nội", landmark_only=True
        ),
    )
    assert values(result)["address_vague"] is True
    assert values(result)["address_missing_house_number"] is True
    assert values(result)["address_completeness"] == 0.15
    assert result.normalized is None


def test_response_schema_rejects_decision_fields_and_coerced_values():
    with pytest.raises(ValidationError):
        AddressParts.model_validate({"risk_score": 100})
    with pytest.raises(ValidationError):
        AddressParts.model_validate({"landmark_only": "false"})


class RecordedClient:
    def __init__(self, response):
        self.response = response
        self.payload = None

    async def generate(self, prompt_name, payload, response_schema):
        assert prompt_name == "address.v1.md"
        assert response_schema is AddressParts
        self.payload = payload
        return self.response


def test_extraction_masks_embedded_phones_in_every_sent_address_field():
    client = RecordedClient(complete_parts())
    address = Address(
        raw="12 Đường Mẫu, gọi +84000000001",
        street="gọi 0000000001",
        ward="Sài Gòn 0000000002",
        province="Hồ Chí Minh 0000000003",
    )
    result = asyncio.run(extract_address(client, address))

    assert result is not None
    assert all("0000000" not in value for value in client.payload.values() if value)
    assert client.payload["raw"].startswith("12 Đường Mẫu")


def test_optional_gemini_failure_leaves_address_signals_missing():
    assert (
        asyncio.run(
            extract_address(RecordedClient(None), Address(raw="12 Đường Mẫu, Phường Sài Gòn"))
        )
        is None
    )
