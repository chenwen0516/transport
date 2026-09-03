# NoiseGate + MMI-FD Test Plan

目标：先在不启用 SpeakerGate 的前提下，把前端 NoiseGate + 后端 MMI-FD 的全双工打断体验调到可衡量、可复现、可迭代。

## Scope

- SpeakerGate 默认关闭，避免声纹身份信号影响本轮结论。
- 前端 WebRTC NoiseGate 开启，`NEXT_PUBLIC_NOISE_GATE_DISABLED` 不能为 `true`。
- 后端 MMI-FD 使用 active 模式，建议本地调试 `MMI_TD_ACTIVE_PERCENTAGE=100`。
- 每轮测试保留 `backend/livekit_agent/tmp` 下的 MMI 日志、session report、raw/stt WAV。

## Metrics

核心指标：

- `interrupt_count`: MMI 主动输出 `START_LISTENING` 的次数。
- `missed_interrupt_count`: 明确打断用例中没有 `START_LISTENING`，只在之后 `START_SPEAKING` 或自然停顿后生效。
- `false_interrupt_count`: 背景人声、噪声、backchannel 导致 `START_LISTENING`。
- `interrupt_latency_ms`: 用户开始打断或首个打断 transcript 到 `START_LISTENING` 的耗时，目标 p50 <= 800ms，p90 <= 1200ms。
- `low_voice_confidence_observe`: NoiseGate 低置信度导致延迟观察的次数。合理存在，但不应最终吞掉有效打断。
- `low_voice_confidence_suppressed`: 目标应为 0；该值大于 0 表示又出现了低置信度直接吃掉打断。
- `ignore_input_count`: 应只出现在明确 backchannel、噪声或背景人声场景。
- `commit_with_low_confidence`: 低置信度仍提交的正常用户轮次。不是必然错误，但过高说明 NoiseGate confidence 作为语音质量信号不稳定。
- `gate_closed_snapshot_ratio`: 一般弱噪声场景 10%-40% 可接受；接近 0 表示门控太松，过高表示可能漏字。
- `external_voice_confidence median`: agent speaking 期间可以偏低，但 listening 期间如果长期接近 0，NoiseGate 阈值过严。

## Test Cases

每轮建议按顺序跑完以下 8 类，录成同一个 session，结束后运行分析脚本。

| ID | 场景 | 操作脚本 | 预期 |
| --- | --- | --- | --- |
| T01 | 安静首轮对话 | 用户说「你好，你好」 | 正常 `START_SPEAKING`，无打断 |
| T02 | 安静完整问题 | 用户说「给我详细介绍一本好看的小说，关于泉州的」 | 正常提交，endpointing 不拖到 max delay |
| T03 | 强打断 | agent 说话中说「别说了」或「等一下」 | `START_LISTENING`，p90 <= 1200ms |
| T04 | 命令式短打断 | agent 说话中说「换一个」「再换一个」「原文，原文」 | 应 `START_LISTENING` 或在命令 interrupt 规则下快速停止 |
| T05 | 继续补充 | agent 说话中说「详细介绍一下」「跟泉州相关的历史小说」 | 应停止 agent 并提交新用户轮次 |
| T06 | backchannel | agent 说话中只说「嗯嗯」「好的」 | 不应打断；可 `CONTINUE_SPEAKING` + `ignore_input=true` |
| T07 | 弱背景人声 | 手机外放低音量背景人声，用户不说话 | 不应打断，不应产生有效用户 turn |
| T08 | 弱背景人声 + 真实用户打断 | 背景人声持续，用户说「换一个」 | 应打断；不能因为 low voice confidence 被吞 |

## Commands

从仓库根目录运行：

```bash
python3 backend/livekit_agent/evaluation/analyze_noisegate_mmi.py backend/livekit_agent/tmp --latest 1
```

从 `backend/livekit_agent` 目录运行：

```bash
python3 evaluation/analyze_mmi_log.py tmp/runs/*/mmi_turn_detection_active_*.log
```

## First-Pass Thresholds

调试阶段建议：

```env
MMI_TD_STRONG_INTERRUPT_MIN_MS=300
MMI_TD_ORDINARY_INTERRUPT_MIN_MS=600
MMI_TD_ORDINARY_INTERRUPT_MIN_CHARS=3
MMI_TD_STT_ONLY_FINAL_INTERRUPT_MIN_MS=250
MMI_TD_STT_ONLY_FINAL_INTERRUPT_MIN_CHARS=2
MMI_TD_OBSERVE_MS=250
MMI_TD_MAX_OBSERVE_MS=800
```

如果 T07 背景人声误打断，优先增加文本规则和 backchannel/noise 识别，不优先把 `ordinary_interrupt_min_ms` 拉回 1000ms；否则会伤害 T04/T05。

## Pass Criteria

一轮可接受标准：

- T03/T04/T05/T08 的 `START_LISTENING` 命中率 >= 90%。
- T03/T04/T05/T08 的 p90 interrupt latency <= 1200ms。
- T06/T07 的 false interrupt 为 0。
- `low_voice_confidence_suppressed == 0`。
- 没有 `agent stopped during active user input without MMI START_LISTENING` 警告。

## Loop

1. 按 Test Cases 跑一次通话，保留 `tmp`。
2. 跑 `analyze_noisegate_mmi.py --latest 1`。
3. 对照 Pass Criteria 找失败类型。
4. 只改一类参数或规则。
5. 重跑同一套 Test Cases。
