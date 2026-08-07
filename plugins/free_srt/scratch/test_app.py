import os
import wave
import math
import struct
import time
import requests

BASE_URL = "http://127.0.0.1:5000"

def create_test_wav(filename):
    print("Generating a test WAV file with a simple 440Hz sine wave...")
    sample_rate = 16000
    duration = 3.0  # seconds
    frequency = 440.0
    num_samples = int(sample_rate * duration)
    
    # 16-bit mono WAV
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        for i in range(num_samples):
            t = float(i) / sample_rate
            value = int(32767.0 * math.sin(2.0 * math.pi * frequency * t))
            data = struct.pack('<h', value)
            wav_file.writeframesraw(data)
    print(f"Generated {filename}")

def run_tests():
    # 1. Check models
    print("\n--- 1. Get models status ---")
    res = requests.get(f"{BASE_URL}/api/models")
    models = res.json()
    for m in models:
        print(f"{m['name']}: {m['status']} ({m['progress']}%)")
        
    # Find base model
    base_model = "ggml-base.bin"
    
    # 2. Start download of base model
    print(f"\n--- 2. Starting download of {base_model} ---")
    res = requests.post(f"{BASE_URL}/api/models/download", json={"filename": base_model})
    print(res.json())
    
    # 3. Poll download status until complete
    print("\n--- 3. Polling download progress ---")
    while True:
        res = requests.get(f"{BASE_URL}/api/models/download-status")
        status = res.json().get(base_model, {})
        state = status.get('status', 'not_started')
        progress = status.get('progress', 0)
        print(f"Download state: {state} | Progress: {progress}%")
        
        if state == 'completed':
            print("Download completed successfully!")
            break
        elif state == 'failed':
            print("Download failed!", status.get('error'))
            return
        elif state == 'not_started':
            # Check if it was already downloaded before running this script
            # In that case /api/models will show downloaded
            res_models = requests.get(f"{BASE_URL}/api/models").json()
            is_downloaded = any(m['filename'] == base_model and m['status'] == 'downloaded' for m in res_models)
            if is_downloaded:
                print("Model was already downloaded.")
                break
        time.sleep(2)
        
    # 4. Generate test audio
    test_wav = "test_audio.wav"
    create_test_wav(test_wav)
    
    # 5. Upload & transcribe
    print(f"\n--- 4. Starting transcription using {base_model} ---")
    with open(test_wav, 'rb') as f:
        files = {'file': (test_wav, f, 'audio/wav')}
        data = {
            'model': base_model,
            'language': 'en',
            'threads': '4'
        }
        res = requests.post(f"{BASE_URL}/api/transcribe", files=files, data=data)
        
    task_info = res.json()
    print("Transcription response:", task_info)
    task_id = task_info.get('task_id')
    if not task_id:
        print("Failed to start transcription job.")
        return
        
    # 6. Poll transcription status
    print("\n--- 5. Polling transcription status ---")
    while True:
        res = requests.get(f"{BASE_URL}/api/transcribe/status/{task_id}")
        job = res.json()
        status = job.get('status')
        progress = job.get('progress')
        print(f"Status: {status} | Progress: {progress}%")
        
        if status == 'completed':
            print("Transcription finished successfully!")
            break
        elif status == 'failed':
            print("Transcription failed!", job.get('error'))
            # Print logs for debugging
            print("\nLogs:")
            print("\n".join(job.get('logs', [])))
            return
        time.sleep(2)
        
    # 7. Get preview of SRT
    print("\n--- 6. Get SRT preview ---")
    res = requests.get(f"{BASE_URL}/api/preview/{task_id}")
    print(res.json().get('content'))
    
    # Clean up test audio
    if os.path.exists(test_wav):
        os.remove(test_wav)
        print("Cleaned up local test audio.")

if __name__ == "__main__":
    time.sleep(1)  # Ensure server is fully ready
    run_tests()
