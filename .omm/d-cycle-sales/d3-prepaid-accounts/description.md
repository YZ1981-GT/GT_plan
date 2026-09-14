# D3 预收账款（2203）

componentType `d3-prepaid-accounts` → `GtD3PrepaidAccounts.vue`，后端 `_d3_prepaid_accounts.py`。
**负债贷方**（期末 = 期初 + 贷 − 借），与 D7 合同负债并列但口径不同：D3 是旧准则/非合同性质的预收，D7 是 CAS14 合同负债。

## Sheet 组成（`d3/` 真实 Tab 组件）

`D3TabIndex` `D3TabProcedure` `D3TabAdjudication`（D3-1）`D3TabDetail`（D3-2）`D3TabAdjustment`
`D3TabAnalysis` `D3TabLongTerm`（长期挂账/处理结论）`D3TabRelatedParty` `D3TabVoucherCheck`（+ `D3VoucherCheckDialog` 逐笔核对引导弹窗）
`D3TabDisclosureListed` / `D3TabDisclosureSoe`（上市/国企**分离组件**）

## 联动

- **TB 回写**：`useD3FormData` → `PUT /api/projects/{pid}/trial-balance/writeback`，`account_code: '2203'`
- **账龄**：2-period 模型（期初/期末审定），`useAgingConfig(projectId,'D3')` 段驱动；审定表按账龄区块由 `crossSheet.agingByKey` + `agingSegments` 动态生成
- **长期挂账处理结论**：枚举（应确认收入 / 应退回 / 应转营业外收入 / 正常挂账 / 待确定）+ 跨底稿联动提示（→ D4 收入 / K12 营业外收入 / 其他应付款重分类）
- **凭证检查**：5 项核对内容对齐源模板（原始凭证齐全 / 账记相符 / 账务处理正确 / 会计期间正确 / 其他），逐笔引导弹窗 + 实时勾稽面板 + 📎OCR
- **截止**：`autoMarkCrossPeriod` 按资产负债表日标记期后结转凭证跨期疑点

## 术语

D3 的交易对手是**预收客户**（不是"债务人"），列头与说明已按此对齐源模板。
