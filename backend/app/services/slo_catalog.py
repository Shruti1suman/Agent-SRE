from __future__ import annotations

from typing import Any


METRIC_CATALOG: tuple[dict[str, Any], ...] = (
    {"name": "execution_success_rate", "label": "Execution success rate", "category": "Reliability", "unit": "ratio", "operators": ["lt", "lte"], "default_operator": "lt", "default_threshold": 0.99, "customizable": False},
    {"name": "total_duration_ms", "label": "Trace latency", "category": "Performance", "unit": "ms", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 1800},
    {"name": "llm_latency_ms", "label": "Model latency", "category": "Model reliability", "unit": "ms", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 5000},
    {"name": "model_rate_limit_count", "label": "Rate-limited model calls", "category": "Model reliability", "unit": "events", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 0},
    {"name": "model_failure_count", "label": "Failed model calls", "category": "Model reliability", "unit": "calls", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 0},
    {"name": "model_timeout_count", "label": "Model timeouts", "category": "Model reliability", "unit": "events", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 0},
    {"name": "model_retry_count", "label": "Model retries", "category": "Model reliability", "unit": "retries", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 2},
    {"name": "model_call_count", "label": "Model calls per run", "category": "Model reliability", "unit": "calls", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 10},
    {"name": "truncated_response_count", "label": "Truncated model responses", "category": "Response quality", "unit": "responses", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 0},
    {"name": "grounded_response_rate", "label": "Grounded response rate", "category": "Response quality", "unit": "ratio", "operators": ["lt", "lte"], "default_operator": "lt", "default_threshold": 0.95},
    {"name": "unsupported_claim_count", "label": "Unsupported response claims", "category": "Response quality", "unit": "claims", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 0},
    {"name": "tool_failure_count", "label": "Failed tool calls", "category": "Tool reliability", "unit": "calls", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 0},
    {"name": "tool_failure_rate", "label": "Tool failure rate", "category": "Tool reliability", "unit": "ratio", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 0.25},
    {"name": "tool_timeout_count", "label": "Tool timeouts", "category": "Tool reliability", "unit": "events", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 0},
    {"name": "repeated_tool_call_count", "label": "Repeated tool calls", "category": "Agent behaviour", "unit": "calls", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 1},
    {"name": "agent_step_count", "label": "Agent processing steps", "category": "Agent behaviour", "unit": "steps", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 10},
    {"name": "loop_detected_count", "label": "Detected loops", "category": "Agent behaviour", "unit": "events", "operators": ["gt"], "default_operator": "gt", "default_threshold": 0},
    {"name": "total_tokens", "label": "Token budget", "category": "Cost and quota", "unit": "tokens", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 12000},
    {"name": "total_cost_usd", "label": "Estimated run cost", "category": "Cost and quota", "unit": "USD", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 0.1},
    {"name": "step_count", "label": "Workflow step count", "category": "Agent behaviour", "unit": "steps", "operators": ["gt", "gte"], "default_operator": "gt", "default_threshold": 10},
)


METRICS_BY_NAME = {item["name"]: item for item in METRIC_CATALOG}


def metric_catalog() -> list[dict[str, Any]]:
    return [{"customizable": True, **item} for item in METRIC_CATALOG]


def metric_definition(name: str) -> dict[str, Any] | None:
    item = METRICS_BY_NAME.get(name)
    return dict(item) if item else None
