"""Endpoints used by the shop web app (bearer token from /auth/login)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Path, Query, Security, UploadFile, status

from app.agents.agent import Pipeline
from app.agents.intake import receive
from app.agents.log import DecisionLog, entry, get_decision_log
from app.api.errors import ApiError, NotImplementedYet, problem_example, problem_responses
from app.api.security import CurrentUser, bearer_auth
from app.calls.service import CallService, get_call_service
from app.data import branches, order_csv
from app.data.orders import to_utc
from app.data.policies import PolicyStore, VersionTaken, get_policy_store
from app.data.shops import ShopStore, get_shop_store, shop_view
from app.data.store import OrderStore, get_store
from app.decision import lifecycle
from app.decision.inbox import InvalidQuery, order_page
from app.decision.views import order_detail, order_summary
from app.risk import artifacts, health
from app.schemas.calls import Call
from app.schemas.dashboard import BacktestResult, DashboardSummary, ModelHealth
from app.schemas.delivery import DeliveryImportResult, DeliveryOutcomeBatch
from app.schemas.enums import ContactBlockReason, ErrorCode, OrderStatus, RiskTier, Role
from app.schemas.orders import (
    ImportResult,
    ImportRowError,
    OrderCreate,
    OrderDetail,
    OrderPage,
    OrdersChange,
    OrderSummary,
    OrderUpdate,
    OverrideRequest,
)
from app.schemas.scoring import Decision
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


Shops = Annotated[ShopStore, Depends(get_shop_store)]
Policies = Annotated[PolicyStore, Depends(get_policy_store)]


@shop_router.get(
    "",
    response_model=Shop,
    responses=problem_responses(401),
    summary="Current user's shop and its settings per country",
    description="The shop exists from its first sign-in, with the defaults of each country "
    "where it has branches, so it works before the owner changes anything (onboarding, E7.1).",
)
def get_shop(user: CurrentUser, shops: Shops) -> Shop:
    return shop_view(user.shop_id, shops.get(user.shop_id, datetime.now(UTC)))


@shop_router.patch(
    "",
    response_model=Shop,
    responses=problem_responses(401, 403, 422),
    summary="Update the shop name or its settings per country (owner only)",
    description="Costs and contact hours apply to decisions and calls made after the change.",
)
def update_shop(body: ShopUpdate, user: CurrentUser, shops: Shops) -> Shop:
    if user.role != Role.OWNER:
        raise ApiError(403, ErrorCode.FORBIDDEN, "Forbidden", "Only the owner changes settings.")
    unknown = {c.country for c in body.countries or []} - set(branches.countries())
    if unknown:
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Validation error",
            f"The shop has no branch in {', '.join(sorted(unknown))}.",
        )
    return shop_view(user.shop_id, shops.update(user.shop_id, body, datetime.now(UTC)))


@shop_router.get(
    "/policy",
    response_model=Policy,
    responses=problem_responses(401),
    summary="Tier policy and call automation in force",
)
def get_policy(user: CurrentUser, policies: Policies) -> Policy:
    return policies.current(user.shop_id)


@shop_router.put(
    "/policy",
    response_model=Policy,
    responses=problem_responses(401, 403, 409, 422),
    summary="Replace the tier policy and call automation (owner only)",
    description="Creates a new version. It applies only to decisions made after "
    "`effective_from`; earlier decisions keep their version. `automation` sets which AI calls "
    "the agent places by itself; the calls it leaves out wait in review as suggestions.",
)
def update_policy(body: PolicyUpdate, user: CurrentUser, policies: Policies) -> Policy:
    if user.role != Role.OWNER:
        raise ApiError(403, ErrorCode.FORBIDDEN, "Forbidden", "Only the owner changes the policy.")
    try:
        return policies.save(user.shop_id, body, user.email, datetime.now(UTC))
    except ValueError as error:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "Validation error", str(error)) from None
    except VersionTaken:
        raise ApiError(
            409, ErrorCode.CONFLICT, "Conflict", "The policy changed meanwhile. Reload it."
        ) from None


@shop_router.get(
    "/policy/versions",
    response_model=list[Policy],
    responses=problem_responses(401),
    summary="All policy versions, newest first (audit)",
)
def list_policy_versions(user: CurrentUser, policies: Policies) -> list[Policy]:
    return policies.versions(user.shop_id)


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

IMPORT_WORKERS = 8
orders_router = APIRouter(prefix="/orders", tags=["orders"], dependencies=auth)
OrderSort = Literal["-placed_at", "placed_at", "-risk_score", "-cod_amount_vnd", "-updated_at"]


@orders_router.get(
    "",
    response_model=OrderPage,
    responses=problem_responses(401, 422),
    summary="Order inbox",
    description="One page of the shop's orders, filtered and sorted in the database; pass "
    "`next_cursor` back as `cursor` for the next page. Filter by branch, status, tier and placing "
    "time (a placing-time range needs `sort` by placing time). The manual review queue is "
    "`status=pending_review`. `q` finds orders by an exact order ID, shop order ID or full "
    "phone number; with `q` the result is one page.",
)
def list_orders(
    status_: Annotated[list[OrderStatus], Query(alias="status", default_factory=list)],
    tier: Annotated[list[RiskTier], Query(default_factory=list)],
    branch: Annotated[
        list[str],
        Query(default_factory=list, description="Branch IDs (config/branches.yaml)."),
    ],
    q: Annotated[
        str | None,
        Query(max_length=100, description="Exact order ID, shop order ID or full phone number."),
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
    try:
        return order_page(
            store,
            user.shop_id,
            statuses=status_,
            tiers=tier,
            branch_ids=branch,
            q=q,
            placed_from=to_utc(placed_from) if placed_from else None,
            placed_to=to_utc(placed_to) if placed_to else None,
            sort=sort,
            cursor=cursor,
            limit=limit,
        )
    except InvalidQuery as exc:
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Validation error",
            str(exc),
            errors=[{"loc": ["query"], "msg": str(exc), "type": "value_error"}],
        ) from exc


@orders_router.post(
    "",
    response_model=OrderSummary,
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(401, 409, 422),
    summary="Create one order",
    description="Scoring runs asynchronously; poll the order to see the score.",
)
def create_order(
    body: OrderCreate,
    user: CurrentUser,
    store: Annotated[OrderStore, Depends(get_store)],
    decision_log: Annotated[DecisionLog, Depends(get_decision_log)],
    calls: Annotated[CallService | None, Depends(get_call_service)],
    policies: Policies,
    shops: Shops,
) -> OrderSummary:
    # Sync, like the intake route: the pipeline's nodes make blocking Firestore calls.
    pipeline = Pipeline(
        store=store,
        log=decision_log,
        calls=calls,
        settings=shops.settings(user.shop_id),
        policy=policies.current(user.shop_id),
    )
    doc, duplicate = receive(
        body,
        user.shop_id,
        pipeline=pipeline,
        actor=user.email,
        message="Shop created the order manually.",
    )
    if duplicate:
        raise ApiError(
            409,
            ErrorCode.CONFLICT,
            "Conflict",
            f"An order with external_id {body.external_id} already exists.",
        )
    return order_summary(doc)


@orders_router.post(
    "/import",
    response_model=ImportResult,
    responses=problem_responses(400, 401, 422),
    summary="Import orders from a CSV file",
    description="One row per order, columns as in OrderCreate. `address` is the address as "
    "written (or an Address as JSON); `items` is JSON, or one item per row in `item_name`, "
    "`quantity` and `unit_price_vnd`. Up to 1,000 rows per file. Every imported order runs "
    "the pipeline at once, without the Gemini assessment and with simulated AI calls.",
)
def import_orders(
    file: Annotated[UploadFile, File(description="CSV, UTF-8.")],
    user: CurrentUser,
    store: Annotated[OrderStore, Depends(get_store)],
    decision_log: Annotated[DecisionLog, Depends(get_decision_log)],
    policies: Policies,
    shops: Shops,
) -> ImportResult:
    now = datetime.now(UTC)
    try:
        rows = order_csv.read_rows(file.file.read(order_csv.MAX_BYTES + 1))
    except order_csv.BadFile as error:
        raise ApiError(400, ErrorCode.VALIDATION_ERROR, "Bad request", str(error)) from error
    orders: list[OrderCreate] = []
    rejected: list[ImportRowError] = []
    repeats, seen = 0, set()
    for number, row in enumerate(rows, start=1):
        parsed = order_csv.parse_row(number, row, now)
        if isinstance(parsed, ImportRowError):
            rejected.append(parsed)
        elif parsed.external_id and parsed.external_id in seen:
            repeats += 1  # the same order twice in one file
        else:
            seen.add(parsed.external_id)
            orders.append(parsed)
    # A file is a batch: its orders skip the Gemini assessment, which keeps the daily quota, and
    # their AI calls stay simulated, so one upload cannot queue hundreds of real calls.
    pipeline = Pipeline(
        store=store,
        log=decision_log,
        assess=False,
        settings=shops.settings(user.shop_id),
        policy=policies.current(user.shop_id),
    )

    def duplicate(order: OrderCreate) -> bool:
        _, known = receive(
            order,
            user.shop_id,
            pipeline=pipeline,
            actor=user.email,
            message="Order imported from a CSV file.",
        )
        return known

    # Each order runs its own pipeline (asyncio.run in a worker thread); a few at a time keeps a
    # 1,000-row file within the request timeout.
    with ThreadPoolExecutor(max_workers=IMPORT_WORKERS) as pool:
        known = sum(pool.map(duplicate, orders))
    return ImportResult(
        received=len(rows),
        imported=len(orders) - known,
        duplicates=repeats + known,
        rejected=rejected,
    )


@orders_router.get(
    "/last-change",
    response_model=OrdersChange,
    responses=problem_responses(401),
    summary="When the shop's orders last changed",
    description="One document read. The inbox polls it and reloads its page only when the value "
    "changes, so new orders appear within seconds without reloading pages for nothing.",
)
def last_orders_change(
    user: CurrentUser, store: Annotated[OrderStore, Depends(get_store)]
) -> OrdersChange:
    return OrdersChange(updated_at=store.last_change(user.shop_id))


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
def update_order(
    order_id: OrderId,
    body: OrderUpdate,
    user: CurrentUser,
    store: Annotated[OrderStore, Depends(get_store)],
    policies: Policies,
    shops: Shops,
) -> OrderDetail:
    doc = lifecycle.edit_order(
        store,
        order_id,
        user.shop_id,
        body,
        datetime.now(UTC),
        actor=user.email,
        settings=shops.settings(user.shop_id),
        policy=policies.current(user.shop_id),
    )
    return order_detail(doc)


@orders_router.post(
    "/{order_id}/override",
    response_model=OrderDetail,
    responses=problem_responses(401, 404, 409, 422, examples={409: _NOT_EDITABLE}),
    summary="Apply a staff decision with a reason",
    description="Recorded in the audit log. The action must be in "
    "`allowed_overrides` of the order.",
)
def override_order(
    order_id: OrderId,
    body: OverrideRequest,
    user: CurrentUser,
    store: Annotated[OrderStore, Depends(get_store)],
    decision_log: Annotated[DecisionLog, Depends(get_decision_log)],
) -> OrderDetail:
    now = datetime.now(UTC)
    doc = lifecycle.override_order(
        store, order_id, user.shop_id, body.action, body.reason, user.email, now
    )
    row = entry(doc, Decision.model_validate(doc["decision"]), workflow="staff", step="override")
    decision_log.write(row | {"actor": user.email, "reason": body.reason})
    return order_detail(doc)


@orders_router.post(
    "/{order_id}/calls",
    response_model=Call,
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(401, 404, 409, examples={409: _CONTACT_BLOCKED}),
    summary="Start an AI confirmation call now",
    description="Contact protection still applies: 409 `contact_blocked` with "
    "`block_reasons` when the call is not allowed.",
)
def start_call(
    order_id: OrderId,
    user: CurrentUser,
    calls: Annotated[CallService | None, Depends(get_call_service)],
) -> Call:
    if calls is None:  # CALL_JOBS_TOPIC unset: the frontend's mock simulates the call
        raise NotImplementedYet("start_call")
    return calls.start_for_shop(order_id, user.shop_id, user.email, datetime.now(UTC))


# ---------------------------------------------------------------- calls

calls_router = APIRouter(prefix="/calls", tags=["calls"], dependencies=auth)


@calls_router.get(
    "/{call_id}",
    response_model=Call,
    responses=problem_responses(401, 404),
    summary="Call status and result (poll during a live call)",
)
def get_call(
    call_id: Annotated[str, Path(examples=["call_01"])],
    user: CurrentUser,
    calls: Annotated[CallService | None, Depends(get_call_service)],
) -> Call:
    if calls is None:
        raise NotImplementedYet("get_call")
    return calls.get_for_shop(call_id, user.shop_id, datetime.now(UTC))


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


@dashboard_router.get(
    "/model-health",
    response_model=list[ModelHealth],
    responses=problem_responses(401),
    summary="How each country's risk model is doing, in plain words",
    description="From the daily check (codguard-monitor) and the trained model. `status` is "
    "`update_recommended` when the model catches fewer failed deliveries on recent orders, recent "
    "orders look different from what it learned, or many orders got a delivery result since.",
)
def get_model_health(user: CurrentUser) -> list[ModelHealth]:
    return health.model_health(datetime.now(UTC))


@dashboard_router.post(
    "/model-health/update",
    response_model=list[ModelHealth],
    responses=problem_responses(401, 403, 409),
    summary="Update the risk models (owner only)",
    description="Starts codguard-train: every country's model learns again from all orders with a "
    "delivery result, in about two minutes. A new model replaces the current one only if it is at "
    "least as good; the current one keeps scoring meanwhile. 409 while an update is running.",
)
def update_models(user: CurrentUser) -> list[ModelHealth]:
    if user.role != Role.OWNER:
        raise ApiError(403, ErrorCode.FORBIDDEN, "Forbidden", "Only the owner updates the model.")
    try:
        return health.request_update(datetime.now(UTC))
    except health.UpdateRunning:
        raise ApiError(
            409, ErrorCode.CONFLICT, "Conflict", "An update is already running. Try again later."
        ) from None
