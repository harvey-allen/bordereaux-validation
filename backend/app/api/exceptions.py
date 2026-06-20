from fastapi import APIRouter

from app.api.handlers import (
    apply_exception_tag,
    create_exception,
    delete_exception,
    get_exception_analytics,
    list_exceptions,
    update_exception,
)
from app.schemas.exceptions import (
    ExceptionAnalyticsResponse,
    ExceptionItem,
    ExceptionListResponse,
)

router = APIRouter()
router.add_api_route(
    "/api/v1/exceptions",
    list_exceptions,
    methods=["GET"],
    response_model=ExceptionListResponse,
)
router.add_api_route(
    "/api/v1/exceptions",
    create_exception,
    methods=["POST"],
    response_model=ExceptionItem,
)
router.add_api_route(
    "/api/v1/exceptions/{exception_id}",
    update_exception,
    methods=["PUT"],
    response_model=ExceptionItem,
)
router.add_api_route(
    "/api/v1/exceptions/{exception_id}",
    delete_exception,
    methods=["DELETE"],
)
router.add_api_route(
    "/api/v1/exceptions/apply",
    apply_exception_tag,
    methods=["POST"],
)
router.add_api_route(
    "/api/v1/exceptions/analytics",
    get_exception_analytics,
    methods=["GET"],
    response_model=ExceptionAnalyticsResponse,
)
