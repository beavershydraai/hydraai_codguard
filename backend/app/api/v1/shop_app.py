"""Endpoints used by the shop web app (bearer token from /auth/login)."""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Path, Query, Security, UploadFile, status

from app.api.errors import ApiError, NotImplementedYet, problem_example, problem_responses
from app.api.security import CurrentUser, bearer_auth
from app.data.orders import to_utc
from app.data.store import OrderStore, get_store
from app.decision.inbox import InvalidCursor, order_page
from app.decision.views import order_detail
from app.risk import artifacts
from app.schemas.calls import Call
from app.schemas.dashboard import BacktestResult, DashboardSummary
from app.schemas.delivery import DeliveryImportResult, DeliveryOutcomeBatch
from app.schemas.enums import ContactBlockReason, ErrorCode, OrderStatus, RiskTier
from app.schemas.orders import (
    ImportResult,
    OrderCreate,
    OrderDetail,
    OrderPage,
    OrderSummary,
    OrderUpdate,
    OverrideRequest,
)
from app.schemas.shops import Me, Policy, PolicyUpdate, Shop, ShopUpdate

auth = [Security(bearer_auth)]
OrderId = Annotated[str, Path(description="Order ID.", examples=["ord_01"])]

# ---------------------------------------------------------------- me & shop

me_router = APIRouter(tags=["me"], dependencies=auth)
shop_router = APIRouter(prefix="/shop", tags=["shop"], dependencies=auth)


@me_router.get("/me", response_model=Me, responses=problem_responses(401), summary="Current user")
async def get_me(user: CurrentUser) -> Me:
    return Me(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        shop_id=user.shop_id,
    )


@shop_router.get(
    "",
    response_model=Shop,
    responses=problem_responses(401),
    summary="Current user's shop and settings",
)
async def get_shop() -> Shop:
    raise NotImplementedYet("get_shop")


@shop_router.patch(
    "",
    response_model=Shop,
    responses=problem_responses(401, 403, 422),
    summary="Update shop name or settings (owner only)",
)
async def update_shop(body: ShopUpdate) -> Shop:
    raise NotImplementedYet("update_shop")


@shop_router.get(
    "/policy",
    response_model=Policy,
    responses=problem_responses(401),
    summary="Tier policy in force",
)
async def get_policy() -> Policy:
    raise NotImplementedYet("get_policy")


@shop_router.put(
    "/policy",
    response_model=Policy,
    responses=problem_responses(401, 403, 422),
    summary="Replace the tier policy (owner only)",
    description="Creates a new version. It applies only to decisions made after "
    "`effective_from`; earlier decisions keep their version.",
)
async def update_policy(body: PolicyUpdate) -> Policy:
    raise NotImplementedYet("update_policy")


@shop_router.get(
    "/policy/versions",
    response_model=list[Policy],
    responses=problem_responses(401),
    summary="All policy versions, newest first (audit)",
)
async def list_policy_versions() -> list[Policy]:
    raise NotImplementedYet("list_policy_versions")


# ---------------------------------------------------------------- orders

_NOT_EDITABLE = problem_example(
    409, ErrorCode.ORDER_NOT_EDITABLE, detail="Order ord_01 has already shipped."
)
_CONTACT_BLOCKED = problem_example(
    409,
    ErrorCode.CONTACT_BLOCKED,
    title="Contact blocked",
    detail="This phone already had an AI call in the last 24 hours.",
    block_reasons=[ContactBlockReason.DAILY_CALL_LIMIT.value],
)

orders_router = APIRouter(prefix="/orders", tags=["orders"], dependencies=auth)
OrderSort = Literal["-placed_at", "placed_at", "-risk_score", "-cod_amount_vnd", "-updated_at"]


@orders_router.get(
    "",
    response_model=OrderPage,
    responses=problem_responses(401, 422),
    summary="Order inbox",
    description="Filter by status and tier. The manual review queue is `status=pending_review`.",
)
def list_orders(
    status_: Annotated[list[OrderStatus], Query(alias="status", default_factory=list)],
    tier: Annotated[list[RiskTier], Query(default_factory=list)],
    q: Annotated[
        str | None, Query(max_length=100, description="Search buyer name, phone or external_id.")
    ] = None,
    placed_from: Annotated[datetime | None, Query()] = None,
    placed_to: Annotated[datetime | None, Query()] = None,
    sort: Annotated[OrderSort, Query()] = "-placed_at",
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    *,
    user: CurrentUser,
    store: Annotated[OrderStore, Depends(get_store)],
) -> OrderPage:
    docs = store.for_shop(
        user.shop_id,
        placed_from=to_utc(placed_from) if placed_from else None,
        placed_to=to_utc(placed_to) if placed_to else None,
    )
    try:
        return order_page(
            docs,
            statuses=status_,
            tiers=tier,
            q=q,
            placed_from=placed_from,
            placed_to=placed_to,
            sort=sort,
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursor as exc:
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Validation error",
            str(exc),
            errors=[{"loc": ["query", "cursor"], "msg": str(exc), "type": "value_error"}],
        ) from exc


@orders_router.post(
    "",
    response_model=OrderSummary,
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(401, 409, 422),
    summary="Create one order",
    description="Scoring runs asynchronously; poll the order to see the score.",
)
async def create_order(body: OrderCreate) -> OrderSummary:
    raise NotImplementedYet("create_order")


@orders_router.post(
    "/import",
    response_model=ImportResult,
    responses=problem_responses(400, 401, 422),
    summary="Import orders from a CSV file",
    description="One row per order, columns as in OrderCreate (items as JSON). "
    "Up to 1,000 rows per file.",
)
async def import_orders(
    file: Annotated[UploadFile, File(description="CSV, UTF-8.")],
) -> ImportResult:
    raise NotImplementedYet("import_orders")


@orders_router.get(
    "/{order_id}",
    response_model=OrderDetail,
    responses=problem_responses(401, 404),
    summary="Order page: score, reasons, decision, contacts, calls, timeline",
)
def get_order(
    order_id: OrderId,
    user: CurrentUser,
    store: Annotated[OrderStore, Depends(get_store)],
) -> OrderDetail:
    doc = store.get(order_id)
    # Another shop's order answers 404 too, so ids cannot be probed across shops.
    if doc is None or doc.get("shop_id") != user.shop_id:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Not found", f"Order {order_id} not found.")
    return order_detail(doc)


@orders_router.patch(
    "/{order_id}",
    response_model=OrderDetail,
    responses=problem_responses(401, 404, 409, 422, examples={409: _NOT_EDITABLE}),
    summary="Edit an order before it ships",
    description="Triggers a new scoring run. 409 `order_not_editable` once shipped.",
)
async def update_order(order_id: OrderId, body: OrderUpdate) -> OrderDetail:
    raise NotImplementedYet("update_order")


@orders_router.post(
    "/{order_id}/override",
    response_model=OrderDetail,
    responses=problem_responses(401, 404, 409, 422, examples={409: _NOT_EDITABLE}),
    summary="Apply a staff decision with a reason",
    description="Recorded in the audit log. The action must be in "
    "`allowed_overrides` of the order.",
)
async def override_order(order_id: OrderId, body: OverrideRequest) -> OrderDetail:
    raise NotImplementedYet("override_order")


@orders_router.post(
    "/{order_id}/calls",
    response_model=Call,
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(401, 404, 409, examples={409: _CONTACT_BLOCKED}),
    summary="Start an AI confirmation call now",
    description="Contact protection still applies: 409 `contact_blocked` with "
    "`block_reasons` when the call is not allowed.",
)
async def start_call(order_id: OrderId) -> Call:
    raise NotImplementedYet("start_call")


# ---------------------------------------------------------------- calls

calls_router = APIRouter(prefix="/calls", tags=["calls"], dependencies=auth)


@calls_router.get(
    "/{call_id}",
    response_model=Call,
    responses=problem_responses(401, 404),
    summary="Call status and result (poll during a live call)",
)
async def get_call(call_id: Annotated[str, Path(examples=["call_01"])]) -> Call:
    raise NotImplementedYet("get_call")


# ---------------------------------------------------------------- delivery outcomes

delivery_router = APIRouter(prefix="/delivery-outcomes", tags=["delivery"], dependencies=auth)


@delivery_router.post(
    "",
    response_model=DeliveryImportResult,
    responses=problem_responses(401, 422),
    summary="Record delivery outcomes (updates phone history)",
)
async def record_delivery_outcomes(body: DeliveryOutcomeBatch) -> DeliveryImportResult:
    raise NotImplementedYet("record_delivery_outcomes")


@delivery_router.post(
    "/import",
    response_model=DeliveryImportResult,
    responses=problem_responses(400, 401, 422),
    summary="Import delivery outcomes from a CSV file",
)
async def import_delivery_outcomes(
    file: Annotated[UploadFile, File(description="CSV, UTF-8.")],
) -> DeliveryImportResult:
    raise NotImplementedYet("import_delivery_outcomes")


# ---------------------------------------------------------------- dashboard

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=auth)


@dashboard_router.get(
    "/summary",
    response_model=DashboardSummary,
    responses=problem_responses(401, 422),
    summary="ROI dashboard",
)
async def get_dashboard_summary(
    period_from: Annotated[date, Query(alias="from")],
    period_to: Annotated[date, Query(alias="to")],
) -> DashboardSummary:
    raise NotImplementedYet("get_dashboard_summary")


@dashboard_router.get(
    "/backtest",
    response_model=BacktestResult,
    responses=problem_responses(401, 404),
    summary="Latest backtest of a country's model: lift curves and policy comparison",
)
def get_backtest(
    country: Annotated[
        Literal["VN", "SG", "PH"], Query(description="Country of the model (one per country).")
    ] = "VN",
) -> BacktestResult:
    """The backtest the training job stored with the country's model (app/risk/backtest.py)."""
    raw = artifacts.read("latest/backtest.json", country)
    if raw is None:  # the country's model has not been trained since the backtest was added
        raise ApiError(404, ErrorCode.NOT_FOUND, "No backtest yet", "Run the codguard-train job.")
    return BacktestResult.model_validate_json(raw)
