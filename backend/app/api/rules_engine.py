from fastapi import APIRouter

from app.api.handlers import get_rules_engine_rules
from app.schemas.rules_engine import RulesEngineResponse

router = APIRouter()
router.add_api_route(
    "/api/v1/rules-engine",
    get_rules_engine_rules,
    methods=["GET"],
    response_model=RulesEngineResponse,
)
