"""Demo-only endpoints for the hackathon judges."""

from pydantic import ConfigDict, Field

from app.schemas.common import ApiModel, MaskedPhone


class DemoResetResult(ApiModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"seed": 42, "orders": 1000}]})

    seed: int
    orders: int = Field(ge=0)


class SpamSimulationResult(ApiModel):
    """Abuse scenario: 50 fake orders from 20 accounts to one phone."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "orders_created": 50,
                    "accounts": 20,
                    "phone_masked": "+84******999",
                    "contacts_made": 1,
                    "phone_blocked": True,
                }
            ]
        }
    )

    orders_created: int = Field(ge=0)
    accounts: int = Field(ge=0)
    phone_masked: MaskedPhone
    contacts_made: int = Field(ge=0, description="Target: exactly 1.")
    phone_blocked: bool
