from fastapi import APIRouter

from app.api.handlers import (
    get_latest_results,
    get_result_version_payload,
    get_result_versions,
    get_result_versions_comparison,
    remove_result_version,
    remove_result_version_by_id,
    save_results,
    update_result_version_by_id_endpoint,
)
from app.schemas.results import (
    LatestResultsVersionResponse,
    SavedResultsVersionItem,
    SavedResultsVersionListResponse,
    SavedResultsVersionPayloadResponse,
    SaveResultsVersionRequest,
    VersionComparisonResponse,
)

router = APIRouter()
router.add_api_route(
    "/api/v1/results/versions",
    save_results,
    methods=["POST"],
    response_model=SavedResultsVersionItem,
)
router.add_api_route(
    "/api/v1/results/versions",
    get_result_versions,
    methods=["GET"],
    response_model=SavedResultsVersionListResponse,
)
router.add_api_route(
    "/api/v1/results/latest",
    get_latest_results,
    methods=["GET"],
    response_model=LatestResultsVersionResponse,
)
router.add_api_route(
    "/api/v1/results/versions/{version_id:int}",
    get_result_version_payload,
    methods=["GET"],
    response_model=SavedResultsVersionPayloadResponse,
)
router.add_api_route(
    "/api/v1/results/versions/comparison",
    get_result_versions_comparison,
    methods=["GET"],
    response_model=VersionComparisonResponse,
)
router.add_api_route(
    "/api/v1/results/versions/{version_id:int}",
    update_result_version_by_id_endpoint,
    methods=["PUT"],
    response_model=SavedResultsVersionItem,
)
router.add_api_route(
    "/api/v1/results/versions",
    remove_result_version,
    methods=["DELETE"],
)
router.add_api_route(
    "/api/v1/results/versions/{version_id:int}",
    remove_result_version_by_id,
    methods=["DELETE"],
)
