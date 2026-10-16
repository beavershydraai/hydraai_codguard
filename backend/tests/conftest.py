from copy import deepcopy

import pytest

from app.data import policies, shops
from app.data.policies import PolicyStore, VersionTaken
from app.data.shops import ShopStore

# 32 zero bytes: a test key, never a real one.
TEST_PHONE_ENC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@pytest.fixture(autouse=True)
def phone_enc_key(monkeypatch):
    """Phones are stored encrypted (app/data/phone.py); tests use a fixed test key."""
    monkeypatch.setenv("PHONE_ENC_KEY", TEST_PHONE_ENC_KEY)


@pytest.fixture(autouse=True)
def policy_versions(monkeypatch):
    """Shop policy versions in memory instead of Firestore: {shop_id: [Policy]}. Empty, every
    shop runs the default policy, as before policies could be changed."""
    stored: dict[str, list] = {}

    def read(self, shop_id, limit=None):
        return sorted(stored.get(shop_id, []), key=lambda p: p.version, reverse=True)[:limit]

    def create(self, shop_id, policy):
        if any(p.version == policy.version for p in stored.get(shop_id, [])):
            raise VersionTaken
        stored.setdefault(shop_id, []).append(policy)

    monkeypatch.setattr(policies, "_client", lambda: None)
    monkeypatch.setattr(PolicyStore, "_stored", read)
    monkeypatch.setattr(PolicyStore, "_create", create)
    return stored


@pytest.fixture(autouse=True)
def shop_docs(monkeypatch):
    """Shop documents in memory instead of Firestore: {shop_id: doc}. Empty, every shop runs the
    country defaults of config/branches.yaml."""
    docs: dict[str, dict] = {}

    def create(self, shop_id, doc):
        return docs.setdefault(shop_id, deepcopy(doc))

    monkeypatch.setattr(shops, "_client", lambda: None)
    monkeypatch.setattr(ShopStore, "_read", lambda self, shop_id: deepcopy(docs.get(shop_id)))
    monkeypatch.setattr(ShopStore, "_create", create)
    monkeypatch.setattr(ShopStore, "_write", lambda self, i, doc: docs.update({i: deepcopy(doc)}))
    return docs


@pytest.fixture(autouse=True)
def automation_on(request, monkeypatch):
    """Most tests check what the agent does by itself, so they run with automation on. The real
    default is `suggest` (the shop accepts every contact); tests of it are marked
    `default_automation`."""
    if request.node.get_closest_marker("default_automation"):
        return
    from app.decision import policy
    from app.schemas.shops import CallAutomation

    auto = policy.default_policy().model_copy(update={"automation": CallAutomation(mode="auto")})
    monkeypatch.setattr(policy, "default_policy", lambda: auto)
    monkeypatch.setattr(policies, "default_policy", lambda: auto)
