"""Parsing and routing for Craw's tools.

The router picks a tool and its args. This module executes it with
policy checks and argument sanitization.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from craw.hands import REGISTRY, policy


_TOOL_PATTERN = re.compile(r"\{[^{}]*\"tool\"[^{}]*\}", re.DOTALL)


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


def parse_tool_call(text: str) -> ToolCall | None:
    """Extract a tool call from arbitrary LLM output. Used only by legacy paths."""
    if not text:
        return None
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and "tool" in data:
            return ToolCall(name=str(data["tool"]), args=data.get("args") or {})
    except json.JSONDecodeError:
        pass
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

    # Sanitize: coerce to expected arg types where obvious.
    clean: dict[str, Any] = {}
    for k, v in (call.args or {}).items():
        if isinstance(v, str):
            v = v.strip()
            if len(v) > 500:
                v = v[:500]
        clean[k] = v

    try:
        result = tool.call(**clean)
        return True, str(result)
    except TypeError as exc:
        return False, f"bad arguments for {call.name}: {exc}"
    except Exception as exc:
        return False, f"{call.name} failed: {exc}"