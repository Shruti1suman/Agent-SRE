from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentsre_sdk.instrumentors import langchain as langchain_instrumentor
from agentsre_sdk.instrumentors.registry import clear_available_tools, snapshot_available_tools


class FakeAgent:
    def __init__(self, name: str | None = None) -> None:
        self.name = name
        self.invoke_calls = 0

    def invoke(self, payload: Any) -> dict[str, Any]:
        self.invoke_calls += 1
        return {"payload": payload, "calls": self.invoke_calls}

    def stream(self, payload: Any) -> Any:
        yield {"payload": payload}

    async def ainvoke(self, payload: Any) -> dict[str, Any]:
        return {"payload": payload}

    async def astream(self, payload: Any) -> Any:
        yield {"payload": payload}


def test_create_agent_result_is_wrapped_once(monkeypatch: Any) -> None:
    exporter = _instrument_with_fake_langchain(monkeypatch)

    import langchain.agents

    langchain_instrumentor.instrument(_tracer_provider(exporter))
    agent = langchain.agents.create_agent(model=object(), tools=[], name="ResearchAgent")
    assert getattr(agent, "_agentsre_langchain_bridge_wrapped") is True

    result = agent.invoke({"messages": []})

    assert result["calls"] == 1
    bridge_spans = _bridge_spans(exporter)
    assert len(bridge_spans) == 1
    span = bridge_spans[0]
    assert span.name == "LangChain Agent: ResearchAgent"
    assert span.attributes["agentsre.span_kind"] == "AGENT"
    assert span.attributes["agentsre.agent_name"] == "ResearchAgent"
    assert span.attributes["agentsre.agent_type"] == "LangChainAgent"


def test_repeated_instrument_calls_do_not_double_wrap(monkeypatch: Any) -> None:
    exporter = _instrument_with_fake_langchain(monkeypatch)
    provider = _tracer_provider(exporter)

    import langchain.agents

    langchain_instrumentor.instrument(provider)
    langchain_instrumentor.instrument(provider)
    agent = langchain.agents.create_agent(model=object(), tools=[], name="StableAgent")
    agent.invoke({"messages": []})

    assert len(_bridge_spans(exporter)) == 1


def test_create_agent_still_registers_static_tools(monkeypatch: Any) -> None:
    exporter = _instrument_with_fake_langchain(monkeypatch)
    clear_available_tools()

    try:
        import langchain.agents

        langchain_instrumentor.instrument(_tracer_provider(exporter))
        tool = SimpleNamespace(
            name="account_profile_lookup",
            description="Looks up account profile details.",
            args={"account_id": {"type": "string"}},
        )

        langchain.agents.create_agent(model=object(), tools=[tool], name="ToolAgent")

        tools = snapshot_available_tools()
        assert len(tools) == 1
        assert tools[0]["tool_name"] == "account_profile_lookup"
        assert tools[0]["tool_arguments"] == {"account_id": {"type": "string"}}
        assert tools[0]["framework"] == "LangChain"
    finally:
        clear_available_tools()


def test_bridge_span_is_skipped_inside_active_langgraph_run(monkeypatch: Any) -> None:
    exporter = _instrument_with_fake_langchain(monkeypatch)

    import langchain.agents
    from agentsre_sdk.instrumentors import langgraph

    langchain_instrumentor.instrument(_tracer_provider(exporter))
    agent = langchain.agents.create_agent(model=object(), tools=[], name="NestedAgent")

    token = langgraph._RUN_STATE.set(langgraph.LangGraphRunState(graph_name="SupportGraph"))
    try:
        agent.invoke({"messages": []})
    finally:
        langgraph._RUN_STATE.reset(token)

    assert _bridge_spans(exporter) == []


def _instrument_with_fake_langchain(monkeypatch: Any) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    fake_openinference = types.ModuleType("openinference")
    fake_instrumentation = types.ModuleType("openinference.instrumentation")
    fake_langchain_instrumentation = types.ModuleType("openinference.instrumentation.langchain")

    class FakeLangChainInstrumentor:
        def instrument(self, **kwargs: Any) -> None:
            return None

    fake_langchain_instrumentation.LangChainInstrumentor = FakeLangChainInstrumentor
    fake_openinference.instrumentation = fake_instrumentation
    fake_instrumentation.langchain = fake_langchain_instrumentation

    fake_langchain = types.ModuleType("langchain")
    fake_agents = types.ModuleType("langchain.agents")

    def create_agent(*args: Any, **kwargs: Any) -> FakeAgent:
        return FakeAgent(kwargs.get("name"))

    def initialize_agent(*args: Any, **kwargs: Any) -> FakeAgent:
        return FakeAgent(kwargs.get("name"))

    fake_agents.create_agent = create_agent
    fake_agents.initialize_agent = initialize_agent
    fake_langchain.agents = fake_agents

    monkeypatch.setitem(sys.modules, "openinference", fake_openinference)
    monkeypatch.setitem(sys.modules, "openinference.instrumentation", fake_instrumentation)
    monkeypatch.setitem(sys.modules, "openinference.instrumentation.langchain", fake_langchain_instrumentation)
    monkeypatch.setitem(sys.modules, "langchain", fake_langchain)
    monkeypatch.setitem(sys.modules, "langchain.agents", fake_agents)
    return exporter


def _tracer_provider(exporter: InMemorySpanExporter) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def _bridge_spans(exporter: InMemorySpanExporter) -> list[Any]:
    return [span for span in exporter.get_finished_spans() if span.name.startswith("LangChain Agent:")]
