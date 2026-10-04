"""Craw's router.

Before the LLM can answer, it must choose: use a tool, or don't. This
removes the "just answer" escape hatch that let the 3B model hallucinate
tool use. The router runs *first*, always. Whatever it decides, the
answer path is grounded in that decision.

Output is one of:
  {"tool": "<name>", "args": {...}}    — call this tool
  {"tool": "none"}                      — conversational, no tool needed
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from craw.brain.llm import LLM
from craw.hands import REGISTRY


KEYWORD_ROUTES: list[tuple[re.Pattern[str], str, dict[str, Any]]] = [
    (re.compile(r"\bwhat time\b", re.I),        "tell_time", {}),
    (re.compile(r"\bwhat day\b", re.I),         "tell_date", {}),
    (re.compile(r"\bwhat date\b", re.I),        "tell_date", {}),
    (re.compile(r"\blist (my )?downloads\b", re.I), "list_dir",
     {"path": "%USERPROFILE%\\Downloads"}),
    (re.compile(r"\blist (my )?desktop\b", re.I),   "list_dir",
     {"path": "%USERPROFILE%\\Desktop"}),
    (re.compile(r"\blist (my )?documents\b", re.I), "list_dir",
     {"path": "%USERPROFILE%\\Documents"}),
    (re.compile(r"\bsystem (stats|status|doing)\b", re.I), "system_stats", {}),
    (re.compile(r"\bwhat window\b", re.I),      "active_window", {}),
    (re.compile(r"\bwhat'?s? on my clipboard\b", re.I), "read_clipboard", {}),
    (re.compile(r"\b(top|what) processes\b", re.I), "list_processes", {}),
]


RAW_OUTPUT_TOOLS = {
    "list_dir",
    "search_files",
    "read_file",
    "read_workspace",
    "list_workspace",
    "system_stats",
    "active_window",
    "list_processes",
    "read_clipboard",
    "run_shell",
    "read_web_page",
    "readings",
}


@dataclass
class Route:
    tool: str | None
    args: dict[str, Any]
    reason: str


def _expand_args(args: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and v.startswith("%USERPROFILE%"):
            out[k] = v.replace("%USERPROFILE%",
                               os.environ.get("USERPROFILE", ""))
        else:
            out[k] = v
    return out


def keyword_route(question: str) -> Route | None:
    for pattern, tool, args in KEYWORD_ROUTES:
        if pattern.search(question):
            return Route(tool=tool, args=_expand_args(args),
                         reason=f"keyword: {pattern.pattern}")
    return None


def llm_route(question: str, llm: LLM) -> Route:
    if not llm.available():
        return Route(tool=None, args={}, reason="no llm")

    tools_block = REGISTRY.prompt_block()
    prompt = (
        f"Request: {question}\n\n"
        f"Pick ONE tool from the list below that best matches this request, "
        f"or pick NONE if it's a conversational question with no tool needed.\n\n"
        f"Reply with a single line of JSON. One of:\n"
        f'  {{"tool": "tool_name", "args": {{...}}}}\n'
        f'  {{"tool": "none"}}\n\n'
        f"No prose. No explanation. Just the JSON.\n\n"
        f"{tools_block}"
    )
    raw = llm.generate_json(prompt, system="You are a tool router. Reply only with JSON.")
    raw = (raw or "").strip()

    if not raw or raw.lower().strip(" .") in ("none", "silence"):
        return Route(tool=None, args={}, reason="llm: none")

    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return Route(tool=None, args={}, reason=f"llm: unparsable {raw[:40]!r}")

    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return Route(tool=None, args={}, reason=f"llm: bad json {raw[:40]!r}")

    tool = str(data.get("tool", "none")).strip()
    if tool in ("none", "", "None"):
        return Route(tool=None, args={}, reason="llm: none")

    if REGISTRY.get(tool) is None:
        return Route(tool=None, args={}, reason=f"llm: unknown tool {tool}")

    args = data.get("args") or {}
    if not isinstance(args, dict):
        args = {}
    return Route(tool=tool, args=args, reason=f"llm: chose {tool}")


def route(question: str, llm: LLM) -> Route:
    kw = keyword_route(question)
    if kw is not None:
        return kw
    return llm_route(question, llm)