from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.router import api_router
from backend.app.repositories.schema_repository import SchemaRepository
from backend.app.services.background_metrics_worker import BackgroundMetricsWorker
from backend.core.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)

    allow_origins = ["*"] if settings.cors_origins == "*" else [
        origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.on_event("startup")
    async def startup() -> None:
        SchemaRepository().ensure_schema()
        app.state.metrics_worker = BackgroundMetricsWorker()
        app.state.metrics_worker.start()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        metrics_worker = getattr(app.state, "metrics_worker", None)
        if metrics_worker is not None:
            await metrics_worker.stop()

    return app


app = create_app()

