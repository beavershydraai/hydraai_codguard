"""The controller service loop (app/telephony/controller.py): claim, ack, call, report, outbox.
No Pub/Sub, backend or Asterisk: each is a small fake."""

import base64
import json

import httpx
import pytest

from app.schemas.telephony import CallJob, CallResult
from app.telephony.controller import Controller, Outbox

JOB = CallJob.model_config["json_schema_extra"]["examples"][0] | {"agent": "gemini_live"}
COMPLETED = CallResult.model_config["json_schema_extra"]["examples"][0]


def message(data: dict | bytes, ack_id: str = "ack-1") -> dict:
    raw = data if isinstance(data, bytes) else json.dumps(data).encode()
    return {"ackId": ack_id, "message": {"data": base64.b64encode(raw).decode()}}


class FakeSubscription:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self.acked, self.nacked = [], []

    async def pull(self):
        return [self.messages.pop(0)] if self.messages else []

    async def ack(self, ack_id):
        self.acked.append(ack_id)

    async def nack(self, ack_id):
        self.nacked.append(ack_id)


class FakeBackend:
    def __init__(self, claim=200, results=(200,)):
        self.claim = claim
        self.results = list(results)
        self.statuses, self.posted = [], []

    async def status(self, call_id, status, at, controller_id):
        self.statuses.append((call_id, status, controller_id))
        if isinstance(self.claim, Exception):
            raise self.claim
        return self.claim if status == "dialing" else 200

    async def result(self, call_id, body):
        self.posted.append((call_id, json.loads(body)))
        code = self.results.pop(0) if self.results else 200
        if isinstance(code, Exception):
            raise code
        return code


async def no_sleep(_seconds):
    return None


def controller(tmp_path, subscription, backend, place=None):
    async def default_place(job, on_answer):
        await on_answer(CallResult.model_validate(COMPLETED).answered_at)
        return CallResult.model_validate(COMPLETED)

    return Controller(
        "codguard-asterisk",
        subscription,
        backend,
        Outbox(tmp_path),
        place or default_place,
        sleep=no_sleep,
    )


@pytest.mark.asyncio
async def test_a_job_is_claimed_acked_called_and_its_result_delivered(tmp_path):
    subscription, backend = FakeSubscription([message(JOB)]), FakeBackend()
    await controller(tmp_path, subscription, backend).step()
    assert subscription.acked == ["ack-1"]
    assert backend.statuses == [
        ("call_01", "dialing", "codguard-asterisk"),
        ("call_01", "in_progress", "codguard-asterisk"),
    ]
    assert backend.posted[0][1]["outcome"] == "edited"
    assert list(tmp_path.glob("*.json")) == []


@pytest.mark.asyncio
async def test_a_call_that_is_not_active_is_dropped_without_dialling(tmp_path):
    calls = []

    async def place(job, on_answer):
        calls.append(job)

    subscription, backend = FakeSubscription([message(JOB)]), FakeBackend(claim=409)
    await controller(tmp_path, subscription, backend, place).step()
    assert subscription.acked == ["ack-1"] and calls == [] and backend.posted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("claim", [503, httpx.ConnectError("backend down")])
async def test_a_failed_claim_is_redelivered_later(tmp_path, claim):
    subscription = FakeSubscription([message(JOB)])
    await controller(tmp_path, subscription, FakeBackend(claim=claim)).step()
    assert subscription.nacked == ["ack-1"] and subscription.acked == []


@pytest.mark.asyncio
async def test_a_message_that_is_not_a_job_is_dropped(tmp_path):
    subscription, backend = FakeSubscription([message(b"not json")]), FakeBackend()
    await controller(tmp_path, subscription, backend).step()
    assert subscription.acked == ["ack-1"] and backend.statuses == []


@pytest.mark.asyncio
async def test_a_broken_call_still_reports_a_failed_result(tmp_path):
    async def place(job, on_answer):
        raise RuntimeError("Live session refused")

    backend = FakeBackend()
    await controller(tmp_path, FakeSubscription([message(JOB)]), backend, place).step()
    ((_, result),) = backend.posted
    assert result["status"] == "failed" and result["failure_reason"] == "agent_error"


@pytest.mark.asyncio
async def test_an_undelivered_result_waits_in_the_outbox_and_is_sent_next_time(tmp_path):
    backend = FakeBackend(results=[503, 503, 503, 503, httpx.ConnectError("down")])
    service = controller(tmp_path, FakeSubscription([message(JOB)]), backend)
    await service.step()
    assert [p.name for p in tmp_path.glob("*.json")] == ["call_01.json"]
    backend.results = [200]
    await service.step()  # the next loop flushes the outbox before pulling
    assert list(tmp_path.glob("*.json")) == [] and len(backend.posted) == 6


@pytest.mark.asyncio
async def test_a_conflicting_result_is_not_retried_forever(tmp_path):
    backend = FakeBackend(results=[409])
    await controller(tmp_path, FakeSubscription([message(JOB)]), backend).step()
    assert len(backend.posted) == 1 and list(tmp_path.glob("*.json")) == []
