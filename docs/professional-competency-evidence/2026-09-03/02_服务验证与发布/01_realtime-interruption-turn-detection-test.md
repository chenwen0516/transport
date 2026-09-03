# 全双工语音助手 — 打断 & 轮次检测自动化测试方案

> 版本：v1.0 | 日期：2026-04-10

---

## 1. 目标

验证语音助手的两个核心实时交互能力：

1. **打断（Barge-in）**：用户说话即打断 Agent（纯 VAD 驱动），测试准确率、误打断率、时延
2. **轮次检测（Turn Detection）**：硬阈值 2s（<2s 一律不切轮，即使 ASR 已返回；>2s 切轮）

---

## 2. 关键配置参数

| 参数 | 当前值 | 来源 |
|---|---|---|
| `min_silence_duration` | 0.55s | `config.py` VADConfig |
| `min_speech_duration` | 0.05s | `config.py` |
| `activation_threshold` | 0.5 | `config.py` |
| Turn Detection | LiveKit recommended defaults + MultilingualModel | `turn_handling.py` |
| 音频输入格式 | pcm16 (16kHz/16bit/mono/LE) | WS API 协议 |

### 产品需求阈值

- 停顿 < 1s → **不切轮**
- 停顿 1s ~ 2s → **不切轮**（即使 ASR 有返回）
- 停顿 > 2s → **切轮**

---

## 3. 双模式测试

### Mock Mode（CI 回归）

- **目的**：隔离 VAD + 打断链路，排除 LLM/TTS 变量
- **实现**：`AGENT_MODE=mock` 环境变量切换，MockLLM（固定回复）+ MockTTS（固定时长正弦波）
- **VAD 保持真实** Silero VAD，不 Mock

```bash
AGENT_MODE=mock pytest backend/livekit_agent/test/realtime/ -m "not real_only" --tb=short
```

### Real Mode（端到端验收）

- **目的**：真实 LLM/TTS/STT 全链路验证
- **配置**：指定真实服务地址和 API Key

```bash
AGENT_MODE=real \
  WS_URL=wss://api.health.com/v1/realtime \
  AUTH_TOKEN=sk-health-xxx \
  pytest backend/livekit_agent/test/realtime/ -m "not mock_only" --tb=short
```

---

## 4. 目录结构

```
backend/livekit_agent/test/realtime/
├── conftest.py                # pytest fixtures
├── pytest.ini                 # pytest 配置
├── requirements-test.txt      # 测试依赖
├── core/
│   ├── ws_test_client.py      # WebSocket 测试客户端
│   ├── audio_generator.py     # PCM 音频生成器
│   ├── metrics.py             # 指标计算
│   └── report.py              # 测试报告
├── fixtures/
│   └── generate_fixtures.py   # 音频素材生成（可选 TTS API）
├── mock_agent/
│   └── mock_agent.py          # MockLLM + MockTTS
├── scenarios/
│   ├── interruption.yaml      # 打断测试场景
│   └── turn_detection.yaml    # 轮次检测场景
├── test_smoke.py              # 冒烟测试
├── test_interruption.py       # 打断测试
└── test_turn_detection.py     # 轮次检测测试
```

---

## 5. 测试场景

### 5.1 打断测试

| 场景 | 音频类型 | 预期 | 说明 |
|---|---|---|---|
| barge_in_clear_speech | speech_like 2s | 打断 | Agent 说话中注入清晰语音 |
| barge_in_short_word | speech_like 500ms | 打断 | 注入短词 |
| barge_in_late_phase | speech_like 1s | 打断 | Agent 快说完时打断 |
| no_barge_in_white_noise | white_noise 2s | 不打断 | 白噪声不应触发 |
| no_barge_in_silence | silence 2s | 不打断 | 纯静音不应触发 |
| no_barge_in_low_amplitude | noise 0.02 amp | 不打断 | 极低音量 |
| no_barge_in_sine_wave | sine 440Hz 2s | 不打断 | 纯正弦波非语音 |

### 5.2 轮次检测测试

| 场景 | 停顿时长 | 预期 | 说明 |
|---|---|---|---|
| turn_normal_2500ms | 2.5s | 切轮 | 超过 2s 阈值 |
| turn_normal_3000ms | 3.0s | 切轮 | 明确超时 |
| turn_boundary_2100ms | 2.1s | 切轮 | 刚过阈值 |
| no_turn_500ms | 0.5s 中间停顿 | 不切轮 | 正常停顿 |
| no_turn_800ms | 0.8s 中间停顿 | 不切轮 | 正常停顿 |
| no_turn_1500ms | 1.5s 中间停顿 | 不切轮 | 灰色地带 |
| no_turn_1900ms | 1.9s 中间停顿 | 不切轮 | 接近阈值 |
| long_speech_with_breaths | <500ms 换气 | 不切轮 | 长语音换气 |

---

## 6. 通过标准

| 指标 | Mock Mode | Real Mode |
|---|---|---|
| 打断准确率 | ≥ 98% | ≥ 95% |
| 误打断率 | ≤ 2% | ≤ 5% |
| 打断时延 P95 | ≤ 500ms | ≤ 800ms |
| 端点检测准确率 | ≥ 95% | ≥ 90% |
| 误切轮率（<2s 被抢答） | ≤ 3% | ≤ 10% |
| 漏切轮率（>2s 不回复） | ≤ 2% | ≤ 5% |
| 端点时延 P95 | ≤ 1000ms | ≤ 2000ms |

---

## 7. 核心模块说明

### WebSocket 测试客户端 (`ws_test_client.py`)

- 后台 `asyncio.Task` 持续收集事件 + `time.monotonic()` 精确时间戳
- `inject_audio()` 按 100ms 一帧发送（3200 bytes/帧）
- 事件查询 API：`get_events()`, `has_event_after()`, `wait_for_agent_state()` 等

### 音频生成器 (`audio_generator.py`)

- `speech_like()`: 多谐波（100-2550Hz）叠加 + 包络调制（模拟音节节奏），触发 VAD
- `silence()`: 全零 PCM
- `white_noise()` / `low_amplitude_noise()`: 噪声干扰测试

### 指标计算 (`metrics.py`)

- `InterruptionResult`: 单次打断的 VAD 延迟、打断完成延迟、端到端延迟
- `TurnDetectionResult`: 端点检测延迟
- `MetricsAggregator`: 聚合计算准确率、误报率、百分位延迟

---

## 8. 风险与应对

| 风险 | 应对 |
|---|---|
| 合成正弦波无法触发 VAD | 使用多谐波+包络调制；备选：录制真实语音 PCM fixture |
| Real Mode 下 LLM/TTS 延迟导致超时 | 放宽超时（turn_timeout=8s），retry 消除偶发失败 |
| agent.state_changed 事件延迟 | 同时观察 audio.delta 停止作为打断辅助判定 |
| 轮次检测中 ASR 返回影响判定 | 同时监听 transcription.completed，验证 <2s 即使有 ASR 也不切轮 |

---

## 9. 测试依赖

```
pytest>=8.0
pytest-asyncio>=0.23
websockets>=12.0
numpy>=1.26
pyyaml>=6.0
tabulate>=0.9
```
