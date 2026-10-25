# Task 2 证据：红基线核实与注释纠偏

> Requirements 2.1 / 2.2。本文件为可复核实证产物，作为「历史注释里的 `period_type`/`balance` 必 500」理由已过期的唯一真源。
> 只改**理由表述**，不放宽「禁止照抄 D3/D5/D6/D7 历史版本」的结论 —— 结论仍成立，理由改为真实缺陷 ①②③④。

## 1. 核实方法（三重实证）

1. **读 SQL 列 vs schema**：codegraph/grep 实读 D3/D5/D6/D7 aux 归集 SQL 的引用列，与 `tb_aux_balance` 真实 schema 逐列比对。
2. **真库 schema 快照**：postgres MCP（只读）取 `tb_aux_balance` 列清单。
3. **真库跑一次**：把 D3 的 aux SQL **逐字**在真库执行，确认返回行、不抛异常（= 不会 500），并数值证明真实缺陷 ①②。

## 2. D3/D5/D6/D7 aux SQL 实际引用列（实读源码）

四家 SQL 主体逐字一致，仅科目前缀不同：

| 文件 | 行 | 科目前缀 | SQL 引用列 |
|---|---|---|---|
| `wp_render_strategies/_d3_import_export.py` | 458 | `'2203%'` | `aux_name` / `opening_balance` / `closing_balance` / `account_code` / `is_deleted` / `project_id` |
| `wp_render_strategies/_d5_import_export.py` | 342 | `'1124%'` | 同上 |
| `wp_render_strategies/_d7_import_export.py` | 579 | `'2205%'` | 同上 |
| `services/d_cycle_extraction/detail_aggregation.py`（D6 `_AUX_QUERY`） | 40 | `'1141%'` | 同上 |

四家 SQL 一律 `SELECT aux_name, COALESCE(SUM(opening_balance),0), COALESCE(SUM(closing_balance),0) FROM tb_aux_balance WHERE project_id=:pid AND account_code LIKE '{prefix}%' AND is_deleted = false GROUP BY aux_name ORDER BY aux_name`。

**没有任何一处引用 `period_type` 或裸 `balance` 列。**

## 3. `tb_aux_balance` 真实 schema（postgres MCP 只读快照）

关键列（存在）：`project_id` `year` `account_code` `aux_type` `aux_name` `opening_balance` `debit_amount` `credit_amount` `closing_balance` `is_deleted` `dataset_id` …

- ✅ `aux_name` / `opening_balance` / `closing_balance` / `account_code` / `is_deleted` / `project_id` **全部存在**。
- ❌ **无 `period_type` 列**；❌ **无裸 `balance` 列**（只有 `opening_balance` / `closing_balance`）。

⇒ SQL 引用的列全部存在，PostgreSQL **不会抛 UndefinedColumn（42703）**，**不会 500**。

## 4. 真库跑一次（D3 SQL 逐字执行）

项目 `a7fc75e5-b67f-436d-a126-42423018b6ce`，account `2203%`，`is_deleted=false`：

- 命中 **2067 行**，返回真实往来单位（如「一四五医院」期初 26581.33 / 期末 17202.89），**无异常**。

⇒ 实证「运行必 500」为**假**。

## 5. 真实缺陷（数值实证）

- **① 裸 `is_deleted = false` 不走 `get_active_filter` ⇒ 跨数据集双算。**
  项目 `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` account `2203%`（`is_deleted=false`）分布在 **2 个 dataset_id**，各 654 行、期末合计**均为 21,183,245.14**。裸 SQL 求和两份 = **42,366,490.28 = 2×**；`get_active_filter` 只取 active 一份 = 21,183,245.14。**实测 2× 双算**，印证 requirements「aux 冗余实测 2×」。

- **② 直接 `GROUP BY aux_name` 未先锁 `aux_type` ⇒ 同科目挂多维度时金额双算。**
  结构性缺陷：SQL 不含 `pick_aux_type` 单维锁定。（本轮抽样项目 2203/1124/2205/1141 恰只挂单一 `aux_type`＝客户，故未触发倍数，但缺陷路径存在且无守卫。）

- **③ 科目码硬编码**：`'2203%'` / `'1124%'` / `'2205%'` / `'1141%'` 直接写死在 SQL，不从报表映射（`ReportLineAccountSpec` / `report_config`）解析。

- **④ 全额塞账龄首段（伪造账龄分布）**：
  - D3：`agingPrior={"within1": prior_balance,...}`、`agingAudited={"within1": current_balance,...}`（`_d3_import_export.py:488/494`）。
  - D7：`_aging_first_seg(balance)` 只把余额塞 `seg_keys[0]`，其余段 0（`_d7_import_export.py:600-604`）。
  - D6：`receivableWithin1y = current_bal`、`receivableAbove1y=0`（`detail_aggregation.py:102`）。

## 6. 结论

- 「`period_type`/`balance` 必 500」这一**理由**已过期、事实为假 —— SQL 用的列都存在、跑得通。
- 但「**禁止照抄 D3/D5/D6/D7 历史版本**」这一**结论仍成立**，理由改写为真实缺陷 ①②③④。
- 注释纠偏落地：
  - `four_table/aux_aggregation.py` 模块 docstring（原「引用了不存在的列，勿照抄」）→ 改为「历史版本裸写 `is_deleted`、未锁 `aux_type`、硬编码科目码、伪造账龄，勿照抄」。
  - `_g7_long_term_equity_main_import_export.py`（原「其 SQL 引用不存在的列 period_type/balance，运行必 500」）→ 改为真实缺陷表述。
  - K1/D1 源码经 grep 实证**不含**该过期表述（仅 G7 与共享件 docstring 携带），故无需改。
  - D6 `detail_aggregation.py:38` 注释「真实列: opening_balance/closing_balance（无 period_type/balance 列）」本身**已是正确表述**（陈述真实列、未声称 500），保留。
