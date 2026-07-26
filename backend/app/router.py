from fastapi import APIRouter

from backend.app.routes import auth, dashboard, governance, health, incidents, ingestion, metrics, projects, slos

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(dashboard.router)
api_router.include_router(incidents.router)
api_router.include_router(governance.router)
api_router.include_router(ingestion.router)
api_router.include_router(metrics.router)
api_router.include_router(slos.router)

