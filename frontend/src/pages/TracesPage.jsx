import Button from "@mui/material/Button";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import PageHeader from "../components/PageHeader";
import MetricCard from "../components/MetricCard";
import DataTable from "../components/DataTable";
import StatusPill from "../components/StatusPill";

const fmtMs = (value) => (value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value}ms`);

function TraceTimestamp({ value }) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "N/A";
  return (
    <Box>
      <Typography sx={{ fontSize: 13.5, lineHeight: 1.25 }}>
        {date.toLocaleDateString()}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.2 }}>
        {date.toLocaleTimeString()}
      </Typography>
    </Box>
  );
}

export default function TracesPage({ rows = [], overview = null, loading, openTrace, setSelectedTrace, setPage }) {
  const traces = rows || [];
  const overviewNumber = (key, fallback) => {
    const value = Number(overview?.[key]);
    return Number.isFinite(value) ? value : fallback;
  };
  const traceCount = overviewNumber("traces", traces.length);
  const llmCalls = overviewNumber("llm_calls", traces.reduce((sum, row) => sum + Number(row.llm || 0), 0));
  const toolCalls = overviewNumber("tool_calls", traces.reduce((sum, row) => sum + Number(row.tools || 0), 0));
  const failed = overviewNumber("failed", traces.filter((row) => row.status === "failed" || row.status === "error").length);

  const openExplorer = (trace) => {
    setSelectedTrace(trace);
    setPage("explorer");
  };

  return (
    <>
      <PageHeader title="Traces" action={<Button variant="outlined" onClick={() => setPage("explorer")}>Trace explorer</Button>} />
      <Grid container spacing={1.75} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><MetricCard label="Total traces" value={loading ? "..." : traceCount} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="LLM calls" value={loading ? "..." : llmCalls} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Tool calls" value={loading ? "..." : toolCalls} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Failed" value={loading ? "..." : failed} /></Grid>
      </Grid>
      <DataTable
        rows={traces}
        getKey={(row) => row.id}
        onRowClick={openTrace}
        emptyMessage="No traces yet. Run an agent with this project's SDK key."
        columns={[
          { id: "status", label: "Status", render: (row) => <StatusPill value={row.status} /> },
          { id: "displayName", label: "Trace", render: (row) => row.displayName || row.root || row.traceId || row.id },
          { id: "timestamp", label: "Timestamp", render: (row) => <TraceTimestamp value={row.timestamp} /> },
          { id: "framework", label: "Framework" },
          { id: "duration", label: "Duration", render: (row) => fmtMs(row.duration) },
          { id: "spans", label: "Spans" },
          { id: "llm", label: "LLM" },
          { id: "tools", label: "Tools" },
          { id: "action", label: "Action", render: (row) => <Button size="small" variant="outlined" onClick={(event) => { event.stopPropagation(); openExplorer(row); }}>View</Button> }
        ]}
      />
    </>
  );
}
