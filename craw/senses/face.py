"""Craw's eyes on who's at the laptop.

Takes a webcam frame every N seconds, detects a face, compares to a
known face stored at .craw/face.npy. Returns one of:
  "henri" — matches the stored face
  "someone else" — a face is present but doesn't match
  "nobody" — no face in frame
  "camera unavailable" — webcam off, in use, or blocked

Fails open — if anything goes wrong, returns "camera unavailable"
and does nothing. This is a sense, not a lock. It never locks the
machine. It never refuses access. It only reports.
"""

from __future__ import annotations

import time
from pathlib import Path

from craw.state import CRAW_HOME

KNOWN_FACE_PATH = CRAW_HOME / "face.npy"
MATCH_TOLERANCE = 0.5   # lower = stricter; 0.5 is a common default
CHECK_INTERVAL = 30.0   # seconds between checks


class FaceSense:
    name = "face"
    interval_seconds = CHECK_INTERVAL

    def __init__(self) -> None:
        self._known = None
        self._last_face = "unknown"
        self._last_check = 0.0

    def available(self) -> bool:
        try:
            import cv2          # noqa: F401
            import face_recognition  # noqa: F401
        except ImportError:
            return False
        return KNOWN_FACE_PATH.exists()

    def who(self) -> str:
        """Return who's at the laptop, right now."""
        if not self.available():
            return "camera unavailable"
        try:
            import cv2
            import face_recognition
            import numpy as np
        except ImportError:
            return "camera unavailable"

        try:
            if self._known is None:
                self._known = np.load(KNOWN_FACE_PATH)
        except Exception:
            return "camera unavailable"

        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return "camera unavailable"
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return "camera unavailable"

            # Convert BGR (OpenCV) to RGB (face_recognition)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Downscale for speed
            small = cv2.resize(rgb, (0, 0), fx=0.25, fy=0.25)

            locations = face_recognition.face_locations(small)
            if not locations:
                return "nobody"

            encodings = face_recognition.face_encodings(small, locations)
            if not encodings:
                return "nobody"

            # Compare each detected face to the known one
            distances = face_recognition.face_distance([self._known], encodings[0])
            if len(distances) == 0:
                return "someone else"

            if distances[0] < MATCH_TOLERANCE:
                return "henri"
            return "someone else"

        except Exception:
            return "camera unavailable"