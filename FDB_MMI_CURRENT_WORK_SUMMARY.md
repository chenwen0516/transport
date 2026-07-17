# FDB 与 MMI 轮次检测当前工作总结

> 更新时间：2026-07-17  
> 工作范围：英文 Full-Duplex-Bench 全量基线、MMI Shadow 日志分析、定向规则修复和小规模回归验证  
> 当前结论：**MMI 继续保持 Shadow 模式，暂不进入 Active 灰度。**

## 1. 执行摘要

目前已经打通英文 FDB 的完整评测链路，并完成了 1225 个样本的全量基线。系统在停顿处理、正常轮次成功率和打断后的回答质量方面表现较好，但平均响应延迟接近 5 秒，而且很容易响应背景讲话或用户对其他人说的话，因此还不是成熟的全双工系统。

在基线之后，已经建立 FDB 样本与 Agent MMI Shadow 日志的精确关联工具，并针对两类明确失败完成修复：

1. 明确强打断不再因为 SpeakerGate 尚未给出身份判决而被压制。
2. 英文 backchannel 词表和 Agent `thinking` 阶段的处理得到补充，避免把附和语当成新问题提交。

定向样本修复有效，但固定 12 条四场景回归显示，普通用户打断仍然会被 `target_speaker_pending` 全部压制，而 SpeakerGate 未锁定时的背景讲话仍可能触发错误打断。下一阶段的核心不是继续修改 prompt，而是让 SpeakerGate 的晚到 verdict 触发 MMI 重算，并补充 warmup 阶段的背景声保护。

## 2. 当前运行环境

| 项目 | 当前配置 | 中文说明 |
|---|---|---|
| FDB 测试框架 | `/opt/Full-Duplex-Bench` | 服务器上的 Full-Duplex-Bench 评测代码、英文数据和运行结果目录。 |
| Agent 代码 | `/opt/health-assistant/backend/livekit_agent` | 当前参与 FDB 会话的健康助手 Agent，不是本地电脑上的进程。 |
| 模型名称 | `health-assistant-qwen` | FDB 请求使用的健康助手模型。服务器实际调度的开发 Agent 名称为 `health-assistant-qwen-dev`。 |
| LiveKit | `ws://127.0.0.1:7880` | FDB 与 Agent 在服务器内部通过本地 LiveKit 通信，绕开了外部域名证书与端口问题。 |
| Token bridge | `http://127.0.0.1:8791/token` | 本地令牌桥根据 Agent 配置生成房间令牌，并显式调度正确的 Agent。 |
| MMI 模式 | `Shadow` | MMI 只生成和记录反事实决策，不执行真实打断、提交或清理动作。 |
| Agent 服务 | `health-agent-fdb-shadow.service` | 用 systemd transient unit 启动的 Shadow Agent 服务。 |

## 3. 已完成工作总览

| 工作项 | 完成情况 | 结果与中文说明 |
|---|---:|---|
| 服务器与 FDB 框架确认 | 已完成 | 已确认 `/opt/Full-Duplex-Bench` 数据、运行脚本、结果目录和 Agent 日志目录。 |
| LiveKit 连接修复 | 已完成 | 改为服务器内部 LiveKit 与本地 token bridge，不再依赖有证书问题的外部 `wss://...:7880`。 |
| Agent 切换 | 已完成 | 当前 FDB 使用 `health-assistant-qwen`，并调度服务器 `/opt/health-assistant` 中的 Agent。 |
| 英文 FDB 全量基线 | 已完成 | 1225 个样本、1723 次实时推理全部纳入 summary，强制对齐 1723/1723 完成。 |
| V1.5 行为重新裁判 | 已完成 | 498 条 V1.5 标签已统一使用同一 DeepSeek 裁判重新生成，避免混用不同裁判。 |
| 缺失裁判结果修复 | 已完成 | 批量裁判缺少 item 时不再静默丢失，会进行两次单条重试并清理旧错误标记。 |
| summary 恢复与合并 | 已完成 | 避免 evaluation-only 或 resume 覆盖原始推理与 ASR 元数据。 |
| 静音失败复现 | 已完成 | 两个 sample-62 静音问题重新运行后仍可复现，已排除偶发文件损坏。 |
| FDB 与 MMI 日志关联器 | 已完成 | 使用 `output_events.jsonl` 中的 LiveKit room ID 精确关联 Agent 日志，并输出 TXT、JSON、CSV。 |
| Shadow 控制口径修复 | 已完成 | MMI 控制动作与 LiveKit 原生后续 lifecycle 分开统计，避免把原生提交误算成 MMI Active 决策。 |
| 英文 backchannel 修复 | 已完成 | 补齐 FDB 中缺失的英文附和词，并覆盖组合短语。 |
| 强打断策略修复 | 已完成 | 明确强控制短语可在身份未知时通过；明确 `NON_TARGET` 仍会阻止打断。 |
| thinking 阶段修复 | 已完成 | 在 Agent 正在生成回复时冻结事件时上下文，正确识别 backchannel，避免异步状态变化污染判定。 |
| 定向样本验证 | 已完成 | `user_interruption/164` 和 `user_backchannel/15` 均从错误决策修复为正确决策。 |
| 四场景小回归 | 已完成 | 固定 seed、每类 3 条，共 12 条；12/12 推理成功并精确关联。 |
| 本地自动化测试 | 已完成 | MMI 与分析器测试共 `169 passed`。 |

## 4. 英文 FDB 全量基线

### 4.1 基线运行信息

| 指标 | 数值 | 中文说明 |
|---|---:|---|
| Run ID | `en_qwen_shadow_full_loopback_20260716_1058` | 英文全量基线的唯一运行标识。 |
| FDB 样本数 | 1225 | 数据集中纳入本次基线的样本总数。 |
| 实际推理次数 | 1723 | 部分 V1.5 样本同时运行 noisy 与 clean 对照，所以推理次数大于样本数。 |
| 强制对齐完成数 | 1723/1723 | 所有输出音频均完成 Qwen3 forced-align 对齐。 |
| V1.5 行为标签数 | 498 | 四类 V1.5 场景统一重新裁判后的有效标签数。 |
| MMI 执行动作数 | 0 | Shadow 决策全部 `executed=false`，没有改变真实会话行为。 |

### 4.2 V1.0 核心结果

| 评测维度 | 结果 | 中文说明 |
|---|---:|---|
| 合成停顿成功率 | 100.00%（137 条） | 用户短暂停顿时，Agent 没有过早抢话。 |
| Candor 自然停顿成功率 | 99.07%（216 条） | 自然对话停顿中仅 2 条在用户继续前提前响应。 |
| 正常轮次成功率 | 99.16%（118/119） | 用户完成普通问题后，Agent 基本都能成功响应。 |
| 正常轮次平均延迟 | 4.93 秒 | 从用户结束到系统响应的总体等待时间偏长。 |
| 用户打断成功率 | 100.00%（200/200） | 基线真实行为最终都对用户打断作出了响应。 |
| 用户打断行为均分 | 4.805/5 | 打断后回答内容总体质量较高。 |
| 用户打断平均延迟 | 5.18 秒 | 能回答，但响应速度仍然偏慢。 |
| ICC 正式轮次率 | 94.55% | Agent 大多输出完整轮次，而不是自然的简短附和。 |
| ICC backchannel 频率 | 0.0163 | Agent 主动产生附和语的频率过低。 |
| ICC 时序分布 JSD | 0.6872 | Agent 附和时机与人类分布差异较大；数值越低通常越接近。 |

### 4.3 V1.5 四场景结果

| FDB 场景 | 场景中文含义 | 基线结果 | 中文结论 |
|---|---|---:|---|
| `background_speech` | 环境中的背景人物讲话，Agent 应忽略 | 正确 21/100（21.00%） | 74/100 直接响应背景讲话，是当前最严重问题之一。 |
| `talking_to_other` | 用户在对其他人说话，Agent 应忽略 | 正确 15/100（15.00%） | 79/100 直接响应，说明缺少可靠的对话对象识别。 |
| `user_backchannel` | 用户说“嗯、好的、我明白”等附和语，Agent 应继续原回复 | 正确 70/98（71.43%） | 错误新响应率为 4.08%，且仍有较多不确定处理。 |
| `user_interruption` | 用户有意打断并提出新内容，Agent 应停止输出并听用户 | 正确 170/200（85.00%） | 有一定打断能力，但低于设计目标 95%。 |

### 4.4 全量基线能力判断

| 能力 | 当前评价 | 中文说明 |
|---|---|---|
| 停顿安全性 | 优秀 | 基本不会因为用户短暂停顿而抢话。 |
| 正常轮次成功率 | 优秀 | 普通问答链路稳定。 |
| 打断后回答质量 | 优秀 | 一旦进入回复，内容质量较高。 |
| 响应速度 | 较弱 | 正常轮次和打断都接近 5 秒。 |
| 用户 backchannel 处理 | 中等偏弱 | 已有能力，但稳定性和覆盖率不足。 |
| 非目标说话人鲁棒性 | 不可接受 | 背景讲话和对其他人讲话会频繁触发 Agent。 |
| 生产级全双工就绪状态 | 未就绪 | 当前不能直接进入生产 Active 模式。 |

## 5. MMI 分析工具与口径修复

新增的分析器会从 FDB 样本的 `output_events.jsonl` 中读取 LiveKit room ID，再匹配：

```text
/opt/health-assistant/backend/livekit_agent/tmp/runs/<timestamp>_<room-id>
```

分析器能够输出每个样本的目标话轮、控制动作、原因、SpeakerGate 状态和 native lifecycle，并汇总混淆矩阵。

| 已修复问题 | 原问题 | 当前处理 |
|---|---|---|
| 复测关联旧 room | 重复运行会在事件文件中留下多条 LiveKit 凭据，旧逻辑读取第一条 | 现在读取最后一条 `client.livekit_credentials`，对应本次最新运行。 |
| 把 native 后续动作算成 MMI | Shadow 下 LiveKit 原生中断或提交后，后续动作会污染反事实指标 | 主指标只统计 MMI 控制通道，原生后续状态单列为 lifecycle。 |
| thinking 状态异步变化 | transcript 到达时 Agent 是 thinking，任务执行时可能已变成 listening | Shadow 在事件发生时冻结上下文，再进行反事实判断。 |
| 隐私风险 | 日志中可能包含用户 transcript | 分析器报告只输出长度、动作和元数据，不输出原始 transcript。 |

## 6. 已完成的定向代码修复

### 6.1 英文 backchannel 词表

补充了以下 FDB 英文附和表达，并同步到正式 JSON 配置和 Python fallback 默认配置：

| 新增表达 | 中文含义或用途 |
|---|---|
| `sure`、`exactly`、`totally`、`indeed` | 表示同意、确认或附和。 |
| `alright`、`yup` | 常见口语确认。 |
| `i see`、`i see that` | 表示理解或正在跟随对话。 |
| `mm-hmm`、`uhuh` | 常见非正式语音附和。 |
| 组合表达 | 支持 `uh-huh sure`、`mm-hmm yeah`、`ok sure`、`yes sure` 等组合。 |

修复后，此前统计出的 16 类 FDB 英文 backchannel 漏项均能被规则识别。

### 6.2 强打断与 SpeakerGate

原策略在 `require_target_speaker=true` 时，会把身份未知的明确强打断也判为 `target_speaker_pending`。当前策略调整为：

| SpeakerGate 状态 | 明确强打断处理 | 中文说明 |
|---|---|---|
| 明确目标说话人 | 允许打断 | 用户身份已确认，可停止 Agent 输出。 |
| 身份未知、没有非目标证据 | 允许明确强打断 | “hold on”“stop”等时间敏感控制命令不应因 verdict 未到而被吞掉。 |
| 明确非目标说话人 | 阻止打断 | 背景人物即使说出类似短语，也不能控制 Agent。 |
| 普通语义插话且身份未知 | 继续等待 verdict | 普通插话仍保持严格策略，避免放大背景声误触发。 |

### 6.3 thinking/pending reply 阶段

当 Agent 已收到前一问题并正在生成回复时，新 transcript 可能在 Agent 真正播放 TTS 前到达。当前逻辑会：

1. 对明确强打断和 backchannel 立即分类。
2. backchannel 产生 `CONTINUE_SPEAKING + ignore_input`，保留待生成回复并忽略附和语。
3. 普通新问题仍走 endpointing，可以替换旧的 pending reply。
4. Shadow 使用事件时快照，避免 thinking 到 listening 的状态竞态。

## 7. 定向样本修复效果

| FDB 样本 | 场景中文说明 | 修复前 | 修复后 | 结论 |
|---|---|---|---|---|
| `v1.5/user_interruption/164` | 用户说“Hold on”并切换到新问题，应立即打断 | `SUPPRESS`（压制），原因是目标说话人待确认 | `INTERRUPT`（打断），原因是明确强打断意图 | 修复有效；明确非目标 verdict 仍能阻止打断。 |
| `v1.5/user_backchannel/15` | 用户说“uh-huh sure”，应继续原回复 | 被当作普通插话或新轮次提交 | `SUPPRESS`（抑制新轮次），原因是 backchannel | 修复有效；Shadow 严格正确率为 100%。 |

这里的 `SUPPRESS` 表示“不打断当前回复，也不把附和语作为新问题”；`INTERRUPT` 表示“停止 Agent 当前输出并开始听用户”。

## 8. 四场景固定小回归

### 8.1 运行信息

| 项目 | 数值 | 中文说明 |
|---|---:|---|
| Run ID | `en_qwen_shadow_mmi_regression_p3_20260717_1558` | 本轮四场景开发回归标识。 |
| 随机种子 | `20260717` | 用于固定抽样，后续必须复用同一 manifest 验证。 |
| 每类样本数 | 3 | 四类场景各抽取 3 条。 |
| 总样本数 | 12 | 这是开发回归，不代表全量统计。 |
| 推理成功 | 12/12 | 所有样本均完成实时会话。 |
| 日志关联 | 12/12 | 所有样本均精确找到对应 Agent MMI 日志。 |
| MMI 决策数 | 74 | 目标话轮及 lifecycle 共记录 74 条决策。 |
| 实际执行数 | 0 | Shadow 模式没有执行真实控制动作。 |

固定样本如下：

| 场景中文名称 | 样本 ID | 中文说明 |
|---|---|---|
| 背景讲话 | 53、56、94 | 验证环境中其他人讲话是否会错误打断 Agent。 |
| 对其他人讲话 | 15、76、89 | 验证用户没有对 Agent 说话时，系统能否保持沉默。 |
| 用户附和 | 28、30、65 | 验证简短 backchannel 是否会被误判为打断或新问题。 |
| 用户打断 | 47、74、91 | 验证普通语义插话能否停止 Agent 并切换说话权。 |

### 8.2 回归结果

| 场景 | 期望动作 | 实际结果 | 严格正确率 | 中文分析 |
|---|---|---|---:|---|
| 背景讲话 | `SUPPRESS`（忽略背景声） | 1 条抑制，2 条错误打断 | 33.33% | SpeakerGate 未锁定时，普通插话规则仍可能把背景声当成用户打断。 |
| 对其他人讲话 | `SUPPRESS`（不响应） | 3 条全部抑制 | 100.00% | 数字正确，但三条都是因为 `target_speaker_pending` 被保守压制，不等于已识别对话对象。 |
| 用户 backchannel | `SUPPRESS`（继续原回复） | 3 条全部抑制 | 100.00% | 本轮词表和 thinking 阶段修复有效，误打断率为 0%。 |
| 用户打断 | `INTERRUPT`（停止输出并听用户） | 3 条全部被抑制 | 0.00% | 普通打断没有明确强控制短语，均被 `target_speaker_pending` 阻止。 |

### 8.3 混淆矩阵

| 缩写 | 数量 | 中文含义 |
|---|---:|---|
| TP（真正例） | 0 | 应打断且 MMI 正确打断的用户插话。 |
| FN（假负例） | 3 | 应打断但被 MMI 错误压制的用户插话。 |
| FP（假正例） | 2 | 不应打断但 MMI 错误打断的背景或非目标讲话。 |
| TN（真负例） | 7 | 不应打断且 MMI 正确保持输出或沉默的样本。 |
| 用户打断召回率 | 0.00% | 本批普通用户打断没有一条被正确放行。 |
| 非打断场景误触发率 | 22.22% | 9 条非打断样本中有 2 条错误触发打断。 |

### 8.4 SpeakerGate 证据

| 场景 | Gate 锁定情况 | 话轮身份判决 | 中文结论 |
|---|---|---|---|
| 用户打断 | 3/3 已锁定 | 3/3 为 `UNKNOWN`（未知） | Gate 已建立目标声纹，但目标话轮期间没有及时向 MMI 提供可用 verdict。 |
| 对其他人讲话 | 3/3 已锁定 | 3/3 为 `UNKNOWN`（未知） | 当前正确抑制主要依赖严格 pending 策略，无法证明说话人识别有效。 |
| 背景讲话 | 1/3 已锁定 | 3/3 为 `UNKNOWN`（未知） | 两条未锁定样本均错误打断，说明 warmup 期保护不足。 |
| 用户 backchannel | 0/3 已锁定 | 3/3 为 `UNKNOWN`（未知） | 本场景主要依靠文本 backchannel 规则正确抑制。 |

## 9. 代码与产物

### 9.1 主要代码变更

| 文件 | 中文说明 |
|---|---|
| `backend/livekit_agent/mmi_turn_detection/interruption_policy.py` | 调整强打断与 SpeakerGate pending 的优先级。 |
| `backend/livekit_agent/mmi_turn_detection/detector.py` | 在 Agent thinking 阶段识别强打断和 backchannel。 |
| `backend/livekit_agent/mmi_turn_detection/runtime.py` | 增强 Shadow 原生中断对比、thinking 快照和事件调度。 |
| `backend/livekit_agent/mmi_turn_detection/mmi-patterns.json` | 扩展正式英文 backchannel 规则并更新版本。 |
| `backend/livekit_agent/mmi_turn_detection/patterns.py` | 同步 Python fallback 默认规则，保证配置失效时行为一致。 |
| `backend/livekit_agent/mmi_turn_detection/context_store.py` | 修正话轮级说话人确认状态的继承范围，减少错误沿用。 |
| `backend/livekit_agent/evaluation/analyze_fdb_mmi.py` | 新增 FDB 与 MMI 日志关联、混淆矩阵、门禁和多格式报告。 |
| `backend/livekit_agent/test/mmi_turn_detection/` | 增加策略、runtime、thinking、强打断和 backchannel 回归测试。 |
| `backend/livekit_agent/test/test_analyze_fdb_mmi.py` | 增加 room 关联、重复复测、控制口径和汇总测试。 |

### 9.2 已生成文档与数据

| 文件 | 中文说明 |
|---|---|
| `docs/FDB_BASELINE_ANALYSIS.txt` | 英文全量基线、定向修复和四场景小回归结论。 |
| `docs/FDB_MMI_SHADOW_REGRESSION_P3.txt` | 12 条固定样本的中文可读 Shadow 分析报告。 |
| `docs/FDB_MMI_SHADOW_REGRESSION_P3.csv` | 每个样本的结构化决策明细，便于 Excel 筛选。 |
| `docs/FDB_MMI_SHADOW_REGRESSION_P3.json` | 完整机器可读报告，便于后续脚本分析。 |
| `docs/FDB_MMI_CURRENT_WORK_SUMMARY.md` | 本文档，汇总目前已经完成的全部主要工作。 |

### 9.3 服务器结果目录

| Run ID | 用途 | 服务器路径 |
|---|---|---|
| `en_qwen_shadow_full_loopback_20260716_1058` | 英文全量基线 | `/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_shadow_full_loopback_20260716_1058` |
| `en_qwen_shadow_fidelity_fix_20260717_1532` | 强打断定向复测 | `/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_shadow_fidelity_fix_20260717_1532` |
| `en_qwen_shadow_backchannel_snapshot_20260717_1554` | backchannel thinking 快照定向复测 | `/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_shadow_backchannel_snapshot_20260717_1554` |
| `en_qwen_shadow_mmi_regression_p3_20260717_1558` | 四场景固定 12 条回归 | `/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_shadow_mmi_regression_p3_20260717_1558` |

## 10. 已知问题

| 优先级 | 问题 | 当前证据 | 影响 |
|---|---|---|---|
| P0 | SpeakerGate verdict 未及时进入 MMI | Gate 已锁定，但 user_interruption 和 talking_to_other 的话轮身份仍全部为 UNKNOWN | 普通用户打断被压制，正确的非目标抑制也缺少可靠身份依据。 |
| P0 | SpeakerGate warmup 期背景声保护不足 | 3 条背景讲话中两条未锁定，并全部错误触发打断 | Agent 可能被会话开始阶段的背景人物打断。 |
| P1 | 端到端响应延迟接近 5 秒 | 正常轮次 4.93 秒，用户打断 5.18 秒 | 交互显得迟钝，不符合自然全双工体验。 |
| P1 | 两个 sample-62 静音失败 | 重新运行仍复现，其中一条有文本但没有有效输出音频 | 可能涉及 TTS、响应完成或 LiveKit 音频发布链路。 |
| P1 | Agent 主动 backchannel 能力弱 | ICC 正式轮次率 94.55%，backchannel 频率仅 0.0163 | Agent 很少像人类一样自然附和。 |
| P2 | 当前没有 MMI 处理耗时指标 | 日志只有 transcript 观察时长，没有事件处理 P95 | 无法验证设计要求中的低延迟门禁。 |

## 11. 下一步计划

| 顺序 | 工作 | 验收方式 | 中文说明 |
|---:|---|---|---|
| 1 | SpeakerGate verdict 触发 MMI 重算 | 同一 12 条 manifest 中，user_interruption 不再全部 pending，同时 talking_to_other 不增加误打断 | verdict 回调必须线程安全，并在当前话轮仍有效时重新执行反事实决策。 |
| 2 | 增加 verdict 与决策延迟日志 | 输出 verdict 产生、回调、MMI 重算的毫秒级时间差 | 判断 verdict 是没有产生，还是产生得晚于 native interruption。 |
| 3 | 增加 warmup/unlocked 背景声保护 | background_speech/53 和 94 不再被普通插话规则直接打断 | 不能通过永久压制所有未知说话人实现，否则会损害真实用户打断。 |
| 4 | 固定 manifest 复测 | 继续使用本轮 12 条样本和同一 seed | 不更换样本掩盖失败，先做可重复的开发集比较。 |
| 5 | 扩大 Shadow 回归 | 四场景每类至少 20 条，再逐步扩到全量 | 小样本通过后才评估是否满足 Active 门禁。 |
| 6 | 拆分端到端延迟 | 记录 ASR final、MMI、LLM 首 token、TTS 首音频时间点 | 找出约 5 秒延迟主要来自哪个环节。 |
| 7 | 定位 sample-62 静音链路 | 对比 Agent 文本、TTS 生成、音轨发布和 FDB 收音事件 | 判断是模型、TTS 还是 RTC 音频发布问题。 |
| 8 | Active 小流量 A/B | Shadow 门禁通过后再做 p20、p50 对照 | 当前不得直接切换 Active。 |

## 12. 当前决策

当前继续维持 **Active BLOCK**，原因如下：

1. 普通用户打断在固定小回归中召回率为 0%。
2. 背景讲话误触发率仍然过高。
3. SpeakerGate 的话轮 verdict 尚未形成可靠闭环。
4. 当前只有 Shadow 反事实结果，还没有真实 Active A/B 增益证据。

不建议直接把 `require_target_speaker` 改为 `false`。该操作可能提高普通用户打断召回，但也会同时放大 `talking_to_other` 和 `background_speech` 的误触发。正确的下一步是补齐 SpeakerGate verdict 到 MMI 重算的链路，再使用同一 manifest 验证收益和副作用。

