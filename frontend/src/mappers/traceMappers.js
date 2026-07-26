import { compactError } from "../utils/errorFormat";

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizeStatus(value) {
  const status = String(value || "").toLowerCase();
  if (["completed", "success", "succeeded"].includes(status)) return "success";
  if (["failed", "failure", "error"].includes(status)) return "failed";
  if (["running", "pending"].includes(status)) return "running";
  return status || "unknown";
}

function readableTraceName(trace) {
  return trace?.root || trace?.serviceName || trace?.agent || trace?.traceId || trace?.id || "Trace";
}

function spanName(item) {
  return item?.name || item?.summary || item?.span_id || item?.step_id || "Span";
}

function spanKind(item, llm = {}, tool = {}) {
  const rawValue = String(item?.canonical_type || item?.kind || "").toLowerCase();
  const raw = ["n/a", "na", "none", "unknown"].includes(rawValue) ? "" : rawValue;
  const name = String(item?.name || item?.summary || "").toLowerCase();
  if (raw.includes("llm")) return "llm";
  if (raw.includes("tool")) return "tool";
  if (raw.includes("agent")) return "agent";
  if (raw.includes("http")) return "http";
  if (raw.includes("memory")) return "memory";
  if (raw.includes("reasoning")) return "reasoning";
  if (llm.model_name || llm.model || llm.request_model) return "llm";
  if (tool.tool_name || item?.tool_name) return "tool";
  return raw || "span";
}

export function mapReplayToTrace(trace, replay) {
  if (!trace || !replay || replay.error) {
    return trace;
  }

  const timeline = replay.timeline || [];
  const llmCalls = replay.llm_calls || [];
  const toolCalls = replay.tool_calls || [];
  const privacy = Array.isArray(replay.privacy) ? replay.privacy[0] || {} : replay.privacy || {};
  const llmBySpan = new Map(llmCalls.map((call) => [call.span_id, call]));
  const toolBySpan = new Map(toolCalls.map((call) => [call.span_id, call]));

  const mappedSpans = timeline.map((item, index) => {
    const llm = llmBySpan.get(item.span_id) || {};
    const tool = toolBySpan.get(item.span_id) || {};
    const name = spanName(item);
    return {
      id: item.span_id || item.step_id || `${trace.id}-span-${index}`,
      stepId: item.step_id,
      parentSpanId: item.parent_span_id,
      name,
      kind: spanKind(item, llm, tool),
      canonicalType: item.canonical_type,
      status: normalizeStatus(item.status_code),
      duration: number(item.duration_ms),
      retryCount: number(item.retry_count),
      sequenceNumber: number(item.sequence_number),
      modelName: llm.model_name || llm.model || llm.request_model,
      provider: llm.provider,
      toolName: tool.tool_name || item.tool_name,
      toolArguments: tool.tool_input,
      input: llm.input_messages?.map((message) => message.content).filter(Boolean).join("\n") || tool.tool_input,
      output: llm.output_messages?.map((message) => message.content).filter(Boolean).join("\n"),
      toolOutput: tool.tool_output,
      error: compactError(item.status_message),
      detail: `${name}: ${number(item.duration_ms)}ms`,
      raw: item
    };
  });
  const failedChildrenByParent = new Map();
  mappedSpans.forEach((span) => {
    if (span.status !== "failed" || !span.parentSpanId) return;
    const children = failedChildrenByParent.get(span.parentSpanId) || [];
    children.push(span.name);
    failedChildrenByParent.set(span.parentSpanId, children);
  });
  const spansList = mappedSpans.map((span) => {
    const failedChildren = failedChildrenByParent.get(span.id) || [];
    return {
      ...span,
      failedChildCount: failedChildren.length,
      failedChildNames: failedChildren,
    };
  });

  const execution = replay.execution || {};
  const graph = replay.graph || {};
  return {
    ...trace,
    root: execution.service_name && execution.service_name !== "N/A" ? execution.service_name : trace.root,
    agent: execution.agent_id && execution.agent_id !== "N/A" ? execution.agent_id : trace.agent,
    status: normalizeStatus(execution.status || trace.status),
    duration: number(execution.duration_ms || trace.duration),
    spans: timeline.length || trace.spans,
    llm: llmCalls.length || trace.llm,
    tools: toolCalls.length || trace.tools,
    spansList,
    replay,
    graph,
    redactions: number(privacy.masked_fields_count || privacy.maskedFields),
    privacy,
    metric: trace.metric || {},
    sloResults: trace.metric?.slo_results || [],
    sloBreaches: trace.metric?.slo_breaches || [],
    sloStatus: trace.metric?.slo_status,
    displayName: readableTraceName(trace)
  };
}

export function traceDisplayName(trace) {
  return readableTraceName(trace);
}
