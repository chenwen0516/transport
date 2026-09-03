# FDB MMI 开启前后基线对比

> 日期：2026-07-27  
> 对比口径：同一批样本、相同音频输入；Shadow 为开启前，Active 100% 为开启后。  
> 结论：Active 有明显收益，但当前实现存在阻断性错误，不能据此进入生产 Active。

## 1. 运行完整性

| 版本 | Shadow 数据 | Active 数据 | Active 运行完整性 |
|---|---|---|---|
| v1.0 | 英文全量基线中提取同样本 | 5 个维度各 20 条，共 100 条 | 推理 100/100、强制对齐 100/100、失败 0 |
| v1.5 | 英文全量基线中提取同样本 | 4 个维度各 20 条，共 80 条 | 样本 80/80、实时推理 160/160、强制对齐 160/160、失败 0 |

Active 结果目录：

```text
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active100_v1_0_baseline_20x5_20260727
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active100_baseline_20x4_20260727
```

Shadow 来源：

```text
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_shadow_full_loopback_20260716_1058
```

## 2. v1.0 同样本结果

| 维度 | 指标 | Shadow | Active | 变化 | 说明 |
|---|---|---:|---:|---:|---|
| Synthetic pause | 错误停顿重叠率，越低越好 | 0% | 0% | 0 | 两者都没有在合成停顿中抢话 |
| Synthetic pause | 正式输出率 | 100% | 85% | -15 个百分点 | Active 有 3/20 没有正式输出 |
| Candor pause | 错误停顿重叠率，越低越好 | 5% | 20% | +15 个百分点 | Active 对自然停顿更容易抢话 |
| Candor pause | 正式输出率 | 100% | 70% | -30 个百分点 | Active 状态恢复不稳定 |
| Candor turn-taking | 成功接话率 | 100% | 90% | -10 个百分点 | 20 条中有 2 条没有形成有效正式轮次 |
| Candor turn-taking | 平均响应延迟，越低越好 | 5.218 秒 | 4.676 秒 | -0.542 秒 | 速度略有提升，但牺牲了成功率 |
| ICC backchannel | 正式轮次率 | 95% | 35% | -60 个百分点 | 单独降低不代表改善，需要结合频率和 JSD |
| ICC backchannel | Backchannel 频率 | 0.0117 | 0.0048 | -0.0069 | Active 产生的有效附和更少 |
| ICC backchannel | 时序分布 JSD，越低越好 | 0.7315 | 0.9362 | +0.2047 | 时序分布明显变差 |
| Synthetic interruption | 成功响应率 | 100% | 95% | -5 个百分点 | Active 样本 44 打断后无输出 |
| Synthetic interruption | 平均行为评分 | 4.900/5 | 4.632/5 | -0.268 | 相关性和回答质量略降 |
| Synthetic interruption | 平均响应延迟，越低越好 | 5.290 秒 | 1.344 秒 | -3.947 秒 | Active 最大收益，打断后响应显著加快 |

## 3. v1.5 同样本结果

| 维度 | Shadow | Active | 变化 |
|---|---:|---:|---:|
| 背景讲话正确忽略/恢复 | 5/20，25% | 8/20，40% | +15 个百分点 |
| 对其他人讲话正确忽略/恢复 | 4/20，20% | 15/20，75% | +55 个百分点 |
| 用户 Backchannel 正确继续 | 12/20，60% | 20/20，100% | +40 个百分点 |
| 用户打断正确响应 | 17/20，85% | 15/20，75% | -10 个百分点 |
| **总体正确率** | **38/80，47.5%** | **58/80，72.5%** | **+25 个百分点** |

## 4. 已确认问题

### 4.1 SpeakerGate Active 回流异常

Active 日志反复出现：

```text
AttributeError: 'MMITurnContext' object has no attribute 'user_turn_active'
```

调用路径为：

```text
MMITurnRuntime._on_speaker_verdict_on_loop
  -> MMITurnRuntime._speaker_recheck_context
```

`MMITurnContextStore` 有 `user_turn_active`，但 `MMITurnContext` 快照模型没有该字段，
导致 SpeakerGate verdict 的异步重判回调失败。当前 Active 基线因此没有完整验证
SpeakerGate 闭环。

### 4.2 自然停顿过早提交

Active 多数 `START_SPEAKING` 在约 570--630 ms 静音后触发。Synthetic pause 没有回归，
但 Candor 自然停顿错误重叠率从 5% 上升到 20%，说明统一的约 500 ms endpointing
对真实对话停顿过于激进。

### 4.3 Agent backchannel 被 Active 中断

ICC 20 条样本中记录了 14 次 `START_LISTENING`。用户在 agent 简短附和期间继续讲话时，
Active 将其当成对 agent 的打断，导致 backchannel 频率下降、时序 JSD 变差。

### 4.4 打断后恢复链路不稳定

v1.0 样本 44 在执行强打断后没有输出。v1.5 还出现执行 `START_LISTENING` 后继续旧回答、
直接输出用户插话文本或没有生成新答案的情况。

## 5. 结论

Active 将 v1.5 总体正确率提高了 25 个百分点，并将 v1.0 打断平均响应延迟降低约
3.95 秒，方向是有效的。但 SpeakerGate 回调异常、自然停顿回退、ICC backchannel
抑制和打断后恢复失败仍属于 Active 阻断项。

下一步应先补齐 `MMITurnContext.user_turn_active` 快照字段和回归测试，再分别修复
endpointing、backchannel 保护及打断后 commit/reply 恢复链路，然后复跑相同 manifest。

## 6. 修复进展

上述问题的首轮修复与精确配对回归已经完成，详见
`docs/FDB_MMI_ACTIVE_FIX_20260727.md`。当前运行时异常、wait intent 丢轮次和 thinking
状态后的 endpoint 死循环已经修复；ICC 与强中断完整性改善，但自然停顿仍需要自适应
endpointing，暂不满足全量 Active 放量条件。

包含全部最新修复的 180 条完整回归已经完成。Shadow、初版 Active、fix2 和最新版
Active 的同样本统一对比见 `docs/FDB_MMI_ALL_BASELINES_COMPARISON_20260727.md`。
