"""Craw's hands.

Tools are what Craw can *do*. The registry holds them. The router runs
them. Policy decides which ones are allowed.

Import this module to populate the registry.
"""

from craw.hands.registry import REGISTRY, Registry, Tool
from craw.hands import policy
from craw.hands import tools   # noqa: F401  — registers on import

__all__ = ["REGISTRY", "Registry", "Tool", "policy"]