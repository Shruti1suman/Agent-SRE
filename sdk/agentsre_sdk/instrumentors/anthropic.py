from __future__ import annotations

from typing import Any


def instrument(tracer_provider: Any | None = None) -> dict[str, str]:
    try:
        from openinference.instrumentation.anthropic import AnthropicInstrumentor
    except ImportError as exc:
        return {"name": "anthropic", "status": "unavailable", "detail": str(exc)}

    kwargs = {"tracer_provider": tracer_provider} if tracer_provider is not None else {}
    AnthropicInstrumentor().instrument(**kwargs)
    return {"name": "anthropic", "status": "instrumented", "detail": "Anthropic SDK instrumentation enabled"}
