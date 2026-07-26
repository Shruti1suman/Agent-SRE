from __future__ import annotations

from typing import Any

from agentsre_sdk.instrumentors import anthropic, crewai, gemini, http, langchain, langgraph, litellm, openai


def instrument_all(
    tracer_provider: Any | None = None,
    *,
    instrument_langgraph: bool = True,
    instrument_crewai: bool = True,
) -> list[dict[str, str]]:
    results = []
    if instrument_langgraph:
        results.append(langgraph.instrument(tracer_provider))
    if instrument_crewai:
        results.append(crewai.instrument(tracer_provider))
    results.extend(
        [
            langchain.instrument(tracer_provider),
            openai.instrument(tracer_provider),
            litellm.instrument(tracer_provider),
            anthropic.instrument(tracer_provider),
            gemini.instrument(tracer_provider),
            http.instrument(tracer_provider),
        ]
    )
    return results


__all__ = ["instrument_all"]
