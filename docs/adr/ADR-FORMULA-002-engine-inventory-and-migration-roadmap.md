# ADR-FORMULA-002: 公式引擎族盘点与统一迁移路线

## 状态

已接受 (2026-06-07)

> 本 ADR 是 ADR-FORMULA-001 的操作补充，侧重盘点调用方、diff 函数集、明确迁移顺序。

## 背景

ADR-FORMULA-001 确立了"单内核 + 三层架构"方向，但缺乏：
1. 各引擎调用方的完整盘点（谁在用、用了什么）
2. 各引擎支持函数集的逐项对比（语义漂移的具体位置）
3. 可执行的迁移顺序和验收标准

本 ADR 补齐以上三块，作为迁移执行的操作手册。

---

## 1. 引擎调用方盘点

### 1.1 `formula_engine.py`（统一内核，报表 DSL）

**导出符号**：`FormulaEngine`, `execute`, `FormulaContext`, `FormulaResult`, `validate_formula`, `safe_eval_expr`, `WPExecutor`, `AddressValidator`, `_validate_custom_expression`, `FunctionRegistry`

| 调用方文件 | 使用方式 | 场景 |
|---|---|---|
| `app/routers/formula.py` | `FormulaEngine` 实例化 + `execute` | 公式路由（增删改查+执行） |
| `app/routers/report_config.py:406-407` | `fe_execute` + `FormulaContext` | 报表配置调试公式 |
| `app/services/event_handlers.py:406` | `FormulaEngine` 缓存失效 | 数据变更事件 |
| `tests/test_formula_engine.py` | `execute`, `FormulaContext`, `validate_formula` | 单元测试 |
| `tests/test_formula_engine_baseline.py` | `fe_execute`, `safe_eval_expr` | 4 引擎对照基线 |
| `tests/test_formula_engine_contract.py` | `execute`, `FormulaContext`, `FormulaResult` | 契约测试 |
| `tests/test_formula_engine_registry.py` | `FunctionRegistry` | 注册表测试 |
| `tests/test_formula_engine_phase0_pbt.py` | `FormulaContext`, `FormulaResult` | PBT 属性测试 |
| `tests/test_formula_engine_parse_roundtrip.py` | AST 节点类 | 解析往返测试 |
| `tests/test_formula_engine_address_validator.py` | `AddressValidator` | 地址校验 |
| `tests/test_custom_dsl_coding.py` | `FormulaEngine` | 自定义函数注册 |
| `tests/test_custom_wp_formula_full_chain.py` | `WPExecutor` | 底稿公式全链路 |

### 1.2 `report_engine.py`（L2 编排层）

**导出符号**：`ReportEngine`, `ReportFormulaParser`, `evaluate_formula`, `_safe_eval_expr`

| 调用方文件 | 使用方式 | 场景 |
|---|---|---|
| `app/routers/reports.py` | `ReportEngine` | 报表生成主路由 |
| `app/routers/report_config.py:441,521` | `evaluate_formula` | 报表配置调试 |
| `app/routers/import_templates.py:492` | `ReportEngine` | 模板导入生成报表 |
| `app/services/chain_orchestrator.py:731` | `ReportEngine` | 一键生成链路 |
| `app/services/consol_report_service.py:108` | `evaluate_formula`, `ReportFormulaParser` | 合并报表 |
| `app/services/event_handlers.py:129` | `ReportEngine` | 试算表更新事件 |
| `scripts/seed/init_4_projects.py` | `ReportEngine` | seed 脚本 |
| `tests/test_report_engine.py` | `ReportEngine`, `ReportFormulaParser` | 单元测试 |
| `tests/test_cfs_worksheet.py` | `ReportEngine` | 现金流量表测试 |
| `tests/test_audit_report.py` | `ReportEngine` | 审计报告测试 |
| `tests/test_phase8*.py` | `ReportEngine` | Phase8 测试 |
| `tests/test_formula_engine_baseline.py` | `evaluate_formula`, `_safe_eval_expr` | 对照基线 |
| `tests/services/test_consol_*.py` | `evaluate_formula` | 合并测试 |

### 1.3 `formula_parse_utils.py`（递归下降解析器）

**导出符号**：`parse_formula`, `tokenize`, `evaluate_formula`, `ParseError`, AST 节点类

| 调用方文件 | 使用方式 | 场景 |
|---|---|---|
| `tests/test_formula_parser.py` | `parse_formula`, `tokenize`, `evaluate_formula` | 解析器测试 |
| `tests/test_formula_engine_baseline.py` | `evaluate_formula` | 对照基线 |

> ⚠️ **生产代码 0 调用**：仅测试引用。按 ADR-FORMULA-001 方向应并入 formula_engine 内核 parse 层。

### 1.4 `cell_formula_evaluator.py`（底稿 Cell 公式，独立语法域）

**导出符号**：`execute_formula`, `parse_formula`, `validate_formula`, `save_formula_batch`, `_safe_eval`

| 调用方文件 | 使用方式 | 场景 |
|---|---|---|
| `app/routers/excel_html.py:683` | `execute_formula` | 底稿 HTML 渲染回写 |
| `app/routers/import_templates.py:569` | `save_formula_batch` | 模板导入批量保存公式 |
| `tests/test_formula_engine_baseline.py` | `execute_formula`, `_safe_eval` | 对照基线 |
| `tests/test_workpaper_formula_scope.py` | `parse_formula`, `validate_formula` | 作用域测试 |

> ✅ **独立语法域**（Excel `=A1+B2` 语法）。ADR-FORMULA-001 决定保持独立，不纳入报表 DSL 内核收敛。

### 1.5 `note_formula_engine.py`（附注勾稽校验）

**导出符号**：`validate_note`, `Finding`, 8 类 Validator（BalanceCheck, WideTableHorizontal, VerticalReconcile, CrossCheck, SubItemCheck, AgingTransition, CompletenessCheck, LLMReview）

| 调用方文件 | 使用方式 | 场景 |
|---|---|---|
| `app/routers/note_templates.py:22` | `validate_note`, `Finding` | 附注校验 API |
| `tests/test_multi_standard_notes.py` | 8 类 Validator | 单元测试 |

> ✅ **排除出收敛**：是 Validator（输入数据→findings），非 Evaluator（公式→数值）。

---

## 2. 支持函数集 Diff

### 2.1 报表 DSL 函数集对比

| 函数 | formula_engine | report_engine | formula_parse_utils | 语义 |
|---|---|---|---|---|
| `TB(code, col)` | ✅ | ✅ | ✅ | 取试算表指定科目指定列金额 |
| `SUM_TB(prefix, col)` | ✅ | ✅ | ✅ | 汇总前缀匹配科目 |
| `ROW(row_code)` | ✅ | ✅ | ❌ | 取报表其他行金额 |
| `SUM_ROW(...)` | ✅ | ❌ | ❌ | 汇总多行 |
| `REPORT(type, row)` | ✅ | ❌ | ❌ | 跨表取值 |
| `NOTE(section)` | ✅ | ❌ | ❌ | 取附注金额 |
| `WP(code, cell)` | ✅ | ❌ | ❌ | 取底稿单元格值 |
| `AUX(code, col)` | ✅ | ❌ | ❌ | 取辅助账余额 |
| `PREV(expr)` | ✅ | ❌ | ❌ | 上年同期值 |
| `IF(cond, a, b)` | ✅ | ❌ | ✅ | 条件表达式 |
| `ABS(x)` | ✅ | ✅ (via _safe_eval) | ✅ | 绝对值 |
| `ROUND(x, n)` | ✅ | ✅ (via _safe_eval) | ✅ | 四舍五入 |
| `MAX(a, b)` | ✅ | ✅ (via _safe_eval) | ✅ | 最大值 |
| `MIN(a, b)` | ✅ | ✅ (via _safe_eval) | ✅ | 最小值 |

### 2.2 语义漂移风险点

| 风险 | 描述 | 影响 |
|---|---|---|
| ROW 未统一 | `report_engine` 用 `ROW` 取报表行；`formula_engine` 也支持但实现路径不同 | 合并报表 vs 单体报表可能取值不一致 |
| _safe_eval 实现差异 | `formula_engine.safe_eval_expr` vs `report_engine._safe_eval_expr` 白名单不完全相同 | 边界表达式可能一方通过一方拒绝 |
| Decimal vs float | `formula_engine` 全程 Decimal；`cell_formula_evaluator` 返回 float | 底稿 Cell 公式精度低于报表 DSL |
| PREV 仅内核支持 | `report_engine`/`formula_parse_utils` 无法处理 `PREV(TB(...))` | 上年对比公式只能走 formula_engine 路径 |

### 2.3 Cell 公式（Excel 语法）— 独立语法域

| 函数 | cell_formula_evaluator | 语义 |
|---|---|---|
| `=A1+B2` | ✅ | 单元格引用 + 算术 |
| `=SUM(A1:A10)` | ✅ | 范围求和 |
| `=IF(B2>0, C2, 0)` | ✅ | 条件 |
| `=VLOOKUP(...)` | ❌ | 未实现 |
| `=AVERAGE(...)` | ❌ | 未实现 |

> 与报表 DSL 是完全不同的语法域，不纳入统一。

---

## 3. 统一主引擎决策

### 3.1 主引擎：`formula_engine.py`

**选择理由**（实证）：
- 唯一具备企业级特征：纯函数 + FormulaContext 注入 + FormulaResult + 插件注册 + 校验
- 最大函数集覆盖（13 个 DSL 函数 + 4 个内置函数）
- 已有 PBT 属性测试守门
- ADR-FORMULA-001 已确认

### 3.2 迁移路线（具体步骤）

```
阶段 0（已完成）：4 引擎对照基线
  ├── test_formula_engine_baseline.py 已建立
  ├── 同一公式经 4 路径求值逐位一致性验证
  └── PBT 守门属性已建立

阶段 1（待执行）：report_engine 委托内核
  ├── report_engine.evaluate_formula → 委托 formula_engine.execute
  ├── report_engine._safe_eval_expr → 委托 formula_engine.safe_eval_expr
  ├── ReportFormulaParser 保留（解析→构造 FormulaContext→委托内核）
  ├── 回归：test_report_engine + test_cfs_worksheet + consol 全绿
  └── 验收：report_engine 无独立 eval/ast.parse 逻辑

阶段 2（待执行）：formula_parse_utils 收口
  ├── formula_parse_utils.evaluate_formula → 委托内核
  ├── 递归下降 tokenize + Parser 考虑并入内核 parse 层
  ├── report_config 路由改用内核统一入口
  ├── 回归：test_formula_parser 全绿
  └── 验收：formula_parse_utils 无独立求值逻辑

阶段 3（不做）：cell_formula_evaluator 保持独立
  └── 语法域不同（Excel vs DSL），不强行统一

阶段 4（待执行）：审计留痕收口
  ├── formula_audit_log 懒建表 → 迁移到 audit_log_entries
  ├── core.Log formula_updated → 改 append_audit_log
  ├── 统一查询接口
  └── 删除 ensure_table 反模式
```

### 3.3 验收标准

- [ ] 全仓 grep 独立求值器（`_safe_eval`/独立 AST eval）只剩 `formula_engine` + `cell_formula_evaluator` 两处
- [ ] 同一公式经报表/合并/底稿任何业务域求值，逐位一致（PBT 守门）
- [ ] 新增 DSL 函数仅改 `FunctionRegistry` 一处即全域可用
- [ ] 公式变更留痕唯一哈希链

---

## 4. 后果

### 正面
- 消除 4 套并行求值器的语义漂移风险
- 新增函数/修复 bug 只需改一处
- 审计留痕单一来源（CAS 1131 合规）
- 迁移路径清晰，每阶段独立可验证

### 负面/风险
- 阶段 1-2 迁移涉及 report_engine 10+ 调用方，需分批逐步
- formula_parse_utils 递归下降并入内核增加 parse 层复杂度
- 审计留痕收口需协调 3 个写入点

### 决策铁律
- `cell_formula_evaluator`（Excel 语法）永远独立，不纳入报表 DSL 内核
- `note_formula_engine`（Validator）永远独立，不是求值器
- 迁移每阶段回归基线全绿才继续，禁止跨阶段合并
- 金额全程 Decimal（金额铁律）

## 关联文档

- ADR-FORMULA-001: 架构决策
- `docs/proposals/global-modules-status-and-improvement-2026-05-31.md` §十五
- `backend/tests/test_formula_engine_baseline.py`: 4 引擎对照基线
- `docs/architecture/service-capability-ledger.md`: 公式引擎族注册表
