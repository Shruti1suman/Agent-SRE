from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.dependencies import current_user
from backend.app.services.governance_service import GovernanceService

router = APIRouter(tags=["governance"])


@router.get("/api/governance/overview")
def governance_overview(
    user: Annotated[dict, Depends(current_user)],
    project_id: str | None = None,
    agent_id: str | None = None,
) -> dict:
    return GovernanceService().overview(project_id=project_id, agent_id=agent_id)


@router.get("/api/governance/executions")
def governance_executions(
    user: Annotated[dict, Depends(current_user)],
    project_id: str | None = None,
    agent_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict]:
    return GovernanceService().executions(project_id=project_id, agent_id=agent_id)[:limit]


@router.get("/api/governance/warnings")
def governance_warnings(
    user: Annotated[dict, Depends(current_user)],
    project_id: str | None = None,
    agent_id: str | None = None,
) -> list[dict]:
    return GovernanceService().warnings(project_id=project_id, agent_id=agent_id)


@router.get("/api/governance/privacy")
def governance_privacy(
    user: Annotated[dict, Depends(current_user)],
    project_id: str | None = None,
    agent_id: str | None = None,
) -> list[dict]:
    return GovernanceService().privacy(project_id=project_id, agent_id=agent_id)


@router.get("/api/governance/audit-actions")
def governance_audit_actions(
    user: Annotated[dict, Depends(current_user)],
    project_id: str | None = None,
    agent_id: str | None = None,
) -> list[dict]:
    return GovernanceService().audit_actions(project_id=project_id, agent_id=agent_id)
