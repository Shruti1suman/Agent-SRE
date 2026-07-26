import { useState } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import MetricCard from "../components/MetricCard";
import PageHeader from "../components/PageHeader";
import StatusPill from "../components/StatusPill";
import { WorkflowGraph, buildTraceGraph } from "../components/Charts";

const fmtMs = (value) => (value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value}ms`);
const fmtPct = (value) => `${Math.round(Number(value || 0) * 100)}%`;

const panelSx = {
  p: 2,
  height: "100%",
  bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(17, 24, 33, 0.86)" : "rgba(255, 255, 255, 0.9)",
  borderColor: "rgba(151, 172, 203, 0.15)",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,.03)"
};

const legendItems = [
  { label: "Agent", value: "agent" },
  { label: "LLM", value: "llm" },
  { label: "Tool", value: "tool" },
  { label: "HTTP", value: "captured" },
  { label: "Failure", value: "failed" },
  { label: "Loop / retry", value: "loop" }
];

function normalizeStatus(value) {
  const status = String(value || "").toLowerCase();
  if (["completed", "success", "succeeded"].includes(status)) return "success";
  if (["failed", "failure", "error"].includes(status)) return "failed";
  return status || "unknown";
}

function edgeLabel(edge, graph) {
  const source = graph.byId.get(edge.source);
  const target = graph.byId.get(edge.target);
  if (!source || !target) return `${edge.source} -> ${edge.target}`;
  const sourceName = source.repeatCount > 1 ? `${source.name} *${source.repeatCount}` : source.name;
  const targetName = target.repeatCount > 1 ? `${target.name} *${target.repeatCount}` : target.name;
  return `${sourceName} -> ${targetName}`;
}

function DetailBlock({ label, value }) {
  if (value === undefined || value === null || value === "") return null;
  const display = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <Box>
      <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 650, textTransform: "uppercase" }}>
        {label}
      </Typography>
      <Box
        component="pre"
        sx={{
          mt: 0.5,
          m: 0,
          p: 1,
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          bgcolor: "background.paper",
          color: "text.primary",
          fontFamily: "inherit",
          fontSize: 13,
          lineHeight: 1.5,
          maxHeight: 240,
          overflow: "auto",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word"
        }}
      >
        {display}
      </Box>
    </Box>
  );
}

function InfoTile({ label, value, tone = "default" }) {
  if (value === undefined || value === null || value === "") return null;
  const toneSx = {
    error: { borderColor: "rgba(255, 98, 112, 0.42)", bgcolor: "rgba(255, 98, 112, 0.08)" },
    warning: { borderColor: "rgba(216, 179, 74, 0.42)", bgcolor: "rgba(216, 179, 74, 0.08)" },
    success: { borderColor: "rgba(53, 198, 157, 0.36)", bgcolor: "rgba(53, 198, 157, 0.08)" },
    default: { borderColor: "divider", bgcolor: "background.paper" }
  };
  return (
    <Box
      sx={{
        minWidth: 150,
        flex: "1 1 150px",
        p: 1,
        border: "1px solid",
        borderRadius: 1.4,
        ...toneSx[tone]
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontWeight: 650, textTransform: "uppercase" }}>
        {label}
      </Typography>
      <Typography sx={{ mt: 0.35, fontWeight: 650, overflowWrap: "anywhere" }}>{String(value)}</Typography>
    </Box>
  );
}

function metricLabel(value) {
  return String(value || "Metric")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatSloValue(metricName, value) {
  if (value === undefined || value === null || value === "") return "N/A";
  const metric = String(metricName || "").toLowerCase();
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  if (metric.includes("rate")) return fmtPct(numeric);
  if (metric.includes("duration") || metric.includes("latency")) return fmtMs(Math.round(numeric));
  if (metric.includes("token") || metric.includes("count")) return numeric.toLocaleString();
  if (metric.includes("cost")) return `$${numeric.toFixed(numeric >= 1 ? 2 : 5)}`;
  return Number.isInteger(numeric) ? numeric.toLocaleString() : numeric.toFixed(3);
}

function observedForConfig(trace, metricName) {
  const metric = trace.metric || {};
  if (metricName === "execution_success_rate") {
    return normalizeStatus(trace.status || metric.trace_status) === "success" ? 1 : 0;
  }
  return metric[metricName];
}

function operatorText(operator) {
  if (operator === "gt") return "at most";
  if (operator === "gte") return "below";
  if (operator === "lt") return "at least";
  if (operator === "lte") return "above";
  return "target";
}

function isRiskStatus(result) {
  const observed = Number(result.observed_value);
  const threshold = Number(result.threshold_value);
  if (!Number.isFinite(observed) || !Number.isFinite(threshold) || threshold <= 0 || result.status === "breached") return false;
  if (result.metric_name === "execution_success_rate") return false;
  const operator = String(result.operator || "");
  if (operator === "gt" || operator === "gte") return observed >= threshold * 0.8;
  if (operator === "lt" || operator === "lte") return observed <= threshold * 1.2;
  return false;
}

function breachesSlo(operator, observedValue, thresholdValue) {
  const observed = Number(observedValue);
  const threshold = Number(thresholdValue);
  if (!Number.isFinite(observed) || !Number.isFinite(threshold)) return null;
  if (operator === "gt") return observed > threshold;
  if (operator === "gte") return observed >= threshold;
  if (operator === "lt") return observed < threshold;
  if (operator === "lte") return observed <= threshold;
  return null;
}

function runSloRows(trace, sloData) {
  const configured = Array.isArray(sloData?.slos) ? sloData.slos : [];
  const results = trace.sloResults || trace.metric?.slo_results || [];
  const bySlo = new Map(results.map((row) => [row.slo_id, row]));
  const byMetric = new Map(results.map((row) => [row.metric_name, row]));
  return configured
    .filter((row) => row.enabled !== false)
    .map((config) => {
      const result = bySlo.get(config.slo_id) || byMetric.get(config.metric_name) || {};
      const observedValue = result.observed_value ?? observedForConfig(trace, config.metric_name);
      const thresholdValue = result.threshold_value ?? config.threshold_value ?? config.target;
      const operator = result.operator || config.operator;
      const fallbackBreach = breachesSlo(operator, observedValue, thresholdValue);
      const fallbackStatus = fallbackBreach === null ? "" : fallbackBreach ? "breached" : "compliant";
      const merged = {
        ...config,
        ...result,
        label: result.label || config.metric || config.label,
        threshold_value: thresholdValue,
        operator,
        observed_value: observedValue,
        status: result.status || fallbackStatus,
      };
      const breached = result.status === "breached";
      const risk = isRiskStatus(merged);
      const status = breached || merged.status === "breached" ? "BREACH" : risk ? "RISK" : merged.status ? "HEALTHY" : "N/A";
      return { ...merged, status };
    });
}

function RunSloPanel({ trace, sloData }) {
  const rows = runSloRows(trace, sloData);
  const healthy = rows.filter((row) => row.status === "HEALTHY").length;
  const risks = rows.filter((row) => row.status === "RISK").length;
  const breaches = rows.filter((row) => row.status === "BREACH").length;
  const overall = breaches ? "BREACH" : risks ? "RISK" : rows.length ? "HEALTHY" : "N/A";

  return (
    <Card variant="outlined" sx={panelSx}>
      <Stack spacing={1.5}>
        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
          <Box>
            <Typography variant="h6">Run SLOs</Typography>
            <Typography variant="caption" color="text.secondary">
              SLO evaluation for {trace.displayName || trace.root || trace.agent || "selected trace"}
            </Typography>
          </Box>
          <StatusPill value={overall.toLowerCase()} />
        </Stack>

        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, minmax(0, 1fr))", md: "repeat(4, minmax(0, 1fr))" }, gap: 1 }}>
          <InfoTile
            label="Status"
            value={String(trace.status || trace.metric?.trace_status || "unknown").toUpperCase()}
            tone={normalizeStatus(trace.status || trace.metric?.trace_status) === "failed" ? "error" : "success"}
          />
          <InfoTile label="Healthy" value={healthy} tone="success" />
          <InfoTile label="Risk" value={risks} tone="warning" />
          <InfoTile label="Breaches" value={breaches} tone="error" />
        </Box>

        {rows.length ? (
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 1.2 }}>
            {rows.map((row) => {
              return (
                <Box
                  key={row.slo_id || row.metric_name}
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1.5,
                    p: 1.35,
                    bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(9, 15, 23, 0.42)" : "rgba(248, 251, 253, 0.78)",
                  }}
                >
                  <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1.5}>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography sx={{ fontWeight: 700, lineHeight: 1.25 }}>{row.label || metricLabel(row.metric_name)}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {operatorText(row.operator)} {formatSloValue(row.metric_name, row.threshold_value)}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end" sx={{ flexShrink: 0 }}>
                      <Typography sx={{ fontWeight: 760, lineHeight: 1 }}>
                        {formatSloValue(row.metric_name, row.observed_value)}
                      </Typography>
                      <StatusPill value={row.status.toLowerCase()} />
                    </Stack>
                  </Stack>
                </Box>
              );
            })}
          </Box>
        ) : (
          <Typography color="text.secondary">No run SLO evaluation was captured for this trace.</Typography>
        )}
      </Stack>
    </Card>
  );
}

function spanFacts(span) {
  const status = String(span.status || "unknown").toLowerCase();
  return [
    { label: "Status", value: span.status || "unknown", tone: status.includes("fail") || status.includes("error") ? "error" : "success" },
    { label: "Duration", value: fmtMs(span.duration || 0) },
    { label: "Type", value: String(span.kind || "span").toUpperCase() },
    { label: "Retry count", value: span.retryCount || 0, tone: Number(span.retryCount || 0) ? "warning" : "default" },
    {
      label: "Child failures",
      value: span.failedChildCount ? `${span.failedChildCount}: ${span.failedChildNames.join(", ")}` : null,
      tone: "error",
    },
    { label: "Model", value: span.modelName || span.provider },
    { label: "Tool", value: span.toolName || span.raw?.tool_name },
    { label: "Span id", value: span.id },
    { label: "Parent span", value: span.parentSpanId || "root" },
    { label: "Step id", value: span.stepId },
    { label: "Error", value: span.error, tone: "error" },
  ];
}

export default function ExplorerPage({ trace, sloData, loading, error, setPage }) {
  const [graphMode, setGraphMode] = useState("workflow");
  const [expandedSpanId, setExpandedSpanId] = useState(null);

  if (!trace) {
    return (
      <>
        <PageHeader title="Trace explorer" action={<Button variant="outlined" onClick={() => setPage("traces")}>Back to traces</Button>} />
        <Alert severity="info">Select a trace from the Traces page to inspect replay details.</Alert>
      </>
    );
  }

  const spans = trace.spansList || [];
  const graph = buildTraceGraph(trace, graphMode);
  const mainGraphEdges = graphMode === "workflow" ? graph.edges.filter((edge) => !edge.childEdge) : graph.edges;
  const slowestSpan = graph.slowestSpan;
  const redactions = Number(trace.redactions || trace.privacy?.masked_fields_count || 0);
  const graphTitle = graphMode === "workflow" ? "Workflow graph" : "Span hierarchy";
  const graphSubtitle = graphMode === "workflow"
    ? `${mainGraphEdges.length} transitions - ${graph.loopNodes.length} loop-risk workflow nodes - ${graph.retryCount} retries`
    : `${graph.edges.length} edges - ${graph.loopNodes.length} repeated spans - ${graph.retryCount} retries`;
  const openTimelineSpan = ({ spanId }) => {
    const span = spans.find((item) => item.id === spanId || item.raw?.span_id === spanId);
    if (!span) return;
    setExpandedSpanId(span.id);
    window.setTimeout(() => {
      document.getElementById(`timeline-span-${span.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 80);
  };

  return (
    <>
      <PageHeader title="Trace explorer" action={<Button variant="outlined" onClick={() => setPage("traces")}>Back to traces</Button>} />
      {loading ? <Alert severity="info" sx={{ mb: 2 }}>Loading trace replay...</Alert> : null}
      {error ? <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert> : null}
      <Grid container spacing={1.75} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><MetricCard label="Spans" value={trace.spans} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="LLM calls" value={trace.llm} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Tool calls" value={trace.tools} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Redactions" value={redactions} /></Grid>
      </Grid>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card variant="outlined" sx={panelSx}>
            <Stack spacing={1.25}>
              <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                <Box>
                  <Typography variant="h6">{graphTitle}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {graphSubtitle}
                    {graph.fallback ? " - workflow metadata unavailable, showing span hierarchy" : ""}
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                  <ToggleButtonGroup
                    exclusive
                    size="small"
                    value={graphMode}
                    onChange={(_, value) => value && setGraphMode(value)}
                    sx={{
                      "& .MuiToggleButton-root": {
                        px: 1.2,
                        py: 0.35,
                        fontSize: 12,
                        textTransform: "none"
                      }
                    }}
                  >
                    <ToggleButton value="workflow">Workflow</ToggleButton>
                    <ToggleButton value="span">Span hierarchy</ToggleButton>
                  </ToggleButtonGroup>
                  <Chip size="small" label={`${graph.failedCount} failed`} color={graph.failedCount ? "error" : "success"} variant="outlined" />
                  <Chip size="small" label={`${graph.loopNodes.length} loop risk`} color={graph.loopNodes.length ? "warning" : "success"} variant="outlined" />
                  <Chip size="small" label={`${graph.retryCount} retries`} color={graph.retryCount ? "warning" : "default"} variant="outlined" />
                </Stack>
              </Stack>
              <WorkflowGraph trace={trace} mode={graphMode} onNodeSelect={openTimelineSpan} />
            </Stack>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={panelSx}>
            <Typography variant="h6" sx={{ mb: 1.5 }}>Risk signals</Typography>
            <Stack spacing={1.1}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1.5}>
                <Typography color="text.secondary">Loop risk</Typography>
                <StatusPill value={graph.loopNodes.length ? "warning" : "none"} />
              </Stack>
              <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1.5}>
                <Typography color="text.secondary">Retries</Typography>
                <StatusPill value={graph.retryCount || "0"} />
              </Stack>
              <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1.5}>
                <Typography color="text.secondary">Failed spans</Typography>
                <StatusPill value={graph.failedCount || "0"} />
              </Stack>
              <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1.5}>
                <Typography color="text.secondary">Slowest span</Typography>
                <Chip
                  size="small"
                  variant="outlined"
                  label={slowestSpan ? `${slowestSpan.name} / ${fmtMs(slowestSpan.duration)}` : "N/A"}
                  sx={{ maxWidth: "72%", justifyContent: "flex-start" }}
                />
              </Stack>
            </Stack>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={panelSx}>
            <Typography variant="h6" sx={{ mb: 1.5 }}>Graph legend</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
              {legendItems.map((item) => <StatusPill key={item.label} value={item.value} />)}
            </Stack>
            <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 1.25, maxHeight: 160, overflowY: "auto" }}>
              <Stack spacing={0.9}>
                {mainGraphEdges.length ? mainGraphEdges.map((edge, index) => (
                  <Typography key={`${edge.source}-${edge.target}-${index}`} color="text.secondary" variant="body2">
                    {edgeLabel(edge, graph)}
                  </Typography>
                )) : (
                  <Typography color="text.secondary">No graph edges available.</Typography>
                )}
              </Stack>
            </Box>
          </Card>
        </Grid>
        <Grid item xs={12}>
          <RunSloPanel trace={trace} sloData={sloData} />
        </Grid>
        <Grid item xs={12}>
          <Card variant="outlined" sx={panelSx}>
            <Typography variant="h6" sx={{ mb: 1.5 }}>Timeline</Typography>
            <Stack spacing={1.2}>
              {spans.length ? spans.map((span, index) => (
                <Accordion
                  key={span.id || span.name}
                  id={`timeline-span-${span.id}`}
                  expanded={expandedSpanId === span.id}
                  onChange={(_, expanded) => setExpandedSpanId(expanded ? span.id : null)}
                  disableGutters
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                    bgcolor: "background.default",
                    boxShadow: "none",
                    "&:before": { display: "none" },
                    "&.Mui-expanded": { m: 0 }
                  }}
                >
                  <AccordionSummary
                    expandIcon={<ExpandMoreIcon fontSize="small" />}
                    sx={{
                      minHeight: 58,
                      px: 1.25,
                      "&.Mui-expanded": { minHeight: 58 },
                      "& .MuiAccordionSummary-content": {
                        my: 1,
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 1.25,
                        minWidth: 0
                      }
                    }}
                  >
                    <Stack direction="row" spacing={1.25} alignItems="center" sx={{ minWidth: 0, flex: 1 }}>
                      <Chip size="small" label={index + 1} color="success" sx={{ minWidth: 34, flexShrink: 0 }} />
                      <Box sx={{ minWidth: 0 }}>
                        <Typography noWrap>{span.name}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {String(span.kind || "span").toUpperCase()} - {String(span.status || "unknown").toUpperCase()} - {fmtMs(span.duration)}
                        </Typography>
                      </Box>
                    </Stack>
                    <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
                      <StatusPill value={span.status} />
                      <StatusPill value={span.kind} />
                    </Stack>
                  </AccordionSummary>
                  <AccordionDetails sx={{ px: 1.5, pt: 0, pb: 1.5 }}>
                    <Stack spacing={1.25}>
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                        {spanFacts(span).map((fact) => (
                          <InfoTile key={fact.label} label={fact.label} value={fact.value} tone={fact.tone} />
                        ))}
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, textTransform: "uppercase" }}>
                          Captured payloads
                        </Typography>
                        <Stack spacing={1.1} sx={{ mt: 0.8 }}>
                          <DetailBlock label="Input" value={span.input} />
                          <DetailBlock label="Output" value={span.output || span.toolOutput} />
                          <DetailBlock label="Raw captured payload" value={span.raw} />
                          {!span.input && !span.output && !span.toolOutput && !span.raw ? (
                            <Typography variant="body2" color="text.secondary">No detailed payload captured for this span.</Typography>
                          ) : null}
                        </Stack>
                      </Box>
                    </Stack>
                  </AccordionDetails>
                </Accordion>
              )) : (
                <Typography color="text.secondary">No replay spans loaded yet.</Typography>
              )}
            </Stack>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
