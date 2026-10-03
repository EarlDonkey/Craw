"""Parsing and routing for Craw's tools.

The LLM replies with either plain text (Craw just talks) or a small
JSON object (Craw wants to call a tool). This module separates the two
and executes the tool if allowed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from craw.hands import REGISTRY, policy


_TOOL_PATTERN = re.compile(r"\{[^{}]*\"tool\"[^{}]*\}", re.DOTALL)


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


def parse_tool_call(text: str) -> ToolCall | None:
    """Extract a tool call from LLM output, if any.

    The LLM is instructed to return exactly one JSON object when it wants
    a tool. It often wraps it in prose anyway. We dig it out.
    """
    if not text:
        return None

    # Fast path: whole string is JSON
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and "tool" in data:
            return ToolCall(name=str(data["tool"]), args=data.get("args") or {})
    except json.JSONDecodeError:
        pass

    # Slow path: find the first {...} containing "tool"
    m = _TOOL_PATTERN.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "tool" not in data:
        return None
    return ToolCall(name=str(data["tool"]), args=data.get("args") or {})


def execute(call: ToolCall) -> tuple[bool, str]:
    """Run a tool call if allowed. Returns (ok, result_text)."""
    tool = REGISTRY.get(call.name)
    if tool is None:
        return False, f"no such tool: {call.name}"
    if not policy.is_allowed(tool):
        return False, f"tool not allowed: {call.name}"

    # Sanitize args: strings only, trimmed, bounded length.
    clean: dict[str, Any] = {}
    for k, v in (call.args or {}).items():
        if isinstance(v, str):
            v = v.strip()
            if len(v) > 200:
                v = v[:200]
            # Common 3B hallucination: embedding shell syntax in the arg.
            # If the value contains shell-ish operators, drop to first token.
            if any(x in v for x in (" && ", " || ", " | ", " -m ", " ; ")):
                v = v.split()[0]
        clean[k] = v

    try:
        result = tool.call(**clean)
        return True, str(result)
    except TypeError as exc:
        return False, f"bad arguments for {call.name}: {exc}"
    except Exception as exc:
        return False, f"{call.name} failed: {exc}"