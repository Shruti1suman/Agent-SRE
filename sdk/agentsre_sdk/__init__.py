from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agentsre_sdk.config import DEFAULT_BACKEND_URL, SDKConfig
from agentsre_sdk.instrumentors import instrument_all
from agentsre_sdk.tracer import TracingSetup, configure_tracing

try:
    from dotenv import find_dotenv, load_dotenv
except ImportError:  # pragma: no cover - dependency is declared, this keeps source imports defensive.
    find_dotenv = None
    load_dotenv = None


__version__ = "1.0.0"


def _load_env_file() -> None:
    if find_dotenv is None or load_dotenv is None:
        return
    explicit_env_path = os.getenv("AGENTSRE_ENV_FILE")
    if explicit_env_path:
        load_dotenv(explicit_env_path, override=True)
        return

    env_path = find_dotenv(filename=".env", usecwd=True)
    if env_path:
        load_dotenv(env_path, override=False)

    examples_env_path = Path.cwd() / "examples" / ".env"
    if examples_env_path.is_file():
        load_dotenv(examples_env_path, override=True)

    sdk_env_path = Path(__file__).resolve().parents[1] / ".env"
    if sdk_env_path.is_file():
        load_dotenv(sdk_env_path, override=False)


_load_env_file()


@dataclass(slots=True)
class SDKState:
    config: SDKConfig
    tracing: TracingSetup
    instrumentors: list[dict[str, str]]


_STATE: SDKState | None = None


def init(
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    service_name: str | None = None,
    environment: str | None = None,
    backend_url: str | None = None,
    api_key: str | None = None,
    user_id: str | None = None,
    pii_redaction: bool = True,
    sensitive_fields: list[str] | None = None,
    instrument_langgraph: bool = True,
    instrument_crewai: bool = True,
    workflow_id: str | None = None,
    session_id: str | None = None,
    export_interval_seconds: float = 5.0,
    max_queue_size: int = 2048,
    batch_timeout_seconds: float = 30.0,
) -> SDKState:
    global _STATE
    if _STATE is not None:
        return _STATE

    config_kwargs = {
        "tenant_id": tenant_id or os.getenv("AGENTSRE_TENANT_ID"),
        "project_id": project_id or os.getenv("AGENTSRE_PROJECT_ID"),
        "service_name": service_name or os.getenv("AGENTSRE_SERVICE_NAME"),
        "environment": environment or os.getenv("AGENTSRE_ENVIRONMENT"),
        "backend_url": backend_url or os.getenv("AGENTSRE_BACKEND_URL") or DEFAULT_BACKEND_URL,
        "api_key": api_key or os.getenv("AGENTSRE_API_KEY"),
        "user_id": user_id or os.getenv("AGENTSRE_USER_ID"),
        "pii_redaction": pii_redaction,
        "sensitive_fields": sensitive_fields or [],
        "instrument_langgraph": instrument_langgraph,
        "instrument_crewai": instrument_crewai,
        "export_interval_seconds": export_interval_seconds,
        "max_queue_size": max_queue_size,
        "batch_timeout_seconds": batch_timeout_seconds,
    }
    if workflow_id is not None:
        config_kwargs["workflow_id"] = workflow_id
    if session_id is not None:
        config_kwargs["session_id"] = session_id

    config = SDKConfig(**config_kwargs)
    tracing = configure_tracing(config)
    instrumentor_results = instrument_all(
        tracing.tracer_provider,
        instrument_langgraph=config.instrument_langgraph,
        instrument_crewai=config.instrument_crewai,
    )
    _STATE = SDKState(config=config, tracing=tracing, instrumentors=instrumentor_results)
    return _STATE


def get_state() -> SDKState | None:
    return _STATE


def shutdown() -> None:
    global _STATE
    if _STATE is not None:
        _STATE.tracing.span_processor.shutdown()
        _STATE = None


__all__ = ["SDKConfig", "SDKState", "get_state", "init", "shutdown"]
