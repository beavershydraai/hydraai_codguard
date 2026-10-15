import pytest

from app.data import policies
from app.data.policies import PolicyStore, VersionTaken


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
