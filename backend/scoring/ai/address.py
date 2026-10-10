"""E3.1: Gemini splits text; code computes address features and resolves names."""

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import Address
from app.schemas.enums import SignalGroup
from scoring.ai.admin import resolve_admin
from scoring.ai.models import ExtractedSignal
from scoring.ai.privacy import mask_phone_numbers

if TYPE_CHECKING:
    from scoring.ai.client import GeminiClient


class AddressParts(BaseModel):
    """As-written text only. Gemini has no administrative mapping or score fields."""

    model_config = ConfigDict(extra="forbid", strict=True)

    house_number: str | None = Field(default=None, max_length=50)
    street: str | None = Field(default=None, max_length=200)
    ward: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    landmark_only: bool = False
    administrative_names: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("house_number", "street", "ward", "district", "province")
    @classmethod
    def trim_parts(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class AddressAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: list[ExtractedSignal]
    normalized: Address | None
    admin_unresolved: bool
    parts: AddressParts


def analyze_address(address: Address, parts: AddressParts) -> AddressAnalysis:
    """Fixed feature weights: house .35, street .25, ward .25, province .15.

    The same parts receive the same completeness, including legacy or unresolved
    admin names. Landmark descriptions contribute only their written admin parts,
    capped at .30; their numbers do not count as delivery house numbers.
    """
    has_house = bool(parts.house_number) and not parts.landmark_only
    has_street = bool(parts.street) and not parts.landmark_only
    completeness = round(
        0.35 * has_house
        + 0.25 * has_street
        + 0.25 * bool(parts.ward)
        + 0.15 * bool(parts.province),
        2,
    )
    if parts.landmark_only:
        completeness = min(completeness, 0.30)
    province, ward, legacy = resolve_admin(parts.province, parts.ward, parts.district)
    normalized = None
    if province is not None and ward is not None and not parts.landmark_only:
        street = " ".join(part for part in (parts.house_number, parts.street) if part) or None
        # Preserve long text in raw and parts without violating Address's limit
        # or silently truncating delivery instructions.
        if street is not None and len(street) > 200:
            street = None
        normalized = Address(raw=address.raw, street=street, ward=ward, province=province)
    features = [
        ("address_completeness", "Mức đầy đủ của địa chỉ", completeness),
        ("address_missing_house_number", "Địa chỉ thiếu số nhà", not has_house),
        ("address_missing_ward", "Địa chỉ thiếu phường/xã", not bool(parts.ward)),
        ("address_vague", "Địa chỉ mơ hồ", parts.landmark_only),
        ("address_legacy_admin_names", "Địa chỉ dùng tên địa giới cũ", legacy),
    ]
    return AddressAnalysis(
        signals=[
            ExtractedSignal(key=key, group=SignalGroup.ADDRESS_QUALITY, label_vi=label, value=value)
            for key, label, value in features
        ],
        normalized=normalized,
        admin_unresolved=province is None or ward is None,
        parts=parts,
    )


async def extract_address(client: "GeminiClient", address: Address) -> AddressAnalysis | None:
    """None means optional Gemini extraction failed: leave model features missing."""
    payload = {
        key: mask_phone_numbers(value) if value is not None else None
        for key, value in address.model_dump().items()
    }
    parts = await client.generate("address.v1.md", payload, AddressParts)
    return analyze_address(address, parts) if parts is not None else None
