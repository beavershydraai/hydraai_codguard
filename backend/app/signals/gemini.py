"""Gemini text calls shared by the signal extractors (E3.1; later E3.2 and E3.3).

Gemini reads text and returns JSON in a fixed schema. It never sets a score, tier or action.
Every failure (off, over the cap, timeout, error, bad JSON) returns None, and the caller falls back
to its rules. Settings come from the environment:

- GEMINI_MODEL: model id; Gemini is off while it is unset
- GEMINI_LOCATION: Agent Platform location, default `asia-southeast1`
- GOOGLE_CLOUD_PROJECT: project; credentials come from ADC, there is no API key
"""

import logging
import os
from collections.abc import Callable
from functools import lru_cache

from pydantic import BaseModel

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 3.0


class Gemini:
    def __init__(
        self,
        client,
        model: str,
        *,
        timeout_s: float = TIMEOUT_SECONDS,
        allow: Callable[[], bool] = lambda: True,
    ):
        """`allow` is the call cap: E1.4 plugs its quota in here so public demo paths cannot
        exhaust it."""
        self.client, self.model, self.timeout_s, self.allow = client, model, timeout_s, allow

    def generate[M: BaseModel](self, instruction: str, text: str, schema: type[M]) -> M | None:
        """`text` is data for the instruction, never instructions itself."""
        if not self.allow():
            log.info("Gemini call skipped: over the cap")
            return None
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=instruction,
            temperature=0,
            response_mime_type="application/json",
            response_schema=schema,
            http_options=types.HttpOptions(
                timeout=int(self.timeout_s * 1000),  # milliseconds
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=text, config=config
            )
            if isinstance(response.parsed, schema):
                return response.parsed
            return schema.model_validate_json(response.text)
        except Exception:  # Gemini is optional: never let it break the caller
            log.warning("Gemini call failed", exc_info=True)
            return None


@lru_cache
def get_gemini() -> Gemini | None:
    model = os.environ.get("GEMINI_MODEL")
    if not model:
        return None
    from google import genai

    client = genai.Client(
        enterprise=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("GEMINI_LOCATION", "asia-southeast1"),
    )
    return Gemini(client, model)
