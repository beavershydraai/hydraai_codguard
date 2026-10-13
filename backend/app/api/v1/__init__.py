from fastapi import APIRouter

from app.api.v1.external import demo_router, intake_router, public_router
from app.api.v1.internal import call_job_webhooks, internal_router
from app.api.v1.shop_app import (
    calls_router,
    dashboard_router,
    delivery_router,
    me_router,
    orders_router,
    shop_router,
)

router = APIRouter(prefix="/api/v1")
for r in (
    me_router,
    shop_router,
    orders_router,
    calls_router,
    delivery_router,
    dashboard_router,
    intake_router,
    public_router,
    demo_router,
    internal_router,
):
    router.include_router(r)

__all__ = ["call_job_webhooks", "router"]
