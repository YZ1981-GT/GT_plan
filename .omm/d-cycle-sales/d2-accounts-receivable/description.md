# D2 应收账款（1122）

componentType `d2-accounts-receivable` → `GtD2AccountsReceivable.vue`，后端 `_d2_accounts_receivable.py`。
**D 循环乃至全平台的范式标杆**：账龄枚举、ECL 三阶段、凭证检查卡片/矩阵双视图、保理终止确认向导、披露↔附注结构化联动都在这里先落地再推广。

## Sheet 组成（`d2/` 真实 Tab 组件）

| 分类 | Tab 组件 |
|---|---|
| 目录 / 程序 | `D2TabIndex` `D2TabProcedure` |
| 审定 / 明细 | `D2TabAdjudication`（D2-1）`D2TabDetail`（D2-2，32 列宽表 + ⚙列设置） |
| 调整 | `D2TabAdjustment` |
| 减值 | `D2TabBadDebt`（坏账准备）`D2TabEcl`（预期信用损失三阶段/迁徙率） |
| 检查 | `D2TabVoucherCheck`（凭证级，卡片/矩阵/在线编辑三视图）`D2TabCutoff`（截止）`D2TabWriteoffCheck`（核销）`D2TabRelatedParty` `D2TabPolicyCheck` `D2TabPledgeCheck`（质押 + 保理）`D2TabBizModel` `D2TabAnalysis` |
| 披露 | `D2TabDisclosure` + `D2DisclosureNoteBody`（上市/国企共享 body） |

专有交互组件：`D2DerecognitionWizard` / `D2DerecognitionOverview`（保理终止确认 9 步判断，逐份合同 + 卡片/矩阵复核视图）、`D2VcCardView` / `D2VcMatrixView` / `D2VcMethodologyPanel` / `D2VcAuditSummaryPanel`（凭证检查四件套）、`D2ReferenceBlock`（源模板方法论内嵌）。

## 联动

- **TB**：`useD2FormData` 读 `trial_balance` 中 `standard_account_code === '1122'` 的 `audited_amount ?? unadjusted_amount` 作核对锚点（本科目未见 writeback 调用，审定数以核对+差异告警呈现）
- **账龄**：`useAgingConfig(projectId,'D2')` 单一真源，明细存 nested `agingPrior/agingAudited`；跨表聚合走 `sumAgingBySegments`（nested 优先 + legacy 扁平回退，3 年段 `over3` 由 3-4/4-5/5年以上合成）
- **附注**：`五、5`（上市）/ `八、5`（国企），`buildD2SyncPayload` 推送账龄/分类/单项计提/**每组合一张分表**/变动/转回/核销/前五名 + 7 段说明文本
- **集中调整**：`useAdjustmentCentralSync`（itemId `D2-...`）→ `adjustments` 表 `origin='workpaper'`
- **抽凭 / 截止**：`GtVoucherSamplingEngine`（1122）+ `useCutoffAutoSampling`（`POST /sampling/cutoff-test`）
- **期后回款**：`importPostPaymentFromLedger` 从次年序时账 1122 贷方按客户名归集
- **函证**：D0 回函按 `companyCode` 精确优先 → 名称精确 → 双向包含兜底回写

## 已实现的复核视角设计

凭证检查表提供**卡片视图**（一笔一卡 + 5 项核对勾选 + 证据区 📎OCR）与**矩阵视图**（固定列 + 可折叠列组）双模，面向"编制"与"复核"两种使用姿态；保理终止确认提供逐份合同的 S1~S9 状态色块矩阵，复核人一屏看全。
