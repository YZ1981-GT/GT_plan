# G 投资循环底稿优化（workpaper-g-investment-cycle）

> **状态**: 三件套 v1.0 完成，待启动实施
> **创建日期**: 2026-05-19
> **唯一入口**: 请直接阅读 `requirements.md` v1.0（450+ 行，8 章 + 3 子章）

## 三件套文件

| 文件 | 版本 | 行数 | 内容 |
|------|------|------|------|
| `requirements.md` | v1.0 | 450+ | 依赖矩阵 + 业务痛点 9 类 + Sprint 0 基线 + 9 项关键发现 + 12 项功能需求（EARS 范式）+ 非功能需求 + 测试矩阵 + 成功判据 + 术语表 25 个 + UAT 17 项（P 列）+ 启动条件 |
| `design.md` | v1.0 | 300+ | 数据流图 + 6 ADR（G1~G6）+ ADR-G6 12 类正则 + 6 Correctness Properties + 12 错误处理 |
| `tasks.md` | v1.0 | 400+ | 46 task / 13 天 / Sprint 0~3 + Sprint 0.X 前置实测 / 17 UAT / 6 PBT / 6 TD |

## 关键数字

- G 循环：15 文件 / 197 raw sheets / 152 dedup / 4 历史遗留（已被现行 regex 覆盖）
- prefill 基线：16 entries / 74 cells → 目标 ≥ 80 新 cells
- cross_wp_ref 基线：8 条 → 目标 ≥ 25 新条目（起编运行时 max+1）
- UAT 门槛：≥ 14 ✓ pass + P0 7 项必过
- 启动条件：4/8 满足（待 review + Sprint 0.X 前置实测）

## G 循环核心特征（vs H/I 循环差异）

| 维度 | G 投资循环 | H 固定资产循环 | I 无形资产循环 |
|------|-----------|-------------|-------------|
| 文件数 | 15（最多） | 11 | 6 |
| Raw sheets | 197（最多） | 187 | 86 |
| 同 wp_code 多 sheet | **无** | 9 个位置 | 无 |
| 计量模式切换 | **无**（per-investment 核算方式）| project-level cost/fair_value | 无 |
| 历史遗留 | 4（"修订前"已覆盖）| 0 | 1 |
| 独有复杂度 | ECL 三阶段 + 公允价值 Level 1/2/3 + CAS 22 分类 | 折旧 4 方法 + 租赁两表 | 商誉 DCF + 资本化时点 |
| 前置底稿 | C5 | C6+C7+C14 | C8+C9 |

## 下一步

review 三件套 → Sprint 0.X 前置实测（tb_aux_balance G 类 aux_type/aux_code + G1-2 表头）→ Sprint 1 启动
