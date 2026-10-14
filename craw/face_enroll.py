"""Take 5 photos of your face, save the average embedding.

Usage:
    python -m craw.face_enroll
"""

from __future__ import annotations

import time
from pathlib import Path

from craw.state import CRAW_HOME

KNOWN_FACE_PATH = CRAW_HOME / "face.npy"


def main() -> int:
    try:
        import cv2
        import face_recognition
        import numpy as np
    except ImportError as exc:
        print(f"missing dependency: {exc}")
        print("run: py -m pip install opencv-python face-recognition")
        return 1

    print("starting webcam...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("couldn't open webcam")
        return 1

    print("look at the camera. capturing 5 frames over 10 seconds.")
    print("press Ctrl+C to cancel.\n")

    samples = []
    last_capture = 0.0
    try:
        while len(samples) < 5:
            ret, frame = cap.read()
            if not ret:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            small = cv2.resize(rgb, (0, 0), fx=0.25, fy=0.25)
            locations = face_recognition.face_locations(small)
            if not locations:
                time.sleep(0.1)
                continue
            if time.time() - last_capture < 2.0:
                continue
            encodings = face_recognition.face_encodings(small, locations)
            if encodings:
                samples.append(encodings[0])
                last_capture = time.time()
                print(f"captured {len(samples)}/5")
    except KeyboardInterrupt:
        print("\ncancelled.")
        cap.release()
        return 1

    cap.release()

    if len(samples) < 3:
        print("not enough samples — try again with better lighting")
        return 1

    avg = np.mean(samples, axis=0)
    CRAW_HOME.mkdir(parents=True, exist_ok=True)
    np.save(KNOWN_FACE_PATH, avg)
    print(f"\nsaved {KNOWN_FACE_PATH}")
    print("done.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())