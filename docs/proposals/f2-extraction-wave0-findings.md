# F2 四表库取数 — Wave 0 核实结果

> spec: `.kiro/specs/f2-four-table-extraction-refresh/` Task 1.3
> 日期: 2026-07-29

## 1. 评估器列名核实

`wp_formula_eval_service._COLUMN_MAP`（line 64-70）：

| 公式列名 | 映射目标 DB 列（trial_balance） |
|---------|-------------------------------|
| 期末余额 | audited_amount |
| 审定数 | audited_amount |
| 年初余额 | opening_balance |
| 期初余额 | opening_balance |
| 未审数 | unadjusted_amount |
| RJE调整 | rje_adjustment |
| AJE调整 | aje_adjustment |

**确认：无「借方发生额」/「贷方发生额」/「期末余额→closing_balance」/「借方金额→debit_amount」/「贷方金额→credit_amount」等 tb_balance 列映射。**

`_resolve_tb` 查的是 **`TrialBalance`**（`from app.models.audit_platform_models import TrialBalance`），不是 `TbBalance`。

→ **结论：F2 取数公式（TB('1401','借方发生额')）绝对不能走共享 `evaluate_wp_formula_expression`，否则会映射到 `audited_amount`（默认回退）返错值。F2 必须自有 tb_balance 求值服务。**

## 2. PUT /formulas 保存路径分析

`wp_formula.py` PUT 端点（line 675）：

```python
if saved.formula_type == "auto_calc":
    evaluated_value, eval_errors = await evaluate_wp_formula_expression(...)
```

保存后**只对 `auto_calc` 类型**调 generic evaluator 求值：
- 若 `is_dcycle_anchor=True`（D 循环 Tier A 锚点 + 灰度开）→ **不写 parsed_data 网格**，只返 `evaluated_value`
- 若非 D 循环锚点 → 写 parsed_data 网格

**F2 方案（Wave 3 实现要点）**：

对 F2 底稿（`base_wp_code` 前缀='F2'），需要：
1. 在 PUT 保存路径加一个分支：`is_f2_anchor = settings.F2_FOUR_TABLE_EXTRACTION_ENABLED and base_wp_code == 'F2' and f2_is_known_anchor(body.target_cell)`
2. `is_f2_anchor=True` 时：
   - **保存校验**（find_unsupported_formula_functions + F2 列名校验）照常执行
   - **不调 generic `evaluate_wp_formula_expression`**（F2 求值走 `f2_extraction.extract`，那是 render/刷新路径的职责，非保存即时求值）
   - 不写 parsed_data 网格（F2 锚点写 checklist_responses.conclusion，由 render seed/刷新完成）
   - 返回 `evaluated_value=None`（或可选调 `f2_extraction` 算出当前值纯展示，非必须）
3. PUT 校验新增分支位置：紧跟 `is_dcycle_anchor` 判定块之后，在求值 `if saved.formula_type == "auto_calc":` 块之前做 `if is_f2_anchor: ... return_early`

**此改动是 additive 分支，灰度关时 `is_f2_anchor` 恒 False，零回归。**

## 3. `find_unsupported_formula_functions` 可复用性

该函数是纯字符串检测（不依赖 DB/evaluator），只检 AUX/PREV/LEDGER/COUNT_LEDGER → 可直接复用于 F2 保存校验。

F2 额外需要：`f2_validate_column_names(expression)` 检出列名 ∉ {期初余额,期末余额,借方发生额,贷方发生额} → 422。

## 4. 总结

| 维度 | 结论 | Wave 影响 |
|------|------|-----------|
| 评估器列名 | 无 借方/贷方发生额；查 trial_balance 非 tb_balance | F2 必须自有 tb_balance 求值（Wave 1 `extract.py`） |
| PUT 保存 | auto_calc 时调 generic evaluator | Wave 3 加 `is_f2_anchor` 分支跳过 generic eval |
| 保存校验 | `find_unsupported_formula_functions` 可复用 | Wave 3 追加 F2 列名校验 |
| parsed_data 写回 | D 循环锚点不写网格 | F2 锚点同理不写网格 |
