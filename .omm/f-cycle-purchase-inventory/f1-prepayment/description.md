# F1 预付账款（1123）

componentType `f1-prepayment` → `GtF1Prepayment.vue`，后端 `_f1_prepayment.py`。资产借方。

## Sheet 组成（`f1/` 真实 Tab 组件）

`F1TabProcedure`（F1A 程序表）`F1TabAdjudication`（F1-1）`F1TabDetail`（F1-2）`F1TabAdjustment`（F1-3）
`F1TabAnalysis`（分析）`F1TabLongTerm`（长期未结转）`F1TabRelatedParty`（关联方）
`F1TabComprehensiveCheck`（综合检查）`F1TabConfirmationProcedure`（函证程序）
`F1TabDisclosureListed` / `F1TabDisclosureSoe`（上市/国企分离组件）

辅助：`F1CreditCheckTable`（征信核对）、`F1VoucherCheckDialog`（凭证引导弹窗）、`F1SheetAttachments`（附件）、
`F1PreparationHandbookDialog`（编制/使用手册）。

**F1 特有**：每个 sheet 配一个 `F1*UsageGuide.vue`（Adjudication / Adjustment / Analysis / ComprehensiveCheck /
Confirmation / Detail / Disclosure / LongTerm / Procedure / RelatedParty 共 10 个）—— 逐 sheet 使用指引组件化，
这是 F1 独有的做法（其他科目走统一的编制提示 details + 手册弹窗）。

## 联动

- **TB 回写**：`useF1FormData.writebackTrialBalance(auditedAmount)` → `account_code: '1123'`
- **审定表预填**：render 输出 `project_context.prepaid_tb_amount`（1123 审定优先回退未审）；
  **F1 的 `allResponses` 来自 `/checklist-responses` 端点而非 render 的 `responses_snapshot`** →
  注入 snapshot 无效，必须经 `project_context` prop + composable 的 `tbAmountSeed`（只读回退，持久化优先）
- **账龄**：nested keyed + `useAgingConfig('F1')`，`agingAggregation` 动态键；账龄下拉一律绑生效段
- **跨循环取数**：`F1TabAnalysis` 的「从试算表带入余额」拉 1401 存货 / 2202 应付期末（后端 `_fetch_f1_tb_context`，应付取 abs 正数），仅空锚点填入不覆盖
- **关联方完整性**：`computeMissingRelatedParties` + `relatedPartyNameMatches`（双向模糊）+ 漏列告警 + 一键补充
- **调整联动**：F1-1 消费 `crossSheet.adjustmentTotals`（纯 computed，**不用事件累加器**，避免多计）+ `adjustmentReconcile` 勾稽告警
- **A13**：`a13:push-misstatement`（事件名统一，早期用 `misstatement:push` 是错的）
- **附注**：`五、7`（上市）/ `八、7`（国企），`buildF1SyncPayload` 按 variant 推送 + columns

## 账龄的正确姿势（F1 是范例）

`agingAggregation` 返回 `Record<segKey, number>` 动态键，模板按 `bands` 渲染；
超 1 年判定按 `dayFrom >= 366`（不能按 `key !== 'within1'`，自定义段会误判）。
