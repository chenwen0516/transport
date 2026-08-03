# AA-FDB 全量 Badcase 分析与 MMI-TD 修复报告

日期：2026-08-03

测试对象：服务器 `/opt/health-assistant` 的 `health-assistant-qwen` Agent

运行模式：MMI-TD Active 100%，CAM++ 开启，`audio_mode=mute`，`mmi_mode=negative_only`

## 1. 结论摘要

1. 英文 770 条与中文 915 条全量基线均已完整执行，主推理和 ASR 阶段没有样本失败。
2. 英文 turn-taking 的 12 个失败中，有 6 个由句首普通词被误识别为“对其他人说话”导致。本次修复后，同一 6 条样本从 0/6 提升到 6/6，TOR 为 100%。
3. 中文 backchannel 中选取 9 个语义明确的短反馈 badcase。v8 回归的行为裁判结果为 9/9 `C_RESUME`，误打断为 0/9。
4. v8 中仍有 2 条纯笑声在控制层产生 COMMIT。v9 补充中英文笑声转写后，这 2 条均变为 SUPPRESS，严格控制正确率为 100%。
5. 当前仍不能通过降低 CAM++ 阈值解决剩余问题。失败样本显示“首段自动注册为目标说话人”的假设在自然多说话人音频中不可靠，直接降阈值会增加背景声误通过风险。
6. 另有少量 MMI 已执行 `START_SPEAKING`、但模型没有产生有效音频的空响应。这属于模型或实时生成管线问题，不是 turn detection 规则问题。

## 2. 全量基线

### 2.1 英文 AA-FDB 770 条

运行目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_aa_badcase_v2_campp_mute_full770_v2_20260731`

| 维度 | 样本与结果 | 中文说明 |
| --- | ---: | --- |
| Pause Handling | 99.31% | 暂停期间不抢答的能力，整体稳定 |
| Turn Taking | 107/119，89.92% | 用户自然结束后是否正确接话，是英文最主要短板 |
| Turn Taking 延迟 | 7.433 s | 包含端点等待、模型生成和音频到达，不等于 MMI 代码耗时 |
| User Interruption | 191/200，95.50% | 用户打断时停止当前回复并响应新输入 |
| Backchannel | 94/98，95.92% | 用户只说简短反馈时继续原回复，不错误抢答 |
| 本地 AA proxy | 95.16% | 按本地四维汇总得到的代理分，不是 AA 官网正式提交分 |

### 2.2 中文 FDB 915 条

运行目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_zh/zh_qwen_mmi_badcase_v2_campp_mute_full915_after_en770_20260731`

| 维度 | 样本与结果 | 中文说明 |
| --- | ---: | --- |
| Pause Handling | 227/239，94.98% | 正式汇总口径；单独检查无重叠行为时为 100% |
| Turn Taking | 151/155，97.42% | 中文自然接话明显好于英文 |
| Turn Taking 延迟 | 8.376 s | 端到端口径，不能视为 MMI 内部计算延迟 |
| v1.0 User Interruption | 161/161 | v1.0 take-turn 成功，平均评分 4.168/5，延迟 6.756 s |
| v1.5 User Interruption | 144/161，89.44% | 中文最需要继续改善的维度之一 |
| Backchannel | 179/199，89.95% | 明确存在中文短反馈覆盖不足 |
| 中文类比 proxy | 94.20% | 仅用于内部纵向比较，不能与英文 AA 榜单直接比较 |

## 3. Badcase 根因

### 3.1 英文 Turn Taking 失败 12 条

| 根因 | 数量 | 样本 | 说明 |
| --- | ---: | --- | --- |
| 英文句首词被误判为他人称呼 | 6 | 3、6、32、37、51、97 | `I've`、`Good`、`Yep`、`Gotcha`、`Mask`、`Ah` 被 vocative 规则误识别 |
| CAM++ 错误拒绝目标说话人 | 3 | 35、69、75 | 相似度跨段明显变化，首段自动注册不能代表后续目标说话人 |
| MMI 已接话但模型输出为空 | 2 | 42、118 | 已执行 `START_SPEAKING`，但实时生成管线没有有效输出 |
| 无有效 MMI 目标决策 | 1 | 62 | 需要继续从 VAD、STT 和会话事件链定位 |

### 3.2 中文 Turn Taking 失败 4 条

| 根因 | 数量 | 样本 | 说明 |
| --- | ---: | --- | --- |
| CAM++ 错误拒绝目标说话人 | 1 | 19 | 相似度约 0.027 至 0.202，属于注册假设失败，不宜简单降阈值 |
| MMI 已接话但模型输出为空 | 3 | 18、46、68 | `START_SPEAKING` 已执行，问题在模型或输出管线 |

### 3.3 中文 Backchannel

全量中有 20 条未被行为裁判判为 `C_RESUME`。其中 9 条是语义明确且适合规则修复的短反馈：

`哈哈哈`、`哇哦`、`确实`、`哎，对对`、`爽啊`、`有意思`、`诶诶`、`呵呵`、`哎哎哎`。

没有纳入规则的表达包括：

- `呃，你`：可能是尚未完成的打断，不应强制视为 backchannel。
- ASR 转写为 `the`：属于识别错误，不能通过中文规则修复。
- 内容完整的问题或陈述：部分样本被裁判标为 UNKNOWN，需要单独检查数据与裁判稳定性。

## 4. 本次代码修复

规则版本从 `2026-07-30.aa-fdb-badcase-v7` 更新到 `2026-08-03.aa-fdb-badcase-v9`。

| 修改 | 作用 | 风险控制 |
| --- | --- | --- |
| 英文句首保护词增加 `good/yep/gotcha/ah/mask/i've` | 避免普通话语起始词被当作他人姓名 | 仅影响带句首标点的单词称呼检测 |
| 中文 backchannel 增加明确短反馈 | 抑制“确实、哇哦、有意思”等反馈触发新回复 | 使用 whole-expression 精确匹配，不匹配带实质内容的长句 |
| 增加中英文纯笑声形式 | 覆盖 `Ha ha ha`、`嘿嘿嘿` 等 ASR 变体 | 仅匹配整句笑声，`Haha, can you explain...` 不匹配 |
| 分析器允许缺少 `metadata.json` | 中文 v1.5 样本可输出 MMI 关联报告 | metadata 仍存在时保持原行为 |

涉及文件：

- `backend/livekit_agent/mmi_turn_detection/patterns.py`
- `backend/livekit_agent/mmi_turn_detection/mmi-patterns.json`
- `backend/livekit_agent/evaluation/analyze_fdb_mmi.py`
- 对应的规则与分析器测试

本地完整 MMI 测试：`241 passed`。

## 5. 定向回归结果

### 5.1 英文称呼误判 6 条

运行目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_mmi_badcase_v3_turn6_20260803`

| 指标 | 修复前 | 修复后 |
| --- | ---: | ---: |
| 成功接话 | 0/6 | 6/6 |
| TOR | 0% | 100% |
| 平均端到端延迟 | 不适用 | 6.202 s |
| 推理失败 | - | 0 |

### 5.2 中文明确短反馈 9 条（v8）

运行目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_zh/zh_qwen_mmi_badcase_v3_backchannel9_20260803`

| 指标 | 结果 | 说明 |
| --- | ---: | --- |
| 行为裁判 `C_RESUME` | 9/9，100% | 目标行为全部正确 |
| MMI SUPPRESS | 7/9 | 7 条在控制层明确抑制 |
| MMI COMMIT | 2/9 | `Ha ha ha` 和 `嘿嘿嘿` 未命中 v8 词表，但最终行为仍正确 |
| MMI INTERRUPT | 0/9 | 没有错误打断 |
| Agent 日志关联 | 9/9 | 所有样本均找到对应会话与目标轮次 |
| MMI 事件处理延迟 P95 | 1.827 ms | 这是回调到 MMI 决策的代码处理延迟 |

定向裁剪数据执行官方 `get_timing.py` 时返回 1，因此没有生成 v1.5 timing 汇总。该失败只影响裁剪集 timing 聚合，不影响 9 条推理、行为裁判或 MMI 日志关联。

### 5.3 残余纯笑声 2 条（v9）

运行目录：

`/opt/Full-Duplex-Bench/runs/health_webrtc_zh/zh_qwen_mmi_badcase_v3_laugh2_v9_20260803`

| 指标 | v8 | v9 |
| --- | ---: | ---: |
| MMI SUPPRESS | 0/2 | 2/2 |
| MMI COMMIT | 2/2 | 0/2 |
| 严格控制正确率 | 0% | 100% |
| MMI 事件处理延迟 P95 | - | 1.699 ms |

v9 的 2 条回归只执行推理和控制日志分析。行为层已经由 v8 的同一批 9 条完整 ASR/DeepSeek 回归证明为 9/9 `C_RESUME`。

## 6. 仍需解决的问题

### P0：模型或实时输出管线空响应

MMI 已执行 `START_SPEAKING`，但 Agent 没有有效音频输出。下一步应在 response create、首 token、首音频帧和 response done 四个节点增加统一 trace，并对空响应执行一次受控重试。

### P1：CAM++ 注册策略

不能直接降低阈值。建议按以下顺序处理：

1. 优先使用显式目标用户声纹，不再默认把会话首段永久注册为目标。
2. 没有显式声纹时，至少使用多个高置信、同一说话人片段完成注册。
3. 注册置信度不足时采用 fail-open 或只提供 MMI 负向证据，避免直接静音目标用户。
4. 增加目标/非目标独立阈值与迟滞，并用 background、talking-to-other、turn-taking 三类共同校准。

### P1：英文 Backchannel 与 Interruption 剩余样本

英文仍有 ASR 破损、裁判不确定和 addressee 误判个案。应先对剩余样本做小规模固定清单回归，不再通过扩大通用关键词表处理。

## 7. 下一步执行顺序

1. 合并并发布 v9 规则，保留现有 v7 全量结果作为不可覆盖的基线。
2. 为“MMI 已提交但模型无输出”增加 trace 和一次受控重试，回放英文 42/118 与中文 18/46/68。
3. 设计 CAM++ 显式注册/多段注册方案，先 shadow 记录，不立即改变音频门控。
4. 上述两项稳定后，再跑英文 770 条和中文 915 条全量；不要因为定向集提升就推算新的全量 AA 分数。

## 8. 口径说明

- 英文 95.16% 是本地 AA-FDB proxy，不是 Artificial Analysis 官网已提交成绩。
- 中文 94.20% 是内部类比汇总，数据集和英文 AA 榜单不同。
- 定向回归用于验证修复因果，不能替代全量分数。
- MMI `event_processing_latency_ms` 与 FDB 端到端响应延迟是不同指标，前者约为毫秒级，后者包含模型和音频链路，通常为秒级。
