"""Craw's connection to its mind.

Talks to a local ollama instance. If ollama isn't running, Craw doesn't
die — it just goes quiet and lets the rule-based voice take over, so the
creature survives its own fainting.

Never used for the face. Only used for speech.

Failure caching:
  - Success cached for 60s.
  - Failure cached for only 5s, so a transient slowness (model loading,
    brief timeout) recovers automatically.
  - A single failed generation does NOT poison the available flag.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
DEFAULT_MODEL = "llama3.2:3b"


_THIRD_PERSON_FIXES = [
    (re.compile(r"\bthe user's\b", re.IGNORECASE), "your"),
    (re.compile(r"\bthe user\b", re.IGNORECASE), "you"),
    (re.compile(r"\bthe person's\b", re.IGNORECASE), "your"),
    (re.compile(r"\bthe person\b", re.IGNORECASE), "you"),
]


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL, timeout: float = 90.0) -> None:
        self.model = model
        self.timeout = timeout
        self._available: bool | None = None
        self._checked_at: float = 0.0

    def available(self) -> bool:
        now = time.time()
        if self._available is True and now - self._checked_at < 60:
            return True
        if self._available is False and now - self._checked_at < 5:
            return False
        try:
            req = urllib.request.Request(OLLAMA_TAGS, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as r:
                self._available = r.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            self._available = False
        self._checked_at = now
        return self._available

    def _post(self, payload: dict) -> str:
        try:
            req = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            return (data.get("response") or "").strip()
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return ""

    def generate(self, prompt: str, system: str = "") -> str:
        if not self.available():
            return ""
        text = self._post({
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 80,
                "stop": ["\n\n", "\nUser:", "\nHuman:"],
            },
        })
        return self._tidy(text)

    def generate_json(self, prompt: str, system: str = "") -> str:
        """Strict JSON mode for the router."""
        if not self.available():
            return ""
        return self._post({
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 120,
            },
        })

    @staticmethod
    def _tidy(text: str) -> str:
        line = " ".join(text.split())
        line = line.replace("!", ".")
        for pattern, replacement in _THIRD_PERSON_FIXES:
            line = pattern.sub(replacement, line)
        return line.strip()