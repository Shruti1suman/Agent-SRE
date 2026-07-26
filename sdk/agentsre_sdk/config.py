from __future__ import annotations

from dataclasses import dataclass, field

from agentsre_sdk.utils.id_generator import generate_session_id, generate_workflow_id


DEFAULT_BACKEND_URL = "http://localhost:8080/v1/executions"


@dataclass(frozen=True, slots=True)
class SDKConfig:
    tenant_id: str
    project_id: str
    service_name: str
    environment: str
    backend_url: str
    api_key: str
    user_id: str | None = None
    pii_redaction: bool = True
    sensitive_fields: list[str] = field(default_factory=list)
    instrument_langgraph: bool = True
    instrument_crewai: bool = True
    workflow_id: str = field(default_factory=generate_workflow_id)
    session_id: str = field(default_factory=generate_session_id)
    export_interval_seconds: float = 5.0
    max_queue_size: int = 2048
    batch_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        required = {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "service_name": self.service_name,
            "environment": self.environment,
            "backend_url": self.backend_url,
            "api_key": self.api_key,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"missing required SDK config values: {', '.join(missing)}")
        if self.export_interval_seconds <= 0:
            raise ValueError("export_interval_seconds must be greater than zero")
        if self.max_queue_size <= 0:
            raise ValueError("max_queue_size must be greater than zero")
        if self.batch_timeout_seconds <= 0:
            raise ValueError("batch_timeout_seconds must be greater than zero")

    @property
    def normalized_sensitive_fields(self) -> set[str]:
        return {field_name.lower() for field_name in self.sensitive_fields}
