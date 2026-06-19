from fastapi import APIRouter

from app.api.handlers import health

router = APIRouter()
router.add_api_route("/health", health, methods=["GET"])
