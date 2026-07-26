from __future__ import annotations

import json
import logging
import os
import threading
import functools
from dataclasses import dataclass
from importlib.util import find_spec
from importlib import import_module
from types import SimpleNamespace
from typing import Any, Callable

from opentelemetry import context, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode


_LOCK = threading.RLock()
_LISTENER: Any | None = None
_BRIDGE: "_CrewAISpanBridge | None" = None
_TRACER_PROVIDER: Any | None = None
_ORIGINAL_EMIT: Callable[..., Any] | None = None
_ORIGINAL_LLM_CALL: Callable[..., Any] | None = None
_EVENT_DISPATCH: dict[type[Any], Callable[[Any, Any], None]] = {}
logger = logging.getLogger(__name__)


_EVENT_MODULES = {
    "CrewKickoffStartedEvent": ("crewai.events.types.crew_events", "crewai.events.event_types"),
    "CrewKickoffCompletedEvent": ("crewai.events.types.crew_events", "crewai.events.event_types"),
    "CrewKickoffFailedEvent": ("crewai.events.types.crew_events", "crewai.events.event_types"),
    "AgentExecutionStartedEvent": ("crewai.events.types.agent_events", "crewai.events.event_types"),
    "AgentExecutionCompletedEvent": ("crewai.events.types.agent_events", "crewai.events.event_types"),
    "AgentExecutionErrorEvent": ("crewai.events.types.agent_events", "crewai.events.event_types"),
    "LiteAgentExecutionStartedEvent": ("crewai.events.types.agent_events", "crewai.events.event_types"),
    "LiteAgentExecutionCompletedEvent": ("crewai.events.types.agent_events", "crewai.events.event_types"),
    "LiteAgentExecutionErrorEvent": ("crewai.events.types.agent_events", "crewai.events.event_types"),
    "TaskStartedEvent": ("crewai.events.types.task_events", "crewai.events.event_types"),
    "TaskCompletedEvent": ("crewai.events.types.task_events", "crewai.events.event_types"),
    "TaskFailedEvent": ("crewai.events.types.task_events", "crewai.events.event_types"),
    "ToolUsageStartedEvent": ("crewai.events.types.tool_usage_events", "crewai.events.event_types"),
    "ToolUsageFinishedEvent": ("crewai.events.types.tool_usage_events", "crewai.events.event_types"),
    "ToolUsageErrorEvent": ("crewai.events.types.tool_usage_events", "crewai.events.event_types"),
    "ToolValidateInputErrorEvent": ("crewai.events.types.tool_usage_events",),
    "ToolExecutionErrorEvent": ("crewai.events.types.tool_usage_events",),
    "ToolSelectionErrorEvent": ("crewai.events.types.tool_usage_events",),
    "MCPToolExecutionStartedEvent": ("crewai.events.types.mcp_events", "crewai.events.event_types"),
    "MCPToolExecutionCompletedEvent": ("crewai.events.types.mcp_events", "crewai.events.event_types"),
    "MCPToolExecutionFailedEvent": ("crewai.events.types.mcp_events", "crewai.events.event_types"),
    "MCPConnectionStartedEvent": ("crewai.events.types.mcp_events", "crewai.events.event_types"),
    "MCPConnectionCompletedEvent": ("crewai.events.types.mcp_events", "crewai.events.event_types"),
    "MCPConnectionFailedEvent": ("crewai.events.types.mcp_events", "crewai.events.event_types"),
    "MCPConfigFetchFailedEvent": ("crewai.events.types.mcp_events",),
    "KnowledgeRetrievalStartedEvent": ("crewai.events.types.knowledge_events", "crewai.events.event_types"),
    "KnowledgeRetrievalCompletedEvent": ("crewai.events.types.knowledge_events", "crewai.events.event_types"),
    "KnowledgeQueryStartedEvent": ("crewai.events.types.knowledge_events", "crewai.events.event_types"),
    "KnowledgeQueryCompletedEvent": ("crewai.events.types.knowledge_events", "crewai.events.event_types"),
    "KnowledgeQueryFailedEvent": ("crewai.events.types.knowledge_events", "crewai.events.event_types"),
    "KnowledgeSearchQueryFailedEvent": ("crewai.events.types.knowledge_events", "crewai.events.event_types"),
    "MemoryQueryStartedEvent": ("crewai.events.types.memory_events", "crewai.events.event_types"),
    "MemoryQueryCompletedEvent": ("crewai.events.types.memory_events", "crewai.events.event_types"),
    "MemoryQueryFailedEvent": ("crewai.events.types.memory_events", "crewai.events.event_types"),
    "MemoryRetrievalStartedEvent": ("crewai.events.types.memory_events", "crewai.events.event_types"),
    "MemoryRetrievalCompletedEvent": ("crewai.events.types.memory_events", "crewai.events.event_types"),
    "MemoryRetrievalFailedEvent": ("crewai.events.types.memory_events",),
    "MemorySaveStartedEvent": ("crewai.events.types.memory_events", "crewai.events.event_types"),
    "MemorySaveCompletedEvent": ("crewai.events.types.memory_events", "crewai.events.event_types"),
    "MemorySaveFailedEvent": ("crewai.events.types.memory_events", "crewai.events.event_types"),
    "LLMCallStartedEvent": ("crewai.events.types.llm_events", "crewai.events.event_types"),
    "LLMCallCompletedEvent": ("crewai.events.types.llm_events", "crewai.events.event_types"),
    "LLMCallFailedEvent": ("crewai.events.types.llm_events", "crewai.events.event_types"),
    "LLMGuardrailStartedEvent": ("crewai.events.types.llm_guardrail_events", "crewai.events.event_types"),
    "LLMGuardrailCompletedEvent": ("crewai.events.types.llm_guardrail_events", "crewai.events.event_types"),
    "LLMGuardrailFailedEvent": ("crewai.events.types.llm_guardrail_events",),
    "AgentReasoningStartedEvent": ("crewai.events.types.reasoning_events", "crewai.events.event_types"),
    "AgentReasoningCompletedEvent": ("crewai.events.types.reasoning_events", "crewai.events.event_types"),
    "AgentReasoningFailedEvent": ("crewai.events.types.reasoning_events", "crewai.events.event_types"),
    "StepObservationStartedEvent": ("crewai.events.types.reasoning_events",),
    "StepObservationCompletedEvent": ("crewai.events.types.reasoning_events",),
    "StepObservationFailedEvent": ("crewai.events.types.reasoning_events",),
    "PlanRefinementEvent": ("crewai.events.types.reasoning_events",),
    "PlanReplanTriggeredEvent": ("crewai.events.types.reasoning_events",),
    "GoalAchievedEarlyEvent": ("crewai.events.types.reasoning_events",),
    "FlowStartedEvent": ("crewai.events.types.flow_events", "crewai.events.event_types"),
    "FlowFinishedEvent": ("crewai.events.types.flow_events", "crewai.events.event_types"),
    "FlowPausedEvent": ("crewai.events.types.flow_events",),
    "MethodExecutionStartedEvent": ("crewai.events.types.flow_events", "crewai.events.event_types"),
    "MethodExecutionFinishedEvent": ("crewai.events.types.flow_events", "crewai.events.event_types"),
    "MethodExecutionFailedEvent": ("crewai.events.types.flow_events", "crewai.events.event_types"),
    "MethodExecutionPausedEvent": ("crewai.events.types.flow_events",),
    "FlowInputRequestedEvent": ("crewai.events.types.flow_events",),
    "FlowInputReceivedEvent": ("crewai.events.types.flow_events",),
    "HumanFeedbackRequestedEvent": ("crewai.events.types.flow_events",),
    "HumanFeedbackReceivedEvent": ("crewai.events.types.flow_events",),
    "A2ADelegationStartedEvent": ("crewai.events.types.a2a_events",),
    "A2ADelegationCompletedEvent": ("crewai.events.types.a2a_events",),
    "A2AParallelDelegationStartedEvent": ("crewai.events.types.a2a_events",),
    "A2AParallelDelegationCompletedEvent": ("crewai.events.types.a2a_events",),
    "A2AConversationStartedEvent": ("crewai.events.types.a2a_events",),
    "A2AConversationCompletedEvent": ("crewai.events.types.a2a_events",),
    "A2AStreamingStartedEvent": ("crewai.events.types.a2a_events",),
    "A2AStreamingChunkEvent": ("crewai.events.types.a2a_events",),
    "A2APollingStartedEvent": ("crewai.events.types.a2a_events",),
    "A2APollingStatusEvent": ("crewai.events.types.a2a_events",),
    "A2AServerTaskStartedEvent": ("crewai.events.types.a2a_events",),
    "A2AServerTaskCompletedEvent": ("crewai.events.types.a2a_events",),
    "A2AServerTaskFailedEvent": ("crewai.events.types.a2a_events",),
    "A2AConnectionErrorEvent": ("crewai.events.types.a2a_events",),
    "A2AAuthenticationFailedEvent": ("crewai.events.types.a2a_events",),
}


@dataclass
class _OpenSpan:
    span: Span
    context_token: Any | None = None


@dataclass
class _CrewTaskContext:
    crew_key: str
    task_names: list[str]
    last_task_name: str | None = None
    last_task_key: tuple[str, str] | None = None


class _CrewAISpanBridge:
    def __init__(self, tracer_provider: Any | None = None) -> None:
        self.tracer_provider = tracer_provider
        self.open_spans: dict[tuple[str, str], _OpenSpan] = {}
        self.reasoning_step = 0
        self.crew_stack: list[_CrewTaskContext] = []

    def start_crew(self, source: Any, event: Any) -> None:
        attrs = _crew_attrs(source, event)
        self._start("crew", source, event, f"CrewAI Crew: {attrs['agentsre.agent_name']}", attrs)
        self.crew_stack.append(_CrewTaskContext(crew_key=_crew_context_key(source, event), task_names=_crew_task_names(source, event)))

    def finish_crew(self, source: Any, event: Any) -> None:
        self._finish("crew", source, event, output=_event_output(event))
        self._pop_crew_context(source, event)

    def fail_crew(self, source: Any, event: Any) -> None:
        self._finish("crew", source, event, error=_event_error(event), output=_event_output(event))
        self._pop_crew_context(source, event)

    def start_agent(self, source: Any, event: Any) -> None:
        attrs = _agent_attrs(source, event)
        self._start("agent", source, event, f"CrewAI Agent: {attrs['agentsre.agent_name']}", attrs)

    def finish_agent(self, source: Any, event: Any) -> None:
        self._finish("agent", source, event, output=_event_output(event))

    def fail_agent(self, source: Any, event: Any) -> None:
        self._finish("agent", source, event, error=_event_error(event), output=_event_output(event))

    def start_task(self, source: Any, event: Any) -> None:
        attrs = _task_attrs(source, event, self._next_step())
        self._apply_task_order_attrs(source, event, attrs)
        self._start("task", source, event, f"CrewAI Task: {attrs['node.name']}", attrs)

    def finish_task(self, source: Any, event: Any) -> None:
        self._finish("task", source, event, output=_event_output(event))

    def fail_task(self, source: Any, event: Any) -> None:
        self._finish("task", source, event, error=_event_error(event), output=_event_output(event))

    def start_tool(self, source: Any, event: Any) -> None:
        attrs = _tool_attrs(source, event)
        self._start("tool", source, event, f"CrewAI Tool: {attrs['tool.name']}", attrs)

    def finish_tool(self, source: Any, event: Any) -> None:
        self._finish("tool", source, event, output=_tool_event_output(event))

    def fail_tool(self, source: Any, event: Any) -> None:
        self._finish("tool", source, event, error=_event_error(event), output=_tool_event_output(event))

    def start_memory(self, source: Any, event: Any) -> None:
        attrs = _memory_attrs(source, event, "retrieve")
        self._start("memory", source, event, f"CrewAI Memory: {attrs['memory.operation']}", attrs)

    def finish_memory(self, source: Any, event: Any) -> None:
        self._finish("memory", source, event, output=_event_output(event), extra_attrs=_memory_result_attrs(event))

    def fail_memory(self, source: Any, event: Any) -> None:
        self._finish("memory", source, event, error=_event_error(event), output=_event_output(event))

    def start_llm(self, source: Any, event: Any) -> None:
        attrs = _llm_attrs(source, event)
        self._start("llm", source, event, f"CrewAI LLM: {attrs.get('llm.model_name') or 'call'}", attrs)

    def finish_llm(self, source: Any, event: Any) -> None:
        self._finish("llm", source, event, output=_event_output(event), extra_attrs=_llm_result_attrs(event))

    def fail_llm(self, source: Any, event: Any) -> None:
        self._finish("llm", source, event, error=_event_error(event), output=_event_output(event))

    def start_reasoning(self, source: Any, event: Any) -> None:
        attrs = _reasoning_attrs(source, event, self._next_step())
        self._start("reasoning", source, event, f"CrewAI Reasoning: {attrs['node.name']}", attrs)

    def finish_reasoning(self, source: Any, event: Any) -> None:
        self._finish("reasoning", source, event, output=_event_output(event), extra_attrs=_reasoning_result_attrs(event))

    def fail_reasoning(self, source: Any, event: Any) -> None:
        self._finish("reasoning", source, event, error=_event_error(event), output=_event_output(event))

    def start_flow(self, source: Any, event: Any) -> None:
        attrs = _flow_attrs(source, event, self._next_step())
        self._start("flow", source, event, f"CrewAI Flow: {attrs['node.name']}", attrs)

    def finish_flow(self, source: Any, event: Any) -> None:
        self._finish("flow", source, event, output=_event_output(event))

    def fail_flow(self, source: Any, event: Any) -> None:
        self._finish("flow", source, event, error=_event_error(event), output=_event_output(event))

    def _next_step(self) -> int:
        self.reasoning_step += 1
        return self.reasoning_step

    def _current_crew_context(self) -> _CrewTaskContext | None:
        return self.crew_stack[-1] if self.crew_stack else None

    def _pop_crew_context(self, source: Any, event: Any) -> None:
        key = _crew_context_key(source, event)
        for index in range(len(self.crew_stack) - 1, -1, -1):
            if self.crew_stack[index].crew_key == key:
                del self.crew_stack[index:]
                return
        if self.crew_stack:
            self.crew_stack.pop()

    def _apply_task_order_attrs(self, source: Any, event: Any, attrs: dict[str, Any]) -> None:
        context_state = self._current_crew_context()
        if context_state is None:
            return
        task_name = _str_value(attrs.get("node.name"))
        if not task_name:
            return
        task_key = _event_key("task", source, event)
        if task_name in context_state.task_names:
            index = context_state.task_names.index(task_name)
            if index > 0:
                attrs["previous_node"] = context_state.task_names[index - 1]
            if index + 1 < len(context_state.task_names):
                attrs["next_node"] = context_state.task_names[index + 1]
        elif context_state.last_task_name:
            attrs["previous_node"] = context_state.last_task_name
            if context_state.last_task_key in self.open_spans:
                self.open_spans[context_state.last_task_key].span.set_attribute("next_node", task_name)
        context_state.last_task_name = task_name
        context_state.last_task_key = task_key

    def _start(self, category: str, source: Any, event: Any, name: str, attrs: dict[str, Any]) -> None:
        key = _event_key(category, source, event)
        if key in self.open_spans:
            return
        span = self._tracer().start_span(name, kind=SpanKind.INTERNAL, context=self._parent_context())
        _set_attrs(span, attrs)
        context_token = None
        if category == "llm":
            context_token = context.attach(trace.set_span_in_context(span, context.get_current()))
        self.open_spans[key] = _OpenSpan(span=span, context_token=context_token)

    def _finish(
        self,
        category: str,
        source: Any,
        event: Any,
        *,
        error: str | None = None,
        output: Any = None,
        extra_attrs: dict[str, Any] | None = None,
    ) -> None:
        key = _event_key(category, source, event)
        open_span = self.open_spans.pop(key, None)
        if open_span is None:
            attrs = _fallback_attrs(category, source, event, self._next_step())
            name = _fallback_span_name(category, attrs)
            span = self._tracer().start_span(name, kind=SpanKind.INTERNAL, context=self._parent_context())
            open_span = _OpenSpan(span=span)
            _set_attrs(span, attrs)

        if extra_attrs:
            _set_attrs(open_span.span, extra_attrs)
        if output is not None:
            output_attr = _output_attr_name(category)
            if output_attr is not None:
                open_span.span.set_attribute(output_attr, _json_dumps(_small_jsonable(output)))
        if error:
            open_span.span.set_attribute("exception.message", error)
            open_span.span.set_attribute("tool.error", error)
            open_span.span.set_status(Status(StatusCode.ERROR, error))
        elif category == "tool":
            open_span.span.set_attribute("tool.status", "SUCCESS")

        if open_span.context_token is not None:
            context.detach(open_span.context_token)
        open_span.span.end()

    def _tracer(self) -> Any:
        if self.tracer_provider is not None:
            return self.tracer_provider.get_tracer(__name__)
        return trace.get_tracer(__name__)

    def _parent_context(self) -> Any:
        if not self.open_spans:
            return context.get_current()
        parent = next(reversed(self.open_spans.values())).span
        return trace.set_span_in_context(parent, context.get_current())


def instrument(tracer_provider: Any | None = None) -> dict[str, str]:
    global _BRIDGE, _EVENT_DISPATCH, _LISTENER, _ORIGINAL_EMIT, _TRACER_PROVIDER
    _TRACER_PROVIDER = tracer_provider
    try:
        import crewai.events as crewai_events

        event_bus = getattr(crewai_events, "crewai_event_bus")
    except Exception as exc:
        return {"name": "crewai", "status": "unavailable", "detail": str(exc)}

    with _LOCK:
        if _BRIDGE is None:
            _BRIDGE = _CrewAISpanBridge(tracer_provider)
        else:
            _BRIDGE.tracer_provider = tracer_provider

        resolved_events, missing_events = _resolve_event_classes(crewai_events)
        _EVENT_DISPATCH = _build_event_dispatch(_BRIDGE, resolved_events)

        if _ORIGINAL_EMIT is None:
            _ORIGINAL_EMIT = event_bus.emit

            def emit_with_agentsre(source: Any, event: Any) -> Any:
                _dispatch_event(source, event)
                return _ORIGINAL_EMIT(source, event)

            event_bus.emit = emit_with_agentsre
        _patch_crewai_llm_call(tracer_provider)

        detail = f"CrewAI event instrumentation enabled; registered={len(_EVENT_DISPATCH)} missing={len(missing_events)}"
        if _crewai_debug_enabled():
            logger.warning("AgentSRE CrewAI instrumentation: %s missing=%s", detail, missing_events)
        return {
            "name": "crewai",
            "status": "instrumented",
            "detail": detail,
            "registered_events": str(len(_EVENT_DISPATCH)),
            "missing_events": ",".join(missing_events),
        }


def _patch_crewai_llm_call(tracer_provider: Any | None) -> None:
    global _ORIGINAL_LLM_CALL
    if _module_available("litellm") or _module_available("openinference.instrumentation.litellm"):
        return
    try:
        from crewai import LLM
    except Exception:
        return
    original = getattr(LLM, "call", None)
    if original is None or getattr(original, "_agentsre_crewai_llm_wrapped", False):
        return

    _ORIGINAL_LLM_CALL = original

    @functools.wraps(original)
    def call_with_agentsre_usage(self: Any, *args: Any, **kwargs: Any) -> Any:
        tracer = tracer_provider.get_tracer(__name__) if tracer_provider is not None else trace.get_tracer(__name__)
        usage_callback = _CrewAIUsageCallback()
        patched_args, patched_kwargs = _inject_usage_callback(args, kwargs, usage_callback)
        model = _str_value(_first_present(self, "model"))
        with tracer.start_as_current_span(f"CrewAI Provider LLM: {_clean_model_name(model) or 'call'}", kind=SpanKind.INTERNAL) as span:
            _set_attrs(span, _crewai_provider_llm_attrs(self, patched_args, patched_kwargs))
            try:
                result = original(self, *patched_args, **patched_kwargs)
            except Exception as exc:
                message = f"{exc.__class__.__name__}: {exc}"
                span.set_attribute("exception.type", exc.__class__.__name__)
                span.set_attribute("exception.message", message)
                span.set_status(Status(StatusCode.ERROR, message))
                raise
            _set_attrs(span, usage_callback.attrs())
            if result is not None:
                span.set_attribute("output.value", _json_dumps(_small_jsonable(result)))
            if not usage_callback.has_usage:
                span.set_attribute("agentsre.drop_span", True)
            return result

    call_with_agentsre_usage._agentsre_crewai_llm_wrapped = True
    setattr(LLM, "call", call_with_agentsre_usage)


def _module_available(name: str) -> bool:
    try:
        return find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


class _CrewAIUsageCallback:
    def __init__(self) -> None:
        self.usage: Any = None
        self.has_usage = False

    def log_success_event(self, kwargs: Any = None, response_obj: Any = None, start_time: Any = None, end_time: Any = None) -> None:
        usage = _nested_first(response_obj, "usage", "token_usage")
        if usage is not None:
            self.usage = usage
            self.has_usage = True

    def attrs(self) -> dict[str, Any]:
        if self.usage is None:
            return {}
        attrs: dict[str, Any] = {}
        for attr_name, names in {
            "input_tokens": ("prompt_tokens", "input_tokens"),
            "output_tokens": ("completion_tokens", "output_tokens"),
            "total_tokens": ("total_tokens",),
        }.items():
            value = _nested_first(self.usage, *names)
            if value is not None:
                attrs[attr_name] = _first_scalar(value)
        return attrs


def _inject_usage_callback(args: tuple[Any, ...], kwargs: dict[str, Any], callback: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
    patched_args = list(args)
    patched_kwargs = dict(kwargs)
    if len(patched_args) >= 3:
        callbacks = patched_args[2]
        callbacks = list(callbacks) if callbacks else []
        callbacks.append(callback)
        patched_args[2] = callbacks
    else:
        callbacks = patched_kwargs.get("callbacks")
        callbacks = list(callbacks) if callbacks else []
        callbacks.append(callback)
        patched_kwargs["callbacks"] = callbacks
    return tuple(patched_args), patched_kwargs


def _crewai_provider_llm_attrs(llm: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    model = _str_value(_first_present(llm, "model"))
    messages = kwargs.get("messages") if "messages" in kwargs else args[0] if args else None
    return {
        "openinference.span.kind": "LLM",
        "agentsre.crewai.provider_llm": True,
        "llm.provider": _provider_from_model(model),
        "llm.model_name": _clean_model_name(model),
        "input.value": _json_dumps(_small_jsonable(messages)),
        "temperature": _float_value(_first_present(llm, "temperature")),
        "max_tokens": _int_value(_first_present(llm, "max_tokens")),
    }


def _register(events_module: Any, event_bus: Any, event_name: str, handler: Callable[[Any, Any], None]) -> None:
    event_cls = getattr(events_module, event_name, None)
    if event_cls is None:
        return

    @event_bus.on(event_cls)
    def on_event(source: Any, event: Any, _handler: Callable[[Any, Any], None] = handler) -> None:
        try:
            _handler(source, event)
        except Exception:
            logger.debug("AgentSRE CrewAI event handler failed for %s", event_name, exc_info=True)


def _resolve_event_classes(events_module: Any) -> tuple[dict[str, type[Any]], list[str]]:
    resolved: dict[str, type[Any]] = {}
    missing: list[str] = []
    for event_name, module_names in _EVENT_MODULES.items():
        event_cls = getattr(events_module, event_name, None)
        if event_cls is None:
            event_cls = _import_event_class(event_name, module_names)
        if event_cls is None:
            missing.append(event_name)
            continue
        resolved[event_name] = event_cls
    return resolved, missing


def _import_event_class(event_name: str, module_names: tuple[str, ...]) -> type[Any] | None:
    for module_name in module_names:
        try:
            module = import_module(module_name)
            event_cls = getattr(module, event_name, None)
        except Exception:
            event_cls = None
        if event_cls is not None:
            return event_cls
    return None


def _build_event_dispatch(bridge: _CrewAISpanBridge, events: dict[str, type[Any]]) -> dict[type[Any], Callable[[Any, Any], None]]:
    dispatch: dict[type[Any], Callable[[Any, Any], None]] = {}
    for event_name, handler in _event_handlers(bridge).items():
        event_cls = events.get(event_name)
        if event_cls is not None:
            dispatch[event_cls] = handler
    return dispatch


def _event_handlers(bridge: _CrewAISpanBridge) -> dict[str, Callable[[Any, Any], None]]:
    return {
        "CrewKickoffStartedEvent": bridge.start_crew,
        "CrewKickoffCompletedEvent": bridge.finish_crew,
        "CrewKickoffFailedEvent": bridge.fail_crew,
        "AgentExecutionStartedEvent": bridge.start_agent,
        "AgentExecutionCompletedEvent": bridge.finish_agent,
        "AgentExecutionErrorEvent": bridge.fail_agent,
        "LiteAgentExecutionStartedEvent": bridge.start_agent,
        "LiteAgentExecutionCompletedEvent": bridge.finish_agent,
        "LiteAgentExecutionErrorEvent": bridge.fail_agent,
        "TaskStartedEvent": bridge.start_task,
        "TaskCompletedEvent": bridge.finish_task,
        "TaskFailedEvent": bridge.fail_task,
        "ToolUsageStartedEvent": bridge.start_tool,
        "ToolUsageFinishedEvent": bridge.finish_tool,
        "ToolUsageErrorEvent": bridge.fail_tool,
        "ToolValidateInputErrorEvent": bridge.fail_tool,
        "ToolExecutionErrorEvent": bridge.fail_tool,
        "ToolSelectionErrorEvent": bridge.fail_tool,
        "MCPToolExecutionStartedEvent": bridge.start_tool,
        "MCPToolExecutionCompletedEvent": bridge.finish_tool,
        "MCPToolExecutionFailedEvent": bridge.fail_tool,
        "MCPConnectionStartedEvent": bridge.start_flow,
        "MCPConnectionCompletedEvent": bridge.finish_flow,
        "MCPConnectionFailedEvent": bridge.fail_flow,
        "MCPConfigFetchFailedEvent": bridge.fail_flow,
        "KnowledgeRetrievalStartedEvent": bridge.start_memory,
        "KnowledgeRetrievalCompletedEvent": bridge.finish_memory,
        "KnowledgeQueryStartedEvent": bridge.start_memory,
        "KnowledgeQueryCompletedEvent": bridge.finish_memory,
        "KnowledgeQueryFailedEvent": bridge.fail_memory,
        "KnowledgeSearchQueryFailedEvent": bridge.fail_memory,
        "MemoryQueryStartedEvent": bridge.start_memory,
        "MemoryQueryCompletedEvent": bridge.finish_memory,
        "MemoryQueryFailedEvent": bridge.fail_memory,
        "MemoryRetrievalStartedEvent": bridge.start_memory,
        "MemoryRetrievalCompletedEvent": bridge.finish_memory,
        "MemoryRetrievalFailedEvent": bridge.fail_memory,
        "MemorySaveStartedEvent": bridge.start_memory,
        "MemorySaveCompletedEvent": bridge.finish_memory,
        "MemorySaveFailedEvent": bridge.fail_memory,
        "LLMCallStartedEvent": bridge.start_llm,
        "LLMCallCompletedEvent": bridge.finish_llm,
        "LLMCallFailedEvent": bridge.fail_llm,
        "LLMGuardrailStartedEvent": bridge.start_reasoning,
        "LLMGuardrailCompletedEvent": bridge.finish_reasoning,
        "LLMGuardrailFailedEvent": bridge.fail_reasoning,
        "AgentReasoningStartedEvent": bridge.start_reasoning,
        "AgentReasoningCompletedEvent": bridge.finish_reasoning,
        "AgentReasoningFailedEvent": bridge.fail_reasoning,
        "StepObservationStartedEvent": bridge.start_reasoning,
        "StepObservationCompletedEvent": bridge.finish_reasoning,
        "StepObservationFailedEvent": bridge.fail_reasoning,
        "PlanRefinementEvent": bridge.finish_reasoning,
        "PlanReplanTriggeredEvent": bridge.finish_reasoning,
        "GoalAchievedEarlyEvent": bridge.finish_reasoning,
        "FlowStartedEvent": bridge.start_flow,
        "FlowFinishedEvent": bridge.finish_flow,
        "FlowPausedEvent": bridge.finish_flow,
        "MethodExecutionStartedEvent": bridge.start_flow,
        "MethodExecutionFinishedEvent": bridge.finish_flow,
        "MethodExecutionFailedEvent": bridge.fail_flow,
        "MethodExecutionPausedEvent": bridge.finish_flow,
        "FlowInputRequestedEvent": bridge.start_flow,
        "FlowInputReceivedEvent": bridge.finish_flow,
        "HumanFeedbackRequestedEvent": bridge.start_flow,
        "HumanFeedbackReceivedEvent": bridge.finish_flow,
        "A2ADelegationStartedEvent": bridge.start_flow,
        "A2ADelegationCompletedEvent": bridge.finish_flow,
        "A2AParallelDelegationStartedEvent": bridge.start_flow,
        "A2AParallelDelegationCompletedEvent": bridge.finish_flow,
        "A2AConversationStartedEvent": bridge.start_flow,
        "A2AConversationCompletedEvent": bridge.finish_flow,
        "A2AStreamingStartedEvent": bridge.start_flow,
        "A2AStreamingChunkEvent": bridge.finish_flow,
        "A2APollingStartedEvent": bridge.start_flow,
        "A2APollingStatusEvent": bridge.finish_flow,
        "A2AServerTaskStartedEvent": bridge.start_flow,
        "A2AServerTaskCompletedEvent": bridge.finish_flow,
        "A2AServerTaskFailedEvent": bridge.fail_flow,
        "A2AConnectionErrorEvent": bridge.fail_flow,
        "A2AAuthenticationFailedEvent": bridge.fail_flow,
    }


def _dispatch_event(source: Any, event: Any) -> None:
    handler = _EVENT_DISPATCH.get(type(event))
    if handler is None:
        return
    try:
        handler(source, event)
    except Exception:
        if _crewai_debug_enabled():
            logger.exception("AgentSRE CrewAI event handler failed for %s", type(event).__name__)
        else:
            logger.debug("AgentSRE CrewAI event handler failed for %s", type(event).__name__, exc_info=True)


def _crewai_debug_enabled() -> bool:
    return os.getenv("AGENTSRE_CREWAI_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _crew_attrs(source: Any, event: Any) -> dict[str, Any]:
    crew = _first_present(event, "crew", "crew_instance") or source
    crew_name = _str_value(_first_present(event, "crew_name", "name") or _first_present(crew, "name", "id") or crew.__class__.__name__)
    return {
        "agentsre.span_kind": "AGENT",
        "agentsre.node_classification": "agent",
        "agentsre.agent_name": crew_name,
        "agentsre.agent_role": "Crew",
        "agentsre.agent_type": "CrewAI.Crew",
        "node.name": crew_name,
        "decision.type": "CrewAI Crew Execution",
        "agentsre.crewai.crew_name": crew_name,
        "agentsre.crewai.process": _str_value(_first_present(crew, "process")),
        "agentsre.crewai.registered_agents": _json_dumps(_crew_agents(crew)),
        "agentsre.crewai.registered_tools": _json_dumps(_crew_tools(crew)),
    }


def _agent_attrs(source: Any, event: Any) -> dict[str, Any]:
    agent = _first_present(event, "agent", "agent_info") or source
    role = _str_value(_first_present(agent, "role", "name", "id") or _first_present(event, "agent_role", "role") or "CrewAI Agent")
    return {
        "agentsre.span_kind": "AGENT",
        "agentsre.node_classification": "agent",
        "agentsre.agent_name": role,
        "agentsre.agent_role": role,
        "agentsre.agent_type": "CrewAI.Agent",
        "agent.id": _str_value(_first_present(agent, "id", "key")),
        "node.name": role,
        "decision.type": "CrewAI Agent Execution",
        "agentsre.crewai.agent_goal": _str_value(_first_present(agent, "goal")),
        "agentsre.crewai.task_id": _str_value(_first_present(event, "task_id")),
    }


def _task_attrs(source: Any, event: Any, step: int) -> dict[str, Any]:
    task = _first_present(event, "task") or source
    name = _task_name(task, event)
    agent = _first_present(task, "agent")
    return {
        "agentsre.span_kind": "REASONING",
        "node.name": name,
        "reasoning.step": step,
        "decision.type": "CrewAI Task Execution",
        "agentsre.crewai.task_id": _str_value(_first_present(task, "id", "key") or _first_present(event, "task_id")),
        "agentsre.crewai.task_description": _str_value(_first_present(task, "description")),
        "agentsre.crewai.expected_output": _str_value(_first_present(task, "expected_output")),
        "agentsre.agent_name": _str_value(_first_present(agent, "role", "name")),
    }


def _tool_attrs(source: Any, event: Any) -> dict[str, Any]:
    tool = _first_present(event, "tool") or source
    name = _str_value(_first_present(event, "tool_name", "name") or _first_present(tool, "name") or tool.__class__.__name__)
    explicit_type = _clean_tool_type(_str_value(_first_present(event, "tool_type", "type")))
    attrs = {
        "agentsre.span_kind": "TOOL",
        "tool.name": name,
        "tool.type": explicit_type or _infer_tool_type(name),
        "tool.description": _str_value(_first_present(tool, "description") or _first_present(event, "description")),
        "tool.arguments": _json_dumps(_small_jsonable(_first_present(event, "tool_args", "arguments", "input", "inputs"))),
    }
    if _event_error(event):
        attrs["tool.status"] = "ERROR"
    return attrs


def _memory_attrs(source: Any, event: Any, operation: str) -> dict[str, Any]:
    query = _first_present(event, "query", "search_query", "value", "task_id") or _first_present(source, "query")
    return {
        "agentsre.span_kind": "MEMORY",
        "memory.operation": _memory_operation(event, operation),
        "memory.key": _str_value(query),
        "vector_store": _str_value(_first_present(event, "storage", "store", "provider", "vector_store")) or "CrewAI",
        "retrieval.score": _float_value(_first_present(event, "score", "score_threshold")),
    }


def _llm_attrs(source: Any, event: Any) -> dict[str, Any]:
    model = _str_value(_first_present(event, "model", "model_name", "llm_model"))
    return {
        "agentsre.span_kind": "LLM",
        "llm.provider": _str_value(_first_present(event, "provider", "llm_provider")) or _provider_from_model(model),
        "llm.model_name": _clean_model_name(model),
        "input.value": _json_dumps(_small_jsonable(_first_present(event, "messages", "prompt", "input"))),
        "temperature": _float_value(_first_present(event, "temperature")),
        "max_tokens": _int_value(_first_present(event, "max_tokens")),
        "agentsre.crewai.llm_event": True,
    }


def _reasoning_attrs(source: Any, event: Any, step: int) -> dict[str, Any]:
    agent_role = _str_value(_first_present(event, "agent_role", "role") or _first_present(source, "role", "name"))
    node_name = agent_role or _str_value(_first_present(event, "task_id")) or "CrewAI Reasoning"
    return {
        "agentsre.span_kind": "REASONING",
        "node.name": node_name,
        "reasoning.step": step,
        "decision.type": "CrewAI Agent Reasoning",
        "agentsre.crewai.task_id": _str_value(_first_present(event, "task_id")),
        "agentsre.crewai.attempt": _int_value(_first_present(event, "attempt", "iteration")),
    }


def _flow_attrs(source: Any, event: Any, step: int) -> dict[str, Any]:
    name = _str_value(_first_present(event, "flow_name", "method_name", "name") or source.__class__.__name__)
    return {
        "agentsre.span_kind": "REASONING",
        "node.name": name,
        "reasoning.step": step,
        "decision.type": "CrewAI Flow Execution",
        "agentsre.crewai.flow_id": _str_value(_first_present(event, "flow_id")),
    }


def _memory_result_attrs(event: Any) -> dict[str, Any]:
    results = _first_present(event, "results", "memory_content", "content", "output")
    attrs: dict[str, Any] = {}
    if results is not None:
        attrs["retrieval.documents"] = _json_dumps(_small_jsonable(results))
        attrs["retrieval.chunks"] = _json_dumps(_small_jsonable(results))
    execution_time = _first_present(event, "query_execution_time", "retrieval_execution_time", "save_execution_time")
    if execution_time is not None:
        attrs["agentsre.crewai.execution_time"] = _float_value(execution_time)
    return attrs


def _llm_result_attrs(event: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    output = _first_present(event, "response", "output", "completion", "result", "raw_response")
    if output is not None:
        attrs["output.value"] = _json_dumps(_small_jsonable(output))
    for attr_name, event_names in {
        "finish_reason": ("finish_reason", "finish_reasons", "stop_reason"),
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "total_tokens": ("total_tokens",),
    }.items():
        value = _first_present(event, *event_names)
        if value is None:
            value = _nested_first(output, *event_names)
        if value is None and attr_name in {"input_tokens", "output_tokens", "total_tokens"}:
            usage = _first_present(event, "usage", "token_usage") or _nested_first(output, "usage", "token_usage")
            value = _nested_first(usage, *event_names)
        if value is not None:
            attrs[attr_name] = _first_scalar(value)
    return attrs


def _reasoning_result_attrs(event: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    plan = _first_present(event, "plan", "output")
    if plan is not None:
        attrs["agentsre.crewai.reasoning_plan"] = _json_dumps(_small_jsonable(plan))
    ready = _first_present(event, "ready", "ready_to_proceed")
    if ready is not None:
        attrs["agentsre.crewai.ready"] = bool(ready)
    return attrs


def _fallback_attrs(category: str, source: Any, event: Any, step: int) -> dict[str, Any]:
    if category == "crew":
        return _crew_attrs(source, event)
    if category == "agent":
        return _agent_attrs(source, event)
    if category == "task":
        return _task_attrs(source, event, step)
    if category == "tool":
        return _tool_attrs(source, event)
    if category == "memory":
        return _memory_attrs(source, event, "retrieve")
    if category == "llm":
        return _llm_attrs(source, event)
    if category == "flow":
        return _flow_attrs(source, event, step)
    return _reasoning_attrs(source, event, step)


def _fallback_span_name(category: str, attrs: dict[str, Any]) -> str:
    if category == "crew":
        return f"CrewAI Crew: {attrs.get('agentsre.agent_name') or 'Crew'}"
    if category == "agent":
        return f"CrewAI Agent: {attrs.get('agentsre.agent_name') or 'Agent'}"
    if category == "task":
        return f"CrewAI Task: {attrs.get('node.name') or 'Task'}"
    if category == "tool":
        return f"CrewAI Tool: {attrs.get('tool.name') or 'Tool'}"
    if category == "memory":
        return f"CrewAI Memory: {attrs.get('memory.operation') or 'memory'}"
    if category == "llm":
        return f"CrewAI LLM: {attrs.get('llm.model_name') or 'call'}"
    return f"CrewAI Reasoning: {attrs.get('node.name') or category}"


def _event_key(category: str, source: Any, event: Any) -> tuple[str, str]:
    if category == "tool":
        tool_name = _str_value(_first_present(event, "tool_name", "name") or _first_present(source, "name"))
        tool_args = _small_jsonable(_first_present(event, "tool_args", "arguments", "input", "inputs"))
        for name in ["tool_call_id", "call_id", "run_id", "event_id", "execution_id"]:
            value = _first_present(event, name)
            if value is not None:
                return category, str(value)
        task_id = _first_present(event, "task_id")
        if task_id is not None and tool_name:
            return category, _json_dumps({"task_id": str(task_id), "tool_name": tool_name, "tool_args": tool_args})
        if tool_name:
            return category, _json_dumps({"tool_name": tool_name, "tool_args": tool_args})
    for name in [
        "event_id",
        "execution_id",
        "task_id",
        "context_id",
        "message_id",
        "agent_id",
        "tool_call_id",
        "call_id",
        "run_id",
        "crew_id",
        "flow_id",
        "server_name",
        "endpoint",
    ]:
        value = _first_present(event, name)
        if value is not None:
            return category, str(value)
    subject = _first_present(event, "task", "agent", "tool", "crew") or source
    return category, str(id(subject))


def _crew_agents(crew: Any) -> list[dict[str, Any]]:
    agents = _as_list(_first_present(crew, "agents"))
    items = []
    for agent in agents:
        role = _str_value(_first_present(agent, "role", "name", "id"))
        if not role:
            continue
        items.append(
            {
                "agent_name": role,
                "agent_role": role,
                "agent_type": "CrewAI.Agent",
                "agent_id": _str_value(_first_present(agent, "id", "key")),
            }
        )
    return items


def _crew_tools(crew: Any) -> list[dict[str, Any]]:
    tools: dict[str, dict[str, Any]] = {}
    for agent in _as_list(_first_present(crew, "agents")):
        for tool in _as_list(_first_present(agent, "tools")):
            name = _str_value(_first_present(tool, "name") or tool.__class__.__name__)
            if not name:
                continue
            tools[name.lower()] = {
                "tool_name": name,
                "tool_description": _str_value(_first_present(tool, "description")),
                "tool_type": _infer_tool_type(name),
                "tool_arguments": _tool_schema(_first_present(tool, "args", "args_schema")),
            }
    for task in _as_list(_first_present(crew, "tasks")):
        for tool in _as_list(_first_present(task, "tools")):
            name = _str_value(_first_present(tool, "name") or tool.__class__.__name__)
            if name and name.lower() not in tools:
                tools[name.lower()] = {
                    "tool_name": name,
                    "tool_description": _str_value(_first_present(tool, "description")),
                    "tool_type": _infer_tool_type(name),
                    "tool_arguments": _tool_schema(_first_present(tool, "args", "args_schema")),
                }
    return list(tools.values())


def _tool_schema(value: Any) -> Any:
    if value is None:
        return None
    schema = _model_json_schema(value)
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            return {
                str(name): _schema_property_summary(property_schema)
                for name, property_schema in properties.items()
            }
        return _small_jsonable(schema)
    return _small_jsonable(value)


def _model_json_schema(value: Any) -> Any:
    for candidate in [value, value.__class__ if value is not None else None]:
        if candidate is None:
            continue
        for method_name in ["model_json_schema", "schema"]:
            method = getattr(candidate, method_name, None)
            if callable(method):
                try:
                    return method()
                except Exception:
                    continue
    return None


def _schema_property_summary(value: Any) -> Any:
    if not isinstance(value, dict):
        return _small_jsonable(value)
    summary: dict[str, Any] = {}
    for key in ["type", "title", "description", "default"]:
        if key in value:
            summary[key] = _small_jsonable(value[key])
    if "anyOf" in value:
        summary["anyOf"] = _small_jsonable(value["anyOf"])
    if "items" in value:
        summary["items"] = _small_jsonable(value["items"])
    return summary or _small_jsonable(value)


def _task_name(task: Any, event: Any) -> str:
    value = _first_present(event, "task_name", "name") or _first_present(task, "name")
    if value:
        return _short_label(_str_value(value) or "Task")
    agent = _first_present(task, "agent")
    agent_role = _str_value(_first_present(agent, "role", "name"))
    description = _str_value(_first_present(task, "description") or _first_present(event, "description"))
    if agent_role and description:
        return _short_label(f"{agent_role}: {description}")
    if description:
        return _short_label(description)
    task_id = _str_value(_first_present(task, "id", "key") or _first_present(event, "task_id"))
    return _short_label(task_id or "Task")


def _crew_context_key(source: Any, event: Any) -> str:
    crew = _first_present(event, "crew", "crew_instance") or source
    return str(id(crew))


def _crew_task_names(source: Any, event: Any) -> list[str]:
    crew = _first_present(event, "crew", "crew_instance") or source
    names: list[str] = []
    for task in _as_list(_first_present(crew, "tasks")):
        name = _task_name(task, SimpleNamespace(task=task))
        if name:
            names.append(name)
    return names


def _short_label(value: str, max_chars: int = 120) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _clean_tool_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    lowered = normalized.lower().replace("-", "_")
    if lowered in {
        "tool_usage_started",
        "tool_usage_finished",
        "tool_usage_error",
        "tool_validate_input_error",
        "tool_execution_error",
        "tool_selection_error",
        "mcp_tool_execution_started",
        "mcp_tool_execution_completed",
        "mcp_tool_execution_failed",
    }:
        return None
    return normalized


def _event_output(event: Any) -> Any:
    return _first_present(event, "output", "result", "response", "completion", "memory_content", "results")


def _tool_event_output(event: Any) -> Any:
    output = _first_present(event, "output", "result", "response", "tool_output", "tool_result")
    if output is not None:
        return output
    dumped = _model_dump(event)
    if isinstance(dumped, dict):
        return _nested_first(dumped, "output", "result", "response", "tool_output", "tool_result")
    return None


def _event_error(event: Any) -> str | None:
    value = _first_present(event, "error", "error_message", "message", "exception")
    return _str_value(value) if value else None


def _output_attr_name(category: str) -> str | None:
    if category == "tool":
        return "tool.output"
    if category == "llm":
        return "output.value"
    if category == "memory":
        return "retrieval.documents"
    return "output.value"


def _memory_operation(event: Any, fallback: str) -> str:
    name = event.__class__.__name__.lower()
    if "save" in name:
        return "save"
    if "query" in name:
        return "query"
    if "retrieval" in name or "knowledge" in name:
        return "retrieve"
    return fallback


def _first_present(obj: Any, *names: str) -> Any:
    for name in names:
        if obj is None:
            continue
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _model_dump(obj: Any) -> Any:
    for method_name in ["model_dump", "dict"]:
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                return method()
            except Exception:
                continue
    return None


def _nested_first(obj: Any, *names: str, depth: int = 0) -> Any:
    if obj is None or depth > 6:
        return None
    direct = _first_present(obj, *names)
    if direct is not None:
        return direct
    if isinstance(obj, dict):
        values = obj.values()
    elif isinstance(obj, (list, tuple)):
        values = obj
    elif callable(getattr(obj, "model_dump", None)):
        try:
            return _nested_first(obj.model_dump(), *names, depth=depth + 1)
        except Exception:
            return None
    elif callable(getattr(obj, "dict", None)):
        try:
            return _nested_first(obj.dict(), *names, depth=depth + 1)
        except Exception:
            return None
    else:
        return None
    for item in values:
        found = _nested_first(item, *names, depth=depth + 1)
        if found is not None:
            return found
    return None


def _first_scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return _first_scalar(value[0]) if value else None
    return _str_value(value)


def _provider_from_model(model: str | None) -> str | None:
    if not model:
        return None
    if "/" in model:
        provider, _ = model.split("/", 1)
        return provider or None
    lowered = model.lower()
    if lowered.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    return None


def _clean_model_name(model: str | None) -> str | None:
    if not model:
        return None
    if "/" in model:
        _, model_name = model.split("/", 1)
        return model_name or model
    return model


def _set_attrs(span: Span, attrs: dict[str, Any]) -> None:
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, _json_dumps(_small_jsonable(value)))


def _small_jsonable(value: Any, *, max_items: int = 25, max_chars: int = 8000) -> Any:
    if isinstance(value, dict):
        return {str(key): _small_jsonable(item, max_items=max_items, max_chars=max_chars) for key, item in list(value.items())[:max_items]}
    if isinstance(value, (list, tuple, set)):
        return [_small_jsonable(item, max_items=max_items, max_chars=max_chars) for item in list(value)[:max_items]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and len(value) > max_chars:
            return value[:max_chars]
        return value
    return str(value)[:max_chars]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=True, sort_keys=True)


def _str_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _infer_tool_type(tool_name: str) -> str:
    lowered = tool_name.lower()
    if "mcp" in lowered:
        return "MCP"
    if "api" in lowered or "http" in lowered or "request" in lowered:
        return "REST API"
    if "search" in lowered:
        return "Search"
    if "memory" in lowered or "knowledge" in lowered:
        return "Memory"
    return "Tool"


__all__ = ["instrument"]
