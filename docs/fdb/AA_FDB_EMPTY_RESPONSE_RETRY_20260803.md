# AA-FDB 空响应追踪与单次重试报告

日期：2026-08-03

测试对象：服务器隔离版本 `health-assistant-a5e4300-empty-response-v1-20260803`

运行配置：MMI-TD Active 100%，CAM++ 开启，`audio_mode=mute`，`mmi_mode=negative_only`

## 1. 结论

1. 历史 5 个空响应样本不是 MMI 未提交。它们都已经执行 `START_SPEAKING`，但事件链停在 `speech_created -> agent thinking -> agent listening`，没有进入 `agent speaking`。
2. 历史会话用量中存在数百个模型输出 token，但 `output_text_tokens=0`、`output_audio_tokens=0`。这说明 Qwen 只生成了内部推理，没有生成可见最终回答；问题位于模型/实时生成链路，而不是 turn detection 规则。
3. 本次增加了统一响应 trace，并在确认无音频输出时执行最多一次受控重试。重试前会中断旧响应，避免原响应稍后恢复而造成双重播报。
4. 英文 42、118 和中文 18、46、68 五个历史 bad case 已完成真实回放，全部产生有效文本和非静音音频。本轮随机性未再次触发空响应。
5. 使用 `3s` 故障注入强制触发超时后，第 0 次响应被停止，仅发起第 1 次重试；重试产生了与中文输入相关的回答，且只有 1 个 `response_done`，没有重复播报。
6. 正式服务器配置已恢复为 `10s` 首音频超时、最多重试 1 次。代码默认仍关闭该功能，必须显式开启，便于灰度和回滚。
7. 本次是故障恢复定向验证，不产生新的 AA-FDB 全量分数，也不能替代英文 770 条和中文 915 条全量回归。

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
| 本地 MMI、发布配置、分析器测试 | 250 passed |
| 服务器隔离版本同范围测试 | 250 passed |
| Python 语法检查 | 通过 |
| `git diff --check` | 通过 |
| 正式 10s Agent 服务 | Active，worker 已注册 |

## 7. 仍需关注

1. 空响应具有随机性，5 条正常回放只能证明没有回归，不能估算稳定的故障率。后续全量回归要统计 `retry_requested`、重试成功率和重试后重复音频数。
2. 当前成功判据使用 `agent speaking` 作为音频到达代理。若以后要区分 TTS 已生成和 RTC 已发布，应补充首个真实音频帧事件。
3. 样本 18 暴露了回答过长问题。可单独收紧 FDB 测试提示词，但不应把提示词缩短与空响应恢复混为同一项改动。
4. 下一轮先做每维 20 条 Active canary；确认重试率、延迟和行为裁判稳定后，再决定是否重跑英文 770 条与中文 915 条全量。
