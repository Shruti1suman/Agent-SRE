from __future__ import annotations

from typing import Any, Callable


def instrument(tracer_provider: Any | None = None) -> dict[str, str]:
    results = [
        _instrument_one("requests", "opentelemetry.instrumentation.requests", "RequestsInstrumentor", tracer_provider),
        _instrument_one("httpx", "opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor", tracer_provider),
        _instrument_one("aiohttp", "opentelemetry.instrumentation.aiohttp_client", "AioHttpClientInstrumentor", tracer_provider),
        _instrument_one("sqlalchemy", "opentelemetry.instrumentation.sqlalchemy", "SQLAlchemyInstrumentor", tracer_provider),
    ]
    enabled = [result["name"] for result in results if result["status"] == "instrumented"]
    return {
        "name": "http",
        "status": "instrumented" if enabled else "unavailable",
        "detail": ", ".join(enabled) if enabled else "No HTTP or SQLAlchemy instrumentors available",
    }


def _instrument_one(name: str, module_name: str, class_name: str, tracer_provider: Any | None) -> dict[str, str]:
    try:
        module = __import__(module_name, fromlist=[class_name])
        instrumentor_factory: Callable[[], Any] = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        return {"name": name, "status": "unavailable", "detail": str(exc)}

    kwargs = {"tracer_provider": tracer_provider} if tracer_provider is not None else {}
    instrumentor_factory().instrument(**kwargs)
    return {"name": name, "status": "instrumented", "detail": f"{name} instrumentation enabled"}
