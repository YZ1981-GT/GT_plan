# D5 应收款项融资（1124）

componentType `d5-receivables-financing` → `GtD5ReceivablesFinancing.vue`，后端 `_d5_receivables_financing.py`。
资产借方，本质是"以公允价值计量且其变动计入其他综合收益的应收款项"，与 D1 应收票据存在**贴现/背书未终止确认**的勾稽关系。

## Sheet 组成（`d5/` 真实 Tab 组件，D 循环里最精简）

`D5TabIndex` `D5TabProcedure` `D5TabAdjudication`（D5-1）`D5TabDetail`（D5-2）`D5TabAdjustment`
`D5TabFairValue`（公允价值 / 贴现利率合理性）`D5TabDisclosure`（上市/国企双变体）

## 联动

- **TB 回写**：`useD5FormData` → `account_code: '1124'`
- **辅助余额导入**：`useD5Detail` 读 `GET /api/projects/{pid}/tb-aux-balance?account_code=1124`
- **期后实现**：从次年序时账 1124 贷方按对手方归集（`importPostRealizedFromLedger`）
- **公允价值 / 利率合理性**：贴现利率偏离阈值（约 200bp）预警；到期日预警（逾期 / 30 天内）
- **ECL 阶段**：`eclStage` + `suggestEclStage`
- **D1 勾稽**：D1-8「已贴现未终止确认」↔ D5 明细（`d1D5FinancingPull`，纯函数 + 跨底稿 pull）
- **函证**：D0 回函回写 `confirmAmount`
- **抽凭**：`GtVoucherSamplingEngine`（1124）
- **附注**：分类表 + 减值准备情况 + **期末已质押的应收票据** + **期末已背书或贴现但尚未到期的应收票据**（终止确认 / 未终止确认双列，CAS23 + 证监会 2014 监管报告）

## 披露内容红线

D5 附注上市版曾被自造成"金融资产风险敞口（最大敞口 / 前五名集中度）"——**那是臆测**。源模板真实结构就是上面列的四块，已纠正为 `D5-note-listed-pledged` / `D5-note-listed-endorsed`。审定表 D5-1 表格内**不含**"试算平衡表数 / 差异数"两行（与底部核对行冗余，`displayRows` 过滤掉，只保留底部核对）。
