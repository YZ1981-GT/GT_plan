# I 无形资产循环底稿优化（workpaper-i-intangible-assets-cycle）

> **状态**: 三件套 v1.0 完成，待启动实施
> **创建日期**: 2026-05-19
> **唯一入口**: 请直接阅读 `requirements.md` v1.0

## 三件套文件

| 文件 | 版本 | 内容 |
|------|------|------|
| `requirements.md` | v1.0 | 依赖矩阵 + 业务痛点 7 类 + Sprint 0 基线 + 10 项功能需求（EARS）+ 非功能需求 + 测试矩阵 + 术语表 + UAT 15 项（P 列）+ 启动条件 |
| `design.md` | v1.0 | 数据流图 + 5 ADR（I1~I5）+ ADR-I5b 10 类正则 + 5 CP + 错误处理 |
| `tasks.md` | v1.0 | 41 task / 8 天 / Sprint 0~3 + Sprint 0.X / 5 PBT / 15 UAT / 5 TD |

## 关键数字

- I 循环：6 文件 / 86 raw sheets / 67 dedup / 1 历史遗留（I3 商誉示例）
- prefill 基线：7 entries / 34 cells → 目标 ≥ 60 新 cells
- cross_wp_ref 基线：5 条 → 目标 ≥ 20 新条目（起编运行时 max+1）
- UAT 门槛：≥ 12 ✓ pass + P0 5 项必过（#1/#3/#9/#10/#11）
- 启动条件：4/9 满足（待 H spec 实施 + review + Sprint 0.X）

## I-cycle 独有特性（vs H 循环）

- **I-F5 资本化时点判断**：CAS 6 五条件 → 建议资本化起始日期（I-cycle 独有）
- **I3 商誉不摊销**：仅年度减值测试（DCF 资产组模型），减值先冲商誉再分摊
- **I6↔I2 双向回填**：研发费用（费用化）↔ 开发支出（资本化）同一活动两面
- **分支选择器语义不同**：I1-10/I1-11 各有独立 wp_code（不同于 H 的同 wp_code 多 sheet），仅提供"跳转到相关 sheet"入口

## 下一步

H spec 实施完成 → Sprint 0.X 前置实测（tb_aux_balance 170x/560x + I1-2 表头）→ Sprint 1 启动
