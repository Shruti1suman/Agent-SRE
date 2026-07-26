function text(value, fallback = "N/A") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

function titleCase(value) {
  return text(value, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase()) || "Incident";
}

function normalizeSeverity(value) {
  const severity = text(value, "warning").toLowerCase();
  if (severity === "critical") return "critical";
  if (severity === "high") return "high";
  if (severity === "medium") return "medium";
  if (severity === "low") return "low";
  if (severity === "warning") return "warning";
  return severity;
}

export function mapIncident(row) {
  const rule = text(row.rule_id || row.ruleId || row.category || row.metric_name, "rule");
  const incident = text(row.rca_text || row.incident || row.category, titleCase(row.category));
  return {
    id: row.incident_id || `${row.trace_id || "trace"}-${rule}`,
    incidentId: row.incident_id || `${row.trace_id || "trace"}-${rule}`,
    severity: normalizeSeverity(row.severity),
    status: row.status || "open",
    rule,
    type: titleCase(row.category || row.triggered_by || "Reliability incident"),
    incident,
    agent: text(row.agent_id || row.agent),
    trace: text(row.trace_id || row.trace),
    projectId: row.project_id,
    recommendation: text(row.suggestion_text || row.recommendation, "Inspect the trace replay and related metrics."),
    evidence: [
      row.metric_name ? `${row.metric_name}: ${row.observed_value ?? "observed"}` : null,
      row.z_score !== undefined && row.z_score !== null ? `z-score ${Number(row.z_score).toFixed(2)}` : null,
      row.threshold_value !== undefined && row.threshold_value !== null ? `threshold ${row.threshold_value}` : null,
    ].filter(Boolean).join(" / ") || incident,
    remediation: text(row.suggestion_text || row.recommendation, "Inspect the trace replay and related metrics."),
    triggeredAt: row.created_at || row.triggeredAt || "N/A",
    raw: row,
  };
}

export function mapIncidents(rows = []) {
  return rows.filter((row) => !row.error).map(mapIncident);
}
