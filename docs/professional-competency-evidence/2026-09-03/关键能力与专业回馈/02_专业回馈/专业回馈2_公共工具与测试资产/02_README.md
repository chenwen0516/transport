# Pipeline Voice E2E

This suite evaluates multi-turn Pipeline Agent conversations through a real
LiveKit room.

The execution path is:

1. read multi-turn JSONL scenarios;
2. synthesize every user turn with the configured Qwen3 TTS websocket;
3. keep one LiveKit room open for every complete scenario;
4. publish each WAV as a microphone track in real time;
   scenarios with `video_fixture` also publish a deterministic camera track;
5. capture user/assistant LiveKit transcriptions, Agent output WAV, and the
   content-free `intent-routing-trace` data packet;
6. apply deterministic checks for STT accuracy, route/action/skills/slots,
   tool execution, response text, output audio, and timing;
7. write JSON and Markdown reports.

Before running the Agent, enable routing trace publication:

```bash
export INTENT_ROUTING_TRACE_DATA=true
```

Prepare audio:

```bash
python evaluation/pipeline_voice_e2e/run_pipeline_voice_e2e.py prepare-audio \
  --tts-ws-url "$QWEN_TTS_WS_URL" \
  --voice Voice_Clone \
  --sample-rate 24000
```

Run selected scenarios:

```bash
python evaluation/pipeline_voice_e2e/run_pipeline_voice_e2e.py run \
  --livekit-url ws://127.0.0.1:7880 \
  --livekit-api-key "$LIVEKIT_API_KEY" \
  --livekit-api-secret "$LIVEKIT_API_SECRET" \
  --agent-name health-assistant-ziyan-dev \
  --scenario-id mt-weather-context \
  --scenario-id mt-web-cache-isolation
```

The default dataset is
`datasets/multiturn_v0.1.jsonl`. Each scenario gets a fresh room; all turns
inside a scenario share that room and Agent session.

The rule judge is the release gate. An optional LLM judge can be added later
for style and semantic quality, but it must not override an incorrect route,
slot, invocation, missing subtitle, or missing output audio.

When LiveKit is served on loopback, start both the worker and evaluator with
`HTTP_PROXY`/`HTTPS_PROXY` cleared. LiveKit Agents 1.5.6 passes those proxy
variables explicitly to the worker WebSocket and does not honor `NO_PROXY`
for this connection.
