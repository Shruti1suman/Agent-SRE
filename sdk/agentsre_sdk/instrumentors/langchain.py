from __future__ import annotations

import contextlib
import functools
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextvars import ContextVar
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from agentsre_sdk.instrumentors.registry import register_available_tools

_TRACER_PROVIDER: Any | None = None
_BRIDGE_ACTIVE: ContextVar[bool] = ContextVar("agentsre_langchain_bridge_active", default=False)


def instrument(tracer_provider: Any | None = None) -> dict[str, str]:
    global _TRACER_PROVIDER
    if tracer_provider is not None:
        _TRACER_PROVIDER = tracer_provider
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
    except ImportError as exc:
        return {"name": "langchain", "status": "unavailable", "detail": str(exc)}

    kwargs = {"tracer_provider": tracer_provider} if tracer_provider is not None else {}
    LangChainInstrumentor().instrument(**kwargs)
    _patch_langchain_tool_registration()
    return {"name": "langchain", "status": "instrumented", "detail": "LangChain and LangGraph instrumentation enabled"}


def _patch_langchain_tool_registration() -> None:
    _patch_function("langchain.agents", "initialize_agent", _tools_from_initialize_agent)
    _patch_function("langchain.agents", "create_agent", _tools_from_create_agent, wrap_agent=True)


def _patch_function(module_name: str, function_name: str, extractor: Any, *, wrap_agent: bool = False) -> None:
    try:
        module = __import__(module_name, fromlist=[function_name])
    except ImportError:
        return
    original = getattr(module, function_name, None)
    if original is None or getattr(original, "_agentsre_tool_registration_wrapped", False):
        return

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        register_available_tools(extractor(args, kwargs), framework="LangChain")
        result = original(*args, **kwargs)
        if wrap_agent:
            return _wrap_agent_result(result, _agent_name_from_create_agent(args, kwargs, result))
        return result

    wrapper._agentsre_tool_registration_wrapped = True
    setattr(module, function_name, wrapper)


def _tools_from_initialize_agent(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    if "tools" in kwargs:
        return kwargs["tools"]
    return args[0] if args else None


def _tools_from_create_agent(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    if "tools" in kwargs:
        return kwargs["tools"]
    return args[1] if len(args) > 1 else None


def _wrap_agent_result(agent: Any, agent_name: str) -> Any:
    if agent is None or getattr(agent, "_agentsre_langchain_bridge_wrapped", False):
        return agent

    wrapped_any = False
    for method_name, factory in {
        "invoke": _make_invoke_wrapper,
        "stream": _make_stream_wrapper,
        "ainvoke": _make_ainvoke_wrapper,
        "astream": _make_astream_wrapper,
    }.items():
        original = getattr(agent, method_name, None)
        if not callable(original) or getattr(original, "_agentsre_langchain_bridge_method", False):
            continue
        with contextlib.suppress(Exception):
            setattr(agent, method_name, factory(original, agent_name))
            wrapped_any = True

    if wrapped_any:
        with contextlib.suppress(Exception):
            setattr(agent, "_agentsre_langchain_bridge_wrapped", True)
            setattr(agent, "_agentsre_langchain_agent_name", agent_name)
    return agent


def _make_invoke_wrapper(original: Callable[..., Any], agent_name: str) -> Callable[..., Any]:
    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _should_skip_bridge_span():
            return original(*args, **kwargs)
        with _agent_span(agent_name) as span:
            token = _BRIDGE_ACTIVE.set(True)
            try:
                return original(*args, **kwargs)
            except Exception as exc:
                _record_error(span, exc)
                raise
            finally:
                _BRIDGE_ACTIVE.reset(token)

    wrapper._agentsre_langchain_bridge_method = True
    return wrapper


def _make_stream_wrapper(original: Callable[..., Iterator[Any]], agent_name: str) -> Callable[..., Iterator[Any]]:
    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Iterator[Any]:
        if _should_skip_bridge_span():
            yield from original(*args, **kwargs)
            return
        with _agent_span(agent_name) as span:
            token = _BRIDGE_ACTIVE.set(True)
            try:
                yield from original(*args, **kwargs)
            except Exception as exc:
                _record_error(span, exc)
                raise
            finally:
                _BRIDGE_ACTIVE.reset(token)

    wrapper._agentsre_langchain_bridge_method = True
    return wrapper


def _make_ainvoke_wrapper(original: Callable[..., Awaitable[Any]], agent_name: str) -> Callable[..., Awaitable[Any]]:
    @functools.wraps(original)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _should_skip_bridge_span():
            return await original(*args, **kwargs)
        with _agent_span(agent_name) as span:
            token = _BRIDGE_ACTIVE.set(True)
            try:
                return await original(*args, **kwargs)
            except Exception as exc:
                _record_error(span, exc)
                raise
            finally:
                _BRIDGE_ACTIVE.reset(token)

    wrapper._agentsre_langchain_bridge_method = True
    return wrapper


def _make_astream_wrapper(original: Callable[..., AsyncIterator[Any]], agent_name: str) -> Callable[..., AsyncIterator[Any]]:
    @functools.wraps(original)
    async def wrapper(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        if _should_skip_bridge_span():
            async for item in original(*args, **kwargs):
                yield item
            return
        with _agent_span(agent_name) as span:
            token = _BRIDGE_ACTIVE.set(True)
            try:
                async for item in original(*args, **kwargs):
                    yield item
            except Exception as exc:
                _record_error(span, exc)
                raise
            finally:
                _BRIDGE_ACTIVE.reset(token)

    wrapper._agentsre_langchain_bridge_method = True
    return wrapper


def _agent_span(agent_name: str) -> Any:
    manager = _get_tracer().start_as_current_span(f"LangChain Agent: {agent_name}", kind=SpanKind.INTERNAL)
    span = manager.__enter__()
    span.set_attribute("agentsre.span_kind", "AGENT")
    span.set_attribute("agentsre.node_classification", "agent")
    span.set_attribute("agentsre.agent_name", agent_name)
    span.set_attribute("agentsre.agent_role", "Agent")
    span.set_attribute("agentsre.agent_type", "LangChainAgent")
    span.set_attribute("node.name", agent_name)
    span.set_attribute("decision.type", "Agent Invocation")
    config = _current_config()
    if config is not None:
        if getattr(config, "workflow_id", None):
            span.set_attribute("agentsre.workflow_id", str(config.workflow_id))
        if getattr(config, "session_id", None):
            span.set_attribute("agentsre.session_id", str(config.session_id))
    return _ManagedSpan(manager, span)


class _ManagedSpan:
    def __init__(self, manager: Any, span: Span) -> None:
        self.manager = manager
        self.span = span

    def __enter__(self) -> Span:
        return self.span

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool | None:
        return self.manager.__exit__(exc_type, exc, traceback)


def _agent_name_from_create_agent(args: tuple[Any, ...], kwargs: dict[str, Any], agent: Any) -> str:
    for candidate in (kwargs.get("name"), getattr(agent, "name", None), getattr(agent, "_name", None)):
        if candidate:
            return str(candidate)
    return "LangChainAgent"


def _should_skip_bridge_span() -> bool:
    if _BRIDGE_ACTIVE.get():
        return True
    return _langgraph_run_active()


def _langgraph_run_active() -> bool:
    try:
        from agentsre_sdk.instrumentors import langgraph

        run_state = getattr(langgraph, "_RUN_STATE", None)
        return bool(run_state is not None and run_state.get() is not None)
    except Exception:
        return False


def _current_config() -> Any | None:
    try:
        from agentsre_sdk import get_state

        state = get_state()
        return getattr(state, "config", None) if state is not None else None
    except Exception:
        return None


def _record_error(span: Span, exc: Exception) -> None:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def _get_tracer() -> Any:
    if _TRACER_PROVIDER is not None:
        return _TRACER_PROVIDER.get_tracer(__name__)
    return trace.get_tracer(__name__)
