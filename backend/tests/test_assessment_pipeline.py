"""Assessment must finish before a new order's deterministic decision is committed."""

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.agents import agent
from app.agents import assessment as real_assessment
from app.agents.agent import Pipeline
from app.agents.runner import run_new_order
from app.data.orders import order_document
from app.data.store import OrderStore
from app.decision import lifecycle
from app.risk import engine
from app.schemas.orders import OrderCreate
from tests.test_assessment import FakeModel
from tests.test_intake import FakeDecisionLog, FakeStore
from tests.test_lifecycle import scored_fields
from tests.test_order_store import MemoryClient
from tests.test_policy import NOW


@pytest.fixture
def pipe(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("ASSESSMENT_DAILY_LIMIT", raising=False)
    monkeypatch.setenv("PHONE_HASH_KEY", "test-key")
    order = OrderCreate.model_validate(OrderCreate.model_config["json_schema_extra"]["examples"][0])
    store = FakeStore()
    store.create(
        order_document(order, order_id="ord_test", shop_id="shop_a", phone_key=b"key", now=NOW)
    )
    fields = scored_fields("high", "call")
    fields["scoring"]["features"] = {"phone_is_new": 1, "address_missing_house_number": 1}
    monkeypatch.setattr(engine, "score", lambda doc, history: deepcopy(fields))
    return Pipeline(store=store, log=FakeDecisionLog(), now=NOW)


def install_assessor(monkeypatch, assess):
    # Replace only the network assessment boundary, leaving scoring, policy and ADK graphs real.
    monkeypatch.setattr(agent, "assessment", SimpleNamespace(assess=assess), raising=False)


@pytest.mark.asyncio
async def test_intake_graph_runs_both_real_agents_and_saves_their_verified_reason(
    pipe, monkeypatch
):
    reason = {"text_vi": "Địa chỉ thiếu số nhà.", "signal_keys": ["address_missing_house_number"]}
    model = FakeModel(responses=[{"reasons": [reason]}, {"reasons": [reason]}])
    assess = real_assessment.assess

    async def with_model(doc, **kwargs):
        return await assess(doc, model=model, **kwargs)

    monkeypatch.setattr(real_assessment, "assess", with_model)
    result = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    doc = pipe.store.get("ord_test")
    assert len(model.requests) == 2
    assert model.requests[1]["input"]["proposal"] == {"reasons": [reason]}
    assert result["action"] == "ai_call" and result["sent"] is True
    assert doc["scoring"]["reasons"] == [reason]
    assert doc["scoring"]["probability"] == 0.6 and doc["tier"] == "high"
    assert doc["scoring"]["assessment"]["agents"] == ["risk_analyst", "evidence_verifier"]


@pytest.mark.asyncio
async def test_assessment_runs_before_scoring_and_decision_are_committed(pipe, monkeypatch):
    observed = []

    async def assess(doc, **kwargs):
        stored = pipe.store.get("ord_test")
        observed.append((stored["scoring"], stored["decision"]))
        assert doc["scoring"]["probability"] == 0.6
        return {"status": "completed", "reasons": [], "agents": ["analyst", "verifier"]}

    install_assessor(monkeypatch, assess)
    result = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    assert observed == [(None, None)]
    assert result["action"] == "ai_call" and result["sent"] is True
    doc = pipe.store.get("ord_test")
    assert doc["scoring"]["assessment"]["status"] == "completed"
    assert doc["scoring"]["probability"] == 0.6 and doc["tier"] == "high"
    assert pipe.log.for_order("ord_test")[0]["assessment"]["status"] == "completed"


@pytest.mark.asyncio
async def test_assessment_cannot_mutate_the_scored_order(pipe, monkeypatch):
    async def assess(doc, **kwargs):
        doc["scoring"].update(probability=0.01, risk_score=1)
        doc.update(tier="low", contact_action="none")
        return {"status": "completed", "reasons": []}

    install_assessor(monkeypatch, assess)
    result = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    doc = pipe.store.get("ord_test")
    assert result["action"] == "ai_call"
    assert doc["scoring"]["probability"] == 0.6 and doc["tier"] == "high"


@pytest.mark.parametrize(
    "output",
    [
        {"status": "completed", "reasons": [], "action": "ship_now"},
        {"status": "quota_exhausted", "reasons": []},
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_over_budget_assessment_holds_without_contact(pipe, monkeypatch, output):
    async def assess(doc, **kwargs):
        return output

    install_assessor(monkeypatch, assess)
    result = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    assert result["action"] == "hold_for_review"
    assert pipe.store.get("ord_test")["status"] == "pending_review"
    assert pipe.log.claims == {}


@pytest.mark.asyncio
async def test_assessment_failure_holds_without_contact(pipe, monkeypatch):
    async def assess(doc, **kwargs):
        raise ValueError("Unsupported reason")

    install_assessor(monkeypatch, assess)
    result = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    assert result["action"] == "hold_for_review"
    assert pipe.store.get("ord_test")["scoring"] is None
    assert pipe.log.claims == {}


@pytest.mark.asyncio
async def test_order_changed_during_assessment_is_not_contacted(pipe, monkeypatch):
    async def assess(doc, **kwargs):
        pipe.store.docs["ord_test"].update(
            note="Edited while assessment ran", updated_at=NOW + timedelta(seconds=1)
        )
        return {"status": "completed", "reasons": []}

    install_assessor(monkeypatch, assess)
    result = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    assert result["action"] == "hold_for_review"
    assert pipe.store.get("ord_test")["note"] == "Edited while assessment ran"
    assert pipe.log.claims == {}


@pytest.mark.asyncio
async def test_no_model_skips_assessment_and_preserves_unscored_state(pipe, monkeypatch):
    monkeypatch.setattr(engine, "score", lambda doc, history: None)

    async def assess(doc, **kwargs):
        pytest.fail("Unscored orders must not invoke assessment")

    install_assessor(monkeypatch, assess)
    result = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    assert result["reason"] == "not_scored"
    assert pipe.store.get("ord_test")["decision"] is None


@pytest.mark.asyncio
async def test_rerun_does_not_assess_or_contact_again(pipe, monkeypatch):
    observed = []

    async def assess(doc, **kwargs):
        observed.append(doc["order_id"])
        return {"status": "completed", "reasons": []}

    install_assessor(monkeypatch, assess)
    first = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    repeated = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    assert first["sent"] is True and repeated["duplicate"] is True
    assert observed == ["ord_test"]


@pytest.mark.asyncio
async def test_failed_assessment_preserves_a_concurrent_winning_decision(pipe, monkeypatch):
    winning = []

    async def assess(doc, **kwargs):
        winning.append(lifecycle.score_order(pipe.store, pipe.store.get("ord_test"), NOW))
        raise ValueError("The slower assessment failed")

    install_assessor(monkeypatch, assess)
    result = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    assert result["duplicate"] is True
    assert pipe.store.get("ord_test")["decision"] == winning[0]["decision"]
    assert pipe.store.get("ord_test")["status"] == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_failure_after_this_run_commits_its_decision_still_reaches_review(pipe, monkeypatch):
    async def assess(doc, **kwargs):
        return {"status": "completed", "reasons": []}

    install_assessor(monkeypatch, assess)
    original_write = pipe.log.write
    first = True

    def write(row):
        nonlocal first
        if first:
            first = False
            raise ValueError("Decision log write failed")
        original_write(row)

    monkeypatch.setattr(pipe.log, "write", write)
    result = await run_new_order("ord_test", "shop_a", pipeline=pipe)
    assert result["action"] == "hold_for_review"
    assert pipe.store.get("ord_test")["status"] == "pending_review"
    assert pipe.log.claims == {}


def test_intake_review_fallback_preserves_a_decision_made_during_transaction_retry(pipe):
    before = pipe.store.get("ord_test")
    winning_decision = {"action": "ship_now", "decided_by": "staff"}

    def override(docs):
        docs["ord_test"].update(status="cleared_to_ship", decision=winning_decision)

    client = MemoryClient({"ord_test": before}, conflict=override)
    with pytest.raises(lifecycle.ExistingDecision):
        lifecycle.hold_for_review(
            OrderStore(client), "ord_test", NOW, guard_decision=True, expected_decision=None
        )
    assert client.docs["ord_test"]["decision"] == winning_decision
    assert client.docs["ord_test"]["status"] == "cleared_to_ship"


def test_prepared_score_rejects_an_edit_during_transaction_retry(pipe):
    before = pipe.store.get("ord_test")

    def edit(docs):
        docs["ord_test"].update(note="A concurrent edit")

    client = MemoryClient({"ord_test": before}, conflict=edit)
    with pytest.raises(lifecycle.StaleAssessment):
        lifecycle.commit_prepared_score(
            OrderStore(client), before, scored_fields("high", "call"), NOW
        )
    assert client.docs["ord_test"]["note"] == "A concurrent edit"
    assert client.docs["ord_test"]["decision"] is None
