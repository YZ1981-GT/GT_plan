# ADR-CONSOL-101: 合并报表复用 report_engine（AmountResolver 注入，删除重复公式引擎）

## 状态
已接受 (2026-05-31)

## 背景

`report_engine._safe_eval_expr`（ast.parse 安全求值，支持 ABS/IF/ROUND/MAX/MIN/比较）是 Phase 1 主引擎正确实现；而 `consol_report_service` 自己复制了一套 `_execute_formula`/`_resolve_consol_tb`/`_resolve_sum_consol`/`_extract_account_codes`。两套引擎各自演进 → 同一报表的单体版与合并版公式语义不一致（A1/A2），属审计准确性硬伤；根因是复制粘贴 + 各自演进。

（注：裸 `eval` 已在 Phase 0/2026-05-31 先行替换为 `_safe_eval_expr`，本 ADR 完成剩余的"注入抽象 + 删除重复取数"。）

## 决策

抽象 `AmountResolver` 协议（`resolve_tb` / `resolve_sum`），`report_engine` 公式求值入口接受 `resolver` 注入：

- 新增 `backend/app/services/amount_resolver.py`：`AmountResolver` Protocol + `TrialBalanceResolver`（单体，读 `trial_balance`，完整保留列名映射 + 未审模式）+ `ConsolTrialResolver`（合并，读 `consol_trial.consol_amount`）。
- `ReportFormulaParser.__init__` 增加可选 `resolver` 参数：`None` → 默认走内部 trial_balance 取数（**单体行为 100% 不变，R1**）；注入 `ConsolTrialResolver` 时 TB()/SUM_TB() 改走合并数据源。
- 新增模块级 `evaluate_formula(formula, *, resolver, row_cache)` 统一入口。
- `consol_report_service.generate_consol_reports` 改调 `evaluate_formula(resolver=ConsolTrialResolver(...))`，**删除** consol 侧 `_execute_formula`/`_resolve_consol_tb`/`_resolve_sum_consol`/`_extract_account_codes` 及死正则。

**为什么不给裸 eval 打白名单补丁**：eval 是反模式；主引擎已证明 ast 方案可行；维护两套求值器必然再次漂移。

## 后果

- 公式语义统一（单体改进自动惠及合并）+ 消除重复代码。
- consol 公式 token（TB/SUM_TB/ROW）是 report_engine 超集的子集，无独有 token，无需先补 report_engine（R2 风险消除）。
- 回归面靠单体报表全量回归基线（test_report_engine 等 56 测试全绿）+ 注入版先跑通再删旧守门（R1/R6）。
