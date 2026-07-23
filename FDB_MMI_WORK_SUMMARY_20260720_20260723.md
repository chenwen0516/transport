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

- `FDB_MMI_HOLDOUT_V1_20260723.json`
- `FDB_MMI_REPLAY_LOGGED_BASELINE_V4_PER20_20260723.json`
- `FDB_MMI_REPLAY_LOGGED_BASELINE_P11_20260723.json`

下一步是基于统一 `StreamingReplayDetector` 接口实现首个流式文本语义候选，再加入同时间窗声学特征进行 A/B；两者先在已见开发集上调试，冻结后才读取上述留出集结果。
