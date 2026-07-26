from dataclasses import dataclass
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def _load_backend_env() -> None:
    if load_dotenv is None:
        return
    backend_env = Path(__file__).resolve().parents[1] / ".env"
    if backend_env.is_file():
        load_dotenv(backend_env, override=False)


_load_backend_env()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _assistant_api_key() -> str:
    return (
        os.getenv("AGENTSRE_ASSISTANT_LLM_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GEMINI_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    )


def _judge_api_key() -> str:
    return (
        os.getenv("AGENTSRE_LLM_JUDGE_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GEMINI_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    )


@dataclass(frozen=True)
class Settings:
    app_name: str = "AgentSRE Backend API"
    app_version: str = "0.1.0"
    cors_origins: str = os.getenv("AGENTSRE_CORS_ORIGINS", "*")

    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = _int_env("POSTGRES_PORT", 5432)
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_database: str = os.getenv("POSTGRES_DATABASE", "sre_agent")
    postgres_maintenance_database: str = os.getenv("POSTGRES_MAINTENANCE_DATABASE", "postgres")
    ingestion_database: str = os.getenv("POSTGRES_INGESTION_DATABASE", os.getenv("POSTGRES_DATABASE", "sre_agent"))
    metrics_database: str = os.getenv("POSTGRES_METRICS_DATABASE", os.getenv("POSTGRES_DATABASE", "sre_agent"))

    ingestion_base_url: str = os.getenv("INGESTION_BASE_URL", "http://localhost:8000")
    governance_base_url: str = os.getenv("GOVERNANCE_BASE_URL", "http://localhost:8001")

    kafka_enabled: bool = os.getenv("KAFKA_ENABLED", "false").lower() == "true"
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_intelligence_topic: str = os.getenv("KAFKA_INTELLIGENCE_TOPIC", "intelligence.execution.trace")
    kafka_governance_topic: str = os.getenv("KAFKA_GOVERNANCE_TOPIC", "governance.execution.full")

    session_ttl_days: int = _int_env("AGENTSRE_SESSION_TTL_DAYS", 14)
    session_prefix: str = os.getenv("AGENTSRE_SESSION_PREFIX", "asre_sess")
    sdk_key_prefix: str = os.getenv("AGENTSRE_SDK_KEY_PREFIX", "asre_sk")

    metrics_worker_enabled: bool = _bool_env("AGENTSRE_METRICS_WORKER_ENABLED", True)
    metrics_worker_interval_seconds: int = _int_env("AGENTSRE_METRICS_WORKER_INTERVAL_SECONDS", 3)
    metrics_worker_batch_size: int = _int_env("AGENTSRE_METRICS_WORKER_BATCH_SIZE", 100)

    llm_judge_enabled: bool = _bool_env("AGENTSRE_LLM_JUDGE_ENABLED", bool(_judge_api_key()))
    llm_judge_api_key: str = _judge_api_key()
    llm_judge_api_url: str = os.getenv("AGENTSRE_LLM_JUDGE_API_URL", "https://generativelanguage.googleapis.com/v1beta/models")
    llm_judge_model: str = os.getenv("AGENTSRE_LLM_JUDGE_MODEL", "gemini-2.5-flash")
    llm_judge_timeout_seconds: int = _int_env("AGENTSRE_LLM_JUDGE_TIMEOUT_SECONDS", 20)
    baseline_min_samples: int = _int_env("AGENTSRE_BASELINE_MIN_SAMPLES", 5)
    anomaly_z_threshold: float = _float_env("AGENTSRE_ANOMALY_Z_THRESHOLD", 2.5)

    assistant_llm_api_key: str = _assistant_api_key()
    assistant_llm_enabled: bool = _bool_env("AGENTSRE_ASSISTANT_LLM_ENABLED", bool(_assistant_api_key()))
    assistant_llm_api_url: str = os.getenv("AGENTSRE_ASSISTANT_LLM_API_URL", "https://generativelanguage.googleapis.com/v1beta/models")
    assistant_llm_model: str = os.getenv("AGENTSRE_ASSISTANT_LLM_MODEL", "gemini-2.5-flash")
    assistant_llm_timeout_seconds: int = _int_env("AGENTSRE_ASSISTANT_LLM_TIMEOUT_SECONDS", 20)


settings = Settings()
