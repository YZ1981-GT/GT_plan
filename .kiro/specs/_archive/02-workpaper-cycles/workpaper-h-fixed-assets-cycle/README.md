# H 固定资产循环底稿优化（workpaper-h-fixed-assets-cycle）

> **状态**: 三件套 v1.0 完成，待启动实施
> **创建日期**: 2026-05-19
> **唯一入口**: 请直接阅读 `requirements.md` v1.2（590+ 行，9 章 + 4 子章）

## 三件套文件

| 文件 | 版本 | 行数 | 内容 |
|------|------|------|------|
| `requirements.md` | v1.2 | 590+ | 依赖矩阵 + 业务痛点 10 类 + Sprint 0 基线 + 5 项关键发现 + 15 项功能需求（EARS 范式）+ 非功能需求 + 测试矩阵 + 成功判据 + 术语表 24 个 + UAT 19 项（P 列）+ 启动条件 |
| `design.md` | v1.0 | 350+ | 数据流图 + 6 ADR（H1~H6）+ ADR-H3b 14 类正则 + 7 Correctness Properties + 11 错误处理 |
| `tasks.md` | v1.0 | 500+ | 48 task / 14.5 天 / Sprint 0~3 + Sprint 0.X 前置实测 / 19 UAT / 7 PBT / 6 TD |

## 关键数字

- H 循环：11 文件 / 187 raw sheets / 159 dedup / 0 历史遗留
- prefill 基线：12 entries / 56 cells → 目标 ≥ 110 新 cells
- cross_wp_ref 基线：9 条 → 目标 ≥ 30 新条目（起编 CW-211）
- UAT 门槛：≥ 16 ✓ pass + P0 8 项必过
- 启动条件：7/8 满足（待 Sprint 0.X 前置实测）

## 命名澄清

用户最初提案"M 固定资产"，实测 `wp_account_mapping.json` 中 M=权益循环，固定资产在 **H 循环**（H0~H10）。无形资产在 I 循环（独立 spec）。

## 下一步

Sprint 0.X 前置实测（tb_aux_balance H 类 aux_type/aux_code + H1-2 表头）→ Sprint 1 启动
