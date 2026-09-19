# Requirements Document

## Introduction

审计平台当前存在**两套互不相通的调整分录系统**：

1. **集中式调整登记**（`adjustments` + `adjustment_entry` 表，`AdjustmentService`）：完整 CRUD、复核状态机（draft→pending_review→approved/rejected）、借贷平衡校验、自动编号、科目标准化校验，`ADJUSTMENT_CREATED/UPDATED/DELETED` 事件触发试算表重算（`trial_balance.aje_adjustment`）。`Adjustments.vue` 管理页 + `Adjustments` 导出基于此。

2. **底稿级调整分录**（各循环 `useXAdjustment` composable，存 `checklist_responses` 的 JSON，如 `D4-4-rows` / `K9-3-adj-entries`）：审计助理现场编制，通过 `X-1-aje-total` / `X-1-rje-total` 键回写本循环审定表（`X-1`），再经审定表 writeback 写 `trial_balance.audited_amount`；发 `adjustment:created` 仅作刷新信号（summary payload，无明细）。

**核心问题（2026-07-24 复盘）**：底稿级调整分录**从不进入集中式登记**。后果：

- 业务合伙人 / 质控在 `Adjustments.vue` 集中调整管理页**看不到**现场在底稿里编制的全部 AJE/RJE，无法跨循环审阅调整全貌。
- 集中式导出（调整分录汇总交付物）**遗漏**底稿来源的调整。
- 试算表存在**两条独立写回路径**（审定表 writeback 的 `audited_amount` vs 集中式 recalc 的 `aje_adjustment`），口径可能不一致、有重复计算风险。
- 底稿调整**无溯源**回集中登记，集中登记的复核结论**无回流**到底稿。

**已完成的相邻修复（不在本 spec 范围，仅作背景）**：`a13:push-misstatement` 死事件已接通——底稿"推送错报至A13错报汇总"按钮现经 `useA13MisstatementBridge` 写入 `unadjusted_misstatements` 表并携 `source_wp_code` 溯源。错报（未更正错报）与调整分录（AJE/RJE）是不同实体，本 spec 只处理**调整分录**的集中化与双向联动。

本 spec 目标：**在不破坏现有底稿→审定表→TB 既有链路（零回归）的前提下**，把底稿级调整分录**汇聚**到集中式登记（供审阅/导出/溯源），并建立集中登记复核结论**回流**到底稿的双向可见性，同时**明确并消除 TB 双写重复计算**风险。

## Glossary

| 术语 | 含义 |
|------|------|
| 底稿级调整 | 各循环 `useXAdjustment` 存于 `checklist_responses` 的 JSON 调整分录行（AJE/RJE） |
| 集中式登记 | `adjustments`/`adjustment_entry` 表 + `Adjustments.vue`，`AdjustmentService` 管理 |
| source_ref | 底稿调整在集中登记中的稳定溯源键：`{wp_id}:{item_id}`（幂等键） |
| origin | 集中登记条目的来源标记：`manual`（手工录入）/ `workpaper`（底稿汇聚） |
| 审定表 writeback | `X-1` 审定表把 `audited_amount` 写回 `trial_balance` 的既有链路 |
| recalc 路径 | 集中式 `ADJUSTMENT_*` 事件 → `trial_balance_service.recalc_adjustments` 写 `aje_adjustment` |
| 汇聚 | 底稿级调整 → 集中登记的单向推送（本 spec 主方向） |
| 回流 | 集中登记复核状态 → 底稿侧只读展示（次方向） |

## Requirements

### Requirement 1: 底稿调整汇聚到集中登记

**User Story:** 作为业务合伙人，我希望现场在底稿里编制的调整分录能出现在集中调整管理页，以便一屏审阅全部循环的 AJE/RJE。

#### Acceptance Criteria

1. WHEN 底稿调整分录 tab 保存（含至少一条借贷平衡的分录组）THEN 系统 SHALL 将该组分录汇聚为集中登记条目（`adjustments`/`adjustment_entry`），并标记 `origin='workpaper'` 与 `source_ref='{wp_id}:{item_id}'`。
2. WHEN 汇聚发生 THEN 集中登记条目 SHALL 保留原始借贷金额，且 `adjustment_type` 按底稿行 `category`（报表调整→rje / 账项调整·其他→aje）映射。
3. IF 底稿分录组借贷不平衡 THEN 系统 SHALL NOT 汇聚该组，并向用户返回明确的不平衡提示（不静默丢弃）。
4. WHERE 底稿分录行未提供标准科目编码 THE 系统 SHALL 按"科目名称→标准科目"解析映射；解析失败的行 SHALL 以可见告警列出待用户补全，不写入无效科目。

### Requirement 2: 汇聚幂等（重存不重复）

**User Story:** 作为审计助理，我反复保存底稿调整时不希望集中登记里产生重复条目。

#### Acceptance Criteria

1. WHEN 同一底稿分录组（同 `source_ref`）再次汇聚 THEN 系统 SHALL 更新既有集中条目而非新建重复。
2. WHEN 底稿删除某分录组后再汇聚 THEN 系统 SHALL 软删除对应集中条目（`source_ref` 不再出现于底稿则清理）。
3. WHERE 集中条目 `source_ref` 已存在且状态为 `approved` THE 系统 SHALL 拒绝静默覆盖，提示需先撤回复核（对齐既有状态机不可逆约束）。

### Requirement 3: 溯源与回流双向可见

**User Story:** 作为质控复核合伙人，我希望在集中登记看到每条调整来自哪张底稿并能跳转，同时底稿侧能看到该调整的集中复核状态。

#### Acceptance Criteria

1. WHEN 在 `Adjustments.vue` 查看某条 `origin='workpaper'` 条目 THEN 系统 SHALL 展示来源底稿编码（wp_code）并提供跳转到该底稿的入口。
2. WHEN 底稿调整 tab 展示某分录组 THEN 系统 SHALL 展示该组在集中登记的复核状态（draft/pending/approved/rejected），只读。
3. WHERE 集中条目被驳回（rejected）THE 底稿侧 SHALL 显示驳回标记与原因，供现场修正。

### Requirement 4: 试算表口径唯一（消除双写重复计算）

**User Story:** 作为项目负责人，我需要试算表的调整数只反映一次，避免底稿 writeback 与集中 recalc 双写导致重复。

#### Acceptance Criteria

1. WHEN 底稿调整既经审定表 writeback 写 `audited_amount`、又经汇聚进入集中登记 THEN 系统 SHALL 保证试算表**不重复计算**同一笔调整。
2. WHERE `origin='workpaper'` 的集中条目 THE 系统 SHALL NOT 通过 recalc 路径再次写 `trial_balance.aje_adjustment`（该调整已由审定表 writeback 体现），即 recalc 仅计入 `origin='manual'` 条目。
3. WHEN 仅在集中登记手工录入（`origin='manual'`）调整 THEN 系统 SHALL 维持既有 recalc 行为不变（零回归）。

### Requirement 5: 集中管理页来源筛选与导出

**User Story:** 作为业务合伙人，我希望能按来源（手工/底稿）筛选调整，并把全部调整导出为交付物。

#### Acceptance Criteria

1. WHEN 打开 `Adjustments.vue` THEN 系统 SHALL 支持按 `origin`（全部/手工/底稿）筛选调整列表。
2. WHEN 导出调整分录汇总 THEN 导出内容 SHALL 同时包含 `manual` 与 `workpaper` 来源条目，并含来源底稿列。

### Requirement 6: 零回归与增量可回退

**User Story:** 作为平台维护者，我要求本改动不破坏既有底稿→审定表→TB 链路与既有集中调整功能。

#### Acceptance Criteria

1. WHEN 汇聚特性未启用或汇聚失败 THEN 底稿→审定表→TB 既有链路 SHALL 完全不受影响。
2. WHEN 既有集中调整（手工）CRUD/复核/导出/recalc 执行 THEN 行为 SHALL 与改动前逐位一致（除新增 origin 筛选列）。
3. WHERE 汇聚逻辑逐循环接入 THE 每个循环的接入 SHALL 独立可回退，单循环失败不影响其他循环。

### Requirement 7: 正确性属性可测

**User Story:** 作为质量负责人，我要求关键不变量有属性测试守卫。

#### Acceptance Criteria

1. WHEN 执行测试套件 THEN 系统 SHALL 覆盖：幂等（同 source_ref 汇聚 N 次条目数不变）、借贷平衡守卫、类别→类型映射、TB 不双计（origin 过滤）、软删除清理等属性。
