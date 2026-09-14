# D 销售与收款循环

D 循环覆盖销售与收款相关的 8 个科目底稿包，是平台实质性程序中**联动最密集、范式最成熟**的循环，其他循环（E/F/G/H/I/J/K/L/M/N）的审定表—明细表—调整—披露四段式结构基本都以 D 循环为参照。

## 组成

| 元素 | 科目 | componentType（前端注册） | 后端 render 策略 |
|------|------|--------------------------|------------------|
| D0 函证枢纽 | — | `confirmation-*`（9 类） | `_confirmation_*` |
| D1 应收票据 | 1121 | `d1-notes-receivable` | `_d1_notes_receivable.py` |
| D2 应收账款 | 1122 | `d2-accounts-receivable` | `_d2_accounts_receivable.py` |
| D3 预收账款 | 2203 | `d3-prepaid-accounts` | `_d3_prepaid_accounts.py` |
| D4 营业收入 | 6001 / 6051 | `d4-operating-revenue` | `_d4_operating_revenue.py` |
| D5 应收款项融资 | 1124 | `d5-receivables-financing` | `_d5_receivables_financing.py` |
| D6 合同资产 | 1402 | `d6-contract-assets` | `_d6_contract_assets.py` |
| D7 合同负债 | 2205 | `d7-contract-liabilities` | `_d7_contract_liabilities.py` |

每个科目是一个**整册专属组件**：一个 `wp_id` 下挂十几到二十几个 sheet，主入口 `GtDxXxx.vue` 按 `sheetName` 用 `v-if` 分发到 `dX/core|inspection|...` 下的 Tab 组件，共享一份 `useDxFormData` 持久化实例。

## 四段式骨架（每个科目都有）

1. **程序表 DxA** — `a-program-console`，审计程序清单，步骤可自动取数（`auto_data_source`）
2. **审定表 Dx-1** — 未审数 + AJE + RJE = 审定数，回写 `trial_balance`
3. **明细表 Dx-2** — 逐笔/逐客户明细，账龄分段，向审定表提供 SUMIF 聚合
4. **调整分录 Dx-3/4** — AJE/RJE 借贷平衡，回写审定表 + 推送集中登记 + 推 A13 错报
5. **附注披露（上市/国企）** — 结构化推送到附注模块对应章节

外加各科目专有的检查表：凭证检查、截止测试、ECL/坏账测算、函证、政策检查、关联方、质押/核销等。

## 数据流主脉

四表库（`tb_balance` / `tb_ledger` / `tb_aux_balance` / `trial_balance`）
→ 后端 render 策略预填 → `checklist_responses`（JSON 存储）
→ 明细表录入/取数 → 审定表聚合 → `trial_balance.audited_amount` 回写
→ 报表取数 + 附注结构化推送

## 关键事实

- **存储不是网格**：D 循环全部走 `checklist_responses`（`item_id` + `remark` JSON），不是 Excel cell 网格；因此四表取数是"render 预填 seed"而非"公式求值"。
- **账龄单一真源**：`useAgingConfig`（项目级 3 年段 / 5 年段 / 自定义），明细表存 nested keyed `agingPrior/agingAudited`，禁止各 tab 自建段清单。
- **函证跨循环共享**：D0 的 9 个 `confirmation-*` 组件被 E0/F0/G0/H0/K0/L0 复用，不为每循环重复开发。
