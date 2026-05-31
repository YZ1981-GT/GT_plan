# 需求文档：formula-engine-unification（公式引擎统一架构）

> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]]（§十五/§十七/§20.1/§20.2/§20.7/§二十一）
> 工作流：Design-First（设计先行，本需求文档从 design.md 派生反推）
> 设计：#[[file:.kiro/specs/formula-engine-unification/design.md]]

## 引言

平台报表公式求值引擎当前**至少 4 套并行**（`formula_engine` / `report_engine` / `formula_parser` / `formula_unified`），各有独立 AST 求值器，同一 DSL 在 4 处各解析一遍，函数支持集一致性无保证（语义漂移硬伤）。本需求把 4 套收敛为**单一企业级公式内核**（formula_engine 升级为唯一内核 L1 + report_engine 退化为编排/取数层 + formula_parser 解析并入 + formula_unified 因 Excel 语法域不同改名独立），并顺带收口公式审计留痕（三处分裂 → 唯一哈希链）。

核心约束：**零功能回归**（分阶段迁移，每阶段回归基线全绿）、**前端 API 零改动**、**金额全程 Decimal**、**删旧代码前 grep 确认 0 调用方**。

## 需求

### 需求 1：单一求值内核（消灭 4 套并行）

**用户故事**：作为平台维护者，我希望全平台只有一个报表公式求值内核，这样同一公式在报表/合并/附注/底稿任何业务域求值结果都逐位一致，消除语义漂移。

#### 验收标准

1. WHEN 全仓 grep 求值器（`_safe_eval`/`safe_eval_expr`/独立 AST eval）THEN 报表 DSL 求值逻辑只剩 `formula_engine` 一处（report_engine/formula_parser 无独立求值逻辑）
2. WHEN 同一公式 `TB('1002','期末余额')+SUM_TB('1400~1499','期末余额')` 经 report 域与 consol 域求值 THEN 函数集行为逐位一致（仅取数源不同）
3. WHEN `report_engine.evaluate_formula` 被调用 THEN 内部委托 `formula_engine.execute`，不再自带 `_safe_eval_expr`/`ReportFormulaParser` 求值
4. IF 单体报表既有公式 THEN 收敛后求值结果与收敛前逐位一致（R1 零回归守门）

### 需求 2：阶段 0 对照基线（迁移安全网）

**用户故事**：作为开发者，我希望在动任何收敛前先建立 4 套引擎对同一公式的输出对照基线，这样能暴露并固化现存语义差异，避免"统一"时悄悄改变某业务域结果。

#### 验收标准

1. WHEN 给定一组代表性公式（TB/SUM_TB/ROW/SUM_ROW/REPORT/PREV/AUX + 嵌套 + IF/ABS）THEN 对照测试记录 4 套引擎各自当前输出作基线
2. IF 某公式 4 套引擎输出不一致 THEN 基线测试显式标注差异（不静默通过），由人工确认目标语义
3. WHEN 内核 parse 层采纳递归下降替换 regex THEN 并行跑 diff 一致后才切换（保留 regex 一个版本周期降级）
4. WHEN 阶段 0 完成 THEN 产出 ADR-FORMULA-001「单内核 + 三层架构 + AmountResolver Protocol」

### 需求 3：三层分责架构（可维护 + 可扩展）

**用户故事**：作为开发者，我希望求值/取数/编排三责分离，这样改函数行为只改内核 registry、改取数口径只改 resolver，互不影响。

#### 验收标准

1. WHEN 新增一个 DSL 函数（如示例 `PCT(a,b)`）THEN 仅在 L1 `FunctionRegistry.register` 一处改动即全域可用
2. WHEN 新增一个数据源 THEN 仅实现一个 L3 `AmountResolver` Protocol 即可（不碰内核）
3. WHEN L1 内核执行 THEN 是纯函数（输入 `(formula, FormulaContext)` → 输出 `FormulaResult`，无 DB/async 耦合，可单测可缓存）
4. WHEN L2 编排层取数 THEN 负责 async 批量取数后构建同步 `FormulaContext` 传给 L1

### 需求 4：公式审计留痕收口哈希链（CAS 1131 合规）

**用户故事**：作为质控/EQCR，我希望公式变更留痕只在一处（防篡改哈希链），这样复核时一处可查全部公式变更，不用并三处。

#### 验收标准

1. WHEN 公式变更发生（report_config 内联 / report_config_service.update_config / consol_report 执行）THEN 统一调 `append_audit_log(action='formula.changed')` 写哈希链 `audit_log_entries`
2. WHEN `audit_log_helper.EVENT_TYPE_SCHEMAS` 加载 THEN 含 `formula_changed` schema（字段 module/row_code/action/old_formula/new_formula/result_value）
3. WHEN 前端调 `formula_audit_log` 的 GET 查询历史 THEN 后端改查 `audit_log_entries WHERE action_type='formula.changed'`（payload JSONB 过滤），**API 路径与返回结构零改动**
4. WHEN 收口完成 THEN `formula_audit_log` 的 `ensure_table` 懒建删除 + `core.Log` 的 `formula_updated` 分支删除（老表数据保留只读一个迁移周期）
5. IF 公式变更入哈希链 THEN 不可篡改（entry_hash + prev_hash，append-only）

### 需求 5：底稿 Cell 公式独立（语法域隔离）

**用户故事**：作为开发者，我希望底稿单元格 Excel 公式（`=A1+B2`）与报表 DSL（`TB('1002',...)`）明确分开，这样不会因"统一"误导把两个语法域强行合并。

#### 验收标准

1. WHEN `formula_unified.py` 重命名 THEN 改为 `cell_formula_evaluator.py`，文件头标注"底稿单元格 Excel 公式，非报表 DSL"
2. WHEN 重命名执行 THEN 调用方 `excel_html.py` / `import_templates.py` 的 import 路径自动更新（smartRelocate 改引用）
3. WHEN `cell_formula_evaluator` 收敛 THEN 不纳入报表 DSL 内核（保持独立的 Excel 语法求值）
4. IF 底稿 Cell 公式既有行为 THEN 重命名后行为 100% 不变（仅文件名 + import 路径变）

### 需求 6：收敛范围排除项（防误伤）

**用户故事**：作为开发者，我希望明确哪些 formula 相关 service 不在收敛范围，避免误伤非求值器。

#### 验收标准

1. WHEN 确定收敛范围 THEN `note_formula_engine.py`（8 类勾稽 Validator，输入数据→findings，非 evaluator）**排除**
2. WHEN 确定收敛范围 THEN `report_formula_service.py`（公式填充/seed，非求值）**排除**
3. WHEN 确定收敛范围 THEN `note_formula_generator` / `formula_reverse_index` / `wp_formula_dependency`（生成/依赖图，非求值）**排除**

### 需求 7：分阶段迁移与零回归守门

**用户故事**：作为现场负责人，我要求 4 套引擎收敛分阶段进行，每阶段独立可回滚、回归基线全绿才继续，禁止一次性合并。

#### 验收标准

1. WHEN 迁移执行 THEN 按阶段 0（对照基线）→ 1（report_engine 委托）→ 2（consol+formula_parser+formula_unified 收口）→ 3（审计+校验收口）顺序
2. WHEN 每阶段完成 THEN 单体报表 + 合并 + 附注 + 试算表既有测试全绿（零回归）
3. WHEN 删旧求值器代码 THEN 删前 grep 确认 0 调用方 + 删前后测试全绿 + 独立 commit
4. IF 阶段 1 报表委托后 THEN `test_report_engine` 全量基线逐位一致
5. WHEN 内核 `validate_formula` 接 address_registry THEN 存悬空引用的公式被拒（地址有效性前置校验）

### 需求 8：公式管理覆盖底稿数据源（§九 P1-7 补全）

**用户故事**：作为审计师，我希望公式管理中心（FormulaManagerDialog）也能管理底稿单元格公式，与报表/附注/合并公式统一入口。

> 实证修正：`FormulaManagerScope` 现已有 6 个 scope（note/consol_note/consol_worksheet/consol_report/report/tb，合并侧已由 consol Phase2 ADR-CONSOL-205 接入），**P1-7「覆盖合并」部分已完成**；本需求仅补**剩余缺口 = 底稿（workpaper）数据源未纳入**。

#### 验收标准

1. WHEN FormulaManagerScope 扩展 THEN 加 `'workpaper'` scope（底稿单元格公式）+ SCOPE_LABEL_MAP 加中文 label
2. WHEN 底稿公式纳入管理中心 THEN 走统一内核求值（与报表 DSL 一致，非 cell_formula_evaluator 的 Excel 语法那套——需评估底稿公式实际语法域归属）
3. IF 底稿公式是 Excel Cell 语法（`=A1+B2`）THEN 明确归 cell_formula_evaluator 不强纳报表 DSL 内核（语法域隔离，呼应需求 5）；IF 是 DSL（`TB()/WP()`）THEN 纳入内核
4. WHEN 公式变更 THEN 底稿公式变更也走哈希链留痕（formula.changed，与需求 4 一致）

> ⚠️ **实施前置**：需 readCode 确认底稿单元格公式的真实语法域（Excel Cell 语法 vs 报表 DSL），决定归内核还是归 cell_formula_evaluator——这直接影响"覆盖底稿"是"纳入内核"还是"管理中心展示入口对接 cell_formula_evaluator"。

### 非功能需求

- **NFR-1 零功能回归**：4 个收敛阶段每阶段回归基线全绿；R1 单体报表逐位一致守门
- **NFR-2 前端零改动**：公式历史查询 API 路径/返回结构不变
- **NFR-3 金额精度**：内核全程 Decimal（金额铁律）
- **NFR-4 可测性**：L1 内核纯函数（同输入同输出），PBT 守门语义一致（关联属性 Q1）
- **NFR-5 性能**：解析结果缓存（同公式不重复解析）

## 正确性属性（PBT 守护）

- **Q1 语义一致**：同一公式经任何业务域（report/consol）求值，函数集行为逐位一致
- **Q2 确定性**：同 formula + 同 FormulaContext → 同 FormulaResult（纯函数）
- **Q3 Decimal 无精度丢失**：求值全程 Decimal，无 float 中间态
- **Q4 解析往返**：parse(formula) 的 AST 求值结果 == 旧 regex 求值结果（阶段 0 对照基线）
- **Q5 审计完整**：每次公式变更恰好一条 formula.changed 入哈希链（不多不少）
