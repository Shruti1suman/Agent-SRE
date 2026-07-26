from typing import Any

from psycopg.types.json import Jsonb

from backend.core.settings import settings
from backend.database.postgresql import PostgresStore, json_value


class MetricsRepository:
    def __init__(self) -> None:
        self.store = PostgresStore(settings.metrics_database)
        self.ingestion = PostgresStore(settings.ingestion_database)

    def pending_intelligence_events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.ingestion.fetch_all(
            """
            SELECT pe.event_id, pe.execution_id, pe.topic, pe.payload, pe.published_at
            FROM published_events pe
            LEFT JOIN trace_evaluations te
              ON te.trace_id = pe.payload ->> 'trace_id'
            WHERE pe.topic = %s
              AND (
                te.trace_id IS NULL
                OR (
                  te.total_tokens > 0
                  AND (
                    te.total_cost_usd IS NULL
                    OR te.total_cost_usd <= 0
                    OR te.cost_computation_skipped = TRUE
                  )
                )
                OR te.slo_status IN ('not_evaluated', 'not_configured')
                OR te.slo_results IS NULL
                OR jsonb_array_length(te.slo_results) = 0
                OR (
                  te.grounded_response_rate IS NULL
                  AND te.groundedness_judgements IS NULL
                )
              )
            ORDER BY pe.created_at ASC
            LIMIT %s
            """,
            (settings.kafka_intelligence_topic, limit),
        )
        for row in rows:
            row["payload"] = json_value(row.get("payload"))
        return rows

    def upsert_trace_evaluation(self, evaluation: dict[str, Any]) -> None:
        self.store.execute(
            """
            INSERT INTO trace_evaluations (
                trace_id, agent_id, project_id, trace_status,
                total_duration_ms, total_prompt_tokens, total_completion_tokens,
                total_tokens, total_cost_usd, cost_computation_skipped,
                llm_latency_ms, total_tool_latency_ms, step_count,
                tool_call_count, tool_failure_count, tool_failure_rate,
                avg_step_latency_ms, p95_step_latency_ms, avg_tool_latency_ms,
                tokens_per_step, repetition_score, grounded_response_rate,
                groundedness_judgements, agentic_metrics, baseline_eligible, loop_detected, loop_reason,
                z_total_duration_ms, z_total_cost_usd, z_step_count,
                z_tool_failure_rate, z_repetition_score, z_grounded_response_rate,
                z_tokens_per_step, z_avg_tool_latency_ms,
                slo_breaches, slo_results, slo_status, incidents_created,
                alerts_sent, model_name, pricing_matched_on
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            ON CONFLICT (trace_id) DO UPDATE SET
                trace_status = EXCLUDED.trace_status,
                total_duration_ms = EXCLUDED.total_duration_ms,
                total_prompt_tokens = EXCLUDED.total_prompt_tokens,
                total_completion_tokens = EXCLUDED.total_completion_tokens,
                total_tokens = EXCLUDED.total_tokens,
                total_cost_usd = EXCLUDED.total_cost_usd,
                cost_computation_skipped = EXCLUDED.cost_computation_skipped,
                llm_latency_ms = EXCLUDED.llm_latency_ms,
                total_tool_latency_ms = EXCLUDED.total_tool_latency_ms,
                step_count = EXCLUDED.step_count,
                tool_call_count = EXCLUDED.tool_call_count,
                tool_failure_count = EXCLUDED.tool_failure_count,
                tool_failure_rate = EXCLUDED.tool_failure_rate,
                avg_step_latency_ms = EXCLUDED.avg_step_latency_ms,
                p95_step_latency_ms = EXCLUDED.p95_step_latency_ms,
                avg_tool_latency_ms = EXCLUDED.avg_tool_latency_ms,
                tokens_per_step = EXCLUDED.tokens_per_step,
                repetition_score = EXCLUDED.repetition_score,
                grounded_response_rate = EXCLUDED.grounded_response_rate,
                groundedness_judgements = EXCLUDED.groundedness_judgements,
                agentic_metrics = EXCLUDED.agentic_metrics,
                baseline_eligible = EXCLUDED.baseline_eligible,
                loop_detected = EXCLUDED.loop_detected,
                loop_reason = EXCLUDED.loop_reason,
                z_total_duration_ms = EXCLUDED.z_total_duration_ms,
                z_total_cost_usd = EXCLUDED.z_total_cost_usd,
                z_step_count = EXCLUDED.z_step_count,
                z_tool_failure_rate = EXCLUDED.z_tool_failure_rate,
                z_repetition_score = EXCLUDED.z_repetition_score,
                z_grounded_response_rate = EXCLUDED.z_grounded_response_rate,
                z_tokens_per_step = EXCLUDED.z_tokens_per_step,
                z_avg_tool_latency_ms = EXCLUDED.z_avg_tool_latency_ms,
                slo_breaches = EXCLUDED.slo_breaches,
                slo_results = EXCLUDED.slo_results,
                slo_status = EXCLUDED.slo_status,
                incidents_created = EXCLUDED.incidents_created,
                alerts_sent = EXCLUDED.alerts_sent,
                model_name = EXCLUDED.model_name,
                pricing_matched_on = EXCLUDED.pricing_matched_on
            """,
            (
                evaluation["trace_id"],
                evaluation.get("agent_id"),
                evaluation.get("project_id"),
                evaluation.get("trace_status"),
                evaluation.get("total_duration_ms"),
                evaluation.get("total_prompt_tokens"),
                evaluation.get("total_completion_tokens"),
                evaluation.get("total_tokens"),
                evaluation.get("total_cost_usd"),
                evaluation.get("cost_computation_skipped", True),
                evaluation.get("llm_latency_ms"),
                evaluation.get("total_tool_latency_ms"),
                evaluation.get("step_count"),
                evaluation.get("tool_call_count"),
                evaluation.get("tool_failure_count"),
                evaluation.get("tool_failure_rate"),
                evaluation.get("avg_step_latency_ms"),
                evaluation.get("p95_step_latency_ms"),
                evaluation.get("avg_tool_latency_ms"),
                evaluation.get("tokens_per_step"),
                evaluation.get("repetition_score"),
                evaluation.get("grounded_response_rate"),
                Jsonb(evaluation.get("groundedness_judgements") or []),
                Jsonb(evaluation.get("agentic_metrics") or {}),
                evaluation.get("baseline_eligible", False),
                evaluation.get("loop_detected", False),
                evaluation.get("loop_reason"),
                evaluation.get("z_total_duration_ms"),
                evaluation.get("z_total_cost_usd"),
                evaluation.get("z_step_count"),
                evaluation.get("z_tool_failure_rate"),
                evaluation.get("z_repetition_score"),
                evaluation.get("z_grounded_response_rate"),
                evaluation.get("z_tokens_per_step"),
                evaluation.get("z_avg_tool_latency_ms"),
                Jsonb(evaluation.get("slo_breaches") or []),
                Jsonb(evaluation.get("slo_results") or []),
                evaluation.get("slo_status", "not_evaluated"),
                evaluation.get("incidents_created", 0),
                evaluation.get("alerts_sent", 0),
                evaluation.get("model_name"),
                evaluation.get("pricing_matched_on"),
            ),
        )

    def baseline_stats(self, agent_id: str) -> dict[str, dict[str, Any]]:
        rows = self.store.fetch_all(
            """
            SELECT metric_name, mean, m2, stddev, sample_count
            FROM agent_baseline_stats
            WHERE agent_id = %s
            """,
            (agent_id,),
        )
        if rows and "error" in rows[0]:
            return {}
        return {str(row["metric_name"]): row for row in rows}

    def upsert_baseline_stats(self, agent_id: str, stats: dict[str, dict[str, Any]]) -> None:
        for metric_name, stat in stats.items():
            self.store.execute(
                """
                INSERT INTO agent_baseline_stats (
                    agent_id, metric_name, mean, m2, stddev, sample_count
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (agent_id, metric_name) DO UPDATE SET
                    mean = EXCLUDED.mean,
                    m2 = EXCLUDED.m2,
                    stddev = EXCLUDED.stddev,
                    sample_count = EXCLUDED.sample_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    agent_id,
                    metric_name,
                    stat.get("mean", 0),
                    stat.get("m2", 0),
                    stat.get("stddev", 0),
                    stat.get("sample_count", 0),
                ),
            )

    def insert_incident(self, incident: dict[str, Any]) -> None:
        self.store.execute(
            """
            INSERT INTO incidents (
                trace_id, agent_id, project_id, rule_id, category, severity,
                metric_name, observed_value, z_score, threshold_value,
                triggered_by, rca_text, suggestion_text, slo_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (trace_id, rule_id) DO UPDATE SET
                severity = EXCLUDED.severity,
                observed_value = EXCLUDED.observed_value,
                threshold_value = EXCLUDED.threshold_value,
                slo_id = EXCLUDED.slo_id,
                rca_text = EXCLUDED.rca_text,
                suggestion_text = EXCLUDED.suggestion_text
            """,
            (
                incident.get("trace_id"),
                incident.get("agent_id"),
                incident.get("project_id"),
                incident.get("rule_id"),
                incident.get("category"),
                incident.get("severity"),
                incident.get("metric_name"),
                incident.get("observed_value"),
                incident.get("z_score"),
                incident.get("threshold_value"),
                incident.get("triggered_by", "rule"),
                incident.get("rca_text"),
                incident.get("suggestion_text"),
                incident.get("slo_id"),
            ),
        )
