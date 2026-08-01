import json
from typing import Any

from psycopg.types.json import Jsonb

from backend.core.settings import settings
from backend.database.postgresql import PostgresStore


class ExecutionRepository:
    def __init__(self) -> None:
        self.store = PostgresStore(settings.ingestion_database)

    def save_execution(
        self,
        raw: dict[str, Any],
        governance: dict[str, Any],
        intelligence: dict[str, Any],
    ) -> None:
        execution = raw.get("execution") or {}
        metrics = governance.get("metrics") or {}
        self.store.execute(
            """
            INSERT INTO executions (
                execution_id,
                trace_id,
                project_id,
                service_name,
                environment,
                status,
                started_at,
                ended_at,
                duration_ms,
                llm_call_count,
                tool_call_count,
                raw_payload,
                governance_payload,
                intelligence_payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (execution_id) DO UPDATE SET
                trace_id = EXCLUDED.trace_id,
                project_id = EXCLUDED.project_id,
                service_name = EXCLUDED.service_name,
                environment = EXCLUDED.environment,
                status = EXCLUDED.status,
                started_at = EXCLUDED.started_at,
                ended_at = EXCLUDED.ended_at,
                duration_ms = EXCLUDED.duration_ms,
                llm_call_count = EXCLUDED.llm_call_count,
                tool_call_count = EXCLUDED.tool_call_count,
                raw_payload = EXCLUDED.raw_payload,
                governance_payload = EXCLUDED.governance_payload,
                intelligence_payload = EXCLUDED.intelligence_payload
            """,
            (
                execution.get("execution_id") or "N/A",
                execution.get("trace_id") or "N/A",
                execution.get("project_id"),
                execution.get("service_name"),
                execution.get("environment"),
                governance.get("execution", {}).get("status"),
                execution.get("execution_start"),
                execution.get("execution_end"),
                execution.get("total_duration_ms"),
                self._non_negative_count(metrics.get("llm_calls")),
                self._non_negative_count(metrics.get("tool_calls")),
                self._json(raw),
                self._json(governance),
                self._json(intelligence),
            ),
        )

    def save_published_event(
        self,
        event_id: str,
        execution_id: str,
        topic: str,
        message_key: str,
        payload: dict[str, Any],
        published_at: str,
    ) -> None:
        self.store.execute(
            """
            INSERT INTO published_events (
                event_id,
                execution_id,
                topic,
                message_key,
                payload,
                published_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id, topic) DO UPDATE SET
                payload = EXCLUDED.payload,
                message_key = EXCLUDED.message_key,
                published_at = EXCLUDED.published_at
            """,
            (event_id, execution_id, topic, message_key, self._json(payload), published_at),
        )

    def _json(self, value: dict[str, Any]) -> Jsonb:
        return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, default=str))

    @staticmethod
    def _non_negative_count(value: Any) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0