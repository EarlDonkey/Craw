"""Craw's senses. Each one produces observations for the brain.

A sense is a thing that watches something and, when it notices something,
tells the brain. Senses do not interpret. They observe. Interpretation is
the brain's job.
"""

from craw.senses.base import Sense
from craw.senses.shell import ShellSense

__all__ = ["Sense", "ShellSense"]