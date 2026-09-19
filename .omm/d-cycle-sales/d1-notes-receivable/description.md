# D1 应收票据（1121）

componentType `d1-notes-receivable` → `GtD1NotesReceivable.vue`，后端 `_d1_notes_receivable.py`。
资产借方，票据特有的"背书/贴现/质押/终止确认"是本科目区别于 D2 的核心。

## Sheet 组成（`d1/` 真实 Tab 组件）

| 分类 | Tab 组件 |
|---|---|
| 目录 / 程序 | `D1TabIndex` `D1TabProcedure` |
| 审定 / 明细 | `D1TabAdjudication`（Dx-1）`D1TabDetailCategory`（按类别）`D1TabDetailCustomer`（按客户/出票人） |
| 调整 | `D1TabAdjustment` |
| 减值 | `D1TabBadDebt` `D1TabEclCalc` |
| 票据专有 | `D1TabEndorsementDetail`（背书/贴现）`D1TabPledgeCheck`（质押）`D1TabInterestCheck`（带息票据利息）`D1TabInventoryCount`（票据实物盘点）`D1TabMemoReconciliation`（备查簿核对） |
| 检查 | `D1TabWriteoffCheck`（核销）`D1TabRelatedPartyCheck`（关联方）`D1TabPolicyCheck`（政策）`D1TabSamplingVouching`（抽凭）`D1TabBusinessMode`（业务模式） |
| 披露 | `D1TabDisclosure`（上市/国企双变体同组件） |

辅助组件：`D1AuditNoteSection` `D1MemoNoteCard` `D1BusinessModeCard/Matrix` `D1PreparationHandbookDialog`（编制/使用手册）。

## 联动

- **TB 回写**：`useD1FormData.writebackTB(accountCode, auditedAmount)` — 科目码**参数化**（1121 及其相关备抵）
- **审定表预填**：render 输出 `project_context.tb_amount`（1121 审定优先，回退未审）作 TB 核对锚点，不做分类行 per-row 预填
- **附注**：`五、4`（上市）/ `八、4`（国企），`d1NoteSectionMap.buildD1SyncPayload` 推送**上市 14 张 / 国企 12 张**子表 + `_note_texts` 说明；正反向跳转均已登记
- **函证**：D0 回函经 `confirmation:received` 回写明细行 `isConfirmed`
- **D5 勾稽**：D1-8 已贴现未终止确认 ↔ D5 应收款项融资（`d1D5FinancingPull`）
- **抽凭**：`D1TabSamplingVouching` 接 `GtVoucherSamplingEngine`（account-code=1121 / phase=final）
- **期后兑付**：明细表可从次年序时账 1121 贷方按客户归集（`importPostSettlementFromLedger`）

## 账龄

国企组合计提分表的"名称"列已枚举化为 `useAgingConfig` 生效段（保留 allow-create 供出票人类型自定义），并提供"按账龄段生成行"只补缺失段。
