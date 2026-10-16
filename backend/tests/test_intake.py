import pickle
from copy import deepcopy
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.agents.log import get_decision_log
from app.data.phone import decrypt_phone
from app.data.store import get_store
from app.main import create_app
from app.risk import artifacts, engine
from app.risk.jobs.train import train
from app.schemas.orders import OrderCreate
from tests.risk_data import START, orders

ORDER = OrderCreate.model_config["json_schema_extra"]["examples"][0]


def project(doc, fields):
    """Only `fields` (dotted paths) of a document, as a Firestore projection returns it."""
    out = {}
    for path in fields:
        *parents, last = path.split(".")
        src, dst = doc, out
        for key in parents:
            src = (src or {}).get(key)
            if not isinstance(src, dict):
                break
            dst = dst.setdefault(key, {})
        else:
            if isinstance(src, dict) and last in src:
                dst[last] = deepcopy(src[last])
    return out


class FakeStore:
    def __init__(self):
        self.docs = {}

    def create(self, doc):
        if doc["order_id"] in self.docs:
            return self.docs[doc["order_id"]]
        self.docs[doc["order_id"]] = doc
        return None

    def get(self, order_id):
        doc = self.docs.get(order_id)
        return deepcopy(doc) if doc else None

    def update(self, order_id, fields):
        self.docs[order_id].update(fields)

    def transact(self, order_id, fn):
        if order_id not in self.docs:
            raise ValueError("order_not_found")
        result = fn(deepcopy(self.docs[order_id]))
        self.docs[order_id] = deepcopy(result)
        return result

    # The inbox's queries, as Firestore answers them (app/data/store.py).
    def _filtered(self, shop_id, f):
        return [
            d
            for d in self.docs.values()
            if d["shop_id"] == shop_id
            and (not f.branches or d.get("branch_id") in f.branches)
            and (not f.statuses or d.get("status") in f.statuses)
            and (not f.tiers or d.get("tier") in f.tiers)
            and (f.placed_from is None or d["placed_at"] >= f.placed_from)
            and (f.placed_to is None or d["placed_at"] <= f.placed_to)
        ]

    def page(self, shop_id, filters, *, sort, after, limit, fields):
        field = sort.lstrip("-")
        # Firestore leaves out documents without the sort field and sorts null lowest.
        rows = [d for d in self._filtered(shop_id, filters) if field in d]
        rows.sort(
            key=lambda d: (d[field] is not None, d[field] or 0, d["order_id"]),
            reverse=sort.startswith("-"),
        )
        if after:
            if after not in self.docs:
                raise LookupError(after)
            ids = [d["order_id"] for d in rows]
            rows = rows[ids.index(after) + 1 :] if after in ids else []
        return [project(d, fields) for d in rows[:limit]], len(rows) > limit

    def count(self, shop_id, filters):
        return len(self._filtered(shop_id, filters))

    def select(self, shop_id, filters, fields):
        return [project(d, fields) for d in self._filtered(shop_id, filters)]

    def due(self, statuses, now, limit):
        rows = [
            d
            for d in self.docs.values()
            if d["status"] in statuses
            and ((d.get("decision") or {}).get("next_action_at") or now + now.resolution) <= now
        ]
        rows.sort(key=lambda d: d["decision"]["next_action_at"])
        return [project(d, ("order_id", "shop_id")) for d in rows[:limit]]

    def last_change(self, shop_id):
        times = [d["updated_at"] for d in self.docs.values() if d["shop_id"] == shop_id]
        return max(times, default=None)

    def find(self, shop_id, field, values, fields):
        return [
            project(d, fields)
            for d in self.docs.values()
            if d["shop_id"] == shop_id and d.get(field) in values
        ]

    def history(self, phone_hash, before):
        return [
            d
            for d in self.docs.values()
            if d["buyer_phone_hash"] == phone_hash and d["placed_at"] < before
        ]


class FakeDecisionLog:
    """In-memory stand-in for app.agents.log.DecisionLog, with the same atomic claim."""

    def __init__(self):
        self.rows = {}
        self.claims = {}

    def write(self, row):
        self.rows[row["order_id"], row["decided_at"]] = deepcopy(row)

    def for_order(self, order_id):
        rows = [r for r in self.rows.values() if r["order_id"] == order_id]
        return sorted(rows, key=lambda r: r["decided_at"])

    def claim(self, key, record):
        if key in self.claims:
            return False
        self.claims[key] = deepcopy(record)
        return True

    def claimed(self, key):
        return self.claims.get(key)


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv(
        "INTAKE_API_KEYS",
        "key-a:shop_a,key-b:shop_b,key-t:shop_a:noagents,key-sg:shop_a:branch_SG:noagents",
    )
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))  # no model yet
    engine._cache.clear()
    store, decisions = FakeStore(), FakeDecisionLog()
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_decision_log] = lambda: decisions
    return TestClient(app), store


def post(client, key, body=ORDER):
    headers = {"X-Api-Key": key} if key else {}
    return client.post("/api/v1/intake/orders", json=body, headers=headers)


def test_intake_rejects_missing_or_unknown_key(api):
    client, _ = api
    for key in (None, "nope"):
        response = post(client, key)
        assert response.status_code == 401
        assert response.json()["code"] == "unauthorized"


def test_intake_stores_a_normalised_order(api):
    client, store = api
    response = post(client, "key-a")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "new" and body["duplicate"] is False
    doc = store.docs[body["order_id"]]
    assert doc["shop_id"] == "shop_a"
    assert decrypt_phone(doc["buyer_phone"]) == "+84000000001"
    assert doc["buyer_phone_hash"]


def test_a_noagents_test_key_marks_the_order_to_skip_the_agents(api):
    client, store = api
    tested = post(client, "key-t", ORDER | {"external_id": "TEST-1"}).json()
    normal = post(client, "key-a", ORDER | {"external_id": "TEST-2"}).json()
    assert store.docs[tested["order_id"]]["shop_id"] == "shop_a"
    assert store.docs[tested["order_id"]]["skip_agents"] is True
    assert "skip_agents" not in store.docs[normal["order_id"]]


def test_the_key_sets_the_branch_country_and_currency(api):
    client, store = api
    default = post(client, "key-a", ORDER | {"external_id": "B-1"}).json()
    assert {
        k: store.docs[default["order_id"]][k] for k in ("branch_id", "country", "currency")
    } == {
        "branch_id": "branch_VN_HCM",
        "country": "VN",
        "currency": "VND",
    }
    sg = ORDER | {"external_id": "B-2", "buyer_phone": "+6500000042", "currency": "SGD"}
    doc = store.docs[post(client, "key-sg", sg).json()["order_id"]]
    assert (doc["branch_id"], doc["country"], doc["currency"]) == ("branch_SG", "SG", "SGD")
    assert decrypt_phone(doc["buyer_phone"]) == "+6500000042" and doc["buyer_phone_hash"]
    assert doc["skip_agents"] is True


def test_an_order_in_another_currency_than_its_branch_is_rejected(api):
    client, store = api
    response = post(client, "key-sg", ORDER | {"external_id": "B-3", "currency": "VND"})
    assert response.status_code == 422
    assert "SGD" in response.json()["detail"]


def test_intake_is_idempotent_on_external_id_per_shop(api):
    client, store = api
    first = post(client, "key-a").json()
    again = post(client, "key-a").json()
    other_shop = post(client, "key-b").json()
    assert again == {"order_id": first["order_id"], "status": "new", "duplicate": True}
    assert other_shop["order_id"] != first["order_id"]
    assert len(store.docs) == 2


def test_intake_without_a_model_stores_the_order_unscored(api):
    client, store = api
    doc = store.docs[post(client, "key-a").json()["order_id"]]
    assert doc["scoring"] is None


def test_intake_scores_the_order_when_a_model_exists(api):
    client, store = api
    model, _, _ = train(orders(), START + timedelta(days=200), None)
    artifacts.write("latest/model1.pkl", pickle.dumps(model))
    engine._cache.clear()
    doc = store.docs[post(client, "key-a").json()["order_id"]]
    engine._cache.clear()
    assert 0 <= doc["scoring"]["probability"] <= 1
    assert doc["scoring"]["chosen_by"] and doc["contact_action"]
    assert doc["scoring"]["features"]["address_missing_house_number"] == 0


def test_intake_returns_the_decided_status_and_duplicate_preserves_it(api, monkeypatch):
    client, store = api
    from tests.test_lifecycle import scored_fields

    monkeypatch.setattr(engine, "score", lambda doc, history: scored_fields("high", "call"))
    first = post(client, "key-a").json()
    assert first["status"] == "awaiting_confirmation"
    again = post(client, "key-a").json()
    assert again == {
        "order_id": first["order_id"],
        "status": "awaiting_confirmation",
        "duplicate": True,
    }
    doc = store.docs[first["order_id"]]
    assert doc["decision"]["action"] == "ai_call"
    assert [e["type"] for e in doc["timeline"]] == ["decided", "scored", "created"]


def test_scoring_failure_holds_an_intake_order_for_review(api, monkeypatch):
    """E4.7: a pipeline that keeps failing hands the order to a person, never to the buyer."""
    client, store = api

    def fail(doc, history):
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(engine, "score", fail)
    response = post(client, "key-a")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending_review"
    doc = store.docs[body["order_id"]]
    assert doc["scoring"] is None
    assert doc["decision"]["action"] == "hold_for_review"
