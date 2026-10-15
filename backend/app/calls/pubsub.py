"""Publish call jobs to the Pub/Sub topic `call-jobs` over the REST API, as the service account
the backend runs as (publisher on the topic). One small request per call, so no client library."""

import base64
from functools import cached_property

import google.auth
from google.auth.transport.requests import AuthorizedSession

from app.schemas.telephony import CallJob

SCOPES = ["https://www.googleapis.com/auth/pubsub"]


class PubSubPublisher:
    def __init__(self, topic: str):
        self.topic = topic  # projects/<project>/topics/<topic>

    @cached_property
    def _session(self) -> AuthorizedSession:
        credentials, _ = google.auth.default(scopes=SCOPES)
        return AuthorizedSession(credentials)

    def publish(self, job: CallJob) -> str:
        """Publish one job and return its message ID. Raises on any failure."""
        message = {
            "data": base64.b64encode(job.model_dump_json().encode()).decode(),
            "attributes": {
                "env": job.env,
                "call_id": job.call_id,
                "target_kind": job.target.kind.value,
                "agent": job.agent.value,
            },
        }
        response = self._session.post(
            f"https://pubsub.googleapis.com/v1/{self.topic}:publish",
            json={"messages": [message]},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["messageIds"][0]
