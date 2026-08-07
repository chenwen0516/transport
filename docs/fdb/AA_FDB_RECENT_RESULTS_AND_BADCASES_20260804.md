# AA-FDB 近期结果与 Badcase 汇总

更新日期：2026-08-04

测试对象：服务器 `113.44.234.195` 上的 `health-assistant-qwen` Agent

当前配置：MMI-TD Active 100%，CAM++ 开启，`audio_mode=mute`，
`mmi_mode=negative_only`，空响应 watchdog 为 10 秒超时、最多重试 1 次。

## 1. 结论摘要

1. 目前可确认已经完整跑完 4 轮全量：英文完整 FDB 1225 条、两轮英文 AA-FDB
   核心集各 770 条，以及中文完整集 915 条。最新英文 770 条推理为 770/770，
   强制对齐 ASR 为 1068/1068，评测主链路没有样本级失败。
2. 本地 AA-FDB 四能力等权代理分由上一轮的 95.16% 提升到 96.02%，提高
   0.86 个百分点。该分数不是 Artificial Analysis 官方榜单分。
3. Turn Taking 从 89.92% 提升到 96.64%，是本轮最明显的收益；平均端到端延迟
   从 7.433 秒变为 7.477 秒，基本持平但仍然偏高。
4. 严格静默从 30/770 降到 14/770，即从 3.90% 降到 1.82%，数量减少 53.3%。
5. User Interruption 的 `C_RESPOND` 从 95.5% 下降到 92.0%，是当前最明确的
   行为回归，不能只根据总代理分提升就认定新版全面优于旧版。
6. 最新 14 条严格静默中，9 条发生在 MMI 控制和输入事件链，5 条发生在 MMI
   已提交之后的模型或实时输出链路。
7. watchdog 在全量中触发 6 次重试，其中 2 次恢复成功；另外 4 次重试时
   `AgentSession` 已进入 closing，无法再次调用 `generate_reply()`。

## 2. 全部全量结果

本节只收录真正完成全量数据的运行。1/5/20/40/80/100/180 条 smoke、canary、
固定基线和定向 badcase 均不计入全量表。

### 2.1 全量运行总表

| 日期 | 语言与数据范围 | MMI/CAM++ | 样本与运行完整性 | 本地代理分 | 结论 |
| --- | --- | --- | --- | ---: | --- |
| 2026-07-16 | 英文完整 FDB v1.0 + v1.5 | Shadow，CAM++ 只观察 | 1225 条；推理 1225/1225；ASR 1723/1723 | 88.78% | 回答覆盖高、延迟较低，但非目标讲话和 Backchannel 较弱 |
| 2026-07-31 | 英文 AA-FDB 核心全量 | Active，CAM++ ON/mute | 770 条；推理 770/770；ASR 1068/1068 | 95.16% | 作为最新修复版的直接全量对照 |
| 2026-07-31 | 中文 FDB 全量 | Active，CAM++ ON/mute | 915 条；推理 915/915；ASR 1275/1275 | 94.20% | 中文内部类比结果，不能当作英文 AA 榜单分 |
| 2026-08-03 至 08-04 | 英文 AA-FDB 核心全量 | Active，CAM++ ON/mute，v9 + watchdog | 770 条；推理 770/770；ASR 1068/1068 | 96.02% | 当前最新英文全量，严格静默降至 14 条 |

### 2.2 全量核心维度

| 全量运行 | Pause Handling | Turn Taking | 平均延迟 | User Interruption | Backchannel | 严格静默/已确认音频静默 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 英文完整 1225，Shadow | 99.54% | 99.16% | 4.935 s | 85.00% | 71.43% | 历史确认 2 条音频静默 |
| 英文 AA 770，上一版 Active | 99.31% | 89.92% | 7.433 s | 95.50% | 95.92% | 30 条严格静默 |
| 中文 915，Active | 100.00% | 97.42% | 8.376 s | 89.44% | 89.95% | 21 条严格静默 |
| 英文 AA 770，最新 Active | 99.54% | 96.64% | 7.477 s | 92.00% | 95.92% | 14 条严格静默 |

其中英文完整 1225 条覆盖 FDB 的全部 v1.0/v1.5 场景；英文 770 条只覆盖
AA Conversational Dynamics 相关的 Pause Handling、Turn Taking、User
Interruption 和 Backchannel；中文 915 条使用中文数据布局。三种数据范围的样本
和语义分布不同，只有两轮英文 770 条是当前最严格的全量前后对比。

表中的 Pause Handling 使用“没有在用户续说阶段错误抢话”的安全成功率。中文
915 条在该口径下为 100%，但其 pause 正式输出率为 94.98%；两者衡量的不是同一
件事，不能用 100% 掩盖正式输出缺失。

### 2.3 全量运行目录

```text
# 英文完整 FDB 1225 条，Shadow
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_shadow_full_loopback_20260716_1058

# 英文 AA-FDB 770 条，上一版 Active
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_badcase_v2_campp_mute_full770_v2_20260731

# 中文 FDB 915 条，Active
/opt/Full-Duplex-Bench/runs/health_webrtc_zh/zh_qwen_mmi_badcase_v2_campp_mute_full915_after_en770_20260731

# 英文 AA-FDB 770 条，最新 Active
/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_greeting_v3_campp_mute_full770_v2_20260803
```

服务器上另有一个名为 `en_qwen_aa_badcase_v2_campp_mute_full770_20260730` 的
目录，但其 summary 只有 100 条；另一个
`en_qwen_aa_greeting_v3_campp_mute_full770_20260803` 只有 2 个事件文件。这两轮
都不是完成的全量，因此没有放进结果表。

## 3. 最新英文全量结果

上一轮目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_badcase_v2_campp_mute_full770_v2_20260731`

最新一轮目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_greeting_v3_campp_mute_full770_v2_20260803`

| AA-FDB 能力 | 上一轮 | 最新一轮 | 变化 | 中文说明 |
| --- | ---: | ---: | ---: | --- |
| Synthetic Pause 成功率 | 100.00% | 100.00% | 0 | 合成停顿期间没有错误抢话 |
| Candor Pause 成功率 | 98.61% | 99.07% | +0.46 pp | 自然对话停顿处理小幅改善 |
| Pause Handling 综合 | 99.31% | 99.54% | +0.23 pp | 两类 Pause 先等权合并 |
| Turn Taking | 89.92% | 96.64% | +6.72 pp | 用户结束后正确接话能力明显改善 |
| Turn Taking 平均延迟 | 7.433 s | 7.477 s | +0.044 s | 略慢，基本持平，仍需优化 |
| User Interruption `C_RESPOND` | 95.50% | 92.00% | -3.50 pp | 用户打断后正确响应新输入的比例下降 |
| User Backchannel `C_RESUME` | 95.92% | 95.92% | 0 | 短反馈后继续原回答的能力保持不变 |
| 本地四能力等权代理分 | 95.16% | 96.02% | +0.86 pp | 非 AA 官方榜单分 |

代理分计算如下：

```text
Pause Handling
  = (100.00% + 99.07%) / 2
  = 99.54%

AA-FDB local proxy
  = (Pause Handling + Turn Taking + User Interruption + Backchannel) / 4
  = (99.54% + 96.64% + 92.00% + 95.92%) / 4
  = 96.02%
```

Artificial Analysis 没有公开其 FDB 子集样本 ID、具体数量和四能力权重，因此
96.02% 只能用于内部版本比较，不能写成 AA 官方 Conversational Dynamics 得分。

## 4. v1.5 行为分布

| 维度 | 上一轮 | 最新一轮 | 判断 |
| --- | --- | --- | --- |
| User Interruption | `C_RESPOND` 95.5%，`C_RESUME` 0.5%，不确定 3.5%，未知 0.5% | `C_RESPOND` 92.0%，`C_RESUME` 1.5%，不确定 6.0%，未知 0.5% | 正确响应下降，不确定处理增加，需要优先复盘 |
| User Backchannel | `C_RESUME` 95.92%，不确定 3.06%，未知 1.02% | `C_RESUME` 95.92%，未知 4.08% | 主指标不变，但裁判标签分布发生变化 |

行为分由 DeepSeek 裁判生成。主指标变化较小时，应结合固定 badcase 和裁判原始
输出复核，避免把裁判波动误认为 Agent 的真实行为变化。

## 5. 输出完整性与告警

| 指标 | 上一轮 | 最新一轮 | 变化 |
| --- | ---: | ---: | ---: |
| 推理成功 | 770/770 | 770/770 | 不变 |
| 强制对齐 ASR 成功 | 1068/1068 | 1068/1068 | 不变 |
| 存在任意 warning 的样本 | 266 | 253 | 减少 13 |
| `missing_response_done` | 186 | 166 | 减少 20 |
| `missing_assistant_transcript` | 30 | 14 | 减少 16 |
| `silent_output` warning | 31 | 15 | 减少 16 |
| 严格静默 | 30，3.90% | 14，1.82% | 减少 16，下降 53.3% |
| `response_completion_timeout` | 239 | 238 | 基本不变 |

warning 之间可以重叠。`response_completion_timeout` 很多是回答超过固定录制窗口，
不等于静默或推理失败。最新 15 条 `silent_output` warning 中，样本
`v1.0/candor_pause_handling/173` 已有 110 个 assistant 字符和 1 个
`response_done`，只是音频非零占比约为 `0.00000259`，因此不计入严格静默。

严格静默按场景分布：

| 场景 | 上一轮 | 最新一轮 | 最新静默率 |
| --- | ---: | ---: | ---: |
| Candor Turn Taking | 12/119 | 4/119 | 3.36% |
| Candor Pause Handling | 16/216 | 8/216 | 3.70% |
| Synthetic Pause Handling | 2/137 | 2/137 | 1.46% |
| User Interruption | 0/200 | 0/200 | 0% |
| User Backchannel | 0/98 | 0/98 | 0% |

两轮严格静默有 9 条样本重合，上一轮独有 21 条，最新一轮新增 5 条。这说明修复
产生了真实收益，同时模型输出、STT 分段和 CAM++ 判断仍有一定随机性。

## 6. 最新 14 条严格静默 Badcase

### 6.1 根因汇总

| 根因 | 数量 | 占严格静默 | 样本 | 说明 |
| --- | ---: | ---: | --- | --- |
| `addressed_to_other` 误抑制 | 6 | 42.9% | Candor Pause 170、68、72、37、53；Synthetic Pause 4 | 文本被当作对其他人说话，MMI 未提交回复 |
| addressee 与 CAM++ 混合抑制 | 1 | 7.1% | Turn Taking 75 | 前一轮命中第三方称呼，后一轮又被判非目标说话人 |
| CAM++ 非目标说话人误判 | 1 | 7.1% | Turn Taking 35 | 目标用户被 `non_target_speaker_ignored` 拦截 |
| 无有效 MMI 目标决策 | 1 | 7.1% | Turn Taking 62 | 未形成可执行 decision，需继续查 VAD、STT 和事件链 |
| 已提交但输出链无有效结果 | 5 | 35.7% | Turn Taking 83；Candor Pause 137、184、210；Synthetic Pause 41 | MMI 已执行接话，模型或实时输出链没有在窗口内产生音频 |
| 合计 | 14 | 100% | - | 控制/输入链 9 条，提交后输出链 5 条 |

### 6.2 Addressee 误判

早期已经修复 `Hopefully`、`There`、`Cross`、`Hello` 等英文句首词误判，但全量
仍有 6 条纯 `addressed_to_other` 和 1 条混合误判。说明当前规则仍过度依赖句首
形式，尤其对自然多人对话、语气词、短句和 STT 标点敏感。

后续不应继续无限扩充保护词列表。更稳妥的方向是：

1. 将“明确姓名、亲属称谓或职称 + 后续完整指令”作为强第三方证据。
2. 普通句首词、寒暄词和 ASR 不稳定单词只作为弱证据。
3. 对长对话使用末尾问题、当前目标说话人状态和对话上下文共同确认 addressee。
4. 建立固定正反例集，分别覆盖 greeting、姓名、亲属、职称和背景对话。

### 6.3 CAM++ 误抑制

样本 35 再次出现目标用户被判为非目标说话人，样本 75 同时受到 addressee 和
CAM++ 影响。根因仍是“首段自动注册为目标声纹”的假设不适合自然多人音频：
首段可能不是最终目标用户，同一人的跨段音色也会因响度、距离和重叠语音变化。

当前 `negative_only` 比硬门控更保守，但明确的 `decide` 非目标结果仍可能静音
真实用户。后续应先在 shadow 中验证多段注册、目标/非目标双阈值、迟滞和
fail-open，再改变 Active 门控。

### 6.4 无有效 MMI 决策

Turn Taking 62 在两轮全量中都属于严格静默，并且没有形成有效 MMI decision。
它不是 addressee 规则或模型空响应可以解释的样本，应单独关联以下事件：

- VAD 的 `start_of_speech`、`end_of_speech`；
- STT partial/final 和 `user_input_transcribed`；
- CAM++ callback 的 event ID；
- MMI 当前 turn ID、endpoint timer 创建与取消；
- 会话关闭时间。

该样本是事件链可观测性的固定回归用例，不应通过调整语言规则掩盖。

### 6.5 MMI 已提交但模型或输出链为空

Turn Taking 83 已执行 `START_SPEAKING`，但后续音频产生了新的空 turn，10 秒后
watchdog 判断原 turn 已 stale 并取消恢复。这里需要把“当前 turn 已变化”和
“原响应是否仍欠缺输出”拆开管理，避免无意义空 turn 使 watchdog 失效。

Candor Pause 137、184、210 和 Synthetic Pause 41 的链路一致：

```text
commit_requested
  -> speech_created
  -> 10 秒没有首音频
  -> first_output_timeout
  -> 中断空响应
  -> retry_requested
  -> AgentSession is closing
  -> retry_request_failed
```

这 4 条的直接异常是模型 10 秒内没有产生首音频；恢复失败的直接原因则是 FDB
录制窗口结束后 AgentSession 已进入 closing。生产长会话通常不会在同一时间关闭，
但评测必须把重试预算纳入录制窗口，否则 watchdog 被触发后没有恢复时间。

## 7. Watchdog 全量表现

最新 770 条对应 770 份 MMI 日志，响应 trace 汇总如下：

| trace 指标 | 数量 | 说明 |
| --- | ---: | --- |
| `commit_requested` | 1026 | 包含 v1.5 clean/output 和多轮输入 |
| `speech_created` | 973 | 已创建响应 handle |
| `first_audio` / `output_confirmed` | 680 | watchdog 观察到首音频并确认成功 |
| `first_output_timeout` | 6 | 10 秒内没有首音频 |
| `retry_requested` | 6 | 每次最多重试一次 |
| 重试恢复成功 | 2 | Turn Taking 102、User Interruption 69 |
| 重试请求失败 | 4 | Session closing，无法再次生成 |

恢复成功的两条中，重试首音频分别在约 1.724 秒和 1.184 秒到达，说明重试机制
本身有效。当前缺口不是是否需要重试，而是会话生命周期和重试可用窗口。

## 8. 近期已完成的修复

| 修改 | 已验证收益 | 当前限制 |
| --- | --- | --- |
| 英文句首和 greeting 保护 | 6 条称呼误判定向集从 0/6 到 6/6，Hello 样本恢复 | 全量仍有新的 addressee 误判 |
| CAM++ target latch 保护 | 修复末尾低分探针覆盖整轮目标判断 | 多人自然音频的首段注册仍不可靠 |
| 中英文 Backchannel 与纯笑声规则 | 中文短反馈 9/9 `C_RESUME`，纯笑声 2/2 SUPPRESS | 英文和中文仍有 ASR 破损及语义边界样本 |
| 空响应 trace 和单次重试 | 6 次触发中 2 次恢复，故障节点已可定位 | 4 次在 Session closing 阶段无法恢复 |
| retry 清理竞态修复 | 定向故障注入可生成单个有效重试回复 | 仍需处理评测窗口和 stale turn |
| FDB participant 转写过滤 | 避免 evaluator 文本污染 assistant transcript | 历史运行仍保留旧诊断口径 |
| MMI 分析器兼容缺失 metadata | 中文 v1.5 可输出关联报告 | 不改变推理或行为结果 |

### 8.1 空响应 P0 修复与定向复测

2026-08-04 已完成两侧修复：

- Agent：允许已提交响应跨过一个已结束、无文本、无 commit、无 wait intent 的空 VAD 后继轮次继续恢复；真实新文本、活跃语音或第二个后继轮次仍会使旧响应失效。
- FDB runner：只要已收到 `transcript_commit` 但尚未观察到 assistant 输出，就在原有 `response_completion_wait_sec` 预算内保持房间和录音存活，不再因为 Agent 已回到 `listening` 而立即断开。
- 测试：本地与服务器发布目录的完整 MMI 套件均为 `250 passed`，并通过编译和服务重启检查；覆盖空后继恢复、真实后继隔离、首轮声纹注册保持、长回答换话题和 `Actually` ASR 变体。

定向复测运行：

`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_response_wait_v2_badcase5_20260804`

| 样本 | 修复前 | 修复后 assistant 字符 | 修复后音频非零率 | `response.done` | warning | 结论 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| Candor Pause 137 | 严格静默 | 204 | 34.63% | 1 | 无 | 恢复完整回复 |
| Candor Pause 184 | 严格静默 | 162 | 30.11% | 1 | 无 | 恢复完整回复 |
| Candor Pause 210 | 严格静默 | 61 | 10.53% | 1 | 无 | 恢复短回复 |
| Candor Turn Taking 83 | 严格静默 | 88 | 26.52% | 2 | 无 | 两个真实用户轮次均有回复 |
| Synthetic Pause 41 | 严格静默 | 150 | 31.06% | 1 | 无 | 恢复完整回复 |

本轮 5/5 均由严格静默恢复为非静音输出，且没有
`missing_response_done`、`missing_assistant_transcript`、`silent_output` 或
`response_completion_timeout`。其中 4 条实际记录了
`client.response_completion_wait(reason=agent_active)`，说明 runner 的延长窗口已进入真实链路。

证据边界：这次模型首轮均正常产生输出，没有再次随机触发 `first_output_timeout`，因此不能把结果表述为
“线上 watchdog 重试 5/5 成功”。空后继轮次下的重试正确性由新增单元测试确定性验证；真实超时后的恢复率还需由固定
100 条 canary 和后续全量运行观察。

### 8.2 固定 100 条与 v11 定向回放

固定 manifest 使用同一份 100 条源样本、140 次实际推理进行前后对比：

| 运行 | 严格静默 | `response_completion_timeout` | `missing_response_done` | 说明 |
| --- | ---: | ---: | ---: | --- |
| `en_qwen_aa_empty_response_v2_canary20x5_20260803` | 1（Turn Taking 38） | 62 | 52 | 修复前固定对照 |
| `en_qwen_aa_response_wait_v2_canary100_fixed_20260804` | 1（Turn Taking 35） | 66 | 57 | runner 记录 122 次 `wait:agent_active` |

固定 100 条的严格静默总数没有下降，只是样本从 38 漂移到 35；这说明 P0 的 5 条历史静默
定向恢复有效，但还不能宣称总体静默率已改善。两轮都在 Pause 8 出现一次“一个 commit、两个
`response.done`”的潜在重复回复，也必须继续监控。该 canary 使用 `--skip-asr --skip-evaluation`，
只能评价推理与输出完整性，不能生成 AA 四维得分。

v10 定向回放目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_mmi_v10_badcase4_20260804`

| 样本 | 控制链结果 | 输出结果 | 判定 |
| --- | --- | --- | --- |
| Turn Taking 35 | 1 commit，无 retract | 137 字、1 个 `response.done`、非静音 | 首轮声纹注册保持修复有效 |
| User Interruption 180 | 两个真实 turn 均 commit | 第二轮正确回答新爱好问题 | 长回答后的 target latch 修复有效 |
| User Interruption 61 | 第二轮 `Angelie` 成功 commit | 已开始正确回答环境纪录片 | endpointing 路径有效，回答过长导致录制窗内缺少第二个 done |
| User Interruption 50 | 第二轮仍 `addressed_to_other` retract | 只保留旧回答 | interruption policy 未复用 ASR 变体融合规则 |

v11 已把同一窄规则补到 interruption policy：只在 Agent 正在 thinking/speaking、命中
`Angeli/Angely/Angelie` 且同轮存在新鲜目标声纹时覆盖普通 vocative；真实 greeting 和明确
第三方称呼仍然拦截。50、61 随后均达到“双 commit、无 retract”，说明控制链缺口已修复。
2026-08-04 11:52 至 12:00 的首次复跑曾被 Qwen TTS WebSocket HTTP 502 阻塞，该轮只保留为
控制链证据。

2026-08-07 TTS WebSocket 已完成真实握手并收到 `session.created`，随后在同一 Agent、同一
样本上完成音频复验：

| 样本 | commit/retract | 第二轮回复 | 音频非零率 | `response.done` | warning | 判定 |
| --- | --- | --- | ---: | ---: | --- | --- |
| User Interruption 50 | 2/0 | 正确切换到周末计划，128 字 | 22.51% | 1 | 无 | 控制链、语义和音频完整通过 |
| User Interruption 61 | 2/0 | 正确给出环境纪录片，390 字 | 49.61% | 0 | `response_completion_timeout`、`missing_response_done` | TTS 与语义通过，长回答在 20 秒完成等待内未正常收尾 |

因此 TTS 故障已经解除，v11 对 50、61 的打断控制修复也获得了真实音频证据。61 暴露的是
长回复的完成事件/录制窗口问题，不是静默或 TTS 不可用；它需要在固定 100 条中继续统计，
并单独检查 TTS/Agent 是否在回答截断后可靠发送 `response.done`。

## 9. 中文结果状态

最近一轮中文全量仍是 2026-07-31 的 915 条运行：

`/opt/Full-Duplex-Bench/runs/health_webrtc_zh/zh_qwen_mmi_badcase_v2_campp_mute_full915_after_en770_20260731`

| 中文维度 | 结果 | 说明 |
| --- | ---: | --- |
| Pause 正式输出率 | 94.98% | 与上文 100% 的停顿安全率口径不同 |
| Turn Taking | 151/155，97.42% | 中文自然接话稳定 |
| Turn Taking 平均延迟 | 8.376 s | 比英文更慢 |
| v1.5 User Interruption | 144/161，89.44% | 仍需重点改善 |
| Backchannel | 179/199，89.95% | 规则覆盖和 ASR 仍有缺口 |
| 中文内部类比代理分 | 94.20% | 非 AA 官方分，也不能与英文直接比较 |

该中文全量早于 8 月 3 日的 greeting、response watchdog 和 v9 规则最终版本，
因此只能作为历史基线，不能代表当前代码的中文最终表现。

## 10. 下一步优先级

### P0：空响应恢复已完成，进入扩大回归

Agent 空后继轮次判断、runner 会话延长、5 条定向回放、第一轮固定 100 条和 v11 的 50、61
音频复验均已完成。固定 100 条的严格静默仍是 1/100，且发现 1 条潜在重复回复，因此下一门禁
是使用 v11 重跑同 manifest 的 100 条，重点观察严格静默、重复回复、
`response_completion_timeout`、`missing_response_done` 和 User Interruption/Backchannel 回退。

### P0：复盘 User Interruption 回归

固定最新一轮未命中 `C_RESPOND` 的 16 条样本，区分 MMI 未打断、回答旧问题、
新问题 STT 丢失、模型语义偏差和 DeepSeek 裁判波动。先做定向重判和回放，避免
通过放宽全部打断阈值破坏 Backchannel。

2026-08-04 已完成首轮人工语义复核：

| 分类 | 数量 | 样本 | 结论 |
| --- | ---: | --- | --- |
| 回答了新问题，但 DeepSeek 判为不确定/未知 | 13 | 3、4、8、9、69、91、93、94、97、118、129、179、191 | 多数是请求补充地点/时间、确认切换话题或澄清 ASR 破损文本，属于 `C_RESPOND` 假阴性 |
| `Actually` 被 ASR 识别成人名后误判第三方称呼 | 2 | 50、61 | `Angely/Angelie` 命中 `addressed_to_other`，新问题被 retract |
| 长旧回答期间 target latch 过期 | 1 | 180 | 新问题文本完整、早期 CAM++ target 已命中，但约 25 秒后 endpoint 以 `target_speaker_not_confirmed` 丢弃 |

按人工语义复核，真实 `C_RESPOND` 为 197/200，即 98.5%；DeepSeek 原始结果 184/200，
即 92.0%。两者相差 6.5 个百分点，后续报告必须同时保留“裁判原始分”和“人工复核分”，
不能把裁判假阴性直接归因于 MMI。

当前已部署 v11，增加两项窄修复：仅在 Agent 正在回答且同轮有新鲜目标声纹证据时，覆盖
`Angeli/Angely/Angelie` 这类已知 `Actually` ASR 变体造成的普通 vocative 误判；
当文本具有明确换话题意图、本轮曾确认目标说话人且不存在决定性非目标证据时，允许 target latch
跨过长回答造成的 TTL；首轮 auto-enrollment 也不会被同 utterance 的后续低相似度探针覆盖。
决定性非目标证据仍优先拦截。完整 MMI 测试在本地和服务器均为 `250 passed`，服务器 Agent
已重启并处于 active。50、61 的控制链和真实音频均已通过；61 仍有长回复完成事件超时，需在
固定 100 条回归中继续观察。

### P1：收敛 addressee 与 CAM++

使用当前 8 条 addressee/CAM++ 静默样本加历史正反例建立固定门禁集。addressee
从词表判断升级为强弱证据融合；CAM++ 先 shadow 验证多段注册和迟滞，再进入
Active。

### P1：降低端到端延迟

当前 Turn Taking 成功率已到 96.64%，下一阶段应分解 7.477 秒延迟中的 endpoint
等待、模型首 token、首音频生成和 RTC 到达时间。MMI 代码处理通常是毫秒级，
不能通过压缩 MMI 决策时间解释全部端到端延迟。

### 回归顺序

1. 已确认 Qwen TTS WebSocket 不再返回 502，并完成真实会话握手。
2. 已重跑 User Interruption 50、61，双 commit、无 retract、第二轮均有非静音输出。
3. 使用 v11 重跑固定 manifest 的英文 100 条 canary，并检查 61 类长回复完成超时。
4. 通过静默、重复回复和 interruption 门禁后跑英文 770 条全量。
5. 最后跑中文 915 条全量。

## 11. 相关文档

- `docs/AA_FDB_BASELINE_COMPARISON_20260730.md`：Shadow、Active 与 CAM++ 早期基线。
- `docs/AA_FDB_FULL_BADCASE_FIX_20260803.md`：英文/中文历史全量和 v9 规则修复。
- `docs/AA_FDB_EMPTY_RESPONSE_RETRY_20260803.md`：空响应 trace、重试和 100 条 canary。
- `docs/mmi-turn-detection-design.md`：MMI-TD 设计与演进方向。
