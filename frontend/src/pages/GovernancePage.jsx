import { useMemo, useState } from "react";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import CloseIcon from "@mui/icons-material/Close";
import ClearIcon from "@mui/icons-material/Clear";
import MetricCard from "../components/MetricCard";
import PageHeader from "../components/PageHeader";
import StatusPill from "../components/StatusPill";
import DataTable from "../components/DataTable";
import { compactStructuredErrors } from "../utils/errorFormat";

const emptySummary = { audit_events: 0, redactions: 0, warnings: 0, replay_events: 0 };
const tableTabs = [
  { id: "warnings", label: "Warnings", metric: "warnings" },
  { id: "privacy", label: "Redaction Evidence", metric: "redactions" },
  { id: "audit", label: "Audit Trails", metric: "audit_events" }
];

function formatDate(value) {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function metadataPretty(value) {
  if (!value) return "N/A";
  if (typeof value === "string") {
    try {
      return JSON.stringify(compactStructuredErrors(JSON.parse(value)), null, 2);
    } catch {
      return compactStructuredErrors(value);
    }
  }
  return JSON.stringify(compactStructuredErrors(value), null, 2);
}

function targetText(row) {
  const target = String(row.target || "").trim();
  if (target && target.toUpperCase() !== "N/A") return target;
  if (row.action === "execution.captured" && row.execution_id) return row.execution_id;
  return String(row.action || "captured").replaceAll(".", " ");
}

function hasRedactionEvidence(row) {
  const maskedFields = Number(row.maskedFields || row.masked_fields_count || 0);
  return maskedFields > 0;
}

function filterByDateRange(rows, fromValue, toValue) {
  const from = fromValue ? new Date(fromValue).getTime() : null;
  const to = toValue ? new Date(toValue).getTime() + (toValue.length === 16 ? 59_999 : 0) : null;
  return rows.filter((row) => {
    const timestamp = new Date(row.created_at || row.started_at || row.ended_at || "").getTime();
    if (!Number.isFinite(timestamp)) return !from && !to;
    if (from && timestamp < from) return false;
    if (to && timestamp > to) return false;
    return true;
  });
}

function ClampText({ value, lines = 2 }) {
  const text = String(value || "N/A");
  return (
    <Tooltip title={text} arrow placement="top-start">
      <Box
        component="span"
        sx={{
          display: "-webkit-box",
          WebkitLineClamp: lines,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          overflowWrap: "anywhere",
          lineHeight: 1.35,
          maxWidth: "100%"
        }}
      >
        {text}
      </Box>
    </Tooltip>
  );
}

function MetadataPreview({ value }) {
  return <ClampText value={metadataPretty(value)} lines={2} />;
}

function Section({ title, subtitle, children }) {
  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent sx={{ p: 1.75, "&:last-child": { pb: 1.75 } }}>
        <Stack spacing={1.25}>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 680 }}>{title}</Typography>
            {subtitle ? (
              <Typography variant="caption" color="text.secondary">{subtitle}</Typography>
            ) : null}
          </Box>
          {children}
        </Stack>
      </CardContent>
    </Card>
  );
}

function DetailField({ label, value }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, textTransform: "uppercase" }}>
        {label}
      </Typography>
      <Typography sx={{ mt: 0.35, overflowWrap: "anywhere" }}>{value || "N/A"}</Typography>
    </Box>
  );
}

export default function GovernancePage({ governance, loading }) {
  const [activeTable, setActiveTable] = useState("warnings");
  const [selectedAudit, setSelectedAudit] = useState(null);
  const [fromDateTime, setFromDateTime] = useState("");
  const [toDateTime, setToDateTime] = useState("");
  const summary = governance?.summary || emptySummary;
  const warnings = governance?.warnings || [];
  const privacyEvidence = (governance?.privacy || []).filter(hasRedactionEvidence);
  const auditRecords = governance?.audit_actions || [];
  const dateFilterActive = Boolean(fromDateTime || toDateTime);
  const rangeInvalid = Boolean(fromDateTime && toDateTime && new Date(fromDateTime) > new Date(toDateTime));
  const filteredWarnings = useMemo(
    () => rangeInvalid ? [] : filterByDateRange(warnings, fromDateTime, toDateTime),
    [fromDateTime, rangeInvalid, toDateTime, warnings],
  );
  const filteredPrivacyEvidence = useMemo(
    () => rangeInvalid ? [] : filterByDateRange(privacyEvidence, fromDateTime, toDateTime),
    [fromDateTime, privacyEvidence, rangeInvalid, toDateTime],
  );
  const filteredAuditRecords = useMemo(
    () => rangeInvalid ? [] : filterByDateRange(auditRecords, fromDateTime, toDateTime),
    [auditRecords, fromDateTime, rangeInvalid, toDateTime],
  );
  const redactionEvidenceCount = filteredPrivacyEvidence.reduce((sum, row) => sum + Number(row.maskedFields || row.masked_fields_count || 0), 0);
  const displaySummary = {
    ...summary,
    warnings: filteredWarnings.length,
    redactions: redactionEvidenceCount,
    audit_events: filteredAuditRecords.length,
  };
  const hasData = Boolean((governance?.executions || []).length || warnings.length || privacyEvidence.length || auditRecords.length);
  const filteredDataExists = Boolean(filteredWarnings.length || filteredPrivacyEvidence.length || filteredAuditRecords.length);
  const rangeEmptyMessage = rangeInvalid
    ? "The start date and time must be before the end date and time."
    : dateFilterActive && !filteredDataExists
      ? "No governance evidence exists in the selected date and time range."
      : null;
  const tableConfig = {
    warnings: {
      title: "Warnings",
      subtitle: "Policy, schema, privacy, and capture warnings raised from governance evidence.",
      rows: filteredWarnings,
      emptyMessage: rangeEmptyMessage || (hasData ? "No governance warnings for the selected project." : "No governance evidence yet."),
      getKey: (row) => row.id,
      columns: [
        { id: "severity", label: "Severity", width: "12%", render: (row) => <StatusPill value={row.severity} /> },
        { id: "source", label: "Source", width: "15%", render: (row) => <ClampText value={row.source} /> },
        { id: "message", label: "Warning", width: "42%", render: (row) => <ClampText value={row.message} /> },
        { id: "agent_id", label: "Agent", width: "14%", render: (row) => <ClampText value={row.agent_id} /> },
        { id: "created_at", label: "Captured", width: "17%", render: (row) => formatDate(row.created_at) }
      ]
    },
    privacy: {
      title: "Privacy And Redaction Evidence",
      subtitle: "Captured redaction status, masked fields, and policy applied to each agent execution.",
      rows: filteredPrivacyEvidence,
      emptyMessage: rangeEmptyMessage || "No privacy or redaction evidence yet.",
      getKey: (row) => row.execution_id || row.field,
      columns: [
        { id: "agent_id", label: "Agent", width: "17%", render: (row) => <ClampText value={row.agent_id} /> },
        { id: "redactionApplied", label: "Redaction applied", width: "17%", render: (row) => <StatusPill value={row.redactionApplied ? "captured" : "none"} /> },
        { id: "redactedFields", label: "Redacted fields", width: "27%", render: (row) => <ClampText value={row.redactedFields} /> },
        { id: "types", label: "Redaction types", width: "17%", render: (row) => <ClampText value={row.types} /> },
        { id: "policy", label: "Capture policy", width: "14%" },
        { id: "maskedFields", label: "Masked", width: "8%" }
      ]
    },
    audit: {
      title: "Audit Trails",
      subtitle: "Immutable execution, replay, LLM, tool, and span capture actions for review.",
      rows: filteredAuditRecords,
      emptyMessage: rangeEmptyMessage || "No audit actions yet.",
      getKey: (row) => row.id,
      scrollX: true,
      minWidth: 1480,
      columns: [
        { id: "created_at", label: "Time", width: "14%", render: (row) => formatDate(row.created_at) },
        { id: "action", label: "Action", width: "15%", render: (row) => <ClampText value={row.action} /> },
        { id: "agent_id", label: "Agent", width: "13%", render: (row) => <ClampText value={row.agent_id} /> },
        { id: "target", label: "Target", width: "16%", render: (row) => <ClampText value={targetText(row)} /> },
        { id: "metadata", label: "Metadata", width: "42%", render: (row) => <MetadataPreview value={row.metadata} /> }
      ]
    }
  };
  const selectedTable = tableConfig[activeTable];
  const closeAuditDetail = () => setSelectedAudit(null);

  return (
    <>
      <PageHeader title="Governance" />
      <Grid container spacing={1.75} sx={{ mb: 2 }}>
        <Grid item xs={6} md={4}><MetricCard label="Warnings" value={loading ? "..." : displaySummary.warnings} /></Grid>
        <Grid item xs={6} md={4}><MetricCard label="Redactions" value={loading ? "..." : displaySummary.redactions} /></Grid>
        <Grid item xs={6} md={4}><MetricCard label="Audit trails" value={loading ? "..." : displaySummary.audit_events} /></Grid>
      </Grid>

      <Section
        title={selectedTable.title}
        subtitle={selectedTable.subtitle}
      >
        <Stack
          direction={{ xs: "column", lg: "row" }}
          spacing={1}
          justifyContent="space-between"
          alignItems={{ xs: "stretch", lg: "center" }}
          sx={{ mb: 0.25 }}
        >
          <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
            {tableTabs.map((tab) => {
            const active = activeTable === tab.id;
            return (
              <Box
                key={tab.id}
                component="button"
                type="button"
                onClick={() => setActiveTable(tab.id)}
                sx={{
                  minHeight: 34,
                  border: "1px solid",
                  borderColor: active ? "primary.main" : "rgba(151, 172, 203, 0.16)",
                  borderRadius: 999,
                  px: 1.3,
                  py: 0.55,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.75,
                  color: "text.primary",
                  bgcolor: (theme) => {
                    if (active) return "rgba(65, 166, 255, 0.12)";
                    return theme.palette.mode === "dark" ? "rgba(17, 24, 33, 0.62)" : "rgba(255, 255, 255, 0.72)";
                  },
                  boxShadow: active ? "inset 0 1px 0 rgba(255,255,255,.05)" : "none",
                  cursor: "pointer",
                  font: "inherit"
                }}
              >
                <Typography variant="caption" color={active ? "primary.main" : "text.secondary"} sx={{ textTransform: "uppercase", fontWeight: 680, lineHeight: 1 }}>
                  {tab.label}
                </Typography>
                <Typography
                  component="span"
                  sx={{
                    minWidth: 24,
                    height: 22,
                    px: 0.7,
                    borderRadius: 999,
                    display: "inline-grid",
                    placeItems: "center",
                    fontSize: 12,
                    fontWeight: 720,
                    color: "text.primary",
                    bgcolor: active ? "rgba(65, 166, 255, 0.18)" : "rgba(151, 172, 203, 0.1)"
                  }}
                >
                  {loading ? "..." : displaySummary[tab.metric] || 0}
                </Typography>
              </Box>
            );
            })}
          </Stack>
          <Stack direction="row" spacing={0.75} alignItems="flex-start" useFlexGap flexWrap={{ xs: "wrap", sm: "nowrap" }}>
            <TextField
              label="From"
              type="datetime-local"
              size="small"
              value={fromDateTime}
              onChange={(event) => setFromDateTime(event.target.value)}
              InputLabelProps={{ shrink: true }}
              sx={{
                width: { xs: "100%", sm: 205 },
                "& input": { colorScheme: (theme) => theme.palette.mode },
                "& input::-webkit-calendar-picker-indicator": { cursor: "pointer", opacity: 0.82 },
              }}
            />
            <TextField
              label="To"
              type="datetime-local"
              size="small"
              value={toDateTime}
              onChange={(event) => setToDateTime(event.target.value)}
              error={rangeInvalid}
              InputLabelProps={{ shrink: true }}
              sx={{
                width: { xs: "calc(100% - 42px)", sm: 205 },
                "& input": { colorScheme: (theme) => theme.palette.mode },
                "& input::-webkit-calendar-picker-indicator": { cursor: "pointer", opacity: 0.82 },
              }}
            />
            <Tooltip title="Clear date and time filter">
              <span>
                <IconButton
                  aria-label="Clear date and time filter"
                  disabled={!dateFilterActive}
                  onClick={() => {
                    setFromDateTime("");
                    setToDateTime("");
                  }}
                  sx={{ width: 40, height: 40, border: "1px solid", borderColor: "divider", borderRadius: 1 }}
                >
                  <ClearIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
        </Stack>
        <DataTable
          rows={selectedTable.rows}
          getKey={selectedTable.getKey}
          onRowClick={activeTable === "audit" ? setSelectedAudit : undefined}
          emptyMessage={selectedTable.emptyMessage}
          scrollX={selectedTable.scrollX}
          minWidth={selectedTable.minWidth || "100%"}
          columns={selectedTable.columns}
        />
      </Section>
      <Dialog open={Boolean(selectedAudit)} onClose={closeAuditDetail} maxWidth="md" fullWidth>
        <DialogTitle sx={{ pr: 6 }}>
          Audit trail detail
          <IconButton
            aria-label="Close audit detail"
            onClick={closeAuditDetail}
            sx={{ position: "absolute", right: 12, top: 10 }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          {selectedAudit ? (
            <Stack spacing={2}>
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
                  gap: 1.5
                }}
              >
                <DetailField label="Action" value={selectedAudit.action} />
                <DetailField label="Target" value={targetText(selectedAudit)} />
                <DetailField label="Agent" value={selectedAudit.agent_id} />
                <DetailField label="Execution" value={selectedAudit.execution_id} />
                <DetailField label="Project" value={selectedAudit.project_id} />
                <DetailField label="Captured" value={formatDate(selectedAudit.created_at)} />
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, textTransform: "uppercase" }}>
                  Metadata
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    mt: 0.75,
                    p: 1.25,
                    maxHeight: 320,
                    overflow: "auto",
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                    bgcolor: "background.default",
                    color: "text.primary",
                    fontFamily: "Consolas, 'SFMono-Regular', monospace",
                    fontSize: 12,
                    lineHeight: 1.55,
                    whiteSpace: "pre-wrap",
                    overflowWrap: "anywhere"
                  }}
                >
                  {metadataPretty(selectedAudit.metadata)}
                </Box>
              </Box>
            </Stack>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
