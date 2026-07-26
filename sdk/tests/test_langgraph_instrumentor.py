import builtins
import importlib
import json

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def test_langgraph_instrumentor_safe_when_unavailable(monkeypatch) -> None:
    langgraph_instrumentor = importlib.import_module("agentsre_sdk.instrumentors.langgraph")
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "langgraph.graph":
            raise ImportError("langgraph missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = langgraph_instrumentor.instrument()

    assert result["name"] == "langgraph"
    assert result["status"] == "unavailable"


def test_langgraph_instrumentor_is_idempotent() -> None:
    langgraph_instrumentor = importlib.import_module("agentsre_sdk.instrumentors.langgraph")

    first = langgraph_instrumentor.instrument()
    second = langgraph_instrumentor.instrument()

    assert first["status"] == "instrumented"
    assert second["status"] == "instrumented"


def test_langgraph_emits_canonical_agent_tool_reasoning_spans() -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))

    langgraph_instrumentor = importlib.import_module("agentsre_sdk.instrumentors.langgraph")
    langgraph_instrumentor.instrument(tracer_provider)

    from langgraph.graph import END, StateGraph
    from langgraph.checkpoint.memory import InMemorySaver

    def planner(state: dict[str, object]) -> dict[str, object]:
        visits = int(state.get("planner_visits", 0)) + 1
        return {**state, "planner_visits": visits}

    def weather(state: dict[str, object]) -> dict[str, object]:
        """Fetches current weather for the requested city."""
        return {**state, "weather": "cloudy"}

    def booking(state: dict[str, object]) -> dict[str, object]:
        return {**state, "__interrupt__": "approval-required"}

    def manual_review(state: dict[str, object]) -> dict[str, object]:
        return state

    def route_after_planner(state: dict[str, object]) -> str:
        if int(state.get("planner_visits", 0)) == 1:
            return "weather"
        return "booking"

    graph = StateGraph(dict)
    graph.add_node("PlannerNode", planner)
    graph.add_node("WeatherNode", weather)
    graph.add_node("BookingNode", booking)
    graph.add_node("ManualApproval", manual_review)
    graph.add_node("CheckpointReview", manual_review)
    graph.set_entry_point("PlannerNode")
    graph.add_conditional_edges("PlannerNode", route_after_planner, {"weather": "WeatherNode", "booking": "BookingNode"})
    graph.add_edge("WeatherNode", "PlannerNode")
    graph.add_edge("BookingNode", END)
    app = graph.compile(
        checkpointer=InMemorySaver(),
        interrupt_before=["ManualApproval"],
        interrupt_after=["CheckpointReview"],
        name="travel_planner_graph",
    )

    result = app.invoke({"city": "Mysore"}, config={"configurable": {"thread_id": "test-thread-001"}})

    assert result is not None
    spans = exporter.get_finished_spans()
    graph_spans = [span for span in spans if span.name == "LangGraph Graph: travel_planner_graph"]
    node_spans = [span for span in spans if span.name.startswith("LangGraph Node:")]
    assert len(graph_spans) == 1
    assert node_spans

    graph_span = graph_spans[0]
    assert graph_span.attributes["agentsre.span_kind"] == "AGENT"
    assert graph_span.attributes["agentsre.agent_name"] == "travel_planner_graph"
    assert graph_span.attributes["agentsre.langgraph.graph_name"] == "travel_planner_graph"
    registered_nodes = json.loads(graph_span.attributes["agentsre.langgraph.registered_nodes"])
    registered_by_name = {node["node_name"]: node for node in registered_nodes}
    assert registered_by_name["PlannerNode"]["classification"] == "agent"
    assert registered_by_name["WeatherNode"]["classification"] == "agent"
    assert registered_by_name["WeatherNode"]["tool_description"] == "Fetches current weather for the requested city."
    assert graph_span.attributes["agentsre.langgraph.has_cycle"] is True
    assert "PlannerNode" in graph_span.attributes["agentsre.langgraph.cycle_nodes"]
    assert "ManualApproval" in graph_span.attributes["agentsre.langgraph.interrupt_before"]
    assert "CheckpointReview" in graph_span.attributes["agentsre.langgraph.interrupt_after"]
    assert graph_span.attributes["agentsre.langgraph.checkpoint_enabled"] is True

    planner_spans = [span for span in node_spans if span.attributes.get("agentsre.langgraph.node_name") == "PlannerNode"]
    weather_spans = [span for span in node_spans if span.attributes.get("agentsre.langgraph.node_name") == "WeatherNode"]
    booking_spans = [span for span in node_spans if span.attributes.get("agentsre.langgraph.node_name") == "BookingNode"]
    assert planner_spans[0].attributes["agentsre.span_kind"] == "AGENT"
    assert sorted(span.attributes["agentsre.iteration_count"] for span in planner_spans) == [1, 2]
    assert weather_spans[0].attributes["agentsre.span_kind"] == "AGENT"
    assert booking_spans[0].attributes["agentsre.span_kind"] == "AGENT"

    conditional_spans = [
        span
        for span in spans
        if span.name.startswith("LangGraph Conditional Edge:")
        and span.attributes.get("agentsre.langgraph.conditional_source") == "PlannerNode"
    ]
    assert {span.attributes["agentsre.langgraph.selected_edge"] for span in conditional_spans} == {"weather", "booking"}
    assert all(span.attributes["agentsre.span_kind"] == "REASONING" for span in conditional_spans)
    assert any(span.attributes.get("agentsre.langgraph.cycle_detected") is True for span in node_spans)


def test_langgraph_classifies_only_langchain_tool_objects_as_tools() -> None:
    langgraph_instrumentor = importlib.import_module("agentsre_sdk.instrumentors.langgraph")

    from langchain_core.tools import tool

    def weather_tool_node(state: dict[str, object]) -> dict[str, object]:
        return {**state, "weather": "cloudy"}

    @tool
    def weather_lookup(city: str) -> str:
        """Retrieves current weather conditions for a city."""
        return f"cloudy in {city}"

    assert langgraph_instrumentor._classify_node("WeatherToolNode", weather_tool_node) == "agent"
    assert langgraph_instrumentor._classify_node("WeatherLookup", weather_lookup) == "tool"


def test_langgraph_node_names_do_not_drive_llm_or_tool_classification() -> None:
    langgraph_instrumentor = importlib.import_module("agentsre_sdk.instrumentors.langgraph")

    def hallucination_llm_node(state: dict[str, object]) -> dict[str, object]:
        return state

    def weather_lookup_node(state: dict[str, object]) -> dict[str, object]:
        return state

    assert langgraph_instrumentor._classify_node("HallucinationLLMNode", hallucination_llm_node) == "agent"
    assert langgraph_instrumentor._classify_node("WeatherLookupNode", weather_lookup_node) == "agent"


def test_langgraph_fallback_classification_avoids_domain_specific_labels() -> None:
    langgraph_instrumentor = importlib.import_module("agentsre_sdk.instrumentors.langgraph")

    assert langgraph_instrumentor._tool_type("WeatherLookupNode") == "Tool"
    assert langgraph_instrumentor._tool_type("BookingNode") == "Tool"
    assert langgraph_instrumentor._tool_type("ReservationNode") == "Tool"
    assert langgraph_instrumentor._tool_type("SearchNode") == "Search"
    assert langgraph_instrumentor._tool_type("HttpRequestNode") == "REST API"


def test_langgraph_classifies_direct_model_objects_as_llm() -> None:
    langgraph_instrumentor = importlib.import_module("agentsre_sdk.instrumentors.langgraph")

    class ChatOpenAI:
        def invoke(self, value: object) -> object:
            return value

    ChatOpenAI.__module__ = "langchain_openai.chat_models.base"

    assert langgraph_instrumentor._classify_node("ModelNode", ChatOpenAI()) == "llm"


def test_langgraph_direct_stream_creates_one_graph_span() -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))

    langgraph_instrumentor = importlib.import_module("agentsre_sdk.instrumentors.langgraph")
    langgraph_instrumentor.instrument(tracer_provider)

    from langgraph.graph import END, StateGraph

    def planner(state: dict[str, object]) -> dict[str, object]:
        return {**state, "plan": "streamed"}

    graph = StateGraph(dict)
    graph.add_node("PlannerNode", planner)
    graph.set_entry_point("PlannerNode")
    graph.add_edge("PlannerNode", END)
    app = graph.compile(name="stream_graph")

    events = list(app.stream({"city": "Mysore"}))

    assert events
    spans = exporter.get_finished_spans()
    graph_spans = [span for span in spans if span.name == "LangGraph Graph: stream_graph"]
    assert len(graph_spans) == 1
    assert graph_spans[0].attributes["agentsre.span_kind"] == "AGENT"


@pytest.mark.asyncio
async def test_langgraph_async_invoke_is_wrapped() -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))

    langgraph_instrumentor = importlib.import_module("agentsre_sdk.instrumentors.langgraph")
    langgraph_instrumentor.instrument(tracer_provider)

    from langgraph.graph import END, StateGraph

    async def async_node(state: dict[str, object]) -> dict[str, object]:
        return {**state, "done": True}

    graph = StateGraph(dict)
    graph.add_node("AsyncNode", async_node)
    graph.set_entry_point("AsyncNode")
    graph.add_edge("AsyncNode", END)
    app = graph.compile(name="async_graph")

    result = await app.ainvoke({"city": "Mysore"})

    assert result["done"] is True
    spans = exporter.get_finished_spans()
    assert any(span.attributes.get("agentsre.span_kind") == "AGENT" for span in spans)
    assert any(span.attributes.get("agentsre.langgraph.node_name") == "AsyncNode" for span in spans)
