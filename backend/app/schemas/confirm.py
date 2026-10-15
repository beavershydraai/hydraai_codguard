"""Buyer confirmation page (public, no login; the link token is the credential)."""

from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.common import Address, ApiModel, MaskedPhone, Vnd
from app.schemas.enums import BuyerAction


class BuyerItem(ApiModel):
    name: str
    variant: str | None = None
    quantity: int = Field(ge=1)


class BuyerOrderView(ApiModel):
    """What the buyer sees. Personal data is partially masked."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "shop_name": "Sample Fashion Shop",
                    "order_ref": "A7K2",
                    "items": [{"name": "Basic T-shirt", "variant": "Size M, black", "quantity": 2}],
                    "cod_amount_vnd": 330000,
                    "recipient_name_masked": "Nguyễn V** A",
                    "phone_masked": "+84******001",
                    "address_masked": "Số 1* ngõ 3*, phường Láng, Hà Nội",
                    "expires_at": "2026-10-11T10:15:06+07:00",
                    "allowed_actions": ["confirm", "edit_address", "cancel", "not_ordered"],
                    "responded_action": None,
                }
            ]
        }
    )

    shop_name: str
    order_ref: str = Field(description="Short code the buyer can quote to the shop.")
    items: list[BuyerItem]
    cod_amount_vnd: Vnd
    recipient_name_masked: str
    phone_masked: MaskedPhone
    address_masked: str
    expires_at: datetime = Field(description="48 hours after the link was sent.")
    allowed_actions: list[BuyerAction]
    responded_action: BuyerAction | None = Field(
        default=None, description="Set if the buyer already answered."
    )


class BuyerResponse(ApiModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"action": "confirm", "new_address": None},
                {
                    "action": "edit_address",
                    "new_address": {"raw": "Số 15 ngõ 34, phường Láng, Hà Nội"},
                },
            ]
        },
    )

    action: BuyerAction
    new_address: Address | None = Field(default=None, description="Required for edit_address.")


class BuyerResponseResult(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"action": "confirm", "message_vi": "Thank you. Your order is confirmed."}]
        }
    )

    action: BuyerAction
    message_vi: str
