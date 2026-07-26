# AgentSRE Backend

The backend is one FastAPI application containing authentication, projects, SDK ingestion, PostgreSQL persistence, metrics processing, SLO evaluation, incidents, governance, and dashboard APIs.

## Prerequisites

- Python 3.10 or newer
- Native PostgreSQL running locally or on a reachable server
- Kafka only when `KAFKA_ENABLED=true`

## Install and configure

Enter this `backend` directory before running the commands.

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with the PostgreSQL credentials. `POSTGRES_INGESTION_DATABASE` and `POSTGRES_METRICS_DATABASE` must have the same value. Set `KAFKA_ENABLED=false` when Kafka is unavailable.

To enable the Gemini groundedness judge and incident assistant, set:

```env
GEMINI_API_KEY=<your_gemini_key>
AGENTSRE_LLM_JUDGE_ENABLED=true
AGENTSRE_ASSISTANT_LLM_ENABLED=true
```

## Run

Run from inside `backend` with its virtual environment active.

PowerShell:

```powershell
python -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8081 --reload --reload-dir .
```

macOS/Linux:

```bash
python -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8081 --reload --reload-dir .
```

Open `http://localhost:8081/docs` or verify `http://localhost:8081/health`. The database schema and background metrics worker start automatically.
