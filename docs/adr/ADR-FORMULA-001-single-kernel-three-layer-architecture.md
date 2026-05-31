# ADR-FORMULA-001: 单内核 + 三层架构 + AmountResolver Protocol（公式引擎统一）

## 状态

已接受 (2026-06-01)

## 背景

平台报表公式求值引擎当前**至少 4 套并行**（grep 实证）：

| 引擎 | 解析策略 | 取数方式 | 返回结构 | 扩展性 |
|------|---------|---------|---------|--------|
| `formula_engine.py` | regex token | **纯函数 + FormulaContext 注入** | **FormulaResult**(value/errors/warnings/trace) | **插件式 register_custom_function** |
| `report_engine.py` | regex token (ReportFormulaParser) | DB 耦合 + AmountResolver 注入(Phase1) | Decimal | 硬编码 |
| `formula_parser.py` | **真递归下降**(tokenize+Parser+AST) | DB 耦合(FormulaEvaluator) | Decimal | 硬编码 |
| `formula_unified.py` | regex (FormulaToken) | 内存 cells (Excel A1:B2) | float/None | 硬编码 |

**核心问题**：

1. **语义漂移**：同一 `TB()/SUM_TB()/ROW()` DSL 在 4 处各解析一遍，函数支持集（ABS/IF/ROUND/MAX/MIN/PREV/AUX）是否一致无保证——ADR-CONSOL-101 在合并侧踩过的硬伤的全局版。
2. **双引擎交叉使用**：`report_config.py:406-407` 同一请求内 `formula_parser.evaluate_formula`（求值）+ `formula_engine.FormulaEngine`（校验）——两套引擎对同一公式解析结果可能不一致。
3. **审计留痕三处分裂**：`formula_audit_log` 懒建表（绕 D6 迁移）+ `core.Log formula_updated` + `audit_log_entries` 哈希链——口径不一，复核需并三处。
4. **维护成本**：4 套独立 AST 求值器各自演进，改一处不惠及其他，bug 修复需重复 4 次。

**前置资产**：
- ADR-CONSOL-101/106 已建 `AmountResolver` Protocol（`TrialBalanceResolver`/`ConsolTrialResolver`）
- `audit_log_helper.append_audit_log` 哈希链（`EVENT_TYPE_SCHEMAS` 7 类 schema）
- `formula_engine.py` 已具企业级特征（纯函数 + Context 注入 + Result 对象 + 插件注册 + 校验）

## 决策

### 1. formula_engine.py 升级为唯一求值内核（L1）

`formula_engine.py` 是 4 套中**唯一已具备企业级特征的引擎**（纯函数 + `FormulaContext` 注入 + `FormulaResult` + 插件式 `register_custom_function` + `validate_formula`），升级为全平台唯一报表 DSL 求值内核。

**核心 API 契约**：
```python
def execute(formula: str | None, ctx: FormulaContext) -> FormulaResult:
    """唯一内核求值入口。纯函数：同 formula + 同 ctx → 同 FormulaResult。"""
```

### 2. 三层分责架构（Single-Kernel, Layered）


| 层级 | 职责 | 约束 |
|------|------|------|
| **L1 公式内核** (formula_engine) | 唯一报表 DSL 求值/解析/校验 | 纯函数，无 DB/async 耦合 |
| **L2 编排层** (report_engine 退化) | async 批量取数 → 构建 FormulaContext → 调 L1 | 负责 async↔sync 边界 |
| **L3 取数适配层** (Resolver Adapters) | 实现 AmountResolver Protocol，各域只管"从哪取数" | 每新增数据源仅实现一个 Resolver |

**职责边界**：
- L1 内核输入 `(formula, FormulaContext)` → 输出 `FormulaResult`，可单测可缓存。
- L2 编排解决"内核纯函数 vs 取数 async"的职责矛盾。
- L3 复用 Phase1 已建的 `TrialBalanceResolver`/`ConsolTrialResolver`，新增 NoteResolver/WPResolver/DisplayResolver。

### 3. AmountResolver Protocol 作为数据源抽象

复用 ADR-CONSOL-101 验证过的 Protocol 模式：

```python
@runtime_checkable
class AmountResolver(Protocol):
    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal: ...
    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal: ...
```

新增数据源 = 仅实现一个 Resolver，不碰内核。

### 4. parse 层升级：递归下降替换 regex

采纳 `formula_parser.py` 的递归下降解析（tokenize + Parser + AST 节点）并入内核 parse 层，替换脆弱的 `_TOKEN_PATTERNS` regex。对嵌套 `PREV(TB(...))` / `IF(TB>0, ROW, 0)` 等更严谨。

**迁移策略**：并行跑 diff（新 AST 求值 vs 旧 regex 求值）一致后才切换，保留 regex 一个版本周期降级。

### 5. formula_unified 改名 cell_formula_evaluator（语法域隔离）

`formula_unified.py` 实际处理底稿 Cell 公式（Excel 语法 `=A1+B2`，与报表 DSL `TB('1002',...)` 是不同语法域）。**改名 `cell_formula_evaluator.py` 保持独立，不纳入收敛**——消除"统一"误导命名，明确语法域边界。

### 6. FunctionRegistry 插件式函数注册

所有 DSL 函数（TB/SUM_TB/ROW/SUM_ROW/REPORT/PREV/AUX/NOTE/WP + 内置 ABS/ROUND/MAX/MIN/IF）注册到单一 `FunctionRegistry`。新增函数 = 注册一个 handler，全域可用。`validate_formula` 用 `registry.known_function_names()` 校验未知函数。

### 7. 审计留痕收口唯一哈希链

三处分裂（`formula_audit_log` 懒建表 + `core.Log formula_updated` + 哈希链）统一收口为 `append_audit_log(action='formula.changed')`：
- `EVENT_TYPE_SCHEMAS` 新增 `formula_changed` schema
- 3 个写入点统一改调 `append_audit_log`
- GET 改查 `audit_log_entries WHERE action_type='formula.changed'`（payload JSONB 过滤）
- 前端 API 路径/返回结构零改动
- 废 `ensure_table` 懒建 + `core.Log` formula_updated 分支

### 迁移策略

遵循 ADR-CONSOL-101 验证过的"先跑通注入版再删旧"稳妥模式，分 4 阶段：

1. **阶段 0**：建 4 引擎同一公式输出对照基线（PBT 守门）+ 内核固化
2. **阶段 1**：report_engine 委托内核（L2 编排 → L1 求值）
3. **阶段 2**：consol + formula_parser + formula_unified 收口
4. **阶段 3**：审计 + 校验收口

每阶段回归基线全绿才继续，禁止一次性合并。删旧代码前 grep 确认 0 调用方 + 删前后测试全绿 + 独立 commit。

### 收敛排除项

- `note_formula_engine.py`：8 类勾稽校验 Validator（输入数据→findings），非 evaluator
- `report_formula_service.py`：公式填充/seed，非求值
- `note_formula_generator` / `formula_reverse_index` / `wp_formula_dependency`：生成/依赖图，非求值

## 后果

### 正面

- **语义一致**：同一公式在报表/合并/附注/底稿任何业务域求值结果逐位一致（消灭语义漂移）
- **可维护**：改函数行为只改内核 registry、改取数口径只改 resolver，互不影响
- **可测**：L1 纯函数（同输入同输出），PBT 守门语义一致
- **可扩展**：新增 DSL 函数仅 `FunctionRegistry.register` 一处；新增数据源仅实现一个 Resolver
- **审计合规**：公式变更留痕唯一哈希链（CAS 1131），一处可查全部历史
- **金额精度**：内核全程 Decimal（金额铁律），无 float 中间态

### 负面/风险

- **迁移面广**：formula_engine 6+ 调用方、report_engine 报表+合并都在用，需分阶段稳妥迁移
- **递归下降并入复杂度**：parse 层升级需并行跑 diff 确保一致，保留 regex 降级一个版本周期
- **审计收口需协调**：3 个写入点分属不同 service，需逐一改造 + 前端 GET 改查哈希链

### 设计铁律

- 金额全程 `Decimal`（金额铁律）
- 删旧代码前 grep 确认 0 调用方 + 删前后测试全绿
- 公式变更只落哈希链一处（CAS 1131）
- 前端 API 路径/返回结构零改动

## 关联文档

- 设计文档：`.kiro/specs/formula-engine-unification/design.md`
- 需求文档：`.kiro/specs/formula-engine-unification/requirements.md`
- 调研文档：`docs/proposals/global-modules-status-and-improvement-2026-05-31.md`（§十五/§十七/§20.1/§20.2/§20.7）
- 前置 ADR：ADR-CONSOL-101（AmountResolver Protocol 首建）、ADR-CONSOL-106（consol async）
