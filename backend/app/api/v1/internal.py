"""Service-to-service endpoints for the call controller on the Asterisk VM.

See docs/call-controller.md. The CallJob that starts a call is a Pub/Sub message, documented
here as the `call-job` webhook so that it is part of the contract.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Security

from app.api.errors import NotImplementedYet, problem_example, problem_responses
from app.api.security import controller_id_token
from app.schemas.calls import Call
from app.schemas.enums import ErrorCode
from app.schemas.telephony import CallJob, CallResult, CallStatusUpdate

CallId = Annotated[str, Path(description="Call ID from the CallJob.", examples=["call_01"])]

_NOT_ACTIVE = problem_example(
    409,
    ErrorCode.CALL_NOT_ACTIVE,
    detail="Call call_01 was cancelled before it was claimed. Ack the job and drop it.",
)
_RESULT_CONFLICT = problem_example(409, detail="Call call_01 already has a different result.")
_AUTH = problem_example(
    401, detail="Missing or invalid Google ID token, or not a controller service account."
)

internal_router = APIRouter(
    prefix="/internal", tags=["internal"], dependencies=[Security(controller_id_token)]
)


@internal_router.post(
    "/calls/{call_id}/status",
    response_model=Call,
    responses=problem_responses(401, 404, 409, 422, examples={401: _AUTH, 409: _NOT_ACTIVE}),
    summary="Report call progress; `dialing` claims the call",
    description="`dialing` is accepted only for a `queued` call, or again from the controller "
    "that already claimed it. `in_progress` is accepted only from that controller. "
    "Otherwise 409 `call_not_active`: the call was cancelled, finished or claimed elsewhere, "
    "so the controller acks the job and does not dial.",
)
async def report_call_status(call_id: CallId, body: CallStatusUpdate) -> Call:
    raise NotImplementedYet("report_call_status")


@internal_router.post(
    "/calls/{call_id}/result",
    response_model=Call,
    responses=problem_responses(401, 404, 409, 422, examples={401: _AUTH, 409: _RESULT_CONFLICT}),
    summary="Record the final result of a call",
    description="Idempotent: repeating the same result returns the call again; a different "
    "result for a finished call is 409 `conflict`. A completed result updates the orders "
    "(an `edited` outcome applies the changes and triggers a rescore).",
)
async def record_call_result(call_id: CallId, body: CallResult) -> Call:
    raise NotImplementedYet("record_call_result")


call_job_webhooks = APIRouter()


@call_job_webhooks.post(
    "call-job",
    operation_id="call_job",
    tags=["internal"],
    summary="Call job on the Pub/Sub topic `call-jobs`",
    description="Not an HTTP request: the backend publishes this body to the Pub/Sub topic "
    "`call-jobs` with the attributes `env`, `call_id`, `target_kind` and `agent`. The "
    "controller pulls it from its subscription, claims the call with "
    "`report_call_status` (`dialing`), then acks the message.",
)
def call_job(body: CallJob) -> None:
    """Documentation only."""
