"""Craw's permission policy.

Three tiers:

  auto    — safe, read-only, no side effects. Craw does it silently.
  confirm — has side effects, but reversible and non-destructive.
            Craw does it, then tells you what it did.
  deny    — not allowed. Never happens.

The registry is a whitelist. Anything not in it is deny.
"""

from __future__ import annotations

from craw.hands.registry import Tool


def is_allowed(tool: Tool) -> bool:
    return tool.tier in ("auto", "confirm")


def requires_announcement(tool: Tool) -> bool:
    return tool.tier == "confirm"