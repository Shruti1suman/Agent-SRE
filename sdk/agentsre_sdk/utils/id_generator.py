from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone


def generate_trace_id() -> str:
    return secrets.token_hex(16)


def generate_span_id() -> str:
    return secrets.token_hex(8)


def generate_execution_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"exec_{timestamp}_{secrets.token_hex(4)}"


def generate_workflow_id(prefix: str = "wf") -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def generate_session_id(prefix: str = "session") -> str:
    return f"{prefix}_{uuid.uuid4()}"
