"""Real ADK specialists assess sanitized evidence; only the model transport is fake."""

import asyncio
import importlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field

from tests.test_intake import FakeDecisionLog

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
REASON = {
    "text_vi": "This phone has 2 of 4 past orders that failed because of the buyer.",
    "signal_keys": ["phone_failed_all", "phone_outcomes_all"],
}
DOC = {
    "order_id": "synthetic-order-private",
    "shop_id": "synthetic-shop-private",
    "external_id": "synthetic-external-private",
    "buyer_phone": "+840000000101",
    "buyer_phone_hash": "synthetic-hash-private",
    "buyer_name": "Synthetic Buyer Private",
    "recipient_phone": "+840000000102",
    "recipient_name": "Synthetic Recipient Private",
    "notes": "synthetic-private-note",
    "address": {"raw": "synthetic-private-address", "street": "synthetic-private-street"},
    "history": [{"buyer_name": "synthetic-private-history"}],
    "is_gift": True,
    "channel": "facebook",
    "cod_amount_vnd": 300000,
    "scoring": {
        "probability": 0.3,
        "risk_score": 30,
        "tier": "high",
        "expected_loss_vnd": 18000,
        "chosen_by": "tier rule",
        "features": {
            "phone_failed_all": 2,
            "phone_outcomes_all": 4,
            "phone_is_new": 0,
            "address_missing_house_number": 0,
            "address_parts_filled": 3,
            "phone_orders_24h": 1,
            "cod_vs_phone_avg_ratio": 1.0,
            "province_fail_rate_te": 0.3,
            "cod_amount_vnd": 300000,
            "unknown_private": "synthetic-feature-private",
            "unknown_numeric_id": 123456,
        },
    },
}


class FakeModel(BaseLlm):
    model: str = "fake-assessment-model"
    responses: list = Field(default_factory=list)
    requests: list[dict] = Field(default_factory=list)
    delay: float = 0.0

    async def generate_content_async(self, llm_request, stream=False):
        texts = [p.text for c in llm_request.contents for p in c.parts if p.text]
        payload = json.loads(texts[-1])
        self.requests.append({"input": payload, "request": str(llm_request), "text": texts[-1]})
        await asyncio.sleep(self.delay)
        response = self.responses.pop(0) if self.responses else {"reasons": [REASON]}
        if isinstance(response, Exception):
            raise response
        text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=1, candidates_token_count=1, total_token_count=2
            ),
        )


async def assess(doc=DOC, *, log=None, now=NOW, model=None):
    module = importlib.import_module("app.agents.assessment")
    return await module.assess(doc, log=log or FakeDecisionLog(), now=now, model=model)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("ASSESSMENT_DAILY_LIMIT", raising=False)


async def test_two_specialists_collaborate_without_changing_the_deterministic_score():
    model, log = FakeModel(), FakeDecisionLog()
    doc = deepcopy(DOC)
    before = deepcopy(doc)
    result = await assess(doc, model=model, log=log)
    assert result == {
        "status": "completed",
        "reasons": [REASON],
        "agents": ["risk_analyst", "evidence_verifier"],
        "model": "fake-assessment-model",
    }
    assert doc == before
    assert len(model.requests) == 2
    assert model.requests[1]["input"]["proposal"] == {"reasons": [REASON]}
    assert len(log.claims) == 1


async def test_prompts_omit_identifiers_personal_data_and_unknown_features():
    model = FakeModel()
    await assess(model=model)
    prompts = json.dumps(model.requests, ensure_ascii=False)
    for secret in (
        "synthetic-order-private",
        "synthetic-shop-private",
        "synthetic-external-private",
        "+840000000101",
        "+840000000102",
        "synthetic-hash-private",
        "Synthetic Buyer Private",
        "Synthetic Recipient Private",
        "synthetic-private-note",
        "synthetic-private-address",
        "synthetic-private-street",
        "synthetic-private-history",
        "synthetic-feature-private",
        "unknown_numeric_id",
    ):
        assert secret not in prompts
    first = model.requests[0]["input"]
    assert first["scoring"]["features"]["phone_failed_all"] == 2
    assert first["order_context"] == {
        "is_gift": True,
        "channel": "facebook",
        "cod_amount_vnd": 300000,
    }


@pytest.mark.parametrize(
    "response",
    [
        {"reasons": [{"text_vi": "The buyer often cancels orders.", "signal_keys": ["fake"]}]},
        {"reasons": [REASON], "action": "ai_call"},
        {"reasons": [REASON], "risk_score": 99},
        {"reasons": [REASON | {"signal_keys": ["phone_failed_all"]}]},
        {"reasons": [REASON | {"text_vi": "This phone has 4 failed deliveries."}]},
    ],
)
async def test_invalid_analyst_output_stops_before_the_verifier(response):
    model = FakeModel(responses=[response])
    with pytest.raises(ValueError):
        await assess(model=model)
    assert len(model.requests) == 1


@pytest.mark.parametrize("response", ["", "{}", {"reasons": [REASON], "tier": "very_high"}])
async def test_missing_or_invalid_verifier_output_fails_the_assessment(response):
    model = FakeModel(responses=[{"reasons": [REASON]}, response])
    with pytest.raises(ValueError):
        await assess(model=model)
    assert len(model.requests) == 2


async def test_verifier_cannot_add_evidence_the_analyst_did_not_select():
    doc = deepcopy(DOC)
    doc["scoring"]["features"]["address_missing_house_number"] = 1
    invented_selection = {
        "text_vi": "The address is missing a house number.",
        "signal_keys": ["address_missing_house_number"],
    }
    model = FakeModel(responses=[{"reasons": [REASON]}, {"reasons": [invented_selection]}])
    with pytest.raises(ValueError):
        await assess(doc, model=model)


async def test_duplicate_reasons_are_returned_once():
    model = FakeModel(responses=[{"reasons": [REASON, REASON]}, {"reasons": [REASON, REASON]}])
    assert (await assess(model=model))["reasons"] == [REASON]
    assert model.requests[1]["input"]["proposal"] == {"reasons": [REASON]}


@pytest.mark.parametrize(
    ("features", "reason"),
    [
        ({"phone_is_new": 1}, "This phone has no past orders."),
        ({"address_missing_house_number": 1}, "The address is missing a house number."),
        ({"address_parts_filled": 2}, "The address has only 2 of the 3 required parts."),
        ({"phone_orders_24h": 3}, "This phone placed 3 other orders in the last 24 hours."),
        (
            {"cod_vs_phone_avg_ratio": 2},
            "The COD amount is 2 times the phone's average past order.",
        ),
    ],
)
async def test_candidate_reasons_describe_only_actual_feature_values(features, reason):
    doc = deepcopy(DOC)
    doc["scoring"]["features"] = features
    model = FakeModel(responses=[{"reasons": []}, {"reasons": []}])
    await assess(doc, model=model)
    assert model.requests[0]["input"]["candidates"] == [
        {"text_vi": reason, "signal_keys": list(features)}
    ]


async def test_location_can_be_model_context_but_never_the_only_high_risk_reason():
    doc = deepcopy(DOC)
    doc["scoring"]["features"] = {"province_fail_rate_te": 0.8}
    model = FakeModel(responses=[{"reasons": []}, {"reasons": []}])
    log = FakeDecisionLog()
    assert await assess(doc, model=model, log=log) == {"status": "no_evidence", "reasons": []}
    assert not model.requests and not log.claims


async def test_shap_context_omits_unknown_keys_and_never_fabricates_values():
    doc = deepcopy(DOC)
    doc["scoring"]["shap"] = {
        "available": True,
        "method": "tree_shap",
        "approximate": False,
        "output": "model_failure_probability",
        "base_value": 0.1,
        "prediction": 0.3,
        "contributions": {"phone_failed_all": 0.2, "unknown_numeric_id": 0.5},
        "private": "synthetic-shap-private",
    }
    model = FakeModel()
    await assess(doc, model=model)
    shap = model.requests[0]["input"]["scoring"]["shap"]
    assert shap == {
        "available": True,
        "method": "tree_shap",
        "approximate": False,
        "output": "model_failure_probability",
        "base_value": 0.1,
        "prediction": 0.3,
        "contributions": {"phone_failed_all": 0.2},
    }
    assert "synthetic-shap-private" not in json.dumps(model.requests)
    assert "shap" not in (await _capture_unexplained())["scoring"]


async def _capture_unexplained():
    model = FakeModel()
    await assess(model=model)
    return model.requests[0]["input"]


async def test_missing_model_configuration_explicitly_disables_assessment():
    log = FakeDecisionLog()
    assert await assess(log=log) == {"status": "disabled", "reasons": []}
    assert not log.claims


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ({"scoring": None}, "unscored"),
        ({"confirmation": {"at": NOW, "via": "link"}}, "skipped"),
        ({"scoring": DOC["scoring"] | {"chosen_by": "hard rule: fully prepaid"}}, "skipped"),
        ({"scoring": DOC["scoring"] | {"chosen_by": "hard rule: invalid phone"}}, "skipped"),
        ({"skip_agents": True}, "skipped"),
    ],
)
async def test_unscored_hard_rule_and_confirmed_orders_use_no_model_requests(change, status):
    model, log = FakeModel(), FakeDecisionLog()
    assert await assess(DOC | change, model=model, log=log) == {"status": status, "reasons": []}
    assert not model.requests and not log.claims


async def test_daily_budget_is_shared_across_shops_and_rolls_over_in_utc(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_DAILY_LIMIT", "2")
    log, model = FakeDecisionLog(), FakeModel()
    assert (await assess(DOC, log=log, model=model))["status"] == "completed"
    assert (await assess(DOC | {"shop_id": "shop_b"}, log=log, model=model))[
        "status"
    ] == "completed"
    assert await assess(DOC | {"shop_id": "shop_c"}, log=log, model=model) == {
        "status": "quota_exhausted",
        "reasons": [],
    }
    assert len(model.requests) == 4
    assert set(log.claims) == {"assessment_budget:2026-10-14:1", "assessment_budget:2026-10-14:2"}
    assert all(row == {"at": NOW} for row in log.claims.values())
    assert (await assess(log=log, model=model, now=NOW + timedelta(days=1)))[
        "status"
    ] == "completed"


@pytest.mark.parametrize("limit", ["0", "31", "-1", "bad"])
async def test_invalid_budget_configuration_fails_before_calling_the_model(monkeypatch, limit):
    monkeypatch.setenv("ASSESSMENT_DAILY_LIMIT", limit)
    model, log = FakeModel(), FakeDecisionLog()
    with pytest.raises(ValueError):
        await assess(log=log, model=model)
    assert not model.requests and not log.claims


async def test_transport_failure_consumes_its_budget_without_retrying(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_DAILY_LIMIT", "1")
    model, log = FakeModel(responses=[OSError("synthetic transport failure")]), FakeDecisionLog()
    with pytest.raises(OSError):
        await assess(model=model, log=log)
    assert await assess(model=model, log=log) == {"status": "quota_exhausted", "reasons": []}
    assert len(model.requests) == 1


async def test_timeout_cancels_assessment_before_a_second_request(monkeypatch):
    module = importlib.import_module("app.agents.assessment")
    monkeypatch.setattr(module, "ASSESSMENT_TIMEOUT_SECONDS", 0.01)
    model, log = FakeModel(delay=0.1), FakeDecisionLog()
    with pytest.raises(TimeoutError):
        await assess(model=model, log=log)
    assert len(model.requests) == 1 and len(log.claims) == 1


async def test_simultaneous_shops_cannot_claim_the_same_budget_slot(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_DAILY_LIMIT", "1")
    model, log = FakeModel(delay=0.01), FakeDecisionLog()
    results = await asyncio.gather(
        assess(DOC | {"shop_id": "shop_a"}, model=model, log=log),
        assess(DOC | {"shop_id": "shop_b"}, model=model, log=log),
    )
    assert sorted(result["status"] for result in results) == ["completed", "quota_exhausted"]
    assert len(model.requests) == 2 and len(log.claims) == 1


async def test_more_than_three_analyst_reasons_cannot_trigger_a_verifier_request():
    model = FakeModel(responses=[{"reasons": [REASON] * 4}])
    with pytest.raises(ValueError):
        await assess(model=model)
    assert len(model.requests) == 1


async def test_conflicting_feature_evidence_is_rejected_without_spending_quota():
    doc = deepcopy(DOC)
    doc["scoring"]["features"]["phone_failed_all"] = 5
    model, log = FakeModel(), FakeDecisionLog()
    with pytest.raises(ValueError, match="Conflicting"):
        await assess(doc, model=model, log=log)
    assert not model.requests and not log.claims


def test_the_response_schema_is_accepted_by_vertex_ai():
    """Vertex AI rejects `examples` in a response schema; with them every live call failed."""
    from app.agents.assessment import _Selection

    assert "examples" not in json.dumps(_Selection.model_json_schema())


async def test_the_agents_read_plain_vietnamese():
    """Escaped text (\\u0110...) made gemini-3.1-flash-lite miscopy the candidate reasons."""
    model = FakeModel()
    await assess(model=model)
    text = model.requests[0]["text"]
    assert "\\u" not in text
    assert any(c["text_vi"] in text for c in model.requests[0]["input"]["candidates"])


def test_every_reason_cites_a_key_that_top_signals_uses():
    """The E3.3 reason check matches reasons to `top_signals` by key, so the names must agree."""
    from app.agents.assessment import _candidates
    from app.risk.features import SIGNALS
    from app.risk.model import top_signals

    features = {k: 0 for k in SIGNALS} | {
        "phone_failed_all": 1,
        "phone_outcomes_all": 2,
        "phone_orders_24h": 3,
        "cod_vs_phone_avg_ratio": 2,
        "address_missing_house_number": 1,
    }
    every = top_signals(features, dict.fromkeys(SIGNALS, 1.0), top=len(SIGNALS))
    cited = {key for reason in _candidates(features) for key in reason["signal_keys"]}
    assert "address_missing_house_number" in cited
    assert cited <= {s["key"] for s in every}
