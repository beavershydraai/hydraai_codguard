from fastapi import APIRouter

from app.api.v1.auth import auth_router
from app.api.v1.external import demo_router, intake_router, public_router
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
    auth_router,
    me_router,
    shop_router,
    orders_router,
    calls_router,
    delivery_router,
    dashboard_router,
    intake_router,
    public_router,
    demo_router,
):
    router.include_router(r)
