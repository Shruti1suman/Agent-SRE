from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.dependencies import current_user
from backend.app.services.project_service import ProjectService
from backend.models.projects import CreateProjectRequest, GenerateProjectKeyRequest

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects(user: Annotated[dict, Depends(current_user)]) -> list[dict]:
    return ProjectService().list_projects(user)


@router.post("")
def create_project(payload: CreateProjectRequest, user: Annotated[dict, Depends(current_user)]) -> dict:
    return ProjectService().create_project(user, payload.project_name, payload.description)


@router.post("/{project_id}/keys")
def regenerate_project_key(
    project_id: str,
    payload: GenerateProjectKeyRequest,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    return ProjectService().regenerate_key(user, project_id, payload.key_name)

