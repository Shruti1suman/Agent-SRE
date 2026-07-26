from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.dependencies import current_user
from backend.app.repositories.dashboard_repository import DashboardRepository
from backend.app.services.incident_chat_service import IncidentChatService
from backend.app.services.incident_report_service import IncidentReportService
from backend.core.settings import settings

router = APIRouter(tags=["dashboard"])


class IncidentChatMessage(BaseModel):
    role: str
    content: str


class IncidentChatRequest(BaseModel):
    incident_id: str
    message: str
    history: list[IncidentChatMessage] = Field(default_factory=list)


@router.get("/api/overview")
def overview(user: Annotated[dict, Depends(current_user)], project_id: str | None = None) -> dict:
    return DashboardRepository().overview(project_id)


@router.get("/api/traces")
def traces(user: Annotated[dict, Depends(current_user)], project_id: str | None = None) -> list[dict]:
    return DashboardRepository().traces(project_id)


@router.get("/api/traces/{execution_id}/replay")
def trace_replay(execution_id: str, user: Annotated[dict, Depends(current_user)]) -> dict:
    repository = DashboardRepository()
    trace = repository.trace_by_execution(execution_id)
    if not trace:
        return {"error": f"execution_id not found: {execution_id}"}
    if "error" in trace:
        return trace
    return repository.replay_from_trace(trace)


@router.get("/api/metrics")
def metrics(user: Annotated[dict, Depends(current_user)], project_id: str | None = None) -> list[dict]:
    return DashboardRepository().metrics(project_id)


@router.get("/api/metrics/{trace_id}")
def metric_detail(trace_id: str, user: Annotated[dict, Depends(current_user)]) -> dict:
    return DashboardRepository().metric_detail(trace_id)


@router.get("/api/incidents")
def incidents(user: Annotated[dict, Depends(current_user)], project_id: str | None = None) -> list[dict]:
    return DashboardRepository().incidents(project_id)


@router.post("/api/incidents/ask")
def ask_incident(
    payload: IncidentChatRequest,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    history = [item.model_dump() for item in payload.history]
    return IncidentChatService().answer(payload.incident_id, payload.message, history, user.get("user_id"))


@router.get("/api/incidents/{incident_id}/chat")
def incident_chat_history(
    incident_id: str,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    return IncidentChatService().history(incident_id, user.get("user_id"))


@router.get("/api/incidents/{incident_id}/report")
def incident_report(
    incident_id: str,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    return IncidentReportService().build(incident_id)


@router.get("/api/dashboard")
def dashboard(user: Annotated[dict, Depends(current_user)], project_id: str | None = None) -> dict:
    repository = DashboardRepository()
    return {
        "overview": repository.overview(project_id),
        "traces": repository.traces(project_id),
        "metrics": repository.metrics(project_id),
        "incidents": repository.incidents(project_id),
    }


@router.get("/api/agents")
async def agents(user: Annotated[dict, Depends(current_user)]) -> object:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.governance_base_url}/agents")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        return {"error": str(exc)}

