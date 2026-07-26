from __future__ import annotations

import json
from typing import Any

from backend.app.repositories.dashboard_repository import DashboardRepository
from backend.app.services.gemini_api import gemini_contents, generate_text
from backend.core.settings import settings


class IncidentChatService:
    def __init__(self) -> None:
        self.repository = DashboardRepository()

    def history(self, incident_id: str, user_id: str) -> dict[str, Any]:
        incident = self.repository.incident_by_id(incident_id)
        if not incident or "error" in incident:
            return {"messages": [], "context": {}, "suggested_questions": []}
        messages = normalize_messages(self.repository.incident_chat_messages(incident_id, user_id))
        return {
            "messages": messages,
            "context": {
                "incident_id": incident.get("incident_id"),
                "trace_id": incident.get("trace_id"),
                "rule_id": incident.get("rule_id"),
                "severity": incident.get("severity"),
                "category": incident.get("category"),
                "agent_id": incident.get("agent_id"),
            },
            "suggested_questions": suggested_questions({}),
        }

    def answer(
        self,
        incident_id: str,
        message: str,
        history: list[dict[str, str]] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        incident = self.repository.incident_by_id(incident_id)
        if not incident or "error" in incident:
            return {
                "answer": "I could not find that incident in the selected backend data.",
                "context": {},
                "suggested_questions": [],
            }

        stored_history = normalize_messages(self.repository.incident_chat_messages(incident_id, user_id)) if user_id else []
        active_history = stored_history or (history or [])
        metric = self.repository.metric_detail(incident.get("trace_id"))
        trace = self.repository.trace_by_trace_id(incident.get("trace_id"))
        replay = self.repository.replay_from_trace(trace) if trace and "error" not in trace else {}
        context = build_incident_context(incident, metric, replay)
        if user_id and message:
            self.repository.append_incident_chat_message(incident_id, user_id, "user", message)
            active_history = [*active_history, {"role": "user", "content": message}]
        answer = conversational_answer(context, message or "", active_history)
        if user_id:
            self.repository.append_incident_chat_message(incident_id, user_id, "assistant", answer)
        messages = normalize_messages(self.repository.incident_chat_messages(incident_id, user_id)) if user_id else []
        return {
            "answer": answer,
            "messages": messages,
            "context": {
                "incident_id": incident.get("incident_id"),
                "trace_id": incident.get("trace_id"),
                "rule_id": incident.get("rule_id"),
                "severity": incident.get("severity"),
                "category": incident.get("category"),
                "agent_id": incident.get("agent_id"),
            },
            "suggested_questions": suggested_questions(context),
        }


def normalize_messages(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages = []
    for row in rows or []:
        if "error" in row:
            continue
        role = "assistant" if row.get("role") == "assistant" else "user"
        content = str(row.get("content") or "").strip()
        if content:
            messages.append({"role": role, "content": content})
    return messages


def conversational_answer(context: dict[str, Any], message: str, history: list[dict[str, str]]) -> str:
    if settings.assistant_llm_enabled and settings.assistant_llm_api_key:
        try:
            return llm_answer(context, message, history)
        except Exception as exc:
            fallback = compose_answer(context, message)
            return (
                f"I tried to use the LLM assistant, but the call failed, so I answered from local incident context.\n\n"
                f"{fallback}\n\n"
                f"LLM error: {exc}"
            )
    if settings.assistant_llm_enabled and not settings.assistant_llm_api_key:
        return (
            "The LLM assistant is enabled, but no API key is available to the backend. "
            "Set `AGENTSRE_ASSISTANT_LLM_API_KEY` or `GEMINI_API_KEY` in `backend/.env`, then restart the backend.\n\n"
            f"{compose_answer(context, message)}"
        )
    return conversational_fallback(context, message, history)


def llm_answer(context: dict[str, Any], message: str, history: list[dict[str, str]]) -> str:
    payload = assistant_context_payload(context)
    system_instruction = (
                "You are AgentSRE Assistant, an incident-scoped SRE copilot for AI agent runs. "
                "Answer the user's exact question conversationally and directly. "
                "Use only the provided incident context, trace metrics, SLO results, spans, LLM payload previews, "
                "tool payloads, and groundedness judgements. Do not invent spans, IDs, metrics, payloads, or logs. "
                "If the user asks for code, provide concrete, production-minded code snippets or pseudocode that would "
                "fix this class of issue in their agent, SDK integration, prompts, retry policy, guardrails, or tool wrapper. "
                "If exact repository code is unavailable in the incident context, say that and give an adaptable snippet. "
                "Prefer short sections: Diagnosis, Evidence, Fix, Code suggestion, Next check. "
                "For casual text, respond naturally but keep the conversation scoped to this incident."
            )
    messages = [
        {
            "role": "user",
            "content": (
                "Incident context JSON:\n"
                f"{json.dumps(payload, indent=2, default=str)}"
            ),
        },
    ]
    for item in history[-8:]:
        role = "assistant" if item.get("role") == "assistant" else "user"
        content = str(item.get("content") or "").strip()
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    return generate_text(
        api_base_url=settings.assistant_llm_api_url,
        api_key=settings.assistant_llm_api_key,
        model=settings.assistant_llm_model,
        system_instruction=system_instruction,
        contents=gemini_contents(messages),
        timeout_seconds=settings.assistant_llm_timeout_seconds,
        generation_config={"temperature": 0.25, "maxOutputTokens": 900},
    )


def conversational_fallback(context: dict[str, Any], message: str, history: list[dict[str, str]]) -> str:
    lowered = message.lower().strip()
    prefix = ""
    if history:
        prefix = "Continuing from this incident context: "
    if any(word in lowered for word in ["hello", "hi", "hey"]):
        return (
            "Hi. I am looking at this incident's RCA, trace metrics, SLO results, spans, LLM payloads, and tool payloads. "
            "Ask me what happened, which span caused it, how to fix it, or ask for a code-level patch idea."
        )
    if any(word in lowered for word in ["code", "snippet", "patch", "implementation", "python", "langgraph"]):
        return code_suggestion_answer(context)
    if any(word in lowered for word in ["what can you do", "help", "explain"]):
        return (
            "I can read this incident's rule, trace metrics, SLO results, groundedness judgement, failed tools, "
            "and replay spans. I will stay scoped to this incident so the answer does not drift into unrelated runs."
        )
    return prefix + compose_answer(context, message)


def assistant_context_payload(context: dict[str, Any]) -> dict[str, Any]:
    incident = context["incident"]
    metric = context["metric"]
    return {
        "incident": {
            "incident_id": incident.get("incident_id"),
            "trace_id": incident.get("trace_id"),
            "agent_id": incident.get("agent_id"),
            "project_id": incident.get("project_id"),
            "rule_id": incident.get("rule_id"),
            "category": incident.get("category"),
            "severity": incident.get("severity"),
            "metric_name": incident.get("metric_name"),
            "observed_value": incident.get("observed_value"),
            "z_score": incident.get("z_score"),
            "threshold_value": incident.get("threshold_value"),
            "triggered_by": incident.get("triggered_by"),
            "rca_text": incident.get("rca_text"),
            "suggestion_text": incident.get("suggestion_text"),
        },
        "trace_metrics": {
            "status": metric.get("trace_status"),
            "duration_ms": metric.get("total_duration_ms"),
            "tokens": metric.get("total_tokens"),
            "cost_usd": metric.get("total_cost_usd"),
            "tool_failure_rate": metric.get("tool_failure_rate"),
            "grounded_response_rate": metric.get("grounded_response_rate"),
            "slo_status": metric.get("slo_status"),
        },
        "slo_breaches": context["slo_breaches"][:6],
        "groundedness_judgements": context["groundedness"][:6],
        "failed_tools": context["failed_tools"][:6],
        "timeline": context["timeline"][:12],
        "llm_calls": context["llm_calls"][:6],
        "intelligence_steps": context["steps"][:8],
        "tool_calls": context["tool_calls"][:8],
        "failed_timeline": context["failed_timeline"][:6],
    }


def build_incident_context(incident: dict[str, Any], metric: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    metric = metric if isinstance(metric, dict) and "error" not in metric else {}
    replay = replay if isinstance(replay, dict) else {}
    steps = replay.get("intelligence_steps") or []
    llm_calls = replay.get("llm_calls") or []
    tool_calls = replay.get("tool_calls") or []
    timeline = replay.get("timeline") or []
    slo_breaches = metric.get("slo_breaches") or []
    groundedness = metric.get("groundedness_judgements") or []
    return {
        "incident": incident,
        "metric": metric,
        "steps": steps,
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "timeline": timeline,
        "slo_breaches": slo_breaches,
        "groundedness": groundedness,
        "failed_tools": [
            tool for tool in tool_calls
            if str(tool.get("status") or "").upper() in {"ERROR", "FAILED", "FAILURE"}
        ],
        "failed_timeline": [
            item for item in timeline
            if str(item.get("status_code") or "").upper() in {"ERROR", "FAILED", "FAILURE"}
        ],
    }


def compose_answer(context: dict[str, Any], message: str) -> str:
    lowered = message.lower()
    if any(word in lowered for word in ["fix", "solve", "remediate", "recommend", "action"]):
        return fix_answer(context)
    if any(word in lowered for word in ["span", "input", "output", "payload", "model"]):
        return span_answer(context)
    if any(word in lowered for word in ["slo", "breach", "threshold", "target"]):
        return slo_answer(context)
    if any(word in lowered for word in ["why", "root", "cause", "reason", "rca"]):
        return rca_answer(context)
    return summary_answer(context)


def summary_answer(context: dict[str, Any]) -> str:
    incident = context["incident"]
    metric = context["metric"]
    lines = [
        f"This incident is `{incident.get('rule_id')}` on trace `{short_id(incident.get('trace_id'))}`.",
        f"Severity is `{incident.get('severity')}` and category is `{incident.get('category')}`.",
        f"Root cause: {incident.get('rca_text') or 'No RCA text was captured.'}",
        f"Recommended fix: {incident.get('suggestion_text') or 'Inspect trace replay and related spans.'}",
    ]
    evidence = evidence_line(incident)
    if evidence:
        lines.append(f"Evidence: {evidence}")
    if metric:
        lines.append(
            "Trace metrics: "
            f"status `{metric.get('trace_status')}`, "
            f"duration `{format_ms(metric.get('total_duration_ms'))}`, "
            f"tokens `{metric.get('total_tokens') or 0}`, "
            f"cost `${float(metric.get('total_cost_usd') or 0):.6f}`."
        )
    return "\n".join(lines)


def rca_answer(context: dict[str, Any]) -> str:
    incident = context["incident"]
    lines = [incident.get("rca_text") or "No RCA text was captured for this incident."]
    evidence = evidence_line(incident)
    if evidence:
        lines.append(f"The detector fired from: {evidence}.")
    if context["failed_tools"]:
        names = ", ".join(unique(tool.get("tool_name") for tool in context["failed_tools"]))
        lines.append(f"Failed tool signal: {names}.")
    if context["groundedness"]:
        bad = [
            item for item in context["groundedness"]
            if str(item.get("verdict") or "").lower() == "ungrounded"
        ]
        if bad:
            lines.append(f"Groundedness judge found {len(bad)} unsupported LLM step(s).")
    return "\n".join(lines)


def fix_answer(context: dict[str, Any]) -> str:
    incident = context["incident"]
    rule = str(incident.get("rule_id") or "").upper()
    category = str(incident.get("category") or "").lower()
    lines = [incident.get("suggestion_text") or "Inspect trace replay and related metrics."]
    if "HS" in rule or "hallucination" in category:
        lines.extend([
            "Add a final evidence check before the agent answers.",
            "Require the agent to cite retrieved/tool evidence or say that evidence is missing.",
        ])
    elif "TF" in rule or "tool" in category:
        lines.extend([
            "Check credentials, dependency health, timeout limits, and retry policy for the failing tool.",
            "Add fallback handling so the agent can stop cleanly instead of continuing with bad context.",
        ])
    elif "LD" in rule or "loop" in category:
        lines.extend([
            "Add a max-iteration guard and short-circuit repeated tool arguments.",
            "Log planner decisions so repeated routes are visible in trace explorer.",
        ])
    elif "CO" in rule or "TOK" in rule or "cost" in category:
        lines.extend([
            "Cap retrieved context and completion length.",
            "Summarize intermediate state instead of passing full history on every step.",
        ])
    elif "LAT" in rule or "latency" in category:
        lines.extend([
            "Open the trace replay and sort spans by duration.",
            "Check external API calls, retries, and slow LLM/tool spans first.",
        ])
    return "\n".join(f"- {line}" for line in lines if line)


def code_suggestion_answer(context: dict[str, Any]) -> str:
    incident = context["incident"]
    rule = str(incident.get("rule_id") or "").upper()
    category = str(incident.get("category") or "").lower()
    if "HS" in rule or "hallucination" in category:
        return (
            "Here is an adaptable guardrail pattern for this hallucination/groundedness incident:\n\n"
            "```python\n"
            "def require_evidence_before_answer(answer: str, evidence: list[str]) -> str:\n"
            "    if not evidence:\n"
            "        return \"I do not have enough verified evidence to answer this safely.\"\n"
            "    unsupported_terms = [term for term in [\"guaranteed\", \"official\", \"secret\"] if term in answer.lower()]\n"
            "    if unsupported_terms:\n"
            "        return \"I found an unsupported claim. Please retrieve or cite evidence before finalizing.\"\n"
            "    return answer\n"
            "```\n\n"
            "Place this immediately before the final response node/tool returns output to the user."
        )
    if "TF" in rule or "tool" in category:
        return (
            "Here is a safer tool wrapper for this tool-failure incident:\n\n"
            "```python\n"
            "def call_tool_with_retries(tool_fn, payload, retries=2):\n"
            "    last_error = None\n"
            "    for attempt in range(retries + 1):\n"
            "        try:\n"
            "            return {\"ok\": True, \"result\": tool_fn(**payload), \"attempt\": attempt + 1}\n"
            "        except Exception as exc:\n"
            "            last_error = exc\n"
            "    return {\"ok\": False, \"error\": str(last_error), \"fallback\": \"Tool unavailable. Ask user or stop safely.\"}\n"
            "```\n\n"
            "Log the failed tool name, arguments, and final error so AgentSRE can show a precise RCA."
        )
    if "LD" in rule or "loop" in category:
        return (
            "Here is a loop guard for repeated tool arguments:\n\n"
            "```python\n"
            "seen_tool_calls = set()\n\n"
            "def should_call_tool(tool_name: str, arguments: dict, max_repeats=1) -> bool:\n"
            "    signature = (tool_name, tuple(sorted(arguments.items())))\n"
            "    if signature in seen_tool_calls:\n"
            "        return False\n"
            "    seen_tool_calls.add(signature)\n"
            "    return True\n"
            "```\n\n"
            "Use this in the planner/router before invoking the same tool with the same arguments again."
        )
    if "CO" in rule or "TOK" in rule or "cost" in category:
        return (
            "Here is a token-budget guard for cost/token incidents:\n\n"
            "```python\n"
            "def trim_context(chunks: list[str], max_chars=6000) -> str:\n"
            "    selected = []\n"
            "    used = 0\n"
            "    for chunk in chunks:\n"
            "        if used + len(chunk) > max_chars:\n"
            "            break\n"
            "        selected.append(chunk)\n"
            "        used += len(chunk)\n"
            "    return \"\\n\\n\".join(selected)\n"
            "```\n\n"
            "Apply this before the LLM call and record prompt/completion tokens in telemetry."
        )
    return (
        "I do not have repository source for the user's agent in this incident context, but here is the general patch shape:\n\n"
        "```python\n"
        "try:\n"
        "    result = run_agent_step(state)\n"
        "except Exception as exc:\n"
        "    logger.exception(\"agent step failed\", extra={\"step\": step_name})\n"
        "    return {**state, \"error\": str(exc), \"should_stop\": True}\n"
        "```\n\n"
        "Add step names, tool arguments, model name, token counts, and errors to telemetry so the next incident has precise evidence."
    )


def span_answer(context: dict[str, Any]) -> str:
    parts = []
    if context["failed_timeline"]:
        parts.append("Failed spans:")
        for item in context["failed_timeline"][:4]:
            parts.append(f"- {item.get('name')} ({format_ms(item.get('duration_ms'))}) status `{item.get('status_code')}`")
    elif context["timeline"]:
        parts.append("Most relevant spans from this trace:")
        for item in context["timeline"][:5]:
            parts.append(f"- {item.get('name')} ({item.get('canonical_type')}, {format_ms(item.get('duration_ms'))})")

    llm = first_llm_with_payload(context["llm_calls"], context["steps"])
    if llm:
        parts.append(f"LLM/model: `{llm.get('model_name') or llm.get('model') or 'N/A'}`")
        prompt = compact(llm.get("input_messages") or llm.get("prompt"))
        output = compact(llm.get("output_messages") or llm.get("response_text"))
        if prompt:
            parts.append(f"Input preview: {prompt}")
        if output:
            parts.append(f"Output preview: {output}")

    if context["failed_tools"]:
        parts.append("Failed tool payloads:")
        for tool in context["failed_tools"][:3]:
            parts.append(f"- {tool.get('tool_name')}: input `{compact(tool.get('tool_input'))}`, status `{tool.get('status')}`")

    return "\n".join(parts) if parts else "No span payload was captured for this incident trace."


def slo_answer(context: dict[str, Any]) -> str:
    breaches = context["slo_breaches"]
    if not breaches:
        return "No SLO breach details were recorded for this incident trace."
    lines = ["SLO breach details:"]
    for breach in breaches:
        lines.append(
            "- "
            f"{breach.get('label') or breach.get('metric_name')}: "
            f"observed `{breach.get('observed_value')}`, "
            f"target `{breach.get('operator')} {breach.get('threshold_value')}`."
        )
    return "\n".join(lines)


def suggested_questions(context: dict[str, Any]) -> list[str]:
    return [
        "Why did this incident happen?",
        "Which span or payload caused it?",
        "How should I fix this?",
        "Was there an SLO breach?",
    ]


def evidence_line(incident: dict[str, Any]) -> str:
    evidence = []
    if incident.get("metric_name"):
        evidence.append(f"{incident.get('metric_name')}={incident.get('observed_value')}")
    if incident.get("z_score") is not None:
        evidence.append(f"z-score={float(incident.get('z_score')):.2f}")
    if incident.get("threshold_value") is not None:
        evidence.append(f"threshold={incident.get('threshold_value')}")
    return ", ".join(evidence)


def first_llm_with_payload(llm_calls: list[dict[str, Any]], steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in llm_calls:
        if item.get("input_messages") or item.get("output_messages"):
            return item
    for item in steps:
        if item.get("input_messages") or item.get("response_text"):
            return item
    return llm_calls[0] if llm_calls else None


def compact(value: Any, limit: int = 360) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    text = " ".join(value.replace("\\n", " ").replace("\n", " ").split())
    return f"{text[:limit]}..." if len(text) > limit else text


def format_ms(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount / 1000:.2f}s" if amount >= 1000 else f"{amount:.0f}ms"


def short_id(value: Any) -> str:
    text = str(value or "N/A")
    return f"{text[:10]}..." if len(text) > 14 else text


def unique(values: list[Any]) -> list[str]:
    seen = []
    for value in values:
        text = str(value or "unknown")
        if text not in seen:
            seen.append(text)
    return seen
