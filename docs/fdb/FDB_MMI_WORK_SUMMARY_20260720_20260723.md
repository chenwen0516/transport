# FDB 与 MMI 工作总结（2026-07-20 至 2026-07-23）

## 1. 当前结论

本阶段已经完成英文 FDB 全量基线、MMI Shadow 小样本回归、v1.5 每场景 20 条的成对验证，以及两轮针对性修复。MMI 的打断召回和回调延迟已经达到可用水平，但“用户在对其他人说话”仍出现误打断，因此当前发布结论是 **BLOCK：继续保持 Shadow，不切换到 Active**。

核心判断如下：

| 结论 | 中文说明 |
|---|---|
| Prompt 不是当前主要矛盾 | 主要失败发生在音频、流式 ASR、说话人/寻址判断和时序决策层，仅修改大模型提示词无法稳定解决 |
| 规则层已接近能力边界 | v4/v5 可以修复明确称呼、部分 ASR 变体和强打断前缀，但无法可靠恢复 WebRTC 链路中已经丢失的称呼信息 |
| Shadow 链路可继续使用 | 80 条 v1.5 验证中日志关联完整，MMI 回调 P95 为毫秒级，未实际执行打断，适合作为下一阶段模型验证平台 |
| Active 尚不满足上线条件 | 非打断场景仍有 2 个误打断；严格门禁要求 background、talking_to_other、backchannel 的误打断数为 0 |

## 2. 环境与测试对象

| 项目 | 当前配置 | 中文说明 |
|---|---|---|
| FDB 框架 | `/opt/Full-Duplex-Bench` | 英文/中文全双工测试、行为裁判、强制对齐和结果汇总 |
| Agent 代码 | `/opt/health-assistant/backend/livekit_agent` | 本阶段修改和验证的服务器侧 health-assistant |
| Shadow Worker | `health-agent-fdb-shadow-unique.service` | 独立 Agent，名称为 `health-assistant-qwen-fdb-shadow` |
| Token Bridge | `fdb-token-bridge-shadow-unique.service` | 为 FDB 分配 Shadow Agent，监听端口 8792 |
| LiveKit | `ws://127.0.0.1:7880` | 服务器本地测试链路 |
| 发布模式 | Shadow | 记录 MMI 决策，但不真正执行打断 |

本报告中的 MMI 修复结论针对服务器上的 Shadow Agent，不等同于 CCE 上生产工作负载已经更新。CCE 镜像版本需要在 CCE 工作负载的 Pod/容器镜像信息中单独核对。

## 3. 最近几天的工作时间线

| 日期 | 工作内容 | 结果 |
|---|---|---|
| 7 月 20 日 | 完成 P7 固定 12 条回归 | 四类场景均为 3/3，打断召回 100%，负类误打断率 0；由于样本太小，仅能作为修复冒烟验证 |
| 7 月 21 日 | 整理全量基线、Shadow 指标和发布门禁 | 明确采用“非打断场景任意 FP 即阻止 Active”的严格标准 |
| 7 月 22 日 | 完成 v1.5 每场景 20 条、共 80 条的 v4 成对 Shadow 测试 | 打断召回 95%，负类误打断率 3.33%，结论 BLOCK；定位 3 个失败样本 |
| 7 月 23 日 | 实现 v5 时序寻址、强打断前缀和 ASR 历史；运行 P11 | 修复打断样本 128，但寻址样本 38、49 仍误打断；173 个 MMI 测试通过 |
| 7 月 23 日 | 对样本 49 进行 ASR 复现、语料偏置和重采样实验 | 证实其主要问题是 WebRTC 后音频/识别信息损失，文本规则无法安全恢复 |

## 4. 关键实验结果

### 4.1 英文完整基线

运行目录：`en_qwen_shadow_full_loopback_20260716_1058`

共 1225 个样本、1723 次实时推理，强制对齐成功 1723/1723。

| FDB 版本/维度 | 指标 | 结果 | 中文说明 |
|---|---|---:|---|
| v1.0 合成停顿 | 正确率 | 100%（137） | 合成停顿场景稳定 |
| v1.0 Candor 停顿 | 正确率 | 99.07%（216） | 自然对话停顿基本稳定 |
| v1.0 正常轮次 | 响应率 | 99.16%（118/119） | 能正常接话，但平均响应延迟 4.93 秒 |
| v1.0 用户打断 | 成功率 | 100%（200/200） | 行为裁判平均 4.805/5，平均延迟 5.18 秒 |
| v1.0 ICC backchannel | 正式轮次率 | 94.55% | backchannel 被当成正式轮次的比例偏高 |
| v1.5 background | 正确忽略/继续 | 21/100 | 74/100 出现直接响应，问题严重 |
| v1.5 talking_to_other | 正确忽略/继续 | 15/100 | 79/100 出现直接响应，说明缺少可靠寻址判断 |
| v1.5 backchannel | 正确 | 70/98（71.43%） | 仍有行为不一致，但错误开启新回复仅 4/98 |
| v1.5 interruption | 正确打断 | 170/200（85%） | 有基础能力，但召回仍需提升 |

### 4.2 MMI Shadow 回归对比

| 实验 | 样本构成 | TP/FN/FP/TN | 打断召回 | 负类误打断率 | 发布结论 |
|---|---|---|---:|---:|---|
| P3（7 月 17 日） | 四类各 3 条 | 0/3/2/7 | 0% | 22.22% | BLOCK |
| P7（7 月 20 日） | 四类各 3 条 | 3/0/0/9 | 100% | 0% | 小样本 REVIEW，不足以上线 |
| v4 per20（7 月 22 日） | 四类各 20 条 | 19/1/2/58 | 95% | 3.33% | BLOCK |
| P11 v5（7 月 23 日） | 寻址 6 条、打断 6 条 | 6/0/2/4 | 100% | 33.33% | BLOCK；这是失败样本压力集，比例不可与全量直接比较 |

v4 每场景 20 条的分项结果：

| 场景 | 正确数 | 正确率 | 中文说明 |
|---|---:|---:|---|
| background | 20/20 | 100% | 背景声场景没有误打断 |
| talking_to_other | 18/20 | 90% | 2 条对其他人说话被误判成对助手说话 |
| backchannel | 20/20 | 100% | 19 条抑制、1 条无目标，均未误打断 |
| user_interruption | 19/20 | 95% | 1 条因 SpeakerGate warmup 被抑制 |

该轮 80 条样本全部完成，160 个成对会话无运行错误；日志关联 80/80，MMI 回调耗时 P95 为 2.678 ms，Shadow 实际执行打断次数为 0。

## 5. 代码与策略修复

| 版本 | 修复内容 | 实际效果 |
|---|---|---|
| v4 addressee | 支持小写姓名、`Coach/Trainer/Doctor/Dr` 等称呼、ASR 撇号变体；排除 `oh/or/also/however/instead` 等话语标记 | P7 和针对性 P10 明显改善；完整 per20 仍残留 2 个寻址 FP |
| Analyzer | 增加可选 transcript 诊断、最终裁判文本提取和严格阶段门禁；默认报告仍只输出元数据 | 自动阻止带有任何非打断 FP 的版本进入 Active；对应测试 11 个通过 |
| v5 temporal addressee | 保存最近 12 条 ASR 假设；仅在上一条显式称呼与当前改写共享至少两个词后缀时继承寻址结论 | 机制本身受控，但真实样本 49 的首条 interim 已丢失称呼，未能修复 |
| v5 interruption | 将 `can we talk about`、`can we discuss` 设为强打断前缀，可绕过 warmup | 成功修复样本 128 |

当前模式版本：`2026-07-23.temporal-addressee-v5`。服务器完整 MMI 测试结果为 **173 passed**，服务重启后保持 active。

## 6. 剩余失败样本

| 场景/编号 | 期望语义 | Agent 实际识别/表现 | 当前判断 |
|---|---|---|---|
| talking_to_other/38 | 对 Grant 说明聚会时间 | `Grant game nights at my place, 7 p.m.` 后触发普通打断 | 称呼与正文粘连/改写，规则没有稳定识别目标对象 |
| talking_to_other/49 | 对 IT desk 请求重置密码 | WebRTC 录音重识别为 `Yes...` 或 `It is...`，随后触发普通打断 | 称呼的关键声学信息在链路后已经丢失，不能用文本规则可靠恢复 |
| user_interruption/128 | `Can we talk about laptops instead?` | v4 因 `speaker_gate_warmup` 抑制 | v5 已通过强打断前缀修复 |

注意：样本 49 的数据集元数据、参考文本和实际发音存在一定不一致，报告中必须保留原始音频、Agent 录音和流式假设，避免只看参考文本下结论。

## 7. ASR 专项排查

| 实验 | 结果 | 结论 |
|---|---|---|
| 原始 `current_turn.wav` 多次识别 | 较稳定得到 `Edes, can you...` | 原始切片中仍存在称呼线索 |
| 完整源 `input.wav` 多次识别 | 较稳定得到 `Eds, can you...` | 单独离线/直连识别仍能保留部分称呼 |
| Agent WebRTC 录音重识别 | 在 `Yes...`、`It is...` 之间变化 | 实际链路后的信息已显著退化 |
| Qwen corpus 语料偏置 | 三次结果仍为 `Yes`、`Yes`、`It is` | 添加 `Edes/Eddes/IT desk` 不能恢复缺失信息 |
| language=None 与 language=en | 无实质改善 | 语言参数不是根因 |
| 线性重采样与 stateful RTC 重采样 | 分别出现 `Yes`、`It is`，复测仍波动 | 没有证据证明替换重采样器可以修复 |

Qwen 实时 ASR 支持通过 `session.input_audio_transcription.corpus.text` 提供上下文偏置，但流式结果不提供可直接使用的词级时间戳；时间对齐仍需依靠离线 forced align。当前不能声称 corpus 或重采样已经解决问题。

参考资料：

- [Qwen 实时语音识别文档](https://docs.qwencloud.com/developer-guides/speech/asr-realtime)
- [Qwen3-ASR 官方仓库](https://github.com/QwenLM/Qwen3-ASR)

## 8. 与论文方案的对应关系

| 论文 | 可借鉴能力 | 对当前项目的启示 |
|---|---|---|
| [FastTurn](https://arxiv.org/abs/2604.01897) | 融合声学和流式语义信息，兼顾低延迟与鲁棒性 | 不应只依赖最终 ASR 文本；应在音频仍保留称呼和语调时进行判断 |
| [SoulX-Duplex](https://arxiv.org/abs/2603.14877) | 插件式流式状态预测和流式 ASR 语义 | 可作为独立 Shadow 模块接入，不必立即改动主对话模型 |
| [Easy Turn](https://arxiv.org/abs/2509.23938) | 声学与语言双模态，区分 complete/incomplete/backchannel/wait | 当前四类 FDB 场景可以映射为更细的控制状态，减少二分类规则冲突 |
| [LLM-enhanced DM](https://arxiv.org/abs/2502.14145) | 轻量语义 VAD 与控制 token | 适合探索低成本语义决策器，但仍需单独处理“说给谁听”的 addressee 维度 |
| [Phoenix-VAD](https://arxiv.org/abs/2509.20410v2) | 滑窗式流式语义端点检测 | 可用于不完整句、等待和接话时机判断，补足纯声学 VAD |

这些论文主要解决“现在是否该接话/打断”，而 FDB 的 `talking_to_other` 还要求回答“这句话是否对助手说”。下一阶段的状态定义应显式包含 `ADDRESSED_OTHER` 或等价侧信号，不能只照搬 endpoint 模型的 complete/incomplete 分类。

## 9. 已验证与未验证边界

| 状态 | 内容 |
|---|---|
| 已验证 | Shadow 链路、日志关联、严格门禁、规则 v4/v5、强打断前缀、80 条 v1.5 per20、P11 失败集、Agent 录音上的 ASR 复现 |
| 尚未验证 | MMI Active 真执行效果、CCE 工作负载镜像是否包含这些修改、完整 v1.5 全量上的 v5 表现、声学+语义模型的收益、真实用户多说话人环境 |
| 不能推出 | P7 的 12/12 不能证明可上线；FDB 基线打断成功率高不能证明寻址正确；离线原始音频识别正确不能代表 WebRTC Agent 链路正确 |

## 10. 下一阶段工作

1. 保持 Shadow 和严格门禁：非打断场景 FP 必须为 0，打断召回目标不低于 95%。
2. 固化样本 38、49、128 为开发回归集，同时建立独立留出集，避免继续针对少量样本堆规则。
3. 生成离线回放数据：关联 Agent 实际 24 kHz 音频、流式 ASR interim/final、SpeakerGate 状态、MMI 决策、FDB 标签和行为裁判结果。
4. 定义独立检测器输出：`INTERRUPT`、`BACKCHANNEL`、`ADDRESSED_OTHER`、`CONTINUE`、`UNCERTAIN`，再映射到现有 MMI 动作。
5. 先在独立进程或插件中实现声学+流式文本原型，只写 Shadow 日志；优先比较 FastTurn/Easy Turn/SoulX-Duplex 类方案。
6. 在留出集通过后重新运行英文 v1.5 per20；只有满足零负类 FP、打断召回不低于 95%、延迟稳定，才进入更大规模或全量测试。
7. 最后才做小流量 Active p20 验证，并单独确认 CCE 镜像版本和回滚方式。

## 11. 运行与产物索引

| 产物 | 标识 |
|---|---|
| 英文完整基线 | `en_qwen_shadow_full_loopback_20260716_1058` |
| P3 回归 | `en_qwen_shadow_mmi_regression_p3_20260717_1558` |
| P7 回归 | `en_qwen_shadow_mmi_regression_p7_20260720_1105` |
| v4 每场景 20 条 | `en_qwen_shadow_latest_v4_ccepaired_v15_per20_20260722` |
| P11 v5 压力回归 | `en_qwen_shadow_mmi_temporal_p11_v5_20260723` |
| P11 子集 | `data_subsets/en_mmi_temporal_p11_20260723` |
| MMI 分析器 | `backend/livekit_agent/evaluation/analyze_fdb_mmi.py` |

本文未包含 Token、API Key、服务器密码等敏感信息。凭据曾在命令行和对话中使用，后续应统一轮换并改用服务器密钥管理或受限环境变量文件。

## 12. 7 月 23 日续作：离线回放数据准备

在完成上述总结后，已继续实现并运行第一版 FDB + MMI 多模态回放导出器：

| 项目 | 结果 | 中文说明 |
|---|---:|---|
| 导出器 | `evaluation/export_fdb_mmi_replay.py` | 按 LiveKit room 关联 FDB 与 Agent，不复制大体积 WAV，只写绝对路径和对齐时间线 |
| 导出器与分析器测试 | 13 passed | 覆盖时间对齐、标签映射、控制终态口径和默认隐藏 transcript |
| 完整相关测试 | 186 passed | 包含 MMI、分析器和回放导出器测试 |
| v4 per20 回放集 | 80/80 replay-ready | 四类各 20 条，均具备 raw/STT 音频、流式 ASR、MMI 和 SpeakerGate 时间线 |
| P11 v5 回放集 | 12/12 replay-ready | 包含 6 条 `ADDRESSED_OTHER` 和 6 条 `INTERRUPT` 压力样本 |

回放标签显式区分 `CONTINUE`、`ADDRESSED_OTHER`、`BACKCHANNEL` 和 `INTERRUPT`；后续模型还应支持 `UNCERTAIN`，但 FDB 当前没有该状态的直接监督标签。

服务器产物：

- v4 per20：`en_qwen_shadow_latest_v4_ccepaired_v15_per20_20260722/mmi_replay_v1/manifest.jsonl`
- P11 v5：`en_qwen_shadow_mmi_temporal_p11_v5_20260723/mmi_replay_v1/manifest.jsonl`

样本 49 的回放时间线验证了修复前后差异：v4 会先产生 `Edes, can you?`，随后改写为 `It is...`；v5 的第一条目标轮 ASR 已直接是 `It is. Can you?`。这进一步证明 addressee 检测必须尽量利用早期流式语义和声学证据，不能只读取最终文本。

操作过程中发现一次非交互 `uv run` 重建了不完整的 `.venv`。已使用原始 `uv.lock`、独立目录和国内镜像恢复环境，完成 186 个测试后原子切换，并重启验证：Shadow Worker 和 Token Bridge 均为 active，Worker 已重新注册为 `health-assistant-qwen-fdb-shadow`。损坏环境保留为 `.venv.broken_20260723_1013`，便于审计，未影响 FDB 产物。

因此下一项工程工作已从“准备回放数据”推进为“实现候选检测器回放接口与首个声学 + 流式文本基线”，仍只输出 Shadow 决策，不接管 Active 控制。

## 13. 7 月 23 日续作：留出集与 Replay Runner

已完成确定性留出集选择器和事件驱动 Replay Runner，生产 MMI 路径未改动。

| 项目 | 结果 | 中文说明 |
|---|---:|---|
| 服务器完整相关测试 | 192 passed | 包含 173 个 MMI 测试、分析器/导出器以及新增的选择器和回放测试 |
| 调参排除范围 | 28 个 Shadow run | 排除完整基线之外的 Shadow 调参、边界、badcase 和 per20 manifest |
| 排除样本并集 | 23/23/23/24 | 依次为 background、talking_to_other、backchannel、interruption |
| 冻结留出集 | 80 条 | 四类各 20 条，seed=`20260723`，使用硬链接生成，不重复复制源音频块 |
| v4 per20 历史回放 | 80/80 对齐 | 复现 TP=19、FN=1、FP=2、TN=58，控制结果与正式分析器完全一致 |
| P11 历史回放 | 12/12 对齐 | 复现 TP=6、FN=0、FP=2、TN=4 |

留出集路径：

`/opt/Full-Duplex-Bench/data_subsets/en_mmi_holdout_v1_20260723`

Replay Runner 按时间合并以下输入：

- Agent `stt_input` 或 `raw_input` PCM，每 200 ms 一帧；
- 流式 ASR interim/final；
- Agent/User 状态变化；
- SpeakerGate 事件；
- 历史 MMI 决策。

v4 per20 实际回放共处理 10,458 个音频块、495 条 ASR、509 条 MMI 决策、434 条 SpeakerGate 事件和 1,026 条状态事件。历史日志基线只用于证明回放口径正确，不作为新的候选模型成绩。

严格口径说明：完整英文基线历史上已经覆盖全部 FDB v1.5，因此现有数据无法宣称“从未运行过”。本留出集的含义是**未进入后续 28 个 MMI 调参/回归 run**。当前 v5 不提前运行该留出集，待候选检测器冻结后再进行一次性评估。

归档文件：

- [holdout v1 清单](../../results/fdb/holdout-v1/FDB_MMI_HOLDOUT_V1_20260723.json)
- [v4 per20 历史回放](../../results/fdb/development/FDB_MMI_REPLAY_LOGGED_BASELINE_V4_PER20_20260723.json)
- [P11 历史回放](../../results/fdb/development/FDB_MMI_REPLAY_LOGGED_BASELINE_P11_20260723.json)

下一步是基于统一 `StreamingReplayDetector` 接口实现首个流式文本语义候选，再加入同时间窗声学特征进行 A/B；两者先在已见开发集上调试，冻结后才读取上述留出集结果。

## 14. 7 月 23 日续作：流式语义混合候选 v3.2

已实现并冻结首个可回放的流式语义混合候选，版本为
`2026-07-23.semantic-hybrid-v3.2-frozen`。该候选仍只用于离线/Shadow
评估，没有接管生产 Agent 的 Active 控制。

候选采用两层判定：

1. Qwen `qwen3-30b-a3b` 根据流式 ASR 历史判断 `INTERRUPT`、
   `ADDRESSED_OTHER`、`BACKCHANNEL`、`CONTINUE` 或 `UNCERTAIN`；
2. 高精度话轮标记补充 `Wait`、`before I forget`、`by the way`、
   `Hey, can...` 和显式改题等抢话信号，但 `ADDRESSED_OTHER` 具有更高优先级。

为保证回放忠实度，同时修复了两个事件时序问题：

- 同一毫秒内不再按固定事件类型排序，而是使用原始 `created_at` 恢复真实先后；
- 当 ASR 早于 User VAD 状态事件到达、且 Agent 正在 speaking/thinking 时，
  回放器会从首个新 ASR 假设推断重叠话轮开始，并避免后续 VAD 事件重复开轮。

| 验证集 | 方法 | TP/FN/FP/TN | 严格正确率 | 打断召回 | 非打断误停率 | 中文说明 |
|---|---|---|---:|---:|---:|---|
| P11 压力集 | 历史 v5 Shadow | 6/0/2/4 | 83.33% | 100% | 33.33% | 两条 talking-to-other 被误停 |
| P11 压力集 | 语义混合 v3.2 | 6/0/1/5 | 91.67% | 100% | 16.67% | 少一条误停，剩余错误为 ASR 信息丢失 |
| v4 per20 开发集 | 历史日志基线 | 19/1/2/58 | 96.25% | 95% | 3.33% | 原始 80 条 Shadow 结果 |
| v4 per20 开发集 | 语义混合 v3.2 | 20/0/1/59 | 98.75% | 100% | 1.67% | 同时减少一个漏检和一个误停 |

v3.2 在 per20 上的目标语义状态正确率为 65/80（81.25%）。这低于控制正确率，
说明它能正确决定“是否停下”，但对 `CONTINUE`、`BACKCHANNEL` 和
`ADDRESSED_OTHER` 的细分类仍需改进，不能把 98.75% 解释为五分类准确率。

唯一剩余控制错误是 `talking_to_other/49`：预期称呼 “IT desk”，Agent
流式 ASR 输出为 “It is. Can you reset my password, please?”。仅凭该文本与真正
面向助手的请求无法可靠区分，因此未增加样本特判。后续应从重叠起始音频中恢复
称呼声学证据。

语义预计算共完成 244 次请求，成功率 100%；API 延迟 P50 为 870.928 ms，
P95 为 1,150.476 ms，最大 2,793.685 ms。该延迟不适合直接同步接入实时
Active 路径，下一阶段需采用本地轻量模型、蒸馏或并行异步早判。

冻结时服务器相关测试为 **232 passed**。冻结校验值：

| 文件 | SHA-256 |
|---|---|
| `evaluation/fdb_mmi_semantic.py` | `fd42e37b5f128726599d2ada3254de01c4b7e044f09d6b44aea944f9cf00cdd0` |
| `evaluation/run_fdb_mmi_replay.py` | `13169107d7d8c7b55a585f971a2aa908a29da9bb2b1b9d8081407ebf66a9d7d0` |
| `holdout_manifest.json` | `8ef80ef3a22dd1cc6bbe1497d001082500cb296a658e072b330182b345ac6917` |

归档文件：

- [v3.2 P11 结果](../../results/fdb/development/FDB_MMI_SEMANTIC_HYBRID_V3_2_P11_20260723.json)
- [v3.2 per20 结果](../../results/fdb/development/FDB_MMI_SEMANTIC_HYBRID_V3_2_PER20_20260723.json)

冻结留出集已按 `en_qwen_shadow_mmi_holdout_v1_20260723` 启动一次性采集。
完成后只补充最终结果，不再根据留出集错误修改 v3.2。

采集任务由 systemd 单元 `fdb-mmi-holdout-v1-20260723.service` 托管。服务器
入口曾在进度 48/80 时暂时不可达，但后台任务未中断，最终于 12:38 完成 80/80。
该网络事件没有触发样本重选、候选修改或推理重跑。

## 15. 一次性留出集最终结果

运行目录：

`en_qwen_shadow_mmi_holdout_v1_20260723`

80 条样本全部完成推理并成功关联 Agent 日志，四类场景各 20 条，共 160 次成对
会话；没有 Agent not-ready 重试。3 条 `response_completion_timeout` warning
均来自 backchannel 会话的回复等待阶段，不影响 MMI 时间线和 replay-ready
完整性。

| 留出集方法 | TP/FN/FP/TN | 严格正确率 | 打断召回 | 非打断误停率 | 结论 |
|---|---|---:|---:|---:|---|
| 历史 Shadow 日志 | 18/2/2/58 | 95.00% | 90% | 3.33% | BLOCK |
| 冻结语义混合 v3.2 | 16/4/1/59 | 93.75% | 80% | 1.67% | BLOCK |

冻结 v3.2 没有通过预设门禁。它减少了一个非打断误停，但比历史 Shadow 多漏掉
两个真实打断，整体严格正确数从 76/80 降至 75/80；目标语义状态正确率为
61/80（76.25%）。因此开发集上的 79/80 提升没有在留出集复现，不能进入 Active。

冻结候选的 238 次语义请求全部成功。API 延迟 P50 为 824.151 ms，P95 为
1,062.035 ms，最大 3,256.086 ms；即便准确率达标，该同步延迟也不满足实时
控制路径要求。

### 15.1 五个控制错误

| 样本 | 错误 | 关键现象 | 后续含义 |
|---|---|---|---|
| `background_speech/40` | FP | 背景语音“关闭烤箱”被文本模型视为面向助手的直接命令 | 必须使用说话人/声学证据，文本命令形式无法判断来源 |
| `user_interruption/75` | FN | 参考文本中的 `instead` 在流式 ASR 中丢失 | 需要利用现有 MMI 强打断信号，不能让保守语义模型单独否决 |
| `user_interruption/166` | FN | `Just a minute` 被识别为 `Open just a minute` | 需要更稳健的流式抢话表征或声学模型 |
| `user_interruption/179` | FN | `By the way` 被识别为 `Either way` | 关键 discourse cue 的声学信息在文本化时丢失 |
| `user_interruption/183` | FN | `Actually` 被识别成虚构称呼 `Julie`，继而误判 `ADDRESSED_OTHER` | 需要抑制晚到且不稳定的称呼假设，并保留音频证据 |

5 个错误中至少 4 个与关键 ASR 信息丢失或改写直接相关。SpeakerGate 在
`75`、`166`、`183` 后段给出了 `TARGET_CONFIDENT`，说明说话人证据有价值；
但 background FP 在 warmup 阶段没有有效 verdict，不能只依靠 SpeakerGate。

### 15.2 下一候选方向

v3.2 留出集已经解封为错误分析数据，后续不得继续作为新版本的最终留出集。
下一候选应采用“现有低延迟 MMI 主路径 + 语义高置信纠错 + 声学/说话人证据”
的分层结构：

1. 保留现有 MMI 的强打断和普通有效插话结果，语义模型不能无条件覆盖；
2. 仅在稳定早期称呼、明确 backchannel 或可靠非目标说话人证据出现时抑制打断；
3. 对晚到且与早期 ASR 不一致的称呼降低可信度；
4. 从重叠起始音频直接提取声学特征，解决背景命令和 discourse cue 误识别；
5. 创建新的调参隔离留出集，排除本次 80 条，再冻结并做一次性评估。

归档文件：

- [holdout v1 replay 导出](../../results/fdb/holdout-v1/FDB_MMI_HOLDOUT_REPLAY_EXPORT_20260723.json)
- [holdout v1 历史基线](../../results/fdb/holdout-v1/FDB_MMI_HOLDOUT_LOGGED_BASELINE_20260723.json)
- [holdout v1 v3.2 结果](../../results/fdb/holdout-v1/FDB_MMI_HOLDOUT_SEMANTIC_HYBRID_V3_2_20260723.json)

## 16. 分层纠错 overlay v4 与 holdout v2

在 v3.2 留出集失败后，没有继续让 Qwen 单独控制，而是实现独立文件
`evaluation/fdb_mmi_semantic_overlay.py`。冻结版本为
`2026-07-23.semantic-overlay-v4-frozen`。

v4 的控制原则是：

- 现有低延迟 MMI 是主决策，`START_LISTENING` 默认保留；
- 仅当首个稳定语义明确寻址他人、明确 backchannel，或整轮都是无请求形式的
  陈述句时，才抑制基础 MMI 的打断；
- 反向补打断只接受高精度抢话/改题 cue，普通文本命令不能覆盖基础抑制；
- 使用两条连续 partial 或一条 final 确认，避免单个流式假设直接改控制。

已用开发集结果：

| 数据集 | 样本数 | TP/FN/FP/TN | 严格正确率 |
|---|---:|---|---:|
| P11 压力集 | 12 | 6/0/1/5 | 91.67% |
| v4 per20 | 80 | 20/0/0/60 | 100% |
| 已解封 holdout v1 | 80 | 20/0/0/60 | 100% |

上述结果仅用于开发，不能替代新留出集。为此创建 holdout v2，额外排除 holdout
v1 的 80 条样本：

| 项目 | 结果 |
|---|---:|
| 排除样本总数 | 173 |
| background 排除数 | 43 |
| talking-to-other 排除数 | 43 |
| backchannel 排除数 | 43 |
| interruption 排除数 | 44 |
| 新留出集 | 四类各 20 条，共 80 条 |
| seed | `20260724` |

holdout v2 运行目录：

`en_qwen_shadow_mmi_holdout_v2_20260723`

80/80 样本、160 次成对会话均成功，没有 Agent not-ready 重试。3 条
`response_completion_timeout` warning 不影响 MMI replay 完整性。

### 16.1 holdout v2 最终结果

| 方法 | TP/FN/FP/TN | 严格正确率 | 打断召回 | 非打断误停率 |
|---|---|---:|---:|---:|
| 历史 Shadow 日志 | 18/2/0/60 | 97.50% | 90% | 0% |
| 语义单独决策 v3.2 | 17/3/3/57 | 92.50% | 85% | 5% |
| 分层纠错 overlay v4 | 20/0/0/60 | 100% | 100% | 0% |

v4 在完全隔离的新留出集上满足控制门禁。它只改变两条历史结果：

- `user_interruption/80`：早期流式 ASR 保留了
  `Actually, let's switch gears...`，即使最终上下文被改写为 `Recently.`，
  overlay 仍正确捕获改题；
- `user_interruption/162`：`before I forget` 连续出现在 partial/final，
  overlay 正确补回基础 MMI 漏掉的打断。

目标语义状态正确率仍只有 63/80（78.75%），因此 100% 是控制二分类结果，
不是五状态语义分类结果。

### 16.2 冻结与上线边界

冻结时服务器相关测试为 **240 passed**。校验值：

| 文件 | SHA-256 |
|---|---|
| `evaluation/fdb_mmi_semantic_overlay.py` | `9c16b459636e7e1857b06e3a82c4527b9f254323a3909cc52cb4508f3fc9dd5f` |
| `evaluation/fdb_mmi_semantic.py` | `fd42e37b5f128726599d2ada3254de01c4b7e044f09d6b44aea944f9cf00cdd0` |
| `evaluation/run_fdb_mmi_replay.py` | `13169107d7d8c7b55a585f971a2aa908a29da9bb2b1b9d8081407ebf66a9d7d0` |
| holdout v2 manifest | `8e56808219d0a1151d28582f360b9546f49d0afb5eb25cd6f5b4bb72ad08325d` |

该结果允许进入**在线 Shadow 集成**，仍不允许直接 Active：

1. 当前 overlay 回放使用历史 MMI 事件，尚未接入实时 runtime；
2. replay 的事件时间戳没有计入在线 Qwen 请求等待时间；
3. holdout v2 的 Qwen API 延迟 P50 为 873.949 ms、P95 为
   1,192.187 ms，不能同步阻塞实时控制；
4. 确定性 cue 补打断可以走本地快速路径，语义抑制应异步运行或换成本地轻量模型；
5. 在线 Shadow 需要记录基础动作、overlay 建议、实际到达延迟和来不及生效的比例，
   再运行更大规模 FDB 与真实流量观测。

归档文件：

- [holdout v2 清单](../../results/fdb/holdout-v2/FDB_MMI_HOLDOUT_V2_20260723.json)
- [holdout v2 replay 导出](../../results/fdb/holdout-v2/FDB_MMI_HOLDOUT_V2_REPLAY_EXPORT_20260723.json)
- [holdout v2 历史基线](../../results/fdb/holdout-v2/FDB_MMI_HOLDOUT_V2_LOGGED_BASELINE_20260723.json)
- [holdout v2 v3.2 结果](../../results/fdb/holdout-v2/FDB_MMI_HOLDOUT_V2_SEMANTIC_HYBRID_V3_2_20260723.json)
- [holdout v2 overlay v4 结果](../../results/fdb/holdout-v2/FDB_MMI_HOLDOUT_V2_SEMANTIC_OVERLAY_V4_20260723.json)
