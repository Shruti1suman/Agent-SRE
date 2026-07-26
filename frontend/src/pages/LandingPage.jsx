import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import AutoGraphOutlinedIcon from "@mui/icons-material/AutoGraphOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import GavelOutlinedIcon from "@mui/icons-material/GavelOutlined";
import KeyOutlinedIcon from "@mui/icons-material/KeyOutlined";
import LightModeIcon from "@mui/icons-material/LightMode";
import LoginIcon from "@mui/icons-material/Login";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import QueryStatsOutlinedIcon from "@mui/icons-material/QueryStatsOutlined";
import RuleOutlinedIcon from "@mui/icons-material/RuleOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import SpeedOutlinedIcon from "@mui/icons-material/SpeedOutlined";
import StorageOutlinedIcon from "@mui/icons-material/StorageOutlined";
import TimelineIcon from "@mui/icons-material/Timeline";
import { BrandMark } from "../components/AppShell";

const capabilities = [
  {
    icon: TimelineIcon,
    title: "Trace explorer",
    text: "Follow agent workflow, LLM, tool, HTTP, and memory spans with inputs, outputs, timing, and errors.",
  },
  {
    icon: QueryStatsOutlinedIcon,
    title: "Incident intelligence",
    text: "Detect tool failures, loops, latency drift, cost spikes, groundedness issues, and failed runs.",
  },
  {
    icon: SpeedOutlinedIcon,
    title: "Configurable SLOs",
    text: "Set project thresholds for success, latency, tool reliability, and token budget, then evaluate every run.",
  },
  {
    icon: GavelOutlinedIcon,
    title: "Governance evidence",
    text: "Review warnings, privacy and redaction evidence, and an execution-linked audit trail.",
  },
  {
    icon: PsychologyOutlinedIcon,
    title: "Incident assistant",
    text: "Ask incident-scoped questions, inspect evidence, understand root cause, and receive concrete code fixes.",
  },
  {
    icon: AutoGraphOutlinedIcon,
    title: "Operational health",
    text: "Track success, latency, loop risk, governance, tokens, cost, and overall agent health in one view.",
  },
];

const pipeline = [
  { icon: KeyOutlinedIcon, step: "01", title: "Instrument", text: "Initialize the SDK with a project key." },
  { icon: StorageOutlinedIcon, step: "02", title: "Collect", text: "Capture normalized execution telemetry." },
  { icon: RuleOutlinedIcon, step: "03", title: "Evaluate", text: "Run SLO and intelligence checks." },
  { icon: ShieldOutlinedIcon, step: "04", title: "Operate", text: "Investigate incidents and improve reliability." },
];

const sdkExample = `pip install -e "sdk[instrumentation]"

# Add the generated values to your agent's .env
AGENTSRE_BACKEND_URL=http://localhost:8081/v1/executions
AGENTSRE_API_KEY=<generated_sdk_key>
AGENTSRE_TENANT_ID=<tenant_id>
AGENTSRE_PROJECT_ID=<project_id>
AGENTSRE_SERVICE_NAME=my-agent
AGENTSRE_ENVIRONMENT=dev

# Your agent's model-provider key, when applicable
GEMINI_API_KEY=<your_gemini_key>

import os
import agentsre_sdk

agentsre_sdk.init(
    tenant_id=os.getenv("AGENTSRE_TENANT_ID"),
    project_id=os.getenv("AGENTSRE_PROJECT_ID"),
    service_name=os.getenv("AGENTSRE_SERVICE_NAME"),
    environment=os.getenv("AGENTSRE_ENVIRONMENT", "dev"),
    api_key=os.getenv("AGENTSRE_API_KEY"),
    pii_redaction=True,
    sensitive_fields=["email", "phone", "ssn", "api_key"],
    instrument_langgraph=True,
)`;

const previewNodes = [
  { label: "Input", color: "#7c8ba1", left: "6%", top: "50%", size: 42 },
  { label: "Agent", color: "#35c69d", left: "23%", top: "43%", size: 58 },
  { label: "LLM", color: "#6ea8fe", left: "44%", top: "22%", size: 52 },
  { label: "Memory", color: "#a985e8", left: "42%", top: "76%", size: 46 },
  { label: "Tool", color: "#e0b53e", left: "64%", top: "70%", size: 47 },
  { label: "Risk", color: "#ff6270", left: "78%", top: "36%", size: 48 },
  { label: "Result", color: "#35c69d", left: "93%", top: "46%", size: 50 },
];

function SectionHeading({ eyebrow, title, description }) {
  return (
    <Box sx={{ maxWidth: 690 }}>
      <Typography sx={{ color: "primary.main", fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>
        {eyebrow}
      </Typography>
      <Typography component="h2" sx={{ mt: 0.6, fontSize: { xs: 24, md: 30 }, lineHeight: 1.15, fontWeight: 700 }}>
        {title}
      </Typography>
      <Typography color="text.secondary" sx={{ mt: 1, fontSize: 14.5, lineHeight: 1.6 }}>
        {description}
      </Typography>
    </Box>
  );
}

function ProductPreview() {
  return (
    <Box
      sx={{
        position: "relative",
        minHeight: { xs: 390, md: 460 },
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        overflow: "hidden",
        bgcolor: "background.paper",
        boxShadow: (theme) => theme.palette.mode === "dark" ? "0 24px 60px rgba(0,0,0,.28)" : "0 24px 60px rgba(23,45,76,.12)",
        animation: "landingEnter .75s ease-out both",
        "@keyframes landingEnter": {
          from: { opacity: 0, transform: "translateY(12px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
      }}
    >
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          backgroundImage: (theme) => theme.palette.mode === "dark"
            ? "linear-gradient(rgba(151,172,203,.07) 1px, transparent 1px), linear-gradient(90deg, rgba(151,172,203,.07) 1px, transparent 1px)"
            : "linear-gradient(rgba(46,66,92,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(46,66,92,.08) 1px, transparent 1px)",
          backgroundSize: "34px 34px",
        }}
      />

      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ position: "relative", zIndex: 2, px: 2, py: 1.5, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
        <Box>
          <Typography sx={{ color: "text.secondary", fontSize: 10.5, fontWeight: 700, textTransform: "uppercase" }}>Live agent run</Typography>
          <Typography sx={{ mt: 0.2, fontSize: 17, fontWeight: 700 }}>sample-agent-run</Typography>
        </Box>
        <Chip label="RISK" color="warning" variant="outlined" size="small" sx={{ fontWeight: 700 }} />
      </Stack>

      <Box sx={{ position: "absolute", inset: { xs: "76px 14px 88px", md: "82px 24px 92px" } }}>
        <Box
          component="svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
          sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", color: "divider" }}
        >
          {[
            "M 6 50 C 12 50, 17 43, 23 43",
            "M 23 43 C 31 42, 35 22, 44 22",
            "M 23 43 C 31 48, 34 76, 42 76",
            "M 44 22 C 58 20, 67 31, 78 36",
            "M 42 76 C 50 76, 56 70, 64 70",
            "M 64 70 C 70 65, 72 43, 78 36",
            "M 78 36 C 84 36, 87 46, 93 46",
          ].map((path) => (
            <path
              key={path}
              d={path}
              fill="none"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <circle r="1.2" fill="#41a6ff">
            <animateMotion
              dur="5.5s"
              repeatCount="indefinite"
              path="M 6 50 C 12 50, 17 43, 23 43 C 31 42, 35 22, 44 22 C 58 20, 67 31, 78 36 C 84 36, 87 46, 93 46"
            />
          </circle>
          <circle r="1.2" fill="#a985e8">
            <animateMotion
              dur="5.5s"
              begin="1.1s"
              repeatCount="indefinite"
              path="M 23 43 C 31 48, 34 76, 42 76 C 50 76, 56 70, 64 70 C 70 65, 72 43, 78 36 C 84 36, 87 46, 93 46"
            />
          </circle>
        </Box>
        {previewNodes.map((node, index) => (
          <Box
            key={node.label}
            sx={{
              position: "absolute",
              left: node.left,
              top: node.top,
              transform: "translate(-50%, -50%)",
              width: node.size,
              height: node.size,
              borderRadius: "50%",
              display: "grid",
              placeItems: "center",
              bgcolor: node.color,
              color: node.color === "#e0b53e" ? "#101820" : "#fff",
              fontSize: 9.5,
              fontWeight: 700,
              boxShadow: `0 0 22px ${node.color}55`,
              border: "2px solid rgba(255,255,255,.24)",
              animation: `nodePulse 3.6s ease-in-out ${index * 0.35}s infinite`,
              "@keyframes nodePulse": {
                "0%, 72%, 100%": { boxShadow: `0 0 16px ${node.color}40` },
                "82%": { boxShadow: `0 0 30px ${node.color}88` },
              },
            }}
          >
            {node.label}
          </Box>
        ))}
      </Box>

      <Box sx={{ position: "absolute", left: 14, right: 14, bottom: 14, display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 1 }}>
        {[
          ["Health score", "82%", "warning.main"],
          ["P90 latency", "2.11s", "text.primary"],
          ["Open incidents", "3", "error.main"],
        ].map(([label, value, color]) => (
          <Box key={label} sx={{ px: 1.25, py: 1, border: "1px solid", borderColor: "divider", borderRadius: 1, bgcolor: "background.paper" }}>
            <Typography sx={{ color: "text.secondary", fontSize: 10.5, fontWeight: 650 }}>{label}</Typography>
            <Typography sx={{ mt: 0.25, fontSize: { xs: 17, md: 19 }, lineHeight: 1.2, fontWeight: 700, color }}>{value}</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

function CapabilityCard({ icon: Icon, title, text, index }) {
  return (
    <Card
      variant="outlined"
      sx={{
        p: 2,
        height: "100%",
        borderRadius: 1.5,
        bgcolor: "background.paper",
        transition: "transform .2s ease, border-color .2s ease, box-shadow .2s ease",
        animation: `landingEnter .55s ease-out ${index * 0.06}s both`,
        "&:hover": { transform: "translateY(-3px)", borderColor: "primary.main", boxShadow: 3 },
      }}
    >
      <Stack direction="row" spacing={1.4} alignItems="flex-start">
        <Box sx={{ flex: "0 0 auto", width: 34, height: 34, borderRadius: 1, display: "grid", placeItems: "center", color: "primary.main", bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(65,166,255,.12)" : "rgba(27,112,190,.09)" }}>
          <Icon sx={{ fontSize: 19 }} />
        </Box>
        <Box>
          <Typography sx={{ fontSize: 15, fontWeight: 700 }}>{title}</Typography>
          <Typography color="text.secondary" sx={{ mt: 0.6, fontSize: 13, lineHeight: 1.55 }}>{text}</Typography>
        </Box>
      </Stack>
    </Card>
  );
}

export default function LandingPage({ colorMode, setColorMode, onLogin, onRegister }) {
  const isDark = colorMode === "dark";

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Stack
        component="nav"
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{
          position: "sticky",
          top: 0,
          zIndex: 10,
          minHeight: { xs: 68, md: 74 },
          px: { xs: 2, md: 4 },
          py: { xs: 1, md: 1.35 },
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(8,13,20,.92)" : "rgba(255,255,255,.94)",
          backdropFilter: "blur(14px)",
        }}
      >
        <Stack direction="row" spacing={1} alignItems="center">
          <BrandMark small />
          <Typography sx={{ fontWeight: 700, fontSize: 16 }}>AgentSRE</Typography>
        </Stack>
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Button startIcon={<LoginIcon />} variant="text" onClick={onLogin} sx={{ minWidth: 0, px: { xs: 1, sm: 1.5 }, fontSize: 13 }}>
            Login
          </Button>
          <Button variant="outlined" onClick={onRegister} sx={{ display: { xs: "none", sm: "inline-flex" }, fontSize: 13 }}>
            Create account
          </Button>
          <IconButton size="small" onClick={() => setColorMode(isDark ? "light" : "dark")} aria-label="Toggle theme" sx={{ ml: 0.25 }}>
            {isDark ? <LightModeIcon fontSize="small" /> : <DarkModeIcon fontSize="small" />}
          </IconButton>
        </Stack>
      </Stack>

      <Box component="main">
        <Box sx={{ maxWidth: 1280, mx: "auto", px: { xs: 2, md: 4 }, pt: { xs: 4, md: 6 }, pb: { xs: 5, md: 7 } }}>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "minmax(0, .9fr) minmax(440px, 1.1fr)" }, gap: { xs: 4, lg: 6 }, alignItems: "center" }}>
            <Stack spacing={2} sx={{ animation: "landingCopy .6s ease-out both", "@keyframes landingCopy": { from: { opacity: 0, transform: "translateX(-10px)" }, to: { opacity: 1, transform: "translateX(0)" } } }}>
              <Stack direction="row" spacing={1.25} alignItems="center">
                <BrandMark />
                <Typography sx={{ fontSize: { xs: 25, md: 30 }, lineHeight: 1, fontWeight: 700 }}>
                  AgentSRE
                </Typography>
              </Stack>
              <Typography component="h1" sx={{ maxWidth: 610, fontSize: { xs: 30, sm: 36, md: 40 }, lineHeight: 1.14, fontWeight: 700 }}>
                operate production AI agents with traceable reliability
              </Typography>
              <Typography sx={{ maxWidth: 600, color: "text.secondary", fontSize: { xs: 14.5, md: 16 }, lineHeight: 1.65 }}>
                See how every agent run behaves through unified telemetry, workflow traces, incidents, SLOs, governance evidence, and guided remediation.
              </Typography>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                <Button variant="contained" endIcon={<ArrowForwardIcon />} onClick={onRegister} sx={{ minHeight: 42, px: 2.2, fontSize: 13.5 }}>
                  Create account
                </Button>
                <Button variant="outlined" startIcon={<LoginIcon />} onClick={onLogin} sx={{ minHeight: 42, px: 2.2, fontSize: 13.5 }}>
                  Login to workspace
                </Button>
              </Stack>
              <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ pt: 0.5 }}>
                {["Minimal SDK setup", "Project-scoped data", "Incident RCA assistant"].map((item) => (
                  <Stack key={item} direction="row" spacing={0.6} alignItems="center">
                    <CheckCircleOutlineIcon color="success" sx={{ fontSize: 16 }} />
                    <Typography color="text.secondary" sx={{ fontSize: 12.5, fontWeight: 600 }}>{item}</Typography>
                  </Stack>
                ))}
              </Stack>
            </Stack>
            <ProductPreview />
          </Box>
        </Box>

        <Box sx={{ borderTop: "1px solid", borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
          <Box sx={{ maxWidth: 1280, mx: "auto", px: { xs: 2, md: 4 }, py: { xs: 4, md: 5 } }}>
            <SectionHeading
              eyebrow="From execution to action"
              title="One operational path for every agent run"
              description="A project SDK key connects the user's agent to a consistent processing path. Each stage adds context without requiring teams to inspect scattered services or raw events."
            />
            <Box sx={{ mt: 3, display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" }, border: "1px solid", borderColor: "divider", borderRadius: 1.5, overflow: "hidden" }}>
              {pipeline.map(({ icon: Icon, step, title, text }, index) => (
                <Box key={title} sx={{ position: "relative", p: 2, minHeight: 150, borderRight: { lg: index < pipeline.length - 1 ? "1px solid" : "none" }, borderBottom: { xs: index < pipeline.length - 1 ? "1px solid" : "none", sm: index < 2 ? "1px solid" : "none", lg: "none" }, borderColor: "divider" }}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Box sx={{ width: 32, height: 32, display: "grid", placeItems: "center", color: "primary.main", border: "1px solid", borderColor: "divider", borderRadius: 1 }}><Icon sx={{ fontSize: 18 }} /></Box>
                    <Typography color="text.secondary" sx={{ fontSize: 11, fontWeight: 700 }}>{step}</Typography>
                  </Stack>
                  <Typography sx={{ mt: 1.5, fontSize: 15, fontWeight: 700 }}>{title}</Typography>
                  <Typography color="text.secondary" sx={{ mt: 0.65, fontSize: 12.5, lineHeight: 1.5 }}>{text}</Typography>
                </Box>
              ))}
            </Box>
          </Box>
        </Box>

        <Box sx={{ maxWidth: 1280, mx: "auto", px: { xs: 2, md: 4 }, py: { xs: 5, md: 7 } }}>
          <SectionHeading
            eyebrow="Platform capabilities"
            title="Everything needed to understand and improve an agent"
            description="Move from fleet-level health to one trace, one span, or one incident without losing the execution context that explains what happened."
          />
          <Box sx={{ mt: 3, display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(3, minmax(0, 1fr))" }, gap: 1.5 }}>
            {capabilities.map((capability, index) => <CapabilityCard key={capability.title} {...capability} index={index} />)}
          </Box>
        </Box>

        <Box sx={{ borderTop: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
          <Box sx={{ maxWidth: 1280, minHeight: { md: 590 }, mx: "auto", px: { xs: 2, md: 4 }, py: { xs: 5, md: 6 }, display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "minmax(280px, .72fr) minmax(520px, 1.28fr)" }, gap: { xs: 3, lg: 5 }, alignItems: "stretch" }}>
              <Box>
                <Typography sx={{ color: "primary.main", fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>SDK quick start</Typography>
                <Typography sx={{ mt: 0.6, fontSize: { xs: 23, md: 28 }, lineHeight: 1.18, fontWeight: 700 }}>Connect the first agent run in minutes.</Typography>
                <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 520, fontSize: 14, lineHeight: 1.6 }}>
                  The Create Project page supplies the real project ID, tenant ID, and SDK key. Add them to the agent environment and initialize the SDK once at application startup.
                </Typography>

                <Stack spacing={1.3} sx={{ mt: 3 }}>
                  {[
                    ["Create a project", "Use one project per agent product or operational boundary."],
                    ["Generate an SDK key", "The full project-scoped key is shown once and should stay in the agent environment."],
                    ["Install and initialize", "Install the instrumentation package and initialize it before building or invoking the agent."],
                    ["Run the agent", "Executions, spans, metrics, incidents, SLOs, and governance evidence begin populating automatically."],
                  ].map(([title, text], index) => (
                    <Stack key={title} direction="row" spacing={1.2} alignItems="flex-start">
                      <Box sx={{ mt: 0.1, flex: "0 0 auto", width: 25, height: 25, borderRadius: "50%", display: "grid", placeItems: "center", border: "1px solid", borderColor: "primary.main", color: "primary.main", fontSize: 11, fontWeight: 700 }}>
                        {index + 1}
                      </Box>
                      <Box>
                        <Typography sx={{ fontSize: 13.5, fontWeight: 700 }}>{title}</Typography>
                        <Typography color="text.secondary" sx={{ mt: 0.25, fontSize: 12.5, lineHeight: 1.5 }}>{text}</Typography>
                      </Box>
                    </Stack>
                  ))}
                </Stack>

                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 3 }}>
                  <Button variant="contained" startIcon={<KeyOutlinedIcon />} onClick={onRegister}>Create project</Button>
                  <Button variant="outlined" onClick={onLogin}>Open workspace</Button>
                </Stack>
              </Box>

              <Box sx={{ minWidth: 0, border: "1px solid", borderColor: "divider", borderRadius: 1.5, overflow: "hidden", bgcolor: (theme) => theme.palette.mode === "dark" ? "#071019" : "#10202d", color: "#c9fff6" }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 1.5, py: 1.1, borderBottom: "1px solid rgba(183,255,244,.14)" }}>
                  <Stack direction="row" spacing={0.7} alignItems="center">
                    {["#ff6270", "#e0b53e", "#35c69d"].map((color) => <Box key={color} sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: color }} />)}
                  </Stack>
                  <Typography sx={{ color: "rgba(201,255,246,.65)", fontSize: 10.5, fontWeight: 650 }}>agent_setup.py</Typography>
                </Stack>
                <Typography
                  component="pre"
                  sx={{
                    m: 0,
                    p: { xs: 1.5, md: 2 },
                    minHeight: { xs: 360, md: 405 },
                    maxHeight: 430,
                    overflow: "auto",
                    fontFamily: '"Cascadia Mono", Consolas, monospace',
                    fontSize: { xs: 10.5, md: 11.5 },
                    lineHeight: 1.6,
                    whiteSpace: "pre",
                  }}
                >
                  {sdkExample}
                </Typography>
              </Box>
            </Box>
            <Divider sx={{ my: 4 }} />
            <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
              <Stack direction="row" spacing={1} alignItems="center"><BrandMark small /><Typography sx={{ fontSize: 13, fontWeight: 700 }}>AgentSRE</Typography></Stack>
              <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>Agent observability, intelligence, SLOs, and governance in one workspace.</Typography>
            </Stack>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
