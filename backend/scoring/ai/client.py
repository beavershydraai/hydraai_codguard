"""The only E3 Gemini gateway: bounded calls, timeout, parsing and input cache."""

import asyncio
import hashlib
import json
import logging
import math
import os
from collections import Counter, OrderedDict
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

PROMPTS = Path(__file__).parent / "prompts"
TEXT_LOCATION = "asia-southeast1"
logger = logging.getLogger(__name__)
Transport = Callable[[str, str, dict, type[BaseModel]], Awaitable[str | dict | None]]


class GeminiClient:
    """Reuse one instance per worker to retain cache and enforce its call budget.

    ``allow_call`` is the E1.4 hook: reserve a visitor/global budget before each
    actual SDK request, including retries. The default cap is local to this
    instance; cross-worker/visitor limits belong in the shared E1.4 hook.
    Transport injection allows offline recorded responses without credentials.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        project: str | None = None,
        timeout_seconds: float | None = None,
        max_calls: int | None = None,
        cache_size: int = 256,
        allow_call: Callable[[], bool] | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.model = os.getenv("GEMINI_MODEL", "") if model is None else model
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT", "") if project is None else project
        self.location = TEXT_LOCATION
        self.timeout_seconds = (
            float(os.getenv("GEMINI_TIMEOUT_SECONDS", "10"))
            if timeout_seconds is None
            else timeout_seconds
        )
        self.max_calls = (
            int(os.getenv("GEMINI_MAX_CALLS", "100")) if max_calls is None else max_calls
        )
        if (
            not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or self.max_calls < 0
            or cache_size < 0
        ):
            raise ValueError("Timeout must be positive; call cap and cache size nonnegative")
        self.calls_made = 0
        self.stats: Counter[str] = Counter()
        self._cache: OrderedDict[str, BaseModel] = OrderedDict()
        self._cache_size = cache_size
        self._allow_call = allow_call
        self._transport = transport
        self._sdk: Any = None

    def _record(self, event: str, prompt_name: str) -> None:
        self.stats[event] += 1
        logger.info("e3_gemini event=%s prompt_version=%s", event, prompt_name)

    async def _request(
        self, instruction: str, payload: dict, response_schema: type[BaseModel]
    ) -> str | dict | None:
        if self._transport is not None:
            return await self._transport(self.model, instruction, payload, response_schema)
        from google import genai
        from google.genai import types

        if self._sdk is None:
            self._sdk = genai.Client(
                enterprise=True,
                project=self.project,
                location=self.location,
                http_options=types.HttpOptions(
                    timeout=max(1, int(self.timeout_seconds * 1000)),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        response = await self._sdk.aio.models.generate_content(
            model=self.model,
            contents=json.dumps({"untrusted_data": payload}, ensure_ascii=False, sort_keys=True),
            config=types.GenerateContentConfig(
                system_instruction=instruction,
                response_mime_type="application/json",
                response_json_schema=response_schema.model_json_schema(),
                temperature=0,
            ),
        )
        return response.text

    async def generate[T: BaseModel](
        self, prompt_name: str, payload: dict, response_schema: type[T]
    ) -> T | None:
        """Parse strict structured output; retry invalid output once, fail open.

        Successful values alone are cached, keyed by the exact payload, prompt
        contents, configured model and response schema. Cache holds no raw text
        keys and is bounded. Return copies so callers cannot corrupt it.
        """
        if Path(prompt_name).name != prompt_name:
            raise ValueError("Prompt must be a versioned filename")
        instruction = (PROMPTS / prompt_name).read_text(encoding="utf-8")
        key = hashlib.sha256(
            json.dumps(
                [self.model, instruction, payload, response_schema.model_json_schema()],
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            self._record("cache_hit", prompt_name)
            return response_schema.model_validate(self._cache[key].model_dump()).model_copy(
                deep=True
            )
        if not self.model or (self._transport is None and not self.project):
            self._record("unavailable", prompt_name)
            return None
        for attempt in range(2):
            try:
                if self.calls_made >= self.max_calls or (
                    self._allow_call is not None and not self._allow_call()
                ):
                    self._record("call_cap", prompt_name)
                    return None
                self.calls_made += 1
                retry_instruction = instruction
                if attempt:
                    retry_instruction += (
                        "\nPrevious output failed schema validation. Follow the schema."
                    )
                async with asyncio.timeout(self.timeout_seconds):
                    raw = await self._request(retry_instruction, payload, response_schema)
                if raw is None:
                    self._record("empty_response", prompt_name)
                    return None
                value = (
                    response_schema.model_validate_json(raw)
                    if isinstance(raw, str)
                    else response_schema.model_validate(raw)
                )
            except ValidationError:
                self._record("invalid_response", prompt_name)
                continue
            except TimeoutError:
                self._record("timeout", prompt_name)
                return None
            except Exception:
                # SDK errors can include buyer text; never log their messages.
                self._record("error", prompt_name)
                return None
            self._record("success", prompt_name)
            if self._cache_size:
                self._cache[key] = value.model_copy(deep=True)
                if len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
            return value
        self._record("invalid_exhausted", prompt_name)
        return None

    async def aclose(self) -> None:
        if self._sdk is not None:
            await self._sdk.aio.aclose()
            self._sdk.close()
            self._sdk = None
