# Retail Support Live LLM Demo Agent

This directory contains six standalone versions of the same realistic retail customer-support agent. Unlike `retail_support`, every model operation here calls a real Gemini model through `ChatGoogleGenerativeAI`. The workflow, tools, state, retries, and failures remain ordinary LangGraph/LangChain application behavior; only the runtime scenario differs between files.

The agent handles a refund inquiry through the same workflow every time:

```text
ClassifyRequest
-> RetrieveOrder
-> EvaluateRefundPolicy
-> ComposeResponse
```

Each agent file loads the same `.env` and calls `agentsre_sdk.init(...)` directly. Keeping `AGENTSRE_SERVICE_NAME` unchanged makes dashboard latency, token, reliability, health, SLO, and incident changes directly comparable.

## What This Agent Does

This is a retail customer-support agent that answers a customer's refund-eligibility question for a delivered product. The sample customer asks whether delivered wireless headphones can be returned for a refund.

The agent works with two sources of business evidence:

- **Order data:** order `ORD-1048`, its delivery status, delivery age, item, customer, and amount.
- **Refund policy:** a 14-day return window, required product inspection, and no automatic refund approval.

The workflow performs four tasks:

1. **ClassifyRequest:** identifies the request as a refund inquiry and determines which evidence is required.
2. **RetrieveOrder:** calls `order_lookup` to retrieve the customer's order and delivery information.
3. **EvaluateRefundPolicy:** calls `refund_policy_lookup` to check the applicable return conditions.
4. **ComposeResponse:** produces a customer-facing answer from the captured order and policy evidence.

During the run, AgentSRE's framework instrumentation automatically captures the existing LangGraph nodes, LangChain model operations, tool arguments and results, duration, token usage, status, and errors. The agent does not create spans or set `agentsre.*` attributes itself. The backend then evaluates the captured telemetry for SLO breaches, tool failures, loops, latency anomalies, excessive tokens, and unsupported answers.

## Integration Boundary

In a real customer project, the business agent already exists. The only AgentSRE-specific integration is:

```python
import agentsre_sdk

agentsre_sdk.init(
    tenant_id=os.getenv("AGENTSRE_TENANT_ID"),
    project_id=os.getenv("AGENTSRE_PROJECT_ID"),
    service_name=os.getenv("AGENTSRE_SERVICE_NAME"),
    environment=os.getenv("AGENTSRE_ENVIRONMENT", "demo"),
    api_key=os.getenv("AGENTSRE_API_KEY"),
    instrument_langgraph=True,
    instrument_crewai=False,
)
```

`instrument_crewai=False` simply disables an unused framework adapter because this agent uses LangGraph. It does not change the agent's behavior. Everything else in these files is normal retail-support application code.

All six files represent the same agent and business task. Only the operating condition changes, allowing the demo to show how one production agent moves from healthy behavior to specific reliability incidents.

## Configure Once

Edit `retail_support2/.env` and paste values from the selected AgentSRE project and Google AI Studio:

```env
AGENTSRE_BACKEND_URL=http://localhost:8081/v1/executions
AGENTSRE_API_KEY=<generated_sdk_key>
AGENTSRE_TENANT_ID=<tenant_id>
AGENTSRE_PROJECT_ID=<project_id>
AGENTSRE_SERVICE_NAME=retail-support-agent-live
AGENTSRE_ENVIRONMENT=demo
GEMINI_API_KEY=<gemini_api_key>
GEMINI_MODEL=gemini-2.5-flash
```

Do not change `AGENTSRE_SERVICE_NAME` between scenarios. Keeping it fixed lets AgentSRE establish one baseline and compare later runs against the same agent.

## Install

Enter `retail_support2` first and use a separate virtual environment.

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

All scenarios use the real model selected by `GEMINI_MODEL`. Outputs, latency, and token usage therefore come from Gemini and may vary slightly between runs. Calls may consume paid quota. The token-spike scenario sends roughly 18,000 tokens of real input context and should only be run when that cost is acceptable.

## Run

Stay inside `retail_support2`. Every standalone agent loads `.env` from this directory.

Run each command below and wait a few seconds for the backend metrics worker before refreshing the dashboard.

First verify that the backend configured in `retail_support2/.env` is running:

```powershell
Invoke-RestMethod http://localhost:8081/health
```

macOS/Linux:

```bash
curl --fail http://localhost:8081/health
```

If it is not running, follow `backend/README.md` in a separate terminal.

## Recommended Demo Order

### 1. Establish a healthy baseline

```powershell
python agent_healthy.py
```

Creates one successful, low-latency, low-token execution. Expected result: a healthy run with no intentional incident.

### 2. Tool failure

```powershell
python agent_tool_failure.py
```

The order service returns HTTP 503. Expected signals: failed execution, tool failure, and tool-failure SLO breach.

### 3. Retry loop

```powershell
python agent_retry_loop.py
```

The same order lookup is repeated four times with identical arguments. Expected signal: loop/retry incident.

### 4. Latency spike

```powershell
python agent_latency_spike.py
```

The order dependency takes more than 2.3 seconds. Expected signals: latency SLO breach and visible dashboard latency spike.

### 5. Token spike

```powershell
python agent_token_spike.py
```

The request sends genuinely oversized context. Expected signals: token-budget breach, cost increase, and taller token/cost bars. Actual usage is determined by the selected model tokenizer.

### 6. Unsupported answer

```powershell
python agent_unsupported_answer.py
```

The agent guarantees refund approval without supporting evidence. Expected signal: groundedness or hallucination-risk incident.

## Project Structure

```text
retail_support2/
  .env                         One fixed service and project configuration
  .env.example
  requirements.txt
  agent_healthy.py             Complete healthy agent run
  agent_tool_failure.py        Complete agent with a tool outage
  agent_retry_loop.py          Complete agent with repeated tool calls
  agent_latency_spike.py       Complete agent with slow dependency latency
  agent_token_spike.py         Complete agent with excessive token usage
  agent_unsupported_answer.py  Complete agent with an unsupported answer
```
