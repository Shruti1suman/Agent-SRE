from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from backend.core.settings import settings
from backend.database.postgresql import PostgresStore, json_value


DEFAULT_SLOS = [
    {
        "slo_type": "min_execution_success_rate",
        "metric_name": "execution_success_rate",
        "label": "Execution success rate",
        "operator": "lt",
        "threshold_value": 0.99,
        "unit": "ratio",
        "severity": "critical",
    },
    {
        "slo_type": "max_latency_ms",
        "metric_name": "total_duration_ms",
        "label": "Trace latency",
        "operator": "gt",
        "threshold_value": 1800.0,
        "unit": "ms",
        "severity": "warning",
    },
    {
        "slo_type": "max_tool_failure_rate",
        "metric_name": "tool_failure_rate",
        "label": "Tool failure rate",
        "operator": "gt",
        "threshold_value": 0.25,
        "unit": "ratio",
        "severity": "critical",
    },
    {
        "slo_type": "max_total_tokens",
        "metric_name": "total_tokens",
        "label": "Token budget",
        "operator": "gt",
        "threshold_value": 12000.0,
        "unit": "tokens",
        "severity": "warning",
    },
]

OBSOLETE_SLO_TYPES = ("max_total_cost", "max_step_count", "max_repetition_score")
OBSOLETE_SLO_METRICS = ("total_cost_usd", "step_count", "repetition_score")


class SloRepository:
    def __init__(self) -> None:
        self.store = PostgresStore(settings.metrics_database)

    def ensure_defaults(self, project_id: str) -> None:
        self.remove_obsolete_slos(project_id)
        for slo in DEFAULT_SLOS:
            self.store.execute(
                """
                INSERT INTO slo_configurations (
                    slo_id, project_id, metric_name, slo_type, label, operator,
                    threshold_value, unit, severity, is_active, configuration_kind
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, 'predefined')
                ON CONFLICT (project_id, slo_type) DO UPDATE SET
                    label = EXCLUDED.label,
                    unit = EXCLUDED.unit,
                    configuration_kind = 'predefined',
                    deleted_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    slo_id(project_id, slo["slo_type"]),
                    project_id,
                    slo["metric_name"],
                    slo["slo_type"],
                    slo["label"],
                    slo["operator"],
                    slo["threshold_value"],
                    slo["unit"],
                    slo["severity"],
                ),
            )

    def list_configs(self, project_id: str, active_only: bool = False) -> list[dict[str, Any]]:
        where = "WHERE project_id = %s AND deleted_at IS NULL"
        params: tuple[Any, ...] = (project_id,)
        if active_only:
            where += " AND is_active = TRUE"
        return self.store.fetch_all(
            f"""
            SELECT slo_id, project_id, metric_name, slo_type, label, operator,
                   threshold_value, unit, severity, is_active, configuration_kind,
                   created_at, updated_at
            FROM slo_configurations
            {where}
            ORDER BY (configuration_kind = 'custom') ASC,
                CASE slo_type
                    WHEN 'min_execution_success_rate' THEN 1
                    WHEN 'max_latency_ms' THEN 2
                    WHEN 'max_tool_failure_rate' THEN 3
                    WHEN 'max_total_tokens' THEN 4
                    ELSE 5
                END,
                created_at ASC
            """,
            params,
        )

    def remove_obsolete_slos(self, project_id: str) -> None:
        type_placeholders = ", ".join(["%s"] * len(OBSOLETE_SLO_TYPES))
        self.store.execute(
            f"""
            DELETE FROM slo_configurations
            WHERE project_id = %s
              AND slo_type IN ({type_placeholders})
            """,
            (project_id, *OBSOLETE_SLO_TYPES),
        )

    def create_config(self, project_id: str, payload: dict[str, Any], metric: dict[str, Any]) -> dict[str, Any]:
        slo_id_value = f"slo_{secrets.token_hex(12)}"
        slo_type = f"custom_{secrets.token_hex(10)}"
        self.store.execute(
            """
            INSERT INTO slo_configurations (
                slo_id, project_id, metric_name, slo_type, label, operator,
                threshold_value, unit, severity, is_active, configuration_kind
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'custom')
            """,
            (
                slo_id_value,
                project_id,
                payload["metric_name"],
                slo_type,
                payload["label"].strip(),
                payload["operator"],
                float(payload["threshold_value"]),
                metric["unit"],
                payload["severity"],
                bool(payload.get("is_active", True)),
            ),
        )
        return self.get_config(project_id, slo_id_value)

    def update_config(self, project_id: str, slo_id_value: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.store.fetch_one(
            """
            SELECT slo_id, project_id
            FROM slo_configurations
            WHERE project_id = %s AND slo_id = %s AND deleted_at IS NULL
            LIMIT 1
            """,
            (project_id, slo_id_value),
        )
        if not current or "error" in current:
            return {}

        assignments = []
        params: list[Any] = []
        if "threshold_value" in payload:
            assignments.append("threshold_value = %s")
            params.append(float(payload["threshold_value"]))
        if "is_active" in payload:
            assignments.append("is_active = %s")
            params.append(bool(payload["is_active"]))
        if "severity" in payload and payload["severity"] is not None:
            assignments.append("severity = %s")
            params.append(str(payload["severity"]))
        if "operator" in payload and payload["operator"] is not None:
            assignments.append("operator = %s")
            params.append(str(payload["operator"]))
        if "label" in payload and payload["label"] is not None:
            assignments.append("label = %s")
            params.append(str(payload["label"]).strip())

        if assignments:
            assignments.append("updated_at = CURRENT_TIMESTAMP")
            params.extend([project_id, slo_id_value])
            self.store.execute(
                f"""
                UPDATE slo_configurations
                SET {", ".join(assignments)}
                WHERE project_id = %s AND slo_id = %s
                """,
                tuple(params),
            )

        return self.store.fetch_one(
            """
            SELECT slo_id, project_id, metric_name, slo_type, label, operator,
                   threshold_value, unit, severity, is_active, configuration_kind,
                   created_at, updated_at
            FROM slo_configurations
            WHERE project_id = %s AND slo_id = %s AND deleted_at IS NULL
            LIMIT 1
            """,
            (project_id, slo_id_value),
        )

    def get_config(self, project_id: str, slo_id_value: str) -> dict[str, Any]:
        return self.store.fetch_one(
            """
            SELECT slo_id, project_id, metric_name, slo_type, label, operator,
                   threshold_value, unit, severity, is_active, configuration_kind,
                   created_at, updated_at
            FROM slo_configurations
            WHERE project_id = %s AND slo_id = %s AND deleted_at IS NULL
            LIMIT 1
            """,
            (project_id, slo_id_value),
        )

    def delete_custom_config(self, project_id: str, slo_id_value: str) -> bool:
        current = self.get_config(project_id, slo_id_value)
        if not current or "error" in current or current.get("configuration_kind") != "custom":
            return False
        self.store.execute(
            """
            UPDATE slo_configurations
            SET is_active = FALSE, deleted_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE project_id = %s AND slo_id = %s AND configuration_kind = 'custom'
            """,
            (project_id, slo_id_value),
        )
        return True

    def recent_evaluations(self, project_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        limit_sql = "LIMIT %s" if limit is not None else ""
        params = (project_id, limit) if limit is not None else (project_id,)
        rows = self.store.fetch_all(
            f"""
            SELECT trace_id, agent_id, project_id, trace_status, evaluated_at,
                   total_duration_ms, total_tokens, total_cost_usd, step_count,
                   tool_failure_rate, repetition_score, loop_detected,
                   slo_breaches, slo_results, slo_status
            FROM trace_evaluations
            WHERE project_id = %s
            ORDER BY evaluated_at DESC
            {limit_sql}
            """,
            params,
        )
        for row in rows:
            row["slo_breaches"] = json_value(row.get("slo_breaches")) or []
            row["slo_results"] = json_value(row.get("slo_results")) or []
        return rows


def slo_id(project_id: str, slo_type: str) -> str:
    digest = hashlib.sha1(f"{project_id}:{slo_type}".encode("utf-8")).hexdigest()[:18]
    return f"slo_{digest}"


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
