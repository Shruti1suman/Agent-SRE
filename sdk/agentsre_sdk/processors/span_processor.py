from __future__ import annotations

import json
import logging
import hashlib
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from opentelemetry.context import get_current
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanProcessor
from opentelemetry.trace import SpanKind as OTelSpanKind

from agentsre_sdk.config import SDKConfig
from agentsre_sdk.exporters.http_exporter import AgentSREHTTPExporter
from agentsre_sdk.instrumentors.registry import snapshot_available_tools
from agentsre_sdk.processors.pii_processor import PIIProcessor, RedactionFindings
from agentsre_sdk.schema.models import (
    AgentSREPayload,
    AgentSection,
    AvailableAgent,
    AvailableTool,
    Execution,
    HTTPSection,
    LLMSection,
    MemorySection,
    ReasoningSection,
    Resource,
    Span,
    ToolSection,
)
from agentsre_sdk.utils.resource import detect_installed_version
from agentsre_sdk.utils.id_generator import generate_execution_id


logger = logging.getLogger(__name__)


@dataclass
class ExecutionBatch:
    execution_id: str
    spans: list[ReadableSpan] = field(default_factory=list)
    updated_at: float = field(default_factory=time.monotonic)


class AgentSRESpanProcessor(SpanProcessor):
    def __init__(
        self,
        config: SDKConfig,
        exporter: AgentSREHTTPExporter,
        resource: Resource,
        pii_processor: PIIProcessor | None = None,
    ) -> None:
        self.config = config
        self.exporter = exporter
        self.resource = resource
        self.pii_processor = pii_processor or PIIProcessor(config.pii_redaction, config.normalized_sensitive_fields)
        self._batches: dict[str, ExecutionBatch] = {}
        self._active_counts: dict[str, int] = {}
        self._lock = threading.RLock()
        self._flush_event = threading.Event()
        self._shutdown = False
        self._worker = threading.Thread(target=self._run_periodic_flush, name="agentsre-sdk-flush", daemon=True)
        self._worker.start()

    def on_start(self, span: Any, parent_context: Any | None = None) -> None:
        trace_id = _trace_id_from_span_like(span)
        if trace_id is not None:
            with self._lock:
                if not self._shutdown:
                    self._active_counts[trace_id] = self._active_counts.get(trace_id, 0) + 1
        current_context = parent_context or get_current()
        span.set_attribute("agentsre.tenant_id", self.config.tenant_id)
        span.set_attribute("agentsre.project_id", self.config.project_id)
        span.set_attribute("agentsre.service_name", self.config.service_name)
        span.set_attribute("agentsre.environment", self.config.environment)
        span.set_attribute("agentsre.workflow_id", self.config.workflow_id)
        span.set_attribute("agentsre.session_id", self.config.session_id)
        if self.config.user_id is not None:
            span.set_attribute("agentsre.user_id", self.config.user_id)
        if current_context is not None:
            span.set_attribute("agentsre.context_attached", True)

    def on_end(self, span: ReadableSpan) -> None:
        trace_id = _trace_id(span)
        with self._lock:
            if self._shutdown:
                return
            batch = self._batches.get(trace_id)
            if batch is None:
                batch = ExecutionBatch(execution_id=generate_execution_id())
                self._batches[trace_id] = batch
            batch.spans.append(span)
            batch.updated_at = time.monotonic()
            active_count = max(0, self._active_counts.get(trace_id, 0) - 1)
            if active_count:
                self._active_counts[trace_id] = active_count
            else:
                self._active_counts.pop(trace_id, None)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        with self._lock:
            trace_ids = list(self._batches.keys())
        for trace_id in trace_ids:
            self._flush_trace(trace_id)
        return True

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
        self._flush_event.set()
        if self._worker.is_alive():
            self._worker.join(timeout=max(1.0, self.config.export_interval_seconds))
        self.force_flush()
        self.exporter.shutdown()

    def _flush_trace(self, trace_id: str) -> None:
        with self._lock:
            batch = self._batches.pop(trace_id, None)
        if batch is None or not batch.spans:
            return
        try:
            payload = self.build_payload(trace_id, batch)
            self.exporter.export(payload)
        except Exception:
            logger.exception("AgentSRE failed to build or export telemetry payload")

    def _run_periodic_flush(self) -> None:
        while not self._flush_event.wait(self.config.export_interval_seconds):
            try:
                self.flush_ready_batches()
            except Exception:
                logger.exception("AgentSRE periodic flush failed")

    def flush_ready_batches(self) -> None:
        now = time.monotonic()
        with self._lock:
            trace_ids = [
                trace_id
                for trace_id, batch in self._batches.items()
                if self._active_counts.get(trace_id, 0) == 0 or now - batch.updated_at >= self.config.batch_timeout_seconds
            ]
        for trace_id in trace_ids:
            self._flush_trace(trace_id)

    def build_payload(self, trace_id: str, batch: ExecutionBatch) -> AgentSREPayload:
        ordered = sorted(batch.spans, key=lambda item: item.start_time or 0)
        ordered = [span for span in ordered if not _should_drop_span(span)]
        ordered, parent_remaps = _filter_langgraph_duplicate_wrappers(ordered)
        ordered, llm_parent_remaps = _filter_duplicate_llm_wrappers(ordered, parent_remaps)
        parent_remaps.update(llm_parent_remaps)
        span_models = [self._convert_span(span, batch.execution_id, parent_remaps) for span in ordered]
        _attach_memory_to_llm_spans(span_models)
        available_tools, available_agents = _available_inventories(ordered, self.config, batch.execution_id)
        starts = [span.start_time for span in ordered if span.start_time is not None]
        ends = [span.end_time for span in ordered if span.end_time is not None]
        execution_start_ns = min(starts) if starts else 0
        execution_end_ns = max(ends) if ends else execution_start_ns
        payload = AgentSREPayload(
            execution=Execution(
                trace_id=trace_id,
                execution_id=batch.execution_id,
                workflow_id=self.config.workflow_id,
                session_id=self.config.session_id,
                user_id=self.config.user_id,
                tenant_id=self.config.tenant_id,
                project_id=self.config.project_id,
                service_name=self.config.service_name,
                environment=self.config.environment,
                execution_start=_ns_to_iso(execution_start_ns),
                execution_end=_ns_to_iso(execution_end_ns),
                total_duration_ms=_duration_ms(execution_start_ns, execution_end_ns),
                available_tools=available_tools,
                available_agents=available_agents,
            ),
            resource=_resource_for_payload(ordered, self.resource),
            spans=span_models,
        )
        redacted, findings = self.pii_processor.redact_payload_with_findings(payload.model_dump(mode="json"))
        _apply_section_redaction_metadata(redacted, findings)
        return AgentSREPayload.model_validate(redacted)

    def _convert_span(self, span: ReadableSpan, execution_id: str, parent_remaps: dict[str, str] | None = None) -> Span:
        attrs = dict(span.attributes or {})
        trace_id = _trace_id(span)
        span_id = _span_id(span)
        span_kind = _canonical_span_kind(span, attrs)
        start_time = span.start_time or 0
        end_time = span.end_time or start_time
        status, error_type, error_message = _status_fields(span, attrs)
        sections = self._sections_for_span(span_kind, attrs, span, execution_id)
        return Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=_parent_span_id(span, parent_remaps),
            span_name=span.name,
            span_kind=span_kind,
            start_time=_ns_to_iso(start_time),
            end_time=_ns_to_iso(end_time),
            duration_ms=_duration_ms(start_time, end_time),
            status=status,
            error_type=error_type,
            error_message=error_message,
            trace_context=f"00-{trace_id}-{span_id}-01",
            baggage=_dict_attr(attrs, "baggage") or {},
            retry_count=_int_attr(attrs, "retry_count", "agentsre.retry_count") or 0,
            iteration_count=_int_attr(attrs, "iteration_count", "agentsre.iteration_count") or 1,
            agent=sections["agent"],
            llm=sections["llm"],
            tool=sections["tool"],
            memory=sections["memory"],
            reasoning=sections["reasoning"],
            http=sections["http"],
        )

    def _sections_for_span(
        self,
        span_kind: str,
        attrs: dict[str, Any],
        span: ReadableSpan,
        execution_id: str,
    ) -> dict[str, Any]:
        sections: dict[str, Any] = {
            "agent": None,
            "llm": None,
            "tool": None,
            "memory": None,
            "reasoning": None,
            "http": None,
        }
        if span_kind == "LLM":
            sections["llm"] = _llm_section(attrs)
        elif span_kind == "TOOL":
            sections["tool"] = _tool_section(attrs, span)
            if _has_http_attrs(attrs):
                sections["http"] = _http_section(attrs, span)
        elif span_kind == "MEMORY":
            sections["memory"] = _memory_section(attrs)
        elif span_kind == "HTTP":
            sections["http"] = _http_section(attrs, span)
        elif span_kind == "AGENT":
            sections["agent"] = _agent_section(attrs, self.config, execution_id, span.name)
            sections["reasoning"] = _reasoning_section(attrs)
        else:
            sections["reasoning"] = _reasoning_section(attrs)
        return sections


def _canonical_span_kind(span: ReadableSpan, attrs: dict[str, Any]) -> str:
    agentsre_kind = _normalized_span_kind(_str_attr(attrs, "agentsre.span_kind"))
    if agentsre_kind is not None:
        return agentsre_kind
    openinference_kind = _normalized_span_kind(_str_attr(attrs, "openinference.span.kind", "span.kind"))
    if openinference_kind is not None:
        return openinference_kind
    if _has_llm_attrs(attrs):
        return "LLM"
    if _has_tool_attrs(attrs):
        return "TOOL"
    if _has_memory_attrs(attrs):
        return "MEMORY"
    if _has_http_attrs(attrs) or span.kind in {OTelSpanKind.CLIENT, OTelSpanKind.SERVER}:
        return "HTTP"
    return "AGENT" if span.parent is None else "UNKNOWN"


def _should_drop_span(span: ReadableSpan) -> bool:
    attrs = dict(span.attributes or {})
    return _bool_attr(attrs, "agentsre.drop_span") is True


def _normalized_span_kind(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.upper()
    if normalized in {"CHAIN", "AGENT"}:
        return "AGENT"
    if normalized in {"LLM", "TOOL", "MEMORY", "REASONING", "HTTP", "UNKNOWN"}:
        return normalized
    return None


def _agent_section(attrs: dict[str, Any], config: SDKConfig, execution_id: str, fallback_name: str) -> AgentSection:
    agent_name = _str_attr(attrs, "agent.name", "agentsre.agent_name", "agentsre.langgraph.node_name", "node.name", "langgraph.node.name") or fallback_name
    return AgentSection(
        agent_id=_str_attr(attrs, "agent.id", "agentsre.agent_id") or _fallback_agent_id(attrs, config, fallback_name),
        agent_name=agent_name,
        parent_agent=_str_attr(attrs, "agent.parent", "agentsre.parent_agent"),
        agent_role=_str_attr(attrs, "agent.role", "agentsre.agent_role") or _infer_agent_role(agent_name),
        agent_type=_str_attr(attrs, "agent.type", "agentsre.agent_type") or _str_attr(attrs, "agentsre.node_classification") or "LangGraphNode",
        workflow_id=config.workflow_id,
        execution_id=execution_id,
        session_id=config.session_id,
    )


def _llm_section(attrs: dict[str, Any]) -> LLMSection:
    input_tokens = _int_attr(attrs, "llm.token_count.prompt", "gen_ai.usage.input_tokens", "input_tokens")
    output_tokens = _int_attr(attrs, "llm.token_count.completion", "gen_ai.usage.output_tokens", "output_tokens")
    total_tokens = _int_attr(attrs, "llm.token_count.total", "gen_ai.usage.total_tokens", "total_tokens")
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)
    model = _str_attr(attrs, "llm.model_name", "gen_ai.request.model", "openai.model_name", "model")
    provider = _str_attr(attrs, "llm.provider", "gen_ai.system", "provider")
    return LLMSection(
        provider=provider,
        model=model,
        temperature=_float_attr(attrs, "llm.invocation_parameters.temperature", "gen_ai.request.temperature", "temperature"),
        max_tokens=_int_attr(attrs, "llm.invocation_parameters.max_tokens", "gen_ai.request.max_tokens", "max_tokens"),
        top_p=_float_attr(attrs, "llm.invocation_parameters.top_p", "gen_ai.request.top_p", "top_p"),
        frequency_penalty=_float_attr(attrs, "frequency_penalty", "llm.invocation_parameters.frequency_penalty"),
        presence_penalty=_float_attr(attrs, "presence_penalty", "llm.invocation_parameters.presence_penalty"),
        system_prompt=_str_attr(attrs, "llm.prompts.0.role.system", "system_prompt"),
        prompt=_str_attr(attrs, "input.value", "llm.input_messages", "prompt"),
        response=_str_attr(attrs, "output.value", "llm.output_messages", "response"),
        finish_reason=_finish_reason(attrs),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost=None,
    )


def _tool_section(attrs: dict[str, Any], span: ReadableSpan) -> ToolSection:
    start_time = span.start_time or 0
    end_time = span.end_time or start_time
    status, _, error_message = _status_fields(span, attrs)
    return ToolSection(
        tool_name=_str_attr(attrs, "tool.name", "tool_name", "agentsre.langgraph.node_name", "node.name") or span.name,
        tool_type=_str_attr(attrs, "tool.type", "tool_type") or _infer_tool_type(_str_attr(attrs, "agentsre.langgraph.node_name", "node.name") or span.name),
        tool_description=_str_attr(attrs, "tool.description", "tool_description", "function.description", "openinference.tool.description"),
        tool_arguments=_jsonish_attr(attrs, "tool.parameters", "tool.arguments", "tool_arguments", "input.value"),
        tool_output=_jsonish_attr(attrs, "tool.output", "tool_output", "output.value"),
        tool_status=_str_attr(attrs, "tool.status", "tool_status") or status,
        tool_error=_str_attr(attrs, "tool.error", "tool_error", "exception.message") or error_message,
        tool_latency=_duration_ms(start_time, end_time),
    )


def _memory_section(attrs: dict[str, Any]) -> MemorySection:
    return MemorySection(
        memory_operation=_str_attr(attrs, "memory.operation", "memory_operation"),
        memory_key=_str_attr(attrs, "memory.key", "memory_key"),
        retrieved_documents=_jsonish_attr(attrs, "retrieval.documents", "retrieved_documents"),
        retrieval_score=_float_attr(attrs, "retrieval.score", "retrieval_score"),
        vector_store=_str_attr(attrs, "vector_store", "db.system"),
        retrieved_chunks=_jsonish_attr(attrs, "retrieval.chunks", "retrieved_chunks"),
    )


def _reasoning_section(attrs: dict[str, Any]) -> ReasoningSection:
    return ReasoningSection(
        reasoning_step=_int_attr(attrs, "reasoning.step", "reasoning_step", "agentsre.reasoning_step"),
        node_name=_str_attr(attrs, "node.name", "langgraph.node.name", "node_name", "agentsre.langgraph.node_name"),
        previous_node=_str_attr(attrs, "previous_node", "agentsre.previous_node", "agentsre.langgraph.previous_node"),
        next_node=_str_attr(attrs, "next_node", "agentsre.next_node", "agentsre.langgraph.next_node", "agentsre.langgraph.conditional_target"),
        decision_type=_str_attr(attrs, "decision.type", "decision_type", "agentsre.decision_type"),
    )


def _http_section(attrs: dict[str, Any], span: ReadableSpan) -> HTTPSection:
    start_time = span.start_time or 0
    end_time = span.end_time or start_time
    return HTTPSection(
        endpoint=_str_attr(attrs, "url.full", "http.url", "http.target", "server.address"),
        method=_str_attr(attrs, "http.request.method", "http.method"),
        response_code=_int_attr(attrs, "http.response.status_code", "http.status_code"),
        request_size=_int_attr(attrs, "http.request.body.size", "http.request_content_length"),
        response_size=_int_attr(attrs, "http.response.body.size", "http.response_content_length"),
        latency=_duration_ms(start_time, end_time),
    )


def _status_fields(span: ReadableSpan, attrs: dict[str, Any]) -> tuple[str, str | None, str | None]:
    exception_type = _str_attr(attrs, "exception.type")
    exception_message = _str_attr(attrs, "exception.message")
    status_code = getattr(span.status, "status_code", None)
    status_name = getattr(status_code, "name", "UNSET")
    if exception_type or status_name == "ERROR":
        return "ERROR", exception_type, exception_message or getattr(span.status, "description", None)
    return "SUCCESS", None, None


def _apply_section_redaction_metadata(payload: dict[str, Any], findings: RedactionFindings) -> None:
    section_findings: dict[tuple[int, str], set[str]] = {}
    tracked_sections = {"agent", "llm", "tool", "memory"}
    for path, fields in findings.items():
        if len(path) < 3 or path[0] != "spans" or not isinstance(path[1], int):
            continue
        section_name = path[2]
        if section_name in tracked_sections:
            section_findings.setdefault((path[1], section_name), set()).update(fields)
    spans = payload.get("spans")
    if not isinstance(spans, list):
        return
    for (span_index, section_name), fields in section_findings.items():
        if not 0 <= span_index < len(spans):
            continue
        span = spans[span_index]
        if not isinstance(span, dict):
            continue
        section = span.get(section_name)
        if not isinstance(section, dict):
            continue
        section["redaction_applied"] = True
        section["redaction_field"] = sorted(fields)


def _attach_memory_to_llm_spans(spans: list[Span]) -> None:
    memory_sections = [span.memory for span in spans if span.memory is not None]
    if not memory_sections:
        return
    for span in spans:
        if span.llm is None or span.memory is not None:
            continue
        prompt = span.llm.prompt or ""
        if not prompt:
            continue
        matching_memory = next((memory for memory in memory_sections if _memory_matches_prompt(memory, prompt)), None)
        if matching_memory is not None:
            span.memory = matching_memory.model_copy(deep=True)


def _memory_matches_prompt(memory: MemorySection, prompt: str) -> bool:
    normalized_prompt = _normalize_match_text(prompt)
    if not normalized_prompt:
        return False
    evidence_found = False
    for item in _memory_items(memory):
        source = item.get("source")
        if source and _normalize_match_text(source) in normalized_prompt:
            return True
        text_value = item.get("text")
        if text_value:
            evidence_found = True
            snippet = _normalize_match_text(text_value)[:80]
            if len(snippet) >= 30 and snippet in normalized_prompt:
                return True
    normalized_key = _normalize_match_text(memory.memory_key or "")
    return evidence_found and bool(normalized_key) and "memory" in normalized_prompt and normalized_key in normalized_prompt


def _memory_items(memory: MemorySection) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for value in [memory.retrieved_documents, memory.retrieved_chunks]:
        if isinstance(value, dict):
            items.append(value)
        elif isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return items


def _normalize_match_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, default=str)
    return " ".join(value.replace("\\n", " ").replace("\n", " ").lower().split())


def _available_inventories(spans: list[ReadableSpan], config: SDKConfig, execution_id: str) -> tuple[list[AvailableTool], list[AvailableAgent]]:
    tools: dict[str, AvailableTool] = {}
    agents: dict[str, tuple[int, AvailableAgent]] = {}
    for registered_tool in snapshot_available_tools():
        tool = _available_tool_from_attrs(
            {
                "tool.name": registered_tool.get("tool_name"),
                "tool.description": registered_tool.get("tool_description"),
                "tool.type": registered_tool.get("tool_type"),
                "tool.arguments": registered_tool.get("tool_arguments"),
            },
            config,
            str(registered_tool.get("tool_name") or "LangChainTool"),
        )
        _put_available_tool(tools, tool)
    for span in spans:
        attrs = dict(span.attributes or {})
        _merge_registered_langgraph_inventory(attrs, config, tools, agents)
        _merge_registered_crewai_inventory(attrs, config, tools, agents)
        span_kind = _canonical_span_kind(span, attrs)
        if span_kind == "TOOL":
            _put_available_tool(tools, _available_tool_from_attrs(attrs, config, span.name))
        if span_kind == "AGENT":
            agent = _available_agent_from_attrs(attrs, config, execution_id, span.name)
            _put_available_agent(agents, agent, _available_agent_priority(span))
    return (
        sorted(tools.values(), key=lambda item: (item.tool_name, item.tool_id)),
        sorted((item[1] for item in agents.values()), key=lambda item: (item.agent_name, item.agent_id)),
    )


def _merge_registered_langgraph_inventory(
    attrs: dict[str, Any],
    config: SDKConfig,
    tools: dict[str, AvailableTool],
    agents: dict[str, tuple[int, AvailableAgent]],
) -> None:
    graph_name = _str_attr(attrs, "agentsre.langgraph.graph_name")
    if graph_name:
        graph_attrs = {
            "agentsre.langgraph.graph_name": graph_name,
            "agentsre.langgraph.node_name": graph_name,
            "agentsre.agent_name": graph_name,
            "agentsre.agent_role": "Graph",
            "agentsre.agent_type": "LangGraph",
        }
        graph_agent = _available_agent_from_attrs(graph_attrs, config, "", f"LangGraph Graph: {graph_name}")
        _put_available_agent(agents, graph_agent, 100)
    registered_nodes = _jsonish_attr(attrs, "agentsre.langgraph.registered_nodes")
    if not isinstance(registered_nodes, list):
        return
    for item in registered_nodes:
        if not isinstance(item, dict):
            continue
        node_name = str(item.get("node_name") or "")
        if not node_name:
            continue
        classification = str(item.get("classification") or "agent")
        node_attrs = {
            "agentsre.langgraph.graph_name": graph_name or "unknown_graph",
            "agentsre.langgraph.node_name": node_name,
            "agentsre.agent_name": node_name,
            "agentsre.agent_role": item.get("agent_role"),
            "agentsre.agent_type": item.get("agent_type") or "LangGraphNode",
            "tool.name": node_name,
            "tool.type": item.get("tool_type"),
            "tool.description": item.get("tool_description"),
            "tool.arguments": item.get("tool_arguments"),
        }
        if classification == "tool":
            tool = _available_tool_from_attrs(node_attrs, config, f"LangGraph Node: {node_name}")
            _put_available_tool(tools, tool)
        elif classification == "agent":
            agent = _available_agent_from_attrs(node_attrs, config, "", f"LangGraph Node: {node_name}")
            _put_available_agent(agents, agent, 90)


def _merge_registered_crewai_inventory(
    attrs: dict[str, Any],
    config: SDKConfig,
    tools: dict[str, AvailableTool],
    agents: dict[str, tuple[int, AvailableAgent]],
) -> None:
    crew_name = _str_attr(attrs, "agentsre.crewai.crew_name")
    if crew_name:
        crew_attrs = {
            "agentsre.agent_name": crew_name,
            "agentsre.agent_role": "Crew",
            "agentsre.agent_type": "CrewAI.Crew",
        }
        _put_available_agent(agents, _available_agent_from_attrs(crew_attrs, config, "", f"CrewAI Crew: {crew_name}"), 100)

    registered_agents = _jsonish_attr(attrs, "agentsre.crewai.registered_agents")
    if isinstance(registered_agents, list):
        for item in registered_agents:
            if not isinstance(item, dict):
                continue
            agent_name = str(item.get("agent_name") or item.get("agent_role") or item.get("role") or "")
            if not agent_name:
                continue
            agent_attrs = {
                "agent.id": item.get("agent_id"),
                "agentsre.agent_name": agent_name,
                "agentsre.agent_role": item.get("agent_role") or agent_name,
                "agentsre.agent_type": item.get("agent_type") or "CrewAI.Agent",
            }
            _put_available_agent(agents, _available_agent_from_attrs(agent_attrs, config, "", f"CrewAI Agent: {agent_name}"), 90)

    registered_tools = _jsonish_attr(attrs, "agentsre.crewai.registered_tools")
    if isinstance(registered_tools, list):
        for item in registered_tools:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name") or item.get("name") or "")
            if not tool_name:
                continue
            tool_attrs = {
                "tool.id": item.get("tool_id"),
                "tool.name": tool_name,
                "tool.description": item.get("tool_description") or item.get("description"),
                "tool.type": item.get("tool_type") or "Tool",
                "tool.arguments": item.get("tool_arguments") or item.get("arguments"),
            }
            _put_available_tool(tools, _available_tool_from_attrs(tool_attrs, config, f"CrewAI Tool: {tool_name}"))


def _available_tool_from_attrs(attrs: dict[str, Any], config: SDKConfig, fallback_name: str) -> AvailableTool:
    tool_name = _str_attr(attrs, "tool.name", "tool_name", "agentsre.langgraph.node_name", "node.name") or fallback_name
    tool_type = _str_attr(attrs, "tool.type", "tool_type") or _infer_tool_type(tool_name)
    raw_arguments = _jsonish_attr(attrs, "tool.parameters", "tool.arguments", "tool_arguments", "input.value")
    return AvailableTool(
        tool_id=_str_attr(attrs, "tool.id", "tool_id") or _fallback_tool_id(attrs, config, tool_name, tool_type),
        tool_name=tool_name,
        tool_description=_str_attr(attrs, "tool.description", "tool_description", "function.description", "openinference.tool.description"),
        tool_type=tool_type,
        tool_arguments=_available_tool_arguments(raw_arguments),
    )


def _available_agent_from_attrs(attrs: dict[str, Any], config: SDKConfig, execution_id: str, fallback_name: str) -> AvailableAgent:
    section = _agent_section(attrs, config, execution_id, fallback_name)
    return AvailableAgent(
        agent_id=section.agent_id or _fallback_agent_id(attrs, config, fallback_name),
        agent_name=section.agent_name or fallback_name,
        agent_role=section.agent_role,
        agent_type=section.agent_type,
    )


def _put_available_tool(tools: dict[str, AvailableTool], tool: AvailableTool) -> None:
    key = _available_tool_key(tool.tool_name)
    if key is None:
        return
    existing = tools.get(key)
    tools[key] = tool if existing is None else _merge_available_tool(existing, tool)


def _available_tool_key(tool_name: str | None) -> str | None:
    normalized = (tool_name or "").strip().lower()
    return normalized or None


def _merge_available_tool(existing: AvailableTool, candidate: AvailableTool) -> AvailableTool:
    return AvailableTool(
        tool_id=existing.tool_id,
        tool_name=existing.tool_name or candidate.tool_name,
        tool_description=existing.tool_description or candidate.tool_description,
        tool_type=existing.tool_type or candidate.tool_type,
        tool_arguments=_prefer_available_tool_arguments(existing.tool_arguments, candidate.tool_arguments),
    )


def _prefer_available_tool_arguments(existing: Any, candidate: Any) -> Any:
    if existing is None:
        return candidate
    if candidate is None:
        return existing
    existing_is_schema = _looks_like_tool_schema(existing)
    candidate_is_schema = _looks_like_tool_schema(candidate)
    if candidate_is_schema and not existing_is_schema:
        return candidate
    return existing


def _available_tool_arguments(value: Any) -> Any:
    if value is None:
        return None
    if _looks_like_tool_schema(value):
        return value
    return _schema_from_runtime_arguments(value)


def _schema_from_runtime_arguments(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): {"type": _json_type_name(item)} for key, item in value.items()}
    if isinstance(value, list):
        return {"type": "array"}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            return _schema_from_runtime_arguments(parsed)
        return {"type": "string"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    return {"type": "null"} if value is None else {"type": "string"}


def _json_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    return "string"


def _looks_like_tool_schema(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    schema_keys = {"type", "title", "description", "default", "anyOf", "items", "properties"}
    if schema_keys.intersection(value):
        return True
    dict_values = [item for item in value.values() if isinstance(item, dict)]
    if not dict_values:
        return False
    return all(bool(schema_keys.intersection(item)) for item in dict_values)


def _put_available_agent(agents: dict[str, tuple[int, AvailableAgent]], agent: AvailableAgent, priority: int) -> None:
    key = _available_agent_key(agent.agent_name)
    if key is None:
        return
    existing = agents.get(key)
    if existing is None or priority > existing[0]:
        agents[key] = (priority, agent)


def _available_agent_key(agent_name: str | None) -> str | None:
    normalized = (agent_name or "").strip()
    lowered = normalized.lower()
    if not normalized:
        return None
    if lowered in {"model", "tool", "tools", "__start__", "__end__", "start", "end"}:
        return None
    if lowered.startswith("route_") or lowered.endswith("_route"):
        return None
    return lowered


def _available_agent_priority(span: ReadableSpan) -> int:
    if span.name.startswith("LangGraph Graph: "):
        return 100
    if span.name.startswith("LangGraph Node: "):
        return 80
    return 50


def _trace_id(span: ReadableSpan) -> str:
    return f"{span.context.trace_id:032x}"


def _trace_id_from_span_like(span: Any) -> str | None:
    context = getattr(span, "context", None)
    if context is None and callable(getattr(span, "get_span_context", None)):
        context = span.get_span_context()
    trace_id = getattr(context, "trace_id", None)
    if not trace_id:
        return None
    return f"{trace_id:032x}"


def _span_id(span: ReadableSpan) -> str:
    return f"{span.context.span_id:016x}"


def _raw_parent_span_id(span: ReadableSpan) -> str | None:
    if span.parent is None:
        return None
    return f"{span.parent.span_id:016x}"


def _parent_span_id(span: ReadableSpan, parent_remaps: dict[str, str] | None = None) -> str | None:
    parent_id = _raw_parent_span_id(span)
    if parent_id is None:
        return None
    if parent_remaps is None:
        return parent_id
    seen = set()
    while parent_id in parent_remaps and parent_id not in seen:
        seen.add(parent_id)
        parent_id = parent_remaps[parent_id]
    return parent_id


def _filter_langgraph_duplicate_wrappers(spans: list[ReadableSpan]) -> tuple[list[ReadableSpan], dict[str, str]]:
    custom_graph_spans: dict[str, ReadableSpan] = {}
    custom_node_spans: dict[str, list[ReadableSpan]] = {}
    for span in spans:
        attrs = dict(span.attributes or {})
        graph_name = _custom_langgraph_graph_name(span, attrs)
        if graph_name is not None:
            custom_graph_spans[graph_name] = span
        node_name = _custom_langgraph_node_name(span, attrs)
        if node_name is not None:
            custom_node_spans.setdefault(node_name, []).append(span)

    if not custom_graph_spans and not custom_node_spans:
        return spans, {}

    filtered = []
    parent_remaps: dict[str, str] = {}
    for span in spans:
        attrs = dict(span.attributes or {})
        if _is_custom_agentsre_langgraph_span(span):
            filtered.append(span)
            continue
        if _is_internal_framework_wrapper_span(span, attrs):
            remap_target = _internal_wrapper_remap_target(span, custom_node_spans, parent_remaps)
            if remap_target is not None:
                parent_remaps[_span_id(span)] = remap_target
            continue
        duplicate_target = custom_graph_spans.get(span.name) or _best_overlapping_span(span, custom_node_spans.get(span.name, []))
        if duplicate_target is not None and _canonical_span_kind(span, attrs) not in {"LLM", "TOOL", "MEMORY", "HTTP"}:
            parent_remaps[_span_id(span)] = _span_id(duplicate_target)
            continue
        filtered.append(span)
    return filtered, parent_remaps


def _best_overlapping_span(target: ReadableSpan, candidates: list[ReadableSpan]) -> ReadableSpan | None:
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda candidate: (
            _time_overlap_ns(target, candidate),
            -(abs((target.start_time or 0) - (candidate.start_time or 0))),
        ),
    )


def _resource_for_payload(spans: list[ReadableSpan], resource: Resource) -> Resource:
    has_crewai = any(_is_crewai_span(span) for span in spans)
    has_langgraph = any(_is_custom_agentsre_langgraph_span(span) for span in spans)
    if has_crewai and not has_langgraph:
        return resource.model_copy(update={"framework": "CrewAI", "framework_version": detect_installed_version("crewai")})
    return resource


def _is_crewai_span(span: ReadableSpan) -> bool:
    attrs = dict(span.attributes or {})
    agent_type = _str_attr(attrs, "agent.type", "agentsre.agent_type") or ""
    return (
        span.name.startswith("CrewAI ")
        or agent_type.startswith("CrewAI.")
        or _bool_attr(attrs, "agentsre.crewai.llm_event") is True
        or _str_attr(attrs, "agentsre.crewai.crew_name", "agentsre.crewai.task_id") is not None
    )


def _time_overlap_ns(left: ReadableSpan, right: ReadableSpan) -> int:
    left_start = left.start_time or 0
    right_start = right.start_time or 0
    left_end = left.end_time or left_start
    right_end = right.end_time or right_start
    return max(0, min(left_end, right_end) - max(left_start, right_start))


def _custom_langgraph_graph_name(span: ReadableSpan, attrs: dict[str, Any]) -> str | None:
    if span.name.startswith("LangGraph Graph: "):
        return span.name.removeprefix("LangGraph Graph: ")
    return None


def _custom_langgraph_node_name(span: ReadableSpan, attrs: dict[str, Any]) -> str | None:
    if span.name.startswith("LangGraph Node: "):
        return span.name.removeprefix("LangGraph Node: ")
    return None


def _is_custom_agentsre_langgraph_span(span: ReadableSpan) -> bool:
    return span.name.startswith(("LangGraph Graph: ", "LangGraph Node: ", "LangGraph Conditional Edge: "))


def _is_internal_framework_wrapper_span(span: ReadableSpan, attrs: dict[str, Any]) -> bool:
    lowered = span.name.strip().lower()
    if lowered in {"model", "tool", "tools", "runnablesequence", "runnablelambda", "__start__", "__end__", "start", "end"}:
        return _canonical_span_kind(span, attrs) not in {"LLM", "TOOL", "MEMORY", "HTTP"}
    if lowered.startswith("route_") or lowered.endswith("_route"):
        return _canonical_span_kind(span, attrs) not in {"LLM", "TOOL", "MEMORY", "HTTP"}
    return False


def _internal_wrapper_remap_target(
    span: ReadableSpan,
    custom_node_spans: dict[str, list[ReadableSpan]],
    parent_remaps: dict[str, str],
) -> str | None:
    parent_id = _raw_parent_span_id(span)
    candidates: list[ReadableSpan] = []
    current = parent_id
    seen: set[str] = set()
    while current is not None and current not in seen:
        seen.add(current)
        parent_span = _span_by_id(custom_node_spans, current)
        if parent_span is not None:
            candidates.append(parent_span)
        current = parent_remaps.get(current)
    overlapping = _best_overlapping_span(span, candidates)
    if overlapping is not None:
        return _span_id(overlapping)
    if parent_id is None:
        return None
    return _effective_parent_id(parent_id, parent_remaps)


def _span_by_id(spans_by_name: dict[str, list[ReadableSpan]], span_id: str) -> ReadableSpan | None:
    for spans in spans_by_name.values():
        for span in spans:
            if _span_id(span) == span_id:
                return span
    return None


def _filter_duplicate_llm_wrappers(
    spans: list[ReadableSpan],
    existing_parent_remaps: dict[str, str] | None = None,
) -> tuple[list[ReadableSpan], dict[str, str]]:
    effective_parent_remaps = existing_parent_remaps or {}
    provider_llm_spans = [
        span
        for span in spans
        if _is_provider_llm_span(span)
    ]
    if not provider_llm_spans:
        return spans, {}

    filtered: list[ReadableSpan] = []
    parent_remaps: dict[str, str] = {}
    for span in spans:
        attrs = dict(span.attributes or {})
        if not _is_llm_wrapper_span(span) or _canonical_span_kind(span, attrs) != "LLM":
            filtered.append(span)
            continue
        duplicate_target = next(
            (
                provider_span
                for provider_span in provider_llm_spans
                if _same_llm_call(span, provider_span, effective_parent_remaps)
            ),
            None,
        )
        if duplicate_target is None:
            filtered.append(span)
            continue
        wrapper_parent = _raw_parent_span_id(span)
        parent_remaps[_span_id(span)] = _effective_parent_id(wrapper_parent, effective_parent_remaps) or _span_id(duplicate_target)
    return filtered, parent_remaps


def _same_llm_call(
    wrapper: ReadableSpan,
    provider_span: ReadableSpan,
    parent_remaps: dict[str, str] | None = None,
) -> bool:
    wrapper_parent = _raw_parent_span_id(wrapper)
    provider_parent = _raw_parent_span_id(provider_span)
    effective_wrapper_parent = _effective_parent_id(wrapper_parent, parent_remaps)
    effective_provider_parent = _effective_parent_id(provider_parent, parent_remaps)
    wrapper_attrs = dict(wrapper.attributes or {})
    provider_attrs = dict(provider_span.attributes or {})
    if (
        _is_crewai_llm_wrapper_span(wrapper)
        and effective_provider_parent == _span_id(wrapper)
        and _same_llm_model(wrapper_attrs, provider_attrs)
        and _has_richer_llm_usage(provider_attrs)
    ):
        return True
    if not _same_time_window(wrapper, provider_span):
        return False
    if _is_crewai_llm_wrapper_span(wrapper) and _same_llm_model(wrapper_attrs, provider_attrs) and _has_richer_llm_usage(provider_attrs):
        return True
    matching_evidence = 0
    for names in [
        ("llm.model_name", "gen_ai.request.model", "openai.model_name", "model"),
        ("llm.token_count.prompt", "gen_ai.usage.input_tokens", "input_tokens"),
        ("llm.token_count.completion", "gen_ai.usage.output_tokens", "output_tokens"),
        ("llm.token_count.total", "gen_ai.usage.total_tokens", "total_tokens"),
        ("llm.completions.0.finish_reason", "gen_ai.response.finish_reasons", "finish_reason"),
    ]:
        wrapper_value = _first_attr(wrapper_attrs, *names)
        provider_value = _first_attr(provider_attrs, *names)
        if (
            wrapper_value is not None
            and provider_value is not None
            and _llm_evidence_value(wrapper_value) != _llm_evidence_value(provider_value)
        ):
            return False
        if wrapper_value is not None and provider_value is not None:
            matching_evidence += 1
    if effective_provider_parent in {effective_wrapper_parent, _span_id(wrapper)}:
        return True
    return matching_evidence >= 2


def _is_llm_wrapper_span(span: ReadableSpan) -> bool:
    return span.name in {"ChatOpenAI", "ChatAnthropic", "ChatGoogleGenerativeAI"} or _is_crewai_llm_wrapper_span(span)


def _is_crewai_llm_wrapper_span(span: ReadableSpan) -> bool:
    return span.name.startswith("CrewAI LLM: ")


def _is_provider_llm_span(span: ReadableSpan) -> bool:
    attrs = dict(span.attributes or {})
    if _canonical_span_kind(span, attrs) != "LLM":
        return False
    if _is_llm_wrapper_span(span):
        return False
    if _bool_attr(attrs, "agentsre.crewai.llm_event"):
        return False
    return True


def _same_llm_model(left_attrs: dict[str, Any], right_attrs: dict[str, Any]) -> bool:
    left_model = _normalized_model_name(_first_attr(left_attrs, "llm.model_name", "gen_ai.request.model", "openai.model_name", "model"))
    right_model = _normalized_model_name(_first_attr(right_attrs, "llm.model_name", "gen_ai.request.model", "openai.model_name", "model"))
    return bool(
        left_model
        and right_model
        and (
            left_model == right_model
            or right_model.startswith(f"{left_model}-")
            or left_model.startswith(f"{right_model}-")
        )
    )


def _normalized_model_name(value: Any) -> str | None:
    if value is None:
        return None
    model = str(value).lower()
    if "/" in model:
        model = model.split("/", 1)[1]
    return model


def _has_richer_llm_usage(attrs: dict[str, Any]) -> bool:
    return any(
        _first_attr(attrs, *names) is not None
        for names in [
            ("llm.token_count.prompt", "gen_ai.usage.input_tokens", "input_tokens"),
            ("llm.token_count.completion", "gen_ai.usage.output_tokens", "output_tokens"),
            ("llm.token_count.total", "gen_ai.usage.total_tokens", "total_tokens"),
            ("llm.completions.0.finish_reason", "gen_ai.response.finish_reasons", "finish_reason"),
        ]
    )


def _same_time_window(left: ReadableSpan, right: ReadableSpan) -> bool:
    left_start = left.start_time or 0
    right_start = right.start_time or 0
    left_end = left.end_time or left_start
    right_end = right.end_time or right_start
    start_delta_ms = abs(left_start - right_start) / 1_000_000
    end_delta_ms = abs(left_end - right_end) / 1_000_000
    return start_delta_ms <= 1000 and end_delta_ms <= 1000


def _llm_evidence_value(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, tuple):
        value = list(value)
    first = _first_string(value)
    if first is not None:
        return first
    return str(value)


def _effective_parent_id(parent_span_id: str | None, parent_remaps: dict[str, str] | None) -> str | None:
    if parent_span_id is None or not parent_remaps:
        return parent_span_id
    seen: set[str] = set()
    current = parent_span_id
    while current in parent_remaps and current not in seen:
        seen.add(current)
        current = parent_remaps[current]
    return current


def _has_meaningful_child_telemetry(span: ReadableSpan, attrs: dict[str, Any]) -> bool:
    span_kind = _canonical_span_kind(span, attrs)
    if span_kind in {"LLM", "TOOL", "MEMORY", "HTTP"}:
        return True
    return any(
        key.startswith(("llm.", "gen_ai.", "openai.", "tool.", "memory.", "retrieval.", "http."))
        or key in {"url.full", "http.url", "tool_name", "tool_arguments", "tool_output", "model", "provider"}
        for key in attrs
    )


def _ns_to_iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000_000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _duration_ms(start_ns: int, end_ns: int) -> int:
    return max(0, round((end_ns - start_ns) / 1_000_000))


def _str_attr(attrs: dict[str, Any], *names: str) -> str | None:
    value = _first_attr(attrs, *names)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)
    return str(value)


def _int_attr(attrs: dict[str, Any], *names: str) -> int | None:
    value = _first_attr(attrs, *names)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_attr(attrs: dict[str, Any], *names: str) -> float | None:
    value = _first_attr(attrs, *names)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_attr(attrs: dict[str, Any], *names: str) -> bool | None:
    value = _first_attr(attrs, *names)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    if isinstance(value, int):
        return bool(value)
    return None


def _dict_attr(attrs: dict[str, Any], *names: str) -> dict[str, Any] | None:
    value = _first_attr(attrs, *names)
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _jsonish_attr(attrs: dict[str, Any], *names: str) -> Any:
    value = _first_attr(attrs, *names)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, tuple):
        return list(value)
    return value


def _finish_reason(attrs: dict[str, Any]) -> str | None:
    direct = _jsonish_attr(attrs, "llm.completions.0.finish_reason", "gen_ai.response.finish_reasons", "finish_reason")
    normalized = _first_string(direct)
    if normalized is not None:
        return normalized
    for name in ["output.value", "response", "llm.output_messages", "gen_ai.response", "openai.response"]:
        found = _find_nested_value(_jsonish_attr(attrs, name), "finish_reason")
        normalized = _first_string(found)
        if normalized is not None:
            return normalized
    return None


def _find_nested_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for item in value.values():
            found = _find_nested_value(item, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_nested_value(item, key)
            if found is not None:
                return found
    return None


def _first_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            normalized = _first_string(item)
            if normalized is not None:
                return normalized
        return None
    if isinstance(value, dict):
        found = _find_nested_value(value, "finish_reason")
        if found is not None and found is not value:
            return _first_string(found)
        return None
    return str(value)


def _str_list_attr(attrs: dict[str, Any], *names: str) -> list[str]:
    value = _jsonish_attr(attrs, *names)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _dict_list_attr(attrs: dict[str, Any], *names: str) -> list[dict[str, Any]]:
    value = _jsonish_attr(attrs, *names)
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _first_attr(attrs: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in attrs:
            return attrs[name]
    return None


def _has_llm_attrs(attrs: dict[str, Any]) -> bool:
    return any(
        key in attrs
        for key in {
            "llm.model_name",
            "gen_ai.request.model",
            "openai.model_name",
            "llm.token_count.prompt",
            "llm.token_count.completion",
            "llm.token_count.total",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
            "gen_ai.usage.total_tokens",
            "input_tokens",
            "output_tokens",
            "total_tokens",
        }
    )


def _has_tool_attrs(attrs: dict[str, Any]) -> bool:
    return any(
        key in attrs
        for key in {
            "tool.name",
            "tool_name",
            "tool.parameters",
            "tool.arguments",
            "tool_arguments",
            "tool.output",
            "tool_output",
        }
    )


def _has_memory_attrs(attrs: dict[str, Any]) -> bool:
    return any(
        key in attrs
        for key in {
            "memory.operation",
            "memory_operation",
            "retrieval.documents",
            "retrieved_documents",
            "retrieval.chunks",
            "retrieved_chunks",
        }
    )


def _has_http_attrs(attrs: dict[str, Any]) -> bool:
    return any(key.startswith("http.") or key in {"url.full", "http.url"} for key in attrs)


def _fallback_agent_id(attrs: dict[str, Any], config: SDKConfig, fallback_name: str) -> str:
    graph_name = _str_attr(attrs, "agentsre.langgraph.graph_name") or "unknown_graph"
    node_name = _str_attr(attrs, "agentsre.langgraph.node_name", "node.name", "langgraph.node.name") or fallback_name
    raw = "|".join([config.tenant_id, config.project_id, config.workflow_id, graph_name, node_name, fallback_name])
    return f"agent_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _fallback_tool_id(attrs: dict[str, Any], config: SDKConfig, tool_name: str, tool_type: str | None) -> str:
    graph_name = _str_attr(attrs, "agentsre.langgraph.graph_name") or "unknown_graph"
    raw = "|".join([config.tenant_id, config.project_id, config.workflow_id, graph_name, tool_name, tool_type or "Tool"])
    return f"tool_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _infer_agent_role(agent_name: str | None) -> str | None:
    lowered = (agent_name or "").lower()
    if "planner" in lowered:
        return "Planner"
    if "supervisor" in lowered:
        return "Supervisor"
    if "worker" in lowered:
        return "Worker"
    if lowered:
        return "Agent"
    return None


def _infer_tool_type(tool_name: str) -> str:
    lowered = tool_name.lower()
    if "api" in lowered or "http" in lowered or "request" in lowered:
        return "REST API"
    if "search" in lowered:
        return "Search"
    return "Tool"


