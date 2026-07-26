from typing import Any

from backend.app.repositories.governance_repository import GovernanceRepository


class GovernanceService:
    def __init__(self) -> None:
        self.repository = GovernanceRepository()

    def overview(self, project_id: str | None = None, agent_id: str | None = None) -> dict[str, Any]:
        executions = self.repository.executions(project_id=project_id, agent_id=agent_id)
        if executions and "error" in executions[0]:
            return {"error": executions[0]["error"], "summary": self._empty_summary(), "executions": []}

        warnings = self.warnings_from(executions)
        privacy = self.privacy_from(executions)
        audit_actions = self.audit_actions_from(executions)
        replay_events = sum(len(row.get("timeline") or []) for row in executions)

        return {
            "summary": {
                "audit_events": len(audit_actions),
                "redactions": sum(row.get("maskedFields", 0) for row in privacy),
                "warnings": len(warnings),
                "replay_events": replay_events,
            },
            "executions": [self.execution_row(row) for row in executions],
            "warnings": warnings,
            "privacy": privacy,
            "audit_actions": audit_actions,
        }

    def executions(self, project_id: str | None = None, agent_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.repository.executions(project_id=project_id, agent_id=agent_id)
        if rows and "error" in rows[0]:
            return rows
        return [self.execution_row(row) for row in rows]

    def warnings(self, project_id: str | None = None, agent_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.repository.executions(project_id=project_id, agent_id=agent_id)
        if rows and "error" in rows[0]:
            return rows
        return self.warnings_from(rows)

    def privacy(self, project_id: str | None = None, agent_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.repository.executions(project_id=project_id, agent_id=agent_id)
        if rows and "error" in rows[0]:
            return rows
        return self.privacy_from(rows)

    def audit_actions(self, project_id: str | None = None, agent_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.repository.executions(project_id=project_id, agent_id=agent_id)
        if rows and "error" in rows[0]:
            return rows
        return self.audit_actions_from(rows)

    def execution_row(self, row: dict[str, Any]) -> dict[str, Any]:
        metrics = row.get("metrics") or {}
        privacy = row.get("privacy") or {}
        warnings = row.get("warnings") or []
        return {
            "execution_id": row.get("execution_id"),
            "trace_id": row.get("trace_id"),
            "project_id": row.get("project_id"),
            "agent_id": row.get("agent_id"),
            "service_name": row.get("service_name"),
            "environment": row.get("environment"),
            "status": row.get("canonical_status") or row.get("status"),
            "outcome": row.get("outcome"),
            "started_at": row.get("started_at"),
            "ended_at": row.get("ended_at"),
            "duration_ms": row.get("duration_ms"),
            "total_spans": metrics.get("total_spans") or len(row.get("timeline") or []),
            "llm_calls": metrics.get("llm_calls") or len(row.get("llm_calls") or []),
            "tool_calls": metrics.get("tool_calls") or len(row.get("tool_calls") or []),
            "redaction_applied": bool(privacy.get("redaction_applied")),
            "masked_fields_count": privacy.get("masked_fields_count") or 0,
            "warning_count": len(warnings),
            "created_at": row.get("created_at"),
        }

    def warnings_from(self, executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for execution in executions:
            for index, warning in enumerate(execution.get("warnings") or []):
                source = warning.get("source") or warning.get("warning_code") or "governance"
                rows.append({
                    "id": f"{execution.get('execution_id')}-warning-{index + 1}",
                    "execution_id": execution.get("execution_id"),
                    "trace_id": execution.get("trace_id"),
                    "project_id": execution.get("project_id"),
                    "agent_id": execution.get("agent_id"),
                    "severity": warning.get("severity") or warning.get("level") or "warning",
                    "message": warning.get("message") or warning.get("summary") or str(warning),
                    "source": source,
                    "details": warning.get("details") or {},
                    "created_at": execution.get("created_at"),
                })
        return rows

    def privacy_from(self, executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for execution in executions:
            privacy = execution.get("privacy") or {}
            redacted_fields = privacy.get("redacted_fields") or []
            redaction_types = privacy.get("redaction_types") or []
            masked_fields = privacy.get("masked_fields_count") or 0
            redaction_applied = bool(privacy.get("redaction_applied"))
            if not masked_fields:
                continue
            rows.append({
                "field": execution.get("execution_id"),
                "execution_id": execution.get("execution_id"),
                "trace_id": execution.get("trace_id"),
                "project_id": execution.get("project_id"),
                "agent_id": execution.get("agent_id"),
                "redactionApplied": redaction_applied,
                "types": ", ".join(redaction_types) if redaction_types else "none",
                "redactedFields": ", ".join(redacted_fields) if redacted_fields else "none",
                "policy": privacy.get("capture_policy") or "full",
                "maskedFields": masked_fields,
                "created_at": execution.get("created_at"),
            })
        return rows

    def audit_actions_from(self, executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for execution in executions:
            rows.append({
                "id": f"audit-{execution.get('execution_id')}",
                "actor_user_id": "system",
                "action": "execution.captured",
                "project_id": execution.get("project_id"),
                "agent_id": execution.get("agent_id"),
                "execution_id": execution.get("execution_id"),
                "trace_id": execution.get("trace_id"),
                "target": execution.get("service_name") or execution.get("agent_id"),
                "status": execution.get("canonical_status") or execution.get("status"),
                "metadata": {
                    "trace_id": execution.get("trace_id"),
                    "status": execution.get("canonical_status") or execution.get("status"),
                    "timeline_events": len(execution.get("timeline") or []),
                },
                "created_at": execution.get("created_at"),
            })
            for item in execution.get("timeline") or []:
                action = self._timeline_action(item)
                rows.append({
                    "id": f"audit-{execution.get('execution_id')}-{item.get('step_id') or item.get('sequence_number')}",
                    "actor_user_id": "system",
                    "action": action,
                    "project_id": execution.get("project_id"),
                    "agent_id": execution.get("agent_id"),
                    "execution_id": execution.get("execution_id"),
                    "trace_id": execution.get("trace_id"),
                    "target": item.get("name") or item.get("span_id"),
                    "status": item.get("status_code") or execution.get("canonical_status") or execution.get("status"),
                    "metadata": {
                        "span_id": item.get("span_id"),
                        "parent_span_id": item.get("parent_span_id"),
                        "duration_ms": item.get("duration_ms"),
                        "summary": item.get("summary"),
                        "model_name": item.get("model_name"),
                        "tool_name": item.get("tool_name"),
                    },
                    "created_at": item.get("ended_at") or item.get("started_at") or execution.get("created_at"),
                })
        return rows

    @staticmethod
    def _timeline_action(item: dict[str, Any]) -> str:
        canonical_type = str(item.get("canonical_type") or "").upper()
        if canonical_type == "LLM_CALL":
            return "llm_call.captured"
        if canonical_type == "TOOL_CALL":
            return "tool_call.captured"
        if canonical_type == "HTTP_CALL":
            return "http_call.captured"
        if canonical_type == "AGENT_STEP":
            return "agent_step.captured"
        return "span.captured"

    @staticmethod
    def _empty_summary() -> dict[str, int]:
        return {"audit_events": 0, "redactions": 0, "warnings": 0, "replay_events": 0}
