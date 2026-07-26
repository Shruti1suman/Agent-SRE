from __future__ import annotations

from typing import Any


def instrument(tracer_provider: Any | None = None) -> dict[str, str]:
    try:
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
    except ImportError as exc:
        return {"name": "gemini", "status": "unavailable", "detail": str(exc)}

    kwargs = {"tracer_provider": tracer_provider} if tracer_provider is not None else {}
    GoogleGenAIInstrumentor().instrument(**kwargs)
    return {"name": "gemini", "status": "instrumented", "detail": "Google Gemini SDK instrumentation enabled"}
