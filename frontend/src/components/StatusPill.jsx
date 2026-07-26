import Chip from "@mui/material/Chip";

const colorMap = {
  success: "success",
  healthy: "success",
  completed: "success",
  warning: "warning",
  risk: "warning",
  high: "warning",
  triggered: "error",
  error: "error",
  critical: "error",
  breach: "error",
  failed: "error",
  captured: "secondary",
  acknowledged: "warning",
  resolved: "success",
  open: "warning",
  disabled: "default",
  not_evaluated: "default",
  compliant: "success",
  breached: "error"
};

const customSx = {
  tool: {
    color: "#d8b34a",
    borderColor: "rgba(216, 179, 74, 0.58)",
    bgcolor: "rgba(216, 179, 74, 0.08)"
  },
  llm: {
    color: "#6ea8fe",
    borderColor: "rgba(110, 168, 254, 0.58)",
    bgcolor: "rgba(110, 168, 254, 0.08)"
  },
  agent: {
    color: "#35c69d",
    borderColor: "rgba(53, 198, 157, 0.58)",
    bgcolor: "rgba(53, 198, 157, 0.08)"
  },
  loop: {
    color: "#ff8a4c",
    borderColor: "rgba(255, 138, 76, 0.58)",
    bgcolor: "rgba(255, 138, 76, 0.08)"
  }
};

export function statusColor(value) {
  return colorMap[String(value || "").toLowerCase()] || "default";
}

export default function StatusPill({ value, size = "small" }) {
  const normalized = String(value || "").toLowerCase();
  return (
    <Chip
      label={String(value || "N/A").toUpperCase()}
      color={statusColor(value)}
      size={size}
      variant="outlined"
      sx={{ fontWeight: 700, letterSpacing: 0, minHeight: size === "small" ? 24 : 30, ...customSx[normalized] }}
    />
  );
}
