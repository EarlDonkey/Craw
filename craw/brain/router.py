"""Craw's router.

Before the LLM can answer, it must choose: use a tool, or don't. This
removes the "just answer" escape hatch that let the small model
hallucinate tool use. The router runs *first*, always.

Output is one of:
  {"tool": "<name>", "args": {...}}    — call this tool
  {"tool": "none"}                      — conversational, no tool needed

Fast-path keyword routes fire first. Only if nothing matches does the
LLM get asked. This means unambiguous requests never depend on the
model's mood or JSON parsing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from craw.brain.llm import LLM
from craw.hands import REGISTRY


# ---- force-none: conversational questions never route to a tool ----

_FORCE_NONE = [
    re.compile(r"\bhow are you\b", re.I),
    re.compile(r"\bhow do you feel\b", re.I),
    re.compile(r"\bhow are you feeling\b", re.I),
    re.compile(r"\bwhat are you\b", re.I),
    re.compile(r"\bwho are you\b", re.I),
    re.compile(r"\bwhere do you come from\b", re.I),
    re.compile(r"\bwho made you\b", re.I),
    re.compile(r"\bwhat can you do\b", re.I),
    re.compile(r"\bwhat'?s up\b", re.I),
]


# Requests that MUST route to a specific tool, no LLM involved.
# If any of these match, the route is fixed and the model is skipped.
FORCE_TOOL: list[tuple[re.Pattern[str], str, dict[str, Any]]] = [
    (re.compile(r"\b(what'?s?|what is) the time\b", re.I), "tell_time", {}),
    (re.compile(r"\bwhat time is it\b", re.I),             "tell_time", {}),
    (re.compile(r"\bwhat day is (it|today)\b", re.I),      "tell_date", {}),
    (re.compile(r"\b(what is|tell me) (the )?date\b", re.I), "tell_date", {}),
    (re.compile(r"\bhow much (ram|memory) (do i have|is used)\b", re.I),
     "system_stats", {}),
    (re.compile(r"\bwhat (is|are) (my )?(cpu|ram|disk)", re.I),
     "system_stats", {}),
    (re.compile(r"\bwhat window (am i|is)\b", re.I),       "active_window", {}),
    (re.compile(r"\bwhat'?s? on my clipboard\b", re.I),    "read_clipboard", {}),
]

# ---- keyword routes: unambiguous requests, no LLM needed ----

KEYWORD_ROUTES: list[tuple[re.Pattern[str], str, dict[str, Any]]] = [
    # time / date
    (re.compile(r"\bwhat time\b", re.I),        "tell_time", {}),
    (re.compile(r"\bwhat day\b", re.I),         "tell_date", {}),
    (re.compile(r"\bwhat date\b", re.I),        "tell_date", {}),

    # memory recall
    (re.compile(r"\bwhat did i read about\b", re.I), "recall", {"query": "MATCH"}),
    (re.compile(r"\bwhat do you (know|remember) about\b", re.I), "recall", {"query": "MATCH"}),
    (re.compile(r"\baccording to what you read\b", re.I), "recall", {"query": "MATCH"}),

    # file listing
    (re.compile(r"\blist (my )?downloads?\b", re.I), "list_dir",
     {"path": "%USERPROFILE%\\Downloads"}),
    (re.compile(r"\blist (my )?desktops?\b", re.I),   "list_dir",
     {"path": "%USERPROFILE%\\Desktop"}),
    (re.compile(r"\blist (my )?documents?\b", re.I), "list_dir",
     {"path": "%USERPROFILE%\\Documents"}),
    (re.compile(r"\blist (my )?(playground|code)\b", re.I), "list_code", {}),
    (re.compile(r"\bwhat'?s in (my )?playground\b", re.I), "list_code", {}),

    # system
    (re.compile(r"\bsystem (stats|status|doing)\b", re.I), "system_stats", {}),
    (re.compile(r"\bwhat window\b", re.I),      "active_window", {}),
    (re.compile(r"\bwhat'?s? on my clipboard\b", re.I), "read_clipboard", {}),
    (re.compile(r"\b(top|what) processes\b", re.I), "list_processes", {}),

    # face sense
    (re.compile(r"\bwho'?s (at|on) (the |my )?laptop\b", re.I), "who_is_at_the_laptop", {}),
    (re.compile(r"\bwho is using\b", re.I), "who_is_at_the_laptop", {}),

    # ---- write_code — file creation patterns ----
    # Bare "write X.py" first — it's the most specific.
    (re.compile(r"\bwrite [\w\-]+\.py\b", re.I),
     "write_code", {"path": "MATCH_PATH", "content": ""}),
    # "write a python file ..."
    (re.compile(r"\bwrite (a |an |the )?(python|py|text|html|js|json|shell|bash)?\s*file\b", re.I),
     "write_code", {"path": "MATCH_PATH", "content": ""}),
    # "write a script ..."
    (re.compile(r"\bwrite (a |an |the )?(python|py)?\s*script\b", re.I),
     "write_code", {"path": "MATCH_PATH", "content": ""}),
    # "create a file ..."
    (re.compile(r"\bcreate (a |an |the )?(python|py|text|html|js)?\s*file\b", re.I),
     "write_code", {"path": "MATCH_PATH", "content": ""}),
    # "make a script/program/tool ..."
    (re.compile(r"\bmake (a |an |the )?(python|py)?\s*(script|program|tool)\b", re.I),
     "write_code", {"path": "MATCH_PATH", "content": ""}),
    # "build a script/program/tool/file ..."
    (re.compile(r"\bbuild (a |an |the )?(python|py)?\s*(script|program|tool|file)\b", re.I),
     "write_code", {"path": "MATCH_PATH", "content": ""}),
]


# Tools whose output should be shown RAW to the user, not paraphrased.
# recall is NOT here — the LLM summarizes what was retrieved.
RAW_OUTPUT_TOOLS = {
    "list_dir",
    "search_files",
    "read_file",
    "read_workspace",
    "list_workspace",
    "read_code",
    "list_code",
    "system_stats",
    "active_window",
    "list_processes",
    "read_clipboard",
    "run_shell",
    "read_web_page",
    "readings",
    "write_code",
}


# Tools the LLM router is NOT allowed to pick on its own.
# These can only be reached via a keyword route.
LLM_FORBIDDEN_TOOLS = {
    "recall",
}


@dataclass
class Route:
    tool: str | None
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def _expand_args(args: dict[str, Any], raw_question: str = "") -> dict[str, Any]:
    """Fill in placeholders like MATCH and MATCH_PATH from the raw question."""
    out: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str) and v == "MATCH":
            out[k] = raw_question

        elif isinstance(v, str) and v == "MATCH_PATH":
            # Try to extract a filename from the question.
            # Priority:
            #   1. "called <name>.py"
            #   2. "called <name>"
            #   3. any token ending in .py
            m = re.search(r"called\s+([A-Za-z0-9_\-]+\.py)", raw_question)
            if not m:
                m = re.search(r"called\s+([A-Za-z0-9_\-]+)", raw_question)
            if not m:
                m = re.search(r"([A-Za-z0-9_\-]+\.py)", raw_question)
            out[k] = (m.group(1) if m else "script.py")

        elif isinstance(v, str) and v.startswith("%USERPROFILE%"):
            out[k] = v.replace("%USERPROFILE%",
                               os.environ.get("USERPROFILE", ""))
        else:
            out[k] = v
    return out


def keyword_route(question: str) -> Route | None:
    """Fast-path: forced-none and keyword routes. None means try the LLM."""
    # 1. Forced-none: conversational questions
    for pat in _FORCE_NONE:
        if pat.search(question):
            return Route(tool=None, args={},
                         reason=f"forced-none: {pat.pattern}")

    # 2. Forced-tool: unambiguous tool requests
    for pattern, tool, args in FORCE_TOOL:
        if pattern.search(question):
            return Route(tool=tool,
                         args=_expand_args(args, question),
                         reason=f"forced-tool: {pattern.pattern}")

    # 3. Regular keyword routes
    for pattern, tool, args in KEYWORD_ROUTES:
        if pattern.search(question):
            return Route(tool=tool,
                         args=_expand_args(args, question),
                         reason=f"keyword: {pattern.pattern}")

    return None

def _filter_tools_for_question(question: str) -> str:
    """Return a filtered tool list for the LLM router.

    Narrower options = better picks from small models.
    """
    q = question.lower()

    # File-ish requests: file tools + browse
    if any(w in q for w in ("file", "folder", "directory", "list", "read", "open")):
        return REGISTRY.prompt_block_for([
            "list_dir", "list_code", "read_file", "read_code",
            "search_files", "open_path", "open_in_browser", "read_web_page",
        ])

    # System-ish requests
    if any(w in q for w in ("system", "cpu", "ram", "disk", "memory", "process", "window")):
        return REGISTRY.prompt_block_for([
            "system_stats", "active_window", "list_processes",
        ])

    # Code-ish requests
    if any(w in q for w in ("write", "code", "script", "program", "tool", "create", "make")):
        return REGISTRY.prompt_block_for([
            "write_code", "read_code", "list_code", "run_shell",
        ])

    # Everything else — chat-level tools only
    return REGISTRY.prompt_block_for([
        "read_web_page", "recall", "tell_time", "tell_date",
    ])


def llm_route(question: str, llm: LLM) -> Route:
    if not llm.available():
        return Route(tool=None, args={}, reason="no llm")

    tools_block = _filter_tools_for_question(question)

    prompt = (
        f"Request: {question}\n\n"
        f"You are a ROUTER. Your only job is to pick a tool or say NONE.\n\n"
        f"CRITICAL: Most questions are NOT tool requests. Pick NONE for:\n"
        f"  - feelings or state: 'how are you', 'how do you feel'\n"
        f"  - identity: 'what are you', 'where do you come from'\n"
        f"  - opinions: 'what do you think of X', 'do you like Y'\n"
        f"  - conversation: 'hello', 'what's up', 'tell me a joke'\n"
        f"  - general knowledge: 'what is an atom', 'what color is the sky',\n"
        f"    'what is 2 plus 2', 'explain gravity'\n"
        f"  - anything you can answer from general knowledge\n\n"
        f"Pick a tool ONLY for explicit actions:\n"
        f"  - time/date: 'what time is it', 'what day is it'\n"
        f"  - files: 'list my downloads', 'what's in my playground'\n"
        f"  - system: 'system status', 'what window am i looking at'\n"
        f"  - web: 'read the wikipedia page on X'\n"
        f"  - code: 'write a script that does X'\n"
        f"  - shell: 'run git status'\n\n"
        f"Do NOT pick recall. Do NOT pick write_code. Those are handled\n"
        f"by other code paths.\n\n"
        f'Reply with a single line of JSON: {{"tool": "<name>", "args": {{...}}}} or {{"tool": "none"}}\n\n'
        f"{tools_block}"
    )
    raw = llm.generate_json(prompt,
                            system="You are a tool router. Reply only with JSON.")
    print(f"[router-raw] {raw[:200]!r}", file=sys.stderr, flush=True)
    raw = (raw or "").strip()

    if not raw or raw.lower().strip(" .") in ("none", "silence"):
        return Route(tool=None, args={}, reason="llm: none")

    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return Route(tool=None, args={}, reason=f"llm: unparsable {raw[:60]!r}")

    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return Route(tool=None, args={}, reason=f"llm: bad json {raw[:60]!r}")

    if not isinstance(data, dict):
        return Route(tool=None, args={}, reason="llm: not an object")

    tool = str(data.get("tool", "none")).strip()
    if tool in ("none", "", "None", "null"):
        return Route(tool=None, args={}, reason="llm: none")

    if REGISTRY.get(tool) is None:
        return Route(tool=None, args={}, reason=f"llm: unknown tool {tool}")

    if tool in LLM_FORBIDDEN_TOOLS:
        return Route(tool=None, args={},
                     reason=f"llm: {tool} is keyword-only")

    args = data.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    # Strip any arguments the tool doesn't actually accept.
    tool_obj = REGISTRY.get(tool)
    if tool_obj and tool_obj.args:
        allowed = set(tool_obj.args.keys())
        args = {k: v for k, v in args.items() if k in allowed}
    else:
        args = {}

    return Route(tool=tool, args=args, reason=f"llm: chose {tool}")


def route(question: str, llm: LLM) -> Route:
    """The one entry point. Keyword first, LLM if nothing matched."""
    kw = keyword_route(question)
    if kw is not None:
        print(f"[router] {kw.reason} -> tool={kw.tool}",
              file=sys.stderr, flush=True)
        return kw
    r = llm_route(question, llm)
    print(f"[router] llm choice: {r.tool}  args={r.args}  reason={r.reason}",
          file=sys.stderr, flush=True)
    return r