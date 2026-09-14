# D7 合同负债（2205）

componentType `d7-contract-liabilities` → `GtD7ContractLiabilities.vue`，后端 `_d7_contract_liabilities.py`。
CAS14 收入准则下的合同负债，**负债贷方**（期末 = 期初 + 贷 − 借；贷方增加 = 预收，借方减少 = 结转收入）。

## Sheet 组成（`d7/` 真实 Tab 组件）

`D7TabIndex` `D7TabProcedure` `D7TabAdjudication`（D7-1，性质维度 + 账龄维度）`D7TabDetail`（D7-2）
`D7TabAdjustment` `D7TabAnalysis` `D7TabLongTerm`（长期挂账 + 处理结论）`D7TabRelatedParty`
`D7TabVoucherCheck` `D7TabDisclosure`

## 联动

- **TB 回写**：`useD7FormData` → `account_code: '2205'`（用 `http.put`）
- **账龄**：nested keyed `agingPrior/agingAudited` + `useAgingConfig('D7')`（**2-period**，与 D3 同族，不含期初账龄的三期结构）；`migrateD7FlatToNested` 迁移历史扁平字段；审定表按 `agingSegs.map` 段驱动生成行
- **D4 收入勾稽**：`useD7D4Reconcile`——D7 借方减少（结转）↔ D4 收入审定数，1% 容差 + 差异告警
- **处理结论**：`D7_DISPOSAL_CONCLUSIONS`（应确认收入 → D4 / 应转营业外收入 → K12 / 应退回 → 其他应付款 / 正常挂账 / 待确定），带 `GtIndexChip` 跨底稿跳转
- **序时账导入**：D7-4 走 `d7_ledger_analysis` resolver（`debit_by_counter` / `credit_by_counter` 按对手方归集）
- **抽凭**：`GtVoucherSamplingEngine`（2205 / final）
- **截止**：`useCutoffAutoSampling`（序时账 ±5 天窗口）
- **附注**：`五、39`（上市）/ `八、39`（国企），emit 载荷带 `accountCode: '2205'` + `sectionIds`

## 与 D3 的区分

D3 预收账款是非合同性质的预收（旧准则残留 / 押金类），D7 是 CAS14 合同负债。两者审定表结构相似（性质 + 账龄双维度、长期挂账处理结论），但科目、附注章节、准则依据都不同，**不要相互套用列结构**。
