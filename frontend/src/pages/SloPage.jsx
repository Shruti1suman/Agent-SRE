import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DataTable from "../components/DataTable";
import MetricCard from "../components/MetricCard";
import PageHeader from "../components/PageHeader";
import { fetchSloMetricCatalog } from "../api/slos";

const SEVERITIES = ["critical", "high", "warning", "info"];
const OPERATOR_LABELS = {
  gt: "At most (<=)",
  gte: "Below (<)",
  lt: "At least (>=)",
  lte: "Above (>)",
};

function displayUnit(unit) {
  return unit === "ratio" ? "%" : unit || "";
}

function valueToDisplay(value, unit) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "";
  return unit === "ratio" ? String(numeric * 100) : String(numeric);
}

function valueToPayload(value, unit) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  return unit === "ratio" ? numeric / 100 : numeric;
}

function targetToDisplay(row) {
  return valueToDisplay(row.target ?? row.threshold_value ?? 0, row.raw_unit);
}

function UpdatedCell({ value }) {
  if (!value) return <Typography sx={{ fontSize: 13 }}>N/A</Typography>;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return <Typography sx={{ fontSize: 13 }}>{String(value)}</Typography>;
  return (
    <Stack spacing={0.15}>
      <Typography sx={{ fontSize: 13.5, lineHeight: 1.2 }}>{date.toLocaleDateString()}</Typography>
      <Typography color="text.secondary" sx={{ fontSize: 12, lineHeight: 1.25 }}>{date.toLocaleTimeString()}</Typography>
    </Stack>
  );
}

function CustomSloDialog({ open, metrics, predefinedMetricNames, onClose, onCreate }) {
  const customMetrics = useMemo(
    () => metrics.filter((item) => item.customizable !== false && !predefinedMetricNames.includes(item.name)),
    [metrics, predefinedMetricNames],
  );
  const categories = useMemo(
    () => [...new Set(customMetrics.map((item) => item.category))],
    [customMetrics],
  );
  const defaultMetric = customMetrics.find((item) => item.name === "model_rate_limit_count") || customMetrics[0];
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !defaultMetric) return;
    setForm({
      label: defaultMetric.label,
      category: defaultMetric.category,
      metric_name: defaultMetric.name,
      operator: defaultMetric.default_operator,
      threshold: valueToDisplay(defaultMetric.default_threshold, defaultMetric.unit),
      severity: "warning",
      is_active: true,
    });
    setError("");
  }, [open, defaultMetric?.name]);

  const selectedMetric = metrics.find((item) => item.name === form.metric_name) || defaultMetric;
  const categoryMetrics = customMetrics.filter((item) => item.category === form.category);
  const updateCategory = (category) => {
    const metric = customMetrics.find((item) => item.category === category);
    if (!metric) return;
    setForm((current) => ({
      ...current,
      category,
      label: metric.label,
      metric_name: metric.name,
      operator: metric.default_operator,
      threshold: valueToDisplay(metric.default_threshold, metric.unit),
    }));
  };
  const updateMetric = (metricName) => {
    const metric = customMetrics.find((item) => item.name === metricName);
    if (!metric) return;
    setForm((current) => ({
      ...current,
      label: metric.label,
      metric_name: metric.name,
      operator: metric.default_operator,
      threshold: valueToDisplay(metric.default_threshold, metric.unit),
    }));
  };

  const submit = async () => {
    const threshold = valueToPayload(form.threshold, selectedMetric?.unit);
    if (!form.label?.trim()) return setError("SLO name is required.");
    if (threshold === null || threshold < 0) return setError("Enter a valid non-negative threshold.");
    setSaving(true);
    setError("");
    try {
      await onCreate?.({
        label: form.label.trim(),
        metric_name: form.metric_name,
        operator: form.operator,
        threshold_value: threshold,
        severity: form.severity,
        is_active: Boolean(form.is_active),
      });
      onClose();
    } catch (requestError) {
      setError(requestError?.message || "Unable to create the custom SLO.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        Add custom SLO
        <IconButton onClick={onClose} disabled={saving} aria-label="Close"><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 0.5 }}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <TextField label="SLO name" value={form.label || ""} onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))} fullWidth />
          <Grid container spacing={1.5}>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Reliability type</InputLabel>
                <Select label="Reliability type" value={form.category || ""} onChange={(event) => updateCategory(event.target.value)}>
                  {categories.map((category) => <MenuItem key={category} value={category}>{category}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Metric</InputLabel>
                <Select label="Metric" value={form.metric_name || ""} onChange={(event) => updateMetric(event.target.value)}>
                  {categoryMetrics.map((metric) => <MenuItem key={metric.name} value={metric.name}>{metric.label}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
          <Grid container spacing={1.5}>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Condition</InputLabel>
                <Select label="Condition" value={form.operator || ""} onChange={(event) => setForm((current) => ({ ...current, operator: event.target.value }))}>
                  {(selectedMetric?.operators || []).map((operator) => <MenuItem key={operator} value={operator}>{OPERATOR_LABELS[operator]}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField label={`Threshold (${displayUnit(selectedMetric?.unit)})`} type="number" value={form.threshold || ""} onChange={(event) => setForm((current) => ({ ...current, threshold: event.target.value }))} fullWidth inputProps={{ min: 0 }} />
            </Grid>
          </Grid>
          <FormControl fullWidth>
            <InputLabel>Severity</InputLabel>
            <Select label="Severity" value={form.severity || "warning"} onChange={(event) => setForm((current) => ({ ...current, severity: event.target.value }))}>
              {SEVERITIES.map((severity) => <MenuItem key={severity} value={severity}>{severity[0].toUpperCase() + severity.slice(1)}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControlLabel control={<Switch checked={Boolean(form.is_active)} onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))} />} label="Enable immediately" />
          <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>This SLO is evaluated independently for every new agent run.</Typography>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ p: 2 }}><Button onClick={onClose} disabled={saving}>Cancel</Button><Button variant="contained" onClick={submit} disabled={saving || !selectedMetric}>Create SLO</Button></DialogActions>
    </Dialog>
  );
}

export default function SloPage({ sloData, loading = false, selectedProject, setToast, onSaveSlo, onCreateSlo, onDeleteSlo }) {
  const slos = sloData?.slos || [];
  const summary = sloData?.summary || {};
  const [drafts, setDrafts] = useState({});
  const [metrics, setMetrics] = useState([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteRow, setDeleteRow] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    fetchSloMetricCatalog().then((result) => setMetrics(result.metrics || [])).catch(() => setMetrics([]));
  }, []);

  useEffect(() => {
    const next = {};
    slos.forEach((row) => {
      next[row.slo_id] = { target: targetToDisplay(row), enabled: Boolean(row.enabled), severity: row.severity, operator: row.operator };
    });
    setDrafts(next);
  }, [slos]);

  const metricByName = useMemo(() => Object.fromEntries(metrics.map((item) => [item.name, item])), [metrics]);
  const predefinedSlos = useMemo(
    () => slos.filter((row) => row.configuration_kind !== "custom"),
    [slos],
  );
  const customSlos = useMemo(
    () => slos.filter((row) => row.configuration_kind === "custom"),
    [slos],
  );
  const predefinedMetricNames = useMemo(
    () => predefinedSlos.map((row) => row.metric_name),
    [predefinedSlos],
  );

  const saveRow = async (row) => {
    const draft = drafts[row.slo_id] || {};
    const threshold = valueToPayload(draft.target, row.raw_unit);
    if (threshold === null || threshold < 0) return setToast?.("Enter a valid non-negative threshold.");
    try {
      await onSaveSlo?.(row.slo_id, { threshold_value: threshold, is_active: Boolean(draft.enabled), severity: draft.severity, operator: draft.operator });
      setToast?.("SLO saved and will be used by the next trace evaluation.");
    } catch (error) {
      setToast?.(error?.message || "Unable to save the SLO.");
    }
  };

  const removeRow = async () => {
    if (!deleteRow) return;
    setDeleteLoading(true);
    try {
      await onDeleteSlo?.(deleteRow.slo_id);
      setDeleteRow(null);
      setToast?.("Custom SLO removed. Historical evidence was preserved.");
    } catch (error) {
      setToast?.(error?.message || "Unable to remove the custom SLO.");
    } finally {
      setDeleteLoading(false);
    }
  };

  const columns = [
    {
      id: "metric",
      label: "SLO",
      width: "21%",
      render: (row) => (
        <Box>
          <Typography sx={{ fontSize: 13.5 }}>{row.metric}</Typography>
          <Typography color="text.secondary" sx={{ fontSize: 11.5 }}>
            {metricByName[row.metric_name]?.category || "Reliability"}
          </Typography>
        </Box>
      ),
    },
    {
      id: "target",
      label: "Target",
      width: "34%",
      render: (row) => (
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ flexWrap: "nowrap", minWidth: 300 }}>
          <FormControl size="small" sx={{ width: 112 }}>
            <Select
              value={drafts[row.slo_id]?.operator ?? row.operator}
              onChange={(event) => setDrafts((current) => ({
                ...current,
                [row.slo_id]: { ...(current[row.slo_id] || {}), operator: event.target.value },
              }))}
            >
              {(metricByName[row.metric_name]?.operators || [row.operator]).map((operator) => (
                <MenuItem key={operator} value={operator}>{OPERATOR_LABELS[operator]}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            type="number"
            value={drafts[row.slo_id]?.target ?? targetToDisplay(row)}
            onChange={(event) => setDrafts((current) => ({
              ...current,
              [row.slo_id]: { ...(current[row.slo_id] || {}), target: event.target.value },
            }))}
            sx={{ width: 105 }}
          />
          <Typography sx={{ fontSize: 12, whiteSpace: "nowrap" }}>{row.unit}</Typography>
        </Stack>
      ),
    },
    {
      id: "severity",
      label: "Severity",
      width: "13%",
      render: (row) => (
        <FormControl size="small" fullWidth>
          <Select
            value={drafts[row.slo_id]?.severity ?? row.severity}
            onChange={(event) => setDrafts((current) => ({
              ...current,
              [row.slo_id]: { ...(current[row.slo_id] || {}), severity: event.target.value },
            }))}
          >
            {SEVERITIES.map((severity) => <MenuItem key={severity} value={severity}>{severity}</MenuItem>)}
          </Select>
        </FormControl>
      ),
    },
    { id: "updated", label: "Updated", width: "12%", render: (row) => <UpdatedCell value={row.updated} /> },
    {
      id: "action",
      label: "Action",
      width: "20%",
      render: (row) => (
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ flexWrap: "nowrap" }}>
          <Switch
            checked={Boolean(drafts[row.slo_id]?.enabled ?? row.enabled)}
            onChange={(event) => setDrafts((current) => ({
              ...current,
              [row.slo_id]: { ...(current[row.slo_id] || {}), enabled: event.target.checked },
            }))}
          />
          <Button variant="outlined" size="small" onClick={() => saveRow(row)}>Save</Button>
          {row.configuration_kind === "custom" ? (
            <Tooltip title="Remove custom SLO">
              <IconButton color="error" size="small" onClick={() => setDeleteRow(row)}>
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          ) : null}
        </Stack>
      ),
    },
  ];

  return (
    <>
      <PageHeader title="SLOs" action={<Button variant="contained" startIcon={<AddIcon />} disabled={!selectedProject || !metrics.length} onClick={() => setCreateOpen(true)}>Add custom SLO</Button>} />
      {!selectedProject ? <Alert severity="info" sx={{ mb: 2 }}>Select or create a project to manage SLOs.</Alert> : null}
      <Grid container spacing={1.75} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><MetricCard label="Configured SLOs" value={loading ? "..." : summary.configured ?? slos.length} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Enabled" value={loading ? "..." : summary.enabled ?? slos.filter((row) => row.enabled).length} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Healthy runs" value={loading ? "..." : summary.healthy_runs ?? 0} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Breached runs" value={loading ? "..." : summary.breached_runs ?? 0} /></Grid>
      </Grid>
      <Stack spacing={2.5}>
        <Box>
          <Typography variant="h3" sx={{ mb: 1 }}>Predefined SLOs</Typography>
          <DataTable
            rows={predefinedSlos}
            getKey={(row) => row.slo_id}
            emptyMessage="No predefined SLOs are configured for this project."
            columns={columns}
          />
        </Box>
        {customSlos.length ? (
          <Box>
            <Typography variant="h3" sx={{ mb: 1 }}>Custom SLOs</Typography>
            <DataTable
              rows={customSlos}
              getKey={(row) => row.slo_id}
              emptyMessage="No custom SLOs configured yet for this project."
              columns={columns}
            />
          </Box>
        ) : null}
      </Stack>
      <CustomSloDialog
        open={createOpen}
        metrics={metrics}
        predefinedMetricNames={predefinedMetricNames}
        onClose={() => setCreateOpen(false)}
        onCreate={onCreateSlo}
      />
      <Dialog open={Boolean(deleteRow)} onClose={deleteLoading ? undefined : () => setDeleteRow(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Remove custom SLO?</DialogTitle>
        <DialogContent><Typography color="text.secondary">{deleteRow?.metric} will no longer be evaluated for new runs. Existing incidents and trace evidence will remain available.</Typography></DialogContent>
        <DialogActions sx={{ p: 2 }}><Button onClick={() => setDeleteRow(null)} disabled={deleteLoading}>Cancel</Button><Button color="error" variant="contained" onClick={removeRow} disabled={deleteLoading}>Remove</Button></DialogActions>
      </Dialog>
    </>
  );
}
