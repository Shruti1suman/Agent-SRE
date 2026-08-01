# AgentSRE

AgentSRE is an observability, reliability, incident-analysis, SLO, and governance platform for production AI agents. A lightweight Python SDK captures agent telemetry, the unified FastAPI backend evaluates every run, and the React dashboard turns that evidence into traces, workflow graphs, health scores, incidents, reports, and audit views.

 ## Demo Link

[Click me to see the app!](https://agent-sre.vercel.app/)

## Contents

- [Why AgentSRE](#why-agentsre)
- [Implemented Capabilities](#implemented-capabilities)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Technology Stack](#technology-stack)
- [Quick Start](#quick-start)
- [Connect an Agent](#connect-an-agent)
- [SDK Development](#sdk-development)
- [Platform Concepts](#platform-concepts)
- [Demo Agents](#demo-agents)
- [API Surface](#api-surface)
- [Configuration](#configuration)
- [Future Scope](#future-scope)
- [Troubleshooting](#troubleshooting)

## Why AgentSRE

Conventional infrastructure monitoring can show that an application is slow or failing, but it usually cannot explain an agent's execution path. AgentSRE adds agent-aware evidence for questions such as:

- Which workflow node, model call, or tool caused a failure?
- Did the final answer have supporting tool or context evidence?
- Is latency, token usage, cost, or tool reliability outside the agent's normal baseline?
- Which SLO was breached, what was observed, and what threshold was configured?
- Did the workflow retry, repeat a tool call, or enter a loop?
- Was sensitive information redacted before telemetry left the agent process?
- What should an operator inspect or change to prevent the incident recurring?

## Implemented Capabilities

### Identity and Projects

- Email/password registration and login with persisted bearer sessions.
- User-owned projects and project-isolated dashboard data.
- Project-scoped SDK keys stored as hashes; the full generated key is shown once.
- Automatic routing to project creation for a new account with no projects.

### Data Collection SDK

- Python 3.10-3.13 package built on OpenTelemetry and OpenInference conventions.
- Automatic instrumentation for LangGraph, CrewAI, LangChain, OpenAI, Anthropic, Google GenAI, HTTP clients, and SQLAlchemy when the corresponding optional packages are installed.
- Canonical execution payloads containing execution metadata, resources, spans, parent-child relationships, timings, statuses, errors, model calls, tokens, tool calls, memory evidence, and HTTP activity.
- Configurable PII redaction before export for common sensitive values and application-defined field names.
- Batched HTTP export with idle-batch flushing and explicit shutdown support.

### Observability and Trace Analysis

- Project dashboard with execution count, success rate, estimated model cost, P90 latency, and agent health score.
- Latency, token, cost, model, and span visualizations with responsive tooltips.
- Trace table with status, timestamp, framework, duration, span count, model calls, and tool calls.
- Trace Explorer with an execution-oriented workflow graph and a raw span hierarchy view.
- Collapsed repeated workflow nodes, loop/retry highlighting, node focus, and timeline navigation.
- Full timeline with span metadata and captured inputs/outputs where instrumentation exposes them.

### Intelligence and Reliability

- Per-run latency, token, estimated cost, tool, step, retry, loop, repetition, and groundedness metrics.
- Model price matching for known Gemini and other supported model families with a documented fallback estimate.
- Per-agent running baselines using online statistics and configurable Z-score anomaly thresholds.
- Detection for failed runs, tool failures, repeated tool arguments, loops, latency anomalies, token/cost spikes, truncated responses, and unsupported output.
- Optional backend LLM groundedness judge with a local heuristic fallback.

### SLOs

- Four project defaults: execution success rate, trace latency, tool failure rate, and token budget.
- Editable threshold, operator, severity, and enabled state.
- Additional custom per-run SLOs selected by reliability category and metric.
- Custom metrics for model reliability, response quality, tool reliability, agent behavior, performance, cost, and quota signals.
- Automatic SLO evaluation for new runs and incident creation when an enabled rule breaches.
- Per-trace SLO evidence in Trace Explorer.

### Incidents and Reports

- Incident categorization by execution failure, tool reliability, loop/retry, latency, cost/tokens, groundedness, and SLO breach.
- Evidence containing the observed value and configured threshold when applicable.
- Incident-specific conversational assistant with persisted chat history.
- Detailed single-incident report covering identity, execution context, impact, evidence, RCA, diagnostics, remediation, prevention, and timeline.
- Downloadable PDF incident report without raw telemetry payloads.

### Governance

- Governance warnings derived from captured executions.
- Privacy and redaction evidence.
- Project and agent-scoped audit trail projections.
- Date/time filtering and replay-event visibility.

## Architecture

AgentSRE uses one unified backend process with clear internal module boundaries. The diagram represents the logical processing layers; Kafka publishing is optional, and the backend metrics worker can process persisted intelligence events directly.

```text
Customer AI agent
  |
  | agentsre-sdk: instrument, correlate, redact, batch
  v
POST /v1/executions
  |
  v
FastAPI ingestion service
  |-- validates SDK key and binds the authoritative project/tenant
  |-- stores raw, governance, and intelligence execution packages
  |-- optionally publishes governance/intelligence events to Kafka
  v
Background metrics worker
  |-- calculates metrics and estimated cost
  |-- evaluates groundedness, baselines, anomaly rules, and SLOs
  |-- persists trace evaluations and incidents
  v
PostgreSQL
  |
  v
FastAPI dashboard APIs
  |
  v
React + Material UI dashboard
```

### Processing Flow

1. A user creates an AgentSRE account and project.
2. The user generates a project SDK key.
3. The agent initializes `agentsre_sdk` before creating or invoking its framework objects.
4. Framework and provider instrumentors produce related spans.
5. The SDK redacts configured sensitive values and exports a canonical execution package.
6. The backend verifies the SDK key and overwrites project/tenant identifiers with the key's authoritative ownership.
7. Ingestion builds governance and intelligence projections and persists them.
8. The built-in background worker processes pending intelligence events.
9. Metrics, SLO results, baselines, incidents, and report evidence are stored.
10. The frontend loads only the project selected in the navigation bar.

### Persistence Model

The backend creates the configured PostgreSQL database and tables at startup when the PostgreSQL role has `CREATEDB` permission. Ingestion and metrics must use the same database because the worker queries both sets of tables together.

| Data | Primary tables |
|---|---|
| Users and sessions | `dashboard_users`, `dashboard_sessions` |
| Projects and SDK-key hashes | `dashboard_projects` |
| Raw and normalized executions | `executions`, `published_events` |
| Reliability evaluations | `trace_evaluations`, `agent_baseline_stats` |
| SLO definitions | `slo_configurations` |
| Incidents and assistant history | `incidents`, `incident_chat_messages` |

## Repository Structure

```text
AgentSRE/
|-- backend/                  Unified FastAPI application
|   |-- app/
|   |   |-- routes/           HTTP API boundaries
|   |   |-- services/         Ingestion, metrics, SLO, incident, and governance logic
|   |   `-- repositories/     PostgreSQL persistence and queries
|   |-- core/                 Environment settings and security helpers
|   |-- database/             PostgreSQL connection utilities
|   `-- models/               Pydantic request models
|-- frontend/                 React, Material UI, ECharts, and Vite application
|   |-- public/               Browser assets
|   `-- src/
|       |-- api/              Backend API clients
|       |-- components/       Shared layout, tables, charts, and controls
|       |-- mappers/          Backend-to-view data mapping
|       |-- pages/            Product pages
|       `-- utils/            Formatting and PDF report generation
|-- sdk/                      Installable agentsre-sdk Python package and tests
|-- retail_support/           Deterministic six-scenario demo agent
|-- retail_support2/          Equivalent demo using live Gemini calls
`-- README.md
```

## Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | React 18, Material UI 5, ECharts 6, Vite 5, jsPDF |
| Backend | Python, FastAPI, Pydantic 2, Uvicorn, HTTPX |
| Persistence | PostgreSQL, Psycopg 3 |
| Messaging | Kafka through `kafka-python` when enabled |
| SDK | OpenTelemetry SDK, OpenInference instrumentors, HTTPX |
| Testing | Pytest for the SDK, Python compilation checks, Vite production build |

## Quick Start

### Prerequisites

- Git
- Python 3.13 recommended for this repository; the SDK supports Python 3.10+
- Node.js 20.19+ (or 22.12+) and npm
- PostgreSQL available locally, normally on port `5432`
- Kafka on port `9092` only when `KAFKA_ENABLED=true`

Use separate Python virtual environments for the backend and instrumented agents. Agent framework/provider dependencies can otherwise conflict with FastAPI dependencies.

### 1. Get the repository

Clone with Git, or download and extract the GitHub ZIP. Then open a terminal in the repository root—the directory containing this `README.md`, `backend/`, `frontend/`, and `sdk/`.

PowerShell:

```powershell
git clone <repository-url>
cd AgentSRE
```

macOS/Linux:

```bash
git clone <repository-url>
cd AgentSRE
```

### 2. Install and run the backend

Enter the backend directory first.

PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` in the backend directory for your local PostgreSQL account. For the simplest setup without Kafka, set:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<postgres-password>
POSTGRES_DATABASE=sre_agent
POSTGRES_MAINTENANCE_DATABASE=postgres
POSTGRES_INGESTION_DATABASE=sre_agent
POSTGRES_METRICS_DATABASE=sre_agent
KAFKA_ENABLED=false
```

Start it while still inside `backend`:

```powershell
python -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8081 --reload --reload-dir .
```

macOS/Linux:

```bash
python -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8081 --reload --reload-dir .
```

The backend automatically ensures the database schema and starts the metrics worker. Verify it in another terminal.

PowerShell:

```powershell
Invoke-RestMethod http://localhost:8081/health
```

macOS/Linux:

```bash
curl --fail http://localhost:8081/health
```

Interactive API documentation is available at `http://localhost:8081/docs`.

### 3. Install and start the frontend

Open another terminal.

PowerShell:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

macOS/Linux:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`.

### 4. Create the first project

1. Select **Create account** on the landing page.
2. Register and sign in.
3. Create a project. The description is optional.
4. Select that project in the navigation bar.
5. Open **Create project** and select **Generate key** for the current project.
6. Store the displayed SDK key immediately; the full value is intentionally shown once.

## Connect an Agent

### Install the SDK

From the extracted or cloned repository root, install the bundled SDK. This works without depending on a branch or another remote repository:

```text
pip install -e "sdk[instrumentation]"
```

Install the agent's own framework and provider dependencies separately.

### Configure the agent

Create a `.env` in the agent's working directory:

```env
AGENTSRE_BACKEND_URL=http://localhost:8081/v1/executions
AGENTSRE_API_KEY=<generated-project-sdk-key>
AGENTSRE_TENANT_ID=<tenant-id>
AGENTSRE_PROJECT_ID=<project-id>
AGENTSRE_SERVICE_NAME=my-production-agent
AGENTSRE_ENVIRONMENT=dev
```

Provider credentials such as `GEMINI_API_KEY` remain in the agent environment and are used by the agent itself. AgentSRE does not require provider secrets to ingest telemetry.

### Initialize once

Initialize AgentSRE before creating clients or running the workflow:

```python
import agentsre_sdk


def initialize_sdk() -> None:
    agentsre_sdk.init(
        pii_redaction=True,
        sensitive_fields=["email", "phone", "ssn", "api_key"],
        instrument_langgraph=True,
        instrument_crewai=False,
    )
```

The required tenant, project, service, environment, backend URL, and SDK key are loaded from environment variables. Disable only adapters for frameworks the agent does not use.

Flush pending telemetry when a short-lived process exits:

```python
try:
    initialize_sdk()
    # Build and run the existing agent normally.
finally:
    agentsre_sdk.shutdown()
```

### Data boundary

The SDK captures data exposed by installed instrumentation: prompts and responses, token counts, model/provider metadata, tool arguments and outputs, errors, timing, memory/retrieval evidence, HTTP spans, graph nodes, and parent-child relationships. It does not calculate SLOs, incidents, RCA, governance decisions, or cost; those belong to the backend.

## SDK Development

The SDK source is in `sdk/agentsre_sdk/`, while `sdk/tests/` contains its regression suite. These tests are not included in the installed wheel and are not required by applications using AgentSRE. They are retained to validate SDK changes before publishing a new version.

The suite covers:

- SDK initialization, environment loading, tracer setup, and shutdown behavior.
- Canonical execution schemas and span-to-payload transformation.
- HTTP exporting, batching, retries, and failure handling.
- PII and configured sensitive-field redaction.
- Trace grouping, parent-child relationships, status propagation, token data, tool data, and error normalization.
- LangGraph, LangChain, CrewAI, and LiteLLM instrumentation behavior.

Install the development dependencies and run the suite from the repository root:

PowerShell:

```powershell
python -m venv .venv-sdk
.\.venv-sdk\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e "sdk[dev]"
pytest sdk\tests
```

macOS/Linux:

```bash
python3 -m venv .venv-sdk
source .venv-sdk/bin/activate
python -m pip install --upgrade pip
pip install -e "sdk[dev]"
pytest sdk/tests
```

### SDK package configuration

`sdk/pyproject.toml` is the SDK's Python package manifest. It defines:

- The `agentsre-sdk` package name, version, supported Python versions, metadata, and Hatchling build backend.
- Core runtime dependencies such as Pydantic, HTTPX, and OpenTelemetry.
- Optional dependency groups for HTTP, LangGraph, LangChain, OpenAI, LiteLLM, Anthropic, Gemini, and CrewAI instrumentation.
- Combined `instrumentation`/`all` extras and the `dev` dependencies used by the test suite.
- The `agentsre_sdk` source package included in generated wheels.
- Pytest discovery and asynchronous-test configuration.

This file is what allows commands such as `pip install -e "sdk[dev]"` and `pip install "agentsre-sdk[langgraph,langchain]"` to select the correct SDK capabilities without a separate SDK requirements file.

## Platform Concepts

### Trace and execution

One exported agent run becomes one execution/trace package. A trace can contain many spans: workflow roots, agent nodes, LLM calls, tools, memory operations, and HTTP calls. Therefore, span count is not execution count.

### Workflow graph and span hierarchy

- **Workflow** presents the user-facing sequence of agent/workflow nodes and summarizes child model/tool activity.
- **Span hierarchy** presents raw telemetry containment based on `span_id` and `parent_span_id`.
- The timeline remains the complete ordered span record even when repeated nodes are visually collapsed.

### Metrics and incidents

Each newly ingested execution is evaluated by the background worker. Incidents can come from deterministic rules, project SLO breaches, baseline deviations, or groundedness judging. A single failed run can legitimately create separate incidents when it breaches independent reliability concerns, such as run failure and tool-failure SLO.

Estimated model cost uses captured prompt/completion tokens and the backend model-price table. Unknown models use the configured fallback calculation; these values are estimates rather than provider invoices.

### Agent health score

The dashboard health score summarizes the selected project's evaluated executions:

```text
health = round((
  success-rate score       * 0.40 +
  latency-compliance score * 0.30 +
  loop-risk score          * 0.15 +
  governance score         * 0.15
) * 100)
```

- Success score: successful executions divided by executions.
- Latency score: runs within the active trace-latency SLO divided by runs with latency data.
- Loop score: `1 - loop-risk executions / executions`.
- Governance score: `1 - governance warnings / executions`.
- `90-100`: Healthy, `70-89`: Degraded, `0-69`: Critical.

The component scores are clamped to `0-100`.

### SLO behavior

Predefined SLOs are created for every project:

| SLO | Default condition | Default severity |
|---|---:|---|
| Execution success rate | at least 99% | Critical |
| Trace latency | at most 1,800 ms | Warning |
| Tool failure rate | at most 25% | Critical |
| Token budget | at most 12,000 tokens | Warning |

Custom SLOs are independent per-run rules. Metrics already represented by predefined SLOs are excluded from the custom selector. Saving or creating an SLO affects subsequent evaluations; historical traces are not automatically reprocessed.

### Groundedness judge and incident assistant

These backend features use backend-side credentials, never credentials captured from an agent environment. Add optional settings to `backend/.env`:

```env
AGENTSRE_LLM_JUDGE_ENABLED=true
AGENTSRE_LLM_JUDGE_API_KEY=<provider-key>
GEMINI_API_KEY=<gemini-api-key>
AGENTSRE_LLM_JUDGE_MODEL=gemini-2.5-flash

AGENTSRE_ASSISTANT_LLM_ENABLED=true
AGENTSRE_ASSISTANT_LLM_API_KEY=<provider-key>
AGENTSRE_ASSISTANT_LLM_MODEL=gemini-2.5-flash
```

If the groundedness provider is disabled, unavailable, or returns an invalid response, the backend uses its local heuristic judge. Restart the backend after changing settings. Previously processed traces are not re-evaluated automatically.

## Demo Agents

Two retail-support demos exercise the same workflow under six operating conditions:

```text
ClassifyRequest -> RetrieveOrder -> EvaluateRefundPolicy -> ComposeResponse
```

### Deterministic demo

`retail_support/` uses a synthetic deterministic chat model for stable, repeatable demonstrations without paid model calls.

```powershell
python -m venv .venv-agent
.\.venv-agent\Scripts\Activate.ps1
Copy-Item retail_support\.env.example retail_support\.env
cd retail_support
pip install -r requirements.txt
python agent_healthy.py
python agent_tool_failure.py
python agent_retry_loop.py
python agent_latency_spike.py
python agent_token_spike.py
python agent_unsupported_answer.py
```

macOS/Linux:

```bash
python3 -m venv .venv-agent
source .venv-agent/bin/activate
cp retail_support/.env.example retail_support/.env
cd retail_support
pip install -r requirements.txt
python agent_healthy.py
python agent_tool_failure.py
python agent_retry_loop.py
python agent_latency_spike.py
python agent_token_spike.py
python agent_unsupported_answer.py
```

Keep one `AGENTSRE_SERVICE_NAME` across scenarios so AgentSRE builds and compares one agent baseline.

### Live-model demo

`retail_support2/` uses `ChatGoogleGenerativeAI` and requires `GEMINI_API_KEY`. It makes live Gemini calls and its latency, output, and token use are naturally variable.

```powershell
Copy-Item retail_support2\.env.example retail_support2\.env
cd retail_support2
pip install -r requirements.txt
python agent_healthy.py
```

macOS/Linux, from the repository root with the agent environment active:

```bash
cp retail_support2/.env.example retail_support2/.env
cd retail_support2
pip install -r requirements.txt
python agent_healthy.py
```

## API Surface

| Area | Main endpoints |
|---|---|
| Health | `GET /health` |
| Authentication | `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Projects | `GET/POST /api/projects`, `POST /api/projects/{project_id}/keys` |
| SDK ingestion | `POST /v1/executions`, `POST /v1/executions/transform` |
| Dashboard and traces | `/api/overview`, `/api/dashboard`, `/api/traces`, `/api/traces/{id}/replay`, `/api/metrics` |
| Incidents | `/api/incidents`, `/api/incidents/{id}/report`, `/api/incidents/{id}/chat`, `/api/incidents/{id}/ask` |
| SLOs | `GET/POST /api/slos`, `PATCH/DELETE /api/slos/{id}`, `GET /api/slos/metrics/catalog` |
| Governance | `/api/governance/overview`, `/executions`, `/warnings`, `/privacy`, `/audit-actions` |

Dashboard APIs require a user bearer session. SDK ingestion requires the project SDK key as `Authorization: Bearer <key>`.

## Configuration

### Backend settings

The backend loads `backend/.env`.

| Setting | Purpose | Default |
|---|---|---|
| `POSTGRES_HOST`, `POSTGRES_PORT` | PostgreSQL server | `localhost`, `5432` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL credentials | `postgres`, empty |
| `POSTGRES_DATABASE` | Application database | `sre_agent` |
| `POSTGRES_MAINTENANCE_DATABASE` | Existing database used to create the application database | `postgres` |
| `POSTGRES_INGESTION_DATABASE` | Execution storage database; must equal metrics database | value of `POSTGRES_DATABASE` |
| `POSTGRES_METRICS_DATABASE` | Dashboard/metrics database; must equal ingestion database | value of `POSTGRES_DATABASE` |
| `KAFKA_ENABLED` | Publish normalized events to Kafka | `false` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | `localhost:9092` |
| `AGENTSRE_METRICS_WORKER_ENABLED` | Automatic evaluation worker | `true` |
| `AGENTSRE_METRICS_WORKER_INTERVAL_SECONDS` | Worker polling cadence | `3` |
| `AGENTSRE_METRICS_WORKER_BATCH_SIZE` | Events processed per cycle | `100` |
| `AGENTSRE_BASELINE_MIN_SAMPLES` | Samples before baseline anomalies | `5` |
| `AGENTSRE_ANOMALY_Z_THRESHOLD` | Baseline deviation threshold | `2.5` |
| `AGENTSRE_CORS_ORIGINS` | Allowed frontend origins | `*` |
| `AGENTSRE_SESSION_TTL_DAYS` | Login session lifetime | `14` |

### Frontend settings

`frontend/.env.local` needs one value:

```env
VITE_API_BASE_URL=http://localhost:8081
```

Vite reads this file at startup; restart `npm run dev` after changing it.

### Kafka

Kafka is an optional downstream publication path in the unified local architecture. When enabled, the backend publishes to:

- `intelligence.execution.trace`
- `governance.execution.full`

Set `KAFKA_ENABLED=false` when Kafka is not available. The built-in metrics worker processes persisted intelligence events directly.

## Future Scope

The product roadmap extends the existing Python, FastAPI, React, OpenTelemetry, Kafka, and PostgreSQL architecture in focused operational areas:

- Rolling SLO windows with P95/P99 objectives, error budgets, and burn-rate evaluation.
- Real-time dashboard updates through Server-Sent Events and agent/model/workflow filtering.
- Notification connectors for email, Slack, PagerDuty, and OpsGenie.
- Scheduled weekly reliability reports generated from existing execution, SLO, and incident evidence.
- OTLP export for forwarding AgentSRE traces to established observability backends.
- SDK control policies for configurable loop termination, execution circuit breaking, and safe model fallback.
- Governance review state, retention policies, and downloadable evidence bundles.

## Troubleshooting

### SDK receives `404 Not Found`

Ensure the agent uses the ingestion endpoint, including `/v1/executions`:

```env
AGENTSRE_BACKEND_URL=http://localhost:8081/v1/executions
```

### SDK receives `401 Unauthorized`

Generate a key for the project selected in the dashboard and update `AGENTSRE_API_KEY`. Keys belong to one project; generating a replacement invalidates the previous key.

### Frontend shows no data

- Verify `VITE_API_BASE_URL` matches the backend port.
- Restart Vite after changing `.env.local`.
- Select the same project whose SDK key the agent uses.
- Wait for the background worker interval, then refresh.

### Backend cannot connect to PostgreSQL

- Confirm PostgreSQL is running and accepts the configured host/port/user/password.
- Ensure the role has `CREATEDB`, or create `POSTGRES_DATABASE` manually before starting the backend.
- Check `GET /health` after restarting the backend.

### Port already in use

Choose another backend port and update both `frontend/.env.local` and every agent's `AGENTSRE_BACKEND_URL`. The frontend defaults to port `3000`; change `frontend/vite.config.js` or start Vite with a port override when needed.

### PowerShell blocks scripts

Use the direct Python/npm commands in this README, or temporarily allow scripts for the current shell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
