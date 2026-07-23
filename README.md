# Transport 研究与评测资料

本仓库用于归档语音助手、全双工打断、轮次检测和音频基准测试资料。
根目录只保留导航文件，正文、结果和附件按用途分类。

## 从这里开始

- [FDB 与 MMI 最新工作总结](docs/fdb/FDB_MMI_WORK_SUMMARY_20260720_20260723.md)
- [Full-Duplex-Bench 运行交接](docs/fdb/FDB_HANDOFF.md)
- [FDB 英文全量基线分析](docs/fdb/FDB_BASELINE_ANALYSIS.txt)
- [FDB 结果索引](results/fdb/README.md)
- [语音打断测试方案](docs/test-plans/interruption_test_plan.html)
- [轮次检测测试方案](docs/test-plans/turn_detection_test_plan.html)

当前最新离线结论：分层纠错
`2026-07-23.semantic-overlay-v4-frozen` 在隔离 holdout v2 上达到
TP/FN/FP/TN=`20/0/0/60`。该结果允许进入在线 Shadow 集成，
不代表可以直接切换 Active。

## 目录

| 目录 | 内容 |
|---|---|
| `docs/fdb/` | FDB 交接、基线分析、阶段总结 |
| `docs/test-plans/` | 可直接在浏览器打开的测试方案 |
| `docs/research/` | 轮次检测与打断调研文档 |
| `docs/reports/` | 阶段汇报文档 |
| `results/fdb/` | FDB/MMI 原始汇总 JSON、CSV 和文本报告 |
| `results/audio-benchmarks/` | 其他音频基准输出和 badcase |
| `presentations/` | 可维护的演示文稿 |
| `spreadsheets/` | 基准测试表格和工作表 |
| `scripts/` | 历史评测脚本 |
| `archive/` | 旧日志、脱敏配置快照、临时笔记和压缩包 |

## 维护约定

1. 新的阶段结论写入 `docs/`，机器生成结果写入 `results/`。
2. FDB 结果按 `development`、`holdout-v1`、`holdout-v2`、`regression-*`
   分目录，避免继续把带日期的 JSON 堆在根目录。
3. 旧日志和一次性附件进入 `archive/`，不得作为当前配置或发布依据。
4. Token、密码、API Key、LiveKit Secret 和未脱敏 ConfigMap 不得提交。
5. 当前树已删除明文 JWT，并对已发现的配置凭据做脱敏；由于凭据曾进入
   Git 历史，相关密钥仍应轮换。若需要彻底清理历史，应另行执行受控的
   history rewrite，并通知所有协作者重新拉取。
