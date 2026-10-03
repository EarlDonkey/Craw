import sounddevice as sd
import numpy as np
from openwakeword.model import Model
import time

oww = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
print("listening for 20 seconds. say 'hey jarvis' a few times...")

def cb(indata, frames, time_info, status):
    # indata is float32 [-1, 1]. Convert to int16 numpy array.
    chunk = (indata[:, 0] * 32767).astype(np.int16)
    preds = oww.predict(chunk)
    for k, v in preds.items():
        if v > 0.1:
            print(f"  {k}: {v:.3f}")

with sd.InputStream(samplerate=16000, channels=1, dtype="float32", blocksize=1280, callback=cb):
    time.sleep(20)
print("done")