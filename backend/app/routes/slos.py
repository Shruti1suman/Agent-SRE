from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import current_user
from backend.app.repositories.project_repository import ProjectRepository
from backend.app.services.slo_service import SloService
from backend.models.slos import CreateSloRequest, UpdateSloRequest

router = APIRouter(prefix="/api/slos", tags=["slos"])


def ensure_project_access(project_id: str, user: dict) -> None:
    project = ProjectRepository().get_for_user(project_id, user.get("user_id"))
    if not project or "error" in project:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/metrics/catalog")
def metrics_catalog(user: Annotated[dict, Depends(current_user)]) -> dict:
    return SloService.catalog()


@router.get("")
def overview(
    user: Annotated[dict, Depends(current_user)],
    project_id: str,
) -> dict:
    ensure_project_access(project_id, user)
    return SloService().overview(project_id)


@router.post("")
def create_slo(
    payload: CreateSloRequest,
    user: Annotated[dict, Depends(current_user)],
    project_id: str,
) -> dict:
    ensure_project_access(project_id, user)
    created = SloService().create(project_id, payload.model_dump())
    if "error" in created:
        raise HTTPException(status_code=400, detail=created["error"])
    return created


@router.patch("/{slo_id}")
def update_slo(
    slo_id: str,
    payload: UpdateSloRequest,
    user: Annotated[dict, Depends(current_user)],
    project_id: str,
) -> dict:
    ensure_project_access(project_id, user)
    updated = SloService().update(project_id, slo_id, payload.model_dump(exclude_none=True))
    if "error" in updated:
        raise HTTPException(status_code=404, detail=updated["error"])
    return updated


@router.delete("/{slo_id}")
def delete_slo(
    slo_id: str,
    user: Annotated[dict, Depends(current_user)],
    project_id: str,
) -> dict:
    ensure_project_access(project_id, user)
    deleted = SloService().delete(project_id, slo_id)
    if "error" in deleted:
        raise HTTPException(status_code=400, detail=deleted["error"])
    return deleted
