# 上下文：F 循环特有机制

渲染链路、持久化、跨底稿事件、共享能力见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。
本文只写 F 特有部分。

## 1. F2 的科目模型是唯一真源

`composables/f2AccountModel.ts`：
- `F2_ROW_KEY_ACCOUNT`：审定表 rowKey → 科目编码（`raw-materials`→1401、`material-in-transit`→1402、`revolving-materials`→1403…）
- `F2_ACCOUNT_TO_ROW_KEY`：反向映射（1406 映射库存商品，进销差价用独立 1412 不与 1406 冲突）
- `F2_PRICE_DIFF_ACCOUNT = '1412'`（商品进销差价，**非跌价**）
- `F2_IMPAIRMENT_ACCOUNT = '1471'`（存货跌价准备）
- `F2_INVENTORY_ACCOUNTS`：调整分录可选科目（含 1412 / 1471 / 6401 / 6001）
- `sumImpairmentAjeByRowKey`：F2-14 的 AJE 汇总为跌价准备账项调整

四个 F2 入口共用它，改科目归属必须改这一处。

## 2. F2 审定表是「单列净额调整」而非 AJE/RJE 双列

F2 审定表的"账项调整"是**单列净额**，`updateCell` 签名是 `(block, rowKey, field, value)`（**4 参 block-scoped**），
且分**原值组（gross，1401~1411）与跌价组（impairment，1471）两个科目族**。

因此"从集中登记带入调整"在 F2 是**自包含双实例实现**（两个 pull + 两个 dialog + 自定义 apply，`net = aje + rje` 一次性累加单列），
**不能复用**通用的双列 helper（其快照累加会覆盖/丢单列原值）。

**注意**：审定表 adjustment 在 F2-14 有数据时会被 `crossSheet.grossAdjustmentByRowKey` /
`impairmentAdjustmentByRowKey` overlay 覆盖，手工值仅作 fallback → 带入只在 F2-14 空时可见。

## 3. F3-1 / F1-1 审定表的 TB 预填

- F1：`useF1FormData.writebackTrialBalance` 回写 1123
- F3：`useF3FormData.seedTrialBalance()` 把 `tbValues['2201']` 种子到 `F3-1-adj-tb-2201`，**仅无持久化时 seed，不覆盖手工录入**

## 4. 账龄：F1 已统一，F4 尚未

- **F1** 明细表用 nested keyed 账龄 + `useAgingConfig('F1')`，`agingAggregation` 是动态键 `Record<string,number>`
- **F4** 仍是自有 5 个固定 rowKey（`within1year` / `1to2year` / `2to3year` / `3yearplus` / `aging-other`）+ 明细表**扁平 4 字段**
  （`unadjustedAgingLt1/1to2/2to3/Gt3` + `auditedAging*`）。读写同源故无静默 0 缺陷，只是**口径未统一**；
  迁移需跨 6+ 文件改数据模型 → 已立 spec `f4-aging-enum-unification`，未实现

## 5. 大量凭证级检查表 + 引导弹窗

F 循环是"凭证检查表引导弹窗"范式的主要落地地：
`F2PurchaseVoucherDialog`（采购入库，5 分组卡片对齐 5 类单据 + 实时勾稽面板）、
`F2MaterialUsageVoucherDialog`（材料领用）、`F2SubcontractVoucherDialog`（委外加工）、
`F2CutoffVoucherDialog`（截止）、`F1/F3/F4VoucherCheckDialog`。
共同范式：分组卡片 + 📎OCR 只回填本组字段 + 实时勾稽提示 + 确认后回写，主表退化为只读卡片/矩阵视图。

## 6. F2 监盘的 AI 解析与问卷

`f2StocktakePlanAiParse.ts`（监盘计划 AI 解析）+ `f2StocktakeQuestionnaire.ts` + `F2StocktakeQuestionnaireDialog`，
以及 `F2RollTable`（倒轧表）。监盘是 F 循环里唯一带"计划—执行—抽盘—差异—倒轧—小结"完整闭环的子模块。
