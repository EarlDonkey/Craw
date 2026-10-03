"""Craw's connection to its mind.

Talks to a local ollama instance. If ollama isn't running, Craw doesn't
die — it just goes quiet and lets the rule-based voice take over, so the
creature survives its own fainting.

Never used for the face. Only used for speech.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "llama3.2:3b"


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL, timeout: float = 30.0) -> None:
        self.model = model
        self.timeout = timeout
        self._available: bool | None = None

    def available(self) -> bool:
        """Cheap check — has ollama answered us recently?"""
        if self._available is False:
            return False
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=2.0) as r:
                self._available = r.status == 200
                return self._available
        except (urllib.error.URLError, TimeoutError, OSError):
            self._available = False
            return False

    def generate(self, prompt: str, system: str = "") -> str:
        """One-shot. Non-streaming for now. Returns the text or ''."""
        if not self.available():
            return ""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 80,      # short answers
                "stop": ["\n\n", "\nUser:", "\nHuman:"],
            },
        }
        try:
            req = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            text = (data.get("response") or "").strip()
            return self._tidy(text)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            self._available = False
            return ""

    @staticmethod
    def _tidy(text: str) -> str:
        line = " ".join(text.split())
        # Craw doesn't shout.
        line = line.replace("!", ".")
        return line.strip()