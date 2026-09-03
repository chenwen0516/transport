# FDB MMI 全部基线对比（2026-07-27）

## 1. 对比范围

本报告使用相同英文 FDB 样本比较 MMI 开启前、初版 Active、阶段性修复版和
最新 Active。正式完整基线包含 v1.0 五个维度各 20 条、v1.5 四个维度各
20 条，共 180 条样本。v1.5 每条样本还包含 clean 输入，因此最新版实际完成
260 次实时音频推理和 260 次强制对齐。

| 版本 | MMI 状态 | v1.0 | v1.5 | 运行完整性 |
|---|---|---:|---:|---|
| Shadow | MMI 仅观察，不控制轮次 | 同样本 100 条 | 同样本 80 条 | 来自英文全量基线 |
| 初版 Active | Active 100% | 100 条 | 80 条 | 推理、ASR 全部成功 |
| fix2 | Active 100%，首轮修复 | 3 个关键维度，共 60 条 | 未运行 | 推理、ASR 全部成功 |
| 最新 Active | Active 100%，包含 thinking 恢复与 1.0 秒 endpoint | 100 条 | 80 条 | 主样本 180/180、实时推理 260/260、ASR 260/260、失败 0 |

最新版与初版 Active 的 manifest 完全一致，180/180 个 `source_relative`
相同，因此可以直接比较。fix2 只覆盖 Candor pause、ICC backchannel 和
Synthetic user interruption，不存在的数据在表中标记为“未测”。

## 2. v1.0 对比

### 2.1 停顿与正常接话

| 维度 | 指标 | Shadow | 初版 Active | fix2 | 最新 Active | 最新版说明 |
|---|---|---:|---:|---:|---:|---|
| Synthetic pause | 用户续说重叠率，越低越好 | 0% | 0% | 未测 | 0% | 保持稳定 |
| Synthetic pause | 正式输出率 | 100% | 85% | 未测 | 100% | 恢复到 Shadow 水平 |
| Candor pause | 用户续说重叠率，越低越好 | 5% | 20% | 10% | 5% | 抢话风险恢复到 Shadow 水平 |
| Candor pause | 正式输出率 | 100% | 70% | 40% | 65% | 比 fix2 提高 25 个百分点，仍低于 Shadow |
| Candor turn-taking | 成功接话率 | 100% | 90% | 未测 | 95% | 比初版提高 5 个百分点 |
| Candor turn-taking | 平均响应延迟，越低越好 | 5.218 秒 | 4.676 秒 | 未测 | 7.634 秒 | 比 Shadow 慢 2.416 秒，明显回归 |

这里的“正式输出率”使用 pause evaluator 的 `legacy_tor`；“用户续说重叠率”
使用 `user_continuation_overlap_rate`。最新版 Candor 的 `5%` 是重叠率，
不是正式输出率；最新版正式输出率为 `65%`。

### 2.2 Backchannel

| 指标 | Shadow | 初版 Active | fix2 | 最新 Active | 最新版说明 |
|---|---:|---:|---:|---:|---|
| 正式轮次率 | 95% | 35% | 50% | 55% | 持续恢复，但仍低于 Shadow |
| Backchannel 频率 | 0.0117 | 0.0048 | 0.0082 | 0.0168 | 已高于 Shadow，需要检查是否附和过多 |
| 时序分布 JSD，越低越好 | 0.7315 | 0.9362 | 0.8066 | 0.7671 | 接近 Shadow，较初版明显改善 |

### 2.3 用户打断

| 指标 | Shadow | 初版 Active | fix2 | 最新 Active | 最新版说明 |
|---|---:|---:|---:|---:|---|
| 成功响应率 | 100% | 95% | 100% | 95% | 仍有 1/20 未形成有效响应 |
| 平均行为评分 | 4.900/5 | 4.632/5 | 4.550/5 | 5.000/5 | 四组中最好 |
| 平均响应延迟，越低越好 | 5.290 秒 | 1.344 秒 | 2.482 秒 | 1.950 秒 | 显著快于 Shadow，略慢于初版 Active |

## 3. v1.5 对比

v1.5 的“正确”含义随场景变化：背景讲话、对其他人讲话和用户 Backchannel
以 `C_RESUME` 为正确；用户打断以 `C_RESPOND` 为正确。

| 维度 | Shadow | 初版 Active | fix2 | 最新 Active | 最新版相对初版 |
|---|---:|---:|---:|---:|---:|
| 背景讲话正确忽略/恢复 | 5/20，25% | 8/20，40% | 未测 | 9/20，45% | +5 个百分点 |
| 对其他人讲话正确忽略/恢复 | 4/20，20% | 15/20，75% | 未测 | 16/20，80% | +5 个百分点 |
| 用户 Backchannel 正确继续 | 12/20，60% | 20/20，100% | 未测 | 18/20，90% | -10 个百分点 |
| 用户打断正确响应 | 17/20，85% | 15/20，75% | 未测 | 17/20，85% | +10 个百分点 |
| **总体正确率** | **38/80，47.5%** | **58/80，72.5%** | **未测** | **60/80，75.0%** | **+2.5 个百分点** |

最新版 v1.5 总体结果是四组中最好，并且将用户打断恢复到 Shadow 的 85%。
用户 Backchannel 从初版的 100% 回落到 90%，但仍明显高于 Shadow。

## 4. 综合结论

1. **运行时稳定性已经修复。** 最新版 180 个样本、260 次实时推理和
   260 次强制对齐全部完成，失败数为 0；此前的 `user_turn_active`
   字段异常和 thinking 状态后的 endpoint 死循环未再阻断评测。
2. **v1.5 的 Active 方向有效。** 总体正确率从 Shadow 的 47.5% 提高到
   75.0%，背景讲话、对其他人讲话和用户打断均优于或等于初版 Active。
3. **自然停顿抢话已经受控，但轮次恢复仍不完整。** Candor 续说重叠率已从
   初版 Active 的 20% 降到 5%，但正式输出率只有 65%，仍比 Shadow 低
   35 个百分点。
4. **全局 1.0 秒 endpoint 带来明显延迟成本。** Candor 正常接话平均延迟
   上升到 7.634 秒，比 Shadow 慢 2.416 秒；这说明继续全局增加等待时间
   不能作为最终方案。
5. **ICC 已接近可用，但需要控制频率。** JSD 已从 0.9362 改善到 0.7671，
   接近 Shadow 的 0.7315；频率 0.0168 高于 Shadow，需要排查是否出现
   过多或重复附和。
6. **最新版仍不建议直接全量生产 Active。** 当前阻断项不再是崩溃，而是
   Candor 正式输出缺失和正常接话延迟。下一步应实现自适应 endpoint：
   普通完整轮次保持低延迟，仅在自然停顿、低 EOU 置信度或续说风险较高时
   使用更长等待，并复跑相同 180 条 manifest。

## 5. 结果位置

```text
# Shadow 来源
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_shadow_full_loopback_20260716_1058

# 初版 Active
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active100_v1_0_baseline_20x5_20260727
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active100_baseline_20x4_20260727

# fix2 三维度配对回归
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active_fix2_v10_exact20x3_20260727

# 最新 Active 完整基线
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active_latest_exact20x9_20260727
```
