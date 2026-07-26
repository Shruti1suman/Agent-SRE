from typing import Any

from fastapi import HTTPException

from backend.app.repositories.execution_repository import ExecutionRepository
from backend.app.repositories.project_repository import ProjectRepository
from backend.app.services.event_publisher import EventPublisher
from backend.app.services.execution_transformer import build_downstream_events
from backend.core.settings import settings


class IngestionService:
    def __init__(self) -> None:
        self.executions = ExecutionRepository()
        self.projects = ProjectRepository()
        self.publisher = EventPublisher()

    def ingest(self, payload: dict[str, Any], authorization: str | None) -> dict:
        self.validate_sdk_payload(payload)
        self.apply_sdk_key_project(payload, authorization, required=True)
        governance, intelligence = build_downstream_events(payload)
        execution_id = governance["execution"]["execution_id"]

        try:
            self.executions.save_execution(payload, governance, intelligence)
            publish_result = self.publisher.publish(governance, intelligence)
            self.record_downstream_event(governance, publish_result["governance"])
            self.record_downstream_event(intelligence, publish_result["intelligence"])
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return {
            "accepted": True,
            "execution_id": execution_id,
            "trace_id": governance["execution"]["trace_id"],
            "project_id": governance["execution"]["project_id"],
            "stored": True,
            "published": publish_result,
        }

    def transform_only(self, payload: dict[str, Any], authorization: str | None = None) -> dict:
        self.validate_sdk_payload(payload)
        self.apply_sdk_key_project(payload, authorization, required=False)
        governance, intelligence = build_downstream_events(payload)
        return {"governance": governance, "intelligence": intelligence}

    def apply_sdk_key_project(self, payload: dict[str, Any], authorization: str | None, required: bool) -> None:
        if not authorization or not authorization.lower().startswith("bearer "):
            if required:
                raise HTTPException(status_code=401, detail="AgentSRE SDK key is required")
            return
        key = authorization.split(" ", 1)[1].strip()
        if not key.startswith(f"{settings.sdk_key_prefix}_"):
            if required:
                raise HTTPException(status_code=401, detail="Invalid AgentSRE SDK key format")
            return
        project = self.projects.get_by_sdk_key(key)
        if not project or "error" in project:
            raise HTTPException(status_code=401, detail="Invalid AgentSRE SDK key")
        execution = payload.setdefault("execution", {})
        execution["project_id"] = project["project_id"]
        execution["tenant_id"] = project["tenant_id"]

    def validate_sdk_payload(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload.get("execution"), dict):
            raise HTTPException(status_code=400, detail="Missing execution object")
        if not isinstance(payload.get("spans"), list):
            raise HTTPException(status_code=400, detail="Missing spans array")

    def record_downstream_event(self, event: dict[str, Any], publish_result: dict[str, Any]) -> None:
        self.executions.save_published_event(
            event_id=publish_result["event_id"],
            execution_id=publish_result["execution_id"],
            topic=publish_result["topic"],
            message_key=publish_result["key"],
            payload=event,
            published_at=publish_result["published_at"],
        )
