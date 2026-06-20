from fastapi import APIRouter

from app.api.handlers import (
    estimate_field_mapping,
    generate_template,
    get_field_config_territories,
    get_pack_config,
    upsert_pack_config,
)
from app.schemas.configuration import (
    FieldMappingEstimationResponse,
    PackConfigResponse,
    TemplateResponse,
    TerritoryOptionsResponse,
)

router = APIRouter()
router.add_api_route(
    "/api/v1/field-config/territories",
    get_field_config_territories,
    methods=["GET"],
    response_model=TerritoryOptionsResponse,
)
router.add_api_route(
    "/api/v1/generate-template",
    generate_template,
    methods=["GET"],
    response_model=TemplateResponse,
)
router.add_api_route(
    "/api/v1/field-config/estimate-mapping",
    estimate_field_mapping,
    methods=["POST"],
    response_model=FieldMappingEstimationResponse,
)
router.add_api_route(
    "/api/v1/pack-config",
    get_pack_config,
    methods=["GET"],
    response_model=PackConfigResponse,
)
router.add_api_route(
    "/api/v1/pack-config",
    upsert_pack_config,
    methods=["PUT"],
    response_model=PackConfigResponse,
)
