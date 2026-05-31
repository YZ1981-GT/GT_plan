# ADR-CONSOL-205: 合并公式纳入公式管理中心 + formula_audit_log

## 状态
已接受 (2026-05-30)

## 背景

公式管理中心 `FormulaManagerScope` 已含 `consol_note` 但数据源树只有试算表/报表/附注，**无合并工作底稿/合并报表节点**；合并公式散在 consol_report_service（Phase 1 已统一为安全解析器）+ 前端 computed + mock CSV，未纳入管理中心/formula_audit_log（用户 5 大能力之"公式管理联动"未闭环）。

## 决策

- 数据源树（`FormulaManagerDialog.vue` treeData）补节点：
  - 新增「合并报表」（🔗，合并资产负债表/合并利润表）。
  - 既有 `consolidation` 节点（含净资产表/模拟权益法/合并抵消分录等 worksheet 表样）**标签纠正为「合并工作底稿」**（原误标"合并报表"且 icon 🏢，与新节点重名）——其子节点本就是工作底稿表样，key 不变（`_consolSheet` 路由不破坏），消除"两个合并报表"重复项。
- `FormulaManagerScope` 类型扩展 `consol_worksheet | consol_report` + SCOPE_LABEL_MAP（纯展示上下文标识）。
- 合并公式审计纳入 `formula_audit_log`（module='consol'）：`consol_report.py` generate 端点成功后调 `_write_consol_formula_audit`（每含公式报表行一条 action='execute'，与单体报表 module='report' 同源留痕）；审计写入独立 try/except，失败仅 warning 不影响报表生成。
- 合并公式求值复用 Phase 1 `report_engine._safe_eval_expr`（consol_report_service._execute_formula 已接，ast 安全求值支持 ABS/IF/ROUND/MAX/MIN/比较），保证管理中心展示=实际求值。

## 后果

- 正向：合并公式可见/可留痕/与单体同源；消除数据源树重复项。
- 代价：依赖 Phase 1 公式引擎统一先完成（前置，已满足）。
