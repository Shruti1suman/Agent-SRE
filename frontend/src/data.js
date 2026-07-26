export const traces = [
  {
    id: "trc_8f19a2",
    root: "PlannerNode",
    agent: "trip-planner",
    framework: "LangGraph",
    duration: 1420,
    spans: 8,
    llm: 3,
    tools: 3,
    tokens: 6420,
    cost: 0.184,
    status: "success",
    failed: "No",
    model: "gemini-2.5-flash",
    spansList: [
      { name: "PlannerNode", kind: "agent", status: "success", duration: 210, input: "Plan a 3-day Berlin itinerary for [REDACTED].", output: "Gathered route, weather, and preference constraints." },
      { name: "WeatherToolNode", kind: "tool", status: "success", duration: 386, tool: "weather", arguments: "{ city: 'Berlin', dates: 'next 3 days' }", toolOutput: "Mild weather, rain risk on day 2." },
      { name: "RouteDecision", kind: "llm", status: "success", duration: 318, model: "gemini-2.5-flash", tokens: 2140, cost: "$0.061", output: "Prioritized museum blocks during rain window." },
      { name: "GenerateResponse", kind: "llm", status: "success", duration: 506, model: "gemini-2.5-flash", tokens: 4280, cost: "$0.123", output: "Final itinerary with transit notes." }
    ]
  },
  {
    id: "trc_91c4d7",
    root: "LLMFailNode",
    agent: "customer-support-agent",
    framework: "LangGraph",
    duration: 2690,
    spans: 11,
    llm: 4,
    tools: 4,
    tokens: 10380,
    cost: 0.322,
    status: "error",
    failed: "Yes",
    model: "gemini-2.5-pro",
    spansList: [
      { name: "PlannerNode", kind: "agent", status: "success", duration: 180, input: "Resolve refund request for order [REDACTED].", output: "Selected order lookup and policy route." },
      { name: "OrderLookup", kind: "tool", status: "success", duration: 440, tool: "order_lookup", arguments: "{ order_id: '[REDACTED]' }", toolOutput: "Delivered, 42 days since purchase." },
      { name: "RefundPolicy", kind: "tool", status: "success", duration: 390, tool: "refund_policy", toolOutput: "Refund window exceeded." },
      { name: "LLMFailNode", kind: "llm", status: "error", duration: 1680, model: "gemini-2.5-pro", tokens: 5950, cost: "$0.221", error: "Model response exceeded policy confidence threshold." }
    ]
  },
  {
    id: "trc_a7d412",
    root: "GenerateResponse",
    agent: "research-agent",
    framework: "LangGraph",
    duration: 980,
    spans: 6,
    llm: 2,
    tools: 2,
    tokens: 5120,
    cost: 0.146,
    status: "captured",
    failed: "No",
    model: "gemini-2.5-flash-lite",
    spansList: [
      { name: "PlannerNode", kind: "agent", status: "success", duration: 140, input: "Summarize quarterly AI governance controls.", output: "Set evidence search plan." },
      { name: "InventoryCheck", kind: "tool", status: "success", duration: 260, tool: "inventory_check", arguments: "{ asset_class: 'policy_docs' }", toolOutput: "Found 14 approved control documents." },
      { name: "GenerateResponse", kind: "llm", status: "captured", duration: 580, model: "gemini-2.5-flash-lite", tokens: 5120, cost: "$0.146", output: "Produced governance summary with two redactions." }
    ]
  },
  {
    id: "trc_c4139e",
    root: "RouteDecision",
    agent: "trip-planner",
    framework: "LangGraph",
    duration: 1870,
    spans: 9,
    llm: 3,
    tools: 2,
    tokens: 7860,
    cost: 0.214,
    status: "success",
    failed: "No",
    model: "gemini-2.5-pro",
    spansList: [
      { name: "PlannerNode", kind: "agent", status: "success", duration: 190, input: "Build route across Tokyo neighborhoods.", output: "Prepared transit checks." },
      { name: "TimezoneToolNode", kind: "tool", status: "success", duration: 330, tool: "timezone", arguments: "{ city: 'Tokyo' }", toolOutput: "UTC+09:00." },
      { name: "RouteDecision", kind: "llm", status: "success", duration: 620, model: "gemini-2.5-pro", tokens: 3660, cost: "$0.109", output: "Chose low-transfer route." },
      { name: "GenerateResponse", kind: "llm", status: "success", duration: 730, model: "gemini-2.5-pro", tokens: 4200, cost: "$0.105", output: "Returned schedule with transfer buffers." }
    ]
  }
];

export const incidents = [
  { severity: "critical", status: "open", rule: "LLM failure rate > 3%", incident: "Support refund workflow crossed failure budget", agent: "customer-support-agent", trace: "trc_91c4d7", recommendation: "Pin the policy prompt version and replay failed trace before widening traffic." },
  { severity: "high", status: "open", rule: "Tool latency P90 > 900ms", incident: "Order lookup dependency is slowing response path", agent: "customer-support-agent", trace: "trc_91c4d7", recommendation: "Cache recent order metadata and alert platform owner if latency persists." },
  { severity: "medium", status: "watching", rule: "Redaction count increased", incident: "Research summaries include more personal identifiers", agent: "research-agent", trace: "trc_a7d412", recommendation: "Review input source mapping and confirm redaction policy coverage." }
];

export const alerts = [
  { id: "alt_7001", severity: "critical", status: "triggered", type: "SLO breach", rule: "P90 latency > 1800ms for 5m", agent: "customer-support-agent", triggeredAt: "2026-07-05 01:26:18", evidence: "P90 2.69s vs 1.80s target", traceId: "trc_91c4d7", span: "LLMFailNode", currentValue: "2.69s", threshold: "1.80s", remediation: "Inspect LLMFailNode, pin the support policy prompt, then replay the failed execution." },
  { id: "alt_7002", severity: "high", status: "triggered", type: "Latency spike", rule: "Trace latency spike above rolling baseline", agent: "trip-planner", triggeredAt: "2026-07-05 01:22:31", evidence: "RouteDecision 1.87s, baseline 820ms", traceId: "trc_c4139e", span: "RouteDecision", currentValue: "1.87s", threshold: "1.64s dynamic baseline", remediation: "Review model latency and route planner branching." },
  { id: "alt_7003", severity: "high", status: "acknowledged", type: "Governance violation", rule: "Review required for low confidence policy response", agent: "customer-support-agent", triggeredAt: "2026-07-05 01:24:12", evidence: "review_status flagged, replay available", traceId: "trc_91c4d7", span: "LLMFailNode", currentValue: "flagged", threshold: "review required", remediation: "Open governance replay and confirm masked evidence before resolving." },
  { id: "alt_7004", severity: "medium", status: "resolved", type: "Privacy/redaction warning", rule: "Masked fields increased by 2x", agent: "research-agent", triggeredAt: "2026-07-05 01:18:44", evidence: "prompt.input and response.output redacted", traceId: "trc_a7d412", span: "GenerateResponse", currentValue: "4 masked fields", threshold: "2x baseline", remediation: "Confirm source mapping and redaction policies." }
];

export const slos = [
  { metric: "Execution success rate", target: "99.0", unit: "%", status: "healthy", updated: "2026-07-05 01:18", enabled: true },
  { metric: "P90 latency", target: "1800", unit: "ms", status: "breach", updated: "2026-07-05 00:52", enabled: true },
  { metric: "Tool error rate", target: "1.5", unit: "%", status: "risk", updated: "2026-07-04 22:17", enabled: true },
  { metric: "Loop count", target: "2", unit: "runs", status: "healthy", updated: "2026-07-04 21:44", enabled: false }
];

export const sloTimeline = [
  { time: "01:26:18", metric: "P90 latency", state: "breach", type: "Latency threshold breach", observed: "Observed P90 2.69s exceeded target 1.80s", evidence: "trc_91c4d7 / LLMFailNode" },
  { time: "01:22:04", metric: "Tool error rate", state: "risk", type: "Tool reliability risk", observed: "Observed 1.2% is close to the 1.5% limit", evidence: "order_lookup and refund_policy spans" },
  { time: "01:18:03", metric: "Execution success rate", state: "healthy", type: "Objective healthy", observed: "Observed 99.2% remains above target 99.0%", evidence: "3.8k successful executions" }
];

export const governanceReplayEvents = [
  { time: "01:24:02", type: "Agent step", status: "success", detail: "customer-support-agent entered refund review workflow", evidence: "execution_id exec_91c4d7" },
  { time: "01:24:04", type: "LLM call", status: "captured", detail: "Prompt captured with masked customer and order fields", evidence: "governance_llm_calls llm_2041" },
  { time: "01:24:06", type: "Tool call", status: "captured", detail: "order_lookup invoked with masked arguments only", evidence: "governance_tool_calls tool_8820" },
  { time: "01:24:11", type: "Warning", status: "warning", detail: "Low confidence policy exception response detected", evidence: "governance_warnings warn_421" },
  { time: "01:24:14", type: "Execution completed", status: "error", detail: "Execution completed with review required", evidence: "review_status flagged" }
];

export const privacyEvidence = [
  { field: "prompt.input", redactionApplied: "true", types: "email, order_id", policy: "masked_only", maskedFields: 2 },
  { field: "tool.arguments", redactionApplied: "true", types: "customer_ref", policy: "masked_only", maskedFields: 1 },
  { field: "response.output", redactionApplied: "true", types: "personal_identifier", policy: "masked_only", maskedFields: 1 }
];

export const governanceWarnings = [
  { severity: "high", source: "review", message: "Execution flagged because response confidence dropped below policy threshold." },
  { severity: "medium", source: "privacy", message: "Masked fields increased for research-agent execution summaries." },
  { severity: "medium", source: "export", message: "Latest export contains evidence metadata only; raw payloads excluded." }
];

export const auditRecords = [
  { id: "aud_9015", actor_user_id: "usr_reviewer_014", action: "execution.viewed", agent_id: "agent_support", execution_id: "exec_91c4d7", metadata: "{ view: 'governance_replay' }", created_at: "2026-07-05 01:24:20" },
  { id: "aud_9016", actor_user_id: "usr_reviewer_014", action: "execution.reviewed", agent_id: "agent_support", execution_id: "exec_91c4d7", metadata: "{ status: 'flagged' }", created_at: "2026-07-05 01:25:02" },
  { id: "aud_9018", actor_user_id: "usr_admin_001", action: "execution.exported", agent_id: "agent_support", execution_id: "exec_91c4d7", metadata: "{ export: 'evidence_bundle' }", created_at: "2026-07-05 01:27:33" }
];

export const findings = [
  "Policy exception response had low confidence and was blocked.",
  "Two research-agent inputs contained personal identifiers and were redacted.",
  "Replay is available for the latest high-cost support trace."
];

export const dashboardRuns = [
  { label: "PlannerNode", value: 6420, detail: "trip-planner: 6.4k tokens" },
  { label: "LLMFailNode", value: 10380, detail: "customer-support-agent: 10.3k tokens" },
  { label: "GenerateResponse", value: 5120, detail: "research-agent: 5.1k tokens" },
  { label: "RouteDecision", value: 7860, detail: "trip-planner: 7.8k tokens" },
  { label: "PolicyReview", value: 8920, detail: "customer-support-agent: 8.9k tokens" }
];

export const latencyTraceSeries = [
  { label: "trip-planner / PlannerNode", value: 1420, detail: "PlannerNode: 1.42s" },
  { label: "support / OrderLookup", value: 860, detail: "OrderLookup: 860ms" },
  { label: "research / GenerateResponse", value: 980, detail: "GenerateResponse: 980ms" },
  { label: "support / LLMFailNode", value: 2690, detail: "LLMFailNode: 2.69s" },
  { label: "trip-planner / RouteDecision", value: 1870, detail: "RouteDecision: 1.87s" }
];

export const modelLatency = [
  { label: "gemini-2.5-pro", value: 1870, detail: "gemini-2.5-pro: 1.87s average latency" },
  { label: "gemini-2.5-flash", value: 1420, detail: "gemini-2.5-flash: 1.42s average latency" },
  { label: "gemini-2.5-flash-lite", value: 2310, detail: "gemini-2.5-flash-lite: 2.31s average latency" },
  { label: "gemini-2.5-flash-image", value: 1640, detail: "gemini-2.5-flash-image: 1.64s average latency" }
];
