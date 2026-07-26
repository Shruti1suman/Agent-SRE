from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.repositories.dashboard_repository import DashboardRepository


FAILED = {"ERROR", "FAILED", "FAILURE"}


class IncidentReportService:
    def __init__(self, repository: DashboardRepository | None = None) -> None:
        self.repository = repository or DashboardRepository()

    def build(self, incident_id: str) -> dict[str, Any]:
        incident = self.repository.incident_by_id(incident_id)
        if not incident or "error" in incident:
            return {"error": f"incident_id not found: {incident_id}"}

        trace_id = incident.get("trace_id")
        metric = self.repository.metric_detail(trace_id) or {}
        if "error" in metric:
            metric = {}
        trace = self.repository.trace_by_trace_id(trace_id) or {}
        replay = self.repository.replay_from_trace(trace) if trace and "error" not in trace else {}

        timeline = replay.get("timeline") or []
        tool_calls = replay.get("tool_calls") or []
        llm_calls = replay.get("llm_calls") or []
        raw_spans = replay.get("raw_spans") or []
        spans_by_id = {
            item.get("span_id"): item for item in raw_spans
            if isinstance(item, dict) and item.get("span_id")
        }
        failed_tools = [
            _report_tool(_enrich_tool(item, spans_by_id.get(item.get("span_id")) or {}))
            for item in tool_calls if _failed(item.get("status"))
        ]
        failed_events = [item for item in timeline if _failed(item.get("status_code"))]

        relevant_slo = _relevant_slo(
            metric.get("slo_results") or [],
            incident.get("metric_name"),
            incident.get("slo_id"),
        )
        relevant_events = _relevant_timeline(timeline, failed_events, incident)
        groundedness = metric.get("groundedness_judgements") or []

        return {
            "report": {
                "type": "AgentSRE Trace Incident Report",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "incident": incident,
            "run": {
                **(replay.get("trace") or {}),
                **(replay.get("execution") or {}),
                "trace_id": trace_id,
                "execution_id": trace.get("execution_id"),
                "project_id": trace.get("project_id"),
                "service_name": trace.get("service_name") or incident.get("agent_id"),
                "environment": trace.get("environment"),
                "status": trace.get("status") or metric.get("trace_status"),
                "started_at": trace.get("started_at"),
                "ended_at": trace.get("ended_at"),
                "duration_ms": trace.get("duration_ms") or metric.get("total_duration_ms"),
            },
            "metrics": _report_metrics(metric),
            "slo_evidence": relevant_slo,
            "diagnostics": {
                "failed_tools": failed_tools,
                "failed_events": [_report_event(item) for item in failed_events],
                "llm_calls": [_report_llm(item) for item in llm_calls],
                "groundedness_judgements": [_report_grounding(item) for item in groundedness],
                "loop": {
                    "detected": bool(metric.get("loop_detected")),
                    "reason": metric.get("loop_reason"),
                    "repetition_score": metric.get("repetition_score"),
                },
            },
            "timeline": [_report_event(item) for item in relevant_events],
        }


def _failed(value: Any) -> bool:
    return str(value or "").upper() in FAILED


def _enrich_tool(tool: dict[str, Any], span: dict[str, Any]) -> dict[str, Any]:
    return {
        **tool,
        "error_message": span.get("error_message") or span.get("status_message"),
        "parent_span_id": span.get("parent_span_id"),
    }


def _report_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": tool.get("step_id"),
        "span_id": tool.get("span_id"),
        "parent_span_id": tool.get("parent_span_id"),
        "tool_name": tool.get("tool_name"),
        "status": tool.get("status"),
        "duration_ms": tool.get("duration_ms"),
        "error_message": _compact_error(tool.get("error_message")),
    }


def _report_llm(call: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": call.get("step_id"),
        "span_id": call.get("span_id"),
        "provider": call.get("provider"),
        "model_name": call.get("model_name"),
        "finish_reason": call.get("finish_reason"),
        "prompt_tokens": call.get("prompt_tokens"),
        "completion_tokens": call.get("completion_tokens"),
        "total_tokens": call.get("total_tokens"),
        "duration_ms": call.get("duration_ms"),
    }


def _report_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence_number": event.get("sequence_number"),
        "step_id": event.get("step_id"),
        "span_id": event.get("span_id"),
        "parent_span_id": event.get("parent_span_id"),
        "name": event.get("name"),
        "canonical_type": event.get("canonical_type"),
        "started_at": event.get("started_at"),
        "ended_at": event.get("ended_at"),
        "duration_ms": event.get("duration_ms"),
        "status_code": event.get("status_code"),
        "status_message": _compact_error(event.get("status_message")),
        "retry_count": event.get("retry_count"),
        "model_name": event.get("model_name"),
        "tool_name": event.get("tool_name"),
        "summary": event.get("summary"),
    }


def _report_grounding(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("step_index", "step_id", "grounded", "score", "reason", "rationale", "explanation")
        if item.get(key) is not None
    }


def _compact_error(value: Any, max_length: int = 320) -> str | None:
    if not value:
        return None
    message = str(value).split("Traceback (most recent call last):", 1)[0]
    message = " ".join(message.replace("\\n", " ").split()).strip(" '\"")
    if len(message) > max_length:
        return f"{message[:max_length - 3].rstrip()}..."
    return message


def _report_metrics(metric: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "trace_status", "total_duration_ms", "total_prompt_tokens",
        "total_completion_tokens", "total_tokens", "total_cost_usd",
        "llm_latency_ms", "total_tool_latency_ms", "step_count",
        "tool_call_count", "tool_failure_count", "tool_failure_rate",
        "grounded_response_rate", "model_name", "slo_status",
    ]
    return {key: metric.get(key) for key in keys if metric.get(key) is not None}


def _relevant_slo(results: list[dict[str, Any]], metric_name: Any, slo_id: Any = None) -> dict[str, Any] | None:
    if slo_id:
        exact = next((result for result in results if result.get("slo_id") == slo_id), None)
        if exact:
            return exact
    target = str(metric_name or "").lower()
    for result in results:
        name = str(result.get("metric_name") or result.get("metric") or "").lower()
        if target and name == target:
            return result
    return None


def _relevant_timeline(
    timeline: list[dict[str, Any]],
    failed_events: list[dict[str, Any]],
    incident: dict[str, Any],
) -> list[dict[str, Any]]:
    if not timeline:
        return []

    category = str(incident.get("category") or "").lower()
    metric = str(incident.get("metric_name") or "").lower()
    if failed_events or "failure" in category or "tool" in category:
        relevant_ids = {
            value
            for event in failed_events
            for value in (event.get("span_id"), event.get("parent_span_id"))
            if value
        }
        selected = [
            event for event in timeline
            if event.get("span_id") in relevant_ids or event.get("parent_span_id") in relevant_ids
        ]
        if selected:
            return selected

    if "ground" in category:
        return [event for event in timeline if str(event.get("canonical_type") or "").upper() == "LLM"] or timeline
    if any(name in metric for name in ("duration", "latency")):
        return sorted(timeline, key=lambda item: float(item.get("duration_ms") or 0), reverse=True)[:10]
    return timeline
