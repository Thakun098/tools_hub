import math
import os
import struct
import sys
import time
import wave

import requests

base_url = sys.argv[1]
model_name = "ggml-base.bin"
test_wav = os.path.join(os.path.dirname(__file__), "portable-smoke.wav")
with wave.open(test_wav, "wb") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(16000)
    for index in range(16000 * 2):
        value = int(12000 * math.sin(2 * math.pi * 440 * index / 16000))
        wav_file.writeframesraw(struct.pack("<h", value))

try:
    with open(test_wav, "rb") as audio:
        response = requests.post(
            f"{base_url}/api/transcribe",
            files={"file": ("portable-smoke.wav", audio, "audio/wav")},
            data={"model": model_name, "language": "en", "threads": "2"},
            timeout=30,
        )
    print("start", response.status_code, response.text)
    response.raise_for_status()
    task_id = response.json()["task_id"]
    deadline = time.time() + 180
    while time.time() < deadline:
        job = requests.get(f"{base_url}/api/transcribe/status/{task_id}", timeout=5).json()
        print(job.get("status"), job.get("progress"), job.get("error"))
        if job.get("status") in {"completed", "failed", "cancelled"}:
            if job.get("status") != "completed":
                raise RuntimeError(f"Portable transcription failed: {job}")
            print("PORTABLE_TRANSCRIPTION_OK")
            break
        time.sleep(1)
    else:
        raise TimeoutError("Portable transcription timed out")
finally:
    if os.path.exists(test_wav):
        os.remove(test_wav)
