# FDB/MMI 结果索引

这里存放机器生成的汇总产物。完整中文分析见
[FDB 与 MMI 最新工作总结](../../docs/fdb/FDB_MMI_WORK_SUMMARY_20260720_20260723.md)。

## Development

`development/` 是已用于设计和调参的数据，不可继续充当最终留出集。

| 文件 | 含义 |
|---|---|
| `FDB_MMI_REPLAY_LOGGED_BASELINE_V4_PER20_20260723.json` | v4 per20 历史 MMI 回放基线 |
| `FDB_MMI_REPLAY_LOGGED_BASELINE_P11_20260723.json` | P11 历史 MMI 回放基线 |
| `FDB_MMI_SEMANTIC_HYBRID_V3_2_PER20_20260723.json` | v3.2 在 per20 上的结果 |
| `FDB_MMI_SEMANTIC_HYBRID_V3_2_P11_20260723.json` | v3.2 在 P11 上的结果 |

## Holdout v1

`holdout-v1/` 是 v3.2 的一次性留出评估。v3.2 得到
TP/FN/FP/TN=`16/4/1/59`，未通过门禁；评估后该集合已解封为 v4 开发数据。

| 文件前缀 | 含义 |
|---|---|
| `FDB_MMI_HOLDOUT_V1_*` | 样本选择清单 |
| `FDB_MMI_HOLDOUT_REPLAY_EXPORT_*` | replay 导出完整性 |
| `FDB_MMI_HOLDOUT_LOGGED_BASELINE_*` | 同批历史 MMI 基线 |
| `FDB_MMI_HOLDOUT_SEMANTIC_HYBRID_V3_2_*` | 冻结 v3.2 结果 |

## Holdout v2

`holdout-v2/` 额外排除 holdout v1 和此前开发样本，是 v4 的一次性最终评估。

| 方法 | TP/FN/FP/TN | 严格正确率 |
|---|---|---:|
| 历史 Shadow 日志 | 18/2/0/60 | 97.50% |
| 语义单独决策 v3.2 | 17/3/3/57 | 92.50% |
| 分层纠错 overlay v4 | 20/0/0/60 | 100% |

对应文件：

- `FDB_MMI_HOLDOUT_V2_20260723.json`
- `FDB_MMI_HOLDOUT_V2_REPLAY_EXPORT_20260723.json`
- `FDB_MMI_HOLDOUT_V2_LOGGED_BASELINE_20260723.json`
- `FDB_MMI_HOLDOUT_V2_SEMANTIC_HYBRID_V3_2_20260723.json`
- `FDB_MMI_HOLDOUT_V2_SEMANTIC_OVERLAY_V4_20260723.json`

## Regression P7

`regression-p7/` 保留早期 12 条 Shadow 回归的 CSV、JSON 和可读文本报告。

## Online Shadow v1

`online-shadow-v1/` 保存 2026-07-23 正式在线 Shadow 的基础 MMI、远端语义延迟、
样本级决策对齐和 2026-07-27 v5 策略反事实结果。

| 文件 | 含义 |
|---|---|
| `FDB_MMI_ONLINE_SHADOW_V1_PER20_20260723.*` | 四场景各 20 条的基础 MMI 报告 |
| `SEMANTIC_OVERLAY_ONLINE_V1_PER20_20260723.json` | 243 次在线语义请求的成功率、丢弃率和延迟 |
| `SEMANTIC_OVERLAY_SAMPLE_ALIGNMENT_V1_PER20_20260723.json` | 修正字段后 345 条目标决策的逐样本对齐 |
| `SEMANTIC_OVERLAY_POLICY_V5_COUNTERFACTUAL_20260727.json` | v5 边界修复后的有状态反事实矩阵 |

结果摘要：基础 MMI 为 TP/FN/FP/TN=`20/0/4/56`；v5 反事实为
`20/0/1/59`。远端语义延迟 P50=`850.725 ms`、P95=`1062.657 ms`，
300 ms 内到达率为 0%，因此结果只支持继续 Shadow，不支持直接 Active。

## FastPath Shadow v1

`fast-path-shadow-v1/` 保存本地 200 ms FastPath 时间线验证。

| 文件 | 含义 |
|---|---|
| `FDB_FAST_PATH_SHADOW_V1_SMOKE_P1_R2_20260727.*` | 四场景各 1 条的基础 MMI 结果 |
| `FAST_PATH_SHADOW_V1_TIMING_P1_R2_20260727.json` | 四条会话的 pending、deadline、明确决策和 native stop 关联 |
| `FDB_FAST_PATH_SHADOW_V1_LATE_SIGNAL_P2_20260727.json` | backchannel/interruption 两条复验的基础结果 |
| `FAST_PATH_SHADOW_V1_LATE_SIGNAL_P2_20260727.json` | 第一条文本信号与 native stop 的先后关系 |

P1 控制矩阵为 `1/0/0/3`，但 200 ms 内明确决策率和 native stop 前明确决策率
均为 0%。P2 显示第一条文本信号只比 native stop 早约 0.5 ms，因此下一阶段需要
从音频/VAD 早期回调启动候选态。
