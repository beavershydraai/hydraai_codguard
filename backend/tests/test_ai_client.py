import asyncio
import logging

import pytest
from pydantic import BaseModel, ConfigDict

from scoring.ai.client import GeminiClient


class Response(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    flag: bool


@pytest.mark.parametrize("timeout", [float("inf"), float("nan")])
def test_nonfinite_timeout_cannot_disable_the_request_deadline(timeout):
    with pytest.raises(ValueError):
        GeminiClient(timeout_seconds=timeout)


def test_invalid_output_retries_once_then_caches_by_payload_and_schema():
    requests = []

    async def transport(model, instruction, payload, response_schema):
        requests.append((model, instruction, payload, response_schema))
        if len(requests) == 1:
            return {"flag": True, "risk_score": 99}
        return {"flag": True}

    async def run():
        client = GeminiClient(model="recorded-model", transport=transport)
        first = await client.generate("conversation.v1.md", {"chat": "chốt"}, Response)
        assert first.flag is True
        first.flag = False
        cached = await client.generate("conversation.v1.md", {"chat": "chốt"}, Response)
        assert cached.flag is True
        assert client.calls_made == 2
        await client.generate("conversation.v1.md", {"chat": "sửa"}, Response)
        assert client.calls_made == 3
        await client.aclose()

    asyncio.run(run())
    assert "Untrusted" in requests[0][1]


def test_cap_counts_retries_and_hook_disallows_calls():
    async def transport(*args):
        return {"flag": "not bool"}

    async def run():
        client = GeminiClient(model="recorded-model", transport=transport, max_calls=1)
        assert await client.generate("conversation.v1.md", {}, Response) is None
        assert client.calls_made == 1
        assert client.stats["call_cap"] == 1
        blocked = GeminiClient(
            model="recorded-model", transport=transport, allow_call=lambda: False
        )
        assert await blocked.generate("conversation.v1.md", {}, Response) is None
        assert blocked.calls_made == 0

    asyncio.run(run())


def test_timeout_error_and_unconfigured_client_are_optional(caplog):
    async def slow(*args):
        await asyncio.sleep(1)

    async def broken(*args):
        raise RuntimeError("private buyer text must never be logged")

    async def run():
        slow_client = GeminiClient(model="recorded-model", transport=slow, timeout_seconds=0.001)
        assert await slow_client.generate("conversation.v1.md", {}, Response) is None
        assert slow_client.stats["timeout"] == 1
        error_client = GeminiClient(model="recorded-model", transport=broken)
        assert await error_client.generate("conversation.v1.md", {}, Response) is None
        assert error_client.stats["error"] == 1
        unconfigured = GeminiClient(model="", project="")
        assert await unconfigured.generate("conversation.v1.md", {}, Response) is None
        assert unconfigured.calls_made == 0

    with caplog.at_level(logging.INFO):
        asyncio.run(run())
    assert "private buyer text" not in caplog.text


def test_environment_model_text_region_and_cap(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "configured-model")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "synthetic-project")
    monkeypatch.setenv("GEMINI_LIVE_LOCATION", "us-central1")
    monkeypatch.setenv("GEMINI_MAX_CALLS", "0")
    client = GeminiClient()
    assert client.model == "configured-model"
    assert client.location == "asia-southeast1"
    assert client.max_calls == 0


def test_cache_evicts_and_does_not_cache_failed_calls():
    responses = iter([None, {"flag": True}, {"flag": False}, {"flag": True}])

    async def transport(*args):
        return next(responses)

    async def run():
        client = GeminiClient(model="recorded-model", transport=transport, cache_size=1)
        assert await client.generate("conversation.v1.md", {"chat": "one"}, Response) is None
        assert (await client.generate("conversation.v1.md", {"chat": "one"}, Response)).flag
        assert not (await client.generate("conversation.v1.md", {"chat": "two"}, Response)).flag
        assert (await client.generate("conversation.v1.md", {"chat": "one"}, Response)).flag
        assert client.calls_made == 4

    asyncio.run(run())


def test_sdk_config_and_json_delimiter_use_installed_google_genai(monkeypatch):
    from types import SimpleNamespace

    from google import genai

    captured = {}

    async def generate_content(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text='{"flag": true}')

    def sdk_client(**kwargs):
        captured["client"] = kwargs
        return SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        )

    monkeypatch.setattr(genai, "Client", sdk_client)
    client = GeminiClient(model="configured-model", project="synthetic-project")
    result = asyncio.run(client.generate("conversation.v1.md", {"chat": "chốt"}, Response))
    assert result.flag is True
    assert captured["client"]["enterprise"] is True
    assert captured["client"]["location"] == "asia-southeast1"
    assert captured["client"]["http_options"].timeout == 10000
    assert captured["client"]["http_options"].retry_options.attempts == 1
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].response_json_schema["additionalProperties"] is False
    assert captured["model"] == "configured-model"
    assert '"untrusted_data"' in captured["contents"]
