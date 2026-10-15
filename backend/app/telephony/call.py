"""Runs one call attempt: originate, wait for the answer, bridge the caller to the agent, hang up
and build the CallResult. See docs/call-controller.md, "Call lifecycle".

Events for the call's channels arrive on `CallRunner.events`; whoever reads the ARI event stream
routes them there (see `CallRunner.wants`).
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

from app.schemas.enums import CallAgent, CallFailureReason, CallInputMethod, CallTargetKind
from app.schemas.telephony import CallJob, CallResult, CallTarget
from app.telephony import live
from app.telephony.ari import AriClient, AriError
from app.telephony.live import AgentReport, LiveAgent, Timing
from app.telephony.outcome import fallback_outcome
from app.telephony.rtp import RtpEndpoint

log = logging.getLogger(__name__)

# Q.850 hang-up causes before the answer. Anything else also counts as no answer.
UNREACHABLE_CAUSES = {3, 20}  # no route; subscriber absent (softphone not registered)
ANSWER_GRACE_S = 15  # beyond ring_timeout_seconds, before giving up on events

SessionFactory = Callable[[CallJob], AbstractAsyncContextManager[Any]]


def endpoint_for(target: CallTarget) -> str:
    if target.kind == CallTargetKind.SIP:
        return f"PJSIP/{target.address}"
    if target.kind == CallTargetKind.WEBRTC:
        return f"PJSIP/web-{target.address}"
    return f"PJSIP/{target.address}@twilio"


def _channel_id(event: dict) -> str:
    return (event.get("channel") or {}).get("id", "")


class CallRunner:
    def __init__(
        self,
        ari: AriClient,
        job: CallJob,
        controller_id: str,
        connect: SessionFactory = live.connect,
        timing: Timing | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if job.agent != CallAgent.GEMINI_LIVE:
            raise NotImplementedError("only the gemini_live agent exists so far")
        self.job = job
        self.events: asyncio.Queue[dict] = asyncio.Queue()
        self.channel_id = f"{job.call_id}-{job.attempt}"
        self._media_id = f"{self.channel_id}-media"
        self._bridge_id = f"{self.channel_id}-bridge"
        self._ari = ari
        self._controller_id = controller_id
        self._connect = connect
        self._timing = timing
        self._now = now
        self._agent: LiveAgent | None = None

    def wants(self, event: dict) -> bool:
        return _channel_id(event).startswith(self.channel_id)

    async def run(self) -> CallResult:
        dial_started = self._now()
        try:
            await self._ari.originate(
                endpoint_for(self.job.target),
                self.channel_id,
                app_args=self.job.call_id,
                timeout=self.job.ring_timeout_seconds,
                variables={"CHANNEL(language)": self.job.language.value},
            )
        except AriError as exc:
            log.warning("originate failed: %s", exc)
            unavailable = exc.status == 0 or exc.status >= 500
            reason = (
                CallFailureReason.ASTERISK_UNAVAILABLE
                if unavailable
                else CallFailureReason.TARGET_UNREACHABLE
            )
            return self._failed(reason, dial_started, None)

        answered, cause = await self._wait_for_answer()
        if not answered:
            log.info("not answered, cause %s", cause)
            if cause in UNREACHABLE_CAUSES:
                return self._failed(CallFailureReason.TARGET_UNREACHABLE, dial_started, None)
            return self._result(dial_started, None, None)

        answered_at = self._now()
        log.info("answered")
        report: AgentReport | None = None
        try:
            report = await self._converse()
        except Exception as exc:
            log.warning("call setup or agent failed: %s", exc)
        finally:
            await self._teardown()
        if report is None or (report.error and report.decision is None):
            return self._failed(CallFailureReason.AGENT_ERROR, dial_started, answered_at, report)
        log.info("call ended: %s, %s tokens", report.end_reason, report.tokens)
        return self._result(dial_started, answered_at, report)

    async def _wait_for_answer(self) -> tuple[bool, int | None]:
        deadline = self.job.ring_timeout_seconds + ANSWER_GRACE_S
        try:
            async with asyncio.timeout(deadline):
                while True:
                    event = await self.events.get()
                    if _channel_id(event) != self.channel_id:
                        continue
                    kind = event.get("type")
                    if kind == "StasisStart":
                        return True, None
                    if kind == "ChannelStateChange" and event["channel"].get("state") == "Ringing":
                        log.info("ringing")
                    if kind == "ChannelDestroyed":
                        return False, event.get("cause")
        except TimeoutError:
            await self._safe(self._ari.hangup(self.channel_id))
            return False, None

    async def _converse(self) -> AgentReport:
        rtp = await RtpEndpoint.open(self._caller_audio)
        try:
            await self._ari.external_media(self._media_id, rtp.local_address)
            await self._ari.create_bridge(self._bridge_id)
            await self._ari.add_channels(self._bridge_id, self.channel_id, self._media_id)
            async with self._connect(self.job) as session:
                agent = LiveAgent(self.job, session, rtp, self._timing)
                self._agent = agent
                watcher = asyncio.create_task(self._watch(agent))
                try:
                    return await agent.run()
                finally:
                    watcher.cancel()
        finally:
            self._agent = None
            rtp.close()
            log.info("rtp packets in %s, out %s", rtp.packets_in, rtp.packets_out)

    def _caller_audio(self, pcm: bytes) -> None:
        if self._agent:
            self._agent.caller_audio(pcm)

    async def _watch(self, agent: LiveAgent) -> None:
        while True:
            event = await self.events.get()
            if _channel_id(event) != self.channel_id:
                continue
            kind = event.get("type")
            if kind == "ChannelDtmfReceived":
                await agent.dtmf(event["digit"])
            elif kind in ("StasisEnd", "ChannelDestroyed", "ChannelHangupRequest"):
                agent.stop("hangup")
                return

    async def _teardown(self) -> None:
        await self._safe(self._ari.hangup(self.channel_id))
        await self._safe(self._ari.hangup(self._media_id))
        await self._safe(self._ari.destroy_bridge(self._bridge_id))

    @staticmethod
    async def _safe(coro) -> None:
        try:
            await coro
        except Exception as exc:
            log.info("cleanup: %s", exc)

    def _failed(
        self,
        reason: CallFailureReason,
        dial_started: datetime,
        answered_at: datetime | None,
        report: AgentReport | None = None,
    ) -> CallResult:
        return CallResult(
            status="failed",
            failure_reason=reason,
            controller_id=self._controller_id,
            agent=self.job.agent,
            language=self.job.language,
            input_method=_input_method(report),
            dial_started_at=dial_started,
            answered_at=answered_at,
            ended_at=self._now(),
            dtmf=report.dtmf if report else "",
            transcript=report.transcript if report else [],
        )

    def _result(
        self, dial_started: datetime, answered_at: datetime | None, report: AgentReport | None
    ) -> CallResult:
        decision = report.decision if report else None
        outcome = (
            decision.outcome
            if decision
            else fallback_outcome(bool(report and report.buyer_spoke), bool(report and report.dtmf))
        )
        return CallResult(
            status="completed",
            outcome=outcome,
            controller_id=self._controller_id,
            agent=self.job.agent,
            language=self.job.language,
            input_method=_input_method(report),
            dial_started_at=dial_started,
            answered_at=answered_at,
            ended_at=self._now(),
            dtmf=report.dtmf if report else "",
            changes=decision.changes if decision else [],
            cancel_reason=decision.cancel_reason if decision else None,
            human_callback_requested=decision.human_callback_requested if decision else False,
            buyer_requests=decision.buyer_requests if decision else None,
            summary_vi=decision.summary if decision else None,
            transcript=report.transcript if report else [],
        )


def _input_method(report: AgentReport | None) -> CallInputMethod:
    if report and report.buyer_spoke:
        return CallInputMethod.VOICE
    if report and report.dtmf:
        return CallInputMethod.DTMF
    return CallInputMethod.NONE
