# AA-FDB 空响应追踪与单次重试报告

日期：2026-08-03

测试对象：服务器隔离版本 `health-assistant-a5e4300-empty-response-v1-20260803`

canary 代码提交：`f6ed177`；根据 canary bad case 形成的修复提交：`b1b34ac`。隔离目录名保留了创建时的 `a5e4300` 基线哈希，服务器运行文件已更新到 `b1b34ac` 对应实现。

运行配置：MMI-TD Active 100%，CAM++ 开启，`audio_mode=mute`，`mmi_mode=negative_only`

## 1. 结论

1. 历史 5 个空响应样本不是 MMI 未提交。它们都已经执行 `START_SPEAKING`，但事件链停在 `speech_created -> agent thinking -> agent listening`，没有进入 `agent speaking`。
2. 历史会话用量中存在数百个模型输出 token，但 `output_text_tokens=0`、`output_audio_tokens=0`。这说明 Qwen 只生成了内部推理，没有生成可见最终回答；问题位于模型/实时生成链路，而不是 turn detection 规则。
3. 本次增加了统一响应 trace，并在确认无音频输出时执行最多一次受控重试。重试前会中断旧响应，避免原响应稍后恢复而造成双重播报。
4. 英文 42、118 和中文 18、46、68 五个历史 bad case 已完成真实回放，全部产生有效文本和非静音音频。本轮随机性未再次触发空响应。
5. 使用 `3s` 故障注入强制触发超时后，第 0 次响应被停止，仅发起第 1 次重试；重试产生了与中文输入相关的回答，且只有 1 个 `response_done`，没有重复播报。
6. 正式服务器配置已恢复为 `10s` 首音频超时、最多重试 1 次。代码默认仍关闭该功能，必须显式开启，便于灰度和回滚。
7. 英文 5 个维度各 20 条 canary 共 100 条推理全部完成，出现 3 条静默输出；由此定位出英文称呼误判、说话人证据冲突和取消清理竞态三类问题。
8. 修复后三条静默样本 `189 / 48 / 41` 均产生有效文本、非静音音频和单个 `response.done`，无运行警告。
9. `1s` 故障注入确认旧响应超时后 retry 能继续生成 247 字符回复，不再被旧响应的取消清理回调误杀。
10. 本次 canary 的本地四维代理分约为 95.6%，不是 AA 官方加权分数，也不能替代英文 770 条和中文 915 条全量回归。

## 2. 历史根因

历史空响应样本：

| 数据集 | 样本 | MMI 提交 | 可见文本 | 可见音频 | 根因判断 |
| --- | --- | --- | --- | --- | --- |
| 英文 v1.0 Turn Taking | 42、118 | 已提交 | 0 | 0 | 模型仅生成内部推理，无最终回答 |
| 中文 v1.0 Turn Taking | 18、46、68 | 已提交 | 0 | 0 | 模型仅生成内部推理，无最终回答 |

成功样本从 `speech_created` 到首次 `agent speaking` 的历史分布：

| 数据集 | 样本数 | P50 | P95 | 最大值 |
| --- | ---: | ---: | ---: | ---: |
| 英文 | 107 | 2.690 s | 4.877 s | 6.722 s |
| 中文 | 151 | 2.922 s | 4.228 s | 4.924 s |

因此测试环境采用 `10s`，高于历史正常首音频最大值，并为模型抖动留出余量。

## 3. 代码修改

| 修改 | 作用 | 风险控制 |
| --- | --- | --- |
| 新增 `MMIResponseWatchdog` | 关联 turn、attempt、speech ID，记录提交、生成、内容、音频和完成阶段 | 仅在 MMI Active 且配置开启时创建 |
| 首音频超时检测 | 提交后超过阈值仍未进入 `agent speaking` 时判定异常 | 正式阈值为 10s；默认阈值为 20s |
| 空响应完成检测 | handle 完成但没有文本和音频时识别 `model_empty_response` | 有音频立即确认成功，不触发重试 |
| TTS/播放缺失检测 | 有文本但没有音频时识别 `tts_or_playout_missing` | 与模型空响应分开记录，便于定位 |
| 单次受控重试 | 停止旧 handle 后调用一次 `generate_reply` | `max_retries` 只允许 0 或 1；旧响应停止失败时放弃重试 |
| 重试清理窗口 | 旧 handle 停止后等待 100 ms，再创建 retry | 等待前后均重新校验 pending turn，避免用户已进入新一轮时误重试 |
| 英文称呼保护 | 将 `Cross` 纳入高频话语/识别噪声保护词 | 只收窄首词称呼匹配，不放松明确姓名、职称称呼 |
| 说话人证据融合 | 已锁存目标说话人时，不让瞬时 `bargein` 非目标探针推翻整轮判定 | CAM++ `decide` 明确非目标判定仍保持最高拦截优先级 |
| 同语言恢复指令 | 要求延续当前对话并使用用户相同语言回答 | 不重复写入 user message，避免污染对话历史 |
| Runtime 启动日志 | 输出 `response_watchdog=True/False` | 可直接确认灰度是否真正生效 |

新增 trace 阶段包括：`commit_requested`、`speech_created`、`generation_created`、`first_content`、`first_audio`、`response_done`、`first_output_timeout`、`retry_requested`、`retry_exhausted` 和 `output_confirmed`。

## 4. 五条真实回放

英文运行目录：

`/opt/Full-Duplex-Bench/runs/empty_response_v1/en_qwen_mmi_empty_response_v1_turn2_20260803`

中文运行目录：

`/opt/Full-Duplex-Bench/runs/empty_response_v1/zh_qwen_mmi_empty_response_v1_turn3_20260803`

| 语言 | 样本 | 文本字符数 | 首音频耗时 | 重试次数 | 音频结果 | 说明 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| 英文 | 42 | 226 | 1.972 s | 0 | 非静音 | 正常完成 |
| 英文 | 118 | 171 | 3.388 s | 0 | 非静音 | 正常完成 |
| 中文 | 18 | 214 | 4.693 s | 0 | 非静音 | 回答较长，录制窗口结束前未收到 `response_done` |
| 中文 | 46 | 47 | 5.474 s | 0 | 非静音 | 正常完成 |
| 中文 | 68 | 88 | 5.239 s | 0 | 非静音 | 正常完成 |

样本 18 的警告是 `response_completion_timeout` 和 `missing_response_done`。它已有 214 个文本字符和连续非静音音频，属于回答过长，不属于空响应恢复失败。

## 5. 强制故障注入

运行目录：

`/opt/Full-Duplex-Bench/runs/empty_response_v1/zh_qwen_mmi_empty_response_forced_3s_20260803`

测试将首音频阈值临时降低到 `3s`，回放中文样本 46：

| 阶段 | 结果 |
| --- | --- |
| 第 0 次 `speech_created` | 提交后 2.006 s |
| 第 0 次超时 | 提交后 3.002 s |
| 旧响应停止 | 超时后约 3 ms 完成，未产生音频 |
| 第 1 次重试 | 仅执行一次 |
| 重试首次音频 | 重试后 2.971 s |
| 最终文本 | `挺有意思的啊，人老了反而更爱分享了，您聊得开心吗？` |
| 最终完成事件 | `response_done=1`，无警告 |
| 重复播报 | 未发现 |

另做过一次 `1s` 极限注入。由于它早于约 2s 的 `speech_created`，会在用户消息稳定进入会话上下文前取消请求，得到通用英文问候。该结果证明过低阈值不安全，也支持正式环境保持 `10s`。

## 6. 配置与验证

正式服务器配置：

```text
AGENT_MMI_TURN_DETECTION__EMPTY_RESPONSE_RETRY_ENABLED=true
AGENT_MMI_TURN_DETECTION__EMPTY_RESPONSE_TIMEOUT_MS=10000
AGENT_MMI_TURN_DETECTION__EMPTY_RESPONSE_MAX_RETRIES=1
AGENT_MMI_TURN_DETECTION__EMPTY_RESPONSE_CANCEL_GRACE_MS=3000
```

验证结果：

| 验证项 | 结果 |
| --- | --- |
| 本地 MMI、发布配置、分析器测试 | 253 passed |
| 服务器三类修复定向测试 | 112 passed |
| Python 语法检查 | 通过 |
| `git diff --check` | 通过 |
| 正式 10s Agent 服务 | Active，worker 已注册 |

## 7. 英文 100 条 canary

运行目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_empty_response_v1_canary20x5_20260803`

| AA-FDB 维度 | 样本数 | 结果 | 中文说明 |
| --- | ---: | ---: | --- |
| v1.0 Candor Pause Handling | 20 | 95.0% | 1 条提前响应，其余通过 |
| v1.0 Synthetic Pause Handling | 20 | 100.0% | 本地 pause 指标全部通过 |
| v1.0 Candor Turn Taking | 20 | 95.0% | 本地 turn-over 成功率 95%，平均延迟 7.804 s |
| v1.5 User Interruption | 20 | 95.0% `C_RESPOND` | 1 条被裁判为 `C_UNKNOWN` |
| v1.5 User Backchannel | 20 | 95.0% `C_RESUME` | 1 条被裁判为 `C_UNCERTAIN_HANDLING` |

推理完成率为 100/100，forced alignment 完成率为 140/140。按四个核心维度做未加权本地代理计算约为 95.6%；AA 榜单使用自己的子集、权重和评分流程，因此这里不能称为官方 AA-FDB 得分。

100 条 benchmark 形成 140 个会话响应尝试。首个 attempt 的首音频 P50 为 4.352 s、P95 为 6.631 s、最大值为 9.574 s。trace 中有 2 次 `first_output_timeout` 和 2 次 `retry_requested`：1 条恢复成功，1 条 retry 在创建后约 33 ms 被旧响应清理链中断。最终有 3 条静默输出：

| 样本 | 现象 | 根因 |
| --- | --- | --- |
| `v1.0/candor_pause_handling/189` | 最终未提交回复 | 整轮 CAM++ 已锁存目标说话人，但末尾低相似度 `bargein` 探针被 endpoint policy 当成决定性非目标 |
| `v1.0/candor_turn_taking/48` | 持续命中 `addressed_to_other` | STT 首词 `Cross.` 被英文 vocative 正则误判为人名 |
| `v1.0/synthetic_pause_handling/41` | 首次响应空输出，retry 随即中断 | 旧 speech handle 取消清理与新 retry 创建存在竞态 |

## 8. 修复后定向复测

正式 `10s` 配置运行目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_empty_response_v2_badcase3_20260803`

| 样本 | Assistant 字符数 | `response.done` | 音频非零占比 | 警告 | 结果 |
| --- | ---: | ---: | ---: | --- | --- |
| `candor_pause_handling/189` | 234 | 1 | 33.32% | 无 | 通过 |
| `candor_turn_taking/48` | 119 | 1 | 24.38% | 无 | 通过 |
| `synthetic_pause_handling/41` | 264 | 1 | 50.35% | 无 | 通过 |

另用 `1s` 阈值对样本 41 做故障注入。attempt 0 在 1001 ms 触发 `first_output_timeout`，随后记录 `retry_requested` 和新的 `speech_created`；最终 retry 产生 247 字符回复、单个 `response.done` 和非静音音频。由于 `1s` 也低于正常 retry 首音延迟，trace 会记录 `retry_exhausted`，但 retry 不再被取消，证明 100 ms 清理窗口修复了原竞态。正式服务已经恢复 `10s` 阈值。

## 9. 仍需关注

1. 空响应具有随机性，5 条正常回放只能证明没有回归，不能估算稳定的故障率。后续全量回归要统计 `retry_requested`、重试成功率和重试后重复音频数。
2. 当前成功判据使用 `agent speaking` 作为音频到达代理。若以后要区分 TTS 已生成和 RTC 已发布，应补充首个真实音频帧事件。
3. 样本 18 暴露了回答过长问题。可单独收紧 FDB 测试提示词，但不应把提示词缩短与空响应恢复混为同一项改动。
4. 三条定向复测证明已知根因得到修复，但样本量不足以估算新故障率。下一轮应重跑同一套英文 100 条 canary，与 `f6ed177` 结果做逐样本对比。
5. 若新版 100 条 canary 静默数归零，且 pause、turn-taking、interruption、backchannel 均无显著退化，再启动英文 770 条正式全量；中文 915 条在英文稳定后单独运行。
