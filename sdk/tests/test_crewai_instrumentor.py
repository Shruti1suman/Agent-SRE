from types import SimpleNamespace

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentsre_sdk.instrumentors import crewai


def test_crewai_bridge_emits_schema_compatible_agent_tool_memory_and_llm_spans() -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    bridge = crewai._CrewAISpanBridge(tracer_provider)
    tool = SimpleNamespace(name="flight_inventory_search", description="Searches approved inventory.", args={"origin": "string"})
    agent = SimpleNamespace(role="TravelCoordinator", goal="Coordinate travel", tools=[tool])
    crew = SimpleNamespace(name="travel_ops_crew", process="sequential", agents=[agent], tasks=[])

    bridge.start_crew(crew, SimpleNamespace(crew=crew))
    bridge.start_agent(agent, SimpleNamespace(agent=agent, task_id="task-1"))
    bridge.finish_agent(agent, SimpleNamespace(agent=agent, output="agent done", task_id="task-1"))
    bridge.start_tool(tool, SimpleNamespace(tool=tool, tool_args={"origin": "Bengaluru"}))
    bridge.finish_tool(tool, SimpleNamespace(tool=tool, output="SB-218 available"))
    bridge.start_memory(crew, SimpleNamespace(query="policy memory"))
    bridge.finish_memory(crew, SimpleNamespace(results=[{"text": "Policy evidence", "source": "policy.txt"}]))
    bridge.start_llm(crew, SimpleNamespace(model="gpt-4o-mini", provider="openai", prompt="Summarize"))
    bridge.finish_llm(crew, SimpleNamespace(output="done", finish_reason="stop", input_tokens=5, output_tokens=3))
    bridge.finish_crew(crew, SimpleNamespace(crew=crew, output="crew done"))

    spans = {span.name: span for span in exporter.get_finished_spans()}

    crew_span = spans["CrewAI Crew: travel_ops_crew"]
    agent_span = spans["CrewAI Agent: TravelCoordinator"]
    tool_span = spans["CrewAI Tool: flight_inventory_search"]
    memory_span = spans["CrewAI Memory: retrieve"]
    llm_span = spans["CrewAI LLM: gpt-4o-mini"]

    assert crew_span.attributes["agentsre.span_kind"] == "AGENT"
    assert crew_span.attributes["agentsre.agent_type"] == "CrewAI.Crew"
    assert "TravelCoordinator" in crew_span.attributes["agentsre.crewai.registered_agents"]
    assert "flight_inventory_search" in crew_span.attributes["agentsre.crewai.registered_tools"]
    assert agent_span.attributes["agentsre.agent_type"] == "CrewAI.Agent"
    assert tool_span.attributes["agentsre.span_kind"] == "TOOL"
    assert tool_span.attributes["tool.status"] == "SUCCESS"
    assert tool_span.attributes["tool.output"] == '"SB-218 available"'
    assert memory_span.attributes["agentsre.span_kind"] == "MEMORY"
    assert memory_span.attributes["retrieval.documents"]
    assert llm_span.attributes["agentsre.span_kind"] == "LLM"
    assert llm_span.attributes["finish_reason"] == "stop"
    assert llm_span.attributes["input_tokens"] == 5


def test_crewai_llm_result_attrs_extract_nested_usage() -> None:
    event = SimpleNamespace(
        response={
            "choices": [{"finish_reason": "stop", "message": {"content": "done"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        }
    )

    attrs = crewai._llm_result_attrs(event)

    assert attrs["finish_reason"] == "stop"
    assert attrs["input_tokens"] == 11
    assert attrs["output_tokens"] == 7
    assert attrs["total_tokens"] == 18


def test_crewai_tool_schema_normalizes_pydantic_model_classes() -> None:
    class InventoryLookup:
        @classmethod
        def model_json_schema(cls):
            return {
                "properties": {
                    "origin": {"title": "Origin", "type": "string"},
                    "destination": {"title": "Destination", "type": "string"},
                    "travel_date": {"title": "Travel Date", "type": "string"},
                }
            }

    schema = crewai._tool_schema(InventoryLookup)

    assert schema == {
        "origin": {"title": "Origin", "type": "string"},
        "destination": {"title": "Destination", "type": "string"},
        "travel_date": {"title": "Travel Date", "type": "string"},
    }


def test_crewai_fallback_tool_type_avoids_domain_specific_labels() -> None:
    assert crewai._infer_tool_type("reservation_submission") == "Tool"
    assert crewai._infer_tool_type("booking_tool") == "Tool"
    assert crewai._infer_tool_type("weather_lookup") == "Tool"
    assert crewai._infer_tool_type("inventory_search") == "Search"
    assert crewai._infer_tool_type("knowledge_lookup") == "Memory"
    assert crewai._infer_tool_type("mcp_fetch") == "MCP"


def test_crewai_task_name_prefers_readable_generic_label() -> None:
    agent = SimpleNamespace(role="Coordinator")
    task = SimpleNamespace(id="task-1", name=None, description="Collect the required context and choose the next action.", agent=agent)

    assert crewai._task_name(task, SimpleNamespace(task=task)) == "Coordinator: Collect the required context and choose the next action."


def test_crewai_task_name_truncates_long_descriptions() -> None:
    task = SimpleNamespace(id="task-1", name=None, description=" ".join(["long"] * 80), agent=SimpleNamespace(role="Worker"))

    label = crewai._task_name(task, SimpleNamespace(task=task))

    assert len(label) <= 120
    assert label.endswith("...")


def test_crewai_sequential_task_order_populates_previous_and_next_nodes() -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    bridge = crewai._CrewAISpanBridge(tracer_provider)
    agent = SimpleNamespace(role="Coordinator")
    task_one = SimpleNamespace(id="task-1", name="Collect context", description=None, agent=agent)
    task_two = SimpleNamespace(id="task-2", name="Prepare response", description=None, agent=agent)
    crew = SimpleNamespace(name="crew", process="sequential", agents=[agent], tasks=[task_one, task_two])

    bridge.start_crew(crew, SimpleNamespace(crew=crew))
    bridge.start_task(task_one, SimpleNamespace(task=task_one))
    bridge.finish_task(task_one, SimpleNamespace(task=task_one, output="done"))
    bridge.start_task(task_two, SimpleNamespace(task=task_two))
    bridge.finish_task(task_two, SimpleNamespace(task=task_two, output="done"))
    bridge.finish_crew(crew, SimpleNamespace(crew=crew, output="done"))

    spans = {span.name: span for span in exporter.get_finished_spans()}

    first = spans["CrewAI Task: Collect context"]
    second = spans["CrewAI Task: Prepare response"]
    assert first.attributes["next_node"] == "Prepare response"
    assert "previous_node" not in first.attributes
    assert second.attributes["previous_node"] == "Collect context"
    assert "next_node" not in second.attributes


def test_crewai_nested_subcrew_task_order_stays_separate() -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    bridge = crewai._CrewAISpanBridge(tracer_provider)
    agent = SimpleNamespace(role="Worker")
    parent_one = SimpleNamespace(id="parent-1", name="Parent one", agent=agent)
    parent_two = SimpleNamespace(id="parent-2", name="Parent two", agent=agent)
    child_one = SimpleNamespace(id="child-1", name="Child one", agent=agent)
    child_two = SimpleNamespace(id="child-2", name="Child two", agent=agent)
    parent_crew = SimpleNamespace(name="parent", process="sequential", agents=[agent], tasks=[parent_one, parent_two])
    child_crew = SimpleNamespace(name="child", process="sequential", agents=[agent], tasks=[child_one, child_two])

    bridge.start_crew(parent_crew, SimpleNamespace(crew=parent_crew))
    bridge.start_task(parent_one, SimpleNamespace(task=parent_one))
    bridge.finish_task(parent_one, SimpleNamespace(task=parent_one, output="done"))
    bridge.start_crew(child_crew, SimpleNamespace(crew=child_crew))
    bridge.start_task(child_one, SimpleNamespace(task=child_one))
    bridge.finish_task(child_one, SimpleNamespace(task=child_one, output="done"))
    bridge.start_task(child_two, SimpleNamespace(task=child_two))
    bridge.finish_task(child_two, SimpleNamespace(task=child_two, output="done"))
    bridge.finish_crew(child_crew, SimpleNamespace(crew=child_crew, output="done"))
    bridge.start_task(parent_two, SimpleNamespace(task=parent_two))
    bridge.finish_task(parent_two, SimpleNamespace(task=parent_two, output="done"))
    bridge.finish_crew(parent_crew, SimpleNamespace(crew=parent_crew, output="done"))

    spans = {span.name: span for span in exporter.get_finished_spans()}

    assert spans["CrewAI Task: Parent one"].attributes["next_node"] == "Parent two"
    assert spans["CrewAI Task: Parent two"].attributes["previous_node"] == "Parent one"
    assert spans["CrewAI Task: Child one"].attributes["next_node"] == "Child two"
    assert spans["CrewAI Task: Child two"].attributes["previous_node"] == "Child one"


def test_crewai_tool_type_ignores_event_lifecycle_names() -> None:
    tool = SimpleNamespace(name="reservation_submission", description="Submit data.")
    attrs = crewai._tool_attrs(tool, SimpleNamespace(tool=tool, type="tool_usage_finished"))

    assert attrs["tool.type"] == "Tool"


def test_crewai_llm_context_parents_provider_span_and_processor_can_dedupe() -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    bridge = crewai._CrewAISpanBridge(tracer_provider)
    provider_tracer = tracer_provider.get_tracer("provider")

    bridge.start_llm(None, SimpleNamespace(model="gpt-4o-mini", provider="openai", prompt="hello", call_id="call-1"))
    with provider_tracer.start_as_current_span("ChatCompletion") as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.provider", "openai")
        span.set_attribute("llm.model_name", "gpt-4o-mini")
        span.set_attribute("input_tokens", 13)
        span.set_attribute("output_tokens", 5)
        span.set_attribute("finish_reason", "stop")
    bridge.finish_llm(None, SimpleNamespace(output="done", call_id="call-1"))

    spans = {span.name: span for span in exporter.get_finished_spans()}
    wrapper = spans["CrewAI LLM: gpt-4o-mini"]
    provider = spans["ChatCompletion"]

    assert provider.context.trace_id == wrapper.context.trace_id
    assert provider.parent.span_id == wrapper.context.span_id


def test_crewai_resolves_core_event_classes() -> None:
    crewai_events = pytest.importorskip("crewai.events")

    resolved, missing = crewai._resolve_event_classes(crewai_events)

    for event_name in [
        "CrewKickoffStartedEvent",
        "CrewKickoffCompletedEvent",
        "TaskStartedEvent",
        "TaskFailedEvent",
        "ToolUsageStartedEvent",
        "ToolUsageFinishedEvent",
        "LiteAgentExecutionStartedEvent",
        "LiteAgentExecutionCompletedEvent",
    ]:
        assert event_name in resolved
    assert "CrewKickoffStartedEvent" not in missing


def test_crewai_instrumentor_dispatches_event_bus_events_synchronously() -> None:
    crewai_events = pytest.importorskip("crewai.events")
    from crewai.events import crewai_event_bus

    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))

    result = crewai.instrument(tracer_provider)

    assert result["status"] == "instrumented"
    assert int(result["registered_events"]) > 0

    tool = SimpleNamespace(name="inventory_lookup", description="Finds inventory.", args={"origin": "string"})
    agent = SimpleNamespace(role="TravelPlannerAgent", goal="Plan travel", tools=[tool])
    crew = SimpleNamespace(name="simple_crew", process="sequential", agents=[agent], tasks=[])
    task = SimpleNamespace(id="task-1", name=None, description="Plan a trip.", agent=agent, expected_output="Plan")

    with crewai_event_bus.scoped_handlers():
        crewai_event_bus.emit(crew, crewai_events.CrewKickoffStartedEvent(crew_name="simple_crew", crew=crew, inputs={}))
        crewai_event_bus.emit(agent, crewai_events.LiteAgentExecutionStartedEvent(agent_info={"role": "TravelPlannerAgent"}, tools=None, messages="start"))
        crewai_event_bus.emit(agent, crewai_events.LiteAgentExecutionCompletedEvent(agent_info={"role": "TravelPlannerAgent"}, output="done"))
        crewai_event_bus.emit(task, crewai_events.TaskStartedEvent(context=None, task=task))
        crewai_event_bus.emit(task, crewai_events.TaskFailedEvent(error="controlled test finish", task=task))
        crewai_event_bus.emit(tool, crewai_events.ToolUsageStartedEvent(tool_name="inventory_lookup", tool_args={"origin": "Bengaluru"}))
        crewai_event_bus.emit(
            tool,
            crewai_events.ToolUsageFinishedEvent(
                tool_name="inventory_lookup",
                tool_args={"origin": "Bengaluru"},
                started_at="2026-01-01T00:00:00Z",
                finished_at="2026-01-01T00:00:01Z",
                output="available",
            ),
        )
        crewai_event_bus.emit(crew, crewai_events.CrewKickoffCompletedEvent(crew_name="simple_crew", crew=crew, output="done"))

    spans = {span.name: span for span in exporter.get_finished_spans()}

    assert spans["CrewAI Crew: simple_crew"].attributes["agentsre.agent_type"] == "CrewAI.Crew"
    assert spans["CrewAI Agent: TravelPlannerAgent"].attributes["agentsre.agent_type"] == "CrewAI.Agent"
    assert spans["CrewAI Task: TravelPlannerAgent: Plan a trip."].attributes["agentsre.span_kind"] == "REASONING"
    assert spans["CrewAI Tool: inventory_lookup"].attributes["agentsre.span_kind"] == "TOOL"
    assert spans["CrewAI Tool: inventory_lookup"].attributes["tool.output"] == '"available"'
