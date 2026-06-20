from fastapi import FastAPI


def include_api_routers(app: FastAPI) -> None:
    from .configuration import router as configuration_router
    from .exceptions import router as exceptions_router
    from .health import router as health_router
    from .results import router as results_router
    from .rules_engine import router as rules_engine_router
    from .subscription import router as subscription_router
    from .validation import router as validation_router

    app.include_router(health_router)
    app.include_router(configuration_router)
    app.include_router(rules_engine_router)
    app.include_router(subscription_router)
    app.include_router(validation_router)
    app.include_router(results_router)
    app.include_router(exceptions_router)
