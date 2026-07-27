# D4 营业收入（6001 主营 / 6051 其他业务）

componentType `d4-operating-revenue` → `GtD4OperatingRevenue.vue`，后端 `_d4_operating_revenue.py`。
**D 循环体量最大的科目包**（`d4/` 下 7 个子目录、40+ 个 Tab 组件），也是**损益类**——取发生额不取余额。

## Sheet 组成（按 `d4/` 子目录）

| 子目录 | Tab 组件 |
|---|---|
| `core/` | `D4TabIndex` `D4TabProcedure` `D4TabAdjudication`（D4-1）`D4TabRevenueDetail`（D4-2 产品×月度）`D4TabAdjustment`（D4-4）`D4TabOtherRevenue`（其他业务收入）`D4TabDisclosureListed` / `D4TabDisclosureSoe` |
| `inspection/` | `D4TabOccurrence`（发生测试）`D4TabCutoffForward` / `D4TabCutoffBackward`（正反向截止）`D4TabContract`（合同检查 + 卡片/矩阵）`D4TabCompleteness`（完整性）`D4TabReturn`（销售退回）`D4TabDiscount`（折扣折让）`D4TabExport`（出口收入）`D4TabErpCheck`（ERP 系统核查，双模式标杆）+ `D4WalkthroughCard/Matrix`（穿行测试） |
| `analysis/` | `D4TabIndicator` `D4TabProductMargin` `D4TabMarginMonthly` `D4TabProductPrice` `D4TabCustomerPrice` `D4TabCustomerStructure` |
| `ipo/` | 13 个 IPO 专项（客户清单/明细、经销商、资金流水、访谈模板/明细/汇总、发票比对、第三方回款、境外收入、未披露关联方、IPO 指标/程序） |
| `policy/` `related/` `other/` | 政策检查、关联方定价、其他业务收入的检查/合同/截止/毛利 |

## 联动

- **TB**：render 输出 6001 / 6051 上下文；**`useD4FormData` 中未见 `trial-balance/writeback` 调用**（其余 D1/D3/D5/D6/D7 都有）→ 是否设计如此待核实（见 perspective 的 todo）
- **序时账取数**：后端 resolver `d4_ledger_monthly_by_product`（`tb_ledger` 6001 按 `account_name` × 月汇总贷方净额）→ D4-2「从序时账导入」
- **审定 → 明细 → 分析**：D4-2 产品×12 月是录入源，D4-1 审定表与各分析表从它派生
- **截止双向**：正向（记账→原始凭证）+ 反向（原始凭证→记账），跨期 → AJE + `a13:push-misstatement`
- **抽凭**：发生测试接 `GtVoucherSamplingEngine`（6001 / final）
- **下游**：D2 应收账款（收入↔应收勾稽）、F5 营业成本（毛利率勾稽）、D7 合同负债（结转收入）、D3 长期挂账（应确认收入）
- **双模式**：`D4TabErpCheck` 是「拉取成功才切 OnlyOffice」的参考实现（`checkOoHealth` + config 预拉 + `disabled:!ooHealthy`）

## 主入口的关键修复历史

`GtD4OperatingRevenue.vue` 必须监听 `d4:save-items` 与 `d4:writeback-trial-balance` 两个 window 事件——大部分子表经 window event 保存，主入口没监听时数据**静默不落库**。
