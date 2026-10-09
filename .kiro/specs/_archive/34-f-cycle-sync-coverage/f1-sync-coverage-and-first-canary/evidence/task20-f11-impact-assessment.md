# Task 20 证据：F1-1 审定表影响评估

**日期**：2026-09-26

## 裁决 F1-H4 影响评估（先于 F1-1 受管）

### 模板口径 vs 前端口径

| 区块 | 模板（逐格实测） | 前端（useF1Adjudication + useF1CrossSheet） |
|---|---|---|
| 性质区 F 列（期末未审数） | `SUMIF(F1-2!D, A8, F1-2!O)` = Σ明细 O 按性质 | `natureAggregation` 取 `aggregateByNature(rows, 'endAudited')` = Σ明细 X（审定数）|
| 性质区 G/H 列（AJE/RJE） | `SUMIF(F1-2!D, A8, F1-2!V)` / `SUMIF(…,W)` = Σ明细 V/W | 逐格手填 per-cell 键 `F1-adj-nature-{rowKey}-aje` / `…-rje` |
| 账龄区 F17（期末未审） | `='明细表F1-2'!R35`（未审账龄合计） | 取 `agingAgg[rowKey]`（聚合 `agingAudited`）= 审定账龄 |
| 账龄区 I17（审定） | `='明细表F1-2'!Y35`（审定账龄合计） | 同上 |

### 对齐模板意味着什么

1. **性质区 F 列**从 Σ`endAudited`(X) 改为 Σ`endBalance`(O) —— 语义从"审定数聚合"变为"期末余额聚合"
2. **性质区 G/H 列**从手填 per-cell 改为 Σ明细 V/W —— 这是**业务口径变更**：手填 AJE 可能与明细 V 列不一致
3. **账龄区 F17**从审定账龄改为未审账龄 —— 语义变化

### 真库现状实测要点

- 真库 `F1-adj-nature-*-aje` / `…-rje` per-cell 键：需查是否有手填值（有则迁移方案）
- `adjustmentReconcile`（F1-1 vs F1-3 一致性校验）语义是否随之变化
- 真库 68 行 F1-2 明细当前 V=W=0 ⇒ 性质区 G/H 变化影响为零（但原理层改变）

### 结论

🔴 **F1-1 保持未受管**（裁决 F1-H4）：对齐模板改变 AJE 来源（手填→汇总明细），属**业务口径变更**，
须业务确认后实施。在此之前灰度开关 `_INCLUDE_F101 = False`。

F1-1 的 `AdjudicationSheetSpec` 声明已准备好（如下），灰度开关打开后即可接入，
但前端 `useF1Adjudication.buildRow` 取数逻辑的改变需要另行确认。

## AdjudicationSheetSpec 声明（灰度关）

已创建 `phase5_f1_01_adjudication.py`（仅声明、灰度关），包含：
- 性质区 `fixed_rows`（5 个 rowKey：goods/construction/equipment/service/other）
- 账龄区（行随账龄口径，仅 THREE_YEAR 启用）
- 逐格 cell_mask（93 个公式格位置）
- per-cell 键模板 `F1-adj-{section}-{rowKey}-{field}`
