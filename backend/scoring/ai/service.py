"""E2 integration boundary: extract features and explain an existing score."""

from dataclasses import dataclass

from app.schemas.orders import OrderCreate
from app.schemas.scoring import RiskScore
from scoring.ai.address import AddressAnalysis, extract_address
from scoring.ai.client import GeminiClient
from scoring.ai.conversation import extract_conversation
from scoring.ai.models import ExtractedSignal
from scoring.ai.reasons import generate_reasons


@dataclass
class AIExtraction:
    address: AddressAnalysis | None = None
    conversation: list[ExtractedSignal] | None = None

    @property
    def signals(self) -> list[ExtractedSignal]:
        return (self.address.signals if self.address else []) + (self.conversation or [])


class AIService:
    """Call after hard rules, then explain E2's score without changing decisions.

    Extracted features deliberately have no contribution field. E2 must supply
    model contributions before using them in RiskScore.top_signals.
    """

    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    async def extract(self, order: OrderCreate, *, skipped: bool = False) -> AIExtraction:
        if skipped:
            return AIExtraction()
        # Each request has its own input hash, so editing the address preserves
        # the cached conversation analysis. Failures leave features missing.
        return AIExtraction(
            address=await extract_address(self.client, order.address),
            conversation=await extract_conversation(self.client, order),
        )

    async def explain(
        self,
        score: RiskScore,
        *,
        facts: dict[str, dict[str, str | int | float]] | None = None,
    ) -> RiskScore:
        reasons = (
            []
            if score.status == "skipped"
            else await generate_reasons(
                self.client, score.top_signals, tier=score.tier, facts=facts
            )
        )
        return score.model_copy(update={"reasons": reasons}, deep=True)
