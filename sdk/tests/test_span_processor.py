import json
import time

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode

from agentsre_sdk.config import SDKConfig
from agentsre_sdk.instrumentors.registry import clear_available_tools, register_available_tools
from agentsre_sdk.processors import span_processor
from agentsre_sdk.processors.span_processor import AgentSRESpanProcessor
from agentsre_sdk.schema.models import Resource


class CaptureExporter:
    def __init__(self) -> None:
        self.payloads = []
        self.shutdown_calls = 0

    def export(self, payload) -> bool:
        self.payloads.append(payload)
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        return None


def test_processor_generates_agent_id_and_exports_canonical_langgraph_payload() -> None:
    config = SDKConfig(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="dev",
        backend_url="https://example.com/ingest",
        api_key="test-key",
        workflow_id="wf_trip_planner",
        session_id="session_001",
    )
    resource = Resource(
        sdk_version="1.0.0",
        plugin_version="1.0.0",
        framework="LangGraph",
        framework_version="1.1.10",
        language="Python",
        host_name="host",
        process_id=123,
        os="Windows",
        cpu_architecture="x86_64",
        runtime="Python",
        runtime_version="3.13.0",
        container_id=None,
        kubernetes_pod=None,
        cloud_provider=None,
    )
    exporter = CaptureExporter()
    processor = AgentSRESpanProcessor(config, exporter, resource)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("PlannerNode") as span:
        span.set_attribute("agentsre.span_kind", "AGENT")
        span.set_attribute("agentsre.langgraph.graph_name", "travel_planner_graph")
        span.set_attribute("agentsre.langgraph.node_name", "PlannerNode")
        span.set_attribute("agentsre.agent_role", "Planner")
        span.set_attribute("reasoning.step", 1)
        span.set_attribute("previous_node", "")
        span.set_attribute("next_node", "WeatherNode")
        span.set_attribute("decision.type", "Node Execution")

    processor.force_flush()

    payload = exporter.payloads[0].model_dump(mode="json")
    span_payload = payload["spans"][0]
    assert payload["resource"]["framework"] == "LangGraph"
    assert span_payload["span_kind"] == "AGENT"
    assert span_payload["agent"]["agent_id"].startswith("agent_")
    assert span_payload["agent"]["agent_id"] == "agent_b09911dd1db9457f"
    assert span_payload["reasoning"]["node_name"] == "PlannerNode"
    assert "span_type" not in span_payload
    assert "graph" not in span_payload
    assert "graph_node" not in span_payload


def test_processor_drops_duplicate_langgraph_wrappers_and_keeps_useful_children() -> None:
    config = SDKConfig(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="dev",
        backend_url="https://example.com/ingest",
        api_key="test-key",
        workflow_id="wf_trip_planner",
        session_id="session_001",
    )
    resource = Resource(
        sdk_version="1.0.0",
        plugin_version="1.0.0",
        framework="LangGraph",
        framework_version="1.1.10",
        language="Python",
        host_name="host",
        process_id=123,
        os="Windows",
        cpu_architecture="x86_64",
        runtime="Python",
        runtime_version="3.13.0",
        container_id=None,
        kubernetes_pod=None,
        cloud_provider=None,
    )
    exporter = CaptureExporter()
    processor = AgentSRESpanProcessor(config, exporter, resource)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("LangGraph Graph: travel_planner_graph") as custom_graph:
        custom_graph.set_attribute("agentsre.span_kind", "AGENT")
        custom_graph.set_attribute("agentsre.langgraph.graph_name", "travel_planner_graph")
        custom_graph.set_attribute("agentsre.agent_name", "travel_planner_graph")
        custom_graph.set_attribute("agentsre.agent_role", "Graph")
        custom_graph.set_attribute("agentsre.agent_type", "LangGraph")
        custom_graph.set_attribute("node.name", "travel_planner_graph")
        custom_graph.set_attribute("decision.type", "Graph Execution")

        with tracer.start_as_current_span("travel_planner_graph") as plain_graph:
            plain_graph.set_attribute("openinference.span.kind", "CHAIN")

        with tracer.start_as_current_span("LangGraph Node: PlannerNode") as custom_planner:
            custom_planner.set_attribute("agentsre.span_kind", "AGENT")
            custom_planner.set_attribute("agentsre.langgraph.node_name", "PlannerNode")
            custom_planner.set_attribute("agentsre.agent_name", "PlannerNode")
            custom_planner.set_attribute("agentsre.agent_role", "Planner")
            custom_planner.set_attribute("agentsre.agent_type", "LangGraphNode")
            custom_planner.set_attribute("node.name", "PlannerNode")
            custom_planner.set_attribute("decision.type", "Node Execution")

        with tracer.start_as_current_span("PlannerNode") as plain_planner:
            plain_planner.set_attribute("openinference.span.kind", "CHAIN")
            with tracer.start_as_current_span("openai.chat.completions.create") as llm_span:
                llm_span.set_attribute("openinference.span.kind", "LLM")
                llm_span.set_attribute("llm.provider", "openai")
                llm_span.set_attribute("llm.model_name", "gpt-4o-mini")

        with tracer.start_as_current_span("LangGraph Node: WeatherNode") as custom_weather:
            custom_weather.set_attribute("agentsre.span_kind", "TOOL")
            custom_weather.set_attribute("agentsre.langgraph.node_name", "WeatherNode")
            custom_weather.set_attribute("tool.name", "WeatherNode")
            custom_weather.set_attribute("tool.type", "Weather")

        with tracer.start_as_current_span("WeatherNode") as tool_span:
            tool_span.set_attribute("openinference.span.kind", "TOOL")
            tool_span.set_attribute("tool.name", "WeatherNode")
            tool_span.set_attribute("tool.type", "Weather")
            tool_span.set_attribute("tool.output", "cloudy")

    processor.force_flush()

    payload = exporter.payloads[0].model_dump(mode="json")
    names = [span["span_name"] for span in payload["spans"]]
    planner = next(span for span in payload["spans"] if span["span_name"] == "LangGraph Node: PlannerNode")
    llm = next(span for span in payload["spans"] if span["span_name"] == "openai.chat.completions.create")

    assert names.count("LangGraph Graph: travel_planner_graph") == 1
    assert "travel_planner_graph" not in names
    assert names.count("LangGraph Node: PlannerNode") == 1
    assert "PlannerNode" not in names
    assert "openai.chat.completions.create" in names
    assert names.count("WeatherNode") == 1
    assert llm["span_kind"] == "LLM"
    assert llm["parent_span_id"] == planner["span_id"]
    assert not any("span_type" in span or "graph" in span or "graph_node" in span for span in payload["spans"])


def test_processor_maps_tool_description_attributes() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("WeatherAPI") as span:
        span.set_attribute("openinference.span.kind", "TOOL")
        span.set_attribute("tool.name", "WeatherAPI")
        span.set_attribute("tool.type", "REST API")
        span.set_attribute("tool.description", "Fetches current weather for a city.")

    with tracer.start_as_current_span("BookingTool") as span:
        span.set_attribute("openinference.span.kind", "TOOL")
        span.set_attribute("tool.name", "BookingTool")
        span.set_attribute("tool_description", "Finds available hotel and transport options.")

    processor.force_flush()

    spans = [span for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]]
    descriptions = {span["tool"]["tool_name"]: span["tool"]["tool_description"] for span in spans}
    assert descriptions["WeatherAPI"] == "Fetches current weather for a city."
    assert descriptions["BookingTool"] == "Finds available hotel and transport options."


def test_processor_fallback_classification_avoids_domain_specific_labels() -> None:
    assert span_processor._infer_tool_type("weather_lookup") == "Tool"
    assert span_processor._infer_tool_type("reservation_submission") == "Tool"
    assert span_processor._infer_tool_type("booking_tool") == "Tool"
    assert span_processor._infer_tool_type("inventory_search") == "Search"
    assert span_processor._infer_tool_type("payments_api_request") == "REST API"
    assert span_processor._infer_agent_role("BookingAgent") == "Agent"
    assert span_processor._infer_agent_role("WorkerAgent") == "Worker"


def test_processor_maps_direct_and_nested_finish_reason() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("DirectLLM") as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.provider", "openai")
        span.set_attribute("llm.model_name", "gpt-4o-mini")
        span.set_attribute("finish_reason", "stop")

    with tracer.start_as_current_span("NestedLLM") as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.provider", "openai")
        span.set_attribute("llm.model_name", "gpt-4o-mini")
        span.set_attribute("output.value", '{"choices": [{"message": {"content": "done"}, "finish_reason": "length"}]}')

    processor.force_flush()

    spans = [span for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]]
    finish_reasons = {span["span_name"]: span["llm"]["finish_reason"] for span in spans}
    assert finish_reasons["DirectLLM"] == "stop"
    assert finish_reasons["NestedLLM"] == "length"


def test_processor_keeps_tokens_but_leaves_cost_for_backend() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("ChatCompletion") as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.provider", "openai")
        span.set_attribute("llm.model_name", "gpt-4o-mini")
        span.set_attribute("input_tokens", 10)
        span.set_attribute("output_tokens", 5)

    processor.force_flush()

    llm = exporter.payloads[0].model_dump(mode="json")["spans"][0]["llm"]
    assert llm["input_tokens"] == 10
    assert llm["output_tokens"] == 5
    assert llm["total_tokens"] == 15
    assert llm["estimated_cost"] is None


def test_processor_flush_ready_batches_exports_completed_trace() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("PlannerNode") as span:
        span.set_attribute("agentsre.span_kind", "AGENT")
        span.set_attribute("agentsre.langgraph.node_name", "PlannerNode")

    assert exporter.payloads == []

    processor.flush_ready_batches()

    assert len(exporter.payloads) == 1


def test_processor_periodic_flush_exports_completed_trace() -> None:
    config = SDKConfig(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="dev",
        backend_url="https://example.com/ingest",
        api_key="test-key",
        workflow_id="wf_trip_planner",
        session_id="session_001",
        export_interval_seconds=0.01,
    )
    exporter = CaptureExporter()
    processor = AgentSRESpanProcessor(config, exporter, _resource())
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer(__name__)

    try:
        with tracer.start_as_current_span("PlannerNode") as span:
            span.set_attribute("agentsre.span_kind", "AGENT")
            span.set_attribute("agentsre.langgraph.node_name", "PlannerNode")

        deadline = time.monotonic() + 1.0
        while not exporter.payloads and time.monotonic() < deadline:
            time.sleep(0.01)

        assert len(exporter.payloads) == 1
    finally:
        processor.shutdown()


def test_processor_idle_timeout_exports_trace_with_open_parent() -> None:
    config = SDKConfig(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="dev",
        backend_url="https://example.com/ingest",
        api_key="test-key",
        workflow_id="wf_trip_planner",
        session_id="session_001",
        batch_timeout_seconds=0.001,
    )
    exporter = CaptureExporter()
    processor = AgentSRESpanProcessor(config, exporter, _resource())
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer(__name__)

    try:
        with tracer.start_as_current_span("PlannerNode") as parent:
            parent.set_attribute("agentsre.span_kind", "AGENT")
            parent.set_attribute("agentsre.langgraph.node_name", "PlannerNode")
            with tracer.start_as_current_span("ChatCompletion") as child:
                child.set_attribute("openinference.span.kind", "LLM")
                child.set_attribute("llm.model_name", "gpt-4o-mini")

            time.sleep(0.01)
            processor.flush_ready_batches()

            assert len(exporter.payloads) == 1
            assert exporter.payloads[0].spans[0].span_name == "ChatCompletion"
    finally:
        processor.shutdown()


def test_processor_builds_execution_available_tools_and_agents_from_langgraph_registry() -> None:
    exporter, processor, tracer = _processor_tracer()
    registered_nodes = [
        {
            "node_name": "PlannerNode",
            "classification": "agent",
            "agent_role": "Planner",
            "agent_type": "LangGraphNode",
            "tool_type": "Tool",
            "tool_description": None,
            "tool_arguments": None,
        },
        {
            "node_name": "WeatherToolNode",
            "classification": "tool",
            "agent_role": "Agent",
            "agent_type": "LangGraphNode",
            "tool_type": "Weather",
            "tool_description": "Aggregates weather lookup results with planner notes.",
            "tool_arguments": None,
        },
        {
            "node_name": "UnexecutedBookingNode",
            "classification": "tool",
            "agent_role": "Agent",
            "agent_type": "LangGraphNode",
            "tool_type": "Booking",
            "tool_description": "Finds hotel and transport options.",
            "tool_arguments": {"city": "Mysore"},
        },
    ]

    with tracer.start_as_current_span("LangGraph Graph: travel_planner_graph") as graph_span:
        graph_span.set_attribute("agentsre.span_kind", "AGENT")
        graph_span.set_attribute("agentsre.langgraph.graph_name", "travel_planner_graph")
        graph_span.set_attribute("agentsre.langgraph.registered_nodes", json.dumps(registered_nodes))
        graph_span.set_attribute("agentsre.agent_name", "travel_planner_graph")
        graph_span.set_attribute("agentsre.agent_role", "Graph")
        graph_span.set_attribute("agentsre.agent_type", "LangGraph")
        graph_span.set_attribute("node.name", "travel_planner_graph")

        with tracer.start_as_current_span("LangGraph Node: PlannerNode") as planner_span:
            planner_span.set_attribute("agentsre.span_kind", "AGENT")
            planner_span.set_attribute("agentsre.langgraph.graph_name", "travel_planner_graph")
            planner_span.set_attribute("agentsre.langgraph.node_name", "PlannerNode")
            planner_span.set_attribute("agentsre.agent_name", "PlannerNode")
            planner_span.set_attribute("agentsre.agent_role", "Planner")
            planner_span.set_attribute("agentsre.agent_type", "LangGraphNode")

        with tracer.start_as_current_span("LangGraph Node: WeatherToolNode") as tool_span:
            tool_span.set_attribute("agentsre.span_kind", "TOOL")
            tool_span.set_attribute("agentsre.langgraph.graph_name", "travel_planner_graph")
            tool_span.set_attribute("agentsre.langgraph.node_name", "WeatherToolNode")
            tool_span.set_attribute("tool.name", "WeatherToolNode")
            tool_span.set_attribute("tool.type", "Weather")
            tool_span.set_attribute("tool.description", "Aggregates weather lookup results with planner notes.")

    processor.force_flush()

    payload = exporter.payloads[0].model_dump(mode="json")
    execution = payload["execution"]
    available_tools = {tool["tool_name"]: tool for tool in execution["available_tools"]}
    available_agents = {agent["agent_name"]: agent for agent in execution["available_agents"]}
    graph_span = next(span for span in payload["spans"] if span["span_name"] == "LangGraph Graph: travel_planner_graph")
    planner_span = next(span for span in payload["spans"] if span["span_name"] == "LangGraph Node: PlannerNode")
    tool_payload = next(span["tool"] for span in payload["spans"] if span["span_name"] == "LangGraph Node: WeatherToolNode")

    assert set(available_tools) == {"WeatherToolNode", "UnexecutedBookingNode"}
    assert available_tools["WeatherToolNode"]["tool_id"].startswith("tool_")
    assert available_tools["WeatherToolNode"]["tool_description"] == "Aggregates weather lookup results with planner notes."
    assert available_tools["UnexecutedBookingNode"]["tool_arguments"] == {"city": {"type": "string"}}
    assert "tool_id" not in tool_payload
    assert available_agents["travel_planner_graph"]["agent_id"] == graph_span["agent"]["agent_id"]
    assert available_agents["PlannerNode"]["agent_id"] == planner_span["agent"]["agent_id"]


def test_processor_includes_registered_langchain_tools() -> None:
    class SearchTool:
        name = "weather_lookup"
        description = "Retrieves current weather conditions for a specified city."
        args = {"city": "Mysore"}
        metadata = {"tool_type": "Weather"}

    clear_available_tools()
    try:
        register_available_tools([SearchTool()], framework="LangChain")
        exporter, processor, tracer = _processor_tracer()

        with tracer.start_as_current_span("PlannerNode") as span:
            span.set_attribute("agentsre.span_kind", "AGENT")
            span.set_attribute("agentsre.langgraph.node_name", "PlannerNode")

        processor.force_flush()

        available_tools = exporter.payloads[0].model_dump(mode="json")["execution"]["available_tools"]
        weather_lookup = next(tool for tool in available_tools if tool["tool_name"] == "weather_lookup")
        assert weather_lookup["tool_id"].startswith("tool_")
        assert weather_lookup["tool_type"] == "Weather"
        assert weather_lookup["tool_description"] == "Retrieves current weather conditions for a specified city."
        assert weather_lookup["tool_arguments"] == {"city": {"type": "string"}}
    finally:
        clear_available_tools()


def test_processor_does_not_discover_unregistered_loaded_langchain_tools() -> None:
    from langchain_core.tools import tool

    @tool
    def weather_lookup(city: str) -> str:
        """Retrieves current weather conditions for a specified city."""
        return f"cloudy in {city}"

    @tool
    def calculator_tool(expression: str) -> str:
        """Evaluates simple arithmetic expressions for calculator tasks."""
        return "42"

    clear_available_tools()
    try:
        exporter, processor, tracer = _processor_tracer()

        with tracer.start_as_current_span("PlannerNode") as span:
            span.set_attribute("agentsre.span_kind", "AGENT")
            span.set_attribute("agentsre.langgraph.node_name", "PlannerNode")

        processor.force_flush()

        available_tools = exporter.payloads[0].model_dump(mode="json")["execution"]["available_tools"]
        assert available_tools == []
    finally:
        clear_available_tools()


def test_available_tools_ignore_runtime_tool_spans_when_registered_tool_exists() -> None:
    class WeatherLookupTool:
        name = "weather_lookup"
        description = "Mock weather lookup tool."
        args = {"city": {"title": "City", "type": "string"}}

    clear_available_tools()
    try:
        register_available_tools([WeatherLookupTool()], framework="LangChain")
        exporter, processor, tracer = _processor_tracer()

        with tracer.start_as_current_span("weather_lookup") as span:
            span.set_attribute("openinference.span.kind", "TOOL")
            span.set_attribute("tool.name", "weather_lookup")
            span.set_attribute("tool.type", "Weather")
            span.set_attribute("tool.description", "Mock weather lookup tool.")
            span.set_attribute("tool.arguments", "Mysore")
            span.set_attribute("tool.output", "Cloudy, 27C")

        processor.force_flush()

        payload = exporter.payloads[0].model_dump(mode="json")
        available_tools = payload["execution"]["available_tools"]
        runtime_tool = payload["spans"][0]["tool"]

        assert [tool["tool_name"] for tool in available_tools] == ["weather_lookup"]
        assert available_tools[0]["tool_arguments"] == {"city": {"title": "City", "type": "string"}}
        assert available_tools[0]["tool_type"] == "LangChain"
        assert runtime_tool["tool_name"] == "weather_lookup"
        assert runtime_tool["tool_arguments"] == "Mysore"
    finally:
        clear_available_tools()


def test_processor_classification_uses_agentsre_kind_before_openinference_kind() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("LangGraph Node: HallucinationLLMNode") as span:
        span.set_attribute("agentsre.span_kind", "AGENT")
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("agentsre.langgraph.node_name", "HallucinationLLMNode")

    processor.force_flush()

    span_payload = exporter.payloads[0].model_dump(mode="json")["spans"][0]
    assert span_payload["span_kind"] == "AGENT"
    assert span_payload["agent"]["agent_name"] == "HallucinationLLMNode"
    assert span_payload["llm"] is None


def test_processor_uses_structural_llm_tool_and_memory_detection() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("ChatCompletion") as span:
        span.set_attribute("llm.model_name", "gpt-4o-mini")
        span.set_attribute("input_tokens", 10)

    with tracer.start_as_current_span("WeatherLookupNode") as span:
        span.set_attribute("tool.name", "weather_lookup")
        span.set_attribute("tool.arguments", "Mysore")

    with tracer.start_as_current_span("corporate_policy.retrieve") as span:
        span.set_attribute("memory.operation", "retrieve")
        span.set_attribute("retrieval.documents", '[{"text": "policy"}]')

    processor.force_flush()

    spans = {span["span_name"]: span for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]}
    assert spans["ChatCompletion"]["span_kind"] == "LLM"
    assert spans["WeatherLookupNode"]["span_kind"] == "TOOL"
    assert spans["corporate_policy.retrieve"]["span_kind"] == "MEMORY"


def test_processor_deduplicates_available_tools_by_normalized_tool_name() -> None:
    class WeatherLookupTool:
        name = "weather_lookup"
        description = "Registered weather lookup."
        args = {"city": {"type": "string"}}
        metadata = {"tool_type": "Weather"}

    clear_available_tools()
    try:
        register_available_tools([WeatherLookupTool()], framework="LangChain")
        exporter, processor, tracer = _processor_tracer()

        with tracer.start_as_current_span("weather_lookup") as span:
            span.set_attribute("openinference.span.kind", "TOOL")
            span.set_attribute("tool.name", "weather_lookup")
            span.set_attribute("tool.description", "Runtime weather lookup.")
            span.set_attribute("tool.arguments", "Mysore")

        processor.force_flush()

        available_tools = exporter.payloads[0].model_dump(mode="json")["execution"]["available_tools"]
        assert len(available_tools) == 1
        assert available_tools[0]["tool_name"] == "weather_lookup"
        assert available_tools[0]["tool_description"] == "Registered weather lookup."
        assert available_tools[0]["tool_arguments"] == {"city": {"type": "string"}}
    finally:
        clear_available_tools()


def test_processor_drops_duplicate_chatopenai_wrapper_when_chatcompletion_exists() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("LangGraph Node: PlannerNode") as node_span:
        node_span.set_attribute("agentsre.span_kind", "AGENT")
        node_span.set_attribute("agentsre.langgraph.node_name", "PlannerNode")
        with tracer.start_as_current_span("ChatOpenAI") as wrapper:
            wrapper.set_attribute("openinference.span.kind", "LLM")
            wrapper.set_attribute("llm.model_name", "gpt-4o-mini")
            wrapper.set_attribute("input_tokens", 10)
            wrapper.set_attribute("output_tokens", 5)
        with tracer.start_as_current_span("ChatCompletion") as provider_span:
            provider_span.set_attribute("openinference.span.kind", "LLM")
            provider_span.set_attribute("llm.model_name", "gpt-4o-mini")
            provider_span.set_attribute("input_tokens", 10)
            provider_span.set_attribute("output_tokens", 5)

    processor.force_flush()

    names = [span["span_name"] for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]]
    assert "ChatCompletion" in names
    assert "ChatOpenAI" not in names


def test_processor_drops_chatopenai_after_langgraph_parent_remap() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("LangGraph Node: HallucinationLLMNode") as node_span:
        node_span.set_attribute("agentsre.span_kind", "AGENT")
        node_span.set_attribute("agentsre.langgraph.node_name", "HallucinationLLMNode")
        with tracer.start_as_current_span("ChatOpenAI") as wrapper:
            wrapper.set_attribute("openinference.span.kind", "LLM")
            wrapper.set_attribute("llm.model_name", "gpt-4o-mini")
            wrapper.set_attribute("input_tokens", 72)
            wrapper.set_attribute("output_tokens", 278)
            wrapper.set_attribute("total_tokens", 350)
        with tracer.start_as_current_span("HallucinationLLMNode") as plain_wrapper:
            plain_wrapper.set_attribute("openinference.span.kind", "CHAIN")
            with tracer.start_as_current_span("ChatCompletion") as provider_span:
                provider_span.set_attribute("openinference.span.kind", "LLM")
                provider_span.set_attribute("llm.model_name", "gpt-4o-mini")
                provider_span.set_attribute("input_tokens", 72)
                provider_span.set_attribute("output_tokens", 278)
                provider_span.set_attribute("total_tokens", 350)

    processor.force_flush()

    names = [span["span_name"] for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]]
    assert "LangGraph Node: HallucinationLLMNode" in names
    assert "ChatCompletion" in names
    assert "HallucinationLLMNode" not in names
    assert "ChatOpenAI" not in names


def test_processor_drops_real_langchain_llm_wrapper_shape_and_keeps_provider_http_child() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("LangGraph Node: TravelOperationsCoordinator") as node_span:
        node_span.set_attribute("agentsre.span_kind", "AGENT")
        node_span.set_attribute("agentsre.langgraph.node_name", "TravelOperationsCoordinator")

        with tracer.start_as_current_span("TravelOperationsCoordinator") as plain_wrapper:
            plain_wrapper.set_attribute("openinference.span.kind", "CHAIN")
            with tracer.start_as_current_span("model") as model_wrapper:
                model_wrapper.set_attribute("openinference.span.kind", "CHAIN")
                with tracer.start_as_current_span("ChatOpenAI") as wrapper:
                    wrapper.set_attribute("openinference.span.kind", "LLM")
                    wrapper.set_attribute("llm.model_name", "gpt-4o-mini")
                    wrapper.set_attribute("input_tokens", 584)
                    wrapper.set_attribute("output_tokens", 70)
                    wrapper.set_attribute("finish_reason", "tool_calls")

        with tracer.start_as_current_span("ChatCompletion") as provider_span:
            provider_span.set_attribute("openinference.span.kind", "LLM")
            provider_span.set_attribute("llm.model_name", "gpt-4o-mini")
            provider_span.set_attribute("input_tokens", 584)
            provider_span.set_attribute("output_tokens", 70)
            provider_span.set_attribute("finish_reason", "tool_calls")
            with tracer.start_as_current_span("POST") as http_span:
                http_span.set_attribute("url.full", "https://api.openai.com/v1/chat/completions")
                http_span.set_attribute("http.request.method", "POST")
                http_span.set_attribute("http.response.status_code", 200)

    processor.force_flush()

    spans = [span for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]]
    names = [span["span_name"] for span in spans]
    node = next(span for span in spans if span["span_name"] == "LangGraph Node: TravelOperationsCoordinator")
    llm = next(span for span in spans if span["span_name"] == "ChatCompletion")
    http = next(span for span in spans if span["span_name"] == "POST")

    assert names == ["LangGraph Node: TravelOperationsCoordinator", "ChatCompletion", "POST"]
    assert "TravelOperationsCoordinator" not in names
    assert "model" not in names
    assert "ChatOpenAI" not in names
    assert llm["parent_span_id"] == node["span_id"]
    assert http["parent_span_id"] == llm["span_id"]


def test_processor_drops_crewai_llm_wrapper_when_litellm_provider_span_has_usage() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("CrewAI Crew: crew") as crew_span:
        crew_span.set_attribute("agentsre.span_kind", "AGENT")
        crew_span.set_attribute("agentsre.agent_name", "crew")
        crew_span.set_attribute("agentsre.agent_role", "Crew")
        crew_span.set_attribute("agentsre.agent_type", "CrewAI.Crew")
        with tracer.start_as_current_span("CrewAI LLM: gpt-4o-mini") as wrapper:
            wrapper.set_attribute("agentsre.span_kind", "LLM")
            wrapper.set_attribute("agentsre.crewai.llm_event", True)
            wrapper.set_attribute("llm.model_name", "gpt-4o-mini")
            with tracer.start_as_current_span("LiteLLM Completion: openai/gpt-4o-mini") as provider:
                provider.set_attribute("openinference.span.kind", "LLM")
                provider.set_attribute("llm.provider", "openai")
                provider.set_attribute("llm.model_name", "gpt-4o-mini")
                provider.set_attribute("input_tokens", 13)
                provider.set_attribute("output_tokens", 5)
                provider.set_attribute("finish_reason", "stop")

    processor.force_flush()

    payload = exporter.payloads[0].model_dump(mode="json")
    names = [span["span_name"] for span in payload["spans"]]
    llm = next(span for span in payload["spans"] if span["span_name"] == "LiteLLM Completion: openai/gpt-4o-mini")

    assert payload["resource"]["framework"] == "CrewAI"
    assert "CrewAI LLM: gpt-4o-mini" not in names
    assert llm["llm"]["provider"] == "openai"
    assert llm["llm"]["input_tokens"] == 13
    assert llm["llm"]["output_tokens"] == 5
    assert llm["llm"]["total_tokens"] == 18
    assert llm["llm"]["finish_reason"] == "stop"


def test_processor_drops_crewai_llm_wrapper_when_chatcompletion_child_has_usage() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("CrewAI Agent: TravelPlannerAgent") as agent_span:
        agent_span.set_attribute("agentsre.span_kind", "AGENT")
        agent_span.set_attribute("agentsre.agent_name", "TravelPlannerAgent")
        agent_span.set_attribute("agentsre.agent_type", "CrewAI.Agent")
        with tracer.start_as_current_span("CrewAI LLM: gpt-4o-mini") as wrapper:
            wrapper.set_attribute("agentsre.span_kind", "LLM")
            wrapper.set_attribute("agentsre.crewai.llm_event", True)
            wrapper.set_attribute("llm.provider", "openai")
            wrapper.set_attribute("llm.model_name", "gpt-4o-mini")
            with tracer.start_as_current_span("ChatCompletion") as provider:
                provider.set_attribute("openinference.span.kind", "LLM")
                provider.set_attribute("llm.provider", "openai")
                provider.set_attribute("llm.model_name", "gpt-4o-mini-2024-07-18")
                provider.set_attribute("input_tokens", 453)
                provider.set_attribute("output_tokens", 321)
                provider.set_attribute("finish_reason", "stop")

    processor.force_flush()

    payload = exporter.payloads[0].model_dump(mode="json")
    names = [span["span_name"] for span in payload["spans"]]
    agent = next(span for span in payload["spans"] if span["span_name"] == "CrewAI Agent: TravelPlannerAgent")
    llm = next(span for span in payload["spans"] if span["span_name"] == "ChatCompletion")

    assert "CrewAI LLM: gpt-4o-mini" not in names
    assert llm["parent_span_id"] == agent["span_id"]
    assert llm["llm"]["input_tokens"] == 453
    assert llm["llm"]["output_tokens"] == 321
    assert llm["llm"]["total_tokens"] == 774


def test_processor_adds_redaction_metadata_to_llm_tool_and_memory_sections() -> None:
    exporter, processor, tracer = _processor_tracer(sensitive_fields=["api_key"])

    with tracer.start_as_current_span("LLMWithPII") as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.provider", "openai")
        span.set_attribute("llm.model_name", "gpt-4o-mini")
        span.set_attribute("input.value", "Traveler Email: person@example.com")
        span.set_attribute("output.value", "Call 555-123-4567")

    with tracer.start_as_current_span("ToolWithPII") as span:
        span.set_attribute("openinference.span.kind", "TOOL")
        span.set_attribute("tool.name", "BookingTool")
        span.set_attribute("tool.arguments", '{"api_key": "secret"}')

    with tracer.start_as_current_span("MemoryWithPII") as span:
        span.set_attribute("openinference.span.kind", "MEMORY")
        span.set_attribute("retrieval.documents", ["customer name: Jane Doe"])

    processor.force_flush()

    spans = {span["span_name"]: span for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]}
    assert spans["LLMWithPII"]["llm"]["prompt"] == "Traveler Email: [REDACTED]"
    assert spans["LLMWithPII"]["llm"]["response"] == "Call [REDACTED]"
    assert spans["LLMWithPII"]["llm"]["redaction_applied"] is True
    assert spans["LLMWithPII"]["llm"]["redaction_field"] == ["email", "phone"]
    assert spans["ToolWithPII"]["tool"]["tool_arguments"] == {"api_key": "[REDACTED]"}
    assert spans["ToolWithPII"]["tool"]["redaction_applied"] is True
    assert spans["ToolWithPII"]["tool"]["redaction_field"] == ["api_key"]
    assert spans["MemoryWithPII"]["memory"]["retrieved_documents"] == ["customer name: [REDACTED]"]
    assert spans["MemoryWithPII"]["memory"]["redaction_applied"] is True
    assert spans["MemoryWithPII"]["memory"]["redaction_field"] == ["name"]


def test_processor_leaves_redaction_metadata_false_when_no_pii() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("CleanLLM") as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.provider", "openai")
        span.set_attribute("llm.model_name", "gpt-4o-mini")
        span.set_attribute("input.value", "Plan a trip to Mysore.")

    processor.force_flush()

    llm = exporter.payloads[0].model_dump(mode="json")["spans"][0]["llm"]
    assert llm["redaction_applied"] is False
    assert llm["redaction_field"] == []


def test_processor_copies_span_status_error_to_tool_error() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("reservation_submission") as span:
        span.set_attribute("openinference.span.kind", "TOOL")
        span.set_attribute("tool.name", "reservation_submission")
        span.set_attribute("tool.arguments", '{"traveler_name": "Ananya Rao"}')
        span.set_status(Status(StatusCode.ERROR, "RuntimeError('Supplier reservation gateway timed out: SUP-504')"))

    processor.force_flush()

    tool_span = exporter.payloads[0].model_dump(mode="json")["spans"][0]
    assert tool_span["status"] == "ERROR"
    assert tool_span["error_message"] == "RuntimeError('Supplier reservation gateway timed out: SUP-504')"
    assert tool_span["tool"]["tool_status"] == "ERROR"
    assert tool_span["tool"]["tool_error"] == "RuntimeError('Supplier reservation gateway timed out: SUP-504')"


def test_processor_exports_iteration_count_from_span_attribute() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("LangGraph Node: PlannerNode") as span:
        span.set_attribute("agentsre.span_kind", "AGENT")
        span.set_attribute("agentsre.langgraph.node_name", "PlannerNode")
        span.set_attribute("agentsre.iteration_count", 3)

    processor.force_flush()

    span_payload = exporter.payloads[0].model_dump(mode="json")["spans"][0]
    assert span_payload["iteration_count"] == 3


def test_processor_deduplicates_available_agents_and_excludes_internal_nodes() -> None:
    exporter, processor, tracer = _processor_tracer()

    registered_nodes = json.dumps(
        [
            {"node_name": "TravelCoordinatorAgent", "classification": "agent", "agent_type": "LangGraphNode"},
            {"node_name": "SupplierOpsAgent", "classification": "agent", "agent_type": "LangGraphNode"},
            {"node_name": "model", "classification": "agent", "agent_type": "LangGraphNode"},
            {"node_name": "tools", "classification": "agent", "agent_type": "LangGraphNode"},
            {"node_name": "route_seat_update", "classification": "agent", "agent_type": "LangGraphNode"},
        ]
    )

    with tracer.start_as_current_span("LangGraph Graph: corporate_travel_booking_graph") as graph:
        graph.set_attribute("agentsre.span_kind", "AGENT")
        graph.set_attribute("agentsre.langgraph.graph_name", "corporate_travel_booking_graph")
        graph.set_attribute("agentsre.langgraph.node_name", "corporate_travel_booking_graph")
        graph.set_attribute("agentsre.agent_name", "corporate_travel_booking_graph")
        graph.set_attribute("agentsre.agent_role", "Graph")
        graph.set_attribute("agentsre.agent_type", "LangGraph")
        graph.set_attribute("agentsre.langgraph.registered_nodes", registered_nodes)

    with tracer.start_as_current_span("LangGraph Node: TravelCoordinatorAgent") as custom_coordinator:
        custom_coordinator.set_attribute("agentsre.span_kind", "AGENT")
        custom_coordinator.set_attribute("agentsre.langgraph.graph_name", "corporate_travel_booking_graph")
        custom_coordinator.set_attribute("agentsre.langgraph.node_name", "TravelCoordinatorAgent")
        custom_coordinator.set_attribute("agentsre.agent_name", "TravelCoordinatorAgent")
        custom_coordinator.set_attribute("agentsre.agent_type", "LangGraphNode")

    with tracer.start_as_current_span("TravelCoordinatorAgent") as plain_coordinator:
        plain_coordinator.set_attribute("openinference.span.kind", "CHAIN")

    with tracer.start_as_current_span("model") as model:
        model.set_attribute("openinference.span.kind", "CHAIN")

    with tracer.start_as_current_span("tools") as tools:
        tools.set_attribute("openinference.span.kind", "CHAIN")

    with tracer.start_as_current_span("route_seat_update") as route:
        route.set_attribute("openinference.span.kind", "CHAIN")

    processor.force_flush()

    agents = exporter.payloads[0].model_dump(mode="json")["execution"]["available_agents"]
    agent_names = [agent["agent_name"] for agent in agents]

    assert agent_names.count("TravelCoordinatorAgent") == 1
    assert "SupplierOpsAgent" in agent_names
    assert "corporate_travel_booking_graph" in agent_names
    assert "model" not in agent_names
    assert "tools" not in agent_names
    assert "route_seat_update" not in agent_names


def test_processor_shutdown_is_idempotent_and_flushes_once() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("PlannerNode") as span:
        span.set_attribute("agentsre.span_kind", "AGENT")
        span.set_attribute("agentsre.langgraph.node_name", "PlannerNode")

    processor.shutdown()
    processor.shutdown()

    assert len(exporter.payloads) == 1
    assert exporter.shutdown_calls == 1


def _processor_tracer(sensitive_fields: list[str] | None = None) -> tuple[CaptureExporter, AgentSRESpanProcessor, object]:
    config = SDKConfig(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="dev",
        backend_url="https://example.com/ingest",
        api_key="test-key",
        sensitive_fields=sensitive_fields or [],
        workflow_id="wf_trip_planner",
        session_id="session_001",
    )
    resource = _resource()
    exporter = CaptureExporter()
    processor = AgentSRESpanProcessor(config, exporter, resource)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    return exporter, processor, provider.get_tracer(__name__)


def _resource() -> Resource:
    return Resource(
        sdk_version="1.0.0",
        plugin_version="1.0.0",
        framework="LangGraph",
        framework_version="1.1.10",
        language="Python",
        host_name="host",
        process_id=123,
        os="Windows",
        cpu_architecture="x86_64",
        runtime="Python",
        runtime_version="3.13.0",
        container_id=None,
        kubernetes_pod=None,
        cloud_provider=None,
    )

def test_processor_attaches_memory_to_llm_span_when_prompt_uses_retrieved_chunks() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("LangGraph Node: TravelOperationsCoordinator") as node_span:
        node_span.set_attribute("agentsre.span_kind", "AGENT")
        node_span.set_attribute("agentsre.langgraph.node_name", "TravelOperationsCoordinator")
        with tracer.start_as_current_span("corporate_policy.retrieve") as memory_span:
            memory_span.set_attribute("agentsre.span_kind", "MEMORY")
            memory_span.set_attribute("memory.operation", "retrieve")
            memory_span.set_attribute("memory.key", "corporate policy supplier timeout")
            memory_span.set_attribute("vector_store", "Chroma")
            memory_span.set_attribute(
                "retrieval.documents",
                json.dumps(
                    [
                        {
                            "text": "Corporate Travel Policy 2026 requires flight inventory before hotel lookup.",
                            "source": "corporate_travel_policy.txt",
                            "chunk_index": 0,
                            "score": 0.12,
                        }
                    ]
                ),
            )
            memory_span.set_attribute(
                "retrieval.chunks",
                json.dumps(
                    [
                        {
                            "text": "Corporate Travel Policy 2026 requires flight inventory before hotel lookup.",
                            "source": "corporate_travel_policy.txt",
                            "chunk_index": 0,
                            "score": 0.12,
                        }
                    ]
                ),
            )
            memory_span.set_attribute("retrieval.score", 0.12)

        with tracer.start_as_current_span("ChatCompletion") as llm_span:
            llm_span.set_attribute("openinference.span.kind", "LLM")
            llm_span.set_attribute("llm.provider", "openai")
            llm_span.set_attribute("llm.model_name", "gpt-4o-mini")
            llm_span.set_attribute(
                "input.value",
                "Use Policy memory from corporate_travel_policy.txt: Corporate Travel Policy 2026 requires flight inventory before hotel lookup.",
            )
            llm_span.set_attribute("output.value", "Inventory should be checked first.")

    processor.force_flush()

    spans = {span["span_name"]: span for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]}
    assert spans["corporate_policy.retrieve"]["span_kind"] == "MEMORY"
    assert spans["ChatCompletion"]["span_kind"] == "LLM"
    assert spans["ChatCompletion"]["memory"] is not None
    assert spans["ChatCompletion"]["memory"]["vector_store"] == "Chroma"
    assert spans["ChatCompletion"]["memory"]["retrieved_documents"][0]["source"] == "corporate_travel_policy.txt"


def test_processor_does_not_attach_memory_to_unrelated_llm_prompt() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("LangGraph Node: TravelOperationsCoordinator") as node_span:
        node_span.set_attribute("agentsre.span_kind", "AGENT")
        node_span.set_attribute("agentsre.langgraph.node_name", "TravelOperationsCoordinator")
        with tracer.start_as_current_span("corporate_policy.retrieve") as memory_span:
            memory_span.set_attribute("agentsre.span_kind", "MEMORY")
            memory_span.set_attribute("memory.operation", "retrieve")
            memory_span.set_attribute("retrieval.documents", '[{"text": "Corporate Travel Policy 2026", "source": "policy.txt"}]')

        with tracer.start_as_current_span("ChatCompletion") as llm_span:
            llm_span.set_attribute("openinference.span.kind", "LLM")
            llm_span.set_attribute("llm.model_name", "gpt-4o-mini")
            llm_span.set_attribute("input.value", "Write a greeting with no retrieval context.")

    processor.force_flush()

    spans = {span["span_name"]: span for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]}
    assert spans["ChatCompletion"]["memory"] is None


def test_processor_drops_internal_model_wrapper_and_deduplicates_llm_child() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("LangGraph Node: TravelOperationsCoordinator") as node_span:
        node_span.set_attribute("agentsre.span_kind", "AGENT")
        node_span.set_attribute("agentsre.langgraph.node_name", "TravelOperationsCoordinator")
        with tracer.start_as_current_span("TravelOperationsCoordinator") as plain_wrapper:
            plain_wrapper.set_attribute("openinference.span.kind", "CHAIN")
            with tracer.start_as_current_span("model") as model_wrapper:
                model_wrapper.set_attribute("openinference.span.kind", "CHAIN")
                with tracer.start_as_current_span("ChatOpenAI") as wrapper:
                    wrapper.set_attribute("openinference.span.kind", "LLM")
                    wrapper.set_attribute("llm.model_name", "gpt-4o-mini")
                    wrapper.set_attribute("input_tokens", 10)
                    wrapper.set_attribute("output_tokens", 5)
        with tracer.start_as_current_span("ChatCompletion") as provider_span:
            provider_span.set_attribute("openinference.span.kind", "LLM")
            provider_span.set_attribute("llm.model_name", "gpt-4o-mini")
            provider_span.set_attribute("input_tokens", 10)
            provider_span.set_attribute("output_tokens", 5)

    processor.force_flush()

    spans = [span for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]]
    names = [span["span_name"] for span in spans]
    node = next(span for span in spans if span["span_name"] == "LangGraph Node: TravelOperationsCoordinator")
    llm = next(span for span in spans if span["span_name"] == "ChatCompletion")

    assert "TravelOperationsCoordinator" not in names
    assert "model" not in names
    assert "ChatOpenAI" not in names
    assert llm["parent_span_id"] == node["span_id"]


def test_processor_remaps_repeated_plain_node_wrappers_to_matching_langgraph_node() -> None:
    exporter, processor, tracer = _processor_tracer()

    for index in range(4):
        with tracer.start_as_current_span("LangGraph Node: SeatPreferenceService") as node_span:
            node_span.set_attribute("agentsre.span_kind", "AGENT")
            node_span.set_attribute("agentsre.langgraph.node_name", "SeatPreferenceService")
            node_span.set_attribute("agentsre.iteration_count", index + 1)
            with tracer.start_as_current_span("SeatPreferenceService") as plain_wrapper:
                plain_wrapper.set_attribute("openinference.span.kind", "CHAIN")
                with tracer.start_as_current_span("seat_preference_update") as tool_span:
                    tool_span.set_attribute("openinference.span.kind", "TOOL")
                    tool_span.set_attribute("tool.name", "seat_preference_update")
                    tool_span.set_attribute("tool.arguments", f"attempt-{index + 1}")
                    tool_span.set_attribute("tool.output", "ok")

    processor.force_flush()

    spans = [span for payload in exporter.payloads for span in payload.model_dump(mode="json")["spans"]]
    names = [span["span_name"] for span in spans]
    node_ids = [span["span_id"] for span in spans if span["span_name"] == "LangGraph Node: SeatPreferenceService"]
    tool_parent_ids = [span["parent_span_id"] for span in spans if span["span_name"] == "seat_preference_update"]

    assert "SeatPreferenceService" not in names
    assert len(node_ids) == 4
    assert tool_parent_ids == node_ids


def test_available_agents_excludes_route_suffix_names() -> None:
    exporter, processor, tracer = _processor_tracer()

    registered_nodes = json.dumps(
        [
            {"node_name": "seat_followup_route", "classification": "agent", "agent_type": "LangGraphNode"},
            {"node_name": "TravelOperationsCoordinator", "classification": "agent", "agent_type": "LangGraphNode"},
        ]
    )
    with tracer.start_as_current_span("LangGraph Graph: travel_operations_workflow") as graph:
        graph.set_attribute("agentsre.span_kind", "AGENT")
        graph.set_attribute("agentsre.langgraph.graph_name", "travel_operations_workflow")
        graph.set_attribute("agentsre.langgraph.registered_nodes", registered_nodes)

    with tracer.start_as_current_span("seat_followup_route") as route:
        route.set_attribute("openinference.span.kind", "CHAIN")

    processor.force_flush()

    names = [agent["agent_name"] for agent in exporter.payloads[0].model_dump(mode="json")["execution"]["available_agents"]]
    assert "TravelOperationsCoordinator" in names
    assert "seat_followup_route" not in names


def test_processor_builds_execution_inventory_from_crewai_registered_metadata() -> None:
    exporter, processor, tracer = _processor_tracer()
    registered_agents = [
        {"agent_name": "TravelCoordinator", "agent_role": "Coordinator", "agent_type": "CrewAI.Agent"},
        {"agent_name": "SupplierSubAgent", "agent_role": "Supplier", "agent_type": "CrewAI.Agent"},
    ]
    registered_tools = [
        {
            "tool_name": "flight_inventory_search",
            "tool_description": "Searches approved inventory.",
            "tool_type": "Search",
            "tool_arguments": {"origin": "Bengaluru", "destination": "Mysore"},
        }
    ]

    with tracer.start_as_current_span("CrewAI Crew: travel_ops_crew") as crew:
        crew.set_attribute("agentsre.span_kind", "AGENT")
        crew.set_attribute("agentsre.agent_name", "travel_ops_crew")
        crew.set_attribute("agentsre.agent_role", "Crew")
        crew.set_attribute("agentsre.agent_type", "CrewAI.Crew")
        crew.set_attribute("agentsre.crewai.crew_name", "travel_ops_crew")
        crew.set_attribute("agentsre.crewai.registered_agents", json.dumps(registered_agents))
        crew.set_attribute("agentsre.crewai.registered_tools", json.dumps(registered_tools))

    processor.force_flush()

    payload = exporter.payloads[0].model_dump(mode="json")
    agents = {agent["agent_name"]: agent for agent in payload["execution"]["available_agents"]}
    tools = {tool["tool_name"]: tool for tool in payload["execution"]["available_tools"]}
    crew_span = payload["spans"][0]

    assert agents["travel_ops_crew"]["agent_type"] == "CrewAI.Crew"
    assert agents["TravelCoordinator"]["agent_type"] == "CrewAI.Agent"
    assert agents["SupplierSubAgent"]["agent_role"] == "Supplier"
    assert tools["flight_inventory_search"]["tool_type"] == "Search"
    assert tools["flight_inventory_search"]["tool_arguments"] == {
        "origin": {"type": "string"},
        "destination": {"type": "string"},
    }
    assert crew_span["agent"]["agent_type"] == "CrewAI.Crew"


def test_crewai_available_tool_schema_survives_redaction_and_runtime_args_are_redacted() -> None:
    exporter, processor, tracer = _processor_tracer()
    registered_tools = [
        {
            "tool_name": "traveler_profile_lookup",
            "tool_description": "Retrieves traveler profile preferences.",
            "tool_type": "Tool",
            "tool_arguments": {
                "traveler_email": {
                    "title": "Traveler Email",
                    "type": "string",
                }
            },
        }
    ]

    with tracer.start_as_current_span("CrewAI Crew: travel_ops_crew") as crew:
        crew.set_attribute("agentsre.span_kind", "AGENT")
        crew.set_attribute("agentsre.agent_name", "travel_ops_crew")
        crew.set_attribute("agentsre.agent_role", "Crew")
        crew.set_attribute("agentsre.agent_type", "CrewAI.Crew")
        crew.set_attribute("agentsre.crewai.crew_name", "travel_ops_crew")
        crew.set_attribute("agentsre.crewai.registered_tools", json.dumps(registered_tools))

        with tracer.start_as_current_span("CrewAI Tool: traveler_profile_lookup") as span:
            span.set_attribute("agentsre.span_kind", "TOOL")
            span.set_attribute("tool.name", "traveler_profile_lookup")
            span.set_attribute("tool.type", "Tool")
            span.set_attribute("tool.arguments", json.dumps({"traveler_email": "ananya.rao@example.com"}))
            span.set_attribute("tool.output", "Profile for ananya.rao@example.com")

    processor.force_flush()

    payload = exporter.payloads[0].model_dump(mode="json")
    tool_inventory = {tool["tool_name"]: tool for tool in payload["execution"]["available_tools"]}
    runtime_tool = next(span["tool"] for span in payload["spans"] if span["span_kind"] == "TOOL")

    assert tool_inventory["traveler_profile_lookup"]["tool_arguments"] == {
        "traveler_email": {
            "title": "Traveler Email",
            "type": "string",
        }
    }
    assert runtime_tool["tool_arguments"] == {"traveler_email": "[REDACTED]"}
    assert runtime_tool["tool_output"] == "Profile for [REDACTED]"


def test_available_tools_convert_runtime_arguments_to_schema_summary() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("reservation_submission") as span:
        span.set_attribute("openinference.span.kind", "TOOL")
        span.set_attribute("tool.name", "reservation_submission")
        span.set_attribute("tool.type", "Tool")
        span.set_attribute("tool.arguments", json.dumps({"traveler_name": "Ananya Rao", "retry": 2, "approved": False}))

    processor.force_flush()

    payload = exporter.payloads[0].model_dump(mode="json")
    available_tool = payload["execution"]["available_tools"][0]
    runtime_tool = payload["spans"][0]["tool"]

    assert available_tool["tool_name"] == "reservation_submission"
    assert available_tool["tool_arguments"] == {
        "approved": {"type": "boolean"},
        "retry": {"type": "integer"},
        "traveler_name": {"type": "string"},
    }
    assert runtime_tool["tool_arguments"] == {
        "approved": False,
        "retry": 2,
        "traveler_name": "[REDACTED]",
    }


def test_processor_propagates_sensitive_tool_argument_values_to_output_and_error() -> None:
    exporter, processor, tracer = _processor_tracer()

    with tracer.start_as_current_span("CrewAI Tool: reservation_submission") as span:
        span.set_attribute("agentsre.span_kind", "TOOL")
        span.set_attribute("tool.name", "reservation_submission")
        span.set_attribute("tool.arguments", json.dumps({"traveler_name": "Ananya Rao", "itinerary": "Bengaluru-Mysore"}))
        span.set_attribute("tool.output", "Reservation confirmed for Ananya Rao on SkyBridge.")
        span.set_attribute("tool.error", "Supplier reservation gateway timed out for Ananya Rao: SUP-504.")

    processor.force_flush()

    tool = exporter.payloads[0].model_dump(mode="json")["spans"][0]["tool"]

    assert tool["tool_arguments"] == {"itinerary": "Bengaluru-Mysore", "traveler_name": "[REDACTED]"}
    assert tool["tool_output"] == "Reservation confirmed for [REDACTED] on SkyBridge."
    assert tool["tool_error"] == "Supplier reservation gateway timed out for [REDACTED]: SUP-504."
    assert tool["redaction_applied"] is True
    assert tool["redaction_field"] == ["name"]

