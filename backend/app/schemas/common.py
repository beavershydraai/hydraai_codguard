"""Shared types: money, phone, address, errors."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import ContactBlockReason, ErrorCode

Vnd = Annotated[int, Field(ge=0, description="Amount in VND (integer, no decimals).")]
Phone = Annotated[
    str,
    Field(
        pattern=r"^\+?[0-9]{9,15}$",
        description="Phone number. Input accepts 0xxxxxxxxx or +84xxxxxxxxx; output is E.164.",
        examples=["+84000000001"],
    ),
]
MaskedPhone = Annotated[
    str, Field(description="Partially masked phone.", examples=["+84******001"])
]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class Address(ApiModel):
    """Delivery address. `raw` is what the buyer wrote; the parsed parts are filled when known.
    Province and ward follow the 2025 two-level administrative units."""

    raw: str = Field(min_length=3, max_length=500, examples=["Số 12 ngõ 34, phường Láng, Hà Nội"])
    street: str | None = Field(default=None, max_length=200, examples=["Số 12 ngõ 34"])
    ward: str | None = Field(default=None, max_length=100, examples=["Phường Láng"])
    province: str | None = Field(default=None, max_length=100, examples=["Hà Nội"])


class FieldError(ApiModel):
    loc: list[str | int] = Field(
        description="Path to the invalid field.", examples=[["body", "buyer_phone"]]
    )
    msg: str = Field(examples=["String should match pattern '^\\+?[0-9]{9,15}$'"])
    type: str = Field(examples=["string_pattern_mismatch"])


class ProblemDetail(BaseModel):
    """Error body (RFC 9457, `application/problem+json`)."""

    type: str = Field(default="about:blank")
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: ErrorCode
    errors: list[FieldError] | None = Field(default=None, description="Set for validation_error.")
    block_reasons: list[ContactBlockReason] | None = Field(
        default=None, description="Set for contact_blocked."
    )
