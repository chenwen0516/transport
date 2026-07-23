# FDB 与 MMI 轮次检测工作总结

> 更新时间：2026-07-20
> 当前阶段：固定 12 条 Shadow 门禁通过，准备受控 Active p20
> 当前结论：**Active REVIEW，不是自动 GO，也不再是架构性 BLOCK。**

## 1. 执行摘要

英文 FDB 全量基线、MMI Shadow 接入、SpeakerGate verdict 闭环和固定清单回归均已完成。此前 P3 暴露的普通用户打断全被 `target_speaker_pending` 压制、背景声可能误打断等问题，已经通过 verdict 回流重判、目标说话者注册、warmup pending、英文称呼识别和 thinking 阶段路由修复。

最终 P7 固定清单共 12 条，四类场景严格正确率均为 100%，强中断召回率 100%，非中断误触发率 0%，日志关联率 100%。由于本轮仍是 Shadow，真实控制动作数为 0；因此下一步应在隔离 worker 上进行限流、可回滚的 Active p20，而不是直接切换生产流量。

## 2. 当前环境

| 项目 | 当前配置 | 中文说明 |
|---|---|---|
| FDB 框架 | `/opt/Full-Duplex-Bench` | 英文数据、评测脚本和运行结果所在目录。 |
| Agent 代码 | `/opt/health-assistant/backend/livekit_agent` | 服务器上的健康助手 Agent。 |
| 隔离 Agent | `health-assistant-qwen-fdb-shadow` | 避免与 CCE 或同名 worker 发生负载分配。 |
| Agent 服务 | `health-agent-fdb-shadow-unique.service` | 当前唯一命名的 FDB Shadow worker。 |
| Token bridge | `http://127.0.0.1:8792/token` | 显式把 FDB 房间调度到隔离 Agent。 |
| LiveKit | `ws://127.0.0.1:7880` | 服务器内部连接，不依赖外部域名证书。 |
| 当前 MMI 模式 | `Shadow` | 只记录反事实控制决策，不执行真实动作。 |

## 3. 已完成工作

| 工作项 | 状态 | 中文说明 |
|---|---:|---|
| 英文 FDB 全量基线 | 完成 | 1225 个样本、1723 次实时推理，forced-align 1723/1723。 |
| V1.5 行为重评 | 完成 | 498 条使用统一 DeepSeek 裁判重新生成。 |
| FDB 与 Agent 日志关联 | 完成 | 使用 LiveKit room ID 精确关联，并输出 TXT、CSV、JSON。 |
| verdict 回流重判 | 完成 | 线程安全回调进入 runtime，并拒绝过期 room/turn/sequence。 |
| SpeakerGate 注册 | 完成 | 第二个一致候选可锁定当前分段并产生 target verdict。 |
| warmup 与强中断策略 | 完成 | 未锁定阶段严格等待；强命令仅在无明确非目标证据时放行。 |
| 英文 addressee | 完成 | 支持句尾称呼及逗号、句号等标点变体。 |
| thinking 阶段路由 | 完成 | SpeakerGate 参与时，新发言统一进入 interruption policy。 |
| 分析器门禁 | 完成 | 区分控制决策和 lifecycle，统计关联、覆盖率、误触发和处理时延。 |
| 自动化测试 | 完成 | 服务器相关测试 `183 passed`。 |

## 4. P7 最终结果

Run ID：`en_qwen_shadow_mmi_regression_p7_20260720_1105`

服务器目录：`/opt/Full-Duplex-Bench/runs/health_webrtc_en/en_qwen_shadow_mmi_regression_p7_20260720_1105/`

| 指标 | 结果 | 中文说明 |
|---|---:|---|
| 推理成功 | 12/12 | 四类场景各三条，全部完成。 |
| Forced-align | 24/24 | 用户和系统音频均完成强制对齐。 |
| Background | 3/3 | 背景声均未触发错误中断。 |
| Talking to other | 3/3 | 对他人说话均被正确抑制。 |
| User backchannel | 3/3 | 两条明确抑制，一条无重叠输出并安全保持 `NO_TARGET`。 |
| User interruption | 3/3 | 三条强用户中断均进入 `INTERRUPT`。 |
| 强中断召回率 | 100% | 无漏判。 |
| 非中断误触发率 | 0% | 无背景声、对他人说话或附和误中断。 |
| Agent 日志关联率 | 100% | 12 条均精确关联到 room 日志。 |
| required interruption 覆盖率 | 100% | 三条必须打断样本均有控制决策。 |
| Shadow 真实动作 | 0 | 符合 Shadow 不执行控制动作的要求。 |
| 回调决策时延 P95 | 1.466 ms | verdict 回流重判本身开销很低。 |

一条 backchannel 发生时没有 active/pending 输出，因此没有可控制目标。分析器保留原始 `NO_TARGET` 诊断，但按“日志关联成功且未执行错误动作”计为严格正确；这不是漏日志或漏判。

## 5. 主要代码改动

| 文件 | 中文说明 |
|---|---|
| `backend/livekit_agent/audio_filter.py` | SpeakerGate 注册、embedding 锁定和 target verdict。 |
| `backend/livekit_agent/mmi_turn_detection/runtime.py` | verdict 回流重判、过期保护、反事实上下文和时延日志。 |
| `backend/livekit_agent/mmi_turn_detection/interruption_policy.py` | warmup、强中断、目标身份和被点名场景策略。 |
| `backend/livekit_agent/mmi_turn_detection/detector.py` | thinking 阶段发言向 interruption policy 的受控路由。 |
| `backend/livekit_agent/mmi_turn_detection/patterns.py` | 英文称呼、句尾称呼和标点变体。 |
| `backend/livekit_agent/evaluation/analyze_fdb_mmi.py` | 精确关联、控制口径、重判统计和最终门禁。 |

## 6. 已生成产物

| 文件 | 中文说明 |
|---|---|
| `docs/FDB_MMI_SHADOW_REGRESSION_P7.txt` | 中文可读的 P7 门禁报告。 |
| `docs/FDB_MMI_SHADOW_REGRESSION_P7.csv` | 样本级决策结果，可用于 Excel 筛选。 |
| `docs/FDB_MMI_SHADOW_REGRESSION_P7.json` | 完整结构化结果，供脚本继续分析。 |

## 7. 下一步计划

| 顺序 | 工作 | 验收条件 |
|---:|---|---|
| 1 | 受控 Active p20 | 重复固定 manifest，直到每类至少有 3 条落入 Active 桶；Active 桶中非中断零误触发、强中断全成功，且回滚开关验证通过。 |
| 2 | Active p50 | p20 无回归后扩大到 50%，使用独立 run-id，其他变量保持不变。 |
| 3 | 扩大四类回归 | 每类至少 20 条，加入纯噪声、多人重叠、弱目标声和句尾不完整。 |
| 4 | 拆分约 5 秒端到端延迟 | 分别记录 ASR final、MMI、LLM 首 token 和 TTS 首音频时间。 |
| 5 | 定位 sample-62 静音 | 核对 Agent 文本、TTS 生成、音轨发布和 FDB 收音事件。 |
| 6 | 验证 Active backchannel 与恢复 | 确认附和不创建新轮次，强打断后输出和状态能正确恢复。 |

## 8. Active p20 约束

1. 只修改隔离 FDB worker，不改 CCE 或生产同名 Agent。
2. 配置使用 `mode=active`、`active_percentage=20`；未命中 Active 桶的 room 仍保持 Shadow。
3. 启动前记录当前 Shadow 配置，并准备一条命令恢复。
4. 先重复使用同一固定 manifest，直到四类场景各积累至少 3 条 Active 观测，禁止更换样本掩盖失败。
5. 同时检查 FDB 结果、MMI 控制日志和实际音频，不只依赖行为裁判。
6. 任一非中断场景出现真实误打断，立即回退 Shadow 并停止扩量。
