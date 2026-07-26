import httpx
from fastapi import APIRouter

from backend.core.settings import settings
from backend.database.postgresql import PostgresStore

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    postgres = PostgresStore(settings.metrics_database).fetch_one("SELECT 1 AS ok")
    return {
        "status": "ok" if postgres.get("ok") == 1 else "degraded",
        "postgresql": postgres,
        "ingestion": {
            "status": "ready",
            "endpoint": "/v1/executions",
            "kafka_enabled": settings.kafka_enabled,
            "kafka_bootstrap_servers": settings.kafka_bootstrap_servers,
            "topics": {
                "governance": settings.kafka_governance_topic,
                "intelligence": settings.kafka_intelligence_topic,
            },
        },
        "metrics_worker": {
            "enabled": settings.metrics_worker_enabled,
            "interval_seconds": settings.metrics_worker_interval_seconds,
            "batch_size": settings.metrics_worker_batch_size,
        },
        "governance": await _get_json(f"{settings.governance_base_url}/health"),
    }


async def _get_json(url: str) -> object:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        return {"error": str(exc)}

