from __future__ import annotations

import json
import re
from typing import Any

from backend.app.services.gemini_api import generate_text
from backend.core.settings import settings


VERDICT_SCORES = {"grounded": 1.0, "partial": 0.5, "ungrounded": 0.0}
FACTUAL_CLAIM_HINTS = re.compile(
    r"\b(is|are|was|were|will|must|can|guaranteed|always|never|approved|founded|located|meters|secret|official)\b",
    re.IGNORECASE,
)
HALLUCINATION_HINTS = re.compile(
    r"\b(secret|invented|uncited|guaranteed|approval|approvals|do not cite|without sources|unsupported)\b",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
CERTAINTY_ROOTS = ("guarante", "approv", "confirm", "definit", "certain")
NEGATION_WORDS = {"no", "not", "never", "cannot", "without", "false", "denied", "unavailable"}


def evaluate_groundedness(steps: list[dict[str, Any]], trace_id: str | None = None) -> dict[str, Any]:
    eligible_steps = [step for step in steps if not should_skip_step(step)]
    if not eligible_steps:
        return {"grounded_response_rate": None, "groundedness_judgements": []}

    previous_summaries: list[str] = []
    for step in eligible_steps[:-1]:
        remember_summary(step, previous_summaries)

    judgement = judge_step(eligible_steps[-1], previous_summaries, trace_id=trace_id)
    score = VERDICT_SCORES.get(judgement["verdict"], 0.0)
    return {
        "grounded_response_rate": score,
        "groundedness_judgements": [judgement],
    }


def judge_step(step: dict[str, Any], previous_summaries: list[str], trace_id: str | None = None) -> dict[str, Any]:
    if settings.llm_judge_enabled and settings.llm_judge_api_key:
        try:
            return llm_judge_step(step, previous_summaries)
        except Exception as exc:
            return heuristic_judge_step(step, previous_summaries, reason=f"LLM judge failed: {exc}")
    return heuristic_judge_step(step, previous_summaries, reason="Heuristic judge used.")


def llm_judge_step(step: dict[str, Any], previous_summaries: list[str]) -> dict[str, Any]:
    prompt = build_prompt(step, previous_summaries)
    content = generate_text(
        api_base_url=settings.llm_judge_api_url,
        api_key=settings.llm_judge_api_key,
        model=settings.llm_judge_model,
        system_instruction="Return only valid JSON with no Markdown formatting.",
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        timeout_seconds=settings.llm_judge_timeout_seconds,
        generation_config={"temperature": 0, "responseMimeType": "application/json"},
    )
    parsed = json.loads(content)
    verdict = str(parsed.get("verdict", "")).lower()
    if verdict not in VERDICT_SCORES:
        raise ValueError(f"Unknown judge verdict: {verdict}")
    return {
        "step_index": step.get("step_index"),
        "verdict": verdict,
        "score": VERDICT_SCORES[verdict],
        "confidence": float(parsed.get("confidence") or 0),
        "grounded_claims": string_list(parsed.get("grounded_claims")),
        "ungrounded_claims": string_list(parsed.get("ungrounded_claims")),
        "reasoning": str(parsed.get("reasoning") or "LLM judge completed."),
        "judge": "llm",
    }


def heuristic_judge_step(step: dict[str, Any], previous_summaries: list[str], reason: str) -> dict[str, Any]:
    response = str(step.get("response_text") or "")
    context_text = grounding_context_text(step, previous_summaries)
    has_context = bool(context_text.strip())
    response_tokens = token_set(response)
    context_tokens = token_set(context_text)
    overlap = len(response_tokens & context_tokens) / max(len(response_tokens), 1)
    factual = bool(FACTUAL_CLAIM_HINTS.search(response))
    suspicious = bool(HALLUCINATION_HINTS.search(response))
    repeated = repetition_score(response) >= 0.25
    unsupported_certainty = unsupported_certainty_claims(response, context_text)

    if unsupported_certainty:
        verdict = "ungrounded"
        reasoning = f"The response makes unsupported certainty claims: {', '.join(unsupported_certainty)}."
    elif not has_context and (suspicious or repeated or factual):
        verdict = "ungrounded"
        reasoning = "The response makes factual or unsupported claims without grounding context."
    elif has_context and factual and overlap < 0.08 and len(response_tokens) >= 12:
        verdict = "ungrounded"
        reasoning = "The response has low overlap with available tool/context evidence."
    elif has_context and factual and overlap < 0.18:
        verdict = "partial"
        reasoning = "Some response claims are weakly supported by available context."
    else:
        verdict = "grounded"
        reasoning = "The response is sufficiently aligned with available context or is non-factual."

    ungrounded_claims = [response] if verdict == "ungrounded" else []
    grounded_claims = [response] if verdict == "grounded" else []
    return {
        "step_index": step.get("step_index"),
        "verdict": verdict,
        "score": VERDICT_SCORES[verdict],
        "confidence": 0.65 if verdict != "partial" else 0.45,
        "grounded_claims": grounded_claims,
        "ungrounded_claims": ungrounded_claims,
        "reasoning": f"{reason} {reasoning}",
        "judge": "heuristic",
        "context_overlap": round(overlap, 4),
    }


def build_prompt(step: dict[str, Any], previous_summaries: list[str]) -> str:
    context_payload = {
        "tool_outputs": [
            {
                "tool_name": tool.get("tool_name"),
                "arguments": tool.get("arguments"),
                "success": tool.get("success"),
                "error_message": tool.get("error_message"),
                "result": tool.get("result"),
            }
            for tool in step.get("tool_executions", [])
        ],
        "input_messages": step.get("input_messages") or [],
        "previous_step_summaries": previous_summaries,
        "context_available": bool(step.get("tool_executions") or step.get("input_messages") or previous_summaries),
    }
    return (
        "You are an evaluation judge. Determine whether the assistant response is grounded in the context.\n\n"
        f"CONTEXT:\n{json.dumps(context_payload, indent=2, default=str)}\n\n"
        f"RESPONSE:\n{step.get('response_text') or ''}\n\n"
        "Return JSON only: {\"verdict\":\"grounded|partial|ungrounded\","
        "\"confidence\":0.0,\"grounded_claims\":[],\"ungrounded_claims\":[],\"reasoning\":\"...\"}"
    )


def should_skip_step(step: dict[str, Any]) -> bool:
    response = str(step.get("response_text") or "").strip()
    if not response:
        return True
    finish_reason = str(step.get("finish_reason") or "").lower()
    return finish_reason in {"tool_calls", "na", "n/a"}


def remember_summary(step: dict[str, Any], previous_summaries: list[str]) -> None:
    response = str(step.get("response_text") or "").strip()
    if response:
        previous_summaries.append(response[:500])


def grounding_context_text(step: dict[str, Any], previous_summaries: list[str]) -> str:
    parts = []
    for message in step.get("input_messages") or []:
        if isinstance(message, dict):
            parts.append(str(message.get("content") or ""))
    for tool in step.get("tool_executions") or []:
        if isinstance(tool, dict):
            parts.extend([str(tool.get("result") or ""), str(tool.get("error_message") or "")])
    parts.extend(previous_summaries)
    return "\n".join(part for part in parts if part)


def token_set(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(text) if len(token) > 2}


def unsupported_certainty_claims(response: str, context: str) -> list[str]:
    response_tokens = lexical_tokens(response)
    context_tokens = lexical_tokens(context)
    unsupported = []

    for index, token in enumerate(response_tokens):
        root = next((item for item in CERTAINTY_ROOTS if token.startswith(item)), None)
        if root is None or is_negated(response_tokens, index):
            continue
        if not context_supports_root(context_tokens, root):
            unsupported.append(token)

    return list(dict.fromkeys(unsupported))


def lexical_tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", text)]


def is_negated(tokens: list[str], index: int) -> bool:
    nearby = tokens[max(0, index - 6):index] + tokens[index + 1:index + 3]
    return any(token in NEGATION_WORDS for token in nearby)


def context_supports_root(tokens: list[str], root: str) -> bool:
    return any(
        token.startswith(root) and not is_negated(tokens, index)
        for index, token in enumerate(tokens)
    )


def repetition_score(text: str) -> float:
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    if len(tokens) < 8:
        return 0.0
    grams = [tuple(tokens[index:index + 5]) for index in range(len(tokens) - 4)]
    return 1.0 - (len(set(grams)) / max(len(grams), 1))


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]
