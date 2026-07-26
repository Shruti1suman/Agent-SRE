from typing import Any

from backend.core.settings import settings
from backend.database.postgresql import PostgresStore, json_value


class GovernanceRepository:
    def __init__(self) -> None:
        self.ingestion = PostgresStore(settings.ingestion_database)

    def executions(self, project_id: str | None = None, agent_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if project_id:
            where.append("project_id = %s")
            params.append(project_id)
        if agent_id:
            where.append(
                "governance_payload #>> '{execution,agent_id}' = %s"
            )
            params.append(agent_id)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        limit_sql = "LIMIT %s" if limit is not None else ""
        query_params = (*params, limit) if limit is not None else tuple(params)
        rows = self.ingestion.fetch_all(
            f"""
            SELECT execution_id, trace_id, project_id, service_name, environment,
                   status, started_at, ended_at, duration_ms, governance_payload,
                   created_at
            FROM executions
            {where_sql}
            ORDER BY created_at DESC
            {limit_sql}
            """,
            query_params,
        )
        if rows and "error" in rows[0]:
            return rows
        return [self._decode(row) for row in rows]

    def _decode(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = json_value(row.pop("governance_payload", None)) or {}
        execution = payload.get("execution") or {}
        metrics = payload.get("metrics") or {}
        privacy = payload.get("privacy") or {}
        warnings = payload.get("warnings") or []
        timeline = payload.get("timeline") or []
        llm_calls = payload.get("llm_calls") or []
        tool_calls = payload.get("tool_calls") or []

        return {
            **row,
            "agent_id": execution.get("agent_id") or row.get("service_name") or "N/A",
            "outcome": execution.get("outcome"),
            "canonical_status": execution.get("status") or row.get("status"),
            "metrics": metrics if isinstance(metrics, dict) else {},
            "privacy": privacy if isinstance(privacy, dict) else {},
            "warnings": warnings if isinstance(warnings, list) else [],
            "timeline": timeline if isinstance(timeline, list) else [],
            "llm_calls": llm_calls if isinstance(llm_calls, list) else [],
            "tool_calls": tool_calls if isinstance(tool_calls, list) else [],
            "graph": payload.get("graph") or {"nodes": [], "edges": []},
        }
