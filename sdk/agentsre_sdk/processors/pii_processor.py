from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


REDACTED = "[REDACTED]"
RedactionPath = tuple[str | int, ...]
RedactionFindings = dict[RedactionPath, set[str]]


@dataclass
class _SensitiveValue:
    value: str
    category: str


@dataclass
class _RedactionContext:
    sensitive_values: list[_SensitiveValue] = field(default_factory=list)


class PIIProcessor:
    EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
    PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[-. ]?)?(?:\(?\d{3}\)?[-. ]?)\d{3}[-. ]?\d{4}(?!\w)")
    TOKEN_RE = re.compile(
        r"\b(?:sk|pk|rk|ghp|gho|ghu|github_pat|xox[baprs]|ya29)[-_A-Za-z0-9]{16,}\b"
    )
    NAME_CONTEXT_RE = re.compile(
        r"\b(?:my name is|name is|customer name:|user name:|patient name:|employee name:|traveler name:|passenger name:|client name:|confirmed for|timed out for|reservation for)\s+[A-Z][a-z]+(?:\s+(?!on\b|in\b|at\b|from\b|to\b|with\b|using\b)[A-Z][a-z]+){0,2}",
        re.IGNORECASE,
    )
    NAME_FIELD_HINTS = {
        "name",
        "full_name",
        "first_name",
        "last_name",
        "customer_name",
        "user_name",
        "client_name",
        "person_name",
        "employee_name",
        "patient_name",
        "account_holder_name",
        "contact_name",
        "traveler_name",
        "passenger_name",
        "guest_name",
    }
    EMAIL_FIELD_HINTS = {
        "email",
        "email_address",
        "customer_email",
        "user_email",
        "client_email",
        "work_email",
        "personal_email",
        "contact_email",
        "traveler_email",
        "passenger_email",
    }
    PHONE_FIELD_HINTS = {
        "phone",
        "phone_number",
        "mobile",
        "mobile_number",
        "contact_number",
        "customer_phone",
        "user_phone",
        "client_phone",
        "patient_phone",
        "traveler_phone",
    }
    SECRET_FIELD_HINTS = {
        "api_key",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "client_secret",
        "password",
        "authorization",
        "auth_token",
        "bearer_token",
        "private_key",
    }
    IDENTITY_FIELD_HINTS = {
        "ssn",
        "national_id",
        "passport_number",
        "driver_license",
        "tax_id",
        "pan",
        "aadhaar",
        "employee_id",
        "patient_id",
        "account_number",
        "card_number",
    }

    def __init__(self, enabled: bool = True, sensitive_fields: set[str] | list[str] | None = None) -> None:
        self.enabled = enabled
        configured = sensitive_fields or set()
        self.sensitive_fields = {field.lower() for field in configured}

    def redact_payload(self, value: Any) -> Any:
        redacted, _ = self.redact_payload_with_findings(value)
        return redacted

    def redact_payload_with_findings(self, value: Any) -> tuple[Any, RedactionFindings]:
        if not self.enabled:
            return value, {}
        findings: RedactionFindings = {}
        context = _RedactionContext(self._collect_sensitive_values(value))
        return self._redact(value, field_name=None, path=(), findings=findings, context=context), findings

    def redact_text(self, text: str) -> str:
        redacted, _ = self.redact_text_with_findings(text)
        return redacted

    def redact_text_with_findings(self, text: str) -> tuple[str, set[str]]:
        return self._redact_text_with_findings(text, _RedactionContext())

    def _redact_text_with_findings(self, text: str, context: _RedactionContext) -> tuple[str, set[str]]:
        if not self.enabled:
            return text, set()
        fields: set[str] = set()

        def replace_email(match: re.Match[str]) -> str:
            fields.add("email")
            return REDACTED

        def replace_ssn(match: re.Match[str]) -> str:
            fields.add("ssn")
            return REDACTED

        def replace_phone(match: re.Match[str]) -> str:
            fields.add("phone")
            return REDACTED

        def replace_credit_card(match: re.Match[str]) -> str:
            candidate = match.group(0)
            digits = re.sub(r"\D", "", candidate)
            if 13 <= len(digits) <= 19 and _luhn_valid(digits):
                fields.add("credit_card")
                return REDACTED
            return candidate

        def replace_token(match: re.Match[str]) -> str:
            fields.add("secret")
            return REDACTED

        def replace_name(match: re.Match[str]) -> str:
            fields.add("name")
            return self._redact_name_context(match)

        redacted = self.EMAIL_RE.sub(replace_email, text)
        redacted = self.SSN_RE.sub(replace_ssn, redacted)
        redacted = self.PHONE_RE.sub(replace_phone, redacted)
        redacted = self.CREDIT_CARD_RE.sub(replace_credit_card, redacted)
        redacted = self.TOKEN_RE.sub(replace_token, redacted)
        redacted, exact_fields = self._redact_known_sensitive_values(redacted, context)
        fields.update(exact_fields)
        redacted = self.NAME_CONTEXT_RE.sub(replace_name, redacted)
        return redacted, fields

    def _redact(
        self,
        value: Any,
        field_name: str | None,
        path: RedactionPath,
        findings: RedactionFindings,
        context: _RedactionContext,
    ) -> Any:
        should_redact_here = _is_redaction_target_path(path)
        inside_redaction_target = _is_inside_redaction_target_path(path)
        if field_name is not None and self._is_sensitive_field(field_name) and inside_redaction_target:
            if _is_schema_descriptor(path, value) or _is_metadata_field_path(path):
                return self._redact(value, field_name=None, path=path, findings=findings, context=context)
            findings.setdefault(path, set()).add(self._sensitive_field_category(field_name))
            return REDACTED
        if isinstance(value, str):
            if not inside_redaction_target and not should_redact_here:
                return value
            parsed_json = _parse_json_container(value)
            if parsed_json is not None:
                redacted = self._redact(parsed_json, field_name=None, path=path, findings=findings, context=context)
                return _json_dumps(redacted)
            if should_redact_here or inside_redaction_target:
                redacted, fields = self._redact_text_with_findings(value, context)
                if fields:
                    findings.setdefault(path, set()).update(fields)
                return redacted
            return value
        if isinstance(value, Mapping):
            return {key: self._redact(item, str(key), (*path, str(key)), findings, context) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact(item, field_name=None, path=(*path, index), findings=findings, context=context) for index, item in enumerate(value)]
        if isinstance(value, tuple):
            return tuple(self._redact(item, field_name=None, path=(*path, index), findings=findings, context=context) for index, item in enumerate(value))
        return value

    def _is_sensitive_field(self, field_name: str) -> bool:
        normalized = field_name.lower()
        return (
            normalized in self.sensitive_fields
            or normalized in self.NAME_FIELD_HINTS
            or normalized in self.EMAIL_FIELD_HINTS
            or normalized in self.PHONE_FIELD_HINTS
            or normalized in self.SECRET_FIELD_HINTS
            or normalized in self.IDENTITY_FIELD_HINTS
        )

    def _sensitive_field_category(self, field_name: str) -> str:
        normalized = field_name.lower()
        if normalized in self.sensitive_fields:
            return normalized
        if normalized in self.NAME_FIELD_HINTS:
            return "name"
        if normalized in self.EMAIL_FIELD_HINTS:
            return "email"
        if normalized in self.PHONE_FIELD_HINTS:
            return "phone"
        if normalized in self.SECRET_FIELD_HINTS:
            return "secret"
        if normalized in self.IDENTITY_FIELD_HINTS:
            return "identity"
        return normalized

    def _collect_sensitive_values(self, value: Any) -> list[_SensitiveValue]:
        values: list[_SensitiveValue] = []
        seen: set[tuple[str, str]] = set()

        def collect(item: Any, field_name: str | None = None, path: RedactionPath = ()) -> None:
            inside_redaction_target = _is_inside_redaction_target_path(path)
            if field_name is not None and self._is_sensitive_field(field_name) and inside_redaction_target:
                if _is_schema_descriptor(path, item) or _is_metadata_field_path(path):
                    return
                category = self._sensitive_field_category(field_name)
                for candidate in _extract_sensitive_strings(item):
                    if not _should_collect_sensitive_value(candidate):
                        continue
                    for variant in _sensitive_value_variants(candidate, category):
                        key = (variant, category)
                        if key not in seen:
                            seen.add(key)
                            values.append(_SensitiveValue(variant, category))
                return
            if isinstance(item, str):
                if not inside_redaction_target and not _is_redaction_target_path(path):
                    return
                parsed = _parse_json_container(item)
                if parsed is not None:
                    collect(parsed, field_name=None, path=path)
                return
            if isinstance(item, Mapping):
                for key, child in item.items():
                    collect(child, str(key), (*path, str(key)))
            elif isinstance(item, (list, tuple)):
                for index, child in enumerate(item):
                    collect(child, field_name=None, path=(*path, index))

        collect(value)
        return sorted(values, key=lambda item: len(item.value), reverse=True)

    def _redact_known_sensitive_values(self, text: str, context: _RedactionContext) -> tuple[str, set[str]]:
        redacted = text
        fields: set[str] = set()
        for item in context.sensitive_values:
            pattern = _exact_value_pattern(item.value)
            next_value, count = pattern.subn(REDACTED, redacted)
            if count:
                redacted = next_value
                fields.add(item.category)
        return redacted, fields

    def _redact_credit_card_candidate(self, match: re.Match[str]) -> str:
        candidate = match.group(0)
        digits = re.sub(r"\D", "", candidate)
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            return REDACTED
        return candidate

    def _redact_name_context(self, match: re.Match[str]) -> str:
        text = match.group(0)
        lowered = text.lower()
        if "customer name:" in lowered:
            return "customer name: [REDACTED]"
        if "user name:" in lowered:
            return "user name: [REDACTED]"
        if "patient name:" in lowered:
            return "patient name: [REDACTED]"
        if "employee name:" in lowered:
            return "employee name: [REDACTED]"
        if "traveler name:" in lowered:
            return "traveler name: [REDACTED]"
        if "passenger name:" in lowered:
            return "passenger name: [REDACTED]"
        if "client name:" in lowered:
            return "client name: [REDACTED]"
        if lowered.startswith("my name is"):
            return f"my name is {REDACTED}"
        if lowered.startswith("name is"):
            return f"name is {REDACTED}"
        for prefix in ["confirmed for", "timed out for", "reservation for"]:
            if lowered.startswith(prefix):
                return f"{text[:len(prefix)]} {REDACTED}"
        return REDACTED


def _is_redaction_target_path(path: RedactionPath) -> bool:
    normalized = _normalize_path(path)
    return (
        _matches_path(normalized, ("spans", "*", "llm", "prompt"))
        or _matches_path(normalized, ("spans", "*", "llm", "response"))
        or _matches_path(normalized, ("spans", "*", "tool", "tool_arguments"))
        or _matches_path(normalized, ("spans", "*", "tool", "tool_output"))
        or _matches_path(normalized, ("spans", "*", "tool", "tool_error"))
        or _matches_path(normalized, ("spans", "*", "memory", "memory_key"))
        or _matches_path(normalized, ("spans", "*", "memory", "retrieved_documents"))
        or _matches_path(normalized, ("spans", "*", "memory", "retrieved_chunks"))
        or _matches_path(normalized, ("spans", "*", "error_message"))
        or _matches_path(normalized, ("llm", "prompt"))
        or _matches_path(normalized, ("llm", "response"))
        or _matches_path(normalized, ("tool", "*"))
        or _matches_path(normalized, ("memory", "memory_key"))
        or _matches_path(normalized, ("memory", "retrieved_documents"))
        or _matches_path(normalized, ("memory", "retrieved_chunks"))
        or _matches_path(normalized, ("error_message",))
    )


def _is_inside_redaction_target_path(path: RedactionPath) -> bool:
    normalized = _normalize_path(path)
    return any(_path_starts_with(normalized, target) for target in _redaction_target_prefixes())


def _redaction_target_prefixes() -> tuple[tuple[str, ...], ...]:
    return (
        ("spans", "*", "llm", "prompt"),
        ("spans", "*", "llm", "response"),
        ("spans", "*", "tool", "tool_arguments"),
        ("spans", "*", "tool", "tool_output"),
        ("spans", "*", "tool", "tool_error"),
        ("spans", "*", "memory", "memory_key"),
        ("spans", "*", "memory", "retrieved_documents"),
        ("spans", "*", "memory", "retrieved_chunks"),
        ("spans", "*", "error_message"),
        ("llm", "prompt"),
        ("llm", "response"),
        ("tool",),
        ("memory", "memory_key"),
        ("memory", "retrieved_documents"),
        ("memory", "retrieved_chunks"),
        ("error_message",),
    )


def _normalize_path(path: RedactionPath) -> tuple[str, ...]:
    return tuple("*" if isinstance(item, int) else str(item) for item in path)


def _matches_path(path: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    return len(path) == len(pattern) and all(expected == "*" or actual == expected for actual, expected in zip(path, pattern))


def _path_starts_with(path: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(path) >= len(prefix) and all(expected == "*" or actual == expected for actual, expected in zip(path, prefix))


def _is_schema_descriptor(path: RedactionPath, value: Any) -> bool:
    if _looks_like_schema_descriptor(value):
        return True
    normalized = _normalize_path(path)
    return (
        "parameters" in normalized
        or "properties" in normalized
        or "schema" in normalized
        or (normalized and normalized[-1] in {"type", "title", "description", "default", "required", "items", "anyOf"})
    )


def _is_metadata_field_path(path: RedactionPath) -> bool:
    normalized = _normalize_path(path)
    if not normalized:
        return False
    if normalized[-1] in {
        "tool_name",
        "tool_type",
        "agent_name",
        "agent_role",
        "agent_type",
        "span_name",
        "span_kind",
        "provider",
        "model",
    }:
        return True
    if len(normalized) >= 2 and normalized[-2:] in {
        ("function", "name"),
        ("function", "description"),
    }:
        return True
    if "tool_calls" in normalized and normalized[-1] in {"name", "type", "id"}:
        return True
    if "tools" in normalized and normalized[-1] in {"name", "type", "description"}:
        return True
    return False


def _looks_like_schema_descriptor(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    schema_keys = {"type", "title", "description", "default", "anyOf", "items", "properties"}
    return bool(schema_keys.intersection(str(key) for key in value.keys()))


def _extract_sensitive_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, Mapping):
        values: list[str] = []
        for item in value.values():
            values.extend(_extract_sensitive_strings(item))
        return values
    if isinstance(value, (list, tuple)):
        values = []
        for item in value:
            values.extend(_extract_sensitive_strings(item))
        return values
    return []


def _should_collect_sensitive_value(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped == REDACTED:
        return False
    if len(stripped) < 3:
        return False
    return True


def _sensitive_value_variants(value: str, category: str) -> list[str]:
    stripped = value.strip()
    variants = [stripped]
    if category == "name":
        words = [word for word in re.split(r"\s+", stripped) if word]
        if len(words) >= 2:
            first = re.sub(r"[^A-Za-z'-]", "", words[0])
            if len(first) >= 3:
                variants.extend([first, f"{first}'s"])
    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        if _should_collect_sensitive_value(variant) and variant not in seen:
            seen.add(variant)
            deduped.append(variant)
    return deduped


def _exact_value_pattern(value: str) -> re.Pattern[str]:
    escaped = re.escape(value.strip())
    return re.compile(rf"(?<!\w){escaped}(?!\w)")


def _luhn_valid(digits: str) -> bool:
    checksum = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        digit = int(char)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _parse_json_container(value: str) -> Any | None:
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        parsed = _json_loads(stripped)
    except ValueError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _json_loads(value: str) -> Any:
    return json.loads(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
