from fastapi import HTTPException

from backend.app.repositories.project_repository import ProjectRepository


class ProjectService:
    def __init__(self) -> None:
        self.repository = ProjectRepository()

    def list_projects(self, user: dict) -> list[dict]:
        return self.repository.list_for_user(user["user_id"])

    def create_project(self, user: dict, project_name: str, description: str | None) -> dict:
        name = project_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Project name is required")
        return self.repository.create(user["user_id"], name, description)

    def regenerate_key(self, user: dict, project_id: str, key_name: str | None = None) -> dict:
        project = self.repository.regenerate_key(project_id, user["user_id"], key_name)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

