from __future__ import annotations

from typing import Any

import httpx


def generate_text(
    *,
    api_base_url: str,
    api_key: str,
    model: str,
    system_instruction: str,
    contents: list[dict[str, Any]],
    timeout_seconds: int,
    generation_config: dict[str, Any] | None = None,
) -> str:
    """Generate text with the Gemini Developer API."""
    url = f"{api_base_url.rstrip('/')}/{model}:generateContent"
    payload: dict[str, Any] = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
    }
    if generation_config:
        payload["generationConfig"] = generation_config

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            url,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    candidates = response.json().get("candidates") or []
    if not candidates:
        raise ValueError("Gemini returned no response candidates.")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise ValueError("Gemini returned an empty text response.")
    return text


def gemini_contents(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Convert simple user/assistant chat messages to Gemini content turns."""
    contents = []
    for message in messages:
        text = str(message.get("content") or "").strip()
        if not text:
            continue
        role = "model" if message.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": text}]})
    return contents
