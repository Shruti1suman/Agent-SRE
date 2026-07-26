import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

export default function MetricCard({ label, value, helper }) {
  return (
    <Card
      variant="outlined"
      sx={{
        p: 1.45,
        minHeight: 86,
        display: "grid",
        alignContent: "center",
        bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(17, 24, 33, 0.82)" : "rgba(255, 255, 255, 0.88)",
        borderColor: "rgba(151, 172, 203, 0.15)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,.03)"
      }}
    >
      <Stack spacing={0.65}>
        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, textTransform: "uppercase", letterSpacing: 0 }}>
          {label}
        </Typography>
        <Typography variant="h4" sx={{ fontWeight: 760, lineHeight: 1, fontSize: { xs: 24, md: 29 } }}>
          {value}
        </Typography>
        {helper ? <Typography variant="caption" color="text.secondary">{helper}</Typography> : null}
      </Stack>
    </Card>
  );
}
