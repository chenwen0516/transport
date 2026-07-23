import os
import asyncio
import ray
import numpy as np
import time
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# Optimization Environment Variables for Ascend NPU
os.environ["ACL_GRAPH_CONFIG"] = "1" # Force Graph Mode
os.environ["PYTORCH_NPU_ALLOC_CONF"] = "expandable_segments:True"

# --- Configuration ---
# You can move these to a yaml/env file later
MODEL_PATH = "/data/nvme-0/models/Qwen3-ASR-1.7B"
AVAILABLE_DEVICES = [0]  # List of NPU IDs, e.g., [0, 1, 2, 3]
WORKERS_PER_DEVICE = 2   # How many instances share one NPU
NUM_CPUS_PER_WORKER = 4

app = FastAPI()

# 1. Initialize Ray
if not ray.is_initialized():
    ray.init(ignore_reinit_error=True, num_cpus=124)

# 2. Define the Ray Actor
@ray.remote(num_cpus=NUM_CPUS_PER_WORKER)
class TranscriberActor:
    def __init__(self, model_path, device_id):
        from qwen_asr import Qwen3ASRModel
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = str(device_id)
        self.asr = Qwen3ASRModel.LLM(
            model=model_path,
            gpu_memory_utilization=(0.8 / WORKERS_PER_DEVICE) - 0.01,
            max_model_len=8192,  # Reduced from 65536 - 32768 - 16384 - 8192 - 4096
            max_new_tokens=32
        )
        # Store states locally in the actor's memory
        self.sessions = {}

    def init_session(self, session_id):
        self.sessions[session_id] = self.asr.init_streaming_state(
            unfixed_chunk_num=1, unfixed_token_num=4, chunk_size_sec=1.5
        )

    def transcribe_chunk(self, session_id, audio_bytes):
        state = self.sessions.get(session_id)
        if not state: return "Error: Session not found"
        
        audio = np.frombuffer(audio_bytes, dtype=np.float32)
        self.asr.streaming_transcribe(audio, state)
        # Only return the text string back to FastAPI, not the whole state
        return state.text

    def finalize_session(self, session_id):
        state = self.sessions.pop(session_id, None)
        if state:
            self.asr.finish_streaming_transcribe(state)
            return state.text
        return ""

# 3. Create the Actor Pool
target_devices = [dev for dev in AVAILABLE_DEVICES for _ in range(WORKERS_PER_DEVICE)]
actors = [TranscriberActor.remote(MODEL_PATH, dev_id) for dev_id in target_devices]

# 4. Use an Async Queue to manage availability (Load Balancer)
actor_pool = asyncio.Queue()
for actor in actors:
    actor_pool.put_nowait(actor)

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    
    actor = await actor_pool.get()
    session_id = str(id(ws)) # Unique ID for this connection
    
    # Initialize the session on the worker
    await actor.init_session.remote(session_id)
    start_time = time.time()

    try:
        while True:
            msg = await ws.receive()

            if "bytes" in msg:
                # Pass only the ID and the bytes. 
                # No more 'Invalid type of object refs' errors!
                text = await actor.transcribe_chunk.remote(session_id, msg["bytes"])
                await ws.send_json({"type": "partial", "text": text})

            elif "text" in msg:
                if "END" in msg["text"]:
                    final_text = await actor.finalize_session.remote(session_id)
                    await ws.send_json({
                        "type": "final", 
                        "text": final_text, 
                        "latency": time.time() - start_time
                    })
                    break
    finally:
        # Cleanup and return actor to pool
        await actor.finalize_session.remote(session_id)
        actor_pool.put_nowait(actor)

@app.get("/health")
def health_check():
    return {"status": "OK", "total_workers": len(actors), "available": actor_pool.qsize()}


if __name__ == "__main__":
    import uvicorn
    # Use multiple workers for the FastAPI app if needed, 
    # but usually 1 is enough since Ray handles the heavy lifting.
    uvicorn.run(app, host="0.0.0.0", port=8000)