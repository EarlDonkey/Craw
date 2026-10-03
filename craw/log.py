"""Craw's voice, for now, is a log line.

When the mouth arrives, this becomes one of several outputs. For now it's
the only way to see Craw think. Keep it quiet and readable.
"""

from __future__ import annotations

import sys
import time


def _stamp() -> str:
    return time.strftime("%H:%M:%S")


def _emit(tag: str, text: str) -> None:
    print(f"[{_stamp()}] {tag:<10} {text}", file=sys.stderr, flush=True)


def body(msg: str) -> None:
    _emit("body", msg)


def sense(msg: str) -> None:
    _emit("sense", msg)


def think(msg: str) -> None:
    _emit("think", msg)


def speak(msg: str) -> None:
    _emit("speak", msg)


def reflex(msg: str) -> None:
    _emit("reflex", msg)