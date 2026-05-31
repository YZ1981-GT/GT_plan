# 实施计划：formula-engine-unification（公式引擎统一架构）

> 设计：#[[file:.kiro/specs/formula-engine-unification/design.md]]
> 需求：#[[file:.kiro/specs/formula-engine-unification/requirements.md]]
> 工作流：Design-First | 分 4 阶段 ~6.5 人天 | 每阶段回归基线全绿才继续
> 铁律：删旧求值器前 grep 0 调用方 + 删前后测试全绿 + 独立 commit；前端 API 零改

## 阶段 0 — 内核固化 + 对照基线（~2 天）

- [ ] 1. 建立 4 套引擎对照基线测试
  - 准备代表性公式集（TB/SUM_TB/ROW/SUM_ROW/REPORT/PREV/AUX + 嵌套 PREV(TB(...)) + IF/ABS/ROUND/MAX/MIN）
  - 对每条公式记录 4 套引擎（formula_engine/report_engine/formula_parser/formula_unified 适用者）当前输出
  - 不一致项显式标注（不静默通过），人工确认目标语义
  - _需求: 2.1, 2.2_ _属性: Q1, Q4_

- [ ] 2. 确立 L1 内核 API 契约
  - `execute(formula, FormulaContext) -> FormulaResult` 确立为唯一内核入口
  - `FormulaContext` 扩展 note_data/wp_data/aux_data 字段
  - `FormulaResult` 含 value/errors/warnings/trace
  - _需求: 3.3, 3.4_ _属性: Q2_

- [ ] 3. parse 层升级：递归下降替换 regex
  - 把 formula_parser 的 tokenize + Parser + AST 节点并入内核 parse 层
  - 并行跑 diff（新 AST 求值 vs 旧 regex 求值）一致后才切换
  - 保留 regex 一个版本周期降级
  - _需求: 2.3_ _属性: Q4_

- [ ] 4. FunctionRegistry 插件式函数注册
  - 内置函数（TB/SUM_TB/ROW/SUM_ROW/REPORT/PREV/AUX/NOTE/WP + ABS/ROUND/MAX/MIN/IF）注册到 registry
  - `register_custom_function` 底层改委托 FunctionRegistry.register
  - `validate_formula` 用 registry.known_function_names 校验未知函数
  - _需求: 3.1_ _属性: Q1_

- [ ] 5. 产出 ADR-FORMULA-001
  - 「单内核 + 三层架构 + AmountResolver Protocol」决策记录
  - 注册前查编号防冲突
  - _需求: 2.4_

- [ ] 6. 阶段 0 PBT
  - Q2 确定性（同输入同输出）+ Q3 Decimal 无精度丢失 + Q4 解析往返
  - hypothesis max_examples 10~15
  - _需求: 1.2_ _属性: Q2, Q3, Q4_

## 阶段 1 — report_engine 委托内核（~1.5 天）

- [ ] 7. report_engine.evaluate_formula 改委托 L1
  - 改为：L2 编排（预载 tb_data/row_cache/prior_tb_data）→ 调 `formula_engine.execute`
  - 删除 report_engine 内嵌的 `_safe_eval_expr` + `ReportFormulaParser` 求值逻辑（保留取数编排）
  - 保持 `evaluate_formula` 签名向后兼容（reports + consol 调用方零改）
  - _需求: 1.3, 7.4_ _属性: Q1_

- [ ] 8. L3 取数适配层补全
  - 复用 TrialBalanceResolver / ConsolTrialResolver（Phase1 已建）
  - 新增 NoteResolver / WPResolver / DisplayResolver（实现 AmountResolver Protocol）
  - _需求: 3.2_ _属性: Q1_

- [ ] 9. 阶段 1 回归基线
  - test_report_engine 全量逐位一致（R1 守门）
  - test_formula_parser / test_phase8 / test_cfs_worksheet / test_audit_report 全绿
  - _需求: 1.4, 7.2, 7.4_

## 阶段 2 — consol + formula_parser + formula_unified 收口（~1.5 天）

- [ ] 10. consol 随阶段 1 自动收口
  - consol_report_service 已走 report_engine.evaluate_formula（ADR-CONSOL-101），验证随阶段 1 收口
  - _需求: 1.2_ _属性: Q1_

- [ ] 11. formula_parser 收口
  - report_config.py 的 formula_parser.evaluate_formula 改委托内核
  - **首批改造 report_config.py 同文件双引擎混用**（§20.1）：parser 求值 + engine 校验 → 统一走内核
  - grep 确认 formula_parser 无其他调用方后删独立求值器
  - _需求: 1.1, 1.3, 7.3_ _属性: Q1_

- [ ] 12. formula_unified 改名独立（非收敛）
  - `formula_unified.py` → `cell_formula_evaluator.py`（smartRelocate 自动改 excel_html/import_templates 引用）
  - 文件头标注"底稿单元格 Excel 公式，非报表 DSL"
  - 删除独立 `_safe_eval`？否——保留（Excel 语法独立求值），仅去"统一"误导命名
  - _需求: 5.1, 5.2, 5.3, 5.4_

- [ ] 13. 阶段 2 回归
  - report_config / 公式预览 / 底稿 Cell 公式相关测试全绿
  - 全仓 grep 确认报表 DSL 求值器只剩 formula_engine
  - _需求: 1.1, 7.2_

## 阶段 3 — 审计 + 校验收口（~1.5 天，并入 §12.1）

- [ ] 14. formula_changed schema + 写入收口
  - audit_log_helper.EVENT_TYPE_SCHEMAS 加 formula_changed
  - 3 写入点（report_config 内联 / report_config_service.update_config / consol_report）统一改 append_audit_log
  - FormulaResult.trace 入留痕
  - _需求: 4.1, 4.2_ _属性: Q5_

- [ ] 15. formula_audit_log GET 改查哈希链
  - GET 改查 `audit_log_entries WHERE action_type='formula.changed'`（payload JSONB 过滤 module/row_code）
  - 前端 apiPaths 不动（API 路径/返回结构零改）
  - _需求: 4.3_

- [ ] 16. 废懒建表 + core.Log 分支
  - grep 确认无其他读取 formula_audit_log 表后停写 + 删 ensure_table 懒建
  - 删 core.Log 的 formula_updated 分支
  - 老表数据保留只读一个迁移周期
  - _需求: 4.4_

- [ ] 17. validate_formula 接 address_registry
  - 内核 validate_formula 加可选 address_validator（存悬空引用即拒）
  - _需求: 7.5_

- [ ] 17b. 公式管理覆盖底稿数据源（§九 P1-7 补全）
  - **前置 readCode**：确认底稿单元格公式真实语法域（Excel Cell `=A1+B2` vs DSL `TB()/WP()`）
  - FormulaManagerScope 加 `'workpaper'` scope + SCOPE_LABEL_MAP 中文 label
  - Excel 语法归 cell_formula_evaluator（管理中心展示入口对接）；DSL 归内核
  - 底稿公式变更走哈希链 formula.changed 留痕
  - _需求: 8.1, 8.2, 8.3, 8.4_ _属性: Q5_

- [ ] 18. 阶段 3 审计 PBT + 收尾
  - Q5 审计完整（每次公式变更恰好一条 formula.changed 入哈希链）
  - 更新 INDEX.md + memory 完成记录
  - 单 commit（commit 前 git status 确认无其他 staged）
  - _需求: 4.5_ _属性: Q5_

- [ ]* 19. 全链路真实验证（待 start-dev.bat 环境）
  - Playwright：报表公式编辑→求值→历史查询 端到端
  - 显式标"待环境"不伪绿
  - _需求: 7.2_
