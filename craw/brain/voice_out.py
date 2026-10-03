"""Craw's out-loud voice.

Wraps Piper: text in, WAV out, then playback via Windows native audio.
Everything runs in a background thread so the daemon's heartbeat is
never blocked by audio.

Uses winsound (not sounddevice) so it can't interfere with the mic
stream. Uses SND_ASYNC so it doesn't hold the audio device.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path


DEFAULT_PIPER_DIR = Path(os.environ.get("USERPROFILE", ".")) / "piper"
DEFAULT_MODEL = "en_US-ryan-medium.onnx"


class Speaker:
    def __init__(
        self,
        piper_dir: Path = DEFAULT_PIPER_DIR,
        model: str = DEFAULT_MODEL,
        enabled: bool = True,
    ) -> None:
        self.piper_dir = Path(piper_dir)
        self.model = model
        self.enabled = enabled
        self._lock = threading.Lock()

    def available(self) -> bool:
        piper_exe = self.piper_dir / "piper.exe"
        model_file = self.piper_dir / self.model
        return piper_exe.exists() and model_file.exists()

    def say(self, text: str) -> None:
        """Fire-and-forget. Renders and plays audio on a background thread."""
        if not self.enabled or not text.strip():
            return
        if not self.available():
            return
        threading.Thread(target=self._say_now, args=(text,), daemon=True).start()

    def _say_now(self, text: str) -> None:
        with self._lock:
            try:
                wav = self._render(text)
                if wav:
                    self._play(wav)
            except Exception:
                pass

    def _render(self, text: str) -> Path | None:
        tmp = Path(tempfile.gettempdir()) / f"craw_voice_{os.getpid()}.wav"
        cmd = [
            str(self.piper_dir / "piper.exe"),
            "--model", str(self.piper_dir / self.model),
            "--output_file", str(tmp),
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=15,
                cwd=str(self.piper_dir),
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if proc.returncode != 0 or not tmp.exists():
            return None
        return tmp

    def mute(self) -> None:
        self.enabled = False

    def unmute(self) -> None:
        self.enabled = True

    @staticmethod
    def _play(wav: Path) -> None:
        """Play through Windows native audio, async so it doesn't hold
        the output device and starve the mic stream."""
        try:
            import winsound
            winsound.PlaySound(
                str(wav),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except Exception:
            pass