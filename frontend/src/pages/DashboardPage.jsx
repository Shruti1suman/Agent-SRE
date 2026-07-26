import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import MetricCard from "../components/MetricCard";
import { HorizontalBarChart, SimpleLineChart, VerticalBarChart } from "../components/Charts";
import DataTable from "../components/DataTable";
import PageHeader from "../components/PageHeader";
import { emptyDashboardData } from "../mappers/dashboardMappers";

const fmtMs = (value) => (value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value}ms`);
const fmtCost = (value) => {
  const amount = Number(value) || 0;
  if (amount === 0) return "$0";
  if (amount < 0.001) return `$${amount.toFixed(5)}`;
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  return `$${amount.toFixed(2)}`;
};
const fmtTokens = (value) => {
  const tokens = Math.round(Number(value) || 0);
  return tokens >= 1000 ? `${Math.round(tokens / 1000)}k` : tokens.toLocaleString();
};
const fmtTimestamp = (value) => {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "N/A";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
};

const panelSx = {
  p: { xs: 1.4, md: 1.7 },
  width: "100%",
  height: "100%",
  display: "flex",
  flexDirection: "column",
  bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(17, 24, 33, 0.86)" : "rgba(255, 255, 255, 0.9)",
  borderColor: "rgba(151, 172, 203, 0.15)",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,.03)"
};

function PanelTitle({ title, subtitle }) {
  return (
    <Box sx={{ mb: 1.1 }}>
      <Typography variant="h6" sx={{ fontWeight: 760 }}>{title}</Typography>
      {subtitle ? <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>{subtitle}</Typography> : null}
    </Box>
  );
}

function scoreTone(score) {
  if (score >= 90) return "success";
  if (score >= 70) return "warning";
  return "error";
}

function HealthScorePanel({ healthScore, loading }) {
  const data = healthScore || emptyDashboardData.healthScore;
  const displayScore = loading ? "..." : `${data.score}%`;
  return (
    <Card variant="outlined" sx={{ ...panelSx, p: { xs: 1.35, md: 1.65 } }}>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "150px minmax(0, 1fr)" },
          gap: { xs: 1.4, md: 2 },
          alignItems: "center",
        }}
      >
        <Stack alignItems={{ xs: "flex-start", md: "center" }} spacing={1}>
          <Box
            sx={{
              width: 118,
              height: 118,
              borderRadius: "50%",
              display: "grid",
              placeItems: "center",
              background: (theme) => {
                const color = theme.palette[data.statusTone]?.main || theme.palette.primary.main;
                const track = theme.palette.mode === "dark" ? "rgba(91, 108, 131, 0.24)" : "rgba(126, 146, 174, 0.22)";
                return `conic-gradient(${color} ${Math.max(0, Math.min(100, data.score)) * 3.6}deg, ${track} 0deg)`;
              },
              boxShadow: (theme) => {
                const color = theme.palette[data.statusTone]?.main || theme.palette.primary.main;
                return `0 0 34px ${color}30`;
              },
            }}
          >
            <Box
              sx={{
                width: 88,
                height: 88,
                borderRadius: "50%",
                display: "grid",
                placeItems: "center",
                bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(9, 14, 21, 0.96)" : "rgba(255, 255, 255, 0.96)",
                border: "1px solid",
                borderColor: "divider",
              }}
            >
              <Stack spacing={0.2} alignItems="center">
                <Typography sx={{ fontSize: 27, lineHeight: 1, fontWeight: 700 }}>{displayScore}</Typography>
                <Typography
                  variant="caption"
                  sx={{
                    color: (theme) => theme.palette[data.statusTone]?.main || theme.palette.primary.main,
                    fontWeight: 700,
                    textTransform: "uppercase",
                  }}
                >
                  {loading ? "Loading" : data.status}
                </Typography>
              </Stack>
            </Box>
          </Box>
        </Stack>

        <Stack spacing={1.2} sx={{ minWidth: 0 }}>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 720 }}>Agent health score</Typography>
            <Typography variant="body2" color="text.secondary">
              Weighted health from success rate, latency SLO compliance, loop risk, and governance warnings.
            </Typography>
          </Box>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, minmax(0, 1fr))" }, gap: 1 }}>
            {data.components.map((item) => {
              const tone = scoreTone(item.score);
              return (
                <Box
                  key={item.id}
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1.2,
                    p: 1.1,
                    bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(8, 13, 20, 0.42)" : "rgba(244, 248, 252, 0.66)",
                    minWidth: 0,
                  }}
                >
                  <Stack spacing={0.8}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                      {item.label}
                    </Typography>
                    <Typography sx={{ fontSize: 20, lineHeight: 1, fontWeight: 700 }}>{loading ? "..." : `${item.score}%`}</Typography>
                    <Box sx={{ height: 6, borderRadius: 999, bgcolor: "action.hover", overflow: "hidden" }}>
                      <Box
                        sx={{
                          height: "100%",
                          width: `${loading ? 0 : item.score}%`,
                          borderRadius: 999,
                          bgcolor: (theme) => theme.palette[tone]?.main || theme.palette.primary.main,
                          transition: "width 600ms ease",
                        }}
                      />
                    </Box>
                    <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.35 }}>
                      {item.detail}
                    </Typography>
                  </Stack>
                </Box>
              );
            })}
          </Box>
        </Stack>
      </Box>
    </Card>
  );
}

export default function DashboardPage({ openTrace, dashboardData, loading, selectedProject, setPage }) {
  const data = dashboardData || emptyDashboardData;
  const summary = data.summary;
  const noProject = !data.hasProject;
  const noData = data.hasProject && !data.hasData;

  return (
    <Stack spacing={1.55}>
      <PageHeader title="Dashboard" />
      {noProject ? (
        <Alert severity="info" action={<Typography component="button" onClick={() => setPage("create")} style={{ background: "transparent", border: 0, color: "inherit", cursor: "pointer", fontWeight: 700 }}>Create project</Typography>}>
          Create a project and generate an SDK key to start collecting telemetry.
        </Alert>
      ) : null}
      {noData ? (
        <Alert severity="info">
          No executions yet for {selectedProject?.project_name || "this project"}. Run an agent with this project's AgentSRE SDK key to populate the dashboard.
        </Alert>
      ) : null}

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, minmax(0, 1fr))", md: "repeat(4, minmax(0, 1fr))" }, gap: 1.35 }}>
        <MetricCard label="Executions" value={loading ? "..." : summary.executions} />
        <MetricCard label="Success rate" value={loading ? "..." : summary.successRate} />
        <MetricCard label="Total cost" value={loading ? "..." : summary.totalCost} />
        <MetricCard label="P90 latency" value={loading ? "..." : summary.p90Latency} />
      </Box>

      <HealthScorePanel healthScore={data.healthScore} loading={loading} />

      <Card variant="outlined" sx={{ ...panelSx, minHeight: 230, p: { xs: 1.05, md: 1.25 } }}>
        <PanelTitle title="Latency by trace" />
        <SimpleLineChart data={data.latencyByTrace} height={190} compact />
      </Card>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 1.35 }}>
        <Box sx={{ display: "flex", minWidth: 0 }}>
          <Card variant="outlined" sx={panelSx}>
            <PanelTitle title="Top spans" />
            <HorizontalBarChart rows={data.topSpans} format={(value) => `${Math.round(value)}ms`} height={232} showYAxisLabels={false} />
          </Card>
        </Box>
        <Box sx={{ display: "flex", minWidth: 0 }}>
          <Card variant="outlined" sx={panelSx}>
            <PanelTitle title="Cost by execution" subtitle={`Total ${summary.totalCost}`} />
            <VerticalBarChart rows={data.costByExecution} format={fmtCost} height={232} scrollable />
          </Card>
        </Box>
      </Box>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 1.35 }}>
        <Box sx={{ display: "flex", minWidth: 0 }}>
          <Card variant="outlined" sx={panelSx}>
            <PanelTitle title="Latency by model" />
            <HorizontalBarChart rows={data.latencyByModel} format={(value) => `${Math.round(value)}ms`} height={232} showYAxisLabels={false} />
          </Card>
        </Box>
        <Box sx={{ display: "flex", minWidth: 0 }}>
          <Card variant="outlined" sx={panelSx}>
            <PanelTitle title="Tokens per run" subtitle={`${data.tokensPerRun.reduce((sum, item) => sum + Number(item.value || 0), 0).toLocaleString()} total`} />
            <VerticalBarChart rows={data.tokensPerRun} format={fmtTokens} height={232} scrollable />
          </Card>
        </Box>
      </Box>

      <Card variant="outlined" sx={{ ...panelSx, p: { xs: 1.35, md: 1.75 } }}>
        <PanelTitle title="Expensive traces" />
        <DataTable
          rows={data.expensiveTraces}
          getKey={(row) => row.id}
          onRowClick={openTrace}
          columns={[
            {
              id: "root",
              label: "Trace",
              width: "34%",
              render: (row) => (
                <Typography sx={{ fontWeight: 650, lineHeight: 1.35, overflowWrap: "anywhere" }}>
                  {row.root}
                </Typography>
              )
            },
            { id: "timestamp", label: "Timestamp", width: "18%", render: (row) => fmtTimestamp(row.timestamp) },
            { id: "cost", label: "Cost", width: "13%", render: (row) => fmtCost(row.cost) },
            { id: "duration", label: "Duration", width: "13%", render: (row) => fmtMs(row.duration) },
            { id: "tokens", label: "Tokens", width: "13%", render: (row) => row.tokens.toLocaleString() },
            { id: "failed", label: "Failed", width: "9%" }
          ]}
        />
      </Card>
    </Stack>
  );
}
