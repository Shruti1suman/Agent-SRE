from __future__ import annotations

import sys
import types

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentsre_sdk.instrumentors import litellm


def test_litellm_fallback_emits_provider_llm_span(monkeypatch) -> None:
    fake_litellm = types.ModuleType("litellm")

    def completion(**kwargs):
        return {
            "model": kwargs["model"],
            "choices": [{"finish_reason": "stop", "message": {"content": "done"}}],
            "usage": {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
        }

    fake_litellm.completion = completion
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    monkeypatch.delitem(sys.modules, "openinference.instrumentation.litellm", raising=False)

    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))

    result = litellm.instrument(tracer_provider)
    response = fake_litellm.completion(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])

    spans = exporter.get_finished_spans()
    assert result["status"] == "instrumented"
    assert response["usage"]["total_tokens"] == 18
    assert len(spans) == 1
    assert spans[0].name == "LiteLLM Completion: openai/gpt-4o-mini"
    assert spans[0].attributes["openinference.span.kind"] == "LLM"
    assert spans[0].attributes["llm.provider"] == "openai"
    assert spans[0].attributes["llm.model_name"] == "gpt-4o-mini"
    assert spans[0].attributes["input_tokens"] == 13
    assert spans[0].attributes["output_tokens"] == 5
    assert spans[0].attributes["total_tokens"] == 18
    assert spans[0].attributes["finish_reason"] == "stop"
