import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { BrandMark } from "../components/AppShell";

export default function AuthPage({ mode, setMode, onEnter, colorMode, setColorMode, error, loading, onBack }) {
  const isDark = colorMode === "dark";
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const submit = (event) => {
    event.preventDefault();
    onEnter({ email, password, displayName });
  };

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "grid",
        gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1.1fr) 420px" },
        gap: 3.5,
        alignItems: "center",
        p: { xs: 2.75, md: 6 },
      }}
    >
      <Box sx={{ maxWidth: 700 }}>
        {onBack ? (
          <Button
            startIcon={<ArrowBackIcon />}
            onClick={onBack}
            variant="outlined"
            sx={{ mb: 3, textTransform: "none", fontWeight: 700 }}
          >
            Back
          </Button>
        ) : null}
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
          <BrandMark />
          <Typography variant="h1" sx={{ fontSize: { xs: 40, md: 72 }, lineHeight: 0.94 }}>
            AgentSRE
          </Typography>
        </Stack>
        <Typography variant="h2" sx={{ maxWidth: 640, fontSize: { xs: 24, md: 40 }, lineHeight: 1.14 }}>
          operate production AI agents with traceable reliability
        </Typography>
        <Typography sx={{ maxWidth: 590, mt: 2.2, color: "text.secondary", fontSize: { xs: 15.5, md: 17 }, lineHeight: 1.45 }}>
          SDK-based LangGraph, LLM, tool, latency, cost, and redaction telemetry
          <Box component="span" sx={{ display: "block" }}>for enterprise agent reliability and governance teams.</Box>
        </Typography>
      </Box>

      <Card variant="outlined" sx={{ position: "relative", p: 3, boxShadow: 12 }}>
        <IconButton onClick={() => setColorMode(isDark ? "light" : "dark")} sx={{ position: "absolute", right: 20, top: 20 }} aria-label="Toggle theme">
          {isDark ? <LightModeIcon /> : <DarkModeIcon />}
        </IconButton>
        <ToggleButtonGroup exclusive value={mode} onChange={(_, value) => value && setMode(value)} sx={{ mb: 3 }}>
          <ToggleButton value="login">Login</ToggleButton>
          <ToggleButton value="register">Register</ToggleButton>
        </ToggleButtonGroup>
        <Stack component="form" spacing={2} onSubmit={submit}>
          {mode === "register" ? (
            <TextField label="Full name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" />
          ) : null}
          <TextField label="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
          <TextField
            label="Password"
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            sx={{ "& input::-ms-reveal, & input::-ms-clear": { display: "none" } }}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    edge="end"
                    onClick={() => setShowPassword((visible) => !visible)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    sx={{ color: "text.secondary" }}
                  >
                    {showPassword ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          {error ? <Typography color="error" variant="body2">{error}</Typography> : null}
          <Button type="submit" variant="contained" size="large" disabled={loading}>
            {loading ? "Please wait..." : mode === "register" ? "Register" : "Login"}
          </Button>
        </Stack>
      </Card>
    </Box>
  );
}
