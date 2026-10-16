"""A shop's tier policy and call automation, versioned (docs/data-model.md): Firestore
`shops/{shop_id}/policy_versions/{version:06d}`. A shop that never changed its policy uses the
default one (config/cod_guard_rules_apac.yaml, version 1). A change is a new version in force from
the moment it is saved; decisions keep the version they were made under.
"""

from datetime import datetime

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from app.data.store import _client
from app.decision.policy import check, default_policy
from app.schemas.shops import Policy, PolicyUpdate


class VersionTaken(Exception):
    """Another change saved the same version number first."""


class PolicyStore:
    def __init__(self, client):
        self.client = client

    def _versions(self, shop_id: str):
        return self.client.collection("shops").document(shop_id).collection("policy_versions")

    def _stored(self, shop_id: str, limit: int | None = None) -> list[Policy]:
        query = self._versions(shop_id).order_by("version", direction=firestore.Query.DESCENDING)
        if limit:
            query = query.limit(limit)
        return [Policy.model_validate(d.to_dict()) for d in query.stream()]

    def current(self, shop_id: str) -> Policy:
        stored = self._stored(shop_id, limit=1)
        return stored[0] if stored else default_policy()

    def versions(self, shop_id: str) -> list[Policy]:
        """Newest first, ending with the default policy."""
        return self._stored(shop_id) + [default_policy()]

    def save(self, shop_id: str, update: PolicyUpdate, by: str, now: datetime) -> Policy:
        """Store the change as the next version. Raises ValueError for a policy the engine
        rejects, VersionTaken when another change took the number."""
        current = self.current(shop_id)
        policy = check(
            Policy(
                version=current.version + 1,
                effective_from=now,
                updated_by=by,
                tiers=update.tiers,
                automation=update.automation or current.automation,
                random_tests=(
                    current.random_tests if update.random_tests is None else update.random_tests
                ),
            )
        )
        self._create(shop_id, policy)
        return policy

    def _create(self, shop_id: str, policy: Policy) -> None:
        try:
            self._versions(shop_id).document(f"{policy.version:06d}").create(
                policy.model_dump(mode="json")
            )
        except AlreadyExists:
            raise VersionTaken from None


def get_policy_store() -> PolicyStore:
    return PolicyStore(_client())
