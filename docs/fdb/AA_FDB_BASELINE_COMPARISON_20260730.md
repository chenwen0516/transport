# AA-FDB Shadow、Active 与 CAM++ 基线对比

更新日期：2026-07-30

## 1. 结论

当前推荐送测配置为 **MMI Active + CAM++ ON**。

| 得分口径 | 得分 | 是否为 AA 官方榜单分 |
|---|---:|---|
| **AA-FDB 四能力等权代理分** | **93.13%** | 否，属于本地送测前预测 |
| 五组样本直接平均 | 94.00% | 否，属于本地辅助统计 |
| AA 官方 Conversational Dynamics 得分 | 待 AA 官方评测 | 是 |

AA-FDB 四能力等权代理分的计算过程：

```text
Pause Handling = (100% + 95%) / 2 = 97.50%

AA-FDB proxy
  = (Pause Handling + Turn Taking + User Interruption + Backchannel) / 4
  = (97.50% + 85.00% + 90.00% + 100.00%) / 4
  = 93.125%
  = 93.13%
```

## 2. AA-FDB 核心结果

表中 Pause Handling 使用“不在用户自然停顿期间抢话”的成功率。Synthetic
Pause 和 Candor Pause 各有 20 条，二者先合并为 Pause Handling，再与另外
三项能力等权平均。

| AA 维度 | 历史 Shadow | 初版 Active | 历史最新 Active | 当前 Active、CAM++ OFF | 当前 Active、CAM++ ON |
|---|---:|---:|---:|---:|---:|
| v1.0 Synthetic Pause | 20/20，100% | 20/20，100% | 20/20，100% | 20/20，100% | 20/20，100% |
| v1.0 Candor Pause | 19/20，95% | 16/20，80% | 19/20，95% | 20/20，100% | 19/20，95% |
| **Pause Handling 综合** | **97.50%** | **90.00%** | **97.50%** | **100.00%** | **97.50%** |
| v1.0 Turn Taking | 20/20，100% | 18/20，90% | 19/20，95% | 17/20，85% | 17/20，85% |
| Turn Taking 平均延迟 | 5.218 秒 | 4.676 秒 | 7.634 秒 | 7.860 秒 | 7.689 秒 |
| v1.5 User Interruption | 17/20，85% | 15/20，75% | 17/20，85% | 20/20，100% | 18/20，90% |
| v1.5 User Backchannel | 12/20，60% | 20/20，100% | 18/20，90% | 16/20，80% | 20/20，100% |
| **AA-FDB 四能力等权代理分** | **85.63%** | **88.75%** | **91.88%** | **91.25%** | **93.13%** |
| 五组样本直接平均 | 88.00% | 89.00% | 93.00% | 93.00% | 94.00% |

## 3. 输出完整性

暂停成功率只衡量是否抢话。Agent 没有在停顿期间发言，但在用户说完后也没有
正常回答时，仍可能获得暂停成功。因此正式输出率和静音数量必须作为配套指标。

| 辅助指标 | 历史 Shadow | 初版 Active | 历史最新 Active | 当前 Active、CAM++ OFF | 当前 Active、CAM++ ON |
|---|---:|---:|---:|---:|---:|
| Synthetic Pause 正式输出率 | 100% | 85% | 100% | 55% | 90% |
| Candor Pause 正式输出率 | 100% | 70% | 65% | 100% | 95% |
| 主样本推理成功 | 历史全量成功 | 180/180 | 180/180 | 100/100 | 100/100 |
| ASR 成功 | 历史全量成功 | 260/260 | 260/260 | 140/140 | 140/140 |
| 存在 warning 的样本 | 历史口径不同 | 未统一统计 | 未统一统计 | 53/100 | 44/100 |
| 静音输出 | 未统一统计 | 未统一统计 | 未统一统计 | 14 | 7 |

## 4. CAM++ 严格 A/B 结论

当前 CAM++ OFF 和 ON 两次运行使用相同代码、Prompt、裁判、seed 和完全相同
的 100 条 manifest，是当前唯一可以用于判断 CAM++ 因果影响的严格对照。

| 变化 | CAM++ OFF | CAM++ ON | 差值 |
|---|---:|---:|---:|
| AA-FDB 四能力等权代理分 | 91.25% | 93.13% | +1.88 个百分点 |
| Pause Handling | 100.00% | 97.50% | -2.50 个百分点 |
| Turn Taking | 85.00% | 85.00% | 0 |
| User Interruption | 100.00% | 90.00% | -10.00 个百分点 |
| User Backchannel | 80.00% | 100.00% | +20.00 个百分点 |
| Turn Taking 平均延迟 | 7.860 秒 | 7.689 秒 | 改善 0.171 秒 |
| 静音输出 | 14 | 7 | 减少 7 个 |

CAM++ ON 的综合得分更高，主要收益来自 Backchannel 和静音输出改善；主要回归
是 User Interruption 从 100% 降到 90%。正式送测前应优先修复声纹门控误抑制
真实用户打断的问题，同时继续优化 Turn Taking 的 85% 成功率和约 7.7 秒延迟。

## 5. 数据规模

| 数据范围 | 数量 |
|---|---:|
| 当前本地 AA-FDB 代理集 | 100 条 |
| Pause Handling | 40 条：Synthetic 20 + Candor 20 |
| Turn Taking | 20 条 |
| User Interruption | 20 条 |
| User Backchannel | 20 条 |
| 当前每次基线的实时推理次数 | 140 次，包含 v1.5 clean 对照 |
| 英文完整 FDB v1.0/v1.5 | 1225 条，1723 次实时推理 |
| AA 官方使用的 FDB 子集 | 官方未公开具体样本数量和样本 ID |

Artificial Analysis 公开方法说明 Conversational Dynamics 基于 Full Duplex Bench
v1 和 v1.5 的一个子集，并由 Pause Handling、Turn Taking、User Interruption
Handling、Backchannel Handling 加权得到，但没有公开四项具体权重和子集数量：

https://artificialanalysis.ai/methodology/speech-to-speech-benchmarking

因此，本报告的 93.13% 应表述为：

> health-assistant-qwen 在本地固定 100 条 AA-FDB 代理集上的四能力等权分为
> 93.13%，该结果用于内部优化和 AA 送测前预测，不是 AA 官方榜单得分。

## 6. 运行位置

```text
# 历史 Shadow
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_shadow_full_loopback_20260716_1058

# 初版 Active
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active100_v1_0_baseline_20x5_20260727
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active100_baseline_20x4_20260727

# 历史最新 Active
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_active_latest_exact20x9_20260727

# 当前 Active、CAM++ OFF
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_fdb_subset20x5_mmi_active_no_sg_20260729

# 当前 Active、CAM++ ON
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_fdb_subset20x5_mmi_active_campp_on_20260730
```

历史 Shadow、初版 Active 和历史最新 Active 可用于观察迭代趋势，但它们使用了
不同阶段的代码或裁判配置，不能作为 CAM++ 开关的严格 A/B。CAM++ 的直接影响
应只比较最后两次当前 Active 运行。

## 7. 修复版 Active 回归与 Bad Case 分析

2026-07-30 使用 wait-intent 修复版 Agent 完成了一轮固定 100 条回归：

```text
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_waitfix_campp_shadow_exact100_20260730
```

该轮推理 100/100 成功，ASR 140/140 成功，v1.5 行为裁判 40/40 完成。
修复版在 `CAM++ audio_mode=shadow` 下的原始结果如下。这些结果仍是本地固定
100 条代理集得分，不是 AA 官方提交分。

| 维度 | 原始结果 | 主要 Bad Case |
|---|---:|---|
| Synthetic Pause | 20/20，100% | 无 |
| Candor Pause 正式输出 | 19/20，95% | 189 |
| Turn Taking | 14/20，70% | 48、35、59、47、110、30 |
| User Interruption | 19/20，95% | 152 |
| User Backchannel | 18/20，90% | 44、98 |

另使用相同代码、相同 20 条 Turn Taking 样本，将 CAM++ 音频模式恢复为
`mute` 做隔离实验：

```text
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_waitfix_campp_mute_turn20_20260730
```

Turn Taking 为 16/20（80%），平均延迟 7.541 秒。59、47、30 恢复正常，
新增的 38 实际回答了 `Who is it?`，但回答不足 1 秒且只有 3 个词，按照
FDB `smooth_turn_taking` 的原始规则仍记为 0。

### 7.1 Agent 与 MMI Bad Case

| 样本 | 现象 | 根因 | 处理 |
|---|---|---|---|
| 48 | 整轮静音 | `Hopefully` 被 `addressee.english_vocative` 误判为呼叫其他人 | 已加入非呼语保护词和回归测试 |
| 110 | 整轮静音 | `There` 被误判为呼叫其他人 | 已加入非呼语保护词和回归测试 |
| 35 | 整轮静音 | CAM++ 在初始注册后连续给出约 0.28～0.32 的低相似度，将真实用户判为背景人 | 需要改进注册样本和多片段聚合 |
| 189 | 前面多个片段为 TARGET，最后短片段约 0.285 后整轮被忽略 | `bargein` 探测阶段的单次低分覆盖了已确认 target latch | 已禁止 `bargein` 探测覆盖 target latch |
| 152 | 回答旧的汽车保养问题，没有回答电动车问题 | 新问题被拆成多个 STT 段，提交时只保留 `What are the benefits?` | 待实现同轮连续片段的安全回溯 |
| 98 | Backchannel 被当作新用户轮次 | `Hmm. Yeah.` 未命中组合 Backchannel | 已补充 `hmm`、`hmm yeah` |
| 59、30 | MMI 已提交但没有语音输出 | LLM thinking 持续约 30.1 秒，超过评测录制窗口 | 增加首 token 超时、重试和独立错误标签 |
| 47 | MMI 已提交但没有语音输出 | 生成链路快速结束但没有 assistant item 或 LLM usage | 增加空响应重试和流水线观测 |
| 38 | 有真实音频但 Turn Taking 记 0 | 回答仅 3 个词且不足 1 秒，命中 FDB 短回答排除规则 | 属于榜单规则，不按静音处理 |
| 44 | 被判 `C_UNCERTAIN_HANDLING` | 原问题语义模糊，clean/output 都生成澄清回答 | 单独标记为裁判语义边界 |

### 7.2 FDB WebRTC 诊断转写归属问题

`run_fdb_eval.py` 的 `_role_for_transcription()` 只将 `user-*` 识别为用户，
将所有其他 participant 默认识别为 assistant。当前评测端身份为
`fdb-evaluator-*`，因此评测端播放的用户输入和 `mhm/uh huh` 也可能写入
`output_assistant_transcript.txt`。

该问题会污染 `output_assistant_transcript.txt`、`response_done_events` 和
相关 warning，使人工排查时误以为评测端播放的文本来自 Agent。

需要说明的是，DeepSeek 行为裁判实际读取 Agent 远端音轨强制对齐产生的
`output.json` 和 `clean_output.json`，不读取上述诊断 transcript。因此该问题
不会直接改变现有 v1.5 行为分，但会严重误导 Bad Case 定位，仍应修复。

修复原则：

1. 只有 `agent-*` participant 的转写可以进入 assistant transcript。
2. `fdb-evaluator-*` 和本地发布轨道必须按 user 处理或从 assistant 汇总中排除。
3. 在诊断产物中保留 participant identity，便于追踪文本来源。
4. 现有运行无需重新做实时推理；可从 `output_events.jsonl` 重新生成过滤后的
   assistant transcript，但行为裁判结果无需因此重算。

2026-07-30 已在服务器 `run_fdb_eval.py` 完成 participant 过滤修复，并通过
`agent-*`、`fdb-evaluator-*`、`user-*` 三类身份断言和 Python 编译检查。
当时正在运行的基线进程已加载旧模块，因此该轮保持原始诊断口径；后续新启动
的评测自动使用修复逻辑。

### 7.3 后续修复与复测顺序

1. 已修复 FDB participant 过滤，恢复后续诊断 transcript 的可信度。
2. 已修复英文呼语 bad case、`bargein` target latch 和 `hmm yeah` 回声组合，
   本地 MMI 测试 228/228 通过，独立远端 release 定向测试 191/191 通过。
3. 为 152 增加跨 STT 段且保持说话人边界的完整提交逻辑。
4. 为 LLM 首 token 超时和空响应增加可观测重试。
5. 使用相同 manifest 定向复测全部 Bad Case。
6. 通过门禁后重新运行固定 100 条 Active 基线，再更新正式代理分。
