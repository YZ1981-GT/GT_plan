# 全下游符号消费点清单（Task 1.5 产出）

实证方法：codegraph_explore + grepSearch（closing_balance / audited_amount / unadjusted_amount / `=TB(` / `=ADJ(`）。
供 Task 2-8 改造时逐一核对。状态：✅=已规划改造任务 / ⚠️=需确认无旧约定假设 / ✓=纯读取（回归验证即可）。

## A. 入库层（写 v2 正数）

| 点 | 文件 | 处理 | 任务 |
|---|---|---|---|
| convert_balance_rows | converter.py | 借-贷净额→改 direction_resolver 存正数 | T2.1 ✅ |
| convert_ledger_rows | converter.py | 分录方向标记 | T2.2 ✅ |

## B. trial_balance 生成层（关键：去二次翻转）

| 点 | 文件:行 | 处理 | 任务 |
|---|---|---|---|
| recalc_unadjusted | trial_balance_service.py:189-212 | 损益类硬编码 `-total_cr`→direction_resolver | T3.1 ✅ |
| get_summary_with_adjustments | trial_balance_service.py:527-536 | "取反"补偿 `if is_credit_dir and amount<0` 移除 | T3.2 ✅ |
| recalc_adjustments / recalc_audited | trial_balance_service.py | audited=unadj+rje+aje 方向验证 | T3.3 ✅ |

## C. 平衡校验层（目标态 / 对齐）

| 点 | 文件 | 处理 | 任务 |
|---|---|---|---|
| _check_debit_credit_balance | data_quality_service.py | 已按 category 分方向=目标态 | T4.2 ✅ |
| consistency_gate check_tb/bs_balance | consistency_gate.py | 资产=负债+权益，保持 | T4 ✅ |
| balance_diagnostics | balance_diagnostics/* | 容差统一 | T4.1 ✅ |
| consistency_check_service | consistency_check_service.py:62-264 | 读 unadjusted/audited 对账 | ⚠️ T4 核对 |
| consistency_replay_engine | consistency_replay_engine.py:124-187 | tb closing vs trial unadjusted；report vs audited | ⚠️ T4 核对（阈值 0.01 用 SUM 差，新约定下需确认口径） |

## D. 调整 / 合并 / CFS（独立符号假设）

| 点 | 文件 | 处理 | 任务 |
|---|---|---|---|
| adjustment_service | adjustment_service.py | 借贷平衡+审定数符号 | T4.3 ✅ |
| consol_report_service | consol_report_service.py:477-487 | audited_amount 加总+平衡校验，容差1元 | T4.4 ✅ |
| consol_individual_sum_service | consol_individual_sum_service.py | audited_amount 加总（口径须与 worksheet 一致） | ⚠️ T4.4 核对 |
| consol_worksheet_engine._get_audited_amount | consol_worksheet_engine.py | audited 取数 | ⚠️ T4.4 核对 |
| cfs_worksheet_engine | cfs_worksheet_engine.py:197-692 | period_change=closing(audited)-opening | T4.4 ✅ |

## E. 公式取数层

| 点 | 文件 | 处理 | 任务 |
|---|---|---|---|
| cell_formula_evaluator | cell_formula_evaluator.py:418-452 | TB/WP/AUX 字段映射（审定数→audited_amount 等） | T5.1 ✅ |
| data_fetch_custom | data_fetch_custom.py | transform negate 配置 | T5.1/5.2 ✅ |
| module_cell_resolver | custom_query/module_cell_resolver.py | TB 虚拟 sheet 列映射 | T5.1 ✅ |

## F. 附注 / 披露（纯读 audited_amount）

| 点 | 文件 | 处理 | 任务 |
|---|---|---|---|
| disclosure_engine | disclosure_engine.py | 读 audited_amount | T5.3 ⚠️ 确认无符号假设 |
| disclosure_trace | disclosure_trace.py | 读 audited_amount | T5.3 ⚠️ |
| consistency_check_service workpaper | parsed_data.audited_amount | 底稿审定数对账 | T8.2 回归 |

## 关键提醒
- **阈值 0.01 的对账（consistency_replay_engine）**：tb closing vs trial unadjusted、report vs audited 用 `ABS(SUM差)>0.01`，新约定下两边都应同号正数，差值逻辑不变但需回归确认。
- **cfs/consol period_change = closing - opening**：新约定下 closing/opening 同为正数自然方向，period_change 语义需确认（尤其负债类减少）。
- T2-T8 改造时每动一处，回到本清单勾掉并标注实际改动。
