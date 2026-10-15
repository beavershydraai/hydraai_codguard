"""Endpoints outside the shop app: intake API, buyer confirmation page, demo controls."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Security, status

from app.agents.agent import Pipeline
from app.agents.log import DecisionLog, get_decision_log
from app.agents.runner import run_new_order_sync
from app.api.errors import ApiError, NotImplementedYet, problem_example, problem_responses
from app.api.security import bearer_auth, intake_api_key
from app.calls.service import CallService, get_call_service
from app.data.orders import order_document
from app.data.store import OrderStore, get_store, order_id_for, phone_key, shop_for_key
from app.schemas.confirm import BuyerOrderView, BuyerResponse, BuyerResponseResult
from app.schemas.demo import DemoResetResult, SpamSimulationResult
from app.schemas.enums import ErrorCode
from app.schemas.orders import IntakeAccepted, OrderCreate

log = logging.getLogger(__name__)
intake_router = APIRouter(
    prefix="/intake", tags=["intake"], dependencies=[Security(intake_api_key)]
)


@intake_router.post(
    "/orders",
    response_model=IntakeAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(401, 422),
    summary="Receive an order from an external sales tool",
    description="Idempotent on `external_id`: a repeat returns the existing order "
    "with `duplicate: true`. A new order runs the E4.7 pipeline before the response, so its "
    "status is already the one the decision engine chose.",
)
def intake_order(
    body: OrderCreate,
    api_key: Annotated[str | None, Security(intake_api_key)],
    store: Annotated[OrderStore, Depends(get_store)],
    decision_log: Annotated[DecisionLog, Depends(get_decision_log)],
    calls: Annotated[CallService | None, Depends(get_call_service)],
) -> IntakeAccepted:
    shop_id = shop_for_key(api_key)
    if shop_id is None:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "Unauthorized", "Missing or unknown X-Api-Key.")
    order_id = order_id_for(shop_id, body.external_id)
    doc = order_document(
        body, order_id=order_id, shop_id=shop_id, phone_key=phone_key(), now=datetime.now(UTC)
    )
    existing = store.create(doc)
    if existing:
        return IntakeAccepted(order_id=order_id, status=existing["status"], duplicate=True)
    try:  # a pipeline problem must never lose the order: it stays stored, for review or unscored
        pipeline = Pipeline(store=store, log=decision_log, calls=calls)
        run_new_order_sync(order_id, shop_id, pipeline=pipeline)
        doc = store.get(order_id) or doc
    except Exception:
        log.exception("The pipeline failed for %s", order_id)
    return IntakeAccepted(order_id=order_id, status=doc["status"], duplicate=False)


public_router = APIRouter(prefix="/public", tags=["public"])
Token = Annotated[
    str,
    Path(
        min_length=16,
        max_length=128,
        description="Signed link token.",
        examples=["tk_9fQ2xL7mVb3sR8cZ1yN4"],
    ),
]


@public_router.get(
    "/confirmations/{token}",
    response_model=BuyerOrderView,
    responses=problem_responses(404, 410),
    summary="Buyer confirmation page data (no login)",
)
async def get_confirmation(token: Token) -> BuyerOrderView:
    raise NotImplementedYet("get_confirmation")


@public_router.post(
    "/confirmations/{token}",
    response_model=BuyerResponseResult,
    responses=problem_responses(
        404,
        409,
        410,
        422,
        examples={
            409: problem_example(
                409, ErrorCode.LINK_ALREADY_USED, detail="This order was already answered."
            )
        },
    ),
    summary="Buyer answers: confirm, edit address, cancel, or not ordered",
    description="`not_ordered` blocks the phone for 30 days across all shops.",
)
async def respond_confirmation(token: Token, body: BuyerResponse) -> BuyerResponseResult:
    raise NotImplementedYet("respond_confirmation")


demo_router = APIRouter(prefix="/demo", tags=["demo"], dependencies=[Security(bearer_auth)])


@demo_router.post(
    "/reset",
    response_model=DemoResetResult,
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(401, 403, 429),
    summary="Reset the demo shop to its fixed seed data",
)
async def reset_demo() -> DemoResetResult:
    raise NotImplementedYet("reset_demo")


@demo_router.post(
    "/spam-simulation",
    response_model=SpamSimulationResult,
    responses=problem_responses(401, 403, 429),
    summary="Run the abuse scenario: 50 orders from 20 accounts to one phone",
)
async def run_spam_simulation() -> SpamSimulationResult:
    raise NotImplementedYet("run_spam_simulation")
