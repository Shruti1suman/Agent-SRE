from __future__ import annotations

from typing import Any


def instrument(tracer_provider: Any | None = None) -> dict[str, str]:
    try:
        from openinference.instrumentation.openai import OpenAIInstrumentor
    except ImportError as exc:
        return {"name": "openai", "status": "unavailable", "detail": str(exc)}

    kwargs = {"tracer_provider": tracer_provider} if tracer_provider is not None else {}
    OpenAIInstrumentor().instrument(**kwargs)
    return {"name": "openai", "status": "instrumented", "detail": "OpenAI SDK instrumentation enabled"}
