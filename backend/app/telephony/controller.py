"""Call controller service on the Asterisk VM (docs/call-controller.md):

    python -m app.telephony.controller

It pulls CallJobs from the Pub/Sub subscription, claims each call with the backend (`dialing`),
acks the message, places the call with CallRunner, reports `in_progress` on the answer and posts
the CallResult. One call at a time: the VM is small, and a waiting job simply stays in Pub/Sub.
A result is written to the outbox before it is sent, so a restart never loses it.

Environment:

- CONTROLLER_ID: sent with every status and result, e.g. `codguard-asterisk`
- CALL_JOBS_SUBSCRIPTION: `projects/<project>/subscriptions/call-jobs-vm`
- BACKEND_URL: the backend's base URL, also the audience of the ID token
- ARI_URL, ARI_USER, ARI_PASSWORD and the Gemini Live variables (see docs/gemini-live.md)
- OUTBOX_DIR: results not delivered yet (default `/var/lib/codguard/outbox`)
- ID_TOKEN=off: send no ID token, for a backend on your machine with INTERNAL_AUTH=off
"""

import asyncio
import base64
import logging
import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import google.auth
import httpx
from google.auth.transport.requests import Request
from pydantic import ValidationError

from app.schemas.enums import CallFailureReason, CallInputMethod
from app.schemas.telephony import CallJob, CallResult
from app.telephony.ari import AriClient
from app.telephony.call import CallRunner

log = logging.getLogger("app.telephony.controller")

APP = "codguard"
METADATA_IDENTITY = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)
TOKEN_TTL_S = 55 * 60
PUBSUB = "https://pubsub.googleapis.com/v1"
PUBSUB_SCOPES = ["https://www.googleapis.com/auth/pubsub"]
STATUS_TRIES = 3
RESULT_TRIES = 5

OnAnswer = Callable[[datetime], Awaitable[None]]
Place = Callable[[CallJob, OnAnswer], Awaitable[CallResult]]


def _now() -> datetime:
    return datetime.now(UTC)


class IdTokens:
    """Google-signed ID token of the VM's service account, from the metadata server."""

    def __init__(self, audience: str, http: httpx.AsyncClient) -> None:
        self._audience = audience
        self._http = http
        self._token = ""
        self._expires = 0.0

    async def headers(self) -> dict[str, str]:
        if os.environ.get("ID_TOKEN") == "off":
            return {}
        if not self._token or time.monotonic() > self._expires:
            response = await self._http.get(
                METADATA_IDENTITY,
                params={"audience": self._audience, "format": "full"},
                headers={"Metadata-Flavor": "Google"},
            )
            response.raise_for_status()
            self._token = response.text
            self._expires = time.monotonic() + TOKEN_TTL_S
        return {"Authorization": f"Bearer {self._token}"}


class Backend:
    """The backend's internal API (tag `internal`)."""

    def __init__(self, url: str, http: httpx.AsyncClient, tokens: IdTokens) -> None:
        self._url = url.rstrip("/")
        self._http = http
        self._tokens = tokens

    async def status(self, call_id: str, status: str, at: datetime, controller_id: str) -> int:
        response = await self._http.post(
            f"{self._url}/api/v1/internal/calls/{call_id}/status",
            json={"status": status, "at": at.isoformat(), "controller_id": controller_id},
            headers=await self._tokens.headers(),
        )
        return response.status_code

    async def result(self, call_id: str, body: str) -> int:
        response = await self._http.post(
            f"{self._url}/api/v1/internal/calls/{call_id}/result",
            content=body,
            headers=await self._tokens.headers() | {"Content-Type": "application/json"},
        )
        return response.status_code


class Subscription:
    """Synchronous pull over the Pub/Sub REST API, as the VM's service account."""

    def __init__(self, name: str, http: httpx.AsyncClient) -> None:
        self._name = name
        self._http = http
        self._credentials = None

    async def _headers(self) -> dict[str, str]:
        if self._credentials is None:
            self._credentials, _ = google.auth.default(scopes=PUBSUB_SCOPES)
        if not self._credentials.valid:
            await asyncio.to_thread(self._credentials.refresh, Request())
        return {"Authorization": f"Bearer {self._credentials.token}"}

    async def _post(self, verb: str, body: dict) -> dict:
        response = await self._http.post(
            f"{PUBSUB}/{self._name}:{verb}", json=body, headers=await self._headers()
        )
        response.raise_for_status()
        return response.json()

    async def pull(self) -> list[dict]:
        """Wait for at most one message. An idle wait that times out returns nothing."""
        try:
            body = await self._post("pull", {"maxMessages": 1})
        except httpx.TimeoutException:
            return []
        return body.get("receivedMessages", [])

    async def ack(self, ack_id: str) -> None:
        await self._post("acknowledge", {"ackIds": [ack_id]})

    async def nack(self, ack_id: str) -> None:
        """Make the message available again now; Pub/Sub redelivers it with its retry policy."""
        await self._post("modifyAckDeadline", {"ackIds": [ack_id], "ackDeadlineSeconds": 0})


class Outbox:
    """One JSON file per result that the backend has not taken yet."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, call_id: str, body: str) -> None:
        temporary = self._dir / f".{call_id}.json"
        temporary.write_text(body, encoding="utf-8")
        temporary.replace(self._dir / f"{call_id}.json")

    def pending(self) -> list[tuple[str, str]]:
        return [(p.stem, p.read_text(encoding="utf-8")) for p in sorted(self._dir.glob("*.json"))]

    def remove(self, call_id: str) -> None:
        (self._dir / f"{call_id}.json").unlink(missing_ok=True)


def failed_result(
    job: CallJob, controller_id: str, reason: CallFailureReason, started: datetime
) -> CallResult:
    return CallResult(
        status="failed",
        failure_reason=reason,
        controller_id=controller_id,
        agent=job.agent,
        language=job.language,
        input_method=CallInputMethod.NONE,
        dial_started_at=started,
        ended_at=_now(),
    )


class Controller:
    def __init__(
        self,
        controller_id: str,
        subscription: Subscription,
        backend: Backend,
        outbox: Outbox,
        place: Place,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.controller_id = controller_id
        self.subscription = subscription
        self.backend = backend
        self.outbox = outbox
        self.place = place
        self._sleep = sleep

    async def run_forever(self) -> None:
        log.info("controller %s started", self.controller_id)
        while True:
            try:
                await self.step()
            except Exception:
                log.exception("controller loop failed; retrying in 5 s")
                await self._sleep(5)

    async def step(self) -> None:
        await self.flush()
        for message in await self.subscription.pull():
            await self.handle(message)

    async def handle(self, message: dict) -> None:
        ack_id = message["ackId"]
        try:
            job = CallJob.model_validate_json(base64.b64decode(message["message"].get("data", "")))
        except (ValidationError, ValueError):
            log.error("dropping a message that is not a CallJob")
            await self.subscription.ack(ack_id)
            return
        started = _now()
        try:
            code = await self.backend.status(job.call_id, "dialing", started, self.controller_id)
        except httpx.HTTPError as exc:
            log.warning("could not claim %s: %s", job.call_id, exc)
            await self.subscription.nack(ack_id)
            return
        if code == 409:  # cancelled, finished or claimed elsewhere
            log.info("%s is not active; dropped", job.call_id)
            await self.subscription.ack(ack_id)
            return
        if not 200 <= code < 300:
            log.warning("could not claim %s: HTTP %s", job.call_id, code)
            await self.subscription.nack(ack_id)
            return
        await self.subscription.ack(ack_id)  # the claim makes a redelivery harmless
        log.info("calling %s, attempt %s, %s", job.call_id, job.attempt, job.target.kind.value)

        async def answered(at: datetime) -> None:
            await self.report_in_progress(job.call_id, at)

        try:
            result = await self.place(job, answered)
        except Exception:
            log.exception("%s failed", job.call_id)
            result = failed_result(job, self.controller_id, CallFailureReason.AGENT_ERROR, started)
        body = result.model_dump_json()
        self.outbox.save(job.call_id, body)
        await self.deliver(job.call_id, body)

    async def report_in_progress(self, call_id: str, at: datetime) -> None:
        """Best effort: the result carries the answer time anyway."""
        for attempt in range(STATUS_TRIES):
            try:
                code = await self.backend.status(call_id, "in_progress", at, self.controller_id)
                if 200 <= code < 300 or code == 409:
                    return
            except httpx.HTTPError:
                pass
            await self._sleep(attempt + 1)

    async def deliver(self, call_id: str, body: str) -> bool:
        for attempt in range(RESULT_TRIES):
            try:
                code = await self.backend.result(call_id, body)
            except httpx.HTTPError as exc:
                log.warning("result of %s not delivered: %s", call_id, exc)
                code = None
            if code is not None and (200 <= code < 300 or code == 409):
                self.outbox.remove(call_id)
                log.info("result of %s delivered (HTTP %s)", call_id, code)
                return True
            if code is not None:
                log.warning("result of %s not delivered: HTTP %s", call_id, code)
            await self._sleep(min(2**attempt, 30))
        log.warning("result of %s stays in the outbox", call_id)
        return False

    async def flush(self) -> None:
        for call_id, body in self.outbox.pending():
            await self.deliver(call_id, body)


def asterisk_placer(controller_id: str) -> Place:
    """Place a call through Asterisk's ARI, as app `codguard`."""

    async def place(job: CallJob, on_answer: OnAnswer) -> CallResult:
        ari = AriClient(
            os.environ["ARI_URL"], os.environ["ARI_USER"], os.environ["ARI_PASSWORD"], APP
        )
        try:
            runner = CallRunner(ari, job, controller_id=controller_id, on_answer=on_answer)
            async with ari.event_stream() as events:

                async def route() -> None:
                    async for event in events:
                        if runner.wants(event):
                            runner.events.put_nowait(event)

                router = asyncio.create_task(route())
                try:
                    return await runner.run()
                finally:
                    router.cancel()
        finally:
            await ari.close()

    return place


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    controller_id = os.environ["CONTROLLER_ID"]
    http = httpx.AsyncClient(timeout=httpx.Timeout(10, read=90))
    backend_url = os.environ["BACKEND_URL"]
    controller = Controller(
        controller_id,
        Subscription(os.environ["CALL_JOBS_SUBSCRIPTION"], http),
        Backend(backend_url, http, IdTokens(backend_url, http)),
        Outbox(Path(os.environ.get("OUTBOX_DIR", "/var/lib/codguard/outbox"))),
        asterisk_placer(controller_id),
    )
    asyncio.run(controller.run_forever())


if __name__ == "__main__":
    main()
