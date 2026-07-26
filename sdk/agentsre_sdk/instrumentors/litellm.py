from __future__ import annotations

import functools
import inspect
import json
from typing import Any, Awaitable, Callable

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode


_WRAPPED = False


def instrument(tracer_provider: Any | None = None) -> dict[str, str]:
    try:
        from openinference.instrumentation.litellm import LiteLLMInstrumentor
    except ImportError:
        return _instrument_fallback(tracer_provider)

    kwargs = {"tracer_provider": tracer_provider} if tracer_provider is not None else {}
    LiteLLMInstrumentor().instrument(**kwargs)
    return {"name": "litellm", "status": "instrumented", "detail": "LiteLLM OpenInference instrumentation enabled"}


def _instrument_fallback(tracer_provider: Any | None) -> dict[str, str]:
    try:
        import litellm
    except ImportError as exc:
        return {"name": "litellm", "status": "unavailable", "detail": str(exc)}

    patched = []
    for function_name in ["completion", "acompletion"]:
        original = getattr(litellm, function_name, None)
        if original is None or getattr(original, "_agentsre_litellm_wrapped", False):
            continue
        setattr(litellm, function_name, _wrap_completion(original, tracer_provider))
        patched.append(function_name)

    if not patched:
        return {"name": "litellm", "status": "instrumented", "detail": "LiteLLM fallback instrumentation already enabled"}
    return {"name": "litellm", "status": "instrumented", "detail": f"LiteLLM fallback instrumentation enabled: {', '.join(patched)}"}


def _wrap_completion(function: Callable[..., Any], tracer_provider: Any | None) -> Callable[..., Any]:
    tracer = tracer_provider.get_tracer(__name__) if tracer_provider is not None else trace.get_tracer(__name__)

    if inspect.iscoroutinefunction(function):

        @functools.wraps(function)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await _run_async_completion(tracer, function, args, kwargs)

        async_wrapper._agentsre_litellm_wrapped = True
        return async_wrapper

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return _run_completion(tracer, function, args, kwargs)

    wrapper._agentsre_litellm_wrapped = True
    return wrapper


def _run_completion(tracer: Any, function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    with tracer.start_as_current_span(_span_name(kwargs), kind=SpanKind.INTERNAL) as span:
        _set_request_attrs(span, args, kwargs)
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            _record_error(span, exc)
            raise
        _set_response_attrs(span, result)
        return result


async def _run_async_completion(
    tracer: Any,
    function: Callable[..., Awaitable[Any]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    with tracer.start_as_current_span(_span_name(kwargs), kind=SpanKind.INTERNAL) as span:
        _set_request_attrs(span, args, kwargs)
        try:
            result = await function(*args, **kwargs)
        except Exception as exc:
            _record_error(span, exc)
            raise
        _set_response_attrs(span, result)
        return result


def _span_name(kwargs: dict[str, Any]) -> str:
    model = _model_name(kwargs)
    return f"LiteLLM Completion: {model or 'completion'}"


def _set_request_attrs(span: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    model = _model_name(kwargs, args)
    _set_attr(span, "openinference.span.kind", "LLM")
    _set_attr(span, "agentsre.provider_span", True)
    _set_attr(span, "llm.provider", _provider_from_model(model) or _str_value(kwargs.get("custom_llm_provider")))
    _set_attr(span, "llm.model_name", _clean_model_name(model))
    _set_attr(span, "model", _clean_model_name(model))
    _set_attr(span, "input.value", _small_jsonable(kwargs.get("messages") or kwargs.get("prompt")))
    for attr_name, key in {
        "temperature": "temperature",
        "max_tokens": "max_tokens",
        "top_p": "top_p",
        "frequency_penalty": "frequency_penalty",
        "presence_penalty": "presence_penalty",
    }.items():
        value = kwargs.get(key)
        if value is not None:
            _set_attr(span, attr_name, value)


def _set_response_attrs(span: Any, result: Any) -> None:
    if _is_streaming_response(result):
        _set_attr(span, "agentsre.litellm.streaming", True)
        return

    _set_attr(span, "output.value", _small_jsonable(result))
    usage = _first_nested(result, ["usage", "token_usage"])
    for attr_name, keys in {
        "input_tokens": ["prompt_tokens", "input_tokens"],
        "output_tokens": ["completion_tokens", "output_tokens"],
        "total_tokens": ["total_tokens"],
    }.items():
        value = _first_nested(usage, keys) if usage is not None else _first_nested(result, keys)
        if value is not None:
            _set_attr(span, attr_name, int(value))

    finish_reason = _first_nested(result, ["finish_reason", "finish_reasons"])
    if finish_reason is not None:
        _set_attr(span, "finish_reason", _first_string(finish_reason))


def _record_error(span: Any, exc: Exception) -> None:
    message = f"{exc.__class__.__name__}: {exc}"
    _set_attr(span, "exception.type", exc.__class__.__name__)
    _set_attr(span, "exception.message", message)
    span.set_status(Status(StatusCode.ERROR, message))


def _model_name(kwargs: dict[str, Any], args: tuple[Any, ...] = ()) -> str | None:
    value = kwargs.get("model")
    if value is None and args:
        value = args[0]
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


def _is_streaming_response(result: Any) -> bool:
    if isinstance(result, (str, bytes, dict, list, tuple)):
        return False
    if inspect.isgenerator(result) or inspect.isasyncgen(result):
        return True
    return hasattr(result, "__iter__") and not hasattr(result, "model_dump") and not hasattr(result, "dict")


def _first_nested(value: Any, keys: list[str], *, depth: int = 0) -> Any:
    if value is None or depth > 6:
        return None
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                return value[key]
        for item in value.values():
            found = _first_nested(item, keys, depth=depth + 1)
            if found is not None:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _first_nested(item, keys, depth=depth + 1)
            if found is not None:
                return found
        return None
    for key in keys:
        attr_value = getattr(value, key, None)
        if attr_value is not None:
            return attr_value
    if callable(getattr(value, "model_dump", None)):
        try:
            return _first_nested(value.model_dump(), keys, depth=depth + 1)
        except Exception:
            return None
    if callable(getattr(value, "dict", None)):
        try:
            return _first_nested(value.dict(), keys, depth=depth + 1)
        except Exception:
            return None
    return None


def _small_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if callable(getattr(value, "model_dump", None)):
        try:
            value = value.model_dump()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _small_jsonable(item) for key, item in list(value.items())[:25]}
    if isinstance(value, (list, tuple, set)):
        return [_small_jsonable(item) for item in list(value)[:25]]
    if isinstance(value, (str, int, float, bool)):
        return value[:8000] if isinstance(value, str) else value
    return str(value)[:8000]


def _first_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return _first_string(value[0]) if value else None
    return str(value)


def _set_attr(span: Any, key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, default=str, ensure_ascii=True, sort_keys=True)
    span.set_attribute(key, value)


def _str_value(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


__all__ = ["instrument"]
