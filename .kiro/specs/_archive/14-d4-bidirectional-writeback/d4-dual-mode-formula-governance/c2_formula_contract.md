# C2 公式定义契约 — D4 双模式

> 状态：FROZEN（此文件为门控契约，不得在未评审情况下修改）
> 依据：Requirements 3.1 / 3.2 / 3.3 / 3.4
> 生成依据：2026-06 grep 实证（`backend/app/services/formula_*` + `backend/app/services/formula_management/` + `backend/app/services/formula_runtime/` + `backend/app/services/wp_formula_service.py` + `backend/app/services/d4_extraction/` + `backend/app/models/workpaper_models.py` + `backend/data/ledger_adapters/wp_render_schema/generated/D4-*.yaml` + `audit-platform/frontend/src/components/formula/`）
> 关联 spec 产物：`formula_engine.py`（L1 内核）/ `formula_management/engine.py`（三类型分派）/ `formula_management/preset_library.py`（预设库 custom/seed 双源）/ `formula_runtime/contracts.py`（CanonicalFormulaTarget + FormulaMutation）/ `wp_formula_service.py`（WpFormula CRUD）/ `user_formula_v2.py`（CAS + batch mutate）/ `formula_grammar.py`（函数白名单）

---

## A. 公式定义 Key 规范（Requirement 3.1）

### A.1 冻结的 Key 结构

```
key = {wp_id}:{stable_sheet_key}:{row_key}:{field_key}[#custom]
```

- **`wp_id`**：运行时底稿实例 ID（UUID）。**必须**使用 `working_paper.id` 而非 `wp_code`。
- **`stable_sheet_key`**：sheet 的稳定标识，**不随 sheet 改名而变**。
- **`row_key`**：行的稳定标识，**不随行号变化而变**。
- **`field_key`**：字段名（列语义 key，如 `本期未审数合计` / `期末余额` / `审定数`），**不是** `col_a` / `col_b` 等自动占位符。
- **`#custom` 后缀**：存在时表示当前公式为 custom 覆盖，与 preset 同键并存不冲突；`preset_version` 仅参与版本比较，**不进入** key。

### A.2 `preset_version` 语义（Requirement 3.1 后半）

`preset_version` 是**公式定义本身的版本字段**（同一 key 上的多次修订），**不是**业务 target identity 的一部分。它**禁止**参与 key 拼接——否则同一 target 会因 preset 升级产生多条 key 记录，导致去重与追溯断裂。

### A.3 现状 grep 实证（Requirement 3.1 落地状态）

| 需求项 | 现状 | 依据 | 状态 |
|--------|------|------|------|
| `wp_id` 使用 | `WpFormula.wp_id` FK → `working_paper.id`（UUID） | `workpaper_models.py` L835-845 | **已实现** |
| `sheet_name` 字段 | 存在（`String(255)`）但**非 stable** | 同上 L846；无 rename 保护 | **UNVERIFIABLE — 语义不达标** |
| `target_cell` 字段 | 存在（Excel cell ref，如 `B5`）但**非稳定 row_key/field_key** | 同上 L847 | **UNVERIFIABLE — 语义不达标** |
| `#custom` 后缀 | `formula_source ∈ {preset, custom, reference}` 是**分类枚举**，非 key 后缀布尔位 | `wp_formula_service.py` L40-42 | **UNVERIFIABLE — 分类替代 boolean 未拆** |
| 唯一索引 | `uq_wp_formula_wp_sheet_cell (wp_id, sheet_name, target_cell)` 与冻结 key **不匹配** | `workpaper_models.py` L900-904 | **UNVERIFIABLE — 索引契约违背** |
| `preset_version` | 不存于 `WpFormula`；`definition_version`（定义修订号）混同使用 | `workpaper_models.py` L883-886 | **UNVERIFIABLE — 语义混同** |

**结论**：Requirement 3.1 的**逻辑契约**（`wp_id + stable_sheet_key + row_key + field_key + custom`）在本 spec 冻结为门控；**当前 DB 三层实现（`wp_formula` 表 + `WpFormula` ORM + `WpFormulaService`）与冻结 key 不一致**，需在 Task 3.2/3.3 补迁移。

### A.4 禁止事项

- ❌ 使用 `wp_code` 替代 `wp_id`（业务身份必须绑定运行时实例）
- ❌ 使用 `sheet_name` 作为 stable_sheet_key（可改名）
- ❌ 使用 `target_cell`（Excel `B5` 形态）作为 row_key/field_key（随行号漂移）
- ❌ 把 `preset_version` 拼进 key（导致升级产生重复记录）
- ❌ 把 `custom` 折叠为 `formula_source='custom'` 单一枚举值（丢失 preset+custom 并存态）

---

## B. 公式状态机（Requirement 3.2）

### B.1 冻结的六态

| 状态 | 定义 | 处理规则 |
|------|------|---------|
| `preset` | 使用平台预设公式（当前 `preset_version`） | 可被 custom 覆盖 |
| `custom` | 用户自定义公式（优先于 preset） | 升级 preset 时保留 custom |
| `missing` | key 在 registry 中不存在 | 显式报错，**禁止静默降级**（禁静默 0 / 静默回退） |
| `damaged` | 公式结构解析失败（AST parse error / 语法不合规） | 显示 `damaged` badge，**禁止执行** |
| `stale` | 依赖版本变化（输入端 `addr_id` 定义版本过期 / 依赖公式 `definition_version` 前进） | 标记 `stale` badge，**禁止静默接受** |
| `blocked` | Excel/OO 公式无法保留原字节（解析到非白名单形态 / 外链 / 动态代码） | 显式 `blocked` badge，**存值但拒绝执行** |

### B.2 现状 grep 实证（Requirement 3.2 落地状态）

| 需求态 | 现状字段 | 依据 | 状态 |
|--------|---------|------|------|
| `preset` | `formula_source='preset'` | `wp_formula_service.py` L40-42 | **已实现（分类，非 state）** |
| `custom` | `formula_source='custom'` | 同上 | **已实现（分类，非 state）** |
| `reference` | `formula_source='reference'` + `reference_formula_id` | `workpaper_models.py` L895-900 | 已实现（本 spec 未提及的第三态） |
| `missing` | **不存在** | grep `MISSING|formula_state` = 0 | **UNVERIFIABLE — 机制不存在** |
| `damaged` | **不存在** | grep `DAMAGED` = 0 | **UNVERIFIABLE — 机制不存在** |
| `stale` | `lifecycle_state='stale'` | `workpaper_models.py` L875-879 | **部分实现（仅状态位，无显式 stale 判定与 badge 接线）** |
| `blocked` | **不存在** | grep `BLOCKED` = 0 | **UNVERIFIABLE — 机制不存在** |
| `lifecycle_state` 全集 | `{saved, validated, executing, succeeded, failed, stale, rolled_back}` | `workpaper_models.py` L873-879 文档注释 | 与本 spec 六态**不同集合**，需明确映射 |

**结论**：`lifecycle_state` 的 7 值集与本 spec 的 6 态**不同构**——`succeeded/failed/rolled_back` 是**执行生命周期**态，`damaged/blocked/missing` 是**定义态**。Requirement 3.2 冻结的六态是**定义态**，需与 `lifecycle_state`（执行态）**正交建模**。

### B.3 三态缺失/损坏/阻塞的语义边界

- **`missing`** ≠ **`damaged`**：
  - `missing`：key 从未被写入过 registry（**从未存在**）。UI 必须显示「未预设」而非「错误」。
  - `damaged`：key 存在但表达式 AST 解析失败（**曾存在但已损坏**）。UI 必须显示「公式损坏」badge。
  - 二者混用会导致 UI 无法区分「新页无预设」和「有预设但坏了」两种截然不同的用户动作。
- **`damaged`** ≠ **`blocked`**：
  - `damaged`：表达式**结构**不合规（AST parse error，如语法错、函数名不识别）。
  - `blocked`：表达式**结构合规**但**违反白名单**（外链 / 动态代码 / 未白名单函数）。存值以便审计展示，但**执行路径必须短路**。
- **`stale`** ≠ **`missing`**：
  - `stale`：key 存在且结构合法，但依赖的 `addr_id` / 依赖公式的 `definition_version` 前进过，需重新评估。
  - `missing`：无该 key。
- **禁止静默**：`missing` / `damaged` / `blocked` / `stale` 四态**均禁止**静默降级为 0 或保留旧值继续执行——必须显式暴露给用户。

### B.4 禁止事项

- ❌ 用 0 值 / 空串静默代替 `missing`（会掩盖「本应有预设却漏」的回归）
- ❌ 用 `fail` 状态统一兜底 `damaged` 与 `blocked`（前者是**结构问题**、后者是**白名单问题**，修复路径不同）
- ❌ 用 `lifecycle_state='failed'` 表达「公式损坏」（`failed` 是**执行失败**，`damaged` 是**定义损坏**）
- ❌ 让 `stale` 公式静默继续计算并覆盖结果（Requirement 3.2 明列）

---

## C. F-SHELL v2 白名单（Requirement 3.2）

### C.1 命名与来源

「F-SHELL v2」在本 spec 冻结为**公式表达式层的白名单 DSL 名称**，覆盖**当前 L1 内核**（`formula_engine.py`）+ **函数名集合**（`formula_grammar.py`）+ **函数注册表**（`FunctionRegistry`）。

⚠️ **现状 grep**：`grep -r "F_SHELL|FShell|fshell|f_shell" backend/app/services` = **0 命中**。当前代码中**没有**名为 F-SHELL 的抽象层，只有隐式的白名单机制（`FunctionRegistry` + `FORMULA_FUNCTION_NAMES`）。本 spec 冻结后，F-SHELL v2 是**逻辑命名**，指向以下已存在的白名单基础设施。

### C.2 允许清单（F-SHELL v2 白名单）

#### 允许的命令表达式（FunctionRegistry 已注册）

来源：`formula_engine.py` L486-511 `_REGISTRY.register(...)` 序列。

| 函数名 | 类别 | 语法 | 用途 |
|--------|------|------|------|
| `TB` | 取数 | `TB('科目编码','列名')` | 单科目取值 |
| `SUM_TB` | 取数 | `SUM_TB('起始~结束','列名')` | 范围科目求和 |
| `ROW` | 引用 | `ROW('行次编码')` | 引用其他行次 |
| `SUM_ROW` | 引用 | `SUM_ROW('起始','结束')` | 范围行次求和 |
| `REPORT` | 引用 | `REPORT('行次编码','期间')` | 跨报表引用 |
| `PREV` | 取数 | `PREV('科目','列名')` / `PREV(TB(...))` | 上年同期值 |
| `AUX` | 取数 | `AUX('科目','辅助项','列名')` | 辅助核算取值 |
| `NOTE` | 取数 | `NOTE('章节','字段','列名')` | 附注数据取值 |
| `WP` | 取数 | `WP('wp_code','列名或单元格')` | 底稿数据取值 |
| `ABS` / `ROUND` / `MAX` / `MIN` / `IF` | 数学/逻辑 | — | 内置函数 |

共 **14** 个函数，来源 `formula_grammar.py` L72-75 `FORMULA_FUNCTION_NAMES`。

#### 允许的引用（Reference）格式

- `TB('CODE','COL')` 形式的地址引用（走 ACNR `full_resolve`）
- `ROW('ROW_CODE')` / `SUM_ROW('A','B')` 行次引用
- `WP('WP_CODE','CELL_OR_COL')` 跨底稿引用
- AST 层引用形式：`ASTRowRef(row_code)` / `ASTRangeSum(start_code, end_code)`（`formula_engine.py` L270-290）

#### 允许的参数

- 字面量数字（`ASTNumber`）
- 字面量字符串（`ASTString`，单引号包裹）
- 函数调用返回值（嵌套，如 `PREV(TB('1002','期末余额'))`）

#### 允许的运算符

- 二元：`+` `-` `*` `/`
- 一元：`-`（负号）
- 比较：`>` `<` `>=` `<=` `==` `!=`（用于 `IF` 条件）
- 括号：`(...)`
- 逗号：`,`（函数参数分隔）

### C.3 禁止清单

| 禁止项 | Requirement | 依据 | 现状 |
|--------|------------|------|------|
| `eval()` 或动态代码执行 | 3.2 | L1 内核纯 AST 求值（`_eval_ast`），无 `eval/exec` 调用 | **已实现**（AST 求值 + FunctionRegistry 白名单，`formula_engine.py` L294-484） |
| 外部链接（HTTP/文件路径/URL） | 3.2 | AST 词法分析器只识别上述 14 函数 + 运算符，URL/文件路径会被解析为 IDENT 或非法 | **已实现**（词法层拒绝） |
| `remark` 字段充当公式库 | 3.2 | `WpFormula.remark` 列**不存在**（grep 实证） | **不适用**（无 remark 字段，无需禁止） |
| `field_overrides` 充当公式库 | 3.2 | `field_override_service.py` 存在（`backend/app/services/field_override_service.py`），是**普通值** override 通道，与公式库正交 | **已实现（正交隔离）** |
| 未在白名单的函数 | 3.2 | `_eval_func_node` 未注册函数返 0 并记 trace | **已实现**（`formula_engine.py` L452-456） |
| 裸 `wp_code+sheet+cell` 拼接 | 3.2 引申（Req 11.5） | `resolve_ref` 强制走 ACNR `full_resolve` | **已实现**（`engine.py` L158-200） |

### C.4 F-SHELL v2 与「编辑 schema 禁止 eval 和外链」

Requirement 3.2 后半明列「编辑 schema 禁止 eval 和外链」。冻结的编辑 schema 允许清单（Requirement 3.2 落地）：

- **`schema` 层**（Pydantic/前端 TypeScript 契约）必须拒绝任何含 `eval` / `exec` / `__import__` / `HTTP` / `file://` / 绝对路径的表达式。
- **前端入口**：`audit-platform/frontend/src/components/formula/FormulaBar.vue` + `GtFormulaEditDialog.vue` + `StructureEditor.vue`。
- **后端入口**：`wp_formula_service.save()` 的 AST parse + `FunctionRegistry` 白名单校验。

⚠️ **现状 grep**：`wp_formula_service.py` 只调 `validate_refs_via_acnr` 校验**引用**（跨底稿地址），**不**校验表达式**语法是否合规白名单**。AST 白名单校验只在 `formula_engine.execute` 求值时兜底（`_eval_func_node` 遇未知函数返 0），**编辑/保存入口无独立 schema gate**。此为本 spec Task 3.3 的接线缺口。

### C.5 禁止事项

- ❌ 未在 `FunctionRegistry` 注册的函数进入表达式（含 `eval` / `exec` / 任意 Python 名）
- ❌ URL / 文件路径 / 绝对路径作为字符串参数（`TB('http://...')` 必须拒绝）
- ❌ 用 `remark` / `description` / `field_overrides` 等文本字段承载公式语义
- ❌ 用 Excel 原生公式语法（`SUM(B1:B10)` 等）绕过白名单 DSL

---

## D. OO 模板公式投影（Requirement 3.3）

### D.1 单一公式定义，多投影

OO（OnlyOffice）模板中的公式是**同一公式定义的投影**，不是独立的公式源：

- **权威公式源**：`WpFormula` 表（+ `preset_library` 显式预设库）
- **HTML 投影**：前端 `FormulaBar.vue` / `StructureEditor.vue` 展示 + 编辑
- **OO 投影**：`onlyoffice_callback_service.py` / `oo_to_html.py` / `formula_import_export.py` 双向同步
- **Excel 字节投影**：`excel_rematerialize.py` 的 `assert_ready_for_commit` 门（本 spec R3 与 C1 契约的 `assert_publishable` 前置门同族）

⚠️ 现状 grep：`formula_import_export.py` 存在（`backend/app/services/formula_management/formula_import_export.py`），但未 grep 到独立的「OO 公式投影」服务。OO 模板公式是否**从 WpFormula 反向渲染**到 Excel 字节，未在本 spec 阶段核实——**UNVERIFIABLE，归 C4 逐表验收**。

### D.2 Mask 保护规则

「公式值字段由 mask 保护」冻结为：

- 公式单元格在 HTML / OO / Excel 三种模式下**均显示只读值**（不是让用户手改公式字节）
- 编辑入口是 `FormulaBar.vue` / `GtFormulaEditDialog.vue`（走白名单 DSL），**不是** Excel 单元格双击
- Excel 用户**若绕过前端**直接在 OO 侧改公式字节：必须走 CAS 流程（见 D.3）

### D.3 Excel 公式修改 CAS 流程（Requirement 3.3）

冻结的 CAS 流程（8 步）：

```
1. 接收 incoming formula bytes（来自 OO callback / Excel 导入）
2. 解析（F-SHELL v2 AST parser：`_tokenize` + `_RecursiveDescentParser`）
3. 校验（FunctionRegistry 白名单：14 函数 + 允许运算符）
4. 若解析失败 → state=damaged（不写入，返回 UI 报错）
5. 若校验不通过（非白名单形态）→ state=blocked（存值以便审计展示，拒绝执行）
6. CAS 版本校验（compare `baseVersion` vs `current.version`）
7. 若版本不匹配 → status='conflict', error_code='version_conflict'（拒绝，记录审计日志）
8. 写入公式定义，state=custom
```

### D.4 CAS 机制 grep 实证

**参照实现**：`user_formula_v2.py` L219-246 —— 本 spec 冻结的 CAS 语义与之一致：

```python
if base_version is not None and base_version != current.version:
    staged.append((
        None, None,
        BatchItemResult(
            ..., status="conflict",
            server_version=current.version,
            field_conflicts=[FieldConflict(
                field="baseVersion", base=base_version,
                current=current.version, incoming=base_version,
            )],
            error_code="version_conflict",
            draft_retained=True,
        ),
    ))
    continue
```

`_new_version()` 使用 `sha256(uuid4() + now).hexdigest()[:16]` 生成不可预测版本号（`user_formula_v2.py` L95-96）。

### D.5 `ContentMutationService` 与本 spec CAS 的关系

- **`ContentMutationService.commit`**（C1 契约冻结）：管**内容单元**（cell value）的唯一 commit 边界，走 `content_revision` 单条 SQL CAS（`bump_content_revision`）
- **本 spec CAS**：管**公式定义**（WpFormula row）的版本 CAS，走 `definition_version` / `baseVersion` 比对
- 二者**正交**：一个是内容版本 CAS，一个是定义版本 CAS。禁止合并到同一 CAS 机制。

⚠️ **现状 grep**：`wp_formula_service.py` 的 `save()` 方法**未做 CAS**——只做 upsert 覆盖（`uq_wp_formula_wp_sheet_cell` unique 冲突时覆盖），**未校验 `baseVersion`**。本 spec Task 3.3 需补 CAS 接线。

### D.6 不能保留原字节 → 显式 blocked

Requirement 3.3 明列：「不能保留原字节时显式 blocked，不得静默仅存值」。冻结语义：

- OO/Excel 导入的公式若**无法经 F-SHELL v2 解析为合法 AST**（如含外链、含未白名单函数、含 Excel 独有函数如 `VLOOKUP` / `INDEX` / `MATCH` 等）→ **必须**置 `state=blocked`
- **禁止**把无法解析的公式静默替换为 0 / 空 / 旧值
- **禁止**只在 Excel 端保留原字节、平台端不记录（会丢失审计轨迹）

⚠️ 现状：`formula_engine.py` `_eval_func_node` L452-456 对未注册函数**返 0 并记 trace**——**这违反「不得静默仅存值」**。本 spec 冻结后，`_eval_func_node` 的兜底行为需**改为抛 `FormulaBlockedError`** 或等价信号，由 `wp_formula_service.save()` 与 `oo_to_html.py` 层捕获置 `state=blocked`。

### D.7 禁止事项

- ❌ OO/Excel 侧改公式不解析（原字节直入 registry）
- ❌ 解析失败静默返 0 / 空
- ❌ 校验失败（非白名单）静默存值不标 blocked
- ❌ 版本 CAS 缺失（`wp_formula_service.save()` 现状）
- ❌ `ContentMutationService` 与公式定义 CAS 混用

---

## E. Preset 升级与 Custom 保留规则（Requirement 3.4）

### E.1 冻结的四条规则

| 操作 | 效果 | 语义保证 |
|------|------|---------|
| 升级 `preset_version` | `custom` 字段不受影响，保持 `custom` 状态 | Preset 升级不覆盖 custom（**custom 优先**） |
| 删除 custom | 自动回退到当前 `preset_version`，state=preset | Preset 是 fallback（**preset 保底**） |
| 依赖项版本变化（`addr_id` / 依赖公式 `definition_version` 前进） | 置为 `stale`（**不自动重算**） | Stale 需显式重评，禁静默 |
| Stale 公式被引用 | 显式标记 stale，**禁止静默接受** | 上游 stale 传染，下游不消费 |

### E.2 现状 grep 实证

| 规则 | 现状 | 依据 | 状态 |
|------|------|------|------|
| 升级 preset 保留 custom | `preset_library.build_preset_library` 明列「custom ∪ seed ∪ 收敛源」custom 置于最前，同键去重首个赢 | `preset_library.py` L252-283 | **已实现** |
| 删除 custom 恢复 preset | `upsert_custom_presets` 提供幂等写入口；未显式实现「删除 custom 回退 preset」 | `preset_library.py` L493-537 | **部分实现**（无显式删除→回退路径） |
| 依赖版本变化 → stale | `WpFormula.lifecycle_state='stale'` 存在但**无触发判定** | `workpaper_models.py` L875-879 | **UNVERIFIABLE — 状态位存在但无驱动** |
| Stale 传染不静默 | 平台有 `stale_propagation_engine.py`（`backend/app/services/stale_propagation_engine.py`），但未确认对公式域接线 | 需进一步 grep（**UNVERIFIABLE**） | **UNVERIFIABLE** |

### E.3 Preset/Custom 并存态的关键实现点

Requirement 3.4 的核心是**同一 key 上 preset 与 custom 可并存且互不覆盖**：

- 存储：`WpFormula` 允许同 `(wp_id, sheet_name, target_cell)` 有 1 条记录，但 `formula_source ∈ {preset, custom, reference}` 是**互斥分类**而非并存态 → 现状**无法表达**「同 key 上 preset 与 custom 并存」。
- 冻结方案：`WpFormula` 需新增 `preset_expression` + `preset_version` + `custom_expression` + `is_custom_active` 四列（或等价结构），才能表达 Requirement 3.1 的 `#custom` 后缀并存语义。

⚠️ 本 spec 冻结逻辑契约；DB schema 变更归 Task 3.3 / 3.4 落地。

### E.4 禁止事项

- ❌ Preset 升级覆盖 custom（会丢失用户手工修改）
- ❌ 删除 custom 后不留 preset 追溯（应保留 preset_version 作为 fallback）
- ❌ 依赖版本变化静默重算（stale 需显式确认）
- ❌ Stale 公式静默参与计算（下游不能消费 stale 值）

---

## F. Schema 白名单（Requirement 3.2 补充）

### F.1 编辑 schema 允许清单

公式编辑入口（Pydantic 后端 schema + 前端 TypeScript 契约）允许的字段：

- `expression`（F-SHELL v2 表达式字符串）
- `formula_type` ∈ `{auto_calc, logic_check, reasonability}`
- `target_cell` / `target.addr_id`（写入目标，需经 ACNR resolve）
- `refs`（引用列表，每项为 `{"addr_id": ...}` 或 `{"formula_ref": ...}` 或裸 `formula_ref` 字符串）
- `issue_description` / `hint_text`（logic_check / reasonability 的辅助文本）
- `definition_version` / `baseVersion`（CAS 字段）

### F.2 编辑 schema 禁止清单

| 字段/值 | 禁止原因 | Requirement |
|--------|---------|------------|
| `expression` 含 `eval` / `exec` / `__import__` | 动态代码执行 | 3.2 |
| `expression` 含 URL（`http://` `https://` `file://` `ftp://`） | 外链 | 3.2 |
| `expression` 含绝对路径（`C:\` `/etc/`） | 文件路径 | 3.2 |
| `expression` 含 Excel 原生公式（`SUM(B1:B10)` / `VLOOKUP(...)` / `INDEX(...)`） | 非 F-SHELL v2 白名单 DSL | 3.2 |
| `expression` 含未注册的函数名 | 违反 FunctionRegistry 白名单 | 3.2 |
| `refs` 含裸 `wp_code+sheet+cell` 拼接串 | 违反 ACNR 单一真源 | Req 11.5 |
| `formula_type` 用 `remark` / `field_overrides` 等字段承载 | 混淆值 override 与公式库 | 3.2 |

### F.3 现状 grep

- 后端 Pydantic schema：`backend/app/schemas/formula_runtime.py`（仅含 draft-refresh 相关模型）；`WpFormula` ORM 层无独立 Pydantic schema 做保存前白名单校验。
- 前端 TypeScript：`audit-platform/frontend/src/components/formula/formulaRuntimeContract.ts` 与 `GtFormulaEditDialog.vue` 存在，但编辑入口的 schema 白名单校验点**未在 grep 阶段核实**。

**结论**：**UNVERIFIABLE — schema 白名单校验点未在编辑/保存入口就位**，`formula_engine._eval_func_node` 兜底返 0 违反 D.6「不静默仅存值」，Task 3.3 需补接线。

---

## G. D4 循环现状（Requirement 3 落地矩阵）

### G.1 分母来源

本 spec 治理 36 个逻辑 `wp_code`（design.md §R1 owner 矩阵）。C2 层的公式机制对 36 个 `wp_code` **一视同仁**，无 per-wp 差异。

### G.2 C2 层统一接入状态

| 机制 | 接入状态 | 说明 |
|------|---------|------|
| F-SHELL v2 白名单 DSL | **已实现**（FunctionRegistry + AST 求值） | 14 函数 + AST 解析器 |
| `wp_id` 使用 | **已实现** | `WpFormula.wp_id` |
| Stable `sheet_key` / `row_key` / `field_key` | **UNVERIFIABLE** | 现状用 `sheet_name` + `target_cell`，非稳定 key |
| `preset` + `custom` 并存态 | **UNVERIFIABLE** | 现状 `formula_source` 是互斥枚举 |
| `preset_version` 独立字段 | **UNVERIFIABLE** | 现状 `definition_version` 混同 |
| `missing` / `damaged` / `blocked` 三态 | **UNVERIFIABLE** | `lifecycle_state` 7 值集与本 spec 6 态不同构 |
| `stale` 显式判定与触发 | **UNVERIFIABLE** | 状态位存在，无驱动 |
| Excel 公式 CAS 校验（baseVersion） | **UNVERIFIABLE** | `wp_formula_service.save()` 未做 CAS |
| 「不静默仅存值」兜底 | **UNVERIFIABLE** | `_eval_func_node` 兜底返 0 违反 |
| Schema 编辑入口白名单 gate | **UNVERIFIABLE** | 编辑/保存入口无独立白名单校验点 |
| OO 公式投影双向同步 | **UNVERIFIABLE** | `formula_import_export.py` 存在但双向映射未核实 |
| Preset 升级保留 custom | **已实现**（`preset_library.build_preset_library` 首个赢） |  |
| 删除 custom 恢复 preset | **部分实现** | `upsert_custom_presets` 存在但无显式回退路径 |
| 依赖版本变化 → stale | **UNVERIFIABLE** | 无驱动 |
| Stale 传染不静默 | **UNVERIFIABLE** | 平台 `stale_propagation_engine` 存在但未确认公式域接线 |

### G.3 D4 render schema 存在性

来源：`backend/data/ledger_adapters/wp_render_schema/generated/D4-*.yaml`（2026-05-29 自动生成，标 `_note: 关键字段需人工审核`）。

| wp_code | render schema 存在 | 公式字段声明 | 接入公式引擎 | 状态 |
|---------|:---:|:---:|:---:|------|
| D4-1 | Y | Y（`preserve: true` + cells 列表） | 已渲染，公式引擎接线**待 C4** | **UNVERIFIABLE — 未逐表验收** |
| D4-5 | Y | Y | — | **UNVERIFIABLE** |
| D4-6 | Y | Y | — | **UNVERIFIABLE** |
| D4-12 | Y | Y | — | **UNVERIFIABLE** |
| D4-13 | Y | Y | — | **UNVERIFIABLE** |
| D4-21 | Y | Y | — | **UNVERIFIABLE** |
| D4-22 | Y | Y | — | **UNVERIFIABLE** |
| D4-33 | Y | Y | — | **UNVERIFIABLE** |
| D4（通用） | Y | Y | — | **UNVERIFIABLE** |
| D4-2/3/4/7/8/9/10/11/14/15/16/17/18/19/20/23/24/25/26/27/28/29/30/31/32/34/35/36 | N | — | — | **UNVERIFIABLE — schema 缺失** |

**分母**：36 个 wp_code；**已生成 render schema 的仅 9 个**（25%），其余 27 个 schema 缺失。schema 缺失 = C2 层公式契约**无法逐表落地**，需 C0 补 render schema 生成 + 人工审核。

### G.4 逐 wp_code C2 层状态表

**统一结论**：C2 层机制（F-SHELL v2 白名单 DSL / `preset_library` / `WpFormula` ORM / `formula_runtime` contracts / `ContentMutationService` CAS）在代码中**已存在且被消费**，但**逐 wp_code 接入状态**取决于 render schema 与 runtime coordinator 是否已把该 wp_code 的公式定义送入 registry。

| wp_code | F-SHELL v2 内核 | WpFormula 表 | Render schema | 公式定义入 registry | 状态 |
|---------|:---:|:---:|:---:|:---:|------|
| D4-1 | Y | Y | Y | 待 C4 | **UNVERIFIABLE** |
| D4-2 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-3 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-4 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-5 | Y | Y | Y | 待 C4 | **UNVERIFIABLE** |
| D4-6 | Y | Y | Y | 待 C4 | **UNVERIFIABLE** |
| D4-7 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-8 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-9 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-10 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-11 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-12 | Y | Y | Y | 待 C4 | **UNVERIFIABLE** |
| D4-13 | Y | Y | Y | 待 C4 | **UNVERIFIABLE** |
| D4-14 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-15 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-16 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-17 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-18 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-19 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-20 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-21 | Y | Y | Y | 待 C4 | **UNVERIFIABLE** |
| D4-22 | Y | Y | Y | 待 C4 | **UNVERIFIABLE** |
| D4-23 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-24 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-25 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-26 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-27 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-28 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-29 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-30 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-31 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-32 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-33 | Y | Y | Y | 待 C4 | **UNVERIFIABLE** |
| D4-34 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-35 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |
| D4-36 | Y | Y | N | 待 C4 | **UNVERIFIABLE** |

### G.5 C2 层 UNVERIFIABLE 声明（严格遵守 Requirement 8.1）

以下**不能**在本契约中判定，归 C0 gap register / C4 逐表验收判定：

- 每个 wp_code 是否已在 render schema 中声明公式字段（**仅 9/36 已生成**）
- 每个 wp_code 的公式定义 key 是否已按 R3 冻结的 `wp_id + stable_sheet_key + row_key + field_key + custom` 落地（**当前 DB 三层未落地**）
- 每个 wp_code 的 `preset_version` 是否独立于 `definition_version` 存库（**当前混同**）
- 每个 wp_code 的 `missing/damaged/blocked` 三态是否已显式建模（**当前无该机制**）
- 每个 wp_code 的 `stale` 触发驱动与传染是否已接线（**当前状态位无驱动**）
- 每个 wp_code 的 Excel 公式修改是否经 CAS 校验（**当前 `wp_formula_service.save()` 无 CAS**）
- 每个 wp_code 的 OO 公式投影双向同步是否完成（**待 C4**）
- **UNVERIFIABLE 不计 GREEN**（Requirement 8.1）

### G.6 已实现证据链（grep 实证，2026-06）

- `backend/app/services/formula_engine.py`（L1 内核，1901 行，AST 求值 + FunctionRegistry 14 函数）
- `backend/app/services/formula_grammar.py`（`FORMULA_FUNCTION_NAMES` 14 名 + `FORMULA_ARITY`）
- `backend/app/services/formula_management/engine.py`（三类型分派 auto_calc/logic_check/reasonability）
- `backend/app/services/formula_management/preset_library.py`（custom ∪ seed ∪ 三收敛源，custom 首个赢）
- `backend/app/services/formula_management/formula_import_export.py`（导入导出，OO 投影接线待核实）
- `backend/app/services/formula_runtime/contracts.py`（`CanonicalFormulaTarget` / `FormulaMutation` / `ExecutionPlan` / `ExecutionResult` / `DomainMutationAdapter` Protocol）
- `backend/app/services/wp_formula_service.py`（`WpFormulaService` CRUD，`validate_refs_via_acnr` 校验）
- `backend/app/services/user_formula_v2.py`（batch mutate + per-item CAS + audit commit gate，本 spec CAS 参照实现）
- `backend/app/models/workpaper_models.py` L827-911（`WpFormula` 表 + `uq_wp_formula_wp_sheet_cell` 索引 + V100/V104 扩展列）
- `backend/app/schemas/formula_runtime.py`（`DraftRefreshRequest` / `DraftRefreshResponse` / `RollbackResponse` / `PresetApplication`）
- `backend/data/ledger_adapters/wp_render_schema/generated/D4-{1,5,6,12,13,21,22,33}.yaml` + `D4.yaml`（9 个 render schema）
- `audit-platform/frontend/src/components/formula/formulaRuntimeContract.ts`（前端运行时契约 TS 类型）
- `audit-platform/frontend/src/components/formula/` 下 15+ 组件（`FormulaBar` / `FormulaManagerDialog` / `GtFormulaEditDialog` / `GtFormulaPresetDialog` / `StructureEditor` 等）
- `audit-platform/frontend/src/components/formula/__tests__/formulaPickers.acnr.pbt.test.ts` + `formulaRefGrammarClosure.p26.pbt.test.ts` + `formulaGrammarClosure.contract.test.ts`（PBT 属性测试）

---

## H. 属性测试锁死清单

以下属性测试锁定本契约的每条铁律，任一被破坏 → CI 必红：

| Property | 锁定内容 | 对应 Requirement |
|---------|---------|-----------------|
| P26 | 公式 ref 语法闭合（ACNR grammar_v1） | 3.2 |
| FormulaKey 稳定性 | `wp_id + stable_sheet_key + row_key + field_key` 五元组不随 sheet/row rename 变化 | 3.1 |
| PresetVersion 不入 Key | `preset_version` 变化不改变公式 key | 3.1 |
| Preset 升级保留 Custom | `preset_version` 前进时 custom 字段不变、state 保持 custom | 3.4 |
| Delete Custom 恢复 Preset | 删除 custom 后 state=preset 且自动 fallback 到当前 preset_version | 3.4 |
| Missing vs Damaged 分态 | key 从未写入 → missing；写入但 AST 解析失败 → damaged；二者 UI/错误码可区分 | 3.2 |
| Damaged vs Blocked 分态 | 结构不合规 → damaged；结构合规但违反白名单 → blocked | 3.2 |
| 未白名单函数拒执行 | 未注册函数进表达式 → blocked，**禁止**兜底返 0 | 3.2 |
| URL/文件路径拒收 | 表达式含 URL / 绝对路径 → blocked | 3.2 |
| `eval/exec` 拒收 | 表达式含 `eval` / `exec` / `__import__` → blocked | 3.2 |
| CAS baseVersion 冲突 | `baseVersion != current.version` → status='conflict', error_code='version_conflict' | 3.3 |
| Stale 不静默接受 | 依赖 `definition_version` 前进时置 stale，下游不消费 stale 值 | 3.4 |
| OO 公式投影字节保真 | 无法保留原字节的公式 → blocked，**禁止**静默仅存值 | 3.3 |

---

## I. 禁止事项（冻结）

- ❌ 用 `wp_code` 替代 `wp_id` 作为业务身份（Requirement 3.1）
- ❌ 用可改名 `sheet_name` 作为 `stable_sheet_key`（Requirement 3.1）
- ❌ 用 Excel 单元格地址 `target_cell`（`B5` 形态）作为 `row_key` / `field_key`（Requirement 3.1）
- ❌ 把 `preset_version` 拼进公式 key（Requirement 3.1）
- ❌ 用单一 `formula_source` 枚举值折叠 `preset` + `custom` 并存态（Requirement 3.1）
- ❌ 用 0 / 空串 / 旧值静默兜底 `missing` / `damaged` / `blocked` / `stale` 四态（Requirement 3.2 / 3.3）
- ❌ 允许 `eval` / `exec` / `__import__` / URL / 文件路径 / Excel 原生公式进入表达式（Requirement 3.2）
- ❌ 用 `remark` / `description` / `field_overrides` 等文本字段承载公式语义（Requirement 3.2）
- ❌ OO/Excel 侧改公式不解析不 CAS 直入 registry（Requirement 3.3）
- ❌ 无法保留原字节的公式静默仅存值（Requirement 3.3）
- ❌ `wp_formula_service.save()` 无 `baseVersion` CAS 校验（Requirement 3.3）
- ❌ Preset 升级覆盖 custom（Requirement 3.4）
- ❌ 删除 custom 后不留 preset 追溯（Requirement 3.4）
- ❌ 依赖版本变化静默重算（Requirement 3.4）
- ❌ Stale 公式静默参与计算（Requirement 3.4）
- ❌ `lifecycle_state` 与 `state`（本 spec 六态）混同（**定义态 vs 执行态必须正交**）
- ❌ `ContentMutationService` 与公式定义 CAS 混用（**内容 CAS vs 定义 CAS 必须正交**）

---

## J. 变更控制

- 本契约为 FROZEN。任何修改必须：
  1. 在 requirements.md 增补对应 Requirement
  2. 在 tasks.md 增补对应任务
  3. 通过 code review（≥ 1 位非本 spec owner）
  4. 更新所有引用本契约的测试
- 未评审修改视为破坏 C2 门控，C4 验收不得进入
