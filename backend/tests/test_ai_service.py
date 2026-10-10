import asyncio

from app.schemas.common import Address
from app.schemas.enums import RiskTier
from app.schemas.scoring import RiskScore
from scoring.ai.client import GeminiClient
from scoring.ai.service import AIService
from tests.test_conversation_signals import order


def test_skipped_scoring_never_calls_gemini():
    async def run():
        client = GeminiClient(model="", project="")
        service = AIService(client)
        extraction = await service.extract(order(), skipped=True)
        assert extraction.signals == []
        score = RiskScore(
            id="synthetic-score",
            scored_at="2026-10-10T10:00:00+07:00",
            status="skipped",
            failed_delivery_cost_vnd=60000,
        )
        assert (await service.explain(score)).reasons == []
        assert client.calls_made == 0

    asyncio.run(run())


def test_address_edit_rereads_address_and_reuses_unchanged_chat():
    async def transport(model, instruction, payload, schema):
        if "house_number" in schema.model_fields:
            return {
                "house_number": "12",
                "street": "Phố Mẫu",
                "ward": "Phường Hoàn Kiếm",
                "district": None,
                "province": "Hà Nội",
                "landmark_only": False,
                "administrative_names": ["Phường Hoàn Kiếm", "Hà Nội"],
            }
        return {"asked_details": True, "rushed_close": False, "buyer_name_in_chat": None}

    async def run():
        client = GeminiClient(model="recorded-model", transport=transport)
        service = AIService(client)
        original = order(conversation_text="Khách: áo mẫu còn size M?")
        first = await service.extract(original)
        assert len(first.signals) == 8
        assert client.calls_made == 2
        edited = original.model_copy(update={"address": Address(raw="Số 15 Phố Mẫu, Hà Nội")})
        assert len((await service.extract(edited)).signals) == 8
        assert client.calls_made == 3

    asyncio.run(run())


def test_explanation_preserves_model_score_and_uses_fallback_without_credentials():
    score = RiskScore.model_validate(RiskScore.model_config["json_schema_extra"]["examples"][0])
    original = score.model_dump()
    score.reasons = []
    explained = asyncio.run(
        AIService(GeminiClient(model="", project="")).explain(
            score, facts={"phone_return_rate": {"returned_orders": 2, "past_orders": 4}}
        )
    )
    assert 1 <= len(explained.reasons) <= 3
    assert explained.risk_score == original["risk_score"]
    assert explained.probability == original["probability"]
    assert explained.tier == RiskTier.HIGH
    assert explained.expected_loss_vnd == original["expected_loss_vnd"]
    assert score.reasons == []
