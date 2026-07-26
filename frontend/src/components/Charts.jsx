import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { compactError } from "../utils/errorFormat";

const LOOP_COLOR = "#ff8a4c";
const TOOL_COLOR = "#d8b34a";

function niceNumber(value) {
  if (value <= 0) return 1;
  const exponent = Math.floor(Math.log10(value));
  const fraction = value / 10 ** exponent;
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return niceFraction * 10 ** exponent;
}

function axisTicks(maxValue, targetSteps = 4) {
  const max = Number(maxValue) > 0 ? Number(maxValue) : 1;
  const step = niceNumber(max / targetSteps);
  const niceMax = Math.ceil(max / step) * step;
  const ticks = [];
  for (let value = 0; value <= niceMax + step / 2; value += step) {
    ticks.push(Number(value.toFixed(8)));
  }
  return { max: niceMax, ticks };
}

function ChartTooltip({ tooltip }) {
  const theme = useTheme();
  if (!tooltip) return null;
  const isDark = theme.palette.mode === "dark";
  const placement = tooltip.placement || "right";
  return (
    <Box
      sx={{
        position: "absolute",
        left: tooltip.x,
        top: tooltip.y,
        transform: placement === "left" ? "translate(calc(-100% - 10px), -88%)" : "translate(10px, -88%)",
        pointerEvents: "none",
        zIndex: 2,
        px: 1.15,
        py: 0.85,
        width: "max-content",
        minWidth: 0,
        maxWidth: "min(360px, calc(100vw - 48px))",
        border: "1px solid",
        borderColor: isDark ? "rgba(151, 172, 203, 0.22)" : "rgba(67, 86, 112, 0.18)",
        borderRadius: 1,
        bgcolor: isDark ? "rgba(13, 20, 30, 0.96)" : "rgba(255, 255, 255, 0.97)",
        boxShadow: isDark
          ? "0 14px 38px rgba(0, 0, 0, 0.34), inset 0 1px 0 rgba(255, 255, 255, 0.04)"
          : "0 14px 34px rgba(34, 50, 74, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.9)",
        color: isDark ? "#e9f2ff" : "#172234",
        backdropFilter: "blur(10px)"
      }}
    >
      <Typography
        variant="caption"
        sx={{
          display: "block",
          color: isDark ? "rgba(233, 242, 255, 0.68)" : "rgba(23, 34, 52, 0.62)",
          fontWeight: 700,
          maxWidth: "min(336px, calc(100vw - 72px))",
          whiteSpace: "normal",
          overflowWrap: "anywhere",
          wordBreak: "break-word"
        }}
      >
        {tooltip.title}
      </Typography>
      <Typography
        variant="body2"
        sx={{
          color: isDark ? "#ffffff" : "#172234",
          fontWeight: 760,
          lineHeight: 1.35,
          whiteSpace: "pre-line",
          overflowWrap: "anywhere",
          wordBreak: "break-word"
        }}
      >
        {tooltip.value}
      </Typography>
    </Box>
  );
}

function svgTooltipPosition(event) {
  const rect = event.currentTarget.ownerSVGElement.getBoundingClientRect();
  const point = event.touches?.[0] || event.changedTouches?.[0] || event;
  const x = point.clientX - rect.left;
  const y = point.clientY - rect.top;
  return {
    x,
    y,
    placement: x > rect.width / 2 ? "left" : "right",
  };
}

const chartAnimationStyles = `
  @keyframes agentsreLineDraw {
    from { stroke-dashoffset: 1200; }
    to { stroke-dashoffset: 0; }
  }
  @keyframes agentsreFadeScale {
    from { opacity: 0; transform: scale(0.6); }
    to { opacity: 1; transform: scale(1); }
  }
  @keyframes agentsreBarGrowX {
    from { transform: scaleX(0); opacity: 0.35; }
    to { transform: scaleX(1); opacity: 1; }
  }
  @keyframes agentsreBarGrowY {
    from { transform: scaleY(0); opacity: 0.35; }
    to { transform: scaleY(1); opacity: 1; }
  }
`;

export function SimpleLineChart({ rows, data, height = 240, compact = false }) {
  const [tooltip, setTooltip] = useState(null);
  const chartRows = rows || data || [];
  const width = 760;
  const top = compact ? 18 : 30;
  const bottom = compact ? 24 : 38;
  const right = compact ? 24 : 40;
  const leftPad = 70;
  const observedMax = Math.max(...chartRows.map((row) => Number(row.value) || 0), 1);
  const { max, ticks } = axisTicks(observedMax * 1.1);
  const plotHeight = height - top - bottom;
  const points = chartRows.map((row, index) => {
    const value = Number(row.value) || 0;
    const x = leftPad + (index * (width - leftPad - right)) / Math.max(chartRows.length - 1, 1);
    const y = top + (1 - value / max) * plotHeight;
    return { ...row, x, y };
  });

  const showTooltip = (event, point) => {
    setTooltip({
      ...svgTooltipPosition(event),
      title: point.tooltipTitle || point.label,
      value: point.detail || `${point.value}`,
    });
  };

  return (
    <Box sx={{ minHeight: height, width: "100%", flex: 1, position: "relative" }}>
      {!chartRows.length ? (
        <Box sx={{ minHeight: height, display: "grid", placeItems: "center" }}>
          <Typography color="text.secondary">No trace latency yet.</Typography>
        </Box>
      ) : (
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Line chart" style={{ width: "100%", minHeight: height, display: "block" }}>
          <defs>
            <style>{chartAnimationStyles}</style>
            <linearGradient id="muiLineGrad" x1="0" x2="1">
              <stop stopColor="#41a6ff" />
              <stop offset="1" stopColor="#69e6d3" />
            </linearGradient>
          </defs>
          {ticks.map((tick) => {
            const y = top + (1 - tick / max) * plotHeight;
            return (
              <g key={tick}>
                <line x1={leftPad} x2={width - right} y1={y} y2={y} stroke="currentColor" opacity=".08" />
                <text x={8} y={y + 4} fill="currentColor" opacity=".52" fontSize="11" fontWeight="650">{tick}ms</text>
              </g>
            );
          })}
          <polyline
            points={points.map((point) => `${point.x},${point.y}`).join(" ")}
            fill="none"
            stroke="url(#muiLineGrad)"
            strokeWidth="2.4"
            pathLength="1200"
            style={{
              strokeDasharray: 1200,
              animation: "agentsreLineDraw 900ms ease-out both"
            }}
          />
          {points.map((point, index) => (
            <circle
              key={`${point.label}-${index}`}
              cx={point.x}
              cy={point.y}
              r="4.7"
              fill="#41a6ff"
              stroke="#65d8dc"
              strokeWidth="1"
              style={{
                cursor: "default",
                opacity: 0,
                transformBox: "fill-box",
                transformOrigin: "center",
                animation: `agentsreFadeScale 360ms ease-out ${Math.min(index * 45 + 260, 900)}ms both`
              }}
              onMouseEnter={(event) => showTooltip(event, point)}
              onMouseMove={(event) => showTooltip(event, point)}
              onMouseLeave={() => setTooltip(null)}
              onTouchStart={(event) => showTooltip(event, point)}
              onTouchMove={(event) => showTooltip(event, point)}
              onTouchEnd={() => setTooltip(null)}
            />
          ))}
        </svg>
      )}
      <ChartTooltip tooltip={tooltip} />
    </Box>
  );
}

export function BarList({ rows, valueKey = "value", format = (value) => value }) {
  const max = Math.max(...rows.map((row) => Number(row[valueKey]) || 0), 1);
  return (
    <Stack spacing={1.05}>
      {rows.map((row, index) => {
        const value = Number(row[valueKey]) || 0;
        return (
          <Box key={`${row.label}-${index}`}>
            <Stack direction="row" justifyContent="space-between" spacing={2} sx={{ mb: 0.5 }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 650 }}>{row.label}</Typography>
              <Typography variant="caption" sx={{ fontWeight: 760 }}>{format(value)}</Typography>
            </Stack>
            <Box sx={{ height: 16, borderRadius: 0.8, bgcolor: "rgba(151,172,203,.08)", overflow: "hidden" }}>
              <Box
                title={row.detail || `${row.label}: ${format(value)}`}
                sx={{
                  height: "100%",
                  width: `${Math.max(5, (value / max) * 100)}%`,
                  borderRadius: 1,
                  background: "linear-gradient(90deg, #41a6ff, #a78bfa)"
                }}
              />
            </Box>
          </Box>
        );
      })}
    </Stack>
  );
}

export function HorizontalBarChart({ rows, valueKey = "value", maxValue, format = (value) => value, height = 210, showYAxisLabels = true }) {
  const [tooltip, setTooltip] = useState(null);
  const rawMax = maxValue || Math.max(...rows.map((row) => Number(row[valueKey]) || 0), 0);
  const { max, ticks } = axisTicks(rawMax);
  const width = 560;
  const left = showYAxisLabels ? 150 : 28;
  const right = 28;
  const top = 20;
  const rowHeight = Math.max(32, (height - top - 26) / rows.length);

  const showTooltip = (event, row, value) => {
    setTooltip({
      ...svgTooltipPosition(event),
      title: row.tooltipTitle || row.label,
      value: row.detail || format(value),
    });
  };

  return (
    <Box sx={{ minHeight: height, width: "100%", flex: 1, position: "relative" }}>
      {!rows.length ? (
        <Box sx={{ minHeight: height, display: "grid", placeItems: "center" }}>
          <Typography color="text.secondary">No data yet.</Typography>
        </Box>
      ) : (
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Horizontal bar chart" style={{ width: "100%", minHeight: height, display: "block" }}>
          <defs>
            <style>{chartAnimationStyles}</style>
            <linearGradient id="horizontalBarGrad" x1="0" x2="1">
              <stop stopColor="#41a6ff" />
              <stop offset="1" stopColor="#a78bfa" />
            </linearGradient>
          </defs>
          {ticks.map((tick) => {
            const x = left + (tick / max) * (width - left - right);
            return (
              <g key={tick}>
                <line x1={x} x2={x} y1={top} y2={height - 26} stroke="currentColor" opacity=".08" />
                <text x={x} y={height - 4} textAnchor="middle" fill="currentColor" opacity=".55" fontSize="12" fontWeight="650">
                  {format(tick)}
                </text>
              </g>
            );
          })}
          {rows.map((row, index) => {
            const value = Number(row[valueKey]) || 0;
            const y = top + index * rowHeight + rowHeight * 0.28;
            const barWidth = Math.max(8, (value / max) * (width - left - right));
            return (
              <g key={`${row.label}-${index}`}>
                {showYAxisLabels ? (
                  <text x={0} y={y + 10} fill="currentColor" opacity=".68" fontSize="13" fontWeight="650">{row.label}</text>
                ) : null}
                <rect
                  x={left}
                  y={y}
                  width={barWidth}
                  height="20"
                  rx="4"
                  fill="url(#horizontalBarGrad)"
                  style={{
                    cursor: "default",
                    transformBox: "fill-box",
                    transformOrigin: "left center",
                    animation: `agentsreBarGrowX 680ms cubic-bezier(.2,.8,.2,1) ${Math.min(index * 70, 420)}ms both`
                  }}
                  onMouseEnter={(event) => showTooltip(event, row, value)}
                  onMouseMove={(event) => showTooltip(event, row, value)}
                  onMouseLeave={() => setTooltip(null)}
                  onTouchStart={(event) => showTooltip(event, row, value)}
                  onTouchMove={(event) => showTooltip(event, row, value)}
                  onTouchEnd={() => setTooltip(null)}
                />
              </g>
            );
          })}
        </svg>
      )}
      <ChartTooltip tooltip={tooltip} />
    </Box>
  );
}

export function VerticalBarChart({ rows, valueKey = "value", maxValue, format = (value) => value, height = 210, scrollable = false }) {
  const [tooltip, setTooltip] = useState(null);
  const values = rows.map((row) => Number(row[valueKey]) || 0);
  const { max, ticks } = axisTicks(maxValue || Math.max(...values, 0));
  const baseWidth = 560;
  const left = 76;
  const right = 20;
  const top = 22;
  const bottom = 34;
  const chartHeight = height - top - bottom;
  const regularGap = 16;
  const visibleBarCapacity = 20;
  const scrollableBarWidth = 10;
  const visiblePlotWidth = baseWidth - left - right;
  const scrollableSlotWidth = visiblePlotWidth / visibleBarCapacity;
  const width = scrollable
    ? left + right + Math.max(rows.length, visibleBarCapacity) * scrollableSlotWidth
    : baseWidth;
  const barWidth = scrollable
    ? scrollableBarWidth
    : Math.max(8, (width - left - right - regularGap * (rows.length - 1)) / rows.length);

  const showTooltip = (event, row, value) => {
    const position = svgTooltipPosition(event);
    const scrollLeft = scrollable ? event.currentTarget.ownerSVGElement?.parentElement?.scrollLeft || 0 : 0;
    setTooltip({
      ...position,
      x: position.x - scrollLeft,
      title: row.tooltipTitle || row.label,
      value: row.detail || format(value),
    });
  };

  return (
    <Box sx={{ minHeight: height, width: "100%", flex: 1, position: "relative" }}>
      {!rows.length ? (
        <Box sx={{ minHeight: height, display: "grid", placeItems: "center" }}>
          <Typography color="text.secondary">No data yet.</Typography>
        </Box>
      ) : (
        <Box
          onScroll={() => setTooltip(null)}
          sx={{
            width: "100%",
            overflowX: scrollable ? "auto" : "hidden",
            overflowY: "hidden",
            pb: scrollable && width > baseWidth ? 0.5 : 0,
            scrollbarWidth: "thin",
            scrollbarColor: "rgba(151, 172, 203, 0.35) transparent",
            "&::-webkit-scrollbar": { height: 7 },
            "&::-webkit-scrollbar-thumb": {
              bgcolor: "rgba(151, 172, 203, 0.35)",
              borderRadius: 999,
            },
          }}
        >
          <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Vertical bar chart" style={{ width: scrollable ? `${width}px` : "100%", minWidth: scrollable ? `${width}px` : 0, minHeight: height, display: "block" }}>
            <defs>
              <style>{chartAnimationStyles}</style>
              <linearGradient id="verticalBarGrad" x1="0" x2="0" y1="0" y2="1">
                <stop stopColor="#62e0dc" />
                <stop offset="1" stopColor="#41a6ff" />
              </linearGradient>
            </defs>
            {ticks.map((tick) => {
              const y = top + (1 - tick / max) * chartHeight;
              return (
                <g key={tick}>
                  <line x1={left} x2={width - right} y1={y} y2={y} stroke="currentColor" opacity=".08" />
                  <text x={8} y={y + 4} fill="currentColor" opacity=".58" fontSize="12" fontWeight="650">{format(tick)}</text>
                </g>
              );
            })}
            {rows.map((row, index) => {
              const value = Number(row[valueKey]) || 0;
              const barHeight = Math.max(5, (value / max) * chartHeight);
              const x = scrollable
                ? left + index * scrollableSlotWidth + (scrollableSlotWidth - barWidth) / 2
                : left + index * (barWidth + regularGap);
              const y = top + chartHeight - barHeight;
              return (
                <rect
                  key={`${row.label}-${index}`}
                  x={x}
                  y={y}
                  width={barWidth}
                  height={barHeight}
                  rx="4"
                  fill="url(#verticalBarGrad)"
                  style={{
                    cursor: "default",
                    transformBox: "fill-box",
                    transformOrigin: "center bottom",
                    animation: `agentsreBarGrowY 680ms cubic-bezier(.2,.8,.2,1) ${Math.min(index * 55, 520)}ms both`
                  }}
                  onMouseEnter={(event) => showTooltip(event, row, value)}
                  onMouseMove={(event) => showTooltip(event, row, value)}
                  onMouseLeave={() => setTooltip(null)}
                  onTouchStart={(event) => showTooltip(event, row, value)}
                  onTouchMove={(event) => showTooltip(event, row, value)}
                  onTouchEnd={() => setTooltip(null)}
                />
              );
            })}
          </svg>
        </Box>
      )}
      <ChartTooltip tooltip={tooltip} />
    </Box>
  );
}

function cleanSpanName(value) {
  return String(value || "Span")
    .replace(/^langgraph\./i, "")
    .replace(/^agent\./i, "")
    .replace(/_/g, " ")
    .trim() || "Span";
}

function graphKind(step) {
  return String(step.kind || step.canonicalType || step.canonical_type || step.span_kind || "").toLowerCase();
}

function graphStatusFailed(step) {
  const status = String(step.status || step.status_code || "").toLowerCase();
  return ["failed", "failure", "error"].some((item) => status.includes(item)) || Boolean(step.error || step.error_message || step.status_message);
}

function graphNodeColor(step) {
  const kind = graphKind(step);
  if (graphStatusFailed(step)) return "#ff6270";
  if (kind.includes("llm")) return "#6ea8fe";
  if (kind.includes("tool")) return TOOL_COLOR;
  if (kind.includes("http")) return "#b48cff";
  if (kind.includes("memory")) return "#7c8da6";
  if (kind.includes("reasoning")) return "#f472b6";
  return "#35c69d";
}

function graphNodeSize(step) {
  if (step.isChild) return graphStatusFailed(step) ? 17 : 14;
  const duration = Number(step.duration || step.duration_ms || 0);
  const base = graphStatusFailed(step) ? 22 : 18;
  const repeatBoost = step.repeatCount > 1 ? Math.min(step.repeatCount, 6) : 0;
  return Math.min(base + Math.sqrt(Math.max(duration, 0)) / 8 + repeatBoost, 36);
}

function spanHierarchyNodeSize(step) {
  return Math.max(10, Math.round(graphNodeSize(step) * 0.74));
}

function graphDepth(step, byId) {
  let depth = 0;
  let parentId = step.parentSpanId || step.parent_span_id;
  const seen = new Set();
  while (parentId && byId.has(parentId) && !seen.has(parentId)) {
    seen.add(parentId);
    depth += 1;
    parentId = byId.get(parentId)?.parentSpanId || byId.get(parentId)?.parent_span_id;
  }
  return Math.min(depth, 3);
}

function graphTooltip(step) {
  const duration = Number(step.duration || step.duration_ms || 0);
  const name = cleanSpanName(step.name || step.span_name || step.id);
  const displayName = name.length > 46 ? `${name.slice(0, 43)}...` : name;
  const rows = [
    `<strong>${displayName}</strong>`,
    `${String(step.kind || step.canonicalType || step.canonical_type || "span").toUpperCase()} / ${step.status || step.status_code || "unknown"}`,
    duration >= 1000 ? `${(duration / 1000).toFixed(2)}s` : `${Math.round(duration)}ms`
  ];
  if (step.repeatCount > 1) rows.push(`Repeated: ${step.repeatCount} spans`);
  if (step.repeatCount > 1) rows.push(`Average: ${Math.round(duration / step.repeatCount)}ms`);
  if (step.childSummary) {
    const summary = step.childSummary;
    rows.push(`Child spans: ${summary.total || 0}`);
    rows.push(`LLM: ${summary.llm || 0} / Tool: ${summary.tool || 0} / HTTP: ${summary.http || 0}`);
    if (summary.memory) rows.push(`Memory: ${summary.memory}`);
    if (summary.failed) rows.push(`Child failures: ${summary.failed}`);
  }
  if (step.invocationRepeatCount >= 3) rows.push(`Same tool arguments repeated: ${step.invocationRepeatCount} times`);
  if (step.repeatedTools?.length) {
    step.repeatedTools.forEach((tool) => rows.push(`Loop: ${cleanSpanName(tool.name)} repeated ${tool.count} times`));
  }
  if (step.modelName || step.model_name) rows.push(`Model: ${step.modelName || step.model_name}`);
  if (step.toolName || step.tool_name) rows.push(`Tool: ${step.toolName || step.tool_name}`);
  if (step.error || step.error_message || step.status_message) {
    const error = compactError(step.error || step.error_message || step.status_message);
    rows.push(error);
  }
  if (step.failedChildNames?.length) rows.push(`Failed child: ${step.failedChildNames.slice(0, 3).join(", ")}`);
  return rows.join("<br/>");
}

function normalizeWorkflowName(value) {
  return cleanSpanName(value)
    .replace(/^LangGraph Node:\s*/i, "")
    .replace(/^LangGraph Graph:\s*/i, "")
    .trim() || "Workflow node";
}

function isGraphRootStep(step) {
  const name = cleanSpanName(step.name || step.span_name || "");
  return /^LangGraph Graph:/i.test(name) || / Graph:/i.test(name);
}

function isWorkflowStep(step) {
  const kind = graphKind(step);
  const canonical = String(step.canonicalType || step.canonical_type || "").toUpperCase();
  const name = cleanSpanName(step.name || step.span_name || "");
  if (isGraphRootStep(step)) return false;
  if (/^LangGraph Node:/i.test(name)) return true;
  return kind.includes("agent") && canonical.includes("AGENT");
}

function childSummary(spans) {
  return spans.reduce((summary, span) => {
    const kind = graphKind(span);
    summary.total += 1;
    if (kind.includes("llm")) summary.llm += 1;
    else if (kind.includes("tool")) summary.tool += 1;
    else if (kind.includes("http")) summary.http += 1;
    else if (kind.includes("memory")) summary.memory += 1;
    if (graphStatusFailed(span)) {
      summary.failed += 1;
      summary.failedNames.push(cleanSpanName(span.name || span.id));
    }
    return summary;
  }, { total: 0, llm: 0, tool: 0, http: 0, memory: 0, failed: 0, failedNames: [] });
}

function closestWorkflowParentId(step, rawById, workflowIds) {
  let parentId = step.parentSpanId || step.parent_span_id;
  const seen = new Set();
  while (parentId && rawById.has(parentId) && !seen.has(parentId)) {
    if (workflowIds.has(parentId)) return parentId;
    seen.add(parentId);
    parentId = rawById.get(parentId)?.parentSpanId || rawById.get(parentId)?.parent_span_id;
  }
  return null;
}

function uniqueGraphEdges(edges) {
  const seen = new Set();
  return edges.filter((edge) => {
    if (!edge.source || !edge.target || edge.source === edge.target) return false;
    const key = `${edge.source}->${edge.target}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function rawTraceSteps(trace) {
  const timeline = trace?.replay?.timeline || [];
  const fallbackSpans = trace?.spansList || [];
  const source = fallbackSpans.length ? fallbackSpans : timeline;
  return source.map((step, index) => ({
    ...step,
    id: step.span_id || step.id || `span-${index}`,
    parentSpanId: step.parent_span_id || step.parentSpanId,
    name: cleanSpanName(step.name || step.span_name || step.summary || step.id || `Span ${index + 1}`),
    kind: inferredGraphKind(step),
    status: step.status || step.status_code,
    duration: Number(step.duration_ms || step.duration || 0),
    retryCount: Number(step.retry_count || step.retryCount || 0),
    modelName: step.model_name || step.modelName,
    toolName: step.tool_name || step.toolName,
    toolArguments: step.toolArguments ?? step.tool_input ?? step.raw?.tool_input,
    error: compactError(step.status_message || step.error_message || step.error),
  }));
}

function stableGraphValue(value) {
  if (Array.isArray(value)) return value.map(stableGraphValue);
  if (value && typeof value === "object") {
    return Object.keys(value).sort().reduce((result, key) => {
      result[key] = stableGraphValue(value[key]);
      return result;
    }, {});
  }
  return value;
}

function toolInvocationSignature(step) {
  if (!graphKind(step).includes("tool") || !step.toolName || step.toolArguments == null) return null;
  return `${step.toolName}::${JSON.stringify(stableGraphValue(step.toolArguments))}`;
}

function annotateRepeatedToolCalls(spans) {
  const counts = new Map();
  spans.forEach((span) => {
    const signature = toolInvocationSignature(span);
    if (signature) counts.set(signature, (counts.get(signature) || 0) + 1);
  });
  return spans.map((span) => {
    const signature = toolInvocationSignature(span);
    const repeatCount = signature ? counts.get(signature) || 0 : 0;
    return repeatCount >= 3 ? { ...span, loopRisk: true, invocationRepeatCount: repeatCount } : span;
  });
}

function inferredGraphKind(step) {
  const rawValue = String(step.kind || step.canonical_type || step.canonicalType || "").toLowerCase();
  const raw = ["n/a", "na", "none", "unknown"].includes(rawValue) ? "" : rawValue;
  if (raw) return raw;
  if (step.model_name || step.modelName) return "llm";
  if (step.tool_name || step.toolName) return "tool";
  return "span";
}

function childNodeLabel(step) {
  if (step.toolName || step.tool_name) return cleanSpanName(step.toolName || step.tool_name);
  return cleanSpanName(step.name || step.span_name || step.summary || step.id);
}

function sortedChildSpans(parent) {
  const childSpans = [...(parent?.childSpans || [])].sort((a, b) => {
    const sequenceA = Number(a.sequence_number || a.sequenceNumber || 0);
    const sequenceB = Number(b.sequence_number || b.sequenceNumber || 0);
    if (sequenceA || sequenceB) return sequenceA - sequenceB;
    return String(a.started_at || "").localeCompare(String(b.started_at || ""));
  });
  return childSpans;
}

function workflowLayoutProfile(workflowCount, rawCount, childCount) {
  const dense = rawCount > 22 || workflowCount > 5 || childCount > 18;
  const sparse = rawCount <= 10 || workflowCount <= 3;
  return {
    dense,
    sparse,
    startX: 96,
    mainY: sparse ? 106 : 88,
    mainGap: dense ? 210 : sparse ? 150 : 176,
    mainRowOffset: dense ? 18 : 28,
    inlineLimit: dense ? 3 : sparse ? 8 : 5,
    inlineColumns: dense ? 2 : sparse ? 4 : 3,
    childGapX: dense ? 72 : sparse ? 78 : 64,
    childGapY: dense ? 50 : sparse ? 58 : 54,
    childOffsetY: dense ? 82 : sparse ? 92 : 82,
    graphHeight: dense ? 360 : sparse ? 330 : 350,
    minWidth: dense ? 1120 : sparse ? 680 : 860,
  };
}

function addInlineChildTimeline(nodes, edges, nodeById, parent, profile, expandedMoreParentId) {
  const allChildSpans = sortedChildSpans(parent);
  const childSpans = allChildSpans.slice(0, expandedMoreParentId === parent.id ? allChildSpans.length : profile.inlineLimit);
  if (!parent || !childSpans.length) return;

  const childIdBySpanId = new Map();
  const columns = Math.min(profile.inlineColumns, Math.max(1, childSpans.length));
  const columnWidth = profile.childGapX;
  const firstX = parent.x - ((columns - 1) * columnWidth) / 2;

  childSpans.forEach((span, index) => {
    const row = Math.floor(index / columns);
    const rawColumn = index % columns;
    const column = row % 2 ? columns - 1 - rawColumn : rawColumn;
    const childNode = {
      ...span,
      id: `${parent.id}-child-${span.id}`,
      sourceSpanId: span.id,
      name: childNodeLabel(span),
      x: firstX + column * columnWidth,
      y: parent.y + profile.childOffsetY + row * profile.childGapY,
      r: graphNodeSize({ ...span, isChild: true }),
      color: graphStatusFailed(span) ? graphNodeColor(span) : span.loopRisk ? LOOP_COLOR : graphNodeColor(span),
      isChild: true,
      compactLabel: profile.dense,
      parentWorkflowId: parent.id,
      childIndex: index,
    };
    childIdBySpanId.set(span.id, childNode.id);
    nodes.push(childNode);
    nodeById.set(childNode.id, childNode);
  });

  childSpans.forEach((span, index) => {
    const target = childIdBySpanId.get(span.id);
    const previous = childSpans[index - 1];
    const source = previous ? childIdBySpanId.get(previous.id) : parent.id;
    if (source && target) {
      edges.push({ source, target, childEdge: true, sequentialChildEdge: true });
    }
  });

  const remainingCount = (parent.childSpans?.length || 0) - childSpans.length;
  if (remainingCount > 0) {
    const lastChild = childSpans[childSpans.length - 1];
    const lastId = childIdBySpanId.get(lastChild.id);
    const moreNode = {
      id: `${parent.id}-child-more`,
      name: `+${remainingCount} more`,
      kind: "span",
      status: parent.status,
      duration: 0,
      x: firstX + columns * columnWidth,
      y: parent.y + profile.childOffsetY + Math.floor((childSpans.length - 1) / columns) * profile.childGapY,
      r: 12,
      color: "#6f7b8f",
      isChild: true,
      isMoreNode: true,
      compactLabel: profile.dense,
      parentWorkflowId: parent.id,
      childIndex: childSpans.length,
    };
    nodes.push(moreNode);
    nodeById.set(moreNode.id, moreNode);
    if (lastId) edges.push({ source: lastId, target: moreNode.id, childEdge: true, sequentialChildEdge: true });
  }
}

function buildWorkflowExecutionGraph(trace, expandedMoreParentId = null) {
  const rawSteps = rawTraceSteps(trace);
  const rawById = new Map(rawSteps.map((step) => [step.id, step]));
  const graphRoot = rawSteps.find(isGraphRootStep);
  const workflowSteps = rawSteps.filter(isWorkflowStep);

  if (!workflowSteps.length) {
    return null;
  }

  const workflowIds = new Set(workflowSteps.map((step) => step.id));
  const childrenByWorkflowId = new Map(workflowSteps.map((step) => [step.id, []]));
  rawSteps.forEach((step) => {
    if (workflowIds.has(step.id)) return;
    const parentId = closestWorkflowParentId(step, rawById, workflowIds);
    if (parentId) childrenByWorkflowId.get(parentId)?.push(step);
  });

  const groups = new Map();
  workflowSteps.forEach((step, index) => {
    const name = normalizeWorkflowName(step.name);
    const group = groups.get(name) || { firstIndex: index, name, steps: [], children: [] };
    group.steps.push(step);
    group.children.push(...(childrenByWorkflowId.get(step.id) || []));
    groups.set(name, group);
  });

  groups.forEach((group) => {
    group.children = annotateRepeatedToolCalls(group.children);
  });

  const groupByWorkflowId = new Map();
  const steps = Array.from(groups.values())
    .sort((a, b) => a.firstIndex - b.firstIndex)
    .map((group) => {
      const first = group.steps[0];
      const repeatCount = group.steps.length;
      const summary = childSummary(group.children);
      const directFailure = group.steps.find(graphStatusFailed);
      const repeatedTools = [...new Map(group.children
        .filter((child) => child.loopRisk)
        .map((child) => [toolInvocationSignature(child), {
          name: child.toolName || child.name,
          count: child.invocationRepeatCount,
        }])).values()];
      const node = {
        ...first,
        id: `workflow-${first.id}`,
        sourceSpanId: first.id,
        name: group.name,
        kind: "agent",
        repeatCount,
        duration: group.steps.reduce((sum, step) => sum + Number(step.duration || 0), 0),
        retryCount: group.steps.reduce((sum, step) => sum + Number(step.retryCount || 0), 0),
        status: directFailure?.status || first.status,
        error: directFailure?.error || first.error,
        childSummary: summary,
        childSpans: group.children,
        failedChildNames: summary.failedNames,
        repeatedTools,
        nodeRepeatRisk: repeatCount > 1,
        loopRisk: repeatCount > 1 || repeatedTools.length > 0,
      };
      group.steps.forEach((step) => groupByWorkflowId.set(step.id, node.id));
      return node;
    });

  const byId = new Map(steps.map((step) => [step.id, step]));
  const loopNodes = steps.filter((step) => step.loopRisk).map((step) => step.name);
  const retryCount = rawSteps.reduce((sum, step) => sum + Number(step.retryCount || 0), 0);
  const failedCount = rawSteps.filter(graphStatusFailed).length;
  const slowestSpan = rawSteps.reduce((slowest, step) => step.duration > (slowest?.duration || 0) ? step : slowest, null);
  const rootNode = graphRoot ? {
    ...graphRoot,
    id: `workflow-root-${graphRoot.id}`,
    sourceSpanId: graphRoot.id,
    name: normalizeWorkflowName(graphRoot.name),
    kind: "agent",
    childSpans: [],
    childSummary: childSummary([]),
    isWorkflowRoot: true,
  } : null;
  const displaySteps = rootNode ? [rootNode, ...steps] : steps;
  const childCount = steps.reduce((sum, step) => sum + (step.childSpans?.length || 0), 0);
  const profile = workflowLayoutProfile(displaySteps.length, rawSteps.length, childCount);
  const width = Math.max(profile.minWidth, profile.startX * 2 + Math.max(displaySteps.length - 1, 0) * profile.mainGap + 220);

  const nodes = displaySteps.map((step, index) => {
    const rowOffset = index % 2 ? profile.mainRowOffset : 0;
    return {
      ...step,
      x: profile.startX + index * profile.mainGap,
      y: profile.mainY + rowOffset,
      r: graphNodeSize(step),
      color: graphStatusFailed(step) ? graphNodeColor(step) : step.nodeRepeatRisk ? LOOP_COLOR : graphNodeColor(step),
      loopRisk: step.loopRisk,
    };
  });
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const edges = uniqueGraphEdges([
    ...(rootNode && workflowSteps.length ? [{
      source: rootNode.id,
      target: groupByWorkflowId.get(workflowSteps[0].id),
    }] : []),
    ...workflowSteps.slice(1).map((step, index) => ({
      source: groupByWorkflowId.get(workflowSteps[index].id),
      target: groupByWorkflowId.get(step.id),
    })),
  ].filter((edge) => nodeById.has(edge.source) && nodeById.has(edge.target)));

  [...nodes].forEach((node) => addInlineChildTimeline(nodes, edges, nodeById, node, profile, expandedMoreParentId));

  return {
    mode: "workflow",
    nodes,
    edges,
    byId: nodeById,
    loopNodes,
    retryCount,
    failedCount,
    slowestSpan,
    width,
    height: profile.graphHeight,
    fallback: false,
  };
}

function buildSpanHierarchyGraph(trace) {
  const rawSteps = rawTraceSteps(trace).filter((step) => !graphKind(step).includes("reasoning"));
  const rawById = new Map(rawSteps.map((step) => [step.id, step]));
  const retryCount = rawSteps.reduce((sum, step) => sum + Number(step.retryCount || 0), 0);
  const failedCount = rawSteps.filter(graphStatusFailed).length;
  const slowestSpan = rawSteps.reduce((slowest, step) => step.duration > (slowest?.duration || 0) ? step : slowest, null);

  const groups = new Map();
  const hierarchyPath = (step) => {
    const path = [];
    let current = step;
    const seen = new Set();
    while (current && !seen.has(current.id)) {
      seen.add(current.id);
      path.unshift([
        graphKind(current) || "span",
        cleanSpanName(current.name),
        current.toolName || "",
        current.modelName || "",
      ].join(":"));
      current = current.parentSpanId ? rawById.get(current.parentSpanId) : null;
    }
    return path.join("/");
  };
  rawSteps.forEach((step, index) => {
    const signature = hierarchyPath(step);
    const group = groups.get(signature) || { key: signature, firstIndex: index, steps: [] };
    group.steps.push(step);
    groups.set(signature, group);
  });

  const collapsedSteps = Array.from(groups.values())
    .sort((a, b) => a.firstIndex - b.firstIndex)
    .map((group) => {
      const first = group.steps[0];
      const repeatCount = group.steps.length;
      const failed = group.steps.find(graphStatusFailed);
      return {
        ...first,
        id: `span-group-${group.firstIndex}`,
        repeatCount,
        duration: group.steps.reduce((sum, step) => sum + Number(step.duration || 0), 0),
        retryCount: group.steps.reduce((sum, step) => sum + Number(step.retryCount || 0), 0),
        status: failed?.status || first.status,
        error: failed?.error || first.error,
        loopRisk: repeatCount > 1,
        rawSpanIds: group.steps.map((step) => step.id),
      };
    });

  const nodeByRawId = new Map();
  collapsedSteps.forEach((node) => {
    node.rawSpanIds.forEach((rawId) => nodeByRawId.set(rawId, node.id));
  });

  const nodesByDepth = new Map();
  collapsedSteps.forEach((step) => {
    const depth = graphDepth(step, rawById);
    const depthNodes = nodesByDepth.get(depth) || [];
    depthNodes.push({ ...step, depth });
    nodesByDepth.set(depth, depthNodes);
  });

  const widestLevel = Math.max(...[...nodesByDepth.values()].map((items) => items.length), 1);
  const width = Math.max(920, widestLevel * 118 + 120);
  const levelGapY = 86;
  const nodeById = new Map();
  nodesByDepth.forEach((depthNodes, depth) => {
    const gapX = Math.min(132, Math.max(86, (width - 140) / Math.max(depthNodes.length, 1)));
    const startX = width / 2 - ((depthNodes.length - 1) * gapX) / 2;
    depthNodes.forEach((node, index) => {
      const positioned = {
        ...node,
        x: startX + index * gapX,
        y: 62 + depth * levelGapY,
        r: spanHierarchyNodeSize(node),
        color: graphStatusFailed(node) ? graphNodeColor(node) : node.repeatCount > 1 ? LOOP_COLOR : graphNodeColor(node),
        hideLabel: true,
      };
      nodeById.set(positioned.id, positioned);
    });
  });

  const positionedNodes = [...nodeById.values()];
  const graphEdges = trace?.graph?.edges || [];
  const rawEdges = graphEdges.length
    ? graphEdges.map((edge) => ({
        source: edge.parent_span_id || edge.source,
        target: edge.child_span_id || edge.target,
      }))
    : rawSteps
        .filter((step) => step.parentSpanId)
        .map((step) => ({ source: step.parentSpanId, target: step.id }));
  const edges = uniqueGraphEdges(rawEdges
    .map((edge) => ({
      source: nodeByRawId.get(edge.source),
      target: nodeByRawId.get(edge.target),
    }))
    .filter((edge) => edge.source && edge.target && edge.source !== edge.target));
  const loopNodes = positionedNodes.filter((node) => node.repeatCount > 1).map((node) => node.name);

  return {
    mode: "span",
    nodes: positionedNodes,
    edges,
    byId: nodeById,
    loopNodes,
    retryCount,
    failedCount,
    slowestSpan,
    width,
    height: 62 + (Math.max(...nodesByDepth.keys(), 0) + 1) * levelGapY + 60,
    fallback: false,
  };
}

export function buildTraceGraph(trace, mode = "workflow", expandedMoreParentId = null) {
  if (mode === "span") {
    return buildSpanHierarchyGraph(trace);
  }
  return buildWorkflowExecutionGraph(trace, expandedMoreParentId) || { ...buildSpanHierarchyGraph(trace), fallback: true };
}

function graphLabel(value, repeatCount = 1) {
  const text = cleanSpanName(value);
  const label = text.length > 22 ? `${text.slice(0, 19)}...` : text;
  return repeatCount > 1 ? `${label} *${repeatCount}` : label;
}

function focusedChildPosition(node, graph, focusedWorkflowId) {
  if (!focusedWorkflowId || node.parentWorkflowId !== focusedWorkflowId) {
    return { x: node.x, y: node.y };
  }

  const parent = graph.byId.get(focusedWorkflowId);
  if (!parent) return { x: node.x, y: node.y };

  const focusedChildren = graph.nodes
    .filter((item) => item.parentWorkflowId === focusedWorkflowId)
    .sort((a, b) => Number(a.childIndex || 0) - Number(b.childIndex || 0));
  const count = Math.max(focusedChildren.length, 1);
  const columns = Math.min(5, count);
  const gapX = 108;
  const gapY = 78;
  const index = Math.max(0, Number(node.childIndex || 0));
  const row = Math.floor(index / columns);
  const rawColumn = index % columns;
  const column = row % 2 ? columns - 1 - rawColumn : rawColumn;
  const maxStart = Math.max(48, (graph.width || 860) - 48 - (columns - 1) * gapX);
  const firstX = Math.min(Math.max(48, parent.x - ((columns - 1) * gapX) / 2), maxStart);

  return {
    x: firstX + column * gapX,
    y: parent.y + 122 + row * gapY,
  };
}

function buildGraphOption(graph, mode = "dark", focusedNodeId = null) {
  const isDark = mode === "dark";
  const focusedWorkflowId = focusedNodeId
    ? graph.byId.get(focusedNodeId)?.isChild
      ? graph.byId.get(focusedNodeId)?.parentWorkflowId
      : focusedNodeId
    : null;
  const graphNodes = [
    ...graph.nodes.map((node) => {
      const inFocus = !focusedWorkflowId || node.id === focusedWorkflowId || node.parentWorkflowId === focusedWorkflowId;
      const childFocused = focusedWorkflowId && node.parentWorkflowId === focusedWorkflowId;
      const opacity = inFocus ? 1 : 0.16;
      const position = focusedChildPosition(node, graph, focusedWorkflowId);
      return {
        id: node.id,
        name: graphLabel(node.name, node.repeatCount),
        value: [node.kind, node.duration],
        x: position.x,
        y: position.y,
        symbolSize: node.r * 2,
        itemStyle: {
          color: node.color,
          opacity,
          borderColor: isDark ? "rgba(6,16,24,.72)" : "rgba(255,255,255,.72)",
          borderWidth: 1.1,
          shadowBlur: inFocus ? childFocused ? 24 : node.compactLabel ? 10 : 16 : 0,
          shadowColor: `${node.color}${inFocus ? "66" : "18"}`,
        },
        label: {
          show: !node.isChild && !node.hideLabel,
          position: node.isChild ? "bottom" : "inside",
          color: isDark ? "#ffffff" : "#172234",
          fontSize: childFocused ? 11 : node.isChild ? 10 : 11,
          fontWeight: childFocused ? 700 : node.isChild ? 600 : 650,
          opacity,
          overflow: "truncate",
          width: childFocused ? 104 : node.isChild ? 82 : Math.max(54, node.r * 3.4),
          textShadowColor: isDark ? "rgba(0,0,0,.34)" : "rgba(255,255,255,.78)",
          textShadowBlur: 3,
        },
        emphasis: {
          scale: 1.18,
          focus: "none",
          label: {
            show: false,
          },
        },
        tooltip: {
          formatter: graphTooltip(node),
        },
      };
    }),
    {
      id: "__layout_origin",
      name: "",
      x: 0,
      y: 0,
      symbolSize: 0,
      silent: true,
      tooltip: { show: false },
      label: { show: false },
      itemStyle: { opacity: 0 },
    },
    {
      id: "__layout_bounds",
      name: "",
      x: graph.width || 860,
      y: graph.height || 350,
      symbolSize: 0,
      silent: true,
      tooltip: { show: false },
      label: { show: false },
      itemStyle: { opacity: 0 },
    },
  ];
  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      confine: true,
      backgroundColor: isDark ? "rgba(13, 20, 30, 0.96)" : "rgba(255, 255, 255, 0.97)",
      borderColor: isDark ? "rgba(151, 172, 203, 0.22)" : "rgba(67, 86, 112, 0.18)",
      borderWidth: 1,
      padding: [9, 11],
      textStyle: {
        color: isDark ? "#e9f2ff" : "#172234",
        fontFamily: "Inter, Segoe UI, Arial, sans-serif",
        fontSize: 12,
        fontWeight: 500,
      },
      appendToBody: true,
      extraCssText: isDark
        ? "box-shadow:0 14px 38px rgba(0,0,0,.34);border-radius:8px;backdrop-filter:blur(10px);min-width:0;max-width:min(420px, calc(100vw - 48px));white-space:normal;overflow-wrap:anywhere;word-break:break-word;"
        : "box-shadow:0 14px 34px rgba(34,50,74,.16);border-radius:8px;backdrop-filter:blur(10px);min-width:0;max-width:min(420px, calc(100vw - 48px));white-space:normal;overflow-wrap:anywhere;word-break:break-word;",
    },
    animationDuration: 500,
    series: [
      {
        type: "graph",
        layout: "none",
        roam: true,
        draggable: true,
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: [0, 8],
        cursor: "move",
        data: graphNodes,
        links: graph.edges.map((edge) => {
          const target = graph.byId.get(edge.target);
          const risk = target?.nodeRepeatRisk || target?.retryCount || (edge.childEdge && target?.loopRisk);
          const failed = target ? graphStatusFailed(target) : false;
          const edgeFocused = !focusedWorkflowId
            || edge.source === focusedWorkflowId
            || edge.target === focusedWorkflowId
            || target?.parentWorkflowId === focusedWorkflowId
            || graph.byId.get(edge.source)?.parentWorkflowId === focusedWorkflowId;
          const focusedChildEdge = focusedWorkflowId
            && edge.childEdge
            && (target?.parentWorkflowId === focusedWorkflowId || graph.byId.get(edge.source)?.parentWorkflowId === focusedWorkflowId);
          return {
            source: edge.source,
            target: edge.target,
            lineStyle: {
              color: failed
                ? "#ff6270"
                : risk ? LOOP_COLOR
                : edge.childEdge
                  ? isDark ? "rgba(133, 179, 232, 0.56)" : "rgba(60, 111, 172, 0.46)"
                  : isDark ? "rgba(91, 101, 118, 0.72)" : "rgba(87, 104, 128, 0.58)",
              opacity: focusedChildEdge ? 1 : edgeFocused ? 0.95 : 0.08,
              width: focusedChildEdge ? 2.35 : edgeFocused ? failed || risk ? 2.5 : edge.childEdge ? 1.7 : 1.55 : 1,
              type: edge.childEdge ? "dashed" : "solid",
              curveness: edge.childEdge ? 0.08 : 0.08,
            },
          };
        }),
        lineStyle: {
          opacity: 0.9,
        },
        emphasis: {
          focus: "none",
          lineStyle: {
            opacity: 0.95,
          },
        },
        blur: {
          itemStyle: {
            opacity: 1,
          },
          lineStyle: {
            opacity: 0.9,
          },
        },
      },
    ],
  };
}

export function WorkflowGraph({ trace, mode = "workflow", onNodeSelect }) {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";
  const [focusedNodeId, setFocusedNodeId] = useState(null);
  const [armedNodeId, setArmedNodeId] = useState(null);
  const [expandedMoreParentId, setExpandedMoreParentId] = useState(null);
  const graph = buildTraceGraph(trace, mode, mode === "workflow" ? expandedMoreParentId : null);
  const option = useMemo(() => buildGraphOption(graph, theme.palette.mode, focusedNodeId), [focusedNodeId, graph, theme.palette.mode]);
  const height = 420;

  useEffect(() => {
    setFocusedNodeId(null);
    setArmedNodeId(null);
    setExpandedMoreParentId(null);
  }, [mode, trace?.id]);

  const onEvents = useMemo(() => ({
    click: (params) => {
      if (params?.dataType !== "node") return;
      const node = graph.byId.get(params?.data?.id);
      if (!node || params?.data?.silent) return;
      const workflowId = node.isChild ? node.parentWorkflowId : node.id;
      if (node.isMoreNode) {
        setExpandedMoreParentId(workflowId);
        setFocusedNodeId(workflowId);
        setArmedNodeId(null);
        return;
      }
      if (mode === "workflow" && !node.isChild) {
        setExpandedMoreParentId(null);
      }

      if (armedNodeId === node.id) {
        const rawSpanId = node.sourceSpanId || node.span_id || node.raw?.span_id || node.rawSpanIds?.[0] || node.id;
        onNodeSelect?.({ node, spanId: rawSpanId });
        return;
      }

      setFocusedNodeId(workflowId);
      setArmedNodeId(node.id);
    },
  }), [armedNodeId, graph.byId, mode, onNodeSelect]);

  if (!graph.nodes.length) {
    return (
      <Box sx={{ minHeight: 320, border: "1px solid", borderColor: "divider", borderRadius: 1, bgcolor: "background.default", display: "grid", placeItems: "center" }}>
        <Typography color="text.secondary">No graph data. Trace graph appears when replay spans include IDs and timing metadata.</Typography>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        height,
        border: "1px solid",
        borderColor: isDark ? "rgba(151, 172, 203, 0.15)" : "rgba(75, 95, 125, 0.18)",
        borderRadius: 1,
        bgcolor: isDark ? "#07090d" : "rgba(248, 251, 255, 0.96)",
        overflow: "hidden",
        backgroundImage: isDark
          ? `
            linear-gradient(rgba(151, 172, 203, 0.045) 1px, transparent 1px),
            linear-gradient(90deg, rgba(151, 172, 203, 0.045) 1px, transparent 1px),
            linear-gradient(rgba(151, 172, 203, 0.022) 1px, transparent 1px),
            linear-gradient(90deg, rgba(151, 172, 203, 0.022) 1px, transparent 1px)
          `
          : `
            linear-gradient(rgba(75, 95, 125, 0.10) 1px, transparent 1px),
            linear-gradient(90deg, rgba(75, 95, 125, 0.10) 1px, transparent 1px),
            linear-gradient(rgba(75, 95, 125, 0.055) 1px, transparent 1px),
            linear-gradient(90deg, rgba(75, 95, 125, 0.055) 1px, transparent 1px)
          `,
        backgroundSize: "42px 42px, 42px 42px, 14px 14px, 14px 14px",
        boxShadow: isDark ? "inset 0 1px 0 rgba(255,255,255,.03)" : "inset 0 1px 0 rgba(255,255,255,.9)",
      }}
    >
      <ReactECharts
        option={option}
        notMerge
        lazyUpdate
        onEvents={onEvents}
        onChartReady={(chart) => {
          if (chart.__agentsreBackgroundClick) {
            chart.getZr().off("click", chart.__agentsreBackgroundClick);
          }
          chart.__agentsreBackgroundClick = (event) => {
            if (!event.target) {
              setFocusedNodeId(null);
              setArmedNodeId(null);
              setExpandedMoreParentId(null);
            }
          };
          chart.getZr().on("click", chart.__agentsreBackgroundClick);
        }}
        style={{ height: "100%", width: "100%" }}
        opts={{ renderer: "canvas" }}
      />
    </Box>
  );
}
