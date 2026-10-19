"""Craw's hands — the registry.

A tool is a function with a name, a description, an argument schema,
and a permission tier. The registry holds them. The brain selects one.
The router executes it.

Nothing in this file *does* anything. It only describes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


Tier = Literal["auto", "confirm", "deny"]


@dataclass
class Tool:
    """One thing Craw can do."""

    name: str
    description: str
    fn: Callable[..., Any]
    tier: Tier = "auto"
    args: dict[str, str] = field(default_factory=dict)

    def call(self, **kwargs: Any) -> Any:
        return self.fn(**kwargs)

    def schema_line(self) -> str:
        if not self.args:
            return f"  - {self.name}: {self.description}"
        args = ", ".join(f"{k}" for k in self.args)
        return f"  - {self.name}({args}): {self.description}"

    def __call__(self, **kwargs: Any) -> Any:
        return self.call(**kwargs)


class Registry:
    """Craw's available hands."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def prompt_block(self) -> str:
        """Full tool list, grouped by tier. Used for chat-level prompts."""
        auto = [t for t in self._tools.values() if t.tier == "auto"]
        confirm = [t for t in self._tools.values() if t.tier == "confirm"]

        lines = ["Things you can do:"]
        for t in auto:
            lines.append(t.schema_line())
        if confirm:
            lines.append("")
            lines.append("Things you can do, but you must announce:")
            for t in confirm:
                lines.append(t.schema_line())
        return "\n".join(lines)

    def prompt_block_for(self, names: list[str]) -> str:
        """Filtered tool list — only the named tools.

        Used by the router to narrow the options for a small model.
        Fewer choices = fewer mistakes.
        """
        lines = ["Things you can do:"]
        for name in names:
            tool = self._tools.get(name)
            if tool:
                lines.append(tool.schema_line())
        return "\n".join(lines)


REGISTRY = Registry()