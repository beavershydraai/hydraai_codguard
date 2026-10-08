"""Delivery outcomes from carriers or CSV, which update phone history."""

from datetime import datetime

from pydantic import ConfigDict, Field, model_validator

from app.schemas.common import ApiModel
from app.schemas.enums import Carrier, DeliveryResult
from app.schemas.orders import ImportRowError


class DeliveryOutcome(ApiModel):
    """Identify the order by `order_id` or by `external_id`."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "order_id": "ord_01",
                    "external_id": None,
                    "carrier": "ghn",
                    "tracking_code": "GHN0000001",
                    "result": "refused",
                    "occurred_at": "2026-10-12T15:30:00+07:00",
                }
            ]
        },
    )

    order_id: str | None = None
    external_id: str | None = None
    carrier: Carrier
    tracking_code: str | None = Field(default=None, max_length=64)
    result: DeliveryResult
    occurred_at: datetime

    @model_validator(mode="after")
    def _needs_an_id(self) -> "DeliveryOutcome":
        if not (self.order_id or self.external_id):
            raise ValueError("order_id or external_id is required")
        return self


class DeliveryOutcomeBatch(ApiModel):
    model_config = ConfigDict(extra="forbid")

    outcomes: list[DeliveryOutcome] = Field(min_length=1, max_length=1000)


class DeliveryImportResult(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"received": 120, "applied": 118, "unknown_orders": 1, "rejected": []}]
        }
    )

    received: int = Field(ge=0)
    applied: int = Field(ge=0)
    unknown_orders: int = Field(ge=0)
    rejected: list[ImportRowError] = Field(default_factory=list)
