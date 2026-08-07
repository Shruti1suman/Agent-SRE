import Card from "@mui/material/Card";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import { useState } from "react";
import PageHeader from "../components/PageHeader";

export default function CreateProjectPage({ setToast, selectedProject, lastSdkKey, onCreateProject, onGenerateKey }) {
  const [projectName, setProjectName] = useState("");
  const [description, setDescription] = useState("");
  const [keyName, setKeyName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const project = selectedProject || {};
  const key = lastSdkKey || (project.sdk_key_preview ? `********${project.sdk_key_preview}` : "<generate_key_first>");

  const handleCreate = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onCreateProject({ projectName, description });
      setToast("Project created with project-level isolation.");
      setProjectName("");
      setDescription("");
    } catch (error) {
      setToast(error.message || "Unable to create project.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleGenerate = async () => {
    setSubmitting(true);
    try {
      await onGenerateKey({ keyName });
      setToast("Generated SDK key shown once.");
      setKeyName("");
    } catch (error) {
      setToast(error.message || "Unable to generate SDK key.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHeader title="Create project" />
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ p: 2 }}>
            <Stack component="form" spacing={2} onSubmit={handleCreate}>
              <TextField
                label="Project name"
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                required
              />
              <TextField
                label="Description"
                multiline
                rows={5}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              <Button type="submit" variant="contained" disabled={submitting || !projectName.trim()}>{submitting ? "Working..." : "Create project"}</Button>
            </Stack>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Project API keys and SDK instructions</Typography>
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25} alignItems={{ sm: "stretch" }}>
                <TextField
                  label="Key name"
                  placeholder="local-dev-sdk"
                  value={keyName}
                  onChange={(event) => setKeyName(event.target.value)}
                  fullWidth
                />
                <Button variant="contained" onClick={handleGenerate} disabled={!project.project_id || submitting} sx={{ minWidth: 150 }}>
                  Generate key
                </Button>
              </Stack>
              <Alert severity={lastSdkKey ? "success" : "info"}>
                {lastSdkKey ? (
                  <Stack spacing={0.7}>
                    <Typography variant="body2">SDK key generated. Copy it now; the full key is shown only once.</Typography>
                    <Typography
                      component="code"
                      sx={{
                        display: "block",
                        fontFamily: '"Cascadia Mono", Consolas, monospace',
                        fontSize: 12.5,
                        fontWeight: 650,
                        overflowWrap: "anywhere",
                        userSelect: "all",
                      }}
                    >
                      {lastSdkKey}
                    </Typography>
                  </Stack>
                ) : project.project_id ? (
                  "Generate an SDK key when you are ready to connect an agent. The full key is shown once."
                ) : (
                  "Create or select a project before generating an SDK key."
                )}
              </Alert>
              <Card variant="outlined" sx={{ p: 2, bgcolor: (theme) => theme.palette.mode === "dark" ? "#071019" : "#10202d", color: "#b7fff4", overflow: "auto" }}>
                <Typography component="pre" sx={{ m: 0, fontFamily: '"Cascadia Mono", Consolas, monospace', fontSize: 12, lineHeight: 1.55 }}>{`# Save these values in your agent project's .env
AGENTSRE_BACKEND_URL=http://localhost:8081/v1/executions
AGENTSRE_API_KEY=${key}
AGENTSRE_TENANT_ID=${project.tenant_id || "<tenant_id>"}
AGENTSRE_PROJECT_ID=${project.project_id || "<create_project_first>"}
AGENTSRE_SERVICE_NAME=example-agent
AGENTSRE_ENVIRONMENT=dev

# Your agent's model-provider key, when applicable
GEMINI_API_KEY=<your_gemini_key>

pip install "agentsre-sdk[instrumentation] @ git+https://github.com/Shruti1suman/Agent-SRE.git#subdirectory=sdk"

import agentsre_sdk
import os

agentsre_sdk.init(
    tenant_id=os.getenv("AGENTSRE_TENANT_ID"),
    project_id=os.getenv("AGENTSRE_PROJECT_ID"),
    service_name=os.getenv("AGENTSRE_SERVICE_NAME"),
    environment=os.getenv("AGENTSRE_ENVIRONMENT", "dev"),
    api_key=os.getenv("AGENTSRE_API_KEY"),
    pii_redaction=True,
    sensitive_fields=["email", "phone", "ssn", "api_key"],
    instrument_langgraph=True,
)`}</Typography>
              </Card>
            </Stack>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
