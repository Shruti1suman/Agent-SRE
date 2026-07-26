import { mapIncidents } from "./incidentMappers";

const emptySummary = {
  executions: 0,
  successRate: "0%",
  totalCost: "$0.00",
  p90Latency: "0ms"
};

const emptyHealthScore = {
  score: 0,
  status: "Critical",
  statusTone: "error",
  components: [
    { id: "success", label: "Success rate", score: 0, weight: 40, detail: "0 successful executions" },
    { id: "latency", label: "Latency SLO", score: 0, weight: 30, detail: "No latency data" },
    { id: "loop", label: "Loop risk", score: 0, weight: 15, detail: "No executions evaluated" },
    { id: "governance", label: "Governance", score: 0, weight: 15, detail: "No governance evidence" }
  ]
};

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function fmtMs(value) {
  const ms = number(value);
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
}

function fmtCost(value) {
  const cost = number(value);
  if (cost === 0) return "$0.00";
  if (cost < 0.001) return `$${cost.toFixed(5)}`;
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

function estimateCostFromTokens(metric) {
  const existing = number(metric.total_cost_usd);
  const tokens = number(metric.total_tokens);
  if (existing > 0 || tokens <= 0) return existing;
  const promptTokens = number(metric.total_prompt_tokens) || tokens * 0.75;
  const completionTokens = number(metric.total_completion_tokens) || tokens * 0.25;
  return ((promptTokens * 0.15) + (completionTokens * 0.60)) / 1_000_000;
}

function shortId(value, fallback = "N/A") {
  if (!value) return fallback;
  const text = String(value);
  return text.length > 14 ? `${text.slice(0, 10)}...` : text;
}

function displayTraceName(trace, fallback = "Trace") {
  return trace?.root || trace?.agent || trace?.raw?.service_name || trace?.traceId || trace?.id || fallback;
}

function traceTimestamp(trace) {
  const raw = trace?.raw || {};
  const value = raw.created_at || raw.started_at || raw.ended_at || raw.execution_start || trace?.id || "";
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function traceTimestampValue(trace) {
  const raw = trace?.raw || {};
  return raw.created_at || raw.started_at || raw.ended_at || raw.execution_start || "";
}

function normalizeStatus(value) {
  const status = String(value || "").toLowerCase();
  if (["completed", "success", "succeeded"].includes(status)) return "success";
  if (["failed", "failure", "error"].includes(status)) return "failed";
  if (["running", "pending"].includes(status)) return "running";
  return status || "unknown";
}

function p90(values) {
  const sorted = values.map(number).filter(Boolean).sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const index = Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.9) - 1);
  return sorted[index];
}

function clamp01(value) {
  const parsed = number(value);
  return Math.max(0, Math.min(1, parsed));
}

function percent(value) {
  return Math.round(clamp01(value) * 100);
}

function activeSloThreshold(slos, metricName, fallback) {
  const rows = Array.isArray(slos?.slos) ? slos.slos : Array.isArray(slos) ? slos : [];
  const row = rows.find((item) => item?.metric_name === metricName && item?.enabled !== false);
  const value = number(row?.threshold_value ?? row?.target);
  return value > 0 ? value : fallback;
}

function healthStatus(score) {
  if (score >= 90) return { status: "Healthy", statusTone: "success" };
  if (score >= 70) return { status: "Degraded", statusTone: "warning" };
  return { status: "Critical", statusTone: "error" };
}

function buildHealthScore({ executions, successful, latencyValues, metrics, incidents, governance, slos }) {
  if (!executions) return emptyHealthScore;

  const successScore = clamp01(successful / executions);
  const latencyTarget = activeSloThreshold(slos, "total_duration_ms", 1800);
  const evaluatedLatencies = latencyValues.map(number).filter((value) => value > 0);
  const latencyCompliantRuns = evaluatedLatencies.filter((value) => value <= latencyTarget).length;
  const latencyScore = evaluatedLatencies.length
    ? clamp01(latencyCompliantRuns / evaluatedLatencies.length)
    : 1;
  const loopRiskCount = metrics.filter((row) => row.loop_detected).length
    || incidents.filter((row) => String(row.category || row.incident || row.rca_text || "").toLowerCase().includes("loop")).length;
  const loopRiskScore = clamp01(1 - (loopRiskCount / executions));
  const governanceWarnings = Math.max(
    number(governance?.summary?.warnings),
    Array.isArray(governance?.warnings) ? governance.warnings.length : 0
  );
  const governanceScore = clamp01(1 - (governanceWarnings / executions));
  const score = Math.round(
    ((successScore * 0.40)
      + (latencyScore * 0.30)
      + (loopRiskScore * 0.15)
      + (governanceScore * 0.15)) * 100
  );
  const status = healthStatus(score);

  return {
    score,
    ...status,
    components: [
      {
        id: "success",
        label: "Success rate",
        score: percent(successScore),
        weight: 40,
        detail: `${successful}/${executions} successful executions`
      },
      {
        id: "latency",
        label: "Latency SLO",
        score: percent(latencyScore),
        weight: 30,
        detail: evaluatedLatencies.length
          ? `${latencyCompliantRuns}/${evaluatedLatencies.length} runs within ${fmtMs(latencyTarget)}`
          : "No latency data"
      },
      {
        id: "loop",
        label: "Loop risk",
        score: percent(loopRiskScore),
        weight: 15,
        detail: `${loopRiskCount} loop-risk execution${loopRiskCount === 1 ? "" : "s"}`
      },
      {
        id: "governance",
        label: "Governance",
        score: percent(governanceScore),
        weight: 15,
        detail: `${governanceWarnings} governance warning${governanceWarnings === 1 ? "" : "s"}`
      }
    ]
  };
}

function byTraceId(rows) {
  return new Map((rows || []).filter((row) => row?.trace_id).map((row) => [String(row.trace_id), row]));
}

function projectFilter(projectId) {
  return (row) => !projectId || String(row?.project_id || "") === String(projectId);
}

function groupByModel(metrics) {
  const groups = new Map();
  for (const row of metrics) {
    const model = row.model_name || "Unknown model";
    const current = groups.get(model) || { total: 0, count: 0 };
    current.total += number(row.total_duration_ms || row.llm_latency_ms);
    current.count += 1;
    groups.set(model, current);
  }
  return Array.from(groups.entries()).map(([label, item]) => ({
    label,
    value: item.count ? item.total / item.count : 0,
    detail: fmtMs(item.count ? item.total / item.count : 0)
  }));
}

function topLatencySignals(metrics, traceByTraceId) {
  const rows = [];
  for (const row of metrics) {
    const trace = traceByTraceId.get(String(row.trace_id));
    const traceName = trace?.displayName || row.agent_id || shortId(row.trace_id, "Trace");
    [
      ["LLM latency", row.llm_latency_ms],
      ["Tool latency", row.total_tool_latency_ms],
      ["P95 step latency", row.p95_step_latency_ms],
      ["Avg step latency", row.avg_step_latency_ms]
    ].forEach(([spanName, rawValue]) => {
      const value = number(rawValue);
      if (value <= 0) return;
      const label = `${traceName} / ${spanName}`;
      rows.push({
        label,
        tooltipTitle: label,
        value,
        detail: fmtMs(value)
      });
    });
  }
  return rows
    .sort((a, b) => b.value - a.value)
    .slice(0, 5)
    .map((row) => ({
      ...row,
      label: row.label.length > 46 ? `${row.label.slice(0, 43)}...` : row.label
    }));
}

export function mapDashboardData({ sources, selectedProjectId }) {
  const traces = (sources?.traces || []).filter(projectFilter(selectedProjectId)).filter((row) => !row.error);
  const metrics = (sources?.metrics || []).filter(projectFilter(selectedProjectId)).filter((row) => !row.error);
  const incidents = (sources?.incidents || []).filter(projectFilter(selectedProjectId)).filter((row) => !row.error);
  const metricByTrace = byTraceId(metrics);

  const loadedSuccessful = traces.filter((trace) => normalizeStatus(trace.status) === "success").length;
  const overviewExecutions = Number(sources?.overview?.traces);
  const overviewSuccessful = Number(sources?.overview?.successful);
  const executions = Number.isFinite(overviewExecutions) ? overviewExecutions : traces.length;
  const successful = Number.isFinite(overviewSuccessful) ? overviewSuccessful : loadedSuccessful;
  const totalCost = metrics.reduce((sum, row) => sum + estimateCostFromTokens(row), 0);
  const latencyValues = metrics.length
    ? metrics.map((metric) => number(metric.total_duration_ms)).filter((value) => value > 0)
    : traces.map((trace) => number(trace.duration_ms)).filter((value) => value > 0);
  const p90LatencyMs = p90(latencyValues);

  const normalizedTraces = traces.map((trace) => {
    const metric = metricByTrace.get(String(trace.trace_id)) || {};
    const cost = estimateCostFromTokens(metric);
    const duration = number(metric.total_duration_ms || trace.duration_ms);
    const tokens = number(metric.total_tokens);
    const timestamp = traceTimestampValue({ raw: trace });
    return {
      id: trace.execution_id,
      traceId: trace.trace_id,
      root: trace.service_name || shortId(trace.trace_id),
      serviceName: trace.service_name,
      agent: metric.agent_id || trace.service_name || "N/A",
      projectId: trace.project_id,
      cost,
      duration,
      tokens,
      timestamp,
      timestampMs: traceTimestamp({ raw: trace }),
      failed: normalizeStatus(trace.status) === "failed" ? "Yes" : "No",
      status: normalizeStatus(trace.status),
      spans: number(trace.span_count || metric.step_count),
      llm: number(trace.llm_count || metric.step_count),
      tools: number(trace.tool_count || metric.tool_call_count),
      framework: trace.framework || "LangGraph",
      displayName: trace.service_name || metric.agent_id || shortId(trace.trace_id, trace.execution_id),
      raw: trace,
      metric
    };
  });
  const chronologicalTraces = [...normalizedTraces].sort((a, b) => traceTimestamp(a) - traceTimestamp(b));
  const traceByTraceId = new Map(normalizedTraces.filter((trace) => trace.traceId).map((trace) => [String(trace.traceId), trace]));
  const normalizedIncidents = mapIncidents(incidents).map((incident) => {
    const trace = traceByTraceId.get(String(incident.trace));
    return {
      ...incident,
      traceName: trace?.displayName || shortId(incident.trace, "Trace"),
      traceDisplay: trace
        ? `${trace.displayName} / ${shortId(trace.traceId)}`
        : shortId(incident.trace, incident.trace),
    };
  });

  const expensiveTraces = [...normalizedTraces]
    .sort((a, b) => b.cost - a.cost || b.timestampMs - a.timestampMs)
    .slice(0, 10);

  return {
    hasProject: Boolean(selectedProjectId),
    hasData: executions > 0 || metrics.length > 0 || incidents.length > 0,
    summary: {
      ...emptySummary,
      executions,
      successRate: executions ? `${Math.round((successful / executions) * 100)}%` : "0%",
      totalCost: fmtCost(totalCost),
      p90Latency: fmtMs(p90LatencyMs)
    },
    healthScore: buildHealthScore({
      executions,
      successful,
      latencyValues,
      metrics,
      incidents,
      governance: sources?.governance,
      slos: sources?.slos
    }),
    latencyByTrace: chronologicalTraces.map((trace, index) => ({
      label: shortId(displayTraceName(trace), `trace-${index + 1}`),
      tooltipTitle: displayTraceName(trace, `trace-${index + 1}`),
      value: trace.duration,
      detail: fmtMs(trace.duration)
    })),
    topSpans: topLatencySignals(metrics, traceByTraceId),
    costByExecution: chronologicalTraces.map((trace, index) => ({
      label: shortId(displayTraceName(trace), `exec-${index + 1}`),
      tooltipTitle: displayTraceName(trace, `exec-${index + 1}`),
      value: trace.cost,
      detail: fmtCost(trace.cost)
    })),
    latencyByModel: groupByModel(metrics),
    tokensPerRun: chronologicalTraces.map((trace, index) => ({
      label: shortId(displayTraceName(trace), `run-${index + 1}`),
      tooltipTitle: displayTraceName(trace, `run-${index + 1}`),
      value: trace.tokens,
      detail: `${trace.tokens.toLocaleString()} tokens`
    })),
    traces: normalizedTraces,
    expensiveTraces,
    incidents: normalizedIncidents
  };
}

export const emptyDashboardData = {
  hasProject: false,
  hasData: false,
  summary: emptySummary,
  healthScore: emptyHealthScore,
  latencyByTrace: [],
  topSpans: [],
  costByExecution: [],
  latencyByModel: [],
  tokensPerRun: [],
  expensiveTraces: [],
  incidents: []
};
