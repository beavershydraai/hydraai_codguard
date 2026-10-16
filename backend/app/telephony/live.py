"""The gemini_live agent: one Live API session per answered call.

Session config, events and the outcome tool follow docs/gemini-live.md. The agent only talks and
reports; the call runner (call.py) owns the phone line, and the backend owns the decisions.
"""

import asyncio
import contextlib
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from google import genai
from google.genai import types

from app.schemas.enums import CallLanguage
from app.schemas.telephony import CallJob, TranscriptTurn
from app.telephony.audio import PHONE_RATE, Downsampler, Resampler
from app.telephony.outcome import Decision, OutcomeError, closing_instruction, validate_outcome

log = logging.getLogger(__name__)

PROMPTS = Path(__file__).resolve().parents[2] / "voice" / "prompts"
LANGUAGES = {CallLanguage.VI: "VIETNAMESE", CallLanguage.EN: "ENGLISH"}
MODEL_IN_RATE = 16_000
MODEL_OUT_RATE = 24_000
INPUT_MIME = f"audio/pcm;rate={MODEL_IN_RATE}"
MAX_TURN_TEXT = 2000


@dataclass
class Timing:
    """Starting values from docs/gemini-live.md, "Call flow"; tune them in E9.2."""

    no_response_s: float = 8.0
    # After a cut-off with no buyer speech: long enough for the buyer's first words to be
    # transcribed, short enough not to leave dead air on the line.
    nothing_heard_s: float = 2.5
    closing_grace_s: float = 0.5
    closing_timeout_s: float = 20.0
    tick_s: float = 0.25


def order_context(job: CallJob) -> dict:
    """What the model may see: no internal IDs, VND figures, call ID or routing."""
    return {
        "shop_name": job.shop_name,
        "buyer": job.buyer.model_dump(mode="json"),
        "orders": [
            order.model_dump(
                mode="json", exclude={"order_id", "cod_amount_vnd", "deposit_paid_vnd"}
            )
            for order in job.orders
        ],
        "total_cod_amount_spoken": job.total_cod_amount_spoken,
    }


def render_instruction(context: dict, language: str) -> str:
    template = (PROMPTS / "confirmation_call.md").read_text(encoding="utf-8")
    # Insert the order data last, so text typed by buyers is never treated as a placeholder.
    return template.replace("{{call_language}}", language).replace(
        "{{order_context}}", json.dumps(context, ensure_ascii=False, indent=2)
    )


def record_call_outcome_tool() -> types.FunctionDeclaration:
    return types.FunctionDeclaration.model_validate(
        json.loads((PROMPTS / "record_call_outcome.json").read_text(encoding="utf-8"))
    )


def live_config(context: dict, language: str) -> types.LiveConnectConfig:
    code = "vi-VN" if language == "VIETNAMESE" else "en-US"
    items = [item["name"] for order in context["orders"] for item in order["items"]]
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=render_instruction(context, language),
        speech_config=types.SpeechConfig(
            language_code=code,
            voice_config=types.VoiceConfig(
                # Placeholder until the E5.1 spike picks a voice.
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=os.environ.get("GEMINI_LIVE_VOICE", "Kore")
                ),
            ),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(
            language_codes=[code], custom_vocabulary=[context["shop_name"], *items]
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        tools=[types.Tool(function_declarations=[record_call_outcome_tool()])],
    )


@asynccontextmanager
async def connect(job: CallJob) -> AsyncIterator[Any]:
    """Open a Live session for this job (Agent Platform, GEMINI_LIVE_LOCATION)."""
    client = genai.Client(
        enterprise=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ["GEMINI_LIVE_LOCATION"],
    )
    config = live_config(order_context(job), LANGUAGES[job.language])
    async with client.aio.live.connect(
        model=os.environ["GEMINI_LIVE_MODEL"], config=config
    ) as session:
        yield session


class AudioOut(Protocol):
    def play(self, pcm: bytes) -> None: ...
    def clear(self) -> None: ...
    async def drain(self, timeout: float) -> None: ...


@dataclass
class AgentReport:
    decision: Decision | None
    buyer_spoke: bool
    dtmf: str
    transcript: list[TranscriptTurn] = field(default_factory=list)
    end_reason: str = ""
    error: str | None = None
    tokens: int = 0


class LiveAgent:
    """Bridges the caller's audio and the Live session until the call should end.

    Feed caller audio (8 kHz 16-bit little-endian PCM) with `caller_audio`, keys with `dtmf`,
    and call `stop` when the line drops. `run` returns once the call is over.
    """

    def __init__(
        self,
        job: CallJob,
        session: Any,
        audio_out: AudioOut,
        timing: Timing | None = None,
        clock=time.monotonic,
    ) -> None:
        self._job = job
        self._session = session
        self._out = audio_out
        self._timing = timing or Timing()
        self._clock = clock
        self._inbound: asyncio.Queue[bytes] = asyncio.Queue(maxsize=250)  # 5 s of audio
        self._upsampler = Resampler(PHONE_RATE, MODEL_IN_RATE)
        self._downsampler = Downsampler(MODEL_OUT_RATE // PHONE_RATE)
        self._done = asyncio.Event()
        self._started = clock()
        self._accepted: list[tuple[str, Decision]] = []
        self._closing = False
        self._closing_since = 0.0
        self._spoke_since_decision = False
        self._model_turn_ended: float | None = None
        self._interrupted_at: float | None = None
        self._no_response_sent = False
        self._time_up_sent = False
        self._buyer_spoke = False
        self._dtmf = ""
        self._turns: list[TranscriptTurn] = []
        self._turn_speaker: str | None = None
        self._turn_text = ""
        self._turn_offset = 0
        self._end_reason = ""
        self._error: str | None = None
        self._tokens = 0

    # Inputs from the call runner

    def caller_audio(self, pcm: bytes) -> None:
        # If the session stalls, dropping audio beats a queue that grows without bound.
        with contextlib.suppress(asyncio.QueueFull):
            self._inbound.put_nowait(pcm)

    async def dtmf(self, digit: str) -> None:
        self._dtmf = (self._dtmf + digit)[-32:]
        self._heard_buyer()
        await self._event(f"[DTMF:{digit}]")

    def stop(self, reason: str) -> None:
        self._finish(reason)

    # Main loop

    async def run(self) -> AgentReport:
        tasks = [
            asyncio.create_task(self._send_audio()),
            asyncio.create_task(self._receive()),
            asyncio.create_task(self._timers()),
        ]
        try:
            await self._event("[CALL_CONNECTED]")
            await self._done.wait()
        except Exception as exc:  # the session broke while sending
            self._fail(exc)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self._flush_turn()
        return AgentReport(
            decision=self._accepted[-1][1] if self._accepted else None,
            buyer_spoke=self._buyer_spoke,
            dtmf=self._dtmf,
            transcript=self._turns,
            end_reason=self._end_reason,
            error=self._error,
            tokens=self._tokens,
        )

    def _finish(self, reason: str) -> None:
        if not self._done.is_set():
            self._end_reason = reason
            self._done.set()

    def _fail(self, exc: BaseException) -> None:
        log.warning("live session failed: %s", type(exc).__name__)
        self._error = type(exc).__name__
        self._finish("agent_error")

    async def _event(self, name: str) -> None:
        await self._session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=name)]), turn_complete=True
        )

    async def _send_audio(self) -> None:
        try:
            while True:
                chunk = await self._inbound.get()
                await self._session.send_realtime_input(
                    audio=types.Blob(data=self._upsampler.process(chunk), mime_type=INPUT_MIME)
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fail(exc)

    async def _receive(self) -> None:
        try:
            while not self._done.is_set():
                got_any = False
                async for message in self._session.receive():
                    got_any = True
                    await self._handle(message)
                if not got_any:  # the server closed the session
                    self._finish("session_closed")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fail(exc)

    async def _handle(self, message: Any) -> None:
        content = message.server_content
        if content:
            if content.interrupted:
                self._out.clear()
                # Line noise or echo can cut the agent off as well as the buyer can. The model
                # then waits for a buyer who says nothing; `_timers` tells it to go on.
                self._interrupted_at = self._clock()
                log.info("agent interrupted")
            if content.model_turn and content.model_turn.parts:
                self._model_turn_ended = None
                self._interrupted_at = None
                for part in content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        self._out.play(self._downsampler.process(part.inline_data.data))
                        self._spoke_since_decision = True
            if content.input_transcription and content.input_transcription.text:
                self._heard_buyer()
                self._transcribe("buyer", content.input_transcription.text)
            if content.output_transcription and content.output_transcription.text:
                self._transcribe("agent", content.output_transcription.text)
            if content.turn_complete:
                self._flush_turn()
                self._model_turn_ended = self._clock()
                # Hang up after the closing line, not after the turn that made the tool call.
                if self._closing and self._spoke_since_decision:
                    await self._out.drain(timeout=10)
                    await asyncio.sleep(self._timing.closing_grace_s)
                    self._finish("closed")
        if message.tool_call and message.tool_call.function_calls:
            await self._tool_calls(message.tool_call.function_calls)
        if message.tool_call_cancellation and message.tool_call_cancellation.ids:
            cancelled = set(message.tool_call_cancellation.ids)
            self._accepted = [(i, d) for i, d in self._accepted if i not in cancelled]
            self._closing = bool(self._accepted)
        if message.usage_metadata and message.usage_metadata.total_token_count:
            self._tokens = message.usage_metadata.total_token_count
        if message.go_away:
            self._finish("go_away")

    async def _tool_calls(self, calls: list[Any]) -> None:
        responses = []
        for call in calls:
            if call.name != "record_call_outcome":
                response = {
                    "status": "not_found",
                    "retryable": False,
                    "message": "Unknown tool. Only record_call_outcome exists.",
                }
            else:
                try:
                    decision = validate_outcome(call.args or {}, self._job)
                except OutcomeError as exc:
                    response = {
                        "status": "invalid_argument",
                        "retryable": True,
                        "message": str(exc),
                    }
                else:
                    self._accepted.append((call.id, decision))
                    self._closing = True
                    self._closing_since = self._clock()
                    self._spoke_since_decision = False
                    response = {
                        "status": "ok",
                        "retryable": False,
                        "message": closing_instruction(decision),
                    }
            responses.append(types.FunctionResponse(id=call.id, name=call.name, response=response))
        await self._session.send_tool_response(function_responses=responses)

    async def _timers(self) -> None:
        max_s = self._job.max_duration_seconds
        time_up_s = max_s - 60
        while not self._done.is_set():
            await asyncio.sleep(self._timing.tick_s)
            now = self._clock()
            elapsed = now - self._started
            if elapsed >= max_s:
                self._finish("max_duration")
                return
            if elapsed >= time_up_s and not self._time_up_sent:
                self._time_up_sent = True
                await self._event("[TIME_UP]")
                continue
            if self._closing:
                if now - self._closing_since > self._timing.closing_timeout_s:
                    self._finish("closed")
                continue
            cut_off = self._interrupted_at
            if cut_off is not None and now - cut_off >= self._timing.nothing_heard_s:
                self._interrupted_at = None
                self._model_turn_ended = now  # if the model stays silent, ask the buyer
                await self._event("[NOTHING_HEARD]")
                continue
            ended = self._model_turn_ended
            if ended is not None and now - ended >= self._timing.no_response_s:
                if self._no_response_sent:
                    self._finish("no_response")
                    return
                self._no_response_sent = True
                # Restart the wait: the model asks once, then the call ends if nobody answers.
                self._model_turn_ended = now
                await self._event("[NO_RESPONSE]")

    def _heard_buyer(self) -> None:
        self._buyer_spoke = True
        self._no_response_sent = False
        self._model_turn_ended = None
        self._interrupted_at = None

    def _transcribe(self, speaker: str, text: str) -> None:
        if speaker != self._turn_speaker:
            self._flush_turn()
            self._turn_speaker = speaker
            self._turn_offset = int((self._clock() - self._started) * 1000)
        self._turn_text += text

    def _flush_turn(self) -> None:
        text = " ".join(self._turn_text.split())
        if self._turn_speaker and text:
            self._turns.append(
                TranscriptTurn(
                    speaker=self._turn_speaker,  # type: ignore[arg-type]
                    text=text[:MAX_TURN_TEXT],
                    offset_ms=self._turn_offset,
                )
            )
        self._turn_speaker = None
        self._turn_text = ""
