from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Status = Literal["SUCCESS", "ERROR", "UNSET"]
SpanKind = Literal["AGENT", "LLM", "TOOL", "MEMORY", "REASONING", "HTTP", "UNKNOWN"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Execution(StrictModel):
    trace_id: str
    execution_id: str
    workflow_id: str
    session_id: str | None
    user_id: str | None
    tenant_id: str
    project_id: str
    service_name: str
    environment: str
    execution_start: str
    execution_end: str
    total_duration_ms: int = Field(ge=0)
    available_tools: list["AvailableTool"] = Field(default_factory=list)
    available_agents: list["AvailableAgent"] = Field(default_factory=list)


class AvailableTool(StrictModel):
    tool_id: str
    tool_name: str
    tool_description: str | None
    tool_type: str | None
    tool_arguments: dict[str, Any] | list[Any] | str | int | float | bool | None


class AvailableAgent(StrictModel):
    agent_id: str
    agent_name: str
    agent_role: str | None
    agent_type: str | None


class Resource(StrictModel):
    sdk_version: str
    plugin_version: str
    framework: str | None
    framework_version: str | None
    language: Literal["Python"]
    host_name: str
    process_id: int
    os: str
    cpu_architecture: str
    runtime: Literal["Python"]
    runtime_version: str
    container_id: str | None
    kubernetes_pod: str | None
    cloud_provider: str | None


class AgentSection(StrictModel):
    agent_id: str | None
    agent_name: str | None
    parent_agent: str | None
    agent_role: str | None
    agent_type: str | None
    workflow_id: str
    execution_id: str
    session_id: str | None
    redaction_applied: bool = False
    redaction_field: list[str] = Field(default_factory=list)


class LLMSection(StrictModel):
    provider: str | None
    model: str | None
    temperature: float | None
    max_tokens: int | None
    top_p: float | None
    frequency_penalty: float | None
    presence_penalty: float | None
    system_prompt: str | None
    prompt: str | None
    response: str | None
    finish_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost: float | None
    redaction_applied: bool = False
    redaction_field: list[str] = Field(default_factory=list)


class ToolSection(StrictModel):
    tool_name: str | None
    tool_type: str | None
    tool_description: str | None
    tool_arguments: dict[str, Any] | list[Any] | str | int | float | bool | None
    tool_output: dict[str, Any] | list[Any] | str | int | float | bool | None
    tool_status: str | None
    tool_error: str | None
    tool_latency: int | None
    redaction_applied: bool = False
    redaction_field: list[str] = Field(default_factory=list)


class MemorySection(StrictModel):
    memory_operation: str | None
    memory_key: str | None
    retrieved_documents: list[Any] | dict[str, Any] | str | None
    retrieval_score: float | None
    vector_store: str | None
    retrieved_chunks: list[Any] | dict[str, Any] | str | None
    redaction_applied: bool = False
    redaction_field: list[str] = Field(default_factory=list)


class ReasoningSection(StrictModel):
    reasoning_step: int | None
    node_name: str | None
    previous_node: str | None
    next_node: str | None
    decision_type: str | None


class HTTPSection(StrictModel):
    endpoint: str | None
    method: str | None
    response_code: int | None
    request_size: int | None
    response_size: int | None
    latency: int | None


class Span(StrictModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None
    span_name: str
    span_kind: SpanKind
    start_time: str
    end_time: str
    duration_ms: int = Field(ge=0)
    status: Status
    error_type: str | None
    error_message: str | None
    trace_context: str
    baggage: dict[str, Any]
    retry_count: int = Field(ge=0)
    iteration_count: int = Field(ge=0)
    agent: AgentSection | None
    llm: LLMSection | None
    tool: ToolSection | None
    memory: MemorySection | None
    reasoning: ReasoningSection | None
    http: HTTPSection | None

    @model_validator(mode="after")
    def require_at_least_one_section(self) -> "Span":
        sections = [self.agent, self.llm, self.tool, self.memory, self.reasoning, self.http]
        if not any(section is not None for section in sections):
            raise ValueError("span must include at least one populated section")
        return self


class AgentSREPayload(StrictModel):
    execution: Execution
    resource: Resource
    spans: list[Span]
