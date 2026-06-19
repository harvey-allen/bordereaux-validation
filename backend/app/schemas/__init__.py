"""Schemas package – Pydantic request/response models grouped by domain.

Import from the specific submodule for clarity, or from here for convenience:

    from app.schemas import ValidateRequest, ExceptionItem
"""
from __future__ import annotations

from app.schemas.configuration import (
    FieldMappingEstimationRequest,
    FieldMappingEstimationResponse,
    PackConfigRequest,
    PackConfigResponse,
    TemplateResponse,
    TerritoryOptionsResponse,
)
from app.schemas.exceptions import (
    ExceptionAnalyticsItem,
    ExceptionAnalyticsResponse,
    ExceptionApplyRequest,
    ExceptionCreateRequest,
    ExceptionItem,
    ExceptionListResponse,
    ExceptionUpdateRequest,
)
from app.schemas.results import (
    FailedTestItem,
    LatestResultsVersionResponse,
    PreviousVersionSummary,
    SavedResultsVersionItem,
    SavedResultsVersionListResponse,
    SavedResultsVersionPayloadResponse,
    SaveResultsVersionRequest,
    TestStatisticsResponse,
    ValidationHistoryItem,
    ValidationHistoryResponse,
    VersionComparisonResponse,
    VersionKpiSummary,
    VersionTrendPoint,
)
from app.schemas.rules_engine import RulesEngineResponse, RulesEngineRule
from app.schemas.subscription import (
    RegisterRequest,
    RegisterResponse,
    SubscriptionInfoResponse,
    TestPackCatalogResponse,
    UsageResponse,
)
from app.schemas.validation import ValidateRequest, ValidateResponse

__all__ = [
    # validation
    "ValidateRequest",
    "ValidateResponse",
    # configuration
    "PackConfigRequest",
    "PackConfigResponse",
    "TerritoryOptionsResponse",
    "TemplateResponse",
    "FieldMappingEstimationRequest",
    "FieldMappingEstimationResponse",
    # subscription
    "UsageResponse",
    "SubscriptionInfoResponse",
    "RegisterRequest",
    "RegisterResponse",
    "TestPackCatalogResponse",
    # rules engine
    "RulesEngineRule",
    "RulesEngineResponse",
    # results
    "ValidationHistoryItem",
    "ValidationHistoryResponse",
    "TestStatisticsResponse",
    "FailedTestItem",
    "SaveResultsVersionRequest",
    "SavedResultsVersionItem",
    "SavedResultsVersionListResponse",
    "SavedResultsVersionPayloadResponse",
    "LatestResultsVersionResponse",
    "VersionKpiSummary",
    "PreviousVersionSummary",
    "VersionTrendPoint",
    "VersionComparisonResponse",
    # exceptions
    "ExceptionItem",
    "ExceptionCreateRequest",
    "ExceptionUpdateRequest",
    "ExceptionListResponse",
    "ExceptionApplyRequest",
    "ExceptionAnalyticsItem",
    "ExceptionAnalyticsResponse",
]
