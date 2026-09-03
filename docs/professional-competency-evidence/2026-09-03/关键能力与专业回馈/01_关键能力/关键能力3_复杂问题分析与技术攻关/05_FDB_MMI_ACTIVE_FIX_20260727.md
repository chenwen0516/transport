# MMI Active 修复与回归记录（2026-07-27）

## 1. 本轮修复

| 修复项 | 原因 | 修改结果 |
|---|---|---|
| 补齐 `MMITurnContext.user_turn_active` | SpeakerGate 异步重判持续抛出 `AttributeError` | 字段进入不可变快照，Active 回调恢复 |
| 关闭 VAD 静音抵扣 | `550ms` VAD 静音抵扣 `500ms` endpoint，事件到达后立即提交 | `vad_silence_offset_ms=0` |
| 收紧 wait intent | `Wait. Can you help...` 被误当成独立“等一下” | 规则版本升为 `2026-07-27.wait-scope-v6` |
| 修复 thinking 后的 endpoint 路由 | Agent 已停止后仍永久走打断策略，重复 `START_LISTENING` | Agent 停止后回到 endpointing |
| 校准 Active endpoint 候选值 | `1.05s` 总静音仍不能覆盖 Candor 长停顿 | `min_endpointing_delay=1.0s`，待完整回归 |

本地 MMI 测试结果：`197 passed`。

## 2. 服务器部署

- Agent：`health-assistant-qwen-fdb-active-fix2`
- Active worker：`health-agent-fdb-active-fix2.service`
- Token bridge：`fdb-token-bridge-active-fix2.service`
- Token bridge 端口：`127.0.0.1:8794`
- 运行模式：`active`，`active_percentage=100`
- 代码目录：`/opt/health-assistant/backend/livekit_agent`
- 远端备份：
  - `/opt/health-assistant/backups/mmi_active_fix_20260727_162534`
  - `/opt/health-assistant/backups/mmi_wait_scope_fix_20260727_164811`
  - `/opt/health-assistant/backups/mmi_endpoint_recovery_fix_20260727_173525.py`
  - `/opt/health-assistant/backups/settings_before_mmi_endpoint_1s_20260727_173805.toml`

本地 LiveKit 容器已更换 API key。隔离 worker 和 bridge 使用权限为 `0600` 的
`/run/fdb-active-fix2.env` 注入当前凭据，没有修改共用 `settings.local.toml`。

## 3. 精确配对回归

正式回归使用旧 Active 基线 `sample_manifest.json` 中相同的 60 个样本：

- Candor pause：20
- ICC backchannel：20
- Synthetic user interruption：20

新运行目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active_fix2_v10_exact20x3_20260727`

该轮使用上下文字段修复、`vad_silence_offset_ms=0` 和 wait-scope-v6；尚未包含随后加入的
thinking endpoint 恢复和 `min_endpointing_delay=1.0s`。

| 指标 | 修复前 Active | fix2 配对回归 | 变化 | 中文说明 |
|---|---:|---:|---:|---|
| Candor 暂停窗口重叠率 | 15% | 10% | -5 个百分点 | 自然停顿抢话减少 |
| Candor 用户续说重叠率 | 20% | 10% | -10 个百分点 | 用户继续说时的重叠减少 |
| Candor 正式输出率 | 70% | 40% | -30 个百分点 | 恢复链路仍有阻断 |
| ICC 正式轮次率 | 35% | 50% | +15 个百分点 | backchannel 恢复，但仍低于 Shadow |
| ICC backchannel 频率 | 0.0048 | 0.0082 | +0.0034 | 有效附和增多 |
| ICC 时序 JSD（越低越好） | 0.9362 | 0.8066 | -0.1296 | 时序分布改善 |
| 强中断响应率 | 95% | 100% | +5 个百分点 | 20/20 均响应 |
| 强中断平均评分 | 4.6316 | 4.55 | -0.0816 | 基本持平、轻微下降 |
| 强中断平均延迟 | 1.3439s | 2.4815s | +1.1376s | 完整性改善但速度变慢 |

60 条 forced-align 全部成功，评测失败数为 0；本轮 Active MMI 日志中的
`AttributeError`、Traceback 和 fail-safe 总数为 0。

## 4. 单样本根因验证

### 4.1 Synthetic interruption 23

修复前，`Wait. Can you help me with something else?` 被识别为 wait intent，15 秒内不提交。
wait-scope-v6 修复后：

- `TOR=1.0`
- `rating=5.0`
- 输出回答：`What type of cake are you looking for?`
- 日志确认第二轮 `wait_intent=false`，在停止说话后约 `501ms` 正常 commit

### 4.2 Candor pause 190

该样本暴露了两层问题：

1. thinking 状态残留导致 endpoint timer 重复返回 `START_LISTENING`。修复后重复次数从
   60 多次降为 0。
2. 后半段语音较安静，VAD 在长停顿/续说附近仍会提前结束。将 endpoint 调到 `1.0s`
   后恢复正式输出，但仍提前约 `0.57s` 与用户续说重叠。

因此不能继续只靠全局延迟解决。下一步应使用低 VAD 置信度、EOU 不确定性或续说风险信号，
仅对高风险自然停顿切换到 `max_endpointing_delay`，同时保留正常轮次和强中断的低延迟。

## 5. 当前结论

本轮已经修复确定的运行时异常、wait intent 丢轮次和 endpoint 恢复死循环，并改善 ICC 与
强中断完整性。但 Candor 正式输出率和自适应自然停顿仍未达到 Active 放量门槛。

当前建议继续保持 Shadow/隔离 Active，不将该版本直接切到全量生产。下一轮应对包含最新
thinking 恢复与 `1.0s` endpoint 的版本重新跑相同 60 条 manifest，再决定是否进入 v1.5
四维度回归。

## 6. 最新完整基线

包含 thinking 恢复与 `1.0s` endpoint 的最新版已完成相同 manifest 的完整回归：

- v1.0：5 个维度各 20 条，共 100 条
- v1.5：4 个维度各 20 条，共 80 条
- 实时音频推理：260/260
- 强制对齐：260/260
- 失败、ERROR、Traceback、AttributeError、fail-safe：均为 0

完整四版本对比和结论见 `docs/FDB_MMI_ALL_BASELINES_COMPARISON_20260727.md`。最新版
解决了运行时稳定性问题，v1.5 总体正确率达到 75.0%，但 Candor 正式输出率 65%、
正常接话平均延迟 7.634 秒，仍不满足全量生产 Active 条件。
