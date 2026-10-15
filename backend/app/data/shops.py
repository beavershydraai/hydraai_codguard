"""A shop's profile and its settings per country (docs/data-model.md): Firestore `shops/{shop_id}`.

The shop exists from its first read (onboarding, E7.1), with the country defaults of
config/branches.yaml: it works before the owner changes anything. The document keeps only what
the owner changed, so a later change to a default still reaches a shop that never touched it.
"""

from datetime import datetime

from google.api_core.exceptions import AlreadyExists

from app.data import branches
from app.data.store import _client, _intake_keys
from app.demo.world import SHOP_ID, SHOP_NAME
from app.schemas.shops import CountrySettings, Shop, ShopSettings, ShopUpdate

# What the decision code accepts as settings: one country's, the shop's per country, or None for
# the country defaults.
Settings = ShopSettings | dict[str, ShopSettings] | None


def default_name(shop_id: str) -> str:
    """The demo shop's name as the app shows it; any other shop is named after its id."""
    if shop_id == SHOP_ID:
        return SHOP_NAME
    return shop_id.removeprefix("shop_").replace("_", " ").title() or "the shop"


def settings_for(doc: dict, settings: Settings) -> ShopSettings:
    """The settings that apply to an order: the shop's for the order's country when given,
    otherwise that country's defaults."""
    country = branches.country_of(doc)
    if isinstance(settings, dict):
        settings = settings.get(country.code)
    return settings or country.settings


def _merged(code: str, doc: dict) -> ShopSettings:
    changed = (doc.get("countries") or {}).get(code, {})
    return ShopSettings.model_validate(branches.country(code).settings.model_dump() | changed)


def _key_last4(shop_id: str) -> str | None:
    key = next((k for k, (s, _, test) in _intake_keys().items() if s == shop_id and not test), None)
    return key[-4:] if key else None


def shop_view(shop_id: str, doc: dict) -> Shop:
    return Shop(
        id=shop_id,
        name=doc["name"],
        created_at=doc["created_at"],
        countries=[
            CountrySettings(
                country=code,
                currency=branches.country(code).currency,
                **_merged(code, doc).model_dump(),
            )
            for code in branches.countries()
        ],
        intake_api_key_last4=_key_last4(shop_id),
    )


class ShopStore:
    def __init__(self, client):
        self.client = client

    def _ref(self, shop_id: str):
        return self.client.collection("shops").document(shop_id)

    def _read(self, shop_id: str) -> dict | None:
        snapshot = self._ref(shop_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def _create(self, shop_id: str, doc: dict) -> dict:
        try:
            self._ref(shop_id).create(doc)
            return doc
        except AlreadyExists:  # another request created it first
            return self._read(shop_id)

    def _write(self, shop_id: str, doc: dict) -> None:
        self._ref(shop_id).set(doc)  # the policy_versions subcollection is not touched

    def get(self, shop_id: str, now: datetime) -> dict:
        new = {"name": default_name(shop_id), "created_at": now, "countries": {}}
        return self._read(shop_id) or self._create(shop_id, new)

    def name(self, shop_id: str) -> str:
        return (self._read(shop_id) or {}).get("name") or default_name(shop_id)

    def settings(self, shop_id: str) -> dict[str, ShopSettings]:
        """The shop's settings per country, defaults filled in. Reading never creates the shop."""
        doc = self._read(shop_id) or {}
        return {code: _merged(code, doc) for code in branches.countries()}

    def update(self, shop_id: str, update: ShopUpdate, now: datetime) -> dict:
        # ponytail: read-modify-write without a transaction; one owner edits the settings.
        doc = self.get(shop_id, now)
        if update.name:
            doc["name"] = update.name
        for change in update.countries or []:
            fields = change.model_dump(exclude_none=True, exclude={"country"})
            doc.setdefault("countries", {}).setdefault(change.country, {}).update(fields)
        self._write(shop_id, doc)
        return doc


def get_shop_store() -> ShopStore:
    return ShopStore(_client())
