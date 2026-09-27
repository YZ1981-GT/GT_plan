# Task 0 前置依赖核查

日期：2026-09-27

## 1. 框架层前置

| 前置 | 状态 | 证据 |
|------|------|------|
| `TransposedSheetSpec` | ✅ 在 HEAD | `git cat-file -t HEAD:backend/app/services/workpaper_sync/phase5_transposed_sheet.py` = blob |
| `RowTableSheetSpec` | ✅ 在 HEAD | `git cat-file -t HEAD:backend/app/services/workpaper_sync/phase5_row_table_sheet.py` = blob |
| `oo_crash_neutralization_fn` | ✅ 在 HEAD | `git cat-file -t HEAD:backend/app/services/workpaper_sync/g7_oo_crash_if_neutralize.py` = blob |
| `StoreMergePlan` | ✅ 在 HEAD | 已被九条 single-region plan 消费 |

## 2. Foundation 前置

| 前置 | 状态 | 证据 |
|------|------|------|
| GC-1 pointer 规则 | ✅ Task 10 已交付 | `test_g_foundation_p20_golden_digest_baseline.py` 12 passed |
| GC-9 TB 裁决 | ✅ Task 8 已交付 | 三家 TB 缺口已书面裁决 |
| GC-2 中性化声明位 | ✅ Task 6 已交付 | 13 册 per-file 全挂 |
| Foundation 19/19 | ✅ | INDEX.md 记录 |

## 3. G4/G6 模板几何实测

### G4 债权投资.xlsx（19 sheets）

- `有价证券盘点表G4-7`：max_row=29 / max_col=7 / merged=3 / 表头 R13 起于 **B 列** / 无合计
- `明细表G4-2`：max_row=48 / max_col=44 / merged=23 / 两区 R12-17/R20-25 / 合计 R27
- `债权投资三阶段划分G4-9`：max_row=61 / **max_col=16384** ✅ 转置 / 实体列 11 有效

### G6 其他债权投资.xlsx（21 sheets）

- `明细表G6-2`：max_row=36 / max_col=33 / merged=18 / 多区
- `公允价值测试表G6-5`：max_row=40 / max_col=18 / merged=10 / R9-18 数据 / R19 合计
- `其他债权投资三阶段划分G6-11`：max_row=61 / **max_col=16384** ✅ 转置

## 4. 阻塞评估

- **前置 A/B/C/D 全部满足**
- G4-9 / G6-11 的 16384 列证实转置形态，`TransposedSheetSpec` 可用
- **可以推进 Task 1 起**
