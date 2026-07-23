import asyncio
import websockets
import numpy as np
import time
import os
import json
import soundfile as sf
from jiwer import wer

# --- Configuration ---
WS_URL = "ws://127.0.0.1:8000/ws"
# Set this based on your WORKERS_PER_DEVICE (e.g., 2 workers = 10-20 concurrency)
MAX_CONCURRENT_CONNECTIONS = 10 
LANGUAGE = "eng" #Select eng or cn
if LANGUAGE == "eng":
    DATA_DIR = "/data/nfs_211/hwx1322329/dataset/LibriSpeech/LibriSpeech/test-clean"
elif LANGUAGE == "cn":
    DATA_DIR = "/data/nfs_211/hwx1322329/dataset/MagicData/Chineese-Mandarin/dev"

# -------------------------
# Data Loader
# -------------------------
def load_librispeech(folder):
    samples = []
    for root, _, files in os.walk(folder):
        trans_file = next((f for f in files if f.endswith(".trans.txt")), None)
        if not trans_file: continue
        
        with open(os.path.join(root, trans_file), "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(" ", 1)
                if len(parts) == 2:
                    audio_path = os.path.join(root, f"{parts[0]}.flac")
                    if os.path.exists(audio_path):
                        samples.append({"path": audio_path, "ref": parts[1]})
    return samples

def load_magicdata(folder):
    samples = []
    trans_path = os.path.join(folder, "TRANS.txt")
    
    if not os.path.exists(trans_path):
        print(f"Error: {trans_path} not found.")
        return []

    with open(trans_path, "r", encoding="utf-8") as f:
        header = next(f) 
        
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                wav_name = parts[0]
                rel_folder = parts[1]
                transcription = parts[2]
                
                audio_path = os.path.join(folder, rel_folder, wav_name)
                
                if os.path.exists(audio_path):
                    samples.append({
                        "path": audio_path, 
                        "ref": transcription
                    })
    return samples

# -------------------------
# Normalize
# -------------------------
def normalize(text):
    import re
    if LANGUAGE == "eng":
        return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()
    elif LANGUAGE == "cn":
        return re.sub(r"[^a-z0-9\u4e00-\u9fa5]", "", text.lower()).strip()
    

# -------------------------
# Optimized Client (Firehose)
# -------------------------
async def run_client(sample, semaphore):
    async with semaphore:
        try:
            # Pre-processing
            wav, sr = sf.read(sample["path"], dtype="float32")
            if wav.ndim > 1: wav = wav.mean(axis=1)
            audio_dur = len(wav) / sr
            
            async with websockets.connect(WS_URL, open_timeout=30, ping_interval=None) as ws:
                start_time = time.time()

                step = int(sr * 0.5) # 1.0s chunks for optimal RTF/Throughput
                for i in range(0, len(wav), step):
                    chunk = wav[i:i+step]
                    await ws.send(chunk.tobytes())

                # Signal the end of audio
                await ws.send(json.dumps({"text": "END"}))
                
                # Drain messages until we hit the 'final' result
                final_text = ""
                while True:
                    raw_resp = await ws.recv()
                    resp = json.loads(raw_resp)
                    if resp.get("type") == "final":
                        final_text = resp.get("text", "")
                        break
                
                latency = time.time() - start_time
                
                # Metrics calculation
                hyp = normalize(final_text)
                ref = normalize(sample["ref"])
                """print("Transcription: ", hyp)
                print("Reference    : ", ref)
                print("\n")"""
                
                if LANGUAGE == "eng": 
                    count = len(ref)
                elif LANGUAGE == "cn":
                    count = len(ref.split())
                return {
                    "latency": latency,
                    "rtf": latency / audio_dur,
                    "wer": wer(ref, hyp),
                    "char_count": len(ref),
                    "word_count": len(ref), #For english len(ref.split()) but for chineese len(ref)
                    "success": True
                }
        except Exception as e:
            print(f"Error processing {sample['path']}: {e}")
            return {"success": False}

# -------------------------
# Main Runner
# -------------------------
async def main(num_samples=100):
    print(f"Loading metadata from {DATA_DIR}...")
    if LANGUAGE == "eng":
        all_samples = load_librispeech(DATA_DIR)
    elif LANGUAGE == "cn":
        all_samples = load_magicdata(DATA_DIR)
    dataset = all_samples[:num_samples]

    if not dataset:
        print("No samples found. Check DATA_DIR.")
        return

    print(f"Starting benchmark: {num_samples} samples | Concurrency: {MAX_CONCURRENT_CONNECTIONS}")
    sem = asyncio.Semaphore(MAX_CONCURRENT_CONNECTIONS)
    
    # Warm-up (The NPU Graph Compilation takes 1-2 seconds on the first run)
    print("Performing NPU warm-up...")
    await run_client(dataset[0], sem)

    print("Starting benchmarking...")
    start_wall_time = time.time()
    tasks = [run_client(s, sem) for s in dataset]
    results = await asyncio.gather(*tasks)
    end_wall_time = time.time()

    # Post-process results
    flat = [r for r in results if r.get("success")]
    if not flat:
        print("All requests failed.")
        return

    total_audio_time = sum((len(sf.read(s["path"])[0]) / sf.read(s["path"])[1]) for s in dataset)
    wall_time = end_wall_time - start_wall_time
    
    avg_wer = sum(r["wer"] for r in flat) / len(flat)
    total_chars = sum(r["char_count"] for r in flat)
    total_words = sum(r["word_count"] for r in flat)
    
    # True System RTF (Total throughput)
    system_rtf = wall_time / total_audio_time

    print(f"\n{'='*45}")
    print(f"       FINAL NPU STREAMING RESULTS")
    print(f"{'='*45}")
    print(f"Samples Processed:   {len(flat)}/{num_samples}")
    print(f"Total Words:         {total_words:,}")
    print(f"Total Characters:    {total_chars:,}")
    print(f"Avg WER:             {avg_wer * 100:.2f}%")
    print(f"System Throughput:   {total_audio_time/wall_time:.2f}x Real-time")
    print(f"System RTF:          {system_rtf:.4f}")
    print(f"Total Wall Time:     {wall_time:.2f}s")
    print(f"{'='*45}")

if __name__ == "__main__":
    # Raise file limit for high concurrency
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (max(soft, 4096), hard))
    except:
        pass

    asyncio.run(main(num_samples=100))