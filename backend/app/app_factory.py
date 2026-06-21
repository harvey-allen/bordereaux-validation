from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import include_api_routers
from app.api.handlers import lifespan
from app.config import config


def create_app() -> FastAPI:
    app = FastAPI(
        title="Reporting Validation API",
        version="1.0.0",
        description="Excel data validation API for configurable reporting test packs with subscription-based access.",
        lifespan=lifespan,
    )

    # Configure CORS based on environment
    # In production, restrict to specific origins; in development, allow all
    cors_origins = ["*"] if config.is_development else [
        "https://your-production-domain.com",  # Update with actual production domain
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    include_api_routers(app)

    # Log configuration on startup (non-sensitive data only)
    app.debug = config.is_development

    return app


app = create_app()
