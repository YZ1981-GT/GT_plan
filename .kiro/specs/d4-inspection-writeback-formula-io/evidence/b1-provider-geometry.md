# B1 provider 几何核定（D4-14/15/16）

> 参照已完成的 IPO provider `phase5_d4_ipo_checklist_sheets.py`（数据驱动 `_SHEETS` dict + mapping_digest 冻结 + rows_table_payload + build_store_projection/merge_projection_into_rows + instrumentation_spec，已装配 `phase5_d4_revenue_detail.py` 运行时）。
> 权威 workbook = `D/D4 收入底稿.xlsx`（含 D4-14/15/16，与 IPO 同一 blob）。json_path 工具（`json_path.py::resolve_json_path`/`set_json_path`）**支持嵌套 slash 路径**（`delivery/amount`）——D4-15/14 嵌套 store 的关键 enabler，与 IPO 扁平路径同机制。

## D4-15 完整性检查（三维嵌套，两级表头）— 适配度高

- 物理表头：row11 父组（A=序号, B:F=发货单, G:K=发票, L:P=记账凭证, Q=所载信息是否一致√(X)），row12 子列（日期/编号/品名/数量/金额）。merges: `A11:A12/B11:F11/G11:K11/L11:P11/Q11:Q12`。
- 数据区 13 起；footer `三、审计说明：` 在 **A26**。
- 前端 store `CompletenessItem`（item_id `D4-15-items`，行 id 前缀 `c-`）：`{id, indexNo, delivery{date,number,productName,quantity,amount}, invoice{...}, voucher{...}, isConsistent, remark}`。
- 字段列映射（json_path 嵌套）：
  - delivery: B=`delivery/date` C=`delivery/number` D=`delivery/productName` E=`delivery/quantity` F=`delivery/amount`
  - invoice: G-K = `invoice/*`（同上五字段）
  - voucher: L-P = `voucher/*`
  - Q=`isConsistent`（√/× 派生，**formula_mask**，由前端 checkConsistency 重算，projection 不覆盖）
  - **A=序号（seq，展示）/ remark 无物理列** —— 不进受管契约（序号是展示、remark 源模板无列）
- UUID 列 = R（数据止 Q）。row_identity = `id`。
- 结论：**可建 provider**，15 个受管字段（3×5 嵌套），Q 入 mask。

## D4-16 出口口岸核对（两级表头，差异派生）— 适配度高（有 1 处建模差异登记）

- 物理表头：row11（A=账面出口收入金额, B:F=电子口岸系统, G:K=免抵退税申报数据），row12 子列（B=期间/C=结关金额/D=差异/E=原因/F=索引 ; G=期间/H=申报外销收入/I=差异/J=原因/K=索引）。
- 数据区 13 起；**D13=0, I13=0**（差异派生列，源模板内嵌 0）；footer `三、审计说明：` 在 A16。
- 前端 store `ExportCheckRow`（item_id `D4-16-rows`，行 id 前缀 `r-`）：`{id, bookAmount, portsPeriod, portsAmount, portsDiff, portsReason, taxReportAmount, taxDiff, taxReason, taxIndex}`。
- 字段列映射：A=`bookAmount`, B=`portsPeriod`, C=`portsAmount`, D=`portsDiff`(**mask**), E=`portsReason`, H=`taxReportAmount`, I=`taxDiff`(**mask**), J=`taxReason`, K=`taxIndex`。
- 🔴 **建模差异登记（T1 已记）**：物理有两个「期间」（B电子口岸/G免抵退税）+ 两个「索引」（F/K），前端 `ExportCheckRow` 只建模单 `portsPeriod` + 单 `taxIndex`（口岸侧 G 期间、F 索引未建模）。provider 只映射前端已建模字段，未建模列（G 期间/F 口岸索引）不进受管契约（保持前端 store 单一真源，不自造字段）。
- UUID 列 = L（数据止 K）。row_identity = `id`。
- 结论：**可建 provider**，差异列 D/I 入 mask。

## D4-14 发生/穿行检查（七维嵌套，32 列，计算 footer）— 显著更复杂，单列评估

- 物理表头：row13 父组 + row14 子列，跨 A:AK。7 维嵌套（B:G 记账凭证 / H:I 合同 / J:M 出库 / N 仓库保管员 / O 发货审批人 / P:T 运输 / U:AA 签收 / AB:AF 发票 / AI 其他 / AJ 索引 / AK 是否异常）。
- 数据区 15 起；footer 是**计算块**：`合计`(A37) + `本期发生额`(A38) + `检查比例`(A39) + `四、审计说明：`(A40)。
- 前端 store `TransactionItem`（item_id `D4-14-transactions`，行 id 前缀 `t-`）：7 嵌套维度 + consistencyScore(派生) + isAnomalous。
- 🔴 **复杂度评估**：32 受管列（远超 IPO 最大 19 列）+ 计算型 footer 块（合计/本期发生额/检查比例，非单行 marker）+ 物理列与前端 store 维度非 1:1（仓库保管员/发货审批人是独立列，前端归入 delivery.warehouseKeeper/contract.approver）。这超出 IPO 范式的「一行 marker footer + 直列映射」，属更高风险形态。
- 结论：**本轮先做 D4-15/16（清晰适配），D4-14 因 32 列 + 计算 footer + 维度错位单列，待 D4-15/16 provider 跑通验收后再评估是否同批做**。

## D4-13 ERP 核对（纯文本表）— N/A

- 源模板两段文本（一、核对过程 / 二、核对结论），merges 仅抬头，无数据表结构。**不适配受管行表同步模型**，登记 N/A（保留裸 OnlyOffice 文本双模式）。
