from __future__ import annotations

import inspect
import threading
from typing import Any


_LOCK = threading.Lock()
_AVAILABLE_TOOLS: dict[str, dict[str, Any]] = {}


def register_available_tools(tools: Any, *, framework: str | None = None) -> None:
    if tools is None:
        return
    tool_items = tools if isinstance(tools, (list, tuple, set)) else [tools]
    with _LOCK:
        for tool in tool_items:
            metadata = _tool_metadata(tool, framework)
            if metadata["tool_name"]:
                _AVAILABLE_TOOLS[_tool_key(metadata)] = metadata


def snapshot_available_tools() -> list[dict[str, Any]]:
    tools: dict[str, dict[str, Any]] = {}
    with _LOCK:
        for item in _AVAILABLE_TOOLS.values():
            tools[_tool_key(item)] = dict(item)
    return [dict(item) for item in tools.values()]


def clear_available_tools() -> None:
    with _LOCK:
        _AVAILABLE_TOOLS.clear()


def _tool_metadata(tool: Any, framework: str | None) -> dict[str, Any]:
    name = getattr(tool, "name", None) or getattr(tool, "__name__", None) or tool.__class__.__name__
    args = getattr(tool, "args", None)
    if args is None:
        args_schema = getattr(tool, "args_schema", None)
        schema = getattr(args_schema, "model_json_schema", None)
        args = schema() if callable(schema) else None
    return {
        "tool_name": str(name) if name is not None else None,
        "tool_description": _tool_description(tool),
        "tool_type": _tool_type(tool, framework),
        "tool_arguments": args,
        "framework": framework,
    }


def _tool_description(tool: Any) -> str | None:
    description = getattr(tool, "description", None)
    if description:
        return str(description)
    metadata = getattr(tool, "metadata", None)
    if isinstance(metadata, dict) and metadata.get("description"):
        return str(metadata["description"])
    doc = inspect.getdoc(tool)
    if doc:
        return doc
    class_doc = inspect.getdoc(tool.__class__)
    return class_doc if class_doc and tool.__class__ is not object else None


def _tool_type(tool: Any, framework: str | None) -> str | None:
    metadata = getattr(tool, "metadata", None)
    if isinstance(metadata, dict):
        tool_type = metadata.get("tool_type") or metadata.get("type")
        if tool_type:
            return str(tool_type)
    category = getattr(tool, "tool_type", None) or getattr(tool, "type", None)
    if category:
        return str(category)
    if _is_langchain_tool(tool):
        return "Tool"
    return framework


def _tool_key(metadata: dict[str, Any]) -> str:
    return "|".join(str(metadata.get(key) or "") for key in ["framework", "tool_name", "tool_type"])


def _is_langchain_tool(tool: Any) -> bool:
    try:
        from langchain_core.tools import BaseTool

        return isinstance(tool, BaseTool)
    except Exception:
        return False
