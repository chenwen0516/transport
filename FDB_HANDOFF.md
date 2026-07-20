# Full-Duplex-Bench（FDB）运行与维护交接

## 1. 交接范围

本工程同时包含官方 FDB v1/v1.5 静态评测、FDB v2 动态评测，以及针对
Health Realtime API 增加的 WebSocket/WebRTC 适配器。本次维护重点是：

- 数据集：`data/`
- WebRTC 主入口：`v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py`
- WebSocket 备选入口：`v1_v1.5/model_inference/health_ws/run_fdb_eval.py`
- 公共评测逻辑：WebRTC 入口复用 `health_ws/run_fdb_eval.py`
- 运行产物：`runs/health_webrtc/<run_id>/`

默认使用 WebRTC/LiveKit 路径。只有目标服务明确提供 WebSocket PCM 接口时，
才使用 `health_ws`。

## 2. FDB 在本工程中的工作流

一次完整运行分为四个阶段：

1. 从 `data/` 按版本、场景和随机种子选择样本，并复制到独立 run 目录。
2. 通过 WebRTC 向被测 Agent 播放 `input.wav`，录制 `output.wav`。
3. 使用 Aliyun FlashRecognizer 或 Qwen3-ASR forced-align 生成带时间戳的
   `output.json`。
4. 运行 FDB 指标脚本，输出场景指标和汇总 `summary.json`。

源数据不会被修改。每次运行都应使用唯一 `run-id`，便于复现、续跑和审计。

版本和场景：

| 版本 | 评测重点 | 常用场景 |
| --- | --- | --- |
| v1.0 | 停顿、接话、轮次切换、打断 | `synthetic_pause_handling`、`candor_pause_handling`、`icc_backchannel`、`candor_turn_taking`、`synthetic_user_interruption` |
| v1.5 | 重叠语音处理 | `user_interruption`、`user_backchannel`、`talking_to_other`、`ambient_speech` |
| 中文集 | 中文场景，运行时映射到 v1.0/v1.5 目录 | `pause_handling`、`turn_taking`、`user_interruption`、`user_backchannel`、`user_interruption_v1.5` |

## 3. 远端部署

部署目录为 `/opt/Full-Duplex-Bench`。不要复制 `.venv/`、`.git/`、
`runs/`、缓存或 `node_modules/`；虚拟环境必须在 Linux 远端重新创建。

从本地同步：

```bash
rsync -az --info=progress2 \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='.uv-cache/' \
  --exclude='runs/' \
  --exclude='**/__pycache__/' \
  --exclude='**/node_modules/' \
  --exclude='.DS_Store' \
  ./ root@113.44.234.195:/opt/Full-Duplex-Bench/
```

远端初始化：

```bash
ssh root@113.44.234.195
cd /opt/Full-Duplex-Bench
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.10
uv sync
```

`uv sync` 包含 ASR/语音质量相关的大依赖。生产维护中应保留 `uv.lock`，
不要在普通执行机上随意升级依赖；依赖升级应单独建分支并重新跑 smoke。

## 4. 凭据配置

凭据只通过远端环境变量或权限为 `600` 的私有环境文件提供，不要写入代码、
README、运行日志或 Git。

WebRTC 二选一：

```bash
export HEALTH_RTC_SESSION_URL='https://<host>/v1/realtime/sessions'
export HEALTH_RTC_TOKEN='<secret>'
```

或前端兼容 token 接口：

```bash
export HEALTH_RTC_TOKEN_URL='https://<host>/api/livekit/token'
export HEALTH_RTC_TOKEN='<secret>'
```

ASR 二选一：

```bash
export ALIYUN_NLS_APPKEY='<appkey>'
export ALIYUN_NLS_TOKEN='<temporary-token>'
```

```bash
export QWEN3_ASR_FORCED_ALIGN_URL='http://127.0.0.1:8000/api/v1/forced-align'
export QWEN3_ASR_LANGUAGE='zh'
```

Aliyun NLS token 有时效，长任务开始前必须刷新。传给下一位维护者时应通过密码
管理器或公司密钥系统交接，不能通过聊天或文档明文交接。

## 5. 验证与演示

### 5.1 无凭据 pipeline smoke

该命令验证 Python 导入、数据集识别、样本选择、run 目录和
manifest/summary 生成，不访问被测服务和 ASR：

```bash
cd /opt/Full-Duplex-Bench
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py smoke \
  --data-root data \
  --run-root runs/health_webrtc \
  --run-id pipeline-smoke \
  --skip-inference \
  --skip-asr \
  --skip-evaluation
```

验收条件：

```bash
test -f runs/health_webrtc/pipeline-smoke/sample_manifest.json
test -f runs/health_webrtc/pipeline-smoke/summary.json
python -m json.tool runs/health_webrtc/pipeline-smoke/summary.json >/dev/null
```

### 5.2 WebRTC 端到端 smoke

先配置 WebRTC 与 ASR 凭据，再执行：

```bash
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py smoke \
  --data-root data \
  --run-root runs/health_webrtc \
  --run-id "smoke-$(date +%Y%m%d-%H%M%S)" \
  --asr-backend aliyun-flash \
  --behavior-backend codex
```

如果使用 Qwen3-ASR：

```bash
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py smoke \
  --data-root data \
  --run-root runs/health_webrtc \
  --run-id "smoke-qwen-$(date +%Y%m%d-%H%M%S)" \
  --asr-backend qwen3-forced-align \
  --forced-align-url "$QWEN3_ASR_FORCED_ALIGN_URL" \
  --behavior-backend codex
```

当前标准数据布局的 smoke 选择
`v1.5/user_interruption/1`。端到端验收应同时满足：

- `summary.json` 存在且 `inference[0].ok` 为 `true`。
- 样本目录内存在非空 `output.wav` 和合法 `output.json`。
- `failures.jsonl` 不存在或为空。
- `warnings` 中没有 `missing_agent_audio_track`、`silent_output`。
- `output_energy.rms`、`peak` 明显大于 0；人工试听输入输出至少一次。

`missing_response_done` 或 `missing_assistant_transcript` 可表示服务端事件不完整；
即使有音频也应记录为接口兼容性问题。

### 5.3 使用硅基流动进行行为评测

远端不依赖 Codex CLI，可以通过 OpenAI-compatible 接口直接使用硅基流动模型：

```bash
export BEHAVIOR_OPENAI_BASE_URL='https://api.siliconflow.cn/v1'
export BEHAVIOR_OPENAI_API_KEY='<siliconflow-api-key>'
export BEHAVIOR_OPENAI_MODEL='<从硅基流动模型广场复制的完整模型ID>'
```

API key 只放在当前 shell、密码管理器或服务器密钥系统中，不要通过
`--behavior-openai-api-key` 写进 shell history。运行端到端 smoke：

```bash
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py smoke \
  --data-root data \
  --run-root runs/health_webrtc \
  --run-id "smoke-siliconflow-$(date +%Y%m%d-%H%M%S)" \
  --asr-backend aliyun-flash \
  --behavior-backend openai
```

对已有 run 只执行评测：

```bash
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py benchmark \
  --data-root data \
  --run-root runs/health_webrtc \
  --run-id '<existing-run-id>' \
  --resume \
  --skip-inference \
  --skip-asr \
  --behavior-backend openai
```

评测会使用 JSON 输出约束，默认每批 20 个样本；批调用两次失败后会降级为逐样本
调用。结果会记录 `base_url` 和模型名，但不会记录 API key。可用参数：

```text
--behavior-openai-timeout-sec 120
--behavior-openai-max-tokens 4096
--behavior-openai-batch-size 20
```

## 6. 正式 benchmark

小批量、固定随机种子验证：

```bash
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py benchmark \
  --data-root data \
  --run-root runs/health_webrtc \
  --run-id "v1-pause-p5-$(date +%Y%m%d-%H%M%S)" \
  --versions v1.0 \
  --scenarios candor_pause_handling synthetic_pause_handling \
  --per-scenario 5 \
  --seed 42 \
  --asr-backend aliyun-flash \
  --behavior-backend codex
```

完整 v1.0/v1.5 示例：

```bash
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py benchmark \
  --data-root data \
  --run-root runs/health_webrtc \
  --run-id "full-p20-$(date +%Y%m%d-%H%M%S)" \
  --versions v1.0 v1.5 \
  --per-scenario 20 \
  --seed 42 \
  --asr-backend aliyun-flash \
  --behavior-backend codex
```

中文数据集：

```bash
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py benchmark \
  --data-root data/Full-Duplex-Bench-zh \
  --dataset-layout zh \
  --run-root runs/health_webrtc_zh \
  --run-id "zh-p20-$(date +%Y%m%d-%H%M%S)" \
  --versions v1.0 v1.5 \
  --per-scenario 20 \
  --seed 42 \
  --asr-backend aliyun-flash \
  --behavior-backend codex
```

正式跑之前必须先通过端到端 smoke，再用 `per-scenario=5` 小批量验证，
最后扩大样本量。不同模型对比必须使用相同数据版本、场景、样本数、seed、
ASR 后端和评审后端。

## 7. 运行产物和结果读取

`runs/health_webrtc/<run_id>/` 中的核心文件：

| 文件 | 用途 |
| --- | --- |
| `sample_manifest.json` | 本次实际选中的源样本，可用于复现 |
| `data/.../output.wav` | Agent 输出音频 |
| `data/.../output.json` | 带时间戳 ASR |
| `data/v1.5/.../clean_output.*` | v1.5 干净输入对应输出 |
| `data/v1.5/.../content_tag.json` | 行为分类 |
| `data/v1.5/.../latency_intervals.json` | 时序区间 |
| `asr_raw/` | ASR 原始响应，定位转写问题 |
| `eval_logs/` | 指标脚本标准输出和错误 |
| `failures.jsonl` | 按阶段记录的失败 |
| `summary.json` | 总结、警告和 `benchmark_metrics` |

交付结果时至少归档 `summary.json`、`sample_manifest.json`、
`failures.jsonl`（若有）、评测日志和实际运行命令。不要只复制表格数字。

## 8. 续跑、重评和常见操作

使用原 `run-id` 续跑，并跳过已有有效音频：

```bash
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py benchmark \
  --data-root data \
  --run-root runs/health_webrtc \
  --run-id '<existing-run-id>' \
  --resume \
  --versions v1.0 v1.5 \
  --per-scenario 20 \
  --seed 42 \
  --asr-backend aliyun-flash \
  --behavior-backend codex
```

只重做 ASR 和评测：

```bash
# 使用已有 run-id；不要删除 output.wav
uv run python v1_v1.5/model_inference/health_webrtc/run_fdb_eval.py benchmark \
  --data-root data \
  --run-root runs/health_webrtc \
  --run-id '<existing-run-id>' \
  --resume \
  --skip-inference \
  --versions v1.0 v1.5 \
  --per-scenario 20 \
  --seed 42 \
  --asr-backend aliyun-flash \
  --behavior-backend codex
```

注意：`--resume` 以已有 `sample_manifest.json` 为准，命令里的抽样参数不会重新
抽样。修改或删除 run 产物前先备份。

## 9. 故障排查

- SSH 连接超时：检查云安全组、主机防火墙、sshd 监听端口和来源 IP 白名单。
- token 请求 401/403：检查 `HEALTH_RTC_TOKEN` 是否过期，以及 Bearer 格式。
- `agent_not_ready`：Agent 未在等待时间内进入 `listening/idle`，先查服务端日志，
  必要时增大 `--wait-agent-ready-sec`。
- `missing_agent_audio_track`：LiveKit 已连接但未订阅 Agent 音轨，检查 Agent 是否
  入房、发布音轨及 token 权限。
- `silent_output`：确认远端音轨、录音采样率和 Agent 是否实际发声。
- ASR 失败：先查 `asr_raw/`；Aliyun token 过期时刷新后只重跑 ASR/评测。
- Codex 行为分类失败：确认执行机可调用 `codex`；也可切换
  `--behavior-backend openai` 并配置对应 API key。
- 指标异常但程序成功：先人工试听，再核对 `output.json` 时间戳和
  `latency_intervals.json`，不要直接相信汇总数字。
- 云执行机出现“ICE connected、音轨已订阅但全部静音”：检查
  `summary.json` 中的 `rtc_stats`。如果 publisher 的 `outbound_rtp` 有发送包，
  但 `remote_inbound_rtp.received.packets_received` 为 0，说明上行 RTP 未到
  LiveKit 对端；应检查云网络 UDP 策略、LiveKit 媒体端口和 TURN/TCP 配置。

## 10. 维护约定

- 不修改 `data/` 内原始样本；所有输出写入 `runs/`。
- 所有可比较实验固定 seed 并保留 manifest。
- 凭据、token、远端密码不入库。
- 新增传输适配器时保持输出文件格式兼容现有 evaluator。
- 每次改动至少运行 Python 编译检查和无凭据 pipeline smoke；涉及网络、音频或
  ASR 的改动必须再跑端到端 smoke。
- 历史 `runs/` 体积增长快，应按 run-id 归档到对象存储，并设置保留策略。

## 11. 本次部署状态

目标主机：`root@113.44.234.195`，部署目录：
`/opt/Full-Duplex-Bench`。

截至 2026-07-07，部署状态如下：

- 已同步源码、锁文件和数据集，远端工程初始传输大小约 3.5GB。
- 已使用 `uv` 安装 CPython 3.10.20，并通过 `uv sync --frozen` 安装 231 个锁定
  依赖；包含 PyTorch 2.11.0、LiveKit 1.1.7、NeMo 2.7.3 和 UTMOSv2。
- 本地和远端均已通过 Python 编译检查。
- 本地和远端均已通过无凭据 pipeline smoke，验证 run-id 为
  `handoff-pipeline-smoke-20260706`。远端成功识别标准数据布局、选择 1 个样本，
  并生成合法的 `sample_manifest.json` 与 `summary.json`。
- 远端关键依赖导入成功。该执行机未检测到 NVIDIA GPU，PyTorch
  `cuda.is_available()` 为 `false`；WebRTC 调用和远程 ASR 不依赖本机 GPU，
  本地运行大型 ASR/语音质量模型时需另选 GPU 执行机。
- 远端未安装 `codex` CLI。运行行为分类时，推荐按第 5.3 节使用硅基流动的
  OpenAI-compatible API；也可以另行安装并认证 Codex。
- 已使用临时凭据执行真实 WebRTC、Qwen3-ASR 和硅基流动评测。2026-07-07
  复跑确认远端已能收到非静音模型输出，静音问题不再复现；当前剩余问题是
  `v1.0/synthetic_user_interruption` 场景的 forced-align ASR 服务返回 502。

2026-07-06 使用临时凭据实际执行了三个验证 run：

- `zh_ziyan_20260630`：中文 5 场景、每场景 1 个样本，推理、Qwen3-ASR 和
  硅基流动评测流程均被调用；7 个输出全部静音，因此 ASR 被静音保护跳过，
  硅基流动正常返回 `C_UNKNOWN`，该 run 不可作为有效 FDB 分数。
- `zh_ziyan_20260706_voicecheck`：改用历史成功配置 `voice=zhixiaobai` 重跑
  v1.5 user_backchannel，仍然静音，排除 voice 配置。
- `zh_ziyan_20260706_rtcdiag`：RTC 统计显示本地已发送 329 个音频 RTP 包，
  对端 `remote_inbound_rtp` 收到 0 个；ICE/DTLS 已连接。结论是该云执行机到
  LiveKit 的上行媒体路径丢包，需要检查 UDP 媒体端口或配置 TURN/TCP。
- timing evaluator 已改用 `soundfile + scipy` 读取 WAV，不再依赖
  `torchaudio` 的可选 `torchcodec`，远端复测 return code 为 0。

2026-07-07 在 ASR 侧修复后执行了两次远端复跑：

- `zh_ziyan_20260707_asr_ok`：中文 5 场景、每场景 1 个样本，`v1.0 + v1.5`，
  `voice=Voice_Clone`，`behavior-backend=openai`，硅基流动模型为
  `deepseek-ai/DeepSeek-V4-Flash`。run 返回码为 0；7 个推理输出均为非静音，
  RMS 约 `0.018` 到 `0.051`，均有 assistant transcript。ASR 7 个输出中 6 个
  成功，唯一失败为 `v1.0/synthetic_user_interruption/7` 的 forced-align ASR
  HTTP 502。v1.5 behavior 评测正常返回，`user_backchannel` 为 `C_RESUME=1.0`，
  `user_interruption` 为 `C_UNKNOWN=1.0`；timing evaluator 均返回 0。
- `zh_ziyan_20260707_asr_retry_ui`：单独重跑
  `v1.0/synthetic_user_interruption`，推理输出仍为非静音，但 forced-align ASR
  对该场景再次返回 HTTP 502。因此当前阻塞点不是 WebRTC 静音，而是 ASR 服务对
  user-interruption 输出的处理失败；后续应优先检查 forced-align 服务的错误日志
  或对该场景切换备用 ASR。

登录密码不得写入文档或磁盘。由于密码曾通过聊天明文提供，交接完成后必须轮换，
并改为 SSH key 登录。
