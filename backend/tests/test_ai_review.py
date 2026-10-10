"""Focused regressions found while reviewing E3's privacy boundary."""

import asyncio

import pytest

from app.schemas.orders import OrderCreate
from scoring.ai.client import GeminiClient
from scoring.ai.conversation import extract_conversation


@pytest.mark.parametrize("separator", ["\u00a0", "\u202f", "\n", "\u200b"])
def test_phone_with_unicode_separators_is_masked_before_model_call(separator):
    synthetic_phone = separator.join(("+84", "0000", "00023"))
    order = OrderCreate(
        channel="facebook",
        buyer_name="Khách Mẫu Kiểm Tra",
        buyer_phone="+84000000023",
        address={"raw": "12 Đường Mẫu, phường Sài Gòn, Hồ Chí Minh"},
        items=[{"name": "Áo mẫu", "quantity": 1, "unit_price_vnd": 150000}],
        placed_at="2026-10-09T10:15:00+07:00",
        conversation_text=f"Khách: chốt áo mẫu, liên hệ {synthetic_phone} nhé.",
    )
    submitted = []

    async def transport(model, instruction, payload, response_schema):
        submitted.append(payload)
        return {"asked_details": False, "rushed_close": True, "buyer_name_in_chat": None}

    result = asyncio.run(
        extract_conversation(GeminiClient(model="recorded-model", transport=transport), order)
    )
    assert result is not None
    assert synthetic_phone not in submitted[0]["conversation_text"]
    assert "[PHONE]" in submitted[0]["conversation_text"]
