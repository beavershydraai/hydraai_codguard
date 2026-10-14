"""Shop app sign-in."""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.common import ApiModel
from app.schemas.shops import Me


class LoginRequest(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"username": "admin@gmail.com", "password": "admin12345"}]}
    )

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "example-access-token",
                    "token_type": "bearer",
                    "expires_at": "2026-10-15T08:00:00+07:00",
                    "user": {
                        "user_id": "usr_admin",
                        "email": "admin@gmail.com",
                        "display_name": "Admin",
                        "role": "owner",
                        "shop_id": "shop_demo",
                    },
                }
            ]
        }
    )

    access_token: str = Field(description="Send as `Authorization: Bearer <token>`.")
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime = Field(description="The token stops working after this time.")
    user: Me
