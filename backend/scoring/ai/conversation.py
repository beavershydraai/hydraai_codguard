"""E3.2: optional chat features, with gift-aware name comparison in code."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import SignalGroup
from app.schemas.orders import OrderCreate
from scoring.ai.client import GeminiClient
from scoring.ai.models import ExtractedSignal
from scoring.ai.privacy import mask_phone_numbers, normalize_text

PROMPT_VERSION = "conversation.v1.md"


class ConversationParts(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    asked_details: bool
    rushed_close: bool
    buyer_name_in_chat: str | None = Field(max_length=100)


async def extract_conversation(
    client: GeminiClient, order: OrderCreate
) -> list[ExtractedSignal] | None:
    if not order.conversation_text or not order.conversation_text.strip():
        return None
    payload = {
        "conversation_text": mask_phone_numbers(order.conversation_text),
        "buyer_name": mask_phone_numbers(order.buyer_name),
        "recipient_name": mask_phone_numbers(order.recipient_name or ""),
        "is_gift": order.is_gift,
        "items": [
            {
                "name": mask_phone_numbers(item.name),
                "variant": mask_phone_numbers(item.variant or ""),
            }
            for item in order.items
        ],
    }
    parts = await client.generate(PROMPT_VERSION, payload, ConversationParts)
    if parts is None:
        return None
    chat_name = normalize_text(parts.buyer_name_in_chat or "")
    allowed_names = {normalize_text(order.buyer_name)}
    if order.is_gift and order.recipient_name:
        allowed_names.add(normalize_text(order.recipient_name))
    mismatch = bool(chat_name and chat_name not in allowed_names)
    return [
        ExtractedSignal(key=key, group=SignalGroup.CONVERSATION, label_vi=label, value=value)
        for key, label, value in [
            ("conversation_asked_details", "Khách có hỏi kỹ về sản phẩm", parts.asked_details),
            ("conversation_rushed_close", "Khách chốt đơn vội", parts.rushed_close),
            (
                "conversation_name_mismatch",
                "Tên trong hội thoại khác tên người đặt",
                mismatch,
            ),
        ]
    ]
