import pytest
from pydantic import ValidationError

from agentsre_sdk.schema.models import AgentSREPayload


def test_travel_planner_payload_validates_with_canonical_sections_only() -> None:
    payload = _base_payload(
        [
            {
                "trace_id": "9f3a5b2c8d7e4f109a1b2c3d4e5f6789",
                "span_id": "100",
                "parent_span_id": None,
                "span_name": "PlannerNode",
                "span_kind": "AGENT",
                "start_time": "2026-06-29T10:15:20.100Z",
                "end_time": "2026-06-29T10:15:20.300Z",
                "duration_ms": 200,
                "status": "SUCCESS",
                "error_type": None,
                "error_message": None,
                "trace_context": "00-9f3a5b2c8d7e4f109a1b2c3d4e5f6789-100-01",
                "baggage": {},
                "retry_count": 0,
                "iteration_count": 1,
                "agent": {
                    "agent_id": "agent_planner",
                    "agent_name": "PlannerNode",
                    "parent_agent": None,
                    "agent_role": "Planner",
                    "agent_type": "LangGraphNode",
                    "workflow_id": "wf_trip_planner",
                    "execution_id": "exec_20260629_001",
                    "session_id": "session_001",
                    "redaction_applied": True,
                    "redaction_field": ["name"],
                },
                "llm": None,
                "tool": None,
                "memory": None,
                "reasoning": {
                    "reasoning_step": 1,
                    "node_name": "PlannerNode",
                    "previous_node": None,
                    "next_node": "WeatherNode",
                    "decision_type": "Node Execution",
                },
                "http": None,
            },
            {
                "trace_id": "9f3a5b2c8d7e4f109a1b2c3d4e5f6789",
                "span_id": "101",
                "parent_span_id": "100",
                "span_name": "LangGraph Conditional Edge: PlannerNode",
                "span_kind": "REASONING",
                "start_time": "2026-06-29T10:15:20.300Z",
                "end_time": "2026-06-29T10:15:20.310Z",
                "duration_ms": 10,
                "status": "SUCCESS",
                "error_type": None,
                "error_message": None,
                "trace_context": "00-9f3a5b2c8d7e4f109a1b2c3d4e5f6789-101-01",
                "baggage": {},
                "retry_count": 0,
                "iteration_count": 1,
                "agent": None,
                "llm": None,
                "tool": None,
                "memory": None,
                "reasoning": {
                    "reasoning_step": 2,
                    "node_name": "PlannerNode",
                    "previous_node": "PlannerNode",
                    "next_node": "WeatherNode",
                    "decision_type": "Conditional Route",
                },
                "http": None,
            },
            {
                "trace_id": "9f3a5b2c8d7e4f109a1b2c3d4e5f6789",
                "span_id": "102",
                "parent_span_id": "100",
                "span_name": "WeatherAPI",
                "span_kind": "TOOL",
                "start_time": "2026-06-29T10:15:20.310Z",
                "end_time": "2026-06-29T10:15:20.490Z",
                "duration_ms": 180,
                "status": "SUCCESS",
                "error_type": None,
                "error_message": None,
                "trace_context": "00-9f3a5b2c8d7e4f109a1b2c3d4e5f6789-102-01",
                "baggage": {},
                "retry_count": 0,
                "iteration_count": 1,
                "agent": None,
                "llm": None,
                "tool": {
                    "tool_name": "WeatherAPI",
                    "tool_type": "REST API",
                    "tool_description": "Fetches current weather for a city.",
                    "tool_arguments": {"city": "Mysore"},
                    "tool_output": {"temperature": 27, "condition": "Cloudy"},
                    "tool_status": "SUCCESS",
                    "tool_error": None,
                    "tool_latency": 180,
                    "redaction_applied": False,
                    "redaction_field": [],
                },
                "memory": None,
                "reasoning": None,
                "http": None,
            },
        ]
    )

    validated = AgentSREPayload.model_validate(payload)

    assert validated.spans[0].agent is not None
    assert validated.spans[0].agent.redaction_applied is True
    assert validated.spans[0].agent.redaction_field == ["name"]
    assert validated.spans[0].reasoning is not None
    assert validated.spans[1].reasoning is not None
    assert validated.spans[2].tool is not None
    assert validated.spans[2].tool.tool_description == "Fetches current weather for a city."
    assert validated.spans[2].tool.redaction_applied is False


def test_non_canonical_graph_fields_are_rejected() -> None:
    payload = _base_payload([])
    span = {
        "trace_id": "9f3a5b2c8d7e4f109a1b2c3d4e5f6789",
        "span_id": "200",
        "parent_span_id": None,
        "span_name": "LangGraph Graph: travel_planner_graph",
        "span_kind": "AGENT",
        "span_type": "graph",
        "start_time": "2026-06-29T10:15:20.100Z",
        "end_time": "2026-06-29T10:15:20.900Z",
        "duration_ms": 800,
        "status": "SUCCESS",
        "error_type": None,
        "error_message": None,
        "trace_context": "00-9f3a5b2c8d7e4f109a1b2c3d4e5f6789-200-01",
        "baggage": {},
        "retry_count": 0,
        "iteration_count": 1,
        "agent": None,
        "llm": None,
        "tool": None,
        "memory": None,
        "reasoning": None,
        "http": None,
        "graph": {"graph_name": "travel_planner_graph"},
        "graph_node": None,
    }
    payload["spans"] = [span]

    with pytest.raises(ValidationError):
        AgentSREPayload.model_validate(payload)


def _base_payload(spans: list[dict]) -> dict:
    return {
        "execution": {
            "trace_id": "9f3a5b2c8d7e4f109a1b2c3d4e5f6789",
            "execution_id": "exec_20260629_001",
            "workflow_id": "wf_trip_planner",
            "session_id": "session_001",
            "user_id": "user_1001",
            "tenant_id": "company_xyz",
            "project_id": "travel-ai",
            "service_name": "trip-planner",
            "environment": "production",
            "execution_start": "2026-06-29T10:15:20.100Z",
            "execution_end": "2026-06-29T10:15:23.900Z",
            "total_duration_ms": 3800,
            "available_tools": [
                {
                    "tool_id": "tool_001_weather_node",
                    "tool_name": "WeatherAPI",
                    "tool_description": "Fetches current weather for a city.",
                    "tool_type": "REST API",
                    "tool_arguments": {"city": "Mysore"},
                }
            ],
            "available_agents": [
                {
                    "agent_id": "agent_planner",
                    "agent_name": "PlannerNode",
                    "agent_role": "Planner",
                    "agent_type": "LangGraphNode",
                }
            ],
        },
        "resource": {
            "sdk_version": "1.0.0",
            "plugin_version": "1.0.0",
            "framework": "LangGraph",
            "framework_version": "1.1.10",
            "language": "Python",
            "host_name": "planner-vm-01",
            "process_id": 4521,
            "os": "Ubuntu 24.04",
            "cpu_architecture": "x86_64",
            "runtime": "Python",
            "runtime_version": "3.12.4",
            "container_id": None,
            "kubernetes_pod": None,
            "cloud_provider": None,
        },
        "spans": spans,
    }


def test_tool_id_is_rejected_inside_span_tool_section() -> None:
    payload = _base_payload([])
    span = {
        "trace_id": "9f3a5b2c8d7e4f109a1b2c3d4e5f6789",
        "span_id": "300",
        "parent_span_id": None,
        "span_name": "WeatherAPI",
        "span_kind": "TOOL",
        "start_time": "2026-06-29T10:15:20.100Z",
        "end_time": "2026-06-29T10:15:20.300Z",
        "duration_ms": 200,
        "status": "SUCCESS",
        "error_type": None,
        "error_message": None,
        "trace_context": "00-9f3a5b2c8d7e4f109a1b2c3d4e5f6789-300-01",
        "baggage": {},
        "retry_count": 0,
        "iteration_count": 1,
        "agent": None,
        "llm": None,
        "tool": {
            "tool_id": "tool_not_allowed_here",
            "tool_name": "WeatherAPI",
            "tool_type": "REST API",
            "tool_description": "Fetches current weather for a city.",
            "tool_arguments": {"city": "Mysore"},
            "tool_output": {"temperature": 27},
            "tool_status": "SUCCESS",
            "tool_error": None,
            "tool_latency": 180,
        },
        "memory": None,
        "reasoning": None,
        "http": None,
    }
    payload["spans"] = [span]

    with pytest.raises(ValidationError):
        AgentSREPayload.model_validate(payload)


def test_redaction_metadata_is_rejected_outside_supported_sections() -> None:
    payload = _base_payload([])
    span = {
        "trace_id": "9f3a5b2c8d7e4f109a1b2c3d4e5f6789",
        "span_id": "400",
        "parent_span_id": None,
        "span_name": "LangGraph Conditional Edge: PlannerNode",
        "span_kind": "REASONING",
        "start_time": "2026-06-29T10:15:20.100Z",
        "end_time": "2026-06-29T10:15:20.300Z",
        "duration_ms": 200,
        "status": "SUCCESS",
        "error_type": None,
        "error_message": None,
        "trace_context": "00-9f3a5b2c8d7e4f109a1b2c3d4e5f6789-400-01",
        "baggage": {},
        "retry_count": 0,
        "iteration_count": 1,
        "agent": None,
        "llm": None,
        "tool": None,
        "memory": None,
        "reasoning": {
            "reasoning_step": 1,
            "node_name": "PlannerNode",
            "previous_node": None,
            "next_node": "WeatherNode",
            "decision_type": "Conditional Route",
            "redaction_applied": True,
            "redaction_field": ["email"],
        },
        "http": None,
    }
    payload["spans"] = [span]

    with pytest.raises(ValidationError):
        AgentSREPayload.model_validate(payload)
