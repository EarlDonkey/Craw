"""Craw's ears.

Listens on the default mic. Watches for a wake word. When it hears it,
captures the utterance, transcribes locally with faster-whisper, and
hands the text to Craw's brain.

Audio never hits disk. Buffer is discarded after transcription.

If any dependency is missing, this sense quietly disables itself and
Craw continues without ears.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable

import numpy as np

WAKE_WORD = "hey_craw"
SAMPLE_RATE = 16000
CHUNK_MS = 80
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_MS / 1000)   # 1280
VAD_SILENCE_MS = 700
MAX_UTTERANCE_S = 12.0
WAKE_THRESHOLD = 0.4


class Ears:
    """Craw's microphone. Calls `on_utterance(text)` when you speak."""

    def __init__(self, on_utterance: Callable[[str], None]) -> None:
        self.on_utterance = on_utterance
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._muted = False

        self._oww = None
        self._vad = None
        self._whisper = None
        self._sd = None

    # --- capability -------------------------------------------------------

    def available(self) -> bool:
        try:
            import sounddevice        # noqa: F401
            import openwakeword      # noqa: F401
            import webrtcvad          # noqa: F401
            import faster_whisper     # noqa: F401
        except ImportError:
            return False
        return True

    # --- lifecycle --------------------------------------------------------

    def start(self) -> None:
        if not self.available():
            print("[ears] deps missing — not starting", flush=True)
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="craw-ears")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def mute(self) -> None:
        self._muted = True

    def unmute(self) -> None:
        self._muted = False

    # --- loading ----------------------------------------------------------

    def _load(self) -> bool:
        try:
            import sounddevice as sd
            from openwakeword.model import Model as OWW
            import webrtcvad
            from faster_whisper import WhisperModel
        except ImportError as exc:
            print(f"[ears] import failed: {exc!r}", flush=True)
            return False

        print("[ears] loading openwakeword...", flush=True)
        self._oww = OWW(wakeword_models=[WAKE_WORD], inference_framework="onnx")
        print("[ears] loading vad...", flush=True)
        self._vad = webrtcvad.Vad(2)
        print("[ears] loading whisper (this is slow)...", flush=True)
        self._whisper = WhisperModel("small", device="cpu", compute_type="int8")
        print("[ears] whisper loaded", flush=True)
        self._sd = sd
        return True

    # --- the loop ---------------------------------------------------------

    def _loop(self) -> None:
        print("[ears] loop starting", flush=True)
        try:
            ok = self._load()
            print(f"[ears] load returned: {ok}", flush=True)
        except Exception as exc:
            import traceback
            print(f"[ears] load raised: {exc!r}", flush=True)
            traceback.print_exc()
            return
        if not ok:
            print("[ears] load failed", flush=True)
            return

        audio_q: "queue.Queue[np.ndarray]" = queue.Queue()

        def callback(indata, frames, time_info, status):   # noqa: ANN001
            chunk = (indata[:, 0] * 32767).astype(np.int16)
            audio_q.put(chunk)

        print("[ears] opening stream", flush=True)
        try:
            with self._sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=CHUNK_SAMPLES,
                callback=callback,
            ):
                print("[ears] stream open — listening", flush=True)
                while not self._stop.is_set():
                    self._tick(audio_q)
        except Exception as exc:
            import traceback
            print(f"[ears] stream error: {exc!r}", flush=True)
            traceback.print_exc()

    def _tick(self, audio_q: "queue.Queue[np.ndarray]") -> None:
        try:
            chunk = audio_q.get(timeout=1.0)
        except queue.Empty:
            return

        if self._muted:
            return

        prediction = self._oww.predict(chunk)
        top = max(prediction.values()) if prediction else 0.0
        if top > 0.02:
            print(f"[ears] wake score: {top:.3f}", flush=True)
        if not any(score > WAKE_THRESHOLD for score in prediction.values()):
            return

        print(f"[ears] WAKE fired (score {top:.3f})", flush=True)

        # flush anything buffered before the wake fired, so _record only
        # captures the utterance that comes after the wake word
        while not audio_q.empty():
            try:
                audio_q.get_nowait()
            except queue.Empty:
                break

        frames = self._record(audio_q)
        if not frames:
            return

        text = self._transcribe(frames)
        print(f"[ears] transcribed: {text!r}", flush=True)
        if not text.strip():
            return
        try:
            self.on_utterance(text.strip())
        except Exception as exc:
            print(f"[ears] on_utterance raised: {exc!r}", flush=True)

    def _record(self, audio_q: "queue.Queue[np.ndarray]") -> list[np.ndarray]:
        frames: list[np.ndarray] = []
        silence_chunks = 0
        silence_limit = int(VAD_SILENCE_MS / CHUNK_MS)
        deadline = time.time() + MAX_UTTERANCE_S

        while time.time() < deadline and not self._stop.is_set():
            try:
                chunk = audio_q.get(timeout=0.5)
            except queue.Empty:
                break
            frames.append(chunk)
            try:
                pcm = chunk.astype(np.int16).tobytes()
                is_speech = self._vad.is_speech(pcm, SAMPLE_RATE)
            except Exception:
                is_speech = True
            if is_speech:
                silence_chunks = 0
            else:
                silence_chunks += 1
                if silence_chunks >= silence_limit and len(frames) > silence_limit * 2:
                    break
        return frames

    def _transcribe(self, frames: list[np.ndarray]) -> str:
        if not frames:
            return ""
        try:
            audio = np.concatenate(frames).astype("float32") / 32768.0
            segments, _ = self._whisper.transcribe(audio, language="en", beam_size=1)
            return " ".join(seg.text for seg in segments).strip()
        except Exception as exc:
            print(f"[ears] transcribe failed: {exc!r}", flush=True)
            return ""