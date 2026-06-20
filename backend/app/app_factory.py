from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import include_api_routers
from app.api.handlers import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="Reporting Validation API",
        version="1.0.0",
        description="Excel data validation API for configurable reporting test packs with subscription-based access.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    include_api_routers(app)
    return app


app = create_app()
