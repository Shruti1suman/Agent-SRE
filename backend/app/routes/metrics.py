from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.dependencies import current_user
from backend.app.services.metrics_service import MetricsService

router = APIRouter(prefix="/api/metrics-engine", tags=["metrics-engine"])


@router.post("/process-pending")
def process_pending(user: Annotated[dict, Depends(current_user)], limit: int = 100) -> dict:
    return MetricsService().process_pending(limit=limit)
