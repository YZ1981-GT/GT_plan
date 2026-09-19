# E1-1 审定表 + 四表取数

E1 的取数核心。审定表本身不直接查库，它消费**跨 sheet 聚合键**与**四表 prefill 种子**。

## 审定表结构（`E1TabAdjudication`）

行 = 货币资金分类（库存现金 / 银行存款 / 其他货币资金 / 数字货币等），
列 = 期初（未审 / 账项调整 / 审定）+ 期末（未审 / 账项调整 / 审定）+ 变动额 / 变动率 + 原因分析，
底部 = 试算平衡表数 / 差异数核对行。

## 三条取数路径

1. **四表 prefill（后端）**：`_build_four_table_prefill` 从 `tb_balance` 叶子科目提取 → `html_data.four_table_prefill`
2. **跨 sheet 聚合键（前端）**：E1-2/E1-3/E1-4 各 composable 持久化明细行时一并写聚合键
   （`E1-cash-detail-total-unaudited` / `E1-bank-detail-principal-total-unaudited` / `E1-digital-total-*` 等），审定表直接读
3. **TB 核对锚点**：`E1-adj-tb-amount-ending` / `-opening`，科目码来自 `report_config` BS-002 规则映射

## 审定数与回写

`审定 = 未审 + 账项调整`；`变动额 = 期末审定 − 期初审定`；`变动率 > 30%` 高亮 + 原因分析必填提示。
`writebackTrialBalance` 按归组一次回写三个科目：
1001（现金）/ 1002（银行本金）/ 1012（其他货币资金 + 数字货币）。

## 两个已修的坑（勿回退）

- **聚合键陈旧 0**：明细行有数据但聚合键是历史写入的 '0' → 审定合计漏项。现由 `reconcileCashAggregateFromRows()` 从持久化明细行权威重算，仅在"聚合陈旧 0/空而行合计非 0"时纠正（不覆盖明细 sheet 里的真实编辑）。
- **`E1-adj-total-{code}` 只在 writeback 时写**：而该函数常常没被调用 → 顶部告警与附注取数读到 0。现由 `syncAuditedTotals()` 随 `detailRows` immediate watch 同步到共享 `allResponses`（仅内存，不落库不发事件），writeback 时再落库。
