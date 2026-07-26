from __future__ import annotations

import json
import re
from collections import Counter
from math import ceil
from typing import Any

from backend.app.repositories.metrics_repository import MetricsRepository
from backend.app.services.intelligence_judge import evaluate_groundedness
from backend.app.services.slo_service import evaluate_slos_for_metrics
from backend.core.settings import settings


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")

TOKEN_PRICES_PER_1M = {
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}
FALLBACK_PRICE_PER_1M = {"input": 0.15, "output": 0.60}
BASELINE_METRICS = (
    "total_duration_ms",
    "total_cost_usd",
    "step_count",
    "tool_failure_rate",
    "avg_step_latency_ms",
    "avg_tool_latency_ms",
    "tokens_per_step",
    "repetition_score",
    "grounded_response_rate",
    "total_tokens",
)
Z_SCORE_COLUMNS = {
    "total_duration_ms": "z_total_duration_ms",
    "total_cost_usd": "z_total_cost_usd",
    "step_count": "z_step_count",
    "tool_failure_rate": "z_tool_failure_rate",
    "repetition_score": "z_repetition_score",
    "grounded_response_rate": "z_grounded_response_rate",
    "tokens_per_step": "z_tokens_per_step",
    "avg_tool_latency_ms": "z_avg_tool_latency_ms",
}


class MetricsService:
    def __init__(self) -> None:
        self.repository = MetricsRepository()

    def process_pending(self, limit: int = 100) -> dict[str, Any]:
        events = self.repository.pending_intelligence_events(limit)
        processed = 0
        incidents = 0
        errors: list[dict[str, str]] = []

        for event in events:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                errors.append({"event_id": str(event.get("event_id")), "error": "Invalid JSON payload"})
                continue
            try:
                result = self.evaluate_and_persist(payload)
                processed += 1
                incidents += result["incidents_created"]
            except Exception as exc:
                errors.append({"event_id": str(event.get("event_id")), "error": str(exc)})

        return {
            "processed": processed,
            "incidents_created": incidents,
            "errors": errors,
            "remaining_hint": "Run again to process more events." if len(events) == limit else "No more pending events in this batch.",
        }

    def evaluate_and_persist(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(payload.get("agent_id") or payload.get("service_name") or "N/A")
        baseline_stats = self.repository.baseline_stats(agent_id)
        evaluation = self.evaluate(payload, baseline_stats)
        incidents = self.evaluate_incidents(payload, evaluation)
        evaluation["incidents_created"] = len(incidents)
        self.repository.upsert_trace_evaluation(evaluation)
        for incident in incidents:
            self.repository.insert_incident(incident)
        self.repository.upsert_baseline_stats(agent_id, self.updated_baseline_stats(evaluation, baseline_stats))
        return {"trace_id": evaluation["trace_id"], "incidents_created": len(incidents)}

    def evaluate(self, payload: dict[str, Any], baseline_stats: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        steps = payload.get("steps") or []
        step_latencies = [num(step.get("duration_ms")) for step in steps]
        tool_executions = [
            tool
            for step in steps
            for tool in step.get("tool_executions", [])
            if isinstance(tool, dict)
        ]
        tool_latencies = [num(tool.get("duration_ms")) for tool in tool_executions]
        tool_failures = [tool for tool in tool_executions if not bool(tool.get("success"))]
        total_prompt_tokens = sum(num(step.get("prompt_tokens")) for step in steps) or num(payload.get("total_prompt_tokens"))
        total_completion_tokens = sum(num(step.get("completion_tokens")) for step in steps) or num(payload.get("total_completion_tokens"))
        total_tokens = sum(num(step.get("total_tokens")) for step in steps) or num(payload.get("total_tokens"))
        step_count = len(steps) or int(num(payload.get("step_count")))
        tool_call_count = len(tool_executions) or int(num(payload.get("tool_call_count")))
        tool_failure_count = len(tool_failures) or int(num(payload.get("tool_failure_count")))
        loop_detected, loop_reason = self.detect_loop(steps, step_count)
        cost_usd, pricing_matched_on = estimate_token_cost(
            payload.get("model_name"),
            total_prompt_tokens,
            total_completion_tokens,
            total_tokens,
        )
        trace_failed = str(payload.get("status") or "").lower() in {"failed", "failure", "error"}
        groundedness = (
            {"grounded_response_rate": None, "groundedness_judgements": []}
            if trace_failed
            else evaluate_groundedness(steps, trace_id=payload.get("trace_id"))
        )
        agentic_metrics = build_agentic_metrics(
            steps,
            tool_executions,
            groundedness.get("groundedness_judgements") or [],
            loop_detected,
        )

        evaluation = {
            "trace_id": payload.get("trace_id") or "N/A",
            "agent_id": payload.get("agent_id") or payload.get("service_name") or "N/A",
            "project_id": payload.get("project_id") or "N/A",
            "trace_status": payload.get("status") or "unknown",
            "total_duration_ms": num(payload.get("duration_ms")),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "total_cost_usd": cost_usd,
            "cost_computation_skipped": cost_usd is None,
            "llm_latency_ms": sum(step_latencies),
            "total_tool_latency_ms": sum(tool_latencies),
            "step_count": step_count,
            "tool_call_count": tool_call_count,
            "tool_failure_count": tool_failure_count,
            "tool_failure_rate": safe_ratio(tool_failure_count, tool_call_count),
            "avg_step_latency_ms": safe_ratio(sum(step_latencies), len(step_latencies)),
            "p95_step_latency_ms": p95(step_latencies),
            "avg_tool_latency_ms": safe_ratio(sum(tool_latencies), len(tool_latencies)),
            "tokens_per_step": safe_ratio(total_tokens, step_count),
            "repetition_score": repetition_score(steps),
            "grounded_response_rate": groundedness.get("grounded_response_rate"),
            "groundedness_judgements": groundedness.get("groundedness_judgements") or [],
            "agentic_metrics": agentic_metrics,
            "baseline_eligible": baseline_is_eligible(baseline_stats or {}),
            "loop_detected": loop_detected,
            "loop_reason": loop_reason,
            "slo_breaches": [],
            "slo_results": [],
            "slo_status": "not_evaluated",
            "alerts_sent": 0,
            "model_name": payload.get("model_name"),
            "pricing_matched_on": pricing_matched_on,
        }
        evaluation.update(evaluate_slos_for_metrics(evaluation["project_id"], evaluation))
        evaluation.update(self.z_score_fields(evaluation, baseline_stats or {}))
        return evaluation

    def z_score_fields(self, evaluation: dict[str, Any], baseline_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
        z_scores: dict[str, float] = {}
        fields = {column: None for column in Z_SCORE_COLUMNS.values()}
        for metric_name in BASELINE_METRICS:
            value = metric_value(evaluation, metric_name)
            stat = baseline_stats.get(metric_name) or {}
            z_score = calculate_z_score(value, stat)
            if z_score is None:
                continue
            z_scores[metric_name] = z_score
            column_name = Z_SCORE_COLUMNS.get(metric_name)
            if column_name:
                fields[column_name] = z_score
        fields["z_scores"] = z_scores
        return fields

    def updated_baseline_stats(
        self,
        evaluation: dict[str, Any],
        baseline_stats: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        updated = {}
        for metric_name in BASELINE_METRICS:
            value = metric_value(evaluation, metric_name)
            if value is None:
                continue
            updated[metric_name] = update_welford_stat(baseline_stats.get(metric_name) or {}, value)
        return updated

    def evaluate_incidents(self, payload: dict[str, Any], evaluation: dict[str, Any]) -> list[dict[str, Any]]:
        incidents = []
        base = {
            "trace_id": evaluation["trace_id"],
            "agent_id": evaluation.get("agent_id"),
            "project_id": evaluation.get("project_id"),
            "z_score": None,
            "threshold_value": None,
            "triggered_by": "rule",
        }

        for breach in evaluation.get("slo_breaches") or []:
            rule_suffix = re.sub(r"[^A-Z0-9]+", "-", str(breach.get("slo_type") or breach.get("metric_name") or "BREACH").upper())
            incidents.append({
                **base,
                "rule_id": f"SLO-{rule_suffix}"[:20],
                "category": "slo_breach",
                "severity": breach.get("severity") or "warning",
                "slo_id": breach.get("slo_id"),
                "metric_name": breach.get("metric_name"),
                "observed_value": breach.get("observed_value"),
                "threshold_value": breach.get("threshold_value"),
                "triggered_by": "slo",
                "rca_text": f"{breach.get('label') or breach.get('metric_name')} breached its configured SLO.",
                "suggestion_text": "Inspect the trace replay, tune the agent behavior, or update the SLO target if this is expected load.",
            })

        slo_breached_metrics = {
            str(breach.get("metric_name"))
            for breach in evaluation.get("slo_breaches") or []
            if breach.get("metric_name")
        }

        if str(evaluation.get("trace_status")).lower() in {"failed", "failure", "error"}:
            incidents.append({
                **base,
                "rule_id": "RUN-FAILED",
                "category": "execution_failure",
                "severity": "critical",
                "metric_name": "trace_status",
                "observed_value": None,
                "rca_text": "Execution reported a failed status.",
                "suggestion_text": "Open trace replay and inspect the first failed span or tool call.",
            })

        if "tool_failure_rate" not in slo_breached_metrics and evaluation["tool_failure_count"] > 0:
            failed_tools = failed_tool_names(payload)
            incidents.append({
                **base,
                "rule_id": "TF-LOCAL",
                "category": "tool_failure_spike",
                "severity": "critical" if evaluation["tool_failure_rate"] >= 1 else "warning",
                "metric_name": "tool_failure_rate",
                "observed_value": evaluation["tool_failure_rate"],
                "rca_text": f"Tool failures detected: {', '.join(failed_tools) or 'unknown tool'}.",
                "suggestion_text": "Check tool credentials, timeout handling, dependency availability, and retry policy.",
            })

        if evaluation["loop_detected"]:
            incidents.append({
                **base,
                "rule_id": "LD-LOCAL",
                "category": "loop_divergence",
                "severity": "warning",
                "metric_name": "step_count",
                "observed_value": evaluation["step_count"],
                "rca_text": f"Loop signal detected: {evaluation['loop_reason']}.",
                "suggestion_text": "Add max-iteration guards and short-circuit repeated tool arguments.",
            })

        token_slo = next(
            (
                result for result in evaluation.get("slo_results") or []
                if result.get("metric_name") == "total_tokens"
            ),
            {},
        )
        token_threshold = num(token_slo.get("threshold_value")) or 12000
        if "total_tokens" not in slo_breached_metrics and evaluation["total_tokens"] >= token_threshold:
            incidents.append({
                **base,
                "rule_id": "CO-TOKENS",
                "category": "cost_overrun",
                "severity": "warning",
                "metric_name": "total_tokens",
                "observed_value": evaluation["total_tokens"],
                "threshold_value": token_threshold,
                "rca_text": "Token usage was high for a single execution.",
                "suggestion_text": "Reduce prompt context, summarize intermediate state, or cap completion length.",
            })

        grounded_rate = evaluation.get("grounded_response_rate")
        if grounded_rate is not None and grounded_rate <= 0.5:
            groundedness_judgements = evaluation.get("groundedness_judgements") or []
            ungrounded_step_text = ungrounded_step_label(groundedness_judgements)
            incidents.append({
                **base,
                "rule_id": "HS-JUDGE",
                "category": "hallucination_risk",
                "severity": "critical" if grounded_rate <= 0.25 else "warning",
                "metric_name": "grounded_response_rate",
                "observed_value": grounded_rate,
                "threshold_value": 0.5,
                "triggered_by": "judge",
                "rca_text": groundedness_rca_text(groundedness_judgements, ungrounded_step_text),
                "suggestion_text": "Require citations or tool evidence before final answers, and constrain the agent to say when evidence is missing.",
            })

        z_scores = evaluation.get("z_scores") or {}
        threshold = settings.anomaly_z_threshold
        z_incidents = [
            (
                "LAT-Z",
                "latency_anomaly",
                "total_duration_ms",
                "Trace latency is unusually high compared with this agent's baseline.",
                "Inspect slow spans, external API latency, and retry behavior for this run.",
            ),
            (
                "CO-Z",
                "cost_overrun",
                "total_cost_usd",
                "Execution cost is unusually high compared with this agent's baseline.",
                "Check prompt growth, context injection, and completion limits.",
            ),
            (
                "TOK-Z",
                "cost_overrun",
                "total_tokens",
                "Token usage is unusually high compared with this agent's baseline.",
                "Summarize state between steps and cap retrieved context.",
            ),
            (
                "TF-Z",
                "tool_failure_spike",
                "tool_failure_rate",
                "Tool failure rate is unusually high compared with this agent's baseline.",
                "Check the failing tool path, credentials, timeout policy, and dependency availability.",
            ),
            (
                "LD-Z",
                "loop_divergence",
                "step_count",
                "Step count is unusually high compared with this agent's baseline.",
                "Add max-iteration guards and inspect planner/tool termination criteria.",
            ),
        ]
        for rule_id, category, metric_name, rca_text, suggestion_text in z_incidents:
            if metric_name in slo_breached_metrics:
                continue
            z_score = z_scores.get(metric_name)
            if z_score is None or z_score < threshold:
                continue
            incidents.append({
                **base,
                "rule_id": rule_id,
                "category": category,
                "severity": "critical" if z_score >= threshold * 1.5 else "warning",
                "metric_name": metric_name,
                "observed_value": metric_value(evaluation, metric_name),
                "z_score": z_score,
                "threshold_value": threshold,
                "triggered_by": "zscore",
                "rca_text": rca_text,
                "suggestion_text": suggestion_text,
            })

        grounded_z = z_scores.get("grounded_response_rate")
        if grounded_z is not None and grounded_z <= -threshold:
            incidents.append({
                **base,
                "rule_id": "HS-Z",
                "category": "hallucination_risk",
                "severity": "critical" if grounded_z <= -(threshold * 1.5) else "warning",
                "metric_name": "grounded_response_rate",
                "observed_value": grounded_rate,
                "z_score": grounded_z,
                "threshold_value": -threshold,
                "triggered_by": "zscore",
                "rca_text": "Final answer included claims that were not supported by captured tool or context evidence.",
                "suggestion_text": "Add retrieval/tool evidence checks before final answer generation.",
            })

        length_steps = [
            step.get("step_index")
            for step in payload.get("steps", [])
            if str(step.get("finish_reason") or "").lower() == "length"
        ]
        if length_steps:
            incidents.append({
                **base,
                "rule_id": "FR-LENGTH",
                "category": "finish_reason_anomaly",
                "severity": "warning",
                "metric_name": "finish_reason_length_count",
                "observed_value": len(length_steps),
                "rca_text": f"Model output was truncated on steps {length_steps}.",
                "suggestion_text": "Increase max output tokens or ask for a shorter response.",
            })

        return dedupe_incidents(incidents)

    def detect_loop(self, steps: list[dict[str, Any]], step_count: int) -> tuple[bool, str | None]:
        if step_count > 10:
            return True, f"step_count_exceeded_local_threshold:{step_count}>10"
        if steps and all(str(step.get("finish_reason") or "").lower() == "tool_calls" for step in steps):
            return True, "all_steps_finished_with_tool_calls"

        repeated_tool_signature = repeated_tool_execution_signature(steps)
        if repeated_tool_signature:
            return True, f"repeated_tool_arguments:{repeated_tool_signature}"

        signatures = []
        for step in steps:
            tools = step.get("tool_executions") or []
            if not tools:
                signatures.append(None)
                continue
            first = tools[0]
            signatures.append((first.get("tool_name"), json.dumps(first.get("arguments"), sort_keys=True, default=str)))

        consecutive = 0
        previous = None
        for signature in signatures:
            if signature and signature == previous:
                consecutive += 1
            elif signature:
                consecutive = 1
                previous = signature
            else:
                consecutive = 0
                previous = None
            if consecutive >= 3:
                return True, f"same_tool_same_arguments_{consecutive}_consecutive_times:{signature[0]}"
        return False, None


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_agentic_metrics(
    steps: list[dict[str, Any]],
    tool_executions: list[dict[str, Any]],
    groundedness_judgements: list[dict[str, Any]],
    loop_detected: bool,
) -> dict[str, float]:
    model_steps = [step for step in steps if is_model_step(step)]
    model_errors = [step for step in model_steps if failed_status(step.get("status")) or step.get("error_message")]
    return {
        "model_call_count": float(len(model_steps)),
        "model_failure_count": float(len(model_errors)),
        "model_rate_limit_count": float(len([step for step in model_errors if contains_error_signal(step, ("rate limit", "ratelimit", "429", "too many requests"))])),
        "model_timeout_count": float(len([step for step in model_errors if contains_error_signal(step, ("timeout", "timed out"))])),
        "model_retry_count": float(sum(int(num(step.get("retry_count"))) for step in model_steps)),
        "truncated_response_count": float(len([step for step in model_steps if str(step.get("finish_reason") or "").lower() == "length"])),
        "fallback_activation_count": float(len([step for step in model_steps if bool(step.get("fallback_used") or step.get("model_fallback"))])),
        "tool_timeout_count": float(len([tool for tool in tool_executions if contains_error_signal(tool, ("timeout", "timed out"))])),
        "repeated_tool_call_count": float(repeated_tool_call_count(tool_executions)),
        "agent_step_count": float(len(steps)),
        "loop_detected_count": 1.0 if loop_detected else 0.0,
        "unsupported_claim_count": float(len([
            item for item in groundedness_judgements
            if item.get("grounded") is False
            or (item.get("score") is not None and num(item.get("score")) < 0.5)
        ])),
    }


def is_model_step(step: dict[str, Any]) -> bool:
    return any([
        num(step.get("total_tokens")) > 0,
        step.get("finish_reason") is not None,
        bool(step.get("response_text")),
        bool(step.get("model_name")),
    ])


def failed_status(value: Any) -> bool:
    return str(value or "").lower() in {"failed", "failure", "error"}


def contains_error_signal(item: dict[str, Any], signals: tuple[str, ...]) -> bool:
    text = " ".join(str(item.get(key) or "") for key in ("error_message", "status_message", "error", "result"))
    lowered = text.lower()
    return any(signal in lowered for signal in signals)


def repeated_tool_call_count(tool_executions: list[dict[str, Any]]) -> int:
    signatures = Counter(
        (
            str(tool.get("tool_name") or "unknown"),
            json.dumps(tool.get("arguments") or tool.get("tool_input"), sort_keys=True, default=str),
        )
        for tool in tool_executions
    )
    return sum(max(count - 1, 0) for count in signatures.values())


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def metric_value(evaluation: dict[str, Any], metric_name: str) -> float | None:
    value = evaluation.get(metric_name)
    if value is None:
        return None
    return num(value)


def dedupe_incidents(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_rank = {"slo": 4, "judge": 3, "rule": 3, "zscore": 2}
    severity_rank = {"critical": 5, "high": 4, "warning": 3, "medium": 3, "low": 2, "info": 1}

    def preferred(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        left_source = source_rank.get(str(left.get("triggered_by") or "rule").lower(), 1)
        right_source = source_rank.get(str(right.get("triggered_by") or "rule").lower(), 1)
        if left_source != right_source:
            return left if left_source > right_source else right

        left_severity = severity_rank.get(str(left.get("severity") or "").lower(), 0)
        right_severity = severity_rank.get(str(right.get("severity") or "").lower(), 0)
        if left_severity != right_severity:
            return left if left_severity > right_severity else right

        return left

    by_metric: dict[str, dict[str, Any]] = {}
    for incident in incidents:
        metric_name = incident.get("metric_name")
        key = ":".join([
            str(incident.get("trace_id") or ""),
            str(metric_name or incident.get("rule_id") or incident.get("category") or ""),
        ])
        existing = by_metric.get(key)
        by_metric[key] = preferred(existing, incident) if existing else incident

    selected = list(by_metric.values())
    traces_with_token_incidents = {
        str(incident.get("trace_id") or "")
        for incident in selected
        if incident.get("metric_name") == "total_tokens"
    }
    return [
        incident for incident in selected
        if not (
            incident.get("metric_name") == "total_cost_usd"
            and incident.get("triggered_by") == "zscore"
            and str(incident.get("trace_id") or "") in traces_with_token_incidents
        )
    ]


def baseline_is_eligible(baseline_stats: dict[str, dict[str, Any]]) -> bool:
    stat = baseline_stats.get("total_duration_ms") or {}
    return int(num(stat.get("sample_count"))) >= settings.baseline_min_samples


def calculate_z_score(value: float | None, stat: dict[str, Any]) -> float | None:
    if value is None:
        return None
    sample_count = int(num(stat.get("sample_count")))
    stddev = num(stat.get("stddev"))
    if sample_count < settings.baseline_min_samples or stddev <= 0:
        return None
    return round((value - num(stat.get("mean"))) / stddev, 4)


def update_welford_stat(stat: dict[str, Any], value: float) -> dict[str, Any]:
    sample_count = int(num(stat.get("sample_count"))) + 1
    previous_mean = num(stat.get("mean"))
    previous_m2 = num(stat.get("m2"))
    delta = value - previous_mean
    mean = previous_mean + (delta / sample_count)
    delta_after = value - mean
    m2 = previous_m2 + (delta * delta_after)
    variance = m2 / (sample_count - 1) if sample_count > 1 else 0.0
    return {
        "mean": mean,
        "m2": m2,
        "stddev": variance ** 0.5,
        "sample_count": sample_count,
    }


def p95(values: list[float]) -> float:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return 0.0
    return float(clean[max(ceil(0.95 * len(clean)) - 1, 0)])


def estimate_token_cost(
    model_name: str | None,
    prompt_tokens: float,
    completion_tokens: float,
    total_tokens: float,
) -> tuple[float | None, str | None]:
    if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0:
        return None, None

    pricing, matched_on = resolve_token_pricing(model_name)
    if prompt_tokens <= 0 and completion_tokens <= 0 and total_tokens > 0:
        prompt_tokens = total_tokens * 0.75
        completion_tokens = total_tokens * 0.25

    cost = (
        (prompt_tokens * pricing["input"]) +
        (completion_tokens * pricing["output"])
    ) / 1_000_000
    return round(cost, 8), matched_on


def resolve_token_pricing(model_name: str | None) -> tuple[dict[str, float], str]:
    normalized = str(model_name or "").strip().lower()
    for prefix, pricing in sorted(TOKEN_PRICES_PER_1M.items(), key=lambda item: len(item[0]), reverse=True):
        if normalized == prefix or normalized.startswith(f"{prefix}-"):
            return pricing, prefix
    return FALLBACK_PRICE_PER_1M, "fallback"


def repetition_score(steps: list[dict[str, Any]]) -> float:
    text = " ".join(str(step.get("response_text") or "") for step in steps)
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    if len(tokens) < 5:
        return 0.0
    grams = [tuple(tokens[index:index + 5]) for index in range(len(tokens) - 4)]
    return 1.0 - safe_ratio(len(set(grams)), len(grams))


def failed_tool_names(payload: dict[str, Any]) -> list[str]:
    names = []
    for step in payload.get("steps", []):
        for tool in step.get("tool_executions", []):
            if isinstance(tool, dict) and not bool(tool.get("success")):
                names.append(tool.get("tool_name") or "unknown")
    return sorted(Counter(names).keys())


def ungrounded_step_label(judgements: list[dict[str, Any]]) -> str:
    labels = []
    for item in judgements:
        if str(item.get("verdict")).lower() != "ungrounded":
            continue
        step_index = item.get("step_index")
        labels.append(f"step {step_index}" if step_index is not None else "an LLM step")
    if not labels:
        return "an LLM step"
    return ", ".join(labels)


def groundedness_rca_text(judgements: list[dict[str, Any]], step_text: str) -> str:
    for item in judgements:
        if str(item.get("verdict")).lower() != "ungrounded":
            continue
        if str(item.get("judge") or "").lower() == "llm":
            claims = item.get("ungrounded_claims") or []
            if claims:
                claim = re.sub(r"\s+", " ", str(claims[0])).strip()
                return f"Final answer included an unsupported claim: \"{claim}\"."
            reasoning = str(item.get("reasoning") or "").strip()
            if reasoning:
                return re.sub(r"\s+", " ", reasoning).strip()
    return f"Final answer included claims on {step_text} that were not supported by captured tool or context evidence."


def compact_text(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:max(limit - 3, 0)].rstrip()}..."


def repeated_tool_execution_signature(steps: list[dict[str, Any]]) -> str | None:
    counts: Counter[tuple[str, str]] = Counter()
    for step in steps:
        for tool in step.get("tool_executions", []) or []:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("tool_name") or "unknown")
            arguments = json.dumps(tool.get("arguments"), sort_keys=True, default=str)
            counts[(name, arguments)] += 1

    for (name, _arguments), count in counts.items():
        if count >= 3:
            return f"{name} repeated {count} times"
    return None
