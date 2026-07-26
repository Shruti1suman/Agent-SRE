import { useMemo, useState } from "react";
import Grid from "@mui/material/Grid";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import CloseIcon from "@mui/icons-material/Close";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import MetricCard from "../components/MetricCard";
import PageHeader from "../components/PageHeader";
import StatusPill from "../components/StatusPill";
import DataTable from "../components/DataTable";
import { fetchIncidentReport } from "../api/incidents";
import { downloadIncidentReportPdf } from "../utils/incidentReportPdf";
import { compactError } from "../utils/errorFormat";

const FAMILY_CONFIG = [
  { id: "all", label: "All" },
  { id: "execution", label: "Execution failure" },
  { id: "tool", label: "Tool reliability" },
  { id: "loop", label: "Loop / retry" },
  { id: "latency", label: "Latency" },
  { id: "cost", label: "Cost / tokens" },
  { id: "groundedness", label: "Groundedness" },
  { id: "slo", label: "SLO breach" },
  { id: "other", label: "Other" },
];

const SEVERITY_RANK = { critical: 5, high: 4, warning: 3, medium: 3, low: 2, info: 1 };
const SOURCE_RANK = { slo: 4, judge: 3, rule: 3, zscore: 2 };

function shortTrace(value) {
  const text = String(value || "N/A");
  return text.length > 14 ? `${text.slice(0, 10)}...` : text;
}

function TimestampCell({ value }) {
  if (!value || value === "N/A") {
    return <Typography sx={{ fontSize: 13 }}>N/A</Typography>;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return <Typography sx={{ fontSize: 13 }}>{String(value)}</Typography>;
  }
  return (
    <Box>
      <Typography sx={{ fontSize: 13.5, lineHeight: 1.25 }}>
        {date.toLocaleDateString()}
      </Typography>
      <Typography color="text.secondary" sx={{ fontSize: 12, lineHeight: 1.3 }}>
        {date.toLocaleTimeString()}
      </Typography>
    </Box>
  );
}

function incidentFamily(row) {
  const category = String(row.raw?.category || row.type || row.rule || row.incident || "").toLowerCase();
  const metric = String(row.raw?.metric_name || row.evidence || "").toLowerCase();
  if (category.includes("slo")) return "slo";
  if (category.includes("tool") || metric.includes("tool")) return "tool";
  if (category.includes("loop") || category.includes("retry") || metric.includes("retry")) return "loop";
  if (category.includes("latency") || category.includes("duration")) return "latency";
  if (category.includes("cost") || category.includes("token") || metric.includes("token") || metric.includes("cost")) return "cost";
  if (category.includes("hallucination") || category.includes("ground")) return "groundedness";
  if (category.includes("failure") || category.includes("failed") || category.includes("finish_reason")) return "execution";
  return "other";
}

function incidentTraceKey(row) {
  return String(row.raw?.trace_id || row.trace || row.id || "");
}

function incidentMetricKey(row) {
  if (row.raw?.slo_id) return `slo:${row.raw.slo_id}`;
  return String(row.raw?.metric_name || row.rule || row.type || row.incident || "");
}

function preferredIncident(left, right) {
  const leftSource = SOURCE_RANK[String(left.raw?.triggered_by || "rule").toLowerCase()] || 1;
  const rightSource = SOURCE_RANK[String(right.raw?.triggered_by || "rule").toLowerCase()] || 1;
  if (leftSource !== rightSource) return leftSource > rightSource ? left : right;

  const leftSeverity = SEVERITY_RANK[left.severity] || 0;
  const rightSeverity = SEVERITY_RANK[right.severity] || 0;
  if (leftSeverity !== rightSeverity) return leftSeverity > rightSeverity ? left : right;

  const leftTime = new Date(left.triggeredAt).getTime() || 0;
  const rightTime = new Date(right.triggeredAt).getTime() || 0;
  return leftTime >= rightTime ? left : right;
}

function dedupeIncidentRows(rows) {
  const byMetric = new Map();
  for (const row of rows) {
    const metric = incidentMetricKey(row);
    if (!metric) {
      byMetric.set(row.id, row);
      continue;
    }
    const key = `${incidentTraceKey(row)}:${metric}`;
    const existing = byMetric.get(key);
    byMetric.set(key, existing ? preferredIncident(existing, row) : row);
  }

  const selected = Array.from(byMetric.values());
  const tokenIncidentTraces = new Set(
    selected
      .filter((row) => String(row.raw?.metric_name || "").toLowerCase() === "total_tokens")
      .map(incidentTraceKey)
  );

  return selected.filter((row) => {
    const metric = String(row.raw?.metric_name || "").toLowerCase();
    const source = String(row.raw?.triggered_by || "").toLowerCase();
    return !(metric === "total_cost_usd" && source === "zscore" && tokenIncidentTraces.has(incidentTraceKey(row)));
  });
}

function metricLabel(value) {
  const labels = {
    total_duration_ms: "Trace latency",
    total_tokens: "Token budget",
    tool_failure_rate: "Tool failure rate",
    execution_success_rate: "Execution success rate",
    grounded_response_rate: "Grounded response rate",
  };
  if (labels[value]) return labels[value];
  return String(value || "metric")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatMetricValue(metricName, value) {
  if (value === undefined || value === null || value === "") return null;
  const metric = String(metricName || "").toLowerCase();
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (metric.includes("rate")) return `${Math.round(number * 100)}%`;
  if (metric.includes("cost")) return `$${number.toFixed(number >= 1 ? 2 : 5)}`;
  if (metric.includes("duration") || metric.includes("latency")) {
    return number >= 1000 ? `${(number / 1000).toFixed(2)}s` : `${Math.round(number)}ms`;
  }
  if (metric.includes("token") || metric.includes("count")) return number.toLocaleString();
  return Number.isInteger(number) ? number.toLocaleString() : number.toFixed(3);
}

function extractToolName(text) {
  const match = String(text || "").match(/tool failures detected:\s*([^.;]+)/i);
  return match?.[1]?.trim();
}

function afterColon(text) {
  const value = String(text || "");
  const index = value.indexOf(":");
  return index >= 0 ? value.slice(index + 1).replace(/\.$/, "").trim() : value;
}

function sloThresholdForMetric(sloData, metricName) {
  const slos = sloData?.slos || [];
  const match = slos.find((item) => item.metric_name === metricName);
  return match?.threshold_value ?? match?.target ?? null;
}

function incidentDetail(row, sloData) {
  const raw = row.raw || {};
  const category = String(raw.category || row.type || "").toLowerCase();
  const metric = raw.metric_name;
  const observed = formatMetricValue(metric, raw.observed_value);
  const configuredThreshold = sloThresholdForMetric(sloData, metric);
  const isBaselineAnomaly = String(raw.triggered_by || "").toLowerCase() === "zscore";
  const rawThreshold = isBaselineAnomaly ? null : raw.threshold_value ?? configuredThreshold;
  const threshold = formatMetricValue(metric, rawThreshold);
  const toolName = extractToolName(row.incident);

  let reason = row.incident;
  if (category.includes("execution_failure")) reason = "Run status was reported as failed.";
  else if (category.includes("finish_reason")) reason = "Model output was truncated because it reached the length limit.";
  else if (category.includes("tool")) reason = toolName ? `${toolName} failed during this trace.` : "A tool call failed during this trace.";
  else if (category.includes("loop")) {
    reason = afterColon(row.incident)
      .replace(/^repeated_tool_arguments:/i, "")
      .replace(/_/g, " ");
    if (/repeated \d+ times$/i.test(reason)) reason = `${reason} with the same arguments.`;
  }
  else if (category.includes("hallucination") || String(metric || "").includes("grounded")) {
    const existing = String(row.incident || "");
    const normalized = existing.toLowerCase();
    const isGenericGroundednessText = normalized.includes("grounded response rate breached")
      || normalized.includes("groundedness judge found unsupported output")
      || normalized.includes("groundedness is unusually low");
    reason = isGenericGroundednessText
      ? "Final answer included claims that were not supported by captured tool or context evidence."
      : existing;
  }
  else if (isBaselineAnomaly && observed) reason = `${row.incident} Observed: ${observed}.`;
  else if (observed && threshold) reason = `${metricLabel(metric)} breached. Observed: ${observed}. Threshold: ${threshold}.`;
  else if (observed && !String(metric || "").toLowerCase().includes("trace_status")) reason = `${metricLabel(metric)} breached. Observed: ${observed}.`;

  return {
    reason,
  };
}

function ReasonText({ value }) {
  return (
    <Tooltip
      title={String(value || "")}
      placement="top-start"
      arrow
      slotProps={{
        tooltip: {
          sx: {
            maxWidth: 560,
            p: 1.25,
            fontSize: 12.5,
            lineHeight: 1.45,
            whiteSpace: "normal",
            overflowWrap: "anywhere",
            color: (theme) => theme.palette.mode === "dark" ? "#e9f2ff" : "#172234",
            bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(13, 20, 30, 0.96)" : "rgba(255, 255, 255, 0.97)",
            border: "1px solid",
            borderColor: (theme) => theme.palette.mode === "dark" ? "rgba(151, 172, 203, 0.22)" : "rgba(67, 86, 112, 0.18)",
            boxShadow: (theme) => theme.palette.mode === "dark"
              ? "0 14px 38px rgba(0, 0, 0, 0.34)"
              : "0 14px 34px rgba(34, 50, 74, 0.16)",
            backdropFilter: "blur(10px)",
          },
        },
        arrow: {
          sx: {
            color: (theme) => theme.palette.mode === "dark" ? "rgba(13, 20, 30, 0.96)" : "rgba(255, 255, 255, 0.97)",
          },
        },
      }}
    >
      <Typography
        color="text.primary"
        sx={{
          display: "-webkit-box",
          WebkitBoxOrient: "vertical",
          WebkitLineClamp: 2,
          overflow: "hidden",
          fontSize: 13,
          lineHeight: 1.35,
          overflowWrap: "anywhere",
          cursor: "help",
        }}
      >
        {value}
      </Typography>
    </Tooltip>
  );
}

function IncidentEvidenceCell({ row, sloData }) {
  const detail = incidentDetail(row, sloData);
  return (
    <Stack spacing={0.25} sx={{ maxWidth: 405 }}>
      <ReasonText value={detail.reason} />
    </Stack>
  );
}

function incidentSuggestion(row) {
  const backendSuggestion = row.raw?.suggestion_text || row.recommendation || row.remediation;
  if (backendSuggestion && backendSuggestion !== "Inspect the trace replay and related metrics.") {
    return backendSuggestion;
  }

  switch (incidentFamily(row)) {
    case "execution":
      return "Open the trace and inspect the first failed span before retrying the execution.";
    case "tool":
      return "Check the failed tool's availability, credentials, timeout, and retry policy.";
    case "loop":
      return "Add an iteration limit and stop repeated tool calls with identical arguments.";
    case "latency":
      return "Inspect the slowest spans and reduce external dependency or model latency.";
    case "cost":
      return "Reduce prompt context, summarize intermediate state, and cap output tokens.";
    case "groundedness":
      return "Require tool or retrieval evidence before producing the final answer.";
    case "slo":
      return "Inspect the breached run and tune the agent before changing the configured threshold.";
    default:
      return "Inspect the trace timeline and captured evidence to identify the failing operation.";
  }
}

const REPORT_GUIDANCE = {
  execution: {
    impact: "The run did not complete reliably, so its response or downstream action may be missing, partial, or unsafe to consume.",
    avoidance: [
      "Fail fast on the first unrecoverable span and return a controlled user-facing error.",
      "Add dependency health checks and bounded retries before rerunning the workflow.",
      "Test failure paths and compensating actions before deployment.",
    ],
  },
  tool: {
    impact: "A required external operation failed, which can block the workflow or leave the answer without current business evidence.",
    avoidance: [
      "Validate tool credentials, availability, request schema, and timeout settings.",
      "Use bounded retries with backoff only for transient failures.",
      "Provide a safe fallback or escalation path when the dependency remains unavailable.",
    ],
  },
  loop: {
    impact: "Repeated work increases latency and cost and may cause duplicate external actions or exhaust the run budget.",
    avoidance: [
      "Set a maximum iteration count and stop identical tool calls with unchanged arguments.",
      "Record retry state explicitly so the agent can choose a different recovery path.",
      "Require progress between iterations before allowing the workflow to continue.",
    ],
  },
  latency: {
    impact: "The response exceeded the expected service time and may cause user abandonment, upstream timeouts, or queue buildup.",
    avoidance: [
      "Inspect the slowest model, tool, and network spans in the trace timeline.",
      "Apply dependency timeouts, caching, concurrency, or a faster model where appropriate.",
      "Keep the latency SLO aligned with the experience promised to users.",
    ],
  },
  cost: {
    impact: "This run consumed more tokens or cost than expected, reducing capacity and increasing operating expense at scale.",
    avoidance: [
      "Limit retrieved context and summarize intermediate workflow state.",
      "Set prompt and completion budgets before invoking the model.",
      "Use a smaller model for routing, extraction, and other bounded tasks.",
    ],
  },
  groundedness: {
    impact: "The final answer may contain claims that are not supported by captured context or tool evidence, reducing user trust.",
    avoidance: [
      "Require relevant retrieval or tool evidence before composing the final answer.",
      "Constrain the agent to state uncertainty when supporting evidence is unavailable.",
      "Validate important claims against captured sources before returning them.",
    ],
  },
  slo: {
    impact: "The run violated a configured reliability objective and may fall outside the service level expected for this project.",
    avoidance: [
      "Inspect the specific breached metric and its contributing spans.",
      "Correct the workflow behavior before considering a threshold change.",
      "Review SLO trends after remediation to verify sustained recovery.",
    ],
  },
  other: {
    impact: "The detected behavior may reduce the reliability, quality, or operational safety of this agent run.",
    avoidance: [
      "Review the trace timeline and interpreted evidence around the triggering operation.",
      "Add a regression test that reproduces this incident condition.",
      "Monitor the affected metric after deploying the correction.",
    ],
  },
};

function reportTimestamp(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime()) ? date.toLocaleString() : "N/A";
}

function reportDuration(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return value == null ? null : String(value);
  return number >= 1000 ? `${(number / 1000).toFixed(2)}s` : `${Math.round(number)}ms`;
}

function buildIncidentReport(row, sloData, payload) {
  const raw = { ...(row.raw || {}), ...(payload?.incident || {}) };
  const family = incidentFamily(row);
  const guidance = REPORT_GUIDANCE[family] || REPORT_GUIDANCE.other;
  const metric = raw.metric_name;
  const observed = formatMetricValue(metric, raw.observed_value);
  const configuredThreshold = sloThresholdForMetric(sloData, metric);
  const isBaselineAnomaly = String(raw.triggered_by || "").toLowerCase() === "zscore";
  const threshold = isBaselineAnomaly
    ? null
    : formatMetricValue(metric, raw.threshold_value ?? configuredThreshold);
  const reason = incidentDetail(row, sloData).reason;
  const run = payload?.run || {};
  const metrics = payload?.metrics || {};
  const slo = payload?.slo_evidence;
  const diagnostics = payload?.diagnostics || {};
  const failedToolNames = (diagnostics.failed_tools || []).map((tool) => tool.tool_name).filter(Boolean);
  const contributingFactors = [
    failedToolNames.length ? `Failed tools: ${failedToolNames.join(", ")}.` : null,
    diagnostics.loop?.detected ? `Loop signal: ${diagnostics.loop.reason || "repeated workflow activity detected"}.` : null,
    slo ? `${metricLabel(slo.metric_name || slo.metric || metric)} exceeded its configured objective.` : null,
    (diagnostics.groundedness_judgements || []).length ? "Groundedness evaluation identified unsupported response content." : null,
  ].filter(Boolean);

  return {
    incidentId: raw.incident_id || row.id,
    generatedAt: reportTimestamp(payload?.report?.generated_at || new Date().toISOString()),
    family,
    reason,
    summary: row.incident || reason,
    rootCause: raw.rca_text || reason,
    impact: guidance.impact,
    recommendation: raw.suggestion_text || incidentSuggestion(row),
    avoidance: guidance.avoidance,
    metadataFields: [
      { label: "Report type", value: "AgentSRE Trace Incident Report" },
      { label: "Generated", value: reportTimestamp(payload?.report?.generated_at || new Date().toISOString()) },
    ],
    executiveFields: [
      { label: "Incident summary", value: row.incident || reason },
      { label: "Potential impact", value: guidance.impact },
    ],
    identity: [
      { label: "Incident ID", value: raw.incident_id || row.id },
      { label: "Severity", value: raw.severity || row.severity },
      { label: "Category", value: metricLabel(raw.category || family) },
      { label: "Occurred", value: reportTimestamp(raw.created_at || row.triggeredAt) },
      { label: "Detection source", value: metricLabel(raw.triggered_by || "rule") },
    ],
    evidence: [
      { label: "Metric", value: metric ? metricLabel(metric) : null },
      { label: "Observed", value: observed },
      { label: "Threshold", value: threshold },
      { label: "Rule reference", value: raw.rule_id },
    ].filter((item) => item.value),
    runFields: [
      { label: "Trace ID", value: run.trace_id || raw.trace_id || row.trace },
      { label: "Execution ID", value: run.execution_id },
      { label: "Project ID", value: run.project_id || raw.project_id },
      { label: "Agent / service", value: run.service_name || raw.agent_id || row.agent },
      { label: "Environment", value: run.environment },
      { label: "Run status", value: run.status || metrics.trace_status },
      { label: "Started", value: run.started_at ? reportTimestamp(run.started_at) : null },
      { label: "Ended", value: run.ended_at ? reportTimestamp(run.ended_at) : null },
      { label: "Duration", value: reportDuration(run.duration_ms || metrics.total_duration_ms) },
      { label: "Model", value: metrics.model_name },
      { label: "Total tokens", value: metrics.total_tokens?.toLocaleString?.() || metrics.total_tokens },
      { label: "Estimated cost", value: metrics.total_cost_usd != null ? `$${Number(metrics.total_cost_usd).toFixed(5)}` : null },
    ].filter((item) => item.value !== null && item.value !== undefined),
    rootCauseFields: [
      { label: "Primary cause", value: raw.rca_text || reason },
      {
        label: "Rule findings",
        value: [
          raw.rule_id ? `Rule: ${raw.rule_id}` : null,
          metric ? `Metric: ${metricLabel(metric)}` : null,
          observed ? `Observed: ${observed}` : null,
          threshold ? `Threshold: ${threshold}` : null,
        ].filter(Boolean).join("\n"),
      },
      { label: "Contributing factors", value: contributingFactors.join("\n") || "No additional contributing factors were captured." },
    ],
    remediationFields: [
      { label: "Immediate action", value: raw.suggestion_text || incidentSuggestion(row) },
      ...guidance.avoidance.map((item, index) => ({ label: `Prevention ${index + 1}`, value: item })),
    ],
    operationalFields: [
      { label: "Workflow steps", value: metrics.step_count },
      { label: "Tool calls", value: metrics.tool_call_count },
      { label: "Failed tools", value: metrics.tool_failure_count },
      { label: "Tool failure rate", value: metrics.tool_failure_rate != null ? `${Math.round(Number(metrics.tool_failure_rate) * 100)}%` : null },
      { label: "LLM latency", value: reportDuration(metrics.llm_latency_ms) },
      { label: "Tool latency", value: reportDuration(metrics.total_tool_latency_ms) },
      { label: "Grounded response rate", value: metrics.grounded_response_rate != null ? `${Math.round(Number(metrics.grounded_response_rate) * 100)}%` : null },
      { label: "Loop detected", value: diagnostics.loop?.detected ? "Yes" : "No" },
      { label: "Loop reason", value: diagnostics.loop?.reason },
    ].filter((item) => item.value !== null && item.value !== undefined),
    sloFields: slo ? [
      { label: "SLO metric", value: metricLabel(slo.metric_name || slo.metric || metric) },
      { label: "Observed", value: formatMetricValue(metric, slo.observed_value ?? slo.observed ?? raw.observed_value) },
      { label: "Threshold", value: formatMetricValue(metric, slo.threshold_value ?? slo.threshold ?? raw.threshold_value) },
      { label: "Result", value: metricLabel(slo.status || slo.result || "breach") },
    ].filter((item) => item.value) : [],
    failedTools: (diagnostics.failed_tools || []).map((tool) => ({
      name: tool.tool_name || "Tool call",
      fields: [
        { label: "Step", value: tool.step_id },
        { label: "Status", value: tool.status },
        { label: "Duration", value: reportDuration(tool.duration_ms) },
        { label: "Span ID", value: tool.span_id },
        { label: "Error", value: compactError(tool.error_message, 320) },
      ].filter((item) => item.value),
    })),
    llmDiagnostics: (diagnostics.llm_calls || []).map((call) => ({
      fields: [
        { label: "Step", value: call.step_id },
        { label: "Model", value: call.model_name },
        { label: "Finish reason", value: call.finish_reason },
        { label: "Prompt tokens", value: call.prompt_tokens },
        { label: "Completion tokens", value: call.completion_tokens },
        { label: "Total tokens", value: call.total_tokens },
        { label: "Duration", value: reportDuration(call.duration_ms) },
      ].filter((item) => item.value !== null && item.value !== undefined),
    })),
    grounding: (diagnostics.groundedness_judgements || []).map((item) => (
      item.reason || item.rationale || item.explanation || "Groundedness evaluation identified unsupported response content."
    )).filter(Boolean),
    timeline: (payload?.timeline || []).map((event, index) => ({
      sequence: event.sequence_number || index + 1,
      name: event.name || "Trace event",
      type: event.canonical_type || "N/A",
      status: event.status_code || "N/A",
      duration: reportDuration(event.duration_ms) || "N/A",
      message: compactError(event.status_message, 260) || event.summary,
    })),
  };
}

function ReportSection({ title, children }) {
  return (
    <Box>
      <Typography sx={{ color: "text.primary", fontSize: 17, lineHeight: 1.3, fontWeight: 650 }}>
        {title}
      </Typography>
      <Box sx={{ mt: 0.8 }}>{children}</Box>
    </Box>
  );
}

function ReportFields({ items }) {
  const visibleItems = (items || []).filter((item) => item.value !== null && item.value !== undefined && item.value !== "");
  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 0.5, overflow: "hidden" }}>
      <Box sx={{ display: "grid", gridTemplateColumns: "minmax(130px, 28%) 1fr", bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(65, 166, 255, 0.13)" : "#dcecf5", borderBottom: "1px solid", borderColor: "divider" }}>
        <Typography sx={{ p: 0.9, fontSize: 12.5, fontWeight: 650 }}>Field</Typography>
        <Typography sx={{ p: 0.9, fontSize: 12.5, fontWeight: 650, borderLeft: "1px solid", borderColor: "divider" }}>Value</Typography>
      </Box>
      {visibleItems.map((item, index) => (
        <Box key={`${item.label}-${index}`} sx={{ display: "grid", gridTemplateColumns: "minmax(130px, 28%) 1fr", borderBottom: index < visibleItems.length - 1 ? "1px solid" : "none", borderColor: "divider" }}>
          <Typography sx={{ p: 0.9, fontSize: 12.5, color: "text.secondary" }}>{item.label}</Typography>
          <Typography component="div" sx={{ p: 0.9, fontSize: 12.5, lineHeight: 1.5, whiteSpace: "pre-wrap", overflowWrap: "anywhere", borderLeft: "1px solid", borderColor: "divider" }}>{item.value}</Typography>
        </Box>
      ))}
    </Box>
  );
}

function IncidentReportDialog({ incident, sloData, payload, loading, error, onClose }) {
  const report = incident && payload ? buildIncidentReport(incident, sloData, payload) : null;
  return (
    <Dialog
      open={Boolean(incident)}
      onClose={onClose}
      fullWidth
      maxWidth="lg"
      PaperProps={{
        sx: {
          borderRadius: 1,
          border: "1px solid",
          borderColor: "divider",
          backgroundImage: "none",
        },
      }}
    >
      {incident ? (
        <DialogContent sx={{ p: { xs: 2, sm: 2.75 } }}>
          <Stack spacing={2.25}>
            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
              <Stack direction="row" spacing={1.25} alignItems="center" sx={{ minWidth: 0 }}>
                <DescriptionOutlinedIcon color="primary" />
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="h5">AgentSRE Trace Incident Report</Typography>
                  <Typography color="text.secondary" sx={{ mt: 0.25, overflowWrap: "anywhere" }}>
                    {incident.traceName || incident.agent || "Agent trace"} / {shortTrace(incident.trace)}
                  </Typography>
                </Box>
              </Stack>
              <Stack direction="row" spacing={0.75} alignItems="center">
                {report ? (
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<DownloadOutlinedIcon />}
                    onClick={() => downloadIncidentReportPdf(report)}
                  >
                    Download PDF
                  </Button>
                ) : null}
                <IconButton onClick={onClose} aria-label="Close incident report"><CloseIcon /></IconButton>
              </Stack>
            </Stack>
            {loading ? <Stack alignItems="center" sx={{ py: 7 }}><CircularProgress size={30} /></Stack> : null}
            {error ? <Alert severity="error">{error}</Alert> : null}
            {report ? (
              <>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <StatusPill value={incident.severity} />
                  <Chip size="small" variant="outlined" label={metricLabel(report.family)} />
                </Stack>
                <ReportSection title="Report metadata"><ReportFields items={report.metadataFields} /></ReportSection>
                <ReportSection title="Incident identity"><ReportFields items={report.identity} /></ReportSection>
                <Divider />
                <ReportSection title="Executive assessment"><ReportFields items={report.executiveFields} /></ReportSection>
                <ReportSection title="Detection evidence"><ReportFields items={report.evidence} /></ReportSection>
                <ReportSection title="Run context"><ReportFields items={report.runFields} /></ReportSection>
                <ReportSection title="Operational diagnostics"><ReportFields items={report.operationalFields} /></ReportSection>
                {report.sloFields.length ? <ReportSection title="SLO evidence"><ReportFields items={report.sloFields} /></ReportSection> : null}
                <ReportSection title="Root cause analysis"><ReportFields items={report.rootCauseFields} /></ReportSection>
                {report.failedTools.length ? (
                  <ReportSection title="Failed tool diagnostics">
                    <Stack spacing={1}>{report.failedTools.map((tool, index) => <Box key={`${tool.name}-${index}`}><Typography sx={{ mb: 0.65, fontWeight: 650 }}>{tool.name}</Typography><ReportFields items={tool.fields} /></Box>)}</Stack>
                  </ReportSection>
                ) : null}
                {report.llmDiagnostics.length || report.grounding.length ? (
                  <ReportSection title="LLM and grounding diagnostics">
                    <Stack spacing={1}>
                      {report.llmDiagnostics.map((item, index) => <ReportFields key={index} items={item.fields} />)}
                      {report.grounding.map((item, index) => <Typography key={index} sx={{ lineHeight: 1.6 }}>{item}</Typography>)}
                    </Stack>
                  </ReportSection>
                ) : null}
                <ReportSection title="Remediation and prevention"><ReportFields items={report.remediationFields} /></ReportSection>
                {report.timeline.length ? (
                  <ReportSection title="Significant event timeline">
                    <Stack spacing={0.75}>{report.timeline.map((event) => (
                      <Box key={`${event.sequence}-${event.name}`} sx={{ p: 1.1, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
                        <Typography sx={{ fontSize: 13, fontWeight: 650 }}>{event.sequence}. {event.name}</Typography>
                        <Typography color="text.secondary" sx={{ fontSize: 12, mt: 0.25 }}>{event.type} / {event.status} / {event.duration}</Typography>
                        {event.message ? <Typography sx={{ fontSize: 12.5, mt: 0.55, overflowWrap: "anywhere" }}>{event.message}</Typography> : null}
                      </Box>
                    ))}</Stack>
                  </ReportSection>
                ) : null}
              </>
            ) : null}
          </Stack>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}

export default function IncidentsPage({ rows = [], sloData = null, loading = false, onAsk }) {
  const incidents = useMemo(() => dedupeIncidentRows(rows || []), [rows]);
  const [selectedFamily, setSelectedFamily] = useState("all");
  const [reportIncident, setReportIncident] = useState(null);
  const [reportPayload, setReportPayload] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState("");

  const openReport = async (row) => {
    setReportIncident(row);
    setReportPayload(null);
    setReportError("");
    setReportLoading(true);
    try {
      const result = await fetchIncidentReport(row.id);
      if (result?.error) throw new Error(result.error);
      setReportPayload(result);
    } catch (error) {
      setReportError(error?.message || "The incident report could not be loaded.");
    } finally {
      setReportLoading(false);
    }
  };
  const open = incidents.filter((row) => row.status !== "resolved").length;
  const critical = incidents.filter((row) => row.severity === "critical").length;
  const high = incidents.filter((row) => row.severity === "high").length;
  const medium = incidents.filter((row) => row.severity === "medium" || row.severity === "warning").length;
  const familyCounts = useMemo(() => {
    const counts = Object.fromEntries(FAMILY_CONFIG.map((item) => [item.id, 0]));
    counts.all = incidents.length;
    incidents.forEach((incident) => {
      const family = incidentFamily(incident);
      counts[family] = (counts[family] || 0) + 1;
    });
    return counts;
  }, [incidents]);
  const tableRows = useMemo(() => {
    const visible = selectedFamily === "all"
      ? incidents
      : incidents.filter((incident) => incidentFamily(incident) === selectedFamily);
    return [...visible].sort((left, right) => {
      const severityDelta = (SEVERITY_RANK[right.severity] || 0) - (SEVERITY_RANK[left.severity] || 0);
      if (severityDelta) return severityDelta;
      return (new Date(right.triggeredAt).getTime() || 0) - (new Date(left.triggeredAt).getTime() || 0);
    });
  }, [incidents, selectedFamily]);

  return (
    <>
      <PageHeader title="Incidents" />
      <Grid container spacing={1.75} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><MetricCard label="Open incidents" value={loading ? "..." : open} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Critical" value={loading ? "..." : critical} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="High" value={loading ? "..." : high} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Medium" value={loading ? "..." : medium} /></Grid>
      </Grid>

      <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mb: 1.5 }}>
        {FAMILY_CONFIG.filter((item) => item.id === "all" || familyCounts[item.id] > 0).map((item) => (
          <Chip
            key={item.id}
            label={`${item.label} ${familyCounts[item.id] || 0}`}
            variant="outlined"
            onClick={() => {
              setSelectedFamily(item.id);
            }}
            sx={{
              height: 30,
              borderRadius: 999,
              fontSize: 12.5,
              color: selectedFamily === item.id ? "text.primary" : "text.secondary",
              borderColor: selectedFamily === item.id ? "rgba(65, 166, 255, 0.28)" : "divider",
              background: selectedFamily === item.id ? "linear-gradient(90deg, rgba(65,166,255,.16), transparent)" : "transparent",
              "&:hover": {
                borderColor: "rgba(65, 166, 255, 0.42)",
                background: selectedFamily === item.id
                  ? "linear-gradient(90deg, rgba(65,166,255,.2), transparent)"
                  : "rgba(65, 166, 255, 0.08)"
              }
            }}
          />
        ))}
      </Stack>

      <DataTable
        rows={tableRows}
        getKey={(row) => row.id}
        emptyMessage={incidents.length ? "No incidents in this category." : "No incidents yet. Run an agent execution to populate incidents."}
        pageSize={10}
        columns={[
          { id: "severity", label: "Severity", width: "12%", render: (row) => <StatusPill value={row.severity} /> },
          { id: "triggeredAt", label: "Time", width: "12%", render: (row) => <TimestampCell value={row.triggeredAt} /> },
          {
            id: "incident",
            label: "Reason",
            width: "34%",
            render: (row) => <IncidentEvidenceCell row={row} sloData={sloData} />,
          },
          {
            id: "traceDisplay",
            label: "Trace",
            width: "20%",
            render: (row) => (
              <Box sx={{ width: "100%", maxWidth: 220 }}>
                <Typography sx={{ fontSize: 13.5, fontWeight: 560, lineHeight: 1.25 }}>
                  {row.traceName || row.traceDisplay || row.agent || row.trace}
                </Typography>
                <Typography title={row.trace} color="text.secondary" sx={{ fontSize: 11.5, lineHeight: 1.35 }}>
                  {shortTrace(row.trace)}
                </Typography>
              </Box>
            ),
          },
          {
            id: "report",
            label: "Report",
            width: "11%",
            render: (row) => (
              <Button
                size="small"
                variant="outlined"
                startIcon={<DescriptionOutlinedIcon fontSize="small" />}
                onClick={(event) => {
                  event.stopPropagation();
                  openReport(row);
                }}
                sx={{ whiteSpace: "nowrap" }}
              >
                Report
              </Button>
            ),
          },
          {
            id: "ask",
            label: "Ask",
            width: "11%",
            render: (row) => (
              <Button
                size="small"
                variant="outlined"
                startIcon={<ChatBubbleOutlineIcon fontSize="small" />}
                onClick={(event) => {
                  event.stopPropagation();
                  onAsk?.(row);
                }}
                sx={{ whiteSpace: "nowrap" }}
              >
                Ask
              </Button>
            ),
          },
        ]}
      />
      <IncidentReportDialog
        incident={reportIncident}
        sloData={sloData}
        payload={reportPayload}
        loading={reportLoading}
        error={reportError}
        onClose={() => {
          setReportIncident(null);
          setReportPayload(null);
          setReportError("");
        }}
      />
    </>
  );
}
