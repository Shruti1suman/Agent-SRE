import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export default function PageHeader({ title, action }) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: { xs: "column", sm: "row" },
        alignItems: { xs: "stretch", sm: "center" },
        justifyContent: "space-between",
        gap: 1.25,
        mb: 2
      }}
    >
      <Typography variant="h5" component="h2" sx={{ fontWeight: 760 }}>
        {title}
      </Typography>
      {action ? <Box sx={{ display: "flex", justifyContent: { xs: "flex-start", sm: "flex-end" } }}>{action}</Box> : null}
    </Box>
  );
}
