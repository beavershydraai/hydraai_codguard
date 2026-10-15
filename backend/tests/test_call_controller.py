"""Call controller (app/telephony) with a fake ARI client and a fake Live session.
CI never needs Asterisk or the Live API (docs/call-controller.md, "Running it")."""

import asyncio
import socket
import struct
from contextlib import asynccontextmanager

import numpy as np
import pytest
from google.genai import types

from app.schemas.enums import CallFailureReason, CallLanguage, CallOutcome
from app.telephony import live
from app.telephony.ari import AriError
from app.telephony.audio import Framer, Resampler, swap16
from app.telephony.call import CallRunner, endpoint_for
from app.telephony.dial import sample_job
from app.telephony.live import LiveAgent, Timing
from app.telephony.outcome import OutcomeError, fallback_outcome, validate_outcome
from app.telephony.rtp import RtpEndpoint, build_rtp, parse_rtp

FAST = Timing(no_response_s=0.05, closing_grace_s=0, closing_timeout_s=1, tick_s=0.01)


def job(language=CallLanguage.VI):
    return sample_job("6001", language)


# Audio


def test_swap16_round_trips():
    pcm = struct.pack("<3h", 1, -2, 300)
    assert swap16(pcm) == struct.pack(">3h", 1, -2, 300)
    assert swap16(swap16(pcm)) == pcm


def test_resampler_gives_the_same_output_in_chunks_as_in_one_go():
    t = np.arange(2400) / 24_000
    pcm = (np.sin(2 * np.pi * 440 * t) * 10_000).astype("<i2").tobytes()
    whole = Resampler(24_000, 16_000).process(pcm)
    chunked = Resampler(24_000, 16_000)
    sizes = [2, 954, 6, 1000, 1, 2838]  # odd byte counts never happen; sample counts vary
    pieces, offset = [], 0
    for size in sizes:
        size -= size % 2
        pieces.append(chunked.process(pcm[offset : offset + size]))
        offset += size
    pieces.append(chunked.process(pcm[offset:]))
    assert b"".join(pieces) == whole
    assert abs(len(whole) // 2 - 1600) <= 1


def test_framer_cuts_fixed_frames_and_keeps_the_rest():
    framer = Framer(4)
    assert framer.push(b"abcdef") == [b"abcd"]
    assert framer.push(b"gh") == [b"efgh"]
    framer.push(b"x")
    framer.clear()
    assert framer.push(b"1234") == [b"1234"]


# RTP


def test_rtp_round_trip_skips_csrc_extension_and_padding():
    packet = build_rtp(118, 7, 160, 0x1234, b"\x00\x01\x00\x02", marker=True)
    assert parse_rtp(packet) == (118, b"\x00\x01\x00\x02")
    extended = bytearray(packet[:12])
    extended[0] |= 0x10 | 0x20 | 0x01  # extension, padding, one CSRC
    extended += b"\x00\x00\x00\x09" + b"\xbe\xde\x00\x01" + b"\x01\x02\x03\x04"
    extended += b"\x00\x05" + b"\x00\x00\x02"  # payload, then 2 padding bytes and the count 2
    assert parse_rtp(bytes(extended)) == (118, b"\x00\x05\x00")
    assert parse_rtp(b"\x00" * 12) is None


async def test_rtp_endpoint_swaps_bytes_both_ways_and_answers_the_sender():
    heard = []
    endpoint = await RtpEndpoint.open(heard.append)
    asterisk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    asterisk.bind(("127.0.0.1", 0))
    asterisk.setblocking(False)
    try:
        host, port = endpoint.local_address.split(":")
        asterisk.sendto(build_rtp(118, 1, 0, 9, struct.pack(">2h", 1, -1)), (host, int(port)))
        await asyncio.sleep(0.05)
        assert heard == [struct.pack("<2h", 1, -1)]

        endpoint.play(struct.pack("<320h", *range(320)))  # one 20 ms frame
        loop = asyncio.get_running_loop()
        packet = await asyncio.wait_for(loop.sock_recv(asterisk, 2048), 1)
        payload_type, payload = parse_rtp(packet)
        assert payload_type == 118
        assert payload == struct.pack(">320h", *range(320))
        assert packet[1] & 0x80  # marker on the first packet of a talk spurt
    finally:
        endpoint.close()
        asterisk.close()


# Outcome tool


def test_valid_outcome_maps_refs_to_order_ids():
    decision = validate_outcome(
        {
            "outcome": "EDITED",
            "summary": "Buyer changed the house number.",
            "changes": [
                {"order_ref": "4721", "field": "delivery_address", "new_value": "Số 15"},
                {
                    "order_ref": "4721",
                    "field": "item_quantity",
                    "item_name": "Áo khoác gió",
                    "new_value": "2",
                },
            ],
        },
        job(),
    )
    assert decision.outcome == CallOutcome.EDITED
    assert [c.order_id for c in decision.changes] == ["ord_01", "ord_01"]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ({"outcome": "MAYBE", "summary": "x"}, "outcome must be one of"),
        ({"outcome": "NO_ANSWER", "summary": "x"}, "outcome must be one of"),
        ({"outcome": "CONFIRMED", "summary": " "}, "summary is empty"),
        ({"outcome": "EDITED", "summary": "x"}, "EDITED needs at least one entry"),
        (
            {
                "outcome": "CONFIRMED",
                "summary": "x",
                "changes": [{"order_ref": "4721", "field": "delivery_address", "new_value": "y"}],
            },
            "CONFIRMED takes no changes",
        ),
        (
            {
                "outcome": "EDITED",
                "summary": "x",
                "changes": [{"order_ref": "9999", "field": "delivery_address", "new_value": "y"}],
            },
            "order_ref must be one of 4721",
        ),
        (
            {
                "outcome": "EDITED",
                "summary": "x",
                "changes": [
                    {
                        "order_ref": "4721",
                        "field": "item_variant",
                        "item_name": "Hat",
                        "new_value": "red",
                    }
                ],
            },
            "item_name must name an item",
        ),
    ],
)
def test_invalid_outcomes_tell_the_model_what_to_fix(args, message):
    with pytest.raises(OutcomeError, match=message):
        validate_outcome(args, job())


def test_fallback_outcome():
    assert fallback_outcome(False, False) == CallOutcome.NO_ANSWER
    assert fallback_outcome(True, False) == CallOutcome.UNCLEAR
    assert fallback_outcome(False, True) == CallOutcome.UNCLEAR


# Gemini context


def test_order_context_hides_ids_amounts_and_routing():
    context = live.order_context(job())
    assert set(context) == {"shop_name", "buyer", "orders", "total_cod_amount_spoken"}
    order = context["orders"][0]
    assert "order_id" not in order and "cod_amount_vnd" not in order
    assert "deposit_paid_vnd" not in order
    instruction = live.render_instruction(context, "VIETNAMESE")
    assert "{{" not in instruction and '"ref": "4721"' in instruction


def test_live_config_validates_with_the_tool():
    config = live.live_config(live.order_context(job(CallLanguage.EN)), "ENGLISH")
    assert config.speech_config.language_code == "en-US"
    assert config.tools[0].function_declarations[0].behavior == types.Behavior.BLOCKING


# Fake Live session


def audio(samples=480):
    blob = types.Blob(data=b"\x01\x00" * samples, mime_type="audio/pcm;rate=24000")
    return types.LiveServerMessage(
        server_content=types.LiveServerContent(
            model_turn=types.Content(parts=[types.Part(inline_data=blob)])
        )
    )


def said(text):
    return types.LiveServerMessage(
        server_content=types.LiveServerContent(output_transcription=types.Transcription(text=text))
    )


def heard(text):
    return types.LiveServerMessage(
        server_content=types.LiveServerContent(input_transcription=types.Transcription(text=text))
    )


def turn_complete():
    return types.LiveServerMessage(server_content=types.LiveServerContent(turn_complete=True))


def tool(call_id, **args):
    return types.LiveServerMessage(
        tool_call=types.LiveServerToolCall(
            function_calls=[types.FunctionCall(id=call_id, name="record_call_outcome", args=args)]
        )
    )


def cancel(*ids):
    return types.LiveServerMessage(
        tool_call_cancellation=types.LiveServerToolCallCancellation(ids=list(ids))
    )


class FakeSession:
    """Plays scripted turns: each receive() yields the next list of messages. A turn may wait
    for a tool response first (the string "await_tool")."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.events = []
        self.audio_in = 0
        self.tool_responses = []
        self._tool_answered = asyncio.Event()

    async def send_client_content(self, *, turns, turn_complete=True):
        self.events.append(turns.parts[0].text)

    async def send_realtime_input(self, *, audio):
        self.audio_in += len(audio.data)

    async def send_tool_response(self, *, function_responses):
        self.tool_responses.extend(function_responses)
        self._tool_answered.set()

    async def receive(self):
        if not self.turns:
            await asyncio.Event().wait()  # nothing more: block like a quiet session
        turn = self.turns.pop(0)
        for message in turn:
            if message == "await_tool":
                await self._tool_answered.wait()
                self._tool_answered.clear()
                continue
            yield message


class FakeOut:
    def __init__(self):
        self.played = b""
        self.cleared = 0

    def play(self, pcm):
        self.played += pcm

    def clear(self):
        self.cleared += 1

    async def drain(self, timeout):
        pass


CONFIRM_CALL = (
    [audio(), said("Hello, this is the AI assistant of Tiệm Mẫu."), turn_complete()],
    [
        heard("Yes, that's right."),
        tool("c1", outcome="CONFIRMED", summary="Confirmed."),
        "await_tool",
        audio(),
        said("Thank you, goodbye."),
        turn_complete(),
    ],
)


async def test_live_agent_confirms_and_hangs_up_after_the_closing_line():
    session, out = FakeSession(*CONFIRM_CALL), FakeOut()
    agent = LiveAgent(job(), session, out, FAST)
    agent.caller_audio(b"\x00\x00" * 320)
    report = await asyncio.wait_for(agent.run(), 2)

    assert report.end_reason == "closed"
    assert report.decision.outcome == CallOutcome.CONFIRMED
    assert report.buyer_spoke
    assert session.events[0] == "[CALL_CONNECTED]"
    assert session.audio_in == 640
    response = session.tool_responses[0]
    assert response.id == "c1" and response.response["status"] == "ok"
    assert len(out.played) == 2 * 640  # two 480-sample model chunks, at 16 kHz
    assert [t.speaker for t in report.transcript] == ["agent", "buyer", "agent"]


async def test_live_agent_rejects_an_invalid_call_and_keeps_listening():
    session = FakeSession([tool("c1", outcome="EDITED", summary="x"), "await_tool"])
    agent = LiveAgent(job(), session, FakeOut(), FAST)
    task = asyncio.create_task(agent.run())
    await asyncio.sleep(0.05)
    agent.stop("hangup")
    report = await asyncio.wait_for(task, 1)
    assert session.tool_responses[0].response["status"] == "invalid_argument"
    assert session.tool_responses[0].response["retryable"] is True
    assert report.decision is None and report.end_reason == "hangup"


async def test_cancelled_tool_call_is_dropped():
    session = FakeSession(
        [tool("c1", outcome="CANCELLED", summary="Cancelled."), "await_tool", cancel("c1")]
    )
    agent = LiveAgent(job(), session, FakeOut(), FAST)
    task = asyncio.create_task(agent.run())
    await asyncio.sleep(0.05)
    agent.stop("hangup")
    report = await asyncio.wait_for(task, 1)
    assert report.decision is None


async def test_silence_sends_no_response_once_then_ends():
    session = FakeSession([audio(), turn_complete()])
    report = await asyncio.wait_for(LiveAgent(job(), session, FakeOut(), FAST).run(), 2)
    assert session.events == ["[CALL_CONNECTED]", "[NO_RESPONSE]"]
    assert report.end_reason == "no_response" and not report.buyer_spoke


async def test_keys_go_to_the_model_and_count_as_an_answer():
    session = FakeSession()
    agent = LiveAgent(job(), session, FakeOut(), FAST)
    task = asyncio.create_task(agent.run())
    await asyncio.sleep(0.02)
    await agent.dtmf("1")
    agent.stop("hangup")
    report = await asyncio.wait_for(task, 1)
    assert "[DTMF:1]" in session.events and report.dtmf == "1"


# Call runner


class FakeAri:
    def __init__(self, originate_error=None):
        self.originate_error = originate_error
        self.calls = []

    async def originate(self, endpoint, channel_id, app_args, timeout, variables=None):
        self.calls.append(("originate", endpoint, channel_id, variables))
        if self.originate_error:
            raise self.originate_error
        return {"id": channel_id}

    async def hangup(self, channel_id):
        self.calls.append(("hangup", channel_id))

    async def external_media(self, channel_id, external_host, audio_format="slin16"):
        self.calls.append(("external_media", channel_id, audio_format))

    async def create_bridge(self, bridge_id):
        self.calls.append(("bridge", bridge_id))

    async def add_channels(self, bridge_id, *channel_ids):
        self.calls.append(("add", bridge_id, channel_ids))

    async def destroy_bridge(self, bridge_id):
        self.calls.append(("destroy_bridge", bridge_id))


def connect_to(session):
    @asynccontextmanager
    async def connect(_job):
        yield session

    return connect


def event(kind, channel_id, **extra):
    return {"type": kind, "channel": {"id": channel_id, "state": "Up"}, **extra}


def test_endpoint_for_each_channel():
    j = job()
    assert endpoint_for(j.target) == "PJSIP/6001"
    assert endpoint_for(
        j.target.model_copy(update={"kind": "pstn", "address": "+84000000000"})
    ) == ("PJSIP/+84000000000@twilio")


@pytest.mark.parametrize(
    ("cause", "status", "outcome", "reason"),
    [
        (19, "completed", CallOutcome.NO_ANSWER, None),
        (17, "completed", CallOutcome.NO_ANSWER, None),
        (20, "failed", None, CallFailureReason.TARGET_UNREACHABLE),
    ],
)
async def test_unanswered_calls(cause, status, outcome, reason):
    ari = FakeAri()
    runner = CallRunner(ari, job(), "codguard-asterisk", connect=connect_to(FakeSession()))
    runner.events.put_nowait(event("ChannelDestroyed", runner.channel_id, cause=cause))
    result = await asyncio.wait_for(runner.run(), 2)
    assert (result.status, result.outcome, result.failure_reason) == (status, outcome, reason)
    assert result.answered_at is None
    assert ari.calls[0][3] == {"CHANNEL(language)": "vi"}


@pytest.mark.parametrize(
    ("status", "reason"),
    [(0, CallFailureReason.ASTERISK_UNAVAILABLE), (404, CallFailureReason.TARGET_UNREACHABLE)],
)
async def test_originate_errors(status, reason):
    ari = FakeAri(originate_error=AriError(status, "boom"))
    runner = CallRunner(ari, job(), "codguard-asterisk", connect=connect_to(FakeSession()))
    result = await runner.run()
    assert result.status == "failed" and result.failure_reason == reason


async def test_answered_call_bridges_media_runs_the_agent_and_cleans_up():
    ari = FakeAri()
    session = FakeSession(*CONFIRM_CALL)
    runner = CallRunner(ari, job(), "codguard-asterisk", connect=connect_to(session), timing=FAST)
    runner.events.put_nowait(event("StasisStart", runner.channel_id))
    runner.events.put_nowait(event("StasisStart", f"{runner.channel_id}-media"))  # ignored
    runner.events.put_nowait(event("ChannelDtmfReceived", runner.channel_id, digit="1"))
    result = await asyncio.wait_for(runner.run(), 3)

    assert result.status == "completed" and result.outcome == CallOutcome.CONFIRMED
    assert result.answered_at is not None and result.summary_vi == "Confirmed."
    assert result.input_method == "voice" and result.dtmf == "1"
    kinds = [call[0] for call in ari.calls]
    assert kinds[:4] == ["originate", "external_media", "bridge", "add"]
    assert ("hangup", runner.channel_id) in ari.calls
    assert ("destroy_bridge", f"{runner.channel_id}-bridge") in ari.calls


async def test_answered_call_whose_agent_breaks_fails_with_agent_error():
    @asynccontextmanager
    async def broken(_job):
        raise ConnectionError("Live API down")
        yield

    ari = FakeAri()
    runner = CallRunner(ari, job(), "codguard-asterisk", connect=broken, timing=FAST)
    runner.events.put_nowait(event("StasisStart", runner.channel_id))
    result = await asyncio.wait_for(runner.run(), 2)
    assert result.status == "failed" and result.failure_reason == CallFailureReason.AGENT_ERROR
    assert result.answered_at is not None
    assert ("hangup", runner.channel_id) in ari.calls
