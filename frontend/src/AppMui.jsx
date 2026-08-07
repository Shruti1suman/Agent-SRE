import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import GlobalStyles from "@mui/material/GlobalStyles";
import Box from "@mui/material/Box";
import Drawer from "@mui/material/Drawer";
import Dialog from "@mui/material/Dialog";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Snackbar from "@mui/material/Snackbar";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SendIcon from "@mui/icons-material/Send";
import AppShell from "./components/AppShell";
import StatusPill from "./components/StatusPill";
import AuthPage from "./pages/AuthPage";
import LandingPage from "./pages/LandingPage";
import DashboardPage from "./pages/DashboardPage";
import TracesPage from "./pages/TracesPage";
import ExplorerPage from "./pages/ExplorerPage";
import IncidentsPage from "./pages/IncidentsPage";
import SloPage from "./pages/SloPage";
import GovernancePage from "./pages/GovernancePage";
import CreateProjectPage from "./pages/CreateProjectPage";
import { governanceReplayEvents } from "./data";
import { makeTheme } from "./theme";
import { setStoredToken } from "./api/client";
import { login as loginApi, logout as logoutApi, signup as signupApi } from "./api/auth";
import { createProject, listProjects, regenerateProjectKey } from "./api/projects";
import { fetchDashboardSources, fetchTraceReplay } from "./api/dashboard";
import { askIncident, fetchIncidentChat } from "./api/incidents";
import { createSlo, deleteSlo, updateSlo } from "./api/slos";
import { emptyDashboardData, mapDashboardData } from "./mappers/dashboardMappers";
import { mapReplayToTrace, traceDisplayName } from "./mappers/traceMappers";

const SELECTED_PROJECT_KEY = "agentsre.selected_project_id";

function initialIncidentMessages() {
  return [
    {
      role: "assistant",
      content: "I can answer from this incident, its trace replay, metrics, SLO results, and captured span payloads. Ask what happened, which span caused it, or how to fix it."
    }
  ];
}

function fmtMs(value) {
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value}ms`;
}

function PayloadBlock({ label, value }) {
  if (!value) return null;
  return (
    <Box>
      <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 650, textTransform: "uppercase" }}>
        {label}
      </Typography>
      <Box
        component="pre"
        sx={{
          mt: 0.5,
          m: 0,
          p: 1,
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          bgcolor: "background.paper",
          color: "text.primary",
          fontFamily: "inherit",
          fontSize: 13,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word"
        }}
      >
        {value}
      </Box>
    </Box>
  );
}

function TraceDrawer({ trace, loading, onClose }) {
  const spans = trace?.spansList || [];
  return (
    <Drawer anchor="right" open={Boolean(trace)} onClose={onClose} PaperProps={{ sx: { width: { xs: "100%", sm: 620 }, p: 2 } }}>
      {trace ? (
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 760 }}>{traceDisplayName(trace)}</Typography>
              <Typography color="text.secondary">{trace.agent} / {trace.root}</Typography>
            </Box>
            <IconButton onClick={onClose} aria-label="Close drawer"><CloseIcon /></IconButton>
          </Stack>
          {spans.length ? spans.map((span, index) => (
            <Accordion
              key={span.id || `${span.name}-${index}`}
              disableGutters
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
                bgcolor: "background.default",
                boxShadow: "none",
                "&:before": { display: "none" },
                "&.Mui-expanded": { m: 0 }
              }}
            >
              <AccordionSummary
                expandIcon={<ExpandMoreIcon fontSize="small" />}
                sx={{
                  minHeight: 58,
                  px: 1.5,
                  "&.Mui-expanded": { minHeight: 58 },
                  "& .MuiAccordionSummary-content": {
                    my: 1,
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 1.5
                  }
                }}
              >
                <Box sx={{ minWidth: 0 }}>
                  <Typography sx={{ fontWeight: 700 }} noWrap>{span.name}</Typography>
                  <Typography variant="caption" color="text.secondary">{fmtMs(span.duration)}</Typography>
                </Box>
                <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
                  <StatusPill value={span.status} />
                  <StatusPill value={span.kind} />
                </Stack>
              </AccordionSummary>
              <AccordionDetails sx={{ px: 1.5, pt: 0, pb: 1.5 }}>
                <Stack spacing={1.25}>
                  <PayloadBlock label="Model used" value={span.modelName || span.provider} />
                  <PayloadBlock label="Input" value={span.input} />
                  <PayloadBlock label="Output" value={span.output || span.toolOutput} />
                  <PayloadBlock label="Error" value={span.error} />
                  {!span.modelName && !span.provider && !span.input && !span.output && !span.toolOutput && !span.error ? (
                    <Typography variant="body2" color="text.secondary">No payload details captured for this span.</Typography>
                  ) : null}
                </Stack>
              </AccordionDetails>
            </Accordion>
          )) : (
            <Typography color="text.secondary">
              {loading ? "Loading replay spans..." : "Open the trace explorer to load replay details for this execution."}
            </Typography>
          )}
        </Stack>
      ) : null}
    </Drawer>
  );
}

function IncidentChatDialog({ incident, messages, loading, onSend, onClose }) {
  const [draft, setDraft] = useState("");
  const messagesEndRef = useRef(null);
  const suggestions = [
    "Why did this incident happen?",
    "Which span or payload caused it?",
    "How should I fix this?",
    "Was there an SLO breach?"
  ];

  const submit = async (value = draft) => {
    const text = value.trim();
    if (!text || loading) return;
    setDraft("");
    await onSend(text);
  };

  useEffect(() => {
    if (!incident) return;
    messagesEndRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [incident?.incidentId, messages.length, loading]);

  return (
    <Dialog
      open={Boolean(incident)}
      onClose={onClose}
      maxWidth={false}
      BackdropProps={{
        sx: {
          backdropFilter: "blur(9px)",
          backgroundColor: "rgba(0, 0, 0, 0.52)"
        }
      }}
      PaperProps={{
        sx: {
          width: { xs: "calc(100vw - 24px)", sm: 680, md: 760 },
          height: { xs: "calc(100vh - 48px)", sm: 680 },
          maxHeight: "calc(100vh - 48px)",
          borderRadius: 1,
          p: { xs: 1.25, sm: 2 },
          bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(10, 15, 23, 0.98)" : "rgba(255, 255, 255, 0.98)",
          backgroundImage: "none",
          border: "1px solid",
          borderColor: "divider",
          boxShadow: "0 28px 90px rgba(0, 0, 0, 0.45)"
        }
      }}
    >
      {incident ? (
        <Stack spacing={2} sx={{ height: "100%" }}>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="h6" sx={{ fontWeight: 720 }}>Ask AgentSRE</Typography>
              <Typography color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
                {incident.rule} / {incident.traceName || incident.traceDisplay || incident.trace}
              </Typography>
            </Box>
            <IconButton onClick={onClose} aria-label="Close incident assistant"><CloseIcon /></IconButton>
          </Stack>

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <StatusPill value={incident.severity} />
            <StatusPill value={incident.status} />
            <StatusPill value={incident.type} />
          </Stack>

          <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1.4 }}>
            <Typography variant="subtitle2">Incident context</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5 }}>{incident.incident}</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.75, fontSize: 13 }}>{incident.recommendation}</Typography>
          </Box>

          <Stack spacing={0.75} direction="row" flexWrap="wrap" useFlexGap>
            {suggestions.map((question) => (
              <Button key={question} size="small" variant="outlined" onClick={() => submit(question)} disabled={loading}>
                {question}
              </Button>
            ))}
          </Stack>

          <Stack spacing={1.2} sx={{ flex: 1, overflowY: "auto", pr: 0.5 }}>
            {messages.map((message, index) => (
              <Box
                key={`${message.role}-${index}`}
                sx={{
                  alignSelf: message.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "92%",
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 1,
                  px: 1.35,
                  py: 1.05,
                  bgcolor: message.role === "user" ? "rgba(65, 166, 255, 0.14)" : "background.default"
                }}
              >
                <Typography
                  sx={{
                    fontSize: 13.5,
                    lineHeight: 1.55,
                    whiteSpace: "pre-wrap",
                    overflowWrap: "anywhere"
                  }}
                >
                  {message.content}
                </Typography>
              </Box>
            ))}
            {loading ? (
              <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "text.secondary" }}>
                <CircularProgress size={16} />
                <Typography variant="body2">Reading incident context...</Typography>
              </Stack>
            ) : null}
            <Box ref={messagesEndRef} sx={{ height: 28, flexShrink: 0 }} />
          </Stack>

          <Stack direction="row" spacing={1} component="form" onSubmit={(event) => { event.preventDefault(); submit(); }}>
            <TextField
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask about RCA, spans, SLO breach, or fixes"
              size="small"
              fullWidth
              multiline
              maxRows={3}
            />
            <IconButton type="submit" color="primary" disabled={!draft.trim() || loading} aria-label="Send incident question">
              <SendIcon />
            </IconButton>
          </Stack>
        </Stack>
      ) : null}
    </Dialog>
  );
}

function GovernanceDrawer({ open, onClose }) {
  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: "100%", sm: 620 }, p: 2 } }}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 760 }}>Governance replay</Typography>
            <Typography color="text.secondary">governance.execution.full</Typography>
          </Box>
          <IconButton onClick={onClose} aria-label="Close drawer"><CloseIcon /></IconButton>
        </Stack>
        {governanceReplayEvents.map((event) => (
          <Box key={event.time} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1.5 }}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="caption" color="text.secondary" sx={{ width: 70, fontWeight: 700 }}>{event.time}</Typography>
              <StatusPill value={event.status} />
              <Typography sx={{ fontWeight: 700 }}>{event.type}</Typography>
            </Stack>
            <Typography color="text.secondary">{event.detail}</Typography>
            <Typography variant="caption">{event.evidence}</Typography>
          </Box>
        ))}
      </Stack>
    </Drawer>
  );
}

export default function AppMui() {
  const [mode, setMode] = useState("dark");
  const [authed, setAuthed] = useState(Boolean(getStoredToken()));
  const [authMode, setAuthMode] = useState("login");
  const [authStarted, setAuthStarted] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [page, setPage] = useState("dashboard");
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [traceReplay, setTraceReplay] = useState(null);
  const [traceReplayLoading, setTraceReplayLoading] = useState(false);
  const [traceReplayError, setTraceReplayError] = useState("");
  const [traceDrawer, setTraceDrawer] = useState(null);
  const [incidentChat, setIncidentChat] = useState(null);
  const [incidentChatHistories, setIncidentChatHistories] = useState({});
  const [incidentChatLoading, setIncidentChatLoading] = useState(false);
  const [governanceOpen, setGovernanceOpen] = useState(false);
  const [toast, setToast] = useState("");
  const [user, setUser] = useState(null);
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(localStorage.getItem(SELECTED_PROJECT_KEY) || "");
  const [lastSdkKey, setLastSdkKey] = useState("");
  const [dashboardSources, setDashboardSources] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [refreshCount, setRefreshCount] = useState(0);
  const theme = useMemo(() => makeTheme(mode), [mode]);
  const selectedProject = projects.find((project) => project.project_id === selectedProjectId) || null;
  const dashboardData = useMemo(
    () => dashboardSources ? mapDashboardData({ sources: dashboardSources, selectedProjectId }) : { ...emptyDashboardData, hasProject: Boolean(selectedProjectId) },
    [dashboardSources, selectedProjectId],
  );
  const traceRows = dashboardData.traces || [];
  const incidentRows = dashboardData.incidents || [];
  const incidentMessages = incidentChat?.incidentId
    ? incidentChatHistories[incidentChat.incidentId] || initialIncidentMessages()
    : [];
  const selectedTraceWithReplay = useMemo(
    () => mapReplayToTrace(selectedTrace, traceReplay),
    [selectedTrace, traceReplay],
  );

  const openTraceDrawer = useCallback((trace) => {
    setSelectedTrace(trace);
    setTraceDrawer(trace);
  }, []);

  const openIncidentChat = useCallback((incident) => {
    setIncidentChat(incident);
    setIncidentChatHistories((current) => (
      current[incident.incidentId]
        ? current
        : { ...current, [incident.incidentId]: initialIncidentMessages() }
    ));
    fetchIncidentChat(incident.incidentId)
      .then((payload) => {
        const messages = payload?.messages?.length ? payload.messages : initialIncidentMessages();
        setIncidentChatHistories((current) => ({ ...current, [incident.incidentId]: messages }));
      })
      .catch(() => {
        setIncidentChatHistories((current) => (
          current[incident.incidentId]
            ? current
            : { ...current, [incident.incidentId]: initialIncidentMessages() }
        ));
      });
  }, []);

  const sendIncidentQuestion = useCallback(async (message) => {
    if (!incidentChat?.incidentId) return;
    const incidentId = incidentChat.incidentId;
    const currentMessages = incidentChatHistories[incidentId] || initialIncidentMessages();
    const nextMessages = [...currentMessages, { role: "user", content: message }];
    setIncidentChatHistories((current) => ({ ...current, [incidentId]: nextMessages }));
    setIncidentChatLoading(true);
    try {
      const response = await askIncident(incidentId, {
        message,
        history: nextMessages
      });
      setIncidentChatHistories((current) => ({
        ...current,
        [incidentId]: response.messages?.length
          ? response.messages
          : [...(current[incidentId] || nextMessages), { role: "assistant", content: response.answer || "No answer was returned." }]
      }));
    } catch (error) {
      const message = String(error.message || "");
      const content = message.toLowerCase().includes("not found")
        ? "The incident assistant API is not loaded in the running backend yet. Restart the backend once, then ask again."
        : message || "Unable to answer from incident context.";
      setIncidentChatHistories((current) => ({
        ...current,
        [incidentId]: [...(current[incidentId] || nextMessages), { role: "assistant", content }]
      }));
    } finally {
      setIncidentChatLoading(false);
    }
  }, [incidentChat?.incidentId, incidentChatHistories]);

  const selectProject = useCallback((projectId) => {
    setSelectedProjectId(projectId);
    setSelectedTrace(null);
    setTraceReplay(null);
    setTraceReplayError("");
    if (projectId) {
      localStorage.setItem(SELECTED_PROJECT_KEY, projectId);
    } else {
      localStorage.removeItem(SELECTED_PROJECT_KEY);
    }
  }, []);

  const loadProjects = useCallback(async () => {
    const rows = await listProjects();
    setProjects(rows);
    const stored = localStorage.getItem(SELECTED_PROJECT_KEY);
    const nextProjectId = rows.find((project) => project.project_id === stored)?.project_id || rows[0]?.project_id || "";
    selectProject(nextProjectId);
    return rows;
  }, [selectProject]);


  useEffect(() => {
    if (!getStoredToken()) {
      setAuthed(false);
      return;
    }
    me()
      .then((payload) => {
        setUser(payload.user);
        setAuthed(true);
        return loadProjects();
      })
      .then((rows) => {
        setPage(rows.length ? "dashboard" : "create");
      })
      .catch(() => {
        setStoredToken(null);
        setAuthed(false);
      });
  }, [loadProjects]);


  useEffect(() => {
    if (!authed || !selectedProjectId) {
      setDashboardSources(null);
      return;
    }

    setDashboardLoading(true);
    fetchDashboardSources(selectedProjectId)
      .then(setDashboardSources)
      .catch((error) => {
        setDashboardSources(null);
        setToast(error.message || "Unable to load dashboard data from the API gateway.");
      })
      .finally(() => setDashboardLoading(false));
  }, [authed, selectedProjectId, refreshCount]);

  useEffect(() => {
    if (!selectedTrace && traceRows.length) {
      setSelectedTrace(traceRows[0]);
    }
  }, [selectedTrace, traceRows]);

  useEffect(() => {
    if (!selectedTrace?.id || !authed) {
      setTraceReplay(null);
      setTraceReplayError("");
      return;
    }

    setTraceReplayLoading(true);
    setTraceReplayError("");
    fetchTraceReplay(selectedTrace.id)
      .then(setTraceReplay)
      .catch((error) => {
        setTraceReplay(null);
        setTraceReplayError(error.message || "Unable to load trace replay.");
      })
      .finally(() => setTraceReplayLoading(false));
  }, [authed, selectedTrace?.id]);

  useEffect(() => {
    if (traceDrawer?.id && selectedTraceWithReplay?.id === traceDrawer.id) {
      setTraceDrawer(selectedTraceWithReplay);
    }
  }, [selectedTraceWithReplay, traceDrawer?.id]);

  async function handleAuth(credentials) {
    setAuthError("");
    if (!credentials.email?.trim()) {
      setAuthError("Email is required.");
      return;
    }
    if (!credentials.password) {
      setAuthError("Password is required.");
      return;
    }
    setAuthLoading(true);
    try {
      const session = authMode === "register"
        ? await signupApi(credentials)
        : await loginApi(credentials);
      setUser(session.user);
      setAuthed(true);
      setAuthStarted(false);
      const rows = await loadProjects();
      setPage(rows.length ? "dashboard" : "create");
      setToast(authMode === "register" ? "Account created." : "Login successful.");
    } catch (error) {
      setAuthError(error?.message || "Authentication failed. Please check your credentials.");
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleLogout() {
    await logoutApi().catch(() => {});
    setAuthed(false);
    setAuthStarted(false);
    setUser(null);
    setProjects([]);
    setDashboardSources(null);
    setSelectedTrace(null);
    setTraceReplay(null);
    selectProject("");
  }

  async function handleCreateProject({ projectName, description }) {
    const project = await createProject({ projectName, description });
    setProjects((current) => [project, ...current.filter((item) => item.project_id !== project.project_id)]);
    setLastSdkKey("");
    selectProject(project.project_id);
    setPage("create");
    return project;
  }

  async function handleGenerateKey({ keyName } = {}) {
    if (!selectedProjectId) {
      setPage("create");
      throw new Error("Create or select a project first.");
    }
    const project = await regenerateProjectKey(selectedProjectId, { keyName });
    setLastSdkKey(project.sdk_key || "");
    setProjects((current) => current.map((item) => item.project_id === project.project_id ? { ...item, ...project } : item));
    return project;
  }

  async function handleSaveSlo(sloId, payload) {
    if (!selectedProjectId) {
      throw new Error("Select a project first.");
    }
    await updateSlo(selectedProjectId, sloId, payload);
    setRefreshCount((count) => count + 1);
  }

  async function handleCreateSlo(payload) {
    if (!selectedProjectId) throw new Error("Select a project first.");
    const created = await createSlo(selectedProjectId, payload);
    setRefreshCount((count) => count + 1);
    return created;
  }

  async function handleDeleteSlo(sloId) {
    if (!selectedProjectId) throw new Error("Select a project first.");
    await deleteSlo(selectedProjectId, sloId);
    setRefreshCount((count) => count + 1);
  }

  const content = (() => {
    if (page === "dashboard") {
      return (
        <DashboardPage
          openTrace={openTraceDrawer}
          dashboardData={dashboardData}
          loading={dashboardLoading}
          selectedProject={selectedProject}
          setPage={setPage}
          refresh={() => setToast("Telemetry refreshed from the selected project.")}
          toggleMode={() => setMode(mode === "dark" ? "light" : "dark")}
        />
      );
    }
    if (page === "traces") {
      return (
        <TracesPage
          rows={traceRows}
          overview={dashboardSources?.overview}
          loading={dashboardLoading}
          openTrace={openTraceDrawer}
          setSelectedTrace={setSelectedTrace}
          setPage={setPage}
        />
      );
    }
    if (page === "explorer") {
      return (
        <ExplorerPage
          trace={selectedTraceWithReplay}
          sloData={dashboardSources?.slos}
          loading={traceReplayLoading}
          error={traceReplayError}
          setPage={setPage}
        />
      );
    }
    if (page === "incidents") {
      return (
        <IncidentsPage
          rows={incidentRows}
          sloData={dashboardSources?.slos}
          loading={dashboardLoading}
          onAsk={openIncidentChat}
        />
      );
    }
    if (page === "slos") {
      return (
        <SloPage
          sloData={dashboardSources?.slos}
          loading={dashboardLoading}
          selectedProject={selectedProject}
          setToast={setToast}
          onSaveSlo={handleSaveSlo}
          onCreateSlo={handleCreateSlo}
          onDeleteSlo={handleDeleteSlo}
        />
      );
    }
    if (page === "governance") {
      return <GovernancePage governance={dashboardSources?.governance} loading={dashboardLoading} openGovernance={() => setGovernanceOpen(true)} />;
    }
    return (
      <CreateProjectPage
        setToast={setToast}
        selectedProject={selectedProject}
        lastSdkKey={lastSdkKey}
        onCreateProject={handleCreateProject}
        onGenerateKey={handleGenerateKey}
      />
    );
  })();

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <GlobalStyles
        styles={(muiTheme) => ({
          body: {
            backgroundColor: muiTheme.palette.background.default
          },
          "body::before": {
            background: muiTheme.palette.mode === "dark"
              ? "radial-gradient(circle at 20% -10%, rgba(65, 166, 255, 0.24), transparent 30%), radial-gradient(circle at 85% 10%, rgba(105, 230, 211, 0.16), transparent 28%)"
              : "radial-gradient(circle at 20% -10%, rgba(65, 166, 255, 0.18), transparent 30%), radial-gradient(circle at 85% 10%, rgba(105, 230, 211, 0.14), transparent 28%)"
          }
        })}
      />
     {!authed ? (
        authStarted ? (
          <AuthPage
            mode={authMode}
            setMode={setAuthMode}
            onEnter={handleAuth}
            colorMode={mode}
            setColorMode={setMode}
            error={authError}
            loading={authLoading}
            onBack={() => {
              setAuthError("");
              setAuthStarted(false);
            }}
          />
        ) : (
          <LandingPage
            colorMode={mode}
            setColorMode={setMode}
            onLogin={() => {
              setAuthMode("login");
              setAuthError("");
              setAuthStarted(true);
            }}
            onRegister={() => {
              setAuthMode("register");
              setAuthError("");
              setAuthStarted(true);
            }}
          />
        )
      ) : (
        <AppShell
          page={page}
          setPage={setPage}
          mode={mode}
          setMode={setMode}
          logout={handleLogout}
          refresh={() => setRefreshCount((count) => count + 1)}
          projects={projects}
          selectedProjectId={selectedProjectId}
          onProjectChange={selectProject}
          user={user}
        >
          {content}
        </AppShell>
      )}
      <TraceDrawer
        trace={traceDrawer}
        loading={traceReplayLoading && selectedTrace?.id === traceDrawer?.id}
        onClose={() => setTraceDrawer(null)}
      />
      <IncidentChatDialog
        incident={incidentChat}
        messages={incidentMessages}
        loading={incidentChatLoading}
        onSend={sendIncidentQuestion}
        onClose={() => setIncidentChat(null)}
      />
      <GovernanceDrawer open={governanceOpen} onClose={() => setGovernanceOpen(false)} />
      <Snackbar open={Boolean(toast)} autoHideDuration={2600} onClose={() => setToast("")}>
        <Alert severity="success" variant="filled" onClose={() => setToast("")}>{toast}</Alert>
      </Snackbar>
    </ThemeProvider>
  );
}
