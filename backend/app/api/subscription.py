from fastapi import APIRouter

from app.api.handlers import get_subscription_info, get_test_pack_catalog, get_usage, register_user
from app.schemas.subscription import (
    RegisterResponse,
    SubscriptionInfoResponse,
    TestPackCatalogResponse,
    UsageResponse,
)

router = APIRouter()
router.add_api_route(
    "/api/v1/register",
    register_user,
    methods=["POST"],
    response_model=RegisterResponse,
)
router.add_api_route(
    "/api/v1/usage",
    get_usage,
    methods=["GET"],
    response_model=UsageResponse,
)
router.add_api_route(
    "/api/v1/subscription",
    get_subscription_info,
    methods=["GET"],
    response_model=SubscriptionInfoResponse,
)
router.add_api_route(
    "/api/v1/test-packs",
    get_test_pack_catalog,
    methods=["GET"],
    response_model=TestPackCatalogResponse,
)
