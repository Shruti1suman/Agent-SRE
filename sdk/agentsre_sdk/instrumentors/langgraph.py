from __future__ import annotations

import asyncio
import functools
import inspect
import json
import types
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode


_RUN_STATE: ContextVar["LangGraphRunState | None"] = ContextVar("agentsre_langgraph_run_state", default=None)
_TRACER_PROVIDER: Any | None = None


@dataclass
class LangGraphRunState:
    graph_name: str | None
    visits: dict[str, int] = field(default_factory=dict)
    last_node: str | None = None
    step: int = 0
    cycle_nodes: set[str] = field(default_factory=set)
    conditional_edges: list[dict[str, Any]] = field(default_factory=list)
    interrupts: list[str] = field(default_factory=list)


def instrument(tracer_provider: Any | None = None) -> dict[str, str]:
    global _TRACER_PROVIDER
    if tracer_provider is not None:
        _TRACER_PROVIDER = tracer_provider
    try:
        from langgraph.graph import StateGraph
    except ImportError as exc:
        return {"name": "langgraph", "status": "unavailable", "detail": str(exc)}

    if getattr(StateGraph, "_agentsre_instrumented", False):
        return {"name": "langgraph", "status": "instrumented", "detail": "LangGraph instrumentation already enabled"}

    StateGraph._agentsre_original_add_node = StateGraph.add_node
    StateGraph._agentsre_original_add_edge = StateGraph.add_edge
    StateGraph._agentsre_original_add_conditional_edges = StateGraph.add_conditional_edges
    StateGraph._agentsre_original_compile = StateGraph.compile
    StateGraph.add_node = _patched_add_node
    StateGraph.add_edge = _patched_add_edge
    StateGraph.add_conditional_edges = _patched_add_conditional_edges
    StateGraph.compile = _patched_compile
    StateGraph._agentsre_instrumented = True
    StateGraph._agentsre_tracer_provider = tracer_provider
    return {"name": "langgraph", "status": "instrumented", "detail": "LangGraph graph and node instrumentation enabled"}


def _patched_add_node(self: Any, node: Any, action: Any | None = None, *args: Any, **kwargs: Any) -> Any:
    original = self.__class__._agentsre_original_add_node
    node_name = _node_name(node, action)
    original_action = action if action is not None else node if callable(node) and not isinstance(node, str) else None
    classification = _classify_node(node_name, original_action)
    _ensure_build_metadata(self)["registered_nodes"][node_name] = _registered_node_metadata(node_name, classification, original_action)
    if action is not None:
        action = _wrap_node_action(node_name, action)
    elif callable(node) and not isinstance(node, str):
        node = _wrap_node_action(node_name, node)
    result = original(self, node, action, *args, **kwargs)
    _ensure_build_metadata(self)["nodes"].add(node_name)
    return result


def _patched_add_edge(self: Any, start_key: Any, end_key: str) -> Any:
    original = self.__class__._agentsre_original_add_edge
    result = original(self, start_key, end_key)
    starts = start_key if isinstance(start_key, list) else [start_key]
    for start in starts:
        _ensure_build_metadata(self)["edges"].append({"source": str(start), "target": str(end_key), "conditional": False})
    return result


def _patched_add_conditional_edges(self: Any, source: str, path: Any, path_map: Any = None) -> Any:
    original = self.__class__._agentsre_original_add_conditional_edges
    wrapped_path = _wrap_conditional_path(source, path, path_map)
    result = original(self, source, wrapped_path, path_map)
    _ensure_build_metadata(self)["conditional_edges"].append(
        {"source": str(source), "path": _callable_name(path), "path_map": _jsonable_path_map(path_map)}
    )
    return result


def _patched_compile(self: Any, *args: Any, **kwargs: Any) -> Any:
    original = self.__class__._agentsre_original_compile
    compiled = original(self, *args, **kwargs)
    graph_name = kwargs.get("name")
    graph_metadata = _graph_metadata(self, graph_name, args, kwargs)
    _wrap_compiled_graph(compiled, graph_metadata)
    return compiled


def _wrap_compiled_graph(compiled: Any, graph_metadata: dict[str, Any]) -> None:
    if getattr(compiled, "_agentsre_wrapped", False):
        return
    if hasattr(compiled, "invoke"):
        compiled._agentsre_original_invoke = compiled.invoke
        compiled.invoke = types.MethodType(_make_invoke_wrapper(compiled.invoke, graph_metadata), compiled)
    if hasattr(compiled, "ainvoke"):
        compiled._agentsre_original_ainvoke = compiled.ainvoke
        compiled.ainvoke = types.MethodType(_make_ainvoke_wrapper(compiled.ainvoke, graph_metadata), compiled)
    if hasattr(compiled, "stream"):
        compiled._agentsre_original_stream = compiled.stream
        compiled.stream = types.MethodType(_make_stream_wrapper(compiled.stream, graph_metadata), compiled)
    if hasattr(compiled, "astream"):
        compiled._agentsre_original_astream = compiled.astream
        compiled.astream = types.MethodType(_make_astream_wrapper(compiled.astream, graph_metadata), compiled)
    compiled._agentsre_graph_metadata = graph_metadata
    compiled._agentsre_wrapped = True


def _make_invoke_wrapper(original: Callable[..., Any], graph_metadata: dict[str, Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        with _graph_span(graph_metadata, kwargs) as span:
            state = LangGraphRunState(graph_name=graph_metadata.get("graph_name"))
            token = _RUN_STATE.set(state)
            try:
                result = original(*args, **kwargs)
                _capture_interrupts_from_output(state, result)
                _finish_graph_span(span, graph_metadata, state)
                return result
            except Exception as exc:
                _record_error(span, exc)
                raise
            finally:
                _RUN_STATE.reset(token)

    return wrapper


def _make_ainvoke_wrapper(original: Callable[..., Awaitable[Any]], graph_metadata: dict[str, Any]) -> Callable[..., Awaitable[Any]]:
    @functools.wraps(original)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        with _graph_span(graph_metadata, kwargs) as span:
            state = LangGraphRunState(graph_name=graph_metadata.get("graph_name"))
            token = _RUN_STATE.set(state)
            try:
                result = await original(*args, **kwargs)
                _capture_interrupts_from_output(state, result)
                _finish_graph_span(span, graph_metadata, state)
                return result
            except Exception as exc:
                _record_error(span, exc)
                raise
            finally:
                _RUN_STATE.reset(token)

    return wrapper


def _make_stream_wrapper(original: Callable[..., Iterator[Any]], graph_metadata: dict[str, Any]) -> Callable[..., Iterator[Any]]:
    @functools.wraps(original)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Iterator[Any]:
        if _RUN_STATE.get() is not None:
            for item in original(*args, **kwargs):
                _capture_interrupts_from_output(_RUN_STATE.get(), item)
                yield item
            return

        with _graph_span(graph_metadata, kwargs) as span:
            state = LangGraphRunState(graph_name=graph_metadata.get("graph_name"))
            token = _RUN_STATE.set(state)
            try:
                for item in original(*args, **kwargs):
                    _capture_interrupts_from_output(state, item)
                    yield item
                _finish_graph_span(span, graph_metadata, state)
            except Exception as exc:
                _record_error(span, exc)
                raise
            finally:
                _RUN_STATE.reset(token)

    return wrapper


def _make_astream_wrapper(original: Callable[..., AsyncIterator[Any]], graph_metadata: dict[str, Any]) -> Callable[..., AsyncIterator[Any]]:
    @functools.wraps(original)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        if _RUN_STATE.get() is not None:
            async for item in original(*args, **kwargs):
                _capture_interrupts_from_output(_RUN_STATE.get(), item)
                yield item
            return

        with _graph_span(graph_metadata, kwargs) as span:
            state = LangGraphRunState(graph_name=graph_metadata.get("graph_name"))
            token = _RUN_STATE.set(state)
            try:
                async for item in original(*args, **kwargs):
                    _capture_interrupts_from_output(state, item)
                    yield item
                _finish_graph_span(span, graph_metadata, state)
            except Exception as exc:
                _record_error(span, exc)
                raise
            finally:
                _RUN_STATE.reset(token)

    return wrapper


def _wrap_node_action(node_name: str, action: Any) -> Any:
    if getattr(action, "_agentsre_langgraph_wrapped", False):
        return action
    if not callable(action):
        return action
    classification = _classify_node(node_name, action)
    tool_description = _tool_description(action) if classification == "tool" else None

    if inspect.iscoroutinefunction(action):
        @functools.wraps(action)
        async def async_node(*args: Any, **kwargs: Any) -> Any:
            with _node_span(node_name, classification) as span:
                if tool_description:
                    span.set_attribute("tool.description", tool_description)
                try:
                    result = await action(*args, **kwargs)
                    _apply_node_result_metadata(span, node_name, classification, result)
                    _capture_interrupts_from_output(_RUN_STATE.get(), result)
                    _finish_node_span(span, node_name)
                    return result
                except Exception as exc:
                    _record_error(span, exc)
                    raise

        async_node._agentsre_langgraph_wrapped = True
        return async_node

    @functools.wraps(action)
    def sync_node(*args: Any, **kwargs: Any) -> Any:
        with _node_span(node_name, classification) as span:
            if tool_description:
                span.set_attribute("tool.description", tool_description)
            try:
                result = action(*args, **kwargs)
                _apply_node_result_metadata(span, node_name, classification, result)
                _capture_interrupts_from_output(_RUN_STATE.get(), result)
                _finish_node_span(span, node_name)
                return result
            except Exception as exc:
                _record_error(span, exc)
                raise

    sync_node._agentsre_langgraph_wrapped = True
    return sync_node


def _wrap_conditional_path(source: str, path: Any, path_map: Any) -> Any:
    if getattr(path, "_agentsre_langgraph_wrapped", False):
        return path
    if not callable(path):
        return path

    if inspect.iscoroutinefunction(path):
        @functools.wraps(path)
        async def async_path(*args: Any, **kwargs: Any) -> Any:
            selected = await path(*args, **kwargs)
            _record_conditional_selection(source, selected, path_map)
            return selected

        async_path._agentsre_langgraph_wrapped = True
        return async_path

    @functools.wraps(path)
    def sync_path(*args: Any, **kwargs: Any) -> Any:
        selected = path(*args, **kwargs)
        _record_conditional_selection(source, selected, path_map)
        return selected

    sync_path._agentsre_langgraph_wrapped = True
    return sync_path


def _graph_span(graph_metadata: dict[str, Any], runtime_kwargs: dict[str, Any]) -> Any:
    tracer = _get_tracer()
    graph_name = graph_metadata.get("graph_name") or "LangGraph"
    manager = tracer.start_as_current_span(f"LangGraph Graph: {graph_name}", kind=SpanKind.INTERNAL)
    span = manager.__enter__()
    span.set_attribute("agentsre.span_kind", "AGENT")
    span.set_attribute("agentsre.node_classification", "agent")
    span.set_attribute("agentsre.agent_name", str(graph_name))
    span.set_attribute("agentsre.agent_role", "Graph")
    span.set_attribute("agentsre.agent_type", "LangGraph")
    span.set_attribute("node.name", str(graph_name))
    span.set_attribute("reasoning.step", 1)
    span.set_attribute("decision.type", "Graph Execution")
    span.set_attribute("agentsre.langgraph.graph_name", str(graph_name))
    span.set_attribute("agentsre.langgraph.nodes", _json_dumps(graph_metadata["nodes"]))
    span.set_attribute("agentsre.langgraph.registered_nodes", _json_dumps(graph_metadata["registered_nodes"]))
    span.set_attribute("agentsre.langgraph.edges", _json_dumps(graph_metadata["edges"]))
    span.set_attribute("agentsre.langgraph.conditional_edges", _json_dumps(graph_metadata["conditional_edges"]))
    span.set_attribute("agentsre.langgraph.entry_nodes", _json_dumps(graph_metadata["entry_nodes"]))
    span.set_attribute("agentsre.langgraph.finish_nodes", _json_dumps(graph_metadata["finish_nodes"]))
    span.set_attribute("agentsre.langgraph.checkpoint_enabled", bool(graph_metadata["checkpoint_enabled"]))
    span.set_attribute("agentsre.langgraph.interrupt_before", _json_dumps(_runtime_or_compile_list(runtime_kwargs, graph_metadata, "interrupt_before")))
    span.set_attribute("agentsre.langgraph.interrupt_after", _json_dumps(_runtime_or_compile_list(runtime_kwargs, graph_metadata, "interrupt_after")))
    span.set_attribute("agentsre.langgraph.durability", str(runtime_kwargs.get("durability")) if runtime_kwargs.get("durability") is not None else "")
    return _ManagedSpan(manager, span)


def _node_span(node_name: str, classification: str) -> Any:
    tracer = _get_tracer()
    state = _RUN_STATE.get()
    previous_node = state.last_node if state is not None else None
    visit_count = state.visits.get(node_name, 0) if state is not None else 0
    cycle_detected = visit_count > 0
    manager = tracer.start_as_current_span(f"LangGraph Node: {node_name}", kind=SpanKind.INTERNAL)
    span = manager.__enter__()
    span_kind = {"agent": "AGENT", "llm": "LLM", "tool": "TOOL"}.get(classification, "AGENT")
    span.set_attribute("agentsre.span_kind", span_kind)
    span.set_attribute("agentsre.node_classification", classification)
    span.set_attribute("agentsre.langgraph.node_name", node_name)
    if state is not None and state.graph_name is not None:
        span.set_attribute("agentsre.langgraph.graph_name", state.graph_name)
    span.set_attribute("node.name", node_name)
    span.set_attribute("reasoning.step", _next_step(state))
    span.set_attribute("agentsre.iteration_count", visit_count + 1)
    span.set_attribute("decision.type", "Cycle Detected" if cycle_detected else "Node Execution")
    if span_kind == "AGENT":
        span.set_attribute("agentsre.agent_name", node_name)
        span.set_attribute("agentsre.agent_role", _agent_role(node_name))
        span.set_attribute("agentsre.agent_type", "LangGraphNode")
    elif span_kind == "TOOL":
        span.set_attribute("tool.name", node_name)
        span.set_attribute("tool.type", _tool_type(node_name))
    if previous_node is not None:
        span.set_attribute("agentsre.langgraph.previous_node", previous_node)
        span.set_attribute("previous_node", previous_node)
    span.set_attribute("agentsre.langgraph.cycle_detected", cycle_detected)
    if state is not None:
        state.visits[node_name] = visit_count + 1
        if cycle_detected:
            state.cycle_nodes.add(node_name)
    return _ManagedNodeSpan(manager, span, node_name)


class _ManagedSpan:
    def __init__(self, manager: Any, span: Span) -> None:
        self.manager = manager
        self.span = span

    def __enter__(self) -> Span:
        return self.span

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool | None:
        return self.manager.__exit__(exc_type, exc, traceback)


class _ManagedNodeSpan(_ManagedSpan):
    def __init__(self, manager: Any, span: Span, node_name: str) -> None:
        super().__init__(manager, span)
        self.node_name = node_name


def _finish_node_span(span: Span, node_name: str) -> None:
    state = _RUN_STATE.get()
    if state is None:
        return
    state.last_node = node_name
    span.set_attribute("agentsre.langgraph.cycle_detected", node_name in state.cycle_nodes)
    if state.conditional_edges:
        latest = state.conditional_edges[-1]
        if latest.get("source") == node_name:
            span.set_attribute("agentsre.langgraph.conditional_source", str(latest.get("source")))
            span.set_attribute("agentsre.langgraph.conditional_target", str(latest.get("target")))
            span.set_attribute("agentsre.langgraph.selected_edge", str(latest.get("selected")))
            span.set_attribute("next_node", str(latest.get("target")))


def _finish_graph_span(span: Span, graph_metadata: dict[str, Any], state: LangGraphRunState) -> None:
    combined_conditionals = [*graph_metadata["conditional_edges"], *state.conditional_edges]
    span.set_attribute("agentsre.langgraph.conditional_edges", _json_dumps(combined_conditionals))
    span.set_attribute("agentsre.langgraph.has_cycle", bool(state.cycle_nodes or graph_metadata["has_cycle"]))
    span.set_attribute("agentsre.langgraph.cycle_nodes", _json_dumps(sorted(set(graph_metadata["cycle_nodes"]) | state.cycle_nodes)))
    if state.interrupts:
        span.set_attribute("agentsre.langgraph.interrupt_events", _json_dumps(state.interrupts))


def _record_conditional_selection(source: str, selected: Any, path_map: Any) -> None:
    state = _RUN_STATE.get()
    selected_values = selected if isinstance(selected, (list, tuple, set)) else [selected]
    for value in selected_values:
        target = _resolve_path_target(value, path_map)
        event = {"source": str(source), "selected": str(value), "target": str(target)}
        if state is not None:
            state.conditional_edges.append(event)
        with _conditional_span(str(source)) as span:
            span.set_attribute("agentsre.langgraph.conditional_source", str(source))
            span.set_attribute("agentsre.langgraph.conditional_target", str(target))
            span.set_attribute("agentsre.langgraph.selected_edge", str(value))
            span.set_attribute("previous_node", str(source))
            span.set_attribute("next_node", str(target))
            span.set_attribute("decision.type", "Conditional Route")


def _conditional_span(source: str) -> Any:
    tracer = _get_tracer()
    manager = tracer.start_as_current_span(f"LangGraph Conditional Edge: {source}", kind=SpanKind.INTERNAL)
    span = manager.__enter__()
    span.set_attribute("agentsre.span_kind", "REASONING")
    span.set_attribute("agentsre.node_classification", "reasoning")
    span.set_attribute("agentsre.langgraph.node_name", source)
    span.set_attribute("node.name", source)
    span.set_attribute("reasoning.step", _next_step(_RUN_STATE.get()))
    return _ManagedSpan(manager, span)


def _capture_interrupts_from_output(state: LangGraphRunState | None, output: Any) -> None:
    if state is None:
        return
    if isinstance(output, dict) and "__interrupt__" in output:
        state.interrupts.append("output.__interrupt__")
    if isinstance(output, (list, tuple)):
        for item in output:
            _capture_interrupts_from_output(state, item)


def _record_error(span: Span, exc: Exception) -> None:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def _classify_node(node_name: str, action: Any) -> str:
    if _is_langchain_tool(action):
        return "tool"
    if _is_model_client(action):
        return "llm"
    return "agent"


def _is_model_client(action: Any) -> bool:
    if action is None:
        return False
    action_class = action.__class__
    module_names = {
        str(getattr(action, "__module__", "")),
        str(getattr(action_class, "__module__", "")),
    }
    class_name = str(getattr(action_class, "__name__", ""))
    known_model_modules = (
        "langchain_openai",
        "langchain_anthropic",
        "langchain_google_genai",
        "openai",
        "anthropic",
        "google.generativeai",
        "google.genai",
    )
    known_model_classes = {
        "ChatOpenAI",
        "OpenAI",
        "AzureChatOpenAI",
        "ChatAnthropic",
        "ChatGoogleGenerativeAI",
        "GenerativeModel",
        "Client",
        "AsyncClient",
    }
    has_model_api = callable(getattr(action, "invoke", None)) or callable(getattr(action, "generate", None))
    return has_model_api and (
        class_name in known_model_classes or any(module_name.startswith(known_model_modules) for module_name in module_names)
    )


def _is_langchain_tool(action: Any) -> bool:
    try:
        from langchain_core.tools import BaseTool

        if isinstance(action, BaseTool):
            return True
    except Exception:
        pass

    action_class = action.__class__
    module_names = {
        str(getattr(action, "__module__", "")),
        str(getattr(action_class, "__module__", "")),
    }
    has_tool_api = (
        callable(getattr(action, "invoke", None))
        and getattr(action, "name", None) is not None
        and getattr(action, "description", None) is not None
        and getattr(action, "args", None) is not None
    )
    return has_tool_api and any(module_name.startswith("langchain") for module_name in module_names)


def _apply_node_result_metadata(span: Span, node_name: str, classification: str, result: Any) -> None:
    if classification == "tool":
        span.set_attribute("tool.name", node_name)
        span.set_attribute("tool.type", _tool_type(node_name))
        span.set_attribute("tool.status", "SUCCESS")
        if result is not None:
            span.set_attribute("tool.output", _json_dumps(_small_jsonable(result)))
    elif classification == "llm":
        metadata = result if isinstance(result, dict) else {}
        for key in ["provider", "model", "prompt", "response", "finish_reason"]:
            if key in metadata and metadata[key] is not None:
                span.set_attribute(_llm_attr_name(key), str(metadata[key]))
        for key in ["input_tokens", "output_tokens", "total_tokens", "max_tokens"]:
            if key in metadata and metadata[key] is not None:
                span.set_attribute(key, int(metadata[key]))


def _next_step(state: LangGraphRunState | None) -> int:
    if state is None:
        return 1
    state.step += 1
    return state.step


def _agent_role(node_name: str) -> str:
    lowered = node_name.lower()
    if "planner" in lowered:
        return "Planner"
    if "supervisor" in lowered:
        return "Supervisor"
    if "worker" in lowered:
        return "Worker"
    return "Agent"


def _tool_type(node_name: str) -> str:
    lowered = node_name.lower()
    if "api" in lowered or "http" in lowered or "request" in lowered:
        return "REST API"
    if "search" in lowered:
        return "Search"
    return "Tool"


def _tool_description(action: Any) -> str | None:
    explicit = getattr(action, "description", None)
    if explicit:
        return str(explicit)
    metadata = getattr(action, "metadata", None)
    if isinstance(metadata, dict) and metadata.get("description"):
        return str(metadata["description"])
    args_schema = getattr(action, "args_schema", None)
    args_schema_doc = inspect.getdoc(args_schema) if args_schema is not None else None
    if args_schema_doc:
        return args_schema_doc
    action_doc = inspect.getdoc(action)
    if action_doc:
        return action_doc
    class_doc = inspect.getdoc(action.__class__)
    if class_doc and action.__class__ is not object:
        return class_doc
    return None


def _tool_arguments(action: Any) -> Any:
    args = getattr(action, "args", None)
    if args is not None:
        return _small_jsonable(args)
    args_schema = getattr(action, "args_schema", None)
    schema = getattr(args_schema, "model_json_schema", None)
    if callable(schema):
        return _small_jsonable(schema())
    return None


def _llm_attr_name(key: str) -> str:
    return {
        "provider": "llm.provider",
        "model": "llm.model_name",
        "prompt": "prompt",
        "response": "response",
        "finish_reason": "finish_reason",
    }[key]


def _small_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _small_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_small_jsonable(item) for item in value[:20]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _graph_metadata(graph: Any, graph_name: str | None, compile_args: tuple[Any, ...], compile_kwargs: dict[str, Any]) -> dict[str, Any]:
    nodes = sorted(str(name) for name in getattr(graph, "nodes", {}).keys())
    registered_nodes = list(_ensure_build_metadata(graph)["registered_nodes"].values())
    edges = _normal_edges(graph)
    conditional_edges = _conditional_edges(graph)
    entry_nodes = sorted({edge["target"] for edge in edges if edge["source"] == "__start__"})
    finish_nodes = sorted({edge["source"] for edge in edges if edge["target"] == "__end__"})
    cycle_nodes = _cycle_nodes(nodes, edges, conditional_edges)
    checkpointer = compile_args[0] if compile_args else compile_kwargs.get("checkpointer")
    return {
        "graph_name": graph_name,
        "nodes": nodes,
        "registered_nodes": sorted(registered_nodes, key=lambda item: item["node_name"]),
        "edges": edges,
        "conditional_edges": conditional_edges,
        "entry_nodes": entry_nodes,
        "finish_nodes": finish_nodes,
        "has_cycle": bool(cycle_nodes),
        "cycle_nodes": cycle_nodes,
        "checkpoint_enabled": checkpointer is not None,
        "interrupt_before": _as_str_list(compile_kwargs.get("interrupt_before")),
        "interrupt_after": _as_str_list(compile_kwargs.get("interrupt_after")),
    }


def _normal_edges(graph: Any) -> list[dict[str, Any]]:
    edges = []
    for source, target in sorted(getattr(graph, "edges", set()), key=lambda item: (str(item[0]), str(item[1]))):
        edges.append({"source": str(source), "target": str(target), "conditional": False})
    for source, target in sorted(getattr(graph, "waiting_edges", set()), key=lambda item: (str(item[0]), str(item[1]))):
        edges.append({"source": str(source), "target": str(target), "conditional": False, "waiting": True})
    return edges


def _conditional_edges(graph: Any) -> list[dict[str, Any]]:
    conditionals = []
    branches = getattr(graph, "branches", {})
    for source, named_branches in branches.items():
        for branch_name, branch in named_branches.items():
            ends = getattr(branch, "ends", None) or {}
            conditionals.append(
                {
                    "source": str(source),
                    "path": str(branch_name),
                    "path_map": {str(key): str(value) for key, value in dict(ends).items()},
                    "conditional": True,
                }
            )
    return conditionals


def _cycle_nodes(nodes: list[str], edges: list[dict[str, Any]], conditional_edges: list[dict[str, Any]]) -> list[str]:
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
    for edge in conditional_edges:
        source = edge["source"]
        for target in edge.get("path_map", {}).values():
            if source in adjacency and target in adjacency:
                adjacency[source].add(target)
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: set[str] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in visiting:
            if node in path:
                cycles.update(path[path.index(node) :])
            return
        if node in visited:
            return
        visiting.add(node)
        path.append(node)
        for target in adjacency.get(node, set()):
            visit(target, path)
        path.pop()
        visiting.remove(node)
        visited.add(node)

    for node in nodes:
        visit(node, [])
    return sorted(cycles)


def _ensure_build_metadata(graph: Any) -> dict[str, Any]:
    metadata = getattr(graph, "_agentsre_build_metadata", None)
    if metadata is None:
        metadata = {"nodes": set(), "edges": [], "conditional_edges": [], "registered_nodes": {}}
        graph._agentsre_build_metadata = metadata
    return metadata


def _registered_node_metadata(node_name: str, classification: str, action: Any | None) -> dict[str, Any]:
    return {
        "node_name": node_name,
        "classification": classification,
        "agent_role": _agent_role(node_name),
        "agent_type": "LangGraphNode",
        "tool_type": _tool_type(node_name),
        "tool_description": _tool_description(action) if action is not None else None,
        "tool_arguments": _tool_arguments(action) if action is not None else None,
    }


def _node_name(node: Any, action: Any | None) -> str:
    if isinstance(node, str):
        return node
    return _callable_name(action or node)


def _callable_name(value: Any) -> str:
    return str(getattr(value, "__name__", getattr(value, "name", value.__class__.__name__)))


def _resolve_path_target(selected: Any, path_map: Any) -> Any:
    if isinstance(path_map, dict):
        return path_map.get(selected, selected)
    if isinstance(path_map, list):
        return selected if selected in path_map else selected
    return selected


def _jsonable_path_map(path_map: Any) -> dict[str, str] | list[str] | None:
    if isinstance(path_map, dict):
        return {str(key): str(value) for key, value in path_map.items()}
    if isinstance(path_map, list):
        return [str(item) for item in path_map]
    return None


def _runtime_or_compile_list(runtime_kwargs: dict[str, Any], graph_metadata: dict[str, Any], key: str) -> list[str]:
    if key in runtime_kwargs and runtime_kwargs[key] is not None:
        return _as_str_list(runtime_kwargs[key])
    return list(graph_metadata[key])


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if value == "All":
        return ["All"]
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _get_tracer() -> Any:
    if _TRACER_PROVIDER is not None:
        return _TRACER_PROVIDER.get_tracer(__name__)
    return trace.get_tracer(__name__)
