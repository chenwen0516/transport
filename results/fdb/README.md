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
