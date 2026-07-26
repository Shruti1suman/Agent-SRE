import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


N_A = "N/A"


def build_downstream_events(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    governance = build_governance_event(raw)
    intelligence = build_intelligence_event(raw)
    return governance, intelligence


def build_governance_event(raw: dict[str, Any]) -> dict[str, Any]:
    execution = raw.get("execution") or {}
    spans = raw.get("spans") or []
    root_agent = _root_agent(raw)
    llm_spans = _canonical_llm_spans(spans)
    tool_spans = [span for span in spans if span.get("span_kind") == "TOOL" and span.get("tool")]

    event_id = f"evt_gov_{execution.get('execution_id') or uuid4().hex}_{uuid4().hex[:8]}"
    published_at = _now_iso()
    timeline = [_timeline_item(index, span) for index, span in enumerate(_sort_spans(spans), start=1)]
    step_by_span = {item["span_id"]: item["step_id"] for item in timeline}

    return {
        "event_id": event_id,
        "event_type": "governance.execution.full",
        "published_at": published_at,
        "execution": {
            "execution_id": execution.get("execution_id") or N_A,
            "trace_id": execution.get("trace_id") or N_A,
            "project_id": execution.get("project_id") or N_A,
            "agent_id": root_agent.get("agent_id") or N_A,
            "environment": execution.get("environment") or N_A,
            "service_name": execution.get("service_name") or N_A,
            "status": _execution_status(execution, spans),
            "outcome": _execution_outcome(spans),
            "started_at": execution.get("execution_start") or N_A,
            "ended_at": execution.get("execution_end") or N_A,
            "duration_ms": execution.get("total_duration_ms"),
            "canonical_schema_version": "1.0",
        },
        "metrics": _governance_metrics(execution, spans, llm_spans, tool_spans),
        "timeline": timeline,
        "llm_calls": [
            _governance_llm_call(span, step_by_span, spans) for span in llm_spans
        ],
        "tool_calls": [
            _governance_tool_call(span, step_by_span) for span in tool_spans
        ],
        "graph": _graph(timeline, step_by_span),
        "privacy": _privacy(spans),
        "warnings": _warnings(raw, llm_spans),
    }


def build_intelligence_event(raw: dict[str, Any]) -> dict[str, Any]:
    execution = raw.get("execution") or {}
    spans = raw.get("spans") or []
    root_agent = _root_agent(raw)
    llm_spans = _canonical_llm_spans(spans)
    tool_spans = [span for span in spans if span.get("span_kind") == "TOOL" and span.get("tool")]
    primary_model = _first([_model_name(span, spans) for span in llm_spans]) or N_A

    steps = []
    sorted_llms = _sort_spans(llm_spans)
    tools_by_llm_span = _assign_tools_to_llms(tool_spans, sorted_llms, spans)
    for index, span in enumerate(sorted_llms):
        step_tools = [_tool_execution(tool) for tool in tools_by_llm_span.get(span.get("span_id"), [])]
        steps.append(_intelligence_step(index, span, execution, step_tools, spans))
    if not steps and tool_spans:
        steps.append(_tool_only_intelligence_step(0, execution, tool_spans))

    return {
        "trace_id": execution.get("trace_id") or N_A,
        "agent_id": root_agent.get("agent_id") or N_A,
        "project_id": execution.get("project_id") or N_A,
        "service_name": execution.get("service_name") or N_A,
        "status": _intelligence_status(execution, spans),
        "started_at": execution.get("execution_start") or N_A,
        "ended_at": execution.get("execution_end") or N_A,
        "duration_ms": execution.get("total_duration_ms"),
        "total_prompt_tokens": sum(_num(_get(span, "llm.input_tokens")) for span in llm_spans),
        "total_completion_tokens": sum(_num(_get(span, "llm.output_tokens")) for span in llm_spans),
        "total_tokens": sum(_num(_get(span, "llm.total_tokens")) for span in llm_spans),
        "step_count": len(steps),
        "tool_call_count": len(tool_spans),
        "tool_failure_count": len([span for span in tool_spans if _span_failed(span)]),
        "model_name": primary_model,
        "steps": steps,
    }


def _governance_metrics(
    execution: dict[str, Any],
    spans: list[dict[str, Any]],
    llm_spans: list[dict[str, Any]],
    tool_spans: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "total_spans": len(spans),
        "llm_calls": len(llm_spans),
        "tool_calls": len(tool_spans),
        "error_count": len([span for span in spans if _span_failed(span)]),
        "retry_count": sum(_num(span.get("retry_count")) for span in spans),
        "prompt_tokens": sum(_num(_get(span, "llm.input_tokens")) for span in llm_spans),
        "completion_tokens": sum(_num(_get(span, "llm.output_tokens")) for span in llm_spans),
        "total_tokens": sum(_num(_get(span, "llm.total_tokens")) for span in llm_spans),
        "execution_duration_ms": execution.get("total_duration_ms"),
        "llm_duration_ms": sum(_num(span.get("duration_ms")) for span in llm_spans),
        "tool_duration_ms": sum(_num(span.get("duration_ms")) for span in tool_spans),
    }


def _timeline_item(index: int, span: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence_number": index,
        "step_id": f"step_{index:03d}",
        "span_id": span.get("span_id") or N_A,
        "parent_span_id": span.get("parent_span_id"),
        "name": span.get("span_name") or N_A,
        "canonical_type": _canonical_type(span),
        "started_at": span.get("start_time") or N_A,
        "ended_at": span.get("end_time") or N_A,
        "duration_ms": span.get("duration_ms"),
        "status_code": span.get("status") or N_A,
        "status_message": span.get("error_message"),
        "retry_count": span.get("retry_count") or 0,
        "model_name": _get(span, "llm.model"),
        "tool_name": _get(span, "tool.tool_name"),
        "summary": _summary(span),
    }


def _governance_llm_call(
    span: dict[str, Any],
    step_by_span: dict[str, str],
    all_spans: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt_messages = _extract_messages(_get(span, "llm.prompt"))
    output_message = _extract_output_message(_get(span, "llm.response"))
    return {
        "step_id": step_by_span.get(span.get("span_id"), N_A),
        "span_id": span.get("span_id") or N_A,
        "provider": _get(span, "llm.provider") or N_A,
        "model_name": _model_name(span, all_spans) or N_A,
        "input_messages": prompt_messages,
        "output_messages": [output_message] if output_message else [],
        "finish_reason": _finish_reason(span),
        "model_name": _model_name(span, all_spans),
        "retry_count": span.get("retry_count") or 0,
        "prompt_tokens": _num(_get(span, "llm.input_tokens")),
        "completion_tokens": _num(_get(span, "llm.output_tokens")),
        "total_tokens": _num(_get(span, "llm.total_tokens")),
        "duration_ms": span.get("duration_ms"),
    }


def _governance_tool_call(
    span: dict[str, Any],
    step_by_span: dict[str, str],
) -> dict[str, Any]:
    tool = span.get("tool") or {}
    return {
        "step_id": step_by_span.get(span.get("span_id"), N_A),
        "span_id": span.get("span_id") or N_A,
        "tool_name": tool.get("tool_name") or N_A,
        "tool_input": _jsonish(tool.get("tool_arguments")),
        "tool_output": _jsonish(tool.get("tool_output")),
        "status": tool.get("tool_status") or span.get("status") or N_A,
        "duration_ms": tool.get("tool_latency") if tool.get("tool_latency") is not None else span.get("duration_ms"),
    }


def _intelligence_step(
    index: int,
    span: dict[str, Any],
    execution: dict[str, Any],
    tool_executions: list[dict[str, Any]],
    all_spans: list[dict[str, Any]],
) -> dict[str, Any]:
    started_at, ended_at, duration_ms = _step_window(span, tool_executions)
    return {
        "step_index": index,
        "status": _span_status(span),
        "error_message": span.get("error_message"),
        "started_at": started_at or execution.get("execution_start") or N_A,
        "ended_at": ended_at or execution.get("execution_end") or N_A,
        "duration_ms": duration_ms if duration_ms is not None else _num(span.get("duration_ms")),
        "prompt_tokens": _num(_get(span, "llm.input_tokens")),
        "completion_tokens": _num(_get(span, "llm.output_tokens")),
        "total_tokens": _num(_get(span, "llm.total_tokens")),
        "finish_reason": _finish_reason(span),
        "input_messages": _extract_messages(_get(span, "llm.prompt")),
        "response_text": _response_text(_get(span, "llm.response")),
        "available_tools": _available_tools(execution),
        "tool_executions": tool_executions,
    }


def _tool_only_intelligence_step(
    index: int,
    execution: dict[str, Any],
    tool_spans: list[dict[str, Any]],
) -> dict[str, Any]:
    step_tools = [_tool_execution(tool) for tool in _sort_spans(tool_spans)]
    started_at, ended_at, duration_ms = _tool_step_window(step_tools)
    return {
        "step_index": index,
        "status": "error" if any(not tool["success"] for tool in step_tools) else "completed",
        "error_message": _first([tool.get("error_message") for tool in step_tools]),
        "started_at": started_at or execution.get("execution_start") or N_A,
        "ended_at": ended_at or execution.get("execution_end") or N_A,
        "duration_ms": duration_ms if duration_ms is not None else 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "finish_reason": None,
        "model_name": None,
        "retry_count": 0,
        "input_messages": [],
        "response_text": None,
        "available_tools": _available_tools(execution),
        "tool_executions": step_tools,
    }


def _tool_step_window(
    tool_executions: list[dict[str, Any]],
) -> tuple[str | None, str | None, int | None]:
    starts = [
        tool.get("started_at") for tool in tool_executions if tool.get("started_at") not in (None, N_A)
    ]
    ends = [
        tool.get("ended_at") for tool in tool_executions if tool.get("ended_at") not in (None, N_A)
    ]
    started_at = min(starts) if starts else None
    ended_at = max(ends) if ends else None
    return started_at, ended_at, _duration_between(started_at, ended_at)


def _available_tools(execution: dict[str, Any]) -> list[dict[str, Any]]:
    tools = execution.get("available_tools") or []
    return [
        {
            "name": tool.get("tool_name") or N_A,
            "description": tool.get("tool_description") or N_A,
            "parameters": _infer_parameters(tool),
        }
        for tool in tools
    ]


def _infer_parameters(tool: dict[str, Any]) -> dict[str, Any] | str:
    description = _clean_tool_description(tool)
    argument = tool.get("tool_arguments")
    lowered = f"{tool.get('tool_name') or ''} {description}".lower()

    if argument is None and not description:
        return N_A

    if "city" in lowered or "weather" in lowered or "specified city" in lowered:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City used by the tool.",
                    "example": argument if argument is not None else N_A,
                }
            },
            "required": ["city"] if argument is not None else [],
            "x_inferred": True,
            "x_inferred_from": ["tool_description", "tool_arguments"],
        }

    if argument is not None:
        return {
            "type": "object",
            "properties": {
                "arguments": {
                    "type": _json_schema_type(argument),
                    "description": "Tool argument inferred from SDK telemetry.",
                    "example": argument,
                }
            },
            "required": ["arguments"],
            "x_inferred": True,
            "x_inferred_from": ["tool_arguments"],
        }

    return {
        "type": "object",
        "properties": {
            "arguments": {
                "type": "string",
                "description": description or "N/A",
            }
        },
        "required": [],
        "x_inferred": True,
        "x_inferred_from": ["tool_description"],
    }


def _clean_tool_description(tool: dict[str, Any]) -> str:
    description = tool.get("tool_description") or ""
    if description and not _is_generic_python_function_doc(description):
        return description

    tool_name = tool.get("tool_name") or "tool"
    tool_type = tool.get("tool_type") or "Tool"
    readable_name = tool_name.replace("_", " ")
    return f"{tool_type} tool for {readable_name}."


def _is_generic_python_function_doc(description: str) -> bool:
    return (
        "Create a function object." in description
        and "code object" in description
        and "globals dictionary" in description
    )


def _step_window(
    llm_span: dict[str, Any],
    tool_executions: list[dict[str, Any]],
) -> tuple[str | None, str | None, int | None]:
    starts = [llm_span.get("start_time")] + [
        tool.get("started_at") for tool in tool_executions if tool.get("started_at") not in (None, N_A)
    ]
    ends = [llm_span.get("end_time")] + [
        tool.get("ended_at") for tool in tool_executions if tool.get("ended_at") not in (None, N_A)
    ]
    starts = [value for value in starts if value]
    ends = [value for value in ends if value]

    started_at = min(starts) if starts else None
    ended_at = max(ends) if ends else None
    duration_ms = _duration_between(started_at, ended_at)
    return started_at, ended_at, duration_ms


def _duration_between(started_at: str | None, ended_at: str | None) -> int | None:
    if not started_at or not ended_at:
        return None
    start = _parse_iso(started_at)
    end = _parse_iso(ended_at)
    if not start or not end:
        return None
    return int(round((end - start).total_seconds() * 1000))


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _assign_tools_to_llms(
    tool_spans: list[dict[str, Any]],
    llm_spans: list[dict[str, Any]],
    all_spans: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    assignments = {span.get("span_id"): [] for span in llm_spans}
    if not llm_spans:
        return assignments

    span_by_id = {span.get("span_id"): span for span in all_spans if span.get("span_id")}
    assigned_tool_ids = set()

    # If a tool span wraps an LLM span, it belongs to that LLM step.
    for llm_span in llm_spans:
        llm_ancestors = _ancestor_ids(llm_span, span_by_id)
        for tool_span in tool_spans:
            tool_id = tool_span.get("span_id")
            if tool_id in llm_ancestors and tool_id not in assigned_tool_ids:
                assignments[llm_span.get("span_id")].append(tool_span)
                assigned_tool_ids.add(tool_id)

    # Standalone tools are assigned to the most recent LLM before they start.
    for tool_span in _sort_spans(tool_spans):
        tool_id = tool_span.get("span_id")
        if tool_id in assigned_tool_ids:
            continue
        target = _nearest_previous_llm(tool_span, llm_spans)
        assignments[target.get("span_id")].append(tool_span)
        assigned_tool_ids.add(tool_id)

    return {
        llm_id: _sort_spans(spans)
        for llm_id, spans in assignments.items()
    }


def _tool_execution(span: dict[str, Any]) -> dict[str, Any]:
    tool = span.get("tool") or {}
    return {
        "tool_name": tool.get("tool_name") or N_A,
        "arguments": tool.get("tool_arguments"),
        "result": _jsonish(tool.get("tool_output")),
        "duration_ms": tool.get("tool_latency") if tool.get("tool_latency") is not None else span.get("duration_ms"),
        "started_at": span.get("start_time") or N_A,
        "ended_at": span.get("end_time") or N_A,
        "success": (tool.get("tool_status") or span.get("status")) == "SUCCESS",
        "error_message": tool.get("tool_error") or span.get("error_message"),
    }


def _ancestor_ids(span: dict[str, Any], span_by_id: dict[str, dict[str, Any]]) -> set[str]:
    ancestors = set()
    parent_id = span.get("parent_span_id")
    while parent_id:
        ancestors.add(parent_id)
        parent = span_by_id.get(parent_id)
        parent_id = parent.get("parent_span_id") if parent else None
    return ancestors


def _nearest_previous_llm(tool_span: dict[str, Any], llm_spans: list[dict[str, Any]]) -> dict[str, Any]:
    tool_start = tool_span.get("start_time") or ""
    previous = [span for span in llm_spans if (span.get("start_time") or "") <= tool_start]
    if previous:
        return previous[-1]
    return llm_spans[0]


def _graph(timeline: list[dict[str, Any]], step_by_span: dict[str, str]) -> dict[str, Any]:
    nodes = [
        {
            "step_id": item["step_id"],
            "span_id": item["span_id"],
            "name": item["name"],
            "canonical_type": item["canonical_type"],
        }
        for item in timeline
    ]
    edges = []
    for item in timeline:
        parent_span_id = item.get("parent_span_id")
        if parent_span_id and parent_span_id in step_by_span:
            edges.append(
                {
                    "parent_step_id": step_by_span[parent_span_id],
                    "child_step_id": item["step_id"],
                    "parent_span_id": parent_span_id,
                    "child_span_id": item["span_id"],
                }
            )
    return {"nodes": nodes, "edges": edges}


def _privacy(spans: list[dict[str, Any]]) -> dict[str, Any]:
    redacted_fields = []
    redaction_applied = False
    for span in spans:
        for section_name in ("agent", "llm", "tool"):
            section = span.get(section_name) or {}
            redacted_fields.extend(section.get("redaction_field") or [])
            redaction_applied = redaction_applied or bool(section.get("redaction_applied"))

    unique_fields = sorted(set(redacted_fields))
    return {
        "redaction_applied": redaction_applied,
        "redacted_fields": unique_fields,
        "redaction_types": ["PII"] if unique_fields else [],
        "capture_policy": "full",
        "masked_fields_count": len(unique_fields),
    }


def _warnings(raw: dict[str, Any], llm_spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    if not llm_spans:
        warnings.append(
            {
                "warning_code": "NO_CANONICAL_LLM_SPANS",
                "message": "No canonical ChatCompletion LLM spans found.",
                "details": {},
            }
        )
    if not _root_agent(raw):
        warnings.append(
            {
                "warning_code": "NO_ROOT_AGENT_METADATA",
                "message": "No root agent metadata found; agent_id defaulted to N/A.",
                "details": {},
            }
        )
    return warnings


def _canonical_llm_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chat_completion = [
        span for span in spans if span.get("span_kind") == "LLM" and span.get("span_name") == "ChatCompletion"
    ]
    return _sort_spans(chat_completion or [span for span in spans if span.get("span_kind") == "LLM"])


def _root_agent(raw: dict[str, Any]) -> dict[str, Any]:
    spans = raw.get("spans") or []
    root_span = next(
        (span for span in spans if span.get("span_kind") == "AGENT" and not span.get("parent_span_id")),
        None,
    )
    if root_span and root_span.get("agent"):
        return root_span["agent"]

    agents = (raw.get("execution") or {}).get("available_agents") or []
    return agents[0] if agents else {}


def _extract_messages(raw_prompt: Any) -> list[dict[str, Any]]:
    parsed = _loads(raw_prompt)
    messages = parsed.get("messages") if isinstance(parsed, dict) else None
    if not messages:
        return []

    flat_messages = _flatten_messages(messages)
    return [_message_from_any(message) for message in flat_messages]


def _message_from_any(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {"role": N_A, "content": str(message), "tool_call_id": None, "tool_calls": None}

    kwargs = message.get("kwargs") if isinstance(message.get("kwargs"), dict) else {}
    role = message.get("role") or kwargs.get("type") or message.get("type") or N_A
    if role == "human":
        role = "user"
    if role == "ai":
        role = "assistant"

    return {
        "role": role,
        "content": message.get("content") if "content" in message else kwargs.get("content"),
        "tool_call_id": message.get("tool_call_id") or kwargs.get("tool_call_id"),
        "tool_calls": message.get("tool_calls") if "tool_calls" in message else kwargs.get("tool_calls"),
    }


def _flatten_messages(messages: Any) -> list[Any]:
    if not isinstance(messages, list):
        return []
    result = []
    for item in messages:
        if isinstance(item, list):
            result.extend(_flatten_messages(item))
        else:
            result.append(item)
    return result


def _extract_output_message(raw_response: Any) -> dict[str, Any] | None:
    text = _response_text(raw_response)
    if text is None:
        return None
    return {"role": "assistant", "content": text, "tool_calls": []}


def _response_text(raw_response: Any) -> str | None:
    parsed = _loads(raw_response)
    if not isinstance(parsed, dict):
        return str(raw_response) if raw_response is not None else None

    choices = parsed.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        if isinstance(message, dict):
            return message.get("content")

    generations = parsed.get("generations")
    if isinstance(generations, list) and generations and isinstance(generations[0], list):
        first = generations[0][0] if generations[0] else {}
        if isinstance(first, dict):
            return first.get("text")

    return _response_text_regex_fallback(raw_response)


def _response_text_regex_fallback(raw_response: Any) -> str | None:
    if not isinstance(raw_response, str):
        return None

    patterns = [
        r'"message"\s*:\s*\{.*?"content"\s*:\s*"(?P<content>(?:\\.|[^"\\])*)"',
        r'"text"\s*:\s*"(?P<content>(?:\\.|[^"\\])*)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_response, flags=re.DOTALL)
        if not match:
            continue
        content = match.group("content")
        try:
            return json.loads(f'"{content}"')
        except json.JSONDecodeError:
            return content.replace('\\"', '"').replace("\\n", "\n")
    return None


def _finish_reason(span: dict[str, Any]) -> str | None:
    direct = _get(span, "llm.finish_reason")
    if direct is not None:
        return direct
    parsed = _loads(_get(span, "llm.response"))
    choices = parsed.get("choices") if isinstance(parsed, dict) else None
    if isinstance(choices, list) and choices:
        return choices[0].get("finish_reason")
    generations = parsed.get("generations") if isinstance(parsed, dict) else None
    if isinstance(generations, list) and generations and isinstance(generations[0], list):
        info = generations[0][0].get("generation_info") if generations[0] else {}
        if isinstance(info, dict):
            return info.get("finish_reason")
    return None


def _span_status(span: dict[str, Any]) -> str:
    status = span.get("status")
    if status == "SUCCESS":
        return "completed"
    if status == "ERROR":
        return "error"
    if status:
        return str(status).lower()
    return N_A


def _model_name(span: dict[str, Any], all_spans: list[dict[str, Any]]) -> str | None:
    direct = _get(span, "llm.model")
    if direct:
        return direct

    prompt_model = _model_from_prompt(_get(span, "llm.prompt"))
    if prompt_model:
        return prompt_model

    span_by_id = {item.get("span_id"): item for item in all_spans if item.get("span_id")}
    for ancestor_id in _ancestor_ids(span, span_by_id):
        ancestor = span_by_id.get(ancestor_id) or {}
        ancestor_model = _get(ancestor, "llm.model")
        if ancestor_model:
            return ancestor_model

    return None


def _model_from_prompt(raw_prompt: Any) -> str | None:
    parsed = _loads(raw_prompt)
    if isinstance(parsed, dict) and parsed.get("model"):
        return parsed["model"]
    return None


def _span_failed(span: dict[str, Any]) -> bool:
    tool = span.get("tool") or {}
    span_status = span.get("status")
    tool_status = tool.get("tool_status")
    return any(
        [
            span_status not in (None, "SUCCESS"),
            tool_status not in (None, "SUCCESS"),
            bool(span.get("error_message")),
            bool(tool.get("tool_error")),
        ]
    )

def _execution_status(execution: dict[str, Any], spans: list[dict[str, Any]]) -> str:
    if any(_span_failed(span) for span in spans):
        return "FAILED"
    if execution.get("execution_end"):
        return "COMPLETED"
    return "N/A"


def _intelligence_status(execution: dict[str, Any], spans: list[dict[str, Any]]) -> str:
    if any(_span_failed(span) for span in spans):
        return "failed"
    if execution.get("execution_end"):
        return "completed"
    return N_A


def _execution_outcome(spans: list[dict[str, Any]]) -> str:
    return "SUCCESS" if all(not _span_failed(span) for span in spans) else "FAILED"


def _canonical_type(span: dict[str, Any]) -> str:
    mapping = {
        "AGENT": "AGENT_STEP",
        "LLM": "LLM_CALL",
        "TOOL": "TOOL_CALL",
        "HTTP": "HTTP_CALL",
        "MEMORY": "MEMORY_ACCESS",
        "REASONING": "REASONING_STEP",
        "UNKNOWN": "UNKNOWN",
    }
    return mapping.get(span.get("span_kind"), "N/A")


def _summary(span: dict[str, Any]) -> str:
    if span.get("error_message"):
        return span["error_message"]
    kind = span.get("span_kind")
    if kind == "AGENT":
        return "Agent step executed"
    if kind == "LLM":
        return "LLM call executed"
    if kind == "TOOL":
        return "Tool call executed"
    if kind == "HTTP":
        return "HTTP call executed"
    if kind == "MEMORY":
        return "Memory access executed"
    if kind == "REASONING":
        return "Reasoning step executed"
    return "Execution span processed"


def _sort_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(spans, key=lambda span: span.get("start_time") or "")


def _get(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _first(values: list[Any]) -> Any:
    return next((value for value in values if value not in (None, "")), None)


def _num(value: Any) -> int | float:
    return value if isinstance(value, (int, float)) else 0


def _jsonish(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _loads(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _json_schema_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
