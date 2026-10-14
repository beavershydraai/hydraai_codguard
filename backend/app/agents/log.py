"""The pipeline's own records (E4.7): an append-only decision log and the claims that keep a
rerun from contacting the buyer twice.

`decision_log` is business history and does not depend on ADK session state, which a session
service may drop. Its fields are the subset of `observability.decision_log` in the rule set that
the current engine can fill; the seven outcome probabilities arrive with the E2.5 model.
"""

from datetime import datetime
from functools import lru_cache

from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore_v1.base_query import FieldFilter

from app.agents import routes
from app.data.store import get_store
from app.schemas.scoring import Decision


def entry(doc: dict, decision: Decision, *, workflow: str, step: str) -> dict:
    """One decision_log row for an order. `probs` stays empty until the model predicts the seven
    outcomes; `failure_probability` is what the current binary model reports."""
    scoring = doc.get("scoring") or {}
    return {
        "order_id": doc["order_id"],
        "shop_id": doc["shop_id"],
        "workflow": workflow,
        "decision_step": step,
        "decided_at": decision.decided_at,
        "action": decision.action.value,
        "rule_id": routes.rule_id(scoring.get("chosen_by")),
        "rule_set_version": routes.rule_set_version(),
        "policy_version": decision.policy_version,
        "tier": doc.get("tier"),
        "probs": {o: p for o, p in (scoring.get("outcome_probabilities") or {}).items()},
        "failure_probability": scoring.get("probability"),
        "expected_loss_vnd": decision.expected_loss_vnd,
        "action_cost_vnd": decision.contact_cost_vnd,
        "block_reason": [r.value for r in decision.block_reasons],
        "propensity": doc.get("action_probability", 1.0),
        "explore": bool(doc.get("random_slice")),
    }


class DecisionLog:
    def __init__(self, client):
        self.entries = client.collection("decision_log")
        self.claims = client.collection("pipeline_claims")

    def write(self, row: dict) -> None:
        """Append one decision. The id is the order and the moment it was decided, so a retried
        node rewrites the same row instead of adding a second one."""
        self.entries.document(_row_id(row)).set(row)

    def for_order(self, order_id: str) -> list[dict]:
        query = self.entries.where(filter=FieldFilter("order_id", "==", order_id)).order_by(
            "decided_at"
        )
        return [d.to_dict() for d in query.stream()]

    def claim(self, key: str, record: dict) -> bool:
        """Take `key` exactly once. True for the caller that may perform the side effect, False
        when someone already did. The create is atomic, so two runs cannot both win."""
        try:
            self.claims.document(key).create(record)
            return True
        except AlreadyExists:
            return False

    def claimed(self, key: str) -> dict | None:
        snapshot = self.claims.document(key).get()
        return snapshot.to_dict() if snapshot.exists else None


def _row_id(row: dict) -> str:
    decided_at = row["decided_at"]
    stamp = decided_at.isoformat() if isinstance(decided_at, datetime) else str(decided_at)
    return f"{row['order_id']}_{stamp}"


@lru_cache
def get_decision_log() -> DecisionLog:
    return DecisionLog(get_store().client)
