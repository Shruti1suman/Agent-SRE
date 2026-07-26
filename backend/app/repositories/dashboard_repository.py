from backend.core.settings import settings
from backend.app.services.metrics_service import estimate_token_cost, groundedness_rca_text, ungrounded_step_label
from backend.database.postgresql import PostgresStore, json_value


class DashboardRepository:
    def __init__(self) -> None:
        self.ingestion = PostgresStore(settings.ingestion_database)
        self.metrics_store = PostgresStore(settings.metrics_database)

    def overview(self, project_id: str | None = None) -> dict:
        where = "WHERE project_id = %s" if project_id else ""
        params = (project_id,) if project_id else ()
        traces = self.ingestion.fetch_one(
            f"""
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(CASE WHEN LOWER(status) IN ('success', 'completed', 'succeeded') THEN 1 ELSE 0 END), 0) AS successful,
                   COALESCE(SUM(CASE WHEN LOWER(status) IN ('failed', 'failure', 'error') THEN 1 ELSE 0 END), 0) AS failed,
                   COALESCE(SUM(COALESCE((governance_payload #>> '{metrics,llm_calls}')::BIGINT, 0)), 0) AS llm_calls,
                   COALESCE(SUM(COALESCE((governance_payload #>> '{metrics,tool_calls}')::BIGINT, 0)), 0) AS tool_calls
            FROM executions
            {where}
            """,
            params,
        )
        evaluations = self.metrics_store.fetch_one(f"SELECT COUNT(*) AS count FROM trace_evaluations {where}", params)
        incidents = self.metrics_store.fetch_one(f"SELECT COUNT(*) AS count FROM incidents {where}", params)
        return {
            "traces": traces.get("count", 0) if "error" not in traces else 0,
            "successful": traces.get("successful", 0) if "error" not in traces else 0,
            "failed": traces.get("failed", 0) if "error" not in traces else 0,
            "llm_calls": traces.get("llm_calls", 0) if "error" not in traces else 0,
            "tool_calls": traces.get("tool_calls", 0) if "error" not in traces else 0,
            "evaluations": evaluations.get("count", 0) if "error" not in evaluations else 0,
            "incidents": incidents.get("count", 0) if "error" not in incidents else 0,
            "errors": {
                "traces": traces.get("error"),
                "evaluations": evaluations.get("error"),
                "incidents": incidents.get("error"),
            },
        }

    def traces(self, project_id: str | None = None, limit: int | None = None) -> list[dict]:
        where = "WHERE project_id = %s" if project_id else ""
        limit_sql = "LIMIT %s" if limit is not None else ""
        id_params = ((project_id, limit) if project_id else (limit,)) if limit is not None else ((project_id,) if project_id else ())
        references = self.ingestion.fetch_all(
            f"""
            SELECT execution_id
            FROM executions
            {where}
            ORDER BY created_at DESC
            {limit_sql}
            """,
            id_params,
        )
        if references and "error" in references[0]:
            return references

        execution_ids = [row.get("execution_id") for row in references if row.get("execution_id")]
        rows_by_id: dict[str, dict] = {}
        for start in range(0, len(execution_ids), 100):
            batch = execution_ids[start:start + 100]
            placeholders = ", ".join(["%s"] * len(batch))
            batch_rows = self.ingestion.fetch_all(
                f"""
                SELECT execution_id, trace_id, project_id, service_name, environment,
                       status, started_at, ended_at, duration_ms, raw_payload,
                       governance_payload, intelligence_payload, created_at
                FROM executions
                WHERE execution_id IN ({placeholders})
                """,
                tuple(batch),
            )
            if batch_rows and "error" in batch_rows[0]:
                return batch_rows
            rows_by_id.update({str(row.get("execution_id")): row for row in batch_rows})

        rows = [rows_by_id[str(execution_id)] for execution_id in execution_ids if str(execution_id) in rows_by_id]
        for row in rows:
            self._attach_trace_counts(row)
        self.attach_project_names(rows)
        return rows

    def attach_project_names(self, rows: list[dict]) -> None:
        names = {}
        for row in self.metrics_store.fetch_all("SELECT project_id, project_name FROM projects"):
            if "error" not in row and row.get("project_id"):
                names[row["project_id"]] = row.get("project_name")
        for row in self.metrics_store.fetch_all("SELECT project_id, project_name FROM dashboard_projects"):
            if "error" not in row and row.get("project_id"):
                names[row["project_id"]] = row.get("project_name")
        for row in rows:
            project_id = row.get("project_id")
            row["project_name"] = names.get(project_id) or project_id or "Unassigned"

    def trace_by_execution(self, execution_id: str) -> dict:
        row = self.ingestion.fetch_one(
            """
            SELECT execution_id, trace_id, project_id, service_name, environment, status,
                   started_at, ended_at, duration_ms, raw_payload, governance_payload,
                   intelligence_payload, created_at
            FROM executions
            WHERE execution_id = %s
            LIMIT 1
            """,
            (execution_id,),
        )
        return self._decode_trace(row)

    def trace_by_trace_id(self, trace_id: str) -> dict:
        row = self.ingestion.fetch_one(
            """
            SELECT execution_id, trace_id, project_id, service_name, environment, status,
                   started_at, ended_at, duration_ms, raw_payload, governance_payload,
                   intelligence_payload, created_at
            FROM executions
            WHERE trace_id = %s
            LIMIT 1
            """,
            (trace_id,),
        )
        return self._decode_trace(row)

    def metrics(self, project_id: str | None = None, limit: int | None = None) -> list[dict]:
        where = "WHERE project_id = %s" if project_id else ""
        limit_sql = "LIMIT %s" if limit is not None else ""
        params = ((project_id, limit) if project_id else (limit,)) if limit is not None else ((project_id,) if project_id else ())
        rows = self.metrics_store.fetch_all(
            f"""
            SELECT trace_id, agent_id, project_id, trace_status, total_duration_ms,
                   total_prompt_tokens, total_completion_tokens, total_tokens,
                   total_cost_usd, cost_computation_skipped, llm_latency_ms,
                   total_tool_latency_ms, step_count, tool_call_count,
                   tool_failure_count, tool_failure_rate, avg_step_latency_ms,
                   p95_step_latency_ms, avg_tool_latency_ms, tokens_per_step,
                   repetition_score, grounded_response_rate, baseline_eligible,
                   loop_detected, loop_reason, slo_status, incidents_created,
                   alerts_sent, model_name, pricing_matched_on, evaluated_at
            FROM trace_evaluations
            {where}
            ORDER BY evaluated_at DESC
            {limit_sql}
            """,
            params,
        )
        if rows and "error" not in rows[0]:
            for row in rows:
                row["metrics_source"] = "trace_evaluations"
                self._attach_cost_estimate(row)
            return rows
        return self.fallback_metrics(project_id, rows[0].get("error") if rows else None, limit)

    def metric_detail(self, trace_id: str) -> dict:
        row = self.metrics_store.fetch_one(
            """
            SELECT trace_id, agent_id, project_id, trace_status, evaluated_at,
                   total_duration_ms, total_prompt_tokens, total_completion_tokens,
                   total_tokens, total_cost_usd, cost_computation_skipped,
                   llm_latency_ms, total_tool_latency_ms, step_count,
                   tool_call_count, tool_failure_count, tool_failure_rate,
                   avg_step_latency_ms, p95_step_latency_ms, avg_tool_latency_ms,
                   tokens_per_step, repetition_score, grounded_response_rate,
                   groundedness_judgements, agentic_metrics, baseline_eligible, loop_detected,
                   loop_reason, z_total_duration_ms, z_total_cost_usd,
                   z_step_count, z_tool_failure_rate, z_repetition_score,
                   z_grounded_response_rate, z_tokens_per_step,
                   z_avg_tool_latency_ms, slo_breaches, slo_results, slo_status,
                   incidents_created, alerts_sent, model_name, pricing_matched_on
            FROM trace_evaluations
            WHERE trace_id = %s
            LIMIT 1
            """,
            (trace_id,),
        )
        if row and "error" not in row:
            row["metrics_source"] = "trace_evaluations"
            row["groundedness_judgements"] = json_value(row.get("groundedness_judgements"))
            row["agentic_metrics"] = json_value(row.get("agentic_metrics")) or {}
            row["slo_breaches"] = json_value(row.get("slo_breaches")) or []
            row["slo_results"] = json_value(row.get("slo_results")) or []
            self._attach_cost_estimate(row)
            return row
        return self.fallback_metric_detail(trace_id) or row

    def incidents(self, project_id: str | None = None, limit: int | None = None) -> list[dict]:
        conditions = [
            "NOT (i.rule_id = 'HS-JUDGE' AND LOWER(COALESCE(te.trace_status, '')) IN ('failed', 'failure', 'error'))"
        ]
        if project_id:
            conditions.append("i.project_id = %s")
        where = f"WHERE {' AND '.join(conditions)}"
        limit_sql = "LIMIT %s" if limit is not None else ""
        params = ((project_id, limit) if project_id else (limit,)) if limit is not None else ((project_id,) if project_id else ())
        rows = self.metrics_store.fetch_all(
            f"""
            SELECT i.incident_id, i.trace_id, i.agent_id, i.project_id, i.rule_id, i.category,
                   i.severity, i.metric_name, i.observed_value, i.z_score, i.threshold_value,
                   i.triggered_by, i.slo_id,
                   i.created_at, i.rca_text, i.suggestion_text, te.groundedness_judgements
            FROM incidents i
            LEFT JOIN trace_evaluations te ON te.trace_id = i.trace_id
            {where}
            ORDER BY i.created_at DESC
            {limit_sql}
            """,
            params,
        )
        for row in rows:
            judgements = json_value(row.pop("groundedness_judgements", None)) or []
            if row.get("rule_id") == "HS-JUDGE" and judgements:
                row["rca_text"] = groundedness_rca_text(judgements, ungrounded_step_label(judgements))
        return rows

    def incident_by_id(self, incident_id: str) -> dict:
        return self.metrics_store.fetch_one(
            """
            SELECT incident_id, trace_id, agent_id, project_id, rule_id, category,
                   severity, metric_name, observed_value, z_score, threshold_value, slo_id,
                   triggered_by, created_at, rca_text, suggestion_text
            FROM incidents
            WHERE incident_id = %s
            LIMIT 1
            """,
            (incident_id,),
        )

    def incident_chat_messages(self, incident_id: str, user_id: str) -> list[dict]:
        return self.metrics_store.fetch_all(
            """
            SELECT message_id, incident_id, user_id, role, content, created_at
            FROM incident_chat_messages
            WHERE incident_id = %s
              AND user_id = %s
            ORDER BY message_id ASC
            """,
            (incident_id, user_id),
        )

    def append_incident_chat_message(self, incident_id: str, user_id: str, role: str, content: str) -> None:
        self.metrics_store.execute(
            """
            INSERT INTO incident_chat_messages (incident_id, user_id, role, content)
            VALUES (%s, %s, %s, %s)
            """,
            (incident_id, user_id, role, content),
        )

    def fallback_metrics(self, project_id: str | None, metrics_error: str | None, limit: int | None) -> list[dict]:
        where = "WHERE project_id = %s AND trace_id IS NOT NULL" if project_id else "WHERE trace_id IS NOT NULL"
        limit_sql = "LIMIT %s" if limit is not None else ""
        params = ((project_id, limit) if project_id else (limit,)) if limit is not None else ((project_id,) if project_id else ())
        traces = self.ingestion.fetch_all(
            f"""
            SELECT trace_id
            FROM executions
            {where}
            ORDER BY created_at DESC
            {limit_sql}
            """,
            params,
        )
        if traces and "error" in traces[0]:
            return traces
        rows = [self.fallback_metric_detail(row["trace_id"]) for row in traces if row.get("trace_id")]
        rows = [row for row in rows if row]
        if metrics_error:
            for row in rows:
                row["metrics_engine_error"] = metrics_error
        return rows

    def fallback_metric_detail(self, trace_id: str) -> dict:
        trace = self.trace_by_trace_id(trace_id)
        intelligence = trace.get("intelligence_payload") if trace else None
        if not isinstance(intelligence, dict):
            return {}
        steps = intelligence.get("steps") or []
        tool_latencies = [
            tool.get("duration_ms") or 0
            for step in steps
            for tool in step.get("tool_executions", [])
        ]
        step_latencies = [step.get("duration_ms") or 0 for step in steps]
        tool_count = intelligence.get("tool_call_count") or sum(
            len(step.get("tool_executions", [])) for step in steps
        )
        tool_failures = intelligence.get("tool_failure_count") or 0
        row = {
            "trace_id": intelligence.get("trace_id") or trace_id,
            "agent_id": intelligence.get("agent_id"),
            "project_id": intelligence.get("project_id"),
            "trace_status": intelligence.get("status"),
            "evaluated_at": None,
            "metrics_source": "ingestion_fallback",
            "total_duration_ms": intelligence.get("duration_ms"),
            "total_prompt_tokens": intelligence.get("total_prompt_tokens"),
            "total_completion_tokens": intelligence.get("total_completion_tokens"),
            "total_tokens": intelligence.get("total_tokens"),
            "total_cost_usd": None,
            "llm_latency_ms": sum(step_latencies),
            "total_tool_latency_ms": sum(tool_latencies),
            "step_count": intelligence.get("step_count") or len(steps),
            "tool_call_count": tool_count,
            "tool_failure_count": tool_failures,
            "tool_failure_rate": (tool_failures / tool_count) if tool_count else 0,
            "avg_step_latency_ms": (sum(step_latencies) / len(step_latencies)) if step_latencies else 0,
            "p95_step_latency_ms": sorted(step_latencies)[max(round(0.95 * len(step_latencies)) - 1, 0)]
            if step_latencies
            else 0,
            "avg_tool_latency_ms": (sum(tool_latencies) / len(tool_latencies)) if tool_latencies else 0,
            "tokens_per_step": ((intelligence.get("total_tokens") or 0) / len(steps)) if steps else 0,
            "slo_status": "not_evaluated",
            "incidents_created": 0,
            "alerts_sent": 0,
            "model_name": intelligence.get("model_name"),
        }
        self._attach_cost_estimate(row)
        return row

    def replay_from_trace(self, trace: dict) -> dict:
        governance = trace.get("governance_payload") or {}
        raw = trace.get("raw_payload") or {}
        intelligence = trace.get("intelligence_payload") or {}
        return {
            "source": "ingestion.governance_payload",
            "trace": {key: value for key, value in trace.items() if not key.endswith("_payload")},
            "execution": governance.get("execution") or raw.get("execution") or {},
            "timeline": governance.get("timeline") or [],
            "llm_calls": governance.get("llm_calls") or [],
            "tool_calls": governance.get("tool_calls") or [],
            "graph": governance.get("graph") or {"nodes": [], "edges": []},
            "privacy": [governance.get("privacy")] if governance.get("privacy") else [],
            "warnings": governance.get("warnings") or [],
            "intelligence_steps": intelligence.get("steps") or [],
            "raw_spans": raw.get("spans") or [],
        }

    def _decode_trace(self, row: dict) -> dict:
        if not row or "error" in row:
            return row
        row["raw_payload"] = json_value(row.get("raw_payload"))
        row["governance_payload"] = json_value(row.get("governance_payload"))
        row["intelligence_payload"] = json_value(row.get("intelligence_payload"))
        return row

    def _attach_trace_counts(self, row: dict) -> None:
        raw = json_value(row.pop("raw_payload", None)) or {}
        governance = json_value(row.pop("governance_payload", None)) or {}
        intelligence = json_value(row.pop("intelligence_payload", None)) or {}

        metrics = governance.get("metrics") if isinstance(governance, dict) else {}
        timeline = governance.get("timeline") if isinstance(governance, dict) else []
        llm_calls = governance.get("llm_calls") if isinstance(governance, dict) else []
        tool_calls = governance.get("tool_calls") if isinstance(governance, dict) else []
        raw_spans = raw.get("spans") if isinstance(raw, dict) else []
        steps = intelligence.get("steps") if isinstance(intelligence, dict) else []

        row["span_count"] = self._first_positive_count(
            metrics.get("total_spans") if isinstance(metrics, dict) else None,
            len(timeline) if isinstance(timeline, list) else None,
            len(raw_spans) if isinstance(raw_spans, list) else None,
            intelligence.get("step_count") if isinstance(intelligence, dict) else None,
            len(steps) if isinstance(steps, list) else None,
        )
        row["llm_count"] = self._first_positive_count(
            metrics.get("llm_calls") if isinstance(metrics, dict) else None,
            len(llm_calls) if isinstance(llm_calls, list) else None,
            self._count_raw_span_kind(raw_spans, "LLM"),
        )
        row["tool_count"] = self._first_positive_count(
            metrics.get("tool_calls") if isinstance(metrics, dict) else None,
            len(tool_calls) if isinstance(tool_calls, list) else None,
            self._count_raw_span_kind(raw_spans, "TOOL"),
        )

    @staticmethod
    def _first_positive_count(*values: object) -> int:
        for value in values:
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count > 0:
                return count
        return 0

    @staticmethod
    def _count_raw_span_kind(spans: object, kind: str) -> int:
        if not isinstance(spans, list):
            return 0
        return len([
            span for span in spans
            if isinstance(span, dict) and str(span.get("span_kind") or "").upper() == kind
        ])

    def _attach_cost_estimate(self, row: dict) -> None:
        existing_cost = self._num(row.get("total_cost_usd"))
        total_tokens = self._num(row.get("total_tokens"))
        if existing_cost > 0 or total_tokens <= 0:
            return
        cost, matched_on = estimate_token_cost(
            row.get("model_name"),
            self._num(row.get("total_prompt_tokens")),
            self._num(row.get("total_completion_tokens")),
            total_tokens,
        )
        if cost is None:
            return
        row["total_cost_usd"] = cost
        row["cost_computation_skipped"] = False
        row["pricing_matched_on"] = matched_on

    @staticmethod
    def _num(value: object) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

