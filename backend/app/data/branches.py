"""Branches and their countries (config/branches.yaml): currency, local time, phone code, costs."""

import pathlib
from dataclasses import dataclass
from datetime import timedelta, timezone
from functools import cache

import yaml

from app.schemas.shops import ShopSettings

CONFIG = pathlib.Path(__file__).resolve().parents[2] / "config" / "branches.yaml"


@dataclass(frozen=True)
class Country:
    code: str
    currency: str
    minor_unit: int
    timezone_name: str
    tz: timezone  # fixed offset: none of these countries has daylight saving
    calling_code: str
    costs: dict

    @property
    def settings(self) -> ShopSettings:
        """The policy's costs in this country's currency."""
        c = self.costs
        return ShopSettings(
            failed_delivery_cost_vnd=c["failed_delivery"],
            confirmation_link_cost_vnd=c["confirmation_link"],
            ai_call_cost_vnd=c["ai_call"],
            deposit_request_cost_vnd=c["deposit_request"],
        )


@cache
def _config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


@cache
def country(code: str) -> Country:
    c = _config()["countries"][code]
    return Country(
        code=code,
        currency=c["currency"],
        minor_unit=c["minor_unit"],
        timezone_name=c["timezone"],
        tz=timezone(timedelta(hours=c["utc_offset_hours"])),
        calling_code=c["calling_code"],
        costs=c["costs"],
    )


def countries() -> list[str]:
    return list(_config()["countries"])


def branches() -> dict[str, str]:
    """{branch_id: country code}."""
    return {b: v["country"] for b, v in _config()["branches"].items()}


def default_branch() -> str:
    return _config()["default_branch"]


def country_of(doc: dict) -> Country:
    """The order's country; orders stored before branches existed are Vietnamese."""
    return country(doc.get("country") or "VN")
