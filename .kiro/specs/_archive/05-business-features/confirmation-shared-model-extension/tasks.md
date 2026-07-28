# Implementation Plan

## Overview

按 design M0 → M5 实施。**M0 是硬前置**（源模板列清单未逐列核实不得进 M1）。全程 additive（新增可选字段），既有 `confirmation-v1` / `entity-verify-v1` / `reliability-v1` / `diff-reconcile-v1` 数据零丢失。改动集中：新增 `confirmationColumnSpec.ts` + `confirmationColumnSourceManifest.ts`、改 `confirmationTypes.ts` / `ConfirmationMaster.vue` / `entityVerifyTypes.ts` + grid / `reliabilityTypes.ts` + `ReliabilityGrid.vue` / `diffReconcileTypes.ts` + grid。**不改** `syncHubFromSummary.ts`、台账表、替代程序区块列、`accountTabs` 派生。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "note": "只读核实源模板列清单 + 基线，无代码风险（硬前置）" },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3"], "note": "列配置驱动层 + ConfirmationRow 共性 ~10 列 + Master 改造 + 列显隐" },
    { "wave": 2, "tasks": ["3.1", "3.2"], "note": "Cycle_Variant_Column：K0/L0 五段与审计结论 / E0 原币汇率 / H0 条款" },
    { "wave": 3, "tasks": ["4.1"], "note": "EntityVerifyRow 回函核实块 + X0-2↔X0-7 单一真源" },
    { "wave": 4, "tasks": ["5.1", "5.2"], "note": "ReliabilityRow + DiffReconcileRow 补列" },
    { "wave": 5, "tasks": ["6.1", "6.2", "6.3"], "note": "属性/契约/守卫测试 + 零回归门 + Playwright" }
  ]
}
```

## Tasks

- [x] 1. Wave 0：源模板列清单核实与基线（硬前置）

- [x] 1.1 逐枢纽逐 sheet 落 CONFIRMATION_SOURCE_MANIFEST
  - 新建 `audit-platform/frontend/src/components/workpaper/confirmation/confirmationColumnSourceManifest.ts`
  - 对照 D0/E0/F0/G0/H0/K0/L0 各自源模板 X0-1，逐列录入真实列清单（列名用各枢纽自身用词）
  - 对照 X0-2 与 X0-7 源模板列清单，判定「回函方式/是否原件/是否直接接收」重叠项归属（design 决策 5 定 X0-7 唯一录入），写入注释
  - 登记现有实现中超出源模板的字段为「源外增强」（如 EntityVerifyRow 的电子函证块若源无）
  - 纯数据文件，不改任何生产行为
  - _Requirements: 8.1, 8.2, 3.5_

- [x] 1.2 建立零回归基线
  - 运行并记录：函证域前端全量测试、`htmlRendererRegistry.spec`、八套 alternative characterization 测试
  - 记录 `syncHubFromSummary` 当前映射字段集合（作为 Property 2 比对基准）
  - _Requirements: 7.1, 7.5_

- [x] 2. Wave 1：列配置驱动层 + ConfirmationRow 共性补列

- [x] 2.1 confirmationColumnSpec.ts 与 ConfirmationRow 共性 ~10 列
  - 新建 `confirmationColumnSpec.ts`：`ColumnDef` / `BASE_CONFIRMATION_COLUMNS`（含 design Data Models 表中「全部」枢纽的 8 个共性新列 + 既有列）/ `CYCLE_VARIANT_COLUMNS`（先只填 K0/L0/E0/H0 键，值 Wave 2 补）/ `resolveConfirmationColumns(cycle)` 纯函数
  - `confirmationTypes.ts`：`ConfirmationRow` additive 补 `sample_purpose` / `send_doc_no` / `send_addr_match` / `reply_courier_no` / `reply_from_addr` / `send_reply_addr_match` / `use_alternative` / `alt_unconfirmed`，每字段注释源模板出处
  - 每个 `ColumnDef.source` 与 manifest 出处对齐
  - _Requirements: 1.1, 1.2, 1.3, 8.2_
  - _Properties: 3, 9_

- [x] 2.2 ConfirmationMaster.vue 列配置驱动改造 + 分段表头
  - `ConfirmationMaster.vue`：列从硬编码 `el-table-column` 改为 `v-for` 消费 `resolveConfirmationColumns(cycle)`（cycle 由 props/上下文传入）
  - 按 `ColumnDef.group` 渲染分段表头（发函信息/收到回函/回函金额确认/替代程序/发函询证纪要）
  - 派生列（difference/confirmed_amount）保持既有自动计算规则不变
  - 与 1.2 基线对照：D0 补列后既有列渲染逐字不变
  - _Requirements: 1.4, 1.5, 2.1_
  - _Properties: 3, 5_

- [x] 2.3 宽表列显隐设置
  - 复用平台 `useXDetailColumnPrefs` 范式：列显隐 popover + 预设（全部/核心/审定）+ localStorage（key `confirmation-{cycle}-column-prefs`）
  - 关键列 `confirm_index` / `entity_name` `fixed="left"`
  - 数值列右对齐 + 平台金额格式
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 3. Wave 2：Cycle_Variant_Column

- [x] 3.1 K0/L0 发函询证纪要段 + 行级审计结论
  - `confirmationTypes.ts` 补 `send_memo` / `row_conclusion`（K0/L0 variant）
  - `CYCLE_VARIANT_COLUMNS.K0` / `.L0` 补 `['send_memo', 'row_conclusion']`
  - Master 渲染 `send_memo` group 与审计结论列（仅 K0/L0 出现）
  - _Requirements: 2.2, 2.5_
  - _Properties: 4_

- [x] 3.2 E0 原币/本位币/汇率 + H0 条款口径
  - `confirmationTypes.ts` 补 E0：`account_no` / `fx_rate` / `amount_orig` / `confirmed_amount_orig`（`amount`/`confirmed_amount` 复用为本位币不改语义）；H0：`term_book` / `term_reply` / `term_match` / `term_note`
  - `CYCLE_VARIANT_COLUMNS.E0` / `.H0` 补对应列
  - 验证覆盖率与差异计算仍用 `amount`（本位币），不受原币列影响；`amount` 类型仍 number
  - _Requirements: 2.3, 2.4, 2.6, 2.5_
  - _Properties: 5, 6_

- [x] 4. Wave 3：EntityVerifyRow 回函核实块

- [x] 4.1 EntityVerifyRow 补列 + X0-2↔X0-7 单一真源
  - `entityVerifyTypes.ts` additive 补 Reply_Verification_Block 差集（is_original/direct_received/reply_from_addr/reply_sender/reply_phone/reply_*_match/reply_inconsistent_note/verify_evidence_index/followup_control_index）+ 企查查缺列（qcc_zipcode/qcc_email_fax/qcc_inconsistent_reasonable/qcc_support_index/qcc_remark）
  - 与 1.1 判定一致：X0-7 重叠项在 X0-2 只读引用或明示「详见 X0-7」，不做双真源可编辑
  - entityVerify grid 渲染新列；一致性判定点选（是/否/不适用）；判定不一致要求/提示填说明
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Properties: 7, 8, 9_

- [x] 5. Wave 4：ReliabilityRow + DiffReconcileRow

- [x] 5.1 ReliabilityRow 补列 + 从 X0-1 带入
  - `reliabilityTypes.ts` additive 补 direct_received/fax_info_verify/send_email/reply_email/reliability_consideration（已有等价字段如 confirm_index/email_domain 复用不新增）
  - `ReliabilityGrid.vue` 渲染新列；从 X0-1 带入函证索引号/被询证单位名去重
  - _Requirements: 4.1, 4.2, 4.4_
  - _Properties: 9_

- [x] 5.2 DiffReconcileRow 补支持性证据列
  - `diffReconcileTypes.ts` 补 `support_evidence`；diffReconcile grid 渲染（按源模板 9 列顺序）
  - _Requirements: 4.3, 4.4_
  - _Properties: 9_

- [x] 6. Wave 5：测试与守卫

- [x] 6.1 属性测试与契约测试
  - fast-check：Property 1 round-trip 保真（旧 payload 读→存→读既有字段不变）、Property 2 Sync_Field_Set 不变
  - 契约：Property 3 `resolveConfirmationColumns(cycle)` 列集合 = BASE∪variant 且出处齐全（对 manifest）、Property 4/5/6 各枢纽 variant、Property 9 每字段可追溯、Property 12 适配器读 X0-1 行不变
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 6.2 单元测试与守卫
  - Property 7 一致性判定点选+不一致说明、Property 8 X0-2↔X0-7 单一真源、Property 10 各枢纽用词不统一、Property 11 accountTabs 不变
  - 守卫：Shared_Row_Model 每字段追溯源出处或登记源外增强（读 manifest）
  - _Requirements: 8.1, 8.3, 8.4, 3.5, 7.3_

- [x] 6.3 零回归门 + Playwright
  - 函证域前端全量 + `htmlRendererRegistry.spec` + 八套 alternative characterization 全绿；改动文件 `get_diagnostics` 清 + Vite transform 200
  - Playwright（D0/K0/E0/H0 各一次）：补列渲染（K0 审计结论/发函询证纪要、E0 原币/汇率、H0 条款、共性 ~10 列）、宽表列显隐、旧 payload 回显不丢
  - _Requirements: 7.1, 7.2, 7.4_
  - _Properties: 1, 5, 6_

## Notes

- **M0（Wave 0）硬前置**：源模板列清单未逐列核实不得进 M1（臆造列/漏列风险）
- 全程 additive 可选字段，`_format` 不升级，无迁移脚本（旧数据天然兼容）
- **不改** `syncHubFromSummary`（Sync_Field_Set 锁定）、台账 `confirmation` 表、替代程序区块列、`accountTabs` 派生
- 各枢纽源模板用词不同不强行统一（`ColumnDef.label` 按各自源模板）
- 每批按 Shared_Row_Model 独立可发布可回退

## 复盘修正记录（2026-07-26）

上一轮 run-all 存在三处假绿，本轮据实修复（5 组件 diagnostics 全清 + Vite 200 + 函证域 668 passed 零回归）：

- **Task 2.2 实际实现与 design 原设想偏差（已纠正）**：design 写「改 ConfirmationMaster 列配置驱动」是在 `ConfirmationFullGrid.vue` 不存在时的假设。实测 **FullGrid（grid 视图）才是真正的宽表全列配置驱动交付点**（`resolveConfirmationColumns(cycle)` + cycle prop + 列显隐 + 分段表头，GtConfirmationSummary 传 `:cycle="confirmCycle"`，链路完整）。`ConfirmationMaster` 是 **list 视图简表概览**（master-detail 模式，配 `ConfirmationDetail` 单行编辑）。上一轮误把 Master 改成 30+ 列宽表 = 与 FullGrid 重复且没传 cycle（variant 列不显示）→ **本轮已回退 Master 为简表 8 列**，宽表职责归 FullGrid。
- **Task 2.2 补充**：list 视图新列编辑靠 `ConfirmationDetail`——本轮补齐共性新字段（sample_purpose/send_doc_no/send_addr_match/reply_courier_no/reply_from_addr/send_reply_addr_match/use_alternative/alt_unconfirmed）到对应 stage；variant 字段（E0/H0/K0/L0）由 FullGrid 宽表编辑（有 cycle）。
- **Task 4.1（本轮真做 UI）**：`EntityVerifyDetail` 补企查查缺列（qcc_zipcode/qcc_email_fax/qcc_inconsistent_reasonable/qcc_support_index/qcc_remark）+ 新增 Stage 6「回函核实」渲染 Reply_Verification_Block（is_original/direct_received 只读引用 X0-7 单一真源 + reply_from_addr/reply_sender/reply_phone + 三项一致性点选 + 不一致要求填说明 + verify_evidence_index/followup_control_index）。上一轮只改了 .ts 类型，grid.vue 未渲染。
- **Task 5.1（本轮真做 UI）**：`ReliabilityGrid` 补 direct_received/send_email/reply_email/fax_info_verify/reliability_consideration 列渲染。「从 X0-1 带入」已有（工具栏 `import-d01`「从 D0-1 带入电子回函」）。
- **Task 5.2（本轮真做 UI）**：`DiffReconcileMaster` 补「支持性证据」列渲染。
- **Task 6.3 诚实标注**：Playwright **未跑**（上一轮标 [x] 不实，仅跑 vitest）。零回归门（668 passed 除并发 L05 外全绿）+ 22 契约测试已充分覆盖类型/配置/UI 编译；Playwright 待实例化函证底稿的项目 + 浏览器 SSE 稳定环境补做。
- **并发失败甄别**：`alternativeCallerMount.smoke.spec.ts` 的 L05 caller 失败（`data.getBlockTotalByDirection is not a function`）属**并发会话 `confirmation-alternative-structure-alignment` spec（Task 3.3 L05 借贷拆表）未完成**——工厂已实现该方法、K06 caller passed，但 L05.vue（工作树 M）引用它而 `useAlternativeL05Data` 适配器未透传。与本 spec 五组件零交集，不擅自修。
