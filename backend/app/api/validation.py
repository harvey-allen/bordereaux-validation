from fastapi import APIRouter

from app.api.handlers import get_history, get_history_detail, get_statistics, validate_range
from app.schemas.results import TestStatisticsResponse, ValidationHistoryResponse
from app.schemas.validation import ValidateResponse

router = APIRouter()
router.add_api_route(
    "/validate-range",
    validate_range,
    methods=["POST"],
    response_model=ValidateResponse,
)
router.add_api_route(
    "/api/v1/history",
    get_history,
    methods=["GET"],
    response_model=ValidationHistoryResponse,
)
router.add_api_route(
    "/api/v1/history/{run_id}",
    get_history_detail,
    methods=["GET"],
)
router.add_api_route(
    "/api/v1/statistics",
    get_statistics,
    methods=["GET"],
    response_model=TestStatisticsResponse,
)
