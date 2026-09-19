# Design Document

## Overview

本设计按「六个建议逐一修复」组织，但**执行顺序与需求编号不同** —— 依赖关系决定顺序
（下表 R 号一律指 `requirements.md` 的编号，本文档全篇同）：

```
Wave 1  R1 端点错配 + R2 面板展示（P0，面板恒空）  ← 独立，最高优先
Wave 2  R3 静默回退 + 48 格列名（数字错）          ← 独立
Wave 3  R4 存储双轨收敛                            ← R6 的前置
Wave 4  R6 三类型执行面接线                        ← 依赖 Wave 3（要有活数据）
Wave 5  R5 WP 双实现锁死 · R6.6 三表定性 · R7 端点收敛
Wave 6  R8/R9/R10 守卫 + CI + 真实库验收
```

核心设计原则三条：

1. **零改预设声明**。1191 个 cell 的 `formula` 字面量一个不改；修的是求值侧（列名注册 + `tb_data` 构造）。
2. **静默回退一律改为显式失败**。取不到列不再回退到**别的列**；「已注册但该科目无此列数据」返
   诚实的 0 并记 trace，「列名未注册」记 error。
3. **`wp_formula` 0 行是本 spec 最大的资产**。存储收敛（R4）在 0 行时是纯代码改动，无迁移、无回滚风险；这是必须现在做的理由。

### 🔴 开工前必读：Wave 2 曾落盘后被回退（2026-08-06 实证）

根目录 `tmp_verify_engine_out.txt`（并发会话留下的探针输出）报
`formula_engine.py` len=**60183** / `COLUMN_ALIASES` **15 键** / 存在
`_resolve_tb_column` 三态 helper；而**磁盘真相**是 len=**58166** / **8 键** /
两处静默回退（L631 `_handle_tb`、L936 `_execute_regex`）**仍在**。同一路径同一文件
⇒ Wave 2 的实现曾经存在、现已不在（并发会话互相回退第 4 次实测）。

**推论三条**：

1. 那份被回退的实现里 `COLUMN_ALIASES` 的规范字段名是 **`本期借方` / `本期贷方`**
   （`借方发生额`/`本期借方发生额` 作别名指向它），与已交付共享件一致 —— 本设计据此定稿。
2. 别人的 `tmp_*` 输出只能当线索不能当判据；**判据 = 该输出里的 `file len` 是否等于当下
   `len(read_text())`**，不等即整份作废。
3. 落盘后必须立刻跑守卫 + `git status` 确认，并在 Notes 记录，防再次被回退且无人察觉。

## Architecture

### 现状分层（实测）

```
┌─ 定义层 ────────────────────────────────────────────────┐
│ wp_formula 表(0 行)          ← wp_formula_service.save   │
│ parsed_data['user_formulas'](0 行) ← wp_user_formulas.py │  ← 双轨，互不可见
│ prefill_formula_mapping.json(1191 cells) ← 静态预设       │
│ report_config.formula(1222 行) ← 报表行公式               │
└──────────────────────────────────────────────────────────┘
           │
┌─ 求值层 ──┴───────────────────────────────────────────────┐
│ formula_engine.execute()  ← L1 纯内核，15 个函数            │
│   ├─ _execute_ast    (L631 静默回退)                        │
│   └─ _execute_regex  (L936 静默回退)   ← 两条路径都要改      │
│ prefill_engine._FORMULA_RESOLVERS  ← 9 个 resolver          │
│   └─ WP/PREV 读 parsed_data['cells'](0 行) = 死链            │
└───────────────────────────────────────────────────────────┘
           │
┌─ 编排层 ──┴───────────────────────────────────────────────┐
│ FormulaRuntimeCoordinator.generate_mutation_plan           │
│   └─ _load_formulas → select(WpFormula) → 0 行 → early ret │  ← 整层空转
│ formula_management/engine.execute_batch                    │
│   ├─ _batch_exec_auto_calc                                 │
│   ├─ _batch_exec_logic_check                                │
│   └─ _batch_exec_reasonability                              │
└───────────────────────────────────────────────────────────┘
           │
┌─ 展示层 ──┴───────────────────────────────────────────────┐
│ FormulaManagerDialog(117 KB, 7 tab)  ← 读 report_config 等  │
│ FormulaStatusPanel(workpaper/) ← 活面板，端点已对；缺 4 字段  │
│ useFormulaStatus + FormulaTooltip + FormulaSourceDrawer      │
│   └─ 孤儿三件套（0 消费方，坏端点在死代码里）→ 删            │
│ GtFormulaHintPanel / GtFormulaEditDialog ← 已消费 hint/issue │
│ GtRefreshScopeDialog ← 唯一 draft-refresh 入口              │
└───────────────────────────────────────────────────────────┘
```

### 目标分层

只改三处结构，其余保持：

- **定义层**：`parsed_data['user_formulas']` → `wp_formula(formula_source='user')`，读时兼容旧键
- **求值层**：`COLUMN_ALIASES` 扩 4 键 + 两条路径静默回退改显式失败 + `tb_data` 构造点补发生额键
- **编排层**：`_load_formulas` 之后若为空，不再 early-return 静默，而是记 `scope_failures` 让上层可见

### 已交付资产（不得重造）

| 资产 | 归属 spec | 本 spec 的用法 |
|---|---|---|
| `four_table/occurrence_by_standard_code.py`（`DEBIT_KEY`/`CREDIT_KEY` + 按标准码归集借贷发生额，含叶子聚合 + 最长前缀继承 + fail-open） | `h-cycle-…` Wave 1 | **直接复用**作 `tb_data` 发生额键的数据源，禁另写一份 tb_balance 查询 |
| `backend/tests/test_formula_column_alias_coverage.py`（12 例，已打红 48 格 + 2 处静默回退，2 变异全打红） | 同上 | **本 spec 的 Wave 2 守卫就是它**；只许在其中补断言，禁新建同族守卫文件 |

⇒ 规范字段名**必须**是 `本期借方` / `本期贷方`：该守卫断言
`DEBIT_KEY in set(COLUMN_ALIASES.values())`，而 `DEBIT_KEY = "本期借方"`。
若按早期草案映射到 `借方发生额`，该断言立刻打红。

## Components and Interfaces

### 组件 1：孤儿 `useFormulaStatus` 删除（R1 / Wave 1）

**🔴 立项前提被实证推翻（2026-08-06）**：`useFormulaStatus.ts` 的两个坏端点
**不是活缺陷** —— 该 composable **零消费方**（全仓 `.vue`/`.ts` 排除自身与
`__tests__` 后 import 命中 **0**）。

活面板是 **`components/workpaper/FormulaStatusPanel.vue`**（消费方
`WorkpaperSidePanel.vue`），它：

| 维度 | 实测 |
|---|---|
| 是否 import `useFormulaStatus` | **0 命中**（自己写 `loadFormulas`） |
| 请求端点 | `/api/workpapers/${props.wpId}/formulas` ✅ **已是真实端点** |
| 响应键 | `items`（17 处命中）✅ |
| 其 docstring | 自承「Task 4.1：修正端点错配 …… 此前调不存在的 projects 作用域端点、读 `data.formulas` 恒空」 |

⇒ 端点错配**已由 spec `d-cycle-four-table-extraction-formulas` Task 4.1 在活面板上修好**，
`useFormulaStatus.ts` 是那次修复**漏删的旧实现**（连同 `FormulaTooltip.vue` /
`FormulaSourceDrawer.vue` 两个同族孤儿组件，均 0 消费方）。

**处置 = 删除，不是修 URL**（memory 铁律「死代码立即删除」+「孤儿三选一」）：

- 留着修好 = 把陷阱擦亮：两份「公式状态」实现并存，下个会话仍要判一次哪份是活的
- 判据：TS/Vue 跨文件消费**必须**先 import ⇒ import 路径 0 命中是充分必要条件
- 同族孤儿一并删：`FormulaTooltip.vue` / `FormulaSourceDrawer.vue`
  （`useFormulaStatus` 的 docstring 自称「配合此二者使用」，三者是同一套死实现）

**Wave 1 的真实价值**转移到组件 1b：活面板缺 issue/hint/计算时间展示（该缺陷经实证仍在，
`issue_description` / `hint_text` / `last_computed_at` / `FORMULA_TYPE_LABEL` 在活面板
命中均为 **0**）。

### 组件 1b：活面板展示 issue / hint / 计算时间（R2 / Wave 1）

**文件**：`audit-platform/frontend/src/components/workpaper/FormulaStatusPanel.vue`
（🔴 **不在** `components/formula/`，后者不存在）

后端 `_formula_to_dict` 实测 **17 键**（已核）：

```
{id, project_id, wp_id, sheet_name, target_cell, expression, category,
 description, formula_type, refs, issue_description, hint_text,
 last_computed_at, created_by, created_at, updated_at}
```

活面板的 `RawFormulaItem` 只声明 7 键，**丢弃** `refs`/`issue_description`/`hint_text`/
`last_computed_at`（且 `formula_type` 以裸英文渲染 `<el-tag>{{ it.formula_type }}`）。
改动 = 扩接口 + 在「持久化公式」区块渲染四字段 + 中文标签复用
`composables/formulaEngineInventory.FORMULA_TYPE_LABEL`。

**`lifecycle_state` 不在 17 键内** ⇒ 要展示它必须先补进 `_formula_to_dict`（归 Wave 4）。

### 组件 2：`COLUMN_ALIASES` 扩键 + 静默回退改三态（R3 / Wave 2）

**文件**：`backend/app/services/formula_engine.py`

`COLUMN_ALIASES` 由 8 键扩到 **≥12**，规范字段名取 **`本期借方` / `本期贷方`**
（**不是** `借方发生额` —— 见「已交付资产」，共享件 `DEBIT_KEY="本期借方"` 且其守卫
断言 `DEBIT_KEY ∈ set(COLUMN_ALIASES.values())`）：

```python
COLUMN_ALIASES: dict[str, str] = {
    # ── 余额类（既有 8 键，映射目标逐字不变；Property 22 钉死） ──
    "期末余额": "期末余额", "审定数": "期末余额", "未审数": "期末余额",
    "年初余额": "年初余额", "期初余额": "年初余额",
    "本期发生额": "本期发生额", "RJE调整": "RJE调整", "AJE调整": "AJE调整",
    # ── 发生额类（新增；规范名 = 共享件 DEBIT_KEY/CREDIT_KEY） ──
    "本期借方": "本期借方", "借方发生额": "本期借方",
    "本期贷方": "本期贷方", "贷方发生额": "本期贷方",
}
```

**两处静默回退**（L631 `_handle_tb` / L936 `_execute_regex`）收敛到**同一个** helper
`_resolve_tb_column`（**三态**，不是二态）：

```python
_MISSING = object()

def _resolve_tb_column(
    account_data: dict, col_name: str, *, code: str, trace: list[str],
) -> Decimal | None:
    """按列名取值 —— 三态，禁回退到「期末余额」。

    | 态 | 条件 | 返回 | 记录 |
    |---|---|---|---|
    | 未注册列名 | `col_name ∉ COLUMN_ALIASES` | `None` | trace + 调用方记 errors |
    | 已注册但无数据 | 键不在 `account_data` | `Decimal("0")` | trace「该科目无此列」 |
    | 正常 | — | 值 | — |

    🔴 改造前两处都写 `account_data.get(resolved_col,
       account_data.get("期末余额", Decimal("0")))` ⇒ 「本期增加」列静默拿到
       期末余额（数字错，不是取不到）。全库 48 个公式格中招。
    """
```

**为什么「已注册但无数据」返 0 而不是 None**：`aggregate_occurrence` **有意不产出零值键**
（借贷双方都为 0 的标准码不进结果），此时 0 是**诚实的 0**（该科目本期确实没有发生额），
不该让整格公式失败。只有「列名压根没注册」才是配置错，返 `None` 让调用方记 error。

**`None` 的传播语义**：`FormulaResult.value` 保持 `Decimal`，但 `errors` 非空时
上层（`_evaluate_tier_a_value` 已有此逻辑、`prefill_engine`）不写值。这与既有
「有 eval_errors → value=None」语义一致，属**沿用**不是新造。

**`tb_data` 构造点补键**：实测 20 个文件构造 `{code: {列: 值}}`，但只有 **2 个**是
`TB()` 求值路径的真实输入源。两者都**复用**已交付共享件
`four_table/occurrence_by_standard_code.aggregate_occurrence`（含叶子聚合 + 最长前缀
继承 + fail-open），禁各写一份 `tb_balance` 查询：

| 文件（路径已实证） | 现状键 | 补 |
|---|---|---|
| **`app/routers/wp_template_files.py`**`::_get_tb_data_for_prefill`（🔴 在 `routers/` 不在 `services/`） | 期初余额/期末余额/未审数/审定数 | `本期借方`/`本期贷方` |
| `app/services/formula_management/adjudication_writeback.py` | 6 键 | 同上 |

其余 18 个文件是各循环 render 自己的局部结构，**不在本 spec 范围**（R3.6）。

### 组件 3：用户公式存储收敛（R4 / Wave 3）

**新增** `wp_formula_service.upsert_user_formula(db, *, wp_id, project_id, cell_key, expression, created_by)`：

- `cell_key`（`sheet!cell`）拆成 `sheet_name` + `target_cell`
- `formula_source='user'`、`formula_type='auto_calc'`、`category='用户自定义'`
- 冲突键 `(project_id, wp_id, sheet_name, target_cell)` → 更新 expression + `definition_version += 1`

**`wp_user_formulas.py` 三个端点改造**：

| 端点 | 改造 |
|---|---|
| `GET /user-formulas` | 读 `wp_formula(formula_source='user')`，**并** merge 旧 `parsed_data['user_formulas']`（旧键优先级低）；返回形状不变 |
| `PUT /user-formulas` | 写 `wp_formula`（不再写 `parsed_data`）；空串仍表示删除 |
| `DELETE /user-formulas/{cell_key}` | 删 `wp_formula` 行；旧 `parsed_data` 键若存在也一并清 |

**读时兼容不做数据迁移**（R4.7）：全库 0 行，无存量可迁。兼容分支是为「万一某环境有存量」
留的，且**必须**有一条守卫断言该分支存在（否则下个会话会把它当死代码删掉）。

**`coordinator._load_formulas` 不改查询**（R4.3）：它已经 `select(WpFormula)` 全量、无
`formula_source` 过滤 ⇒ 用户公式落表后自动进入 mutation plan，零改动。

### 组件 4：三类型执行面（R6 / Wave 4）

**`_load_formulas` 空结果可见化**：

```python
if not formulas:
    logger.info(...)                      # 既有
    plan.scope_failures.append({          # 新增
        "addr_id": "", "kind": "no_formulas",
        "detail": f"项目 {project_id} 年度 {year} 无公式定义（wp_formula 空）",
    })
    return plan
```

**`logic_check` 执行入口接线**：`run_cross_checks` / `build_cross_check_formulas` 零调用方。
本 spec **不新建端点**，而是把它们接进已有的 `execute_report_cross_checks`（唯一有调用方的入口，
挂 `GET /api/projects/{pid}/formula/report-cross-check`），并把结果落 `cross_check_results` 表
（现 0 行）。落库 fail-open。

**`lifecycle_state` / `definition_version` 展示**：这两个字段真零消费。加进
`_formula_to_dict` 已有（`lifecycle_state` 实测**不在** `_formula_to_dict` 里 → 需补），
前端 `GtFormulaEditDialog` 加中文标签展示（`draft`/`active`/`archived` → 草稿/生效/已归档）。

### 组件 5：`WP()` 双实现锁死（R5 / Wave 5）

两份实现语义比对表（守卫真源，`backend/app/services/formula_wp_semantics.py`）：

| 维度 | `prefill_engine._resolve_wp_formula` | `formula_engine._handle_wp` |
|---|---|---|
| 实参 | `(wp_code, sheet, cell_ref)` | 同 |
| 数据源 | `parsed_data['cells']`（**0 行 = 死**） | `ctx.wp_data`（调用方预载） |
| 取不到 | `None` | `Decimal('0')` ← **不一致** |

守卫断言：两份实现的**实参个数与位置语义**必须一致；`formula_engine._handle_wp` 取不到时
返 0 的行为**登记为已知差异**（改它会波及 Tier A 求值，属范围外），但必须有登记条目。

### 组件 6：三张 0 行表定性（R6.6 / Wave 5）

| 表 | 判据 | 处置 |
|---|---|---|
| `cross_check_results` | 有 `wp_cross_check_service` / `wp_quality_score_service` 两个读方 | **接线**（组件 4 落库） |
| `draft_marker` | `DraftRefreshOrchestrator` 唯一写方，前端 `GtRefreshScopeDialog` 有入口 | 保留 + 登记「等 Wave 3 后有活数据」 |
| `formula_runtime_outbox` | `formula_runtime/outbox.py` 唯一写方 | 保留 + 登记同上 |

**不删表**（R6.6）：三张表都有生产读/写方，删表会打断已实现的链路。

### 组件 7：端点收敛（R7 / Wave 5）

`apiPaths/accounting.ts` 的 `formula` 常量由 2 项扩到覆盖全部 **27 个未登记 URL**。
**分批**：本 spec 只收敛 `components/formula/**` 与 `composables/useFormula*.ts` 下的
（约 14 个），各循环的 `gN/hN/validate-formulas`（6 个）登记为范围外。

`formula.py::/execute` 的 `tb_map` 父子双算：**只加告警不改口径**（R7.5）。改口径要动
`FormulaRequest`/`FormulaResult` 契约与前端两个已登记端点，风险高于收益。加一条
docstring 说明 + 一条守卫钉住「该实现已知不做叶子聚合」。

## Data Models

### 无 DB 迁移

`wp_formula` 表已有全部所需列（实测 21 列，含 `formula_source`/`lifecycle_state`/
`definition_version`/`definition_hash`）。用户公式收敛复用现有列，**不加列不加表**。

### 新增真源模块

| 文件 | 内容 |
|---|---|
| `backend/app/services/formula_column_aliases.py` | `COLUMN_ALIASES` 提取为独立真源 + `OCCURRENCE_COLUMNS` 集合 + `column_evidence()` 逐键实证 |
| `backend/app/services/formula_wp_semantics.py` | `WP()` 双实现语义对照表 + 已知差异登记 |
| `backend/app/services/formula_runtime_table_status.py` | 三张 0 行表的定性登记（表名 → {判据, 处置, 读写方}） |

`formula_column_aliases.py` 由 `formula_engine.py` re-export 以保持既有 import 路径不变
（`from app.services.formula_engine import COLUMN_ALIASES` 全仓可能已有引用）。

## Error Handling

| 场景 | 现状 | 改为 |
|---|---|---|
| TB 列名未注册 | 静默返期末余额 | `errors` 记录 + `value=None`，上层不写值 |
| `useFormulaStatus` 端点 404 | `catch → []`，显示「暂无公式」 | `loadError` ref → 显示「加载失败」+ 可重试 |
| `_load_formulas` 空 | 静默 early-return | `scope_failures` 记 `no_formulas` |
| `upsert_user_formula` 冲突 | — | 按 `(project,wp,sheet,cell)` 更新，`definition_version += 1` |
| `cross_check_results` 落库失败 | — | fail-open + WARNING（不阻断 GET 返回结果） |
| 旧 `parsed_data['user_formulas']` 解析失败 | — | 跳过该键 + WARNING，不阻断新表读取 |

## Testing Strategy

- **守卫全部带变异检验**：每条 Property 至少一个变异（改回旧行为必须打红），且变异检验按
  「失败测试名集合差集」判定，不看 exit code（memory 已记该铁律）
- **源码级守卫必先 `stripComments()`**：本 spec 的注释里会写出被禁的旧写法
- **连库守卫用单次 `asyncio.run` 取快照**（连接池绑首个事件循环）
- **前端守卫读后端源码交叉锁死**：`COLUMN_ALIASES` 键集、`_formula_to_dict` 字段集
- **零回归判据**：`四表` 域 + `formula` 域全量 pytest，失败集合与改动前逐条比对

## Correctness Properties

### Property 1: 孤儿模块已删且不复活

`composables/useFormulaStatus.ts` / `components/workpaper/FormulaTooltip.vue` /
`components/workpaper/FormulaSourceDrawer.vue` 三个文件 SHALL 不存在；且全仓
SHALL 无 `useFormulaStatus` 的 import。反向自检：把任一文件写回（含其坏 URL）必打红。

**Validates: Requirements 1.1, 1.2**

### Property 2: 全仓无 projects 作用域的 formula 端点

`frontend/src/**` 的非测试源码 SHALL 不含
`/api/projects/${...}/workpapers/${...}/formulas` 与 `.../prefill` 两种形态
（它们在 `app/routers/**` 零命中）。守卫剥注释后扫描；反向自检：注入该形态必打红。

**Validates: Requirements 1.3, 8.3**

### Property 3: 活面板端点在后端真实注册

`FormulaStatusPanel.vue` 请求的每个 `/api/` URL 去掉插值后 SHALL 能在
`backend/app/routers/wp_formula.py` 的路由装饰器中匹配到（GET/PUT `/formulas`、
DELETE `/formulas/{id}`）。守卫读后端源码做交叉锁死。

**Validates: Requirements 1.4**

### Property 4: 活面板读的响应键与后端容器一致

`FormulaStatusPanel.vue` 读取的公式数组键 SHALL 等于后端 `list_formulas` 返回体的
对应键（实测 `items`）；守卫读后端源码抽键名交叉锁死。反向自检：改成 `formulas` 必打红。

**Validates: Requirements 1.4, 1.5**

### Property 5: COLUMN_ALIASES 覆盖全部预设列名

`prefill_formula_mapping.json` 中所有 `TB`/`SUM_TB` 第二实参的 distinct 值 SHALL 全部是
`COLUMN_ALIASES` 的键；反向自检：删掉新增 4 键之一必打红。

**Validates: Requirements 3.1, 3.7**

### Property 6: 两条求值路径都不静默回退

`formula_engine.py` 中 SHALL 不存在 `account_data.get(<任意>, account_data.get("期末余额"`
形态；两处 TB 取值 SHALL 都调用同一个 helper；反向自检：只改一处必打红。

**Validates: Requirements 3.2, 3.3, 3.4, 8.1**

### Property 7: 取不到列必产生 error

对构造好的 `tb_data`（缺 `借方发生额` 键）求值 `TB('X','本期借方')` SHALL 使
`FormulaResult.errors` 非空，且返回值 SHALL 不等于该科目的期末余额。

**Validates: Requirements 3.2, 3.3**

### Property 8: tb_data 构造点产出发生额键

两个真实输入源（`wp_template_files` / `adjudication_writeback`）构造的 `tb_data`
SHALL 含 `借方发生额` 与 `贷方发生额` 键；反向自检：去掉必打红。

**Validates: Requirements 3.5, 3.6**

### Property 9: 用户公式写 wp_formula 不写 parsed_data

`wp_user_formulas.py` 的 PUT/DELETE 端点源码 SHALL 不含 `parsed_data["user_formulas"] =`
赋值形态；GET 端点 SHALL 仍含读兼容分支。

**Validates: Requirements 4.1, 4.2, 8.4**

### Property 10: 用户公式进入 coordinator 视野

`coordinator._load_formulas` 的查询 SHALL 不含 `formula_source` 过滤，使
`formula_source='user'` 的行被载入。

**Validates: Requirements 4.3**

### Property 11: cell_key ↔ (sheet_name, target_cell) 往返无损

对任意合法 `cell_key`（匹配 `_CELL_KEY_RE`），拆分再拼回 SHALL 逐字相等。

**Validates: Requirements 4.5**

### Property 12: 用户公式 upsert 幂等

同一 `(project, wp, sheet, cell)` 连续 upsert 两次 SHALL 只产生一行，且
`definition_version` 递增。

**Validates: Requirements 4.7**

### Property 13: _load_formulas 空结果可见

`generate_mutation_plan` 在无公式时返回的 plan SHALL 含一条 `kind='no_formulas'` 的
`scope_failures` 条目。

**Validates: Requirements 6.4, 6.5**

### Property 14: logic_check 执行入口有生产调用方

`run_cross_checks` 与 `build_cross_check_formulas` SHALL 各有至少一个
`backend/app/**` 非测试调用方。

**Validates: Requirements 6.2, 6.4**

### Property 15: cross_check_results 有写入路径

`backend/app/**` SHALL 存在向 `cross_check_results` 表 INSERT 的生产代码。

**Validates: Requirements 6.1, 6.6**

### Property 16: lifecycle_state 进入响应与展示

`_formula_to_dict` SHALL 含 `lifecycle_state` 键，且前端 SHALL 有该字段的中文标签映射。

**Validates: Requirements 2.2, 6.6**

### Property 17: WP 双实现语义登记完整

`formula_wp_semantics.py` SHALL 登记两份 `WP()` 实现的实参语义与已知差异；
守卫 SHALL 断言两份实现的实参个数一致，且每条已知差异带理由。

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 18: 三张 0 行表定性完整

`formula_runtime_table_status.py` SHALL 为 `cross_check_results` / `draft_marker` /
`formula_runtime_outbox` 三表各登记一条 {判据, 处置, 读写方}，且处置取值域为
`{'接线','保留待接线'}`（不含 `'弃用'` —— 三表都有生产读写方）。

**Validates: Requirements 6.6**

### Property 19: formula 域 URL 登记率只升不降

`components/formula/**` 与 `composables/useFormula*.ts` 下的 `/api/` URL 中，
未登记进 `apiPaths` 的条目数 SHALL 由常量钉死且只许减少。

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 20: formula.py 父子双算已登记

`formula.py::FormulaEngine.execute` 的 docstring 或紧邻注释 SHALL 说明其 `tb_map`
不做叶子聚合；守卫钉住该说明存在。

**Validates: Requirements 7.4, 7.5**

### Property 21: 零回归 — 其余 resolver 与函数集不变

`prefill_engine._FORMULA_RESOLVERS` 键集与 `formula_engine._REGISTRY` 已注册函数名集合
SHALL 与改造前逐字相等（基线常量钉死）。

**Validates: Requirements 9.1, 9.2**

### Property 22: 零回归 — 既有 COLUMN_ALIASES 8 键语义不变

原 8 个键的映射目标 SHALL 逐字不变；反向自检：改任一原键的目标必打红。

**Validates: Requirements 9.3, 8.2**

### Property 23: 诊断脚本区分四态

真实库诊断脚本对每条公式 SHALL 输出四态之一：`ok` / `missing_column` /
`no_data` / `no_formula`，禁合并成「无数据」。

**Validates: Requirements 10.1, 10.2**

### Property 24: 48 格清单可复算

诊断脚本 SHALL 输出未注册列名的公式格清单，其条目数在修复前 SHALL 为 48、
修复后 SHALL 为 0；两个数字都由守卫钉死。

**Validates: Requirements 10.1, 10.3, 3.7**

### Property 25: apiPaths barrel 完整性

`services/apiPaths/formula.ts` 的每个 `export const` SHALL 出现在
`services/apiPaths/index.ts` 的 re-export 清单里。**该 barrel 用具名
re-export（不是 `export *`）** ⇒ 漏登记时 `import { x } from '@/services/apiPaths'`
静默取到 `undefined`，`get_diagnostics` 与 vitest 都查不出。
反向自检：从清单里删掉任一导出名必打红。

**Validates: Requirements 7.1, 7.2**

## Notes

### 范围外（显式登记）

| 项 | 理由 |
|---|---|
| `WP()`/`PREV()` 死链修复 | 已有 spec `prefill-wp-prev-resolution-repair`(0/13)；本 spec 只做语义锁死不改实现 |
| `formula.py::/execute` 改叶子聚合口径 | 要动 `FormulaRequest`/`FormulaResult` 契约与前端两个已登记端点 |
| 18 个循环级 `tb_data` 局部构造点 | 各循环 render 的私有结构，不是 `TB()` 求值输入源 |
| 6 个 `gN/hN/validate-formulas` URL 收敛 | 属各循环 spec |
| `DISCLOSURE_NOTE_FORMULA_ENABLED` 灰度翻默认 | 平台级决策 |
| 跨年度 `PREV()` 数据模型变更 | 已在另一 spec 登记 |

### 实证纠错记录

1. **`issue_description`/`hint_text` 不是零消费**（我首轮结论有误）：实测 3~5 个消费方
   （`GtFormulaHintPanel.vue` / `GtFormulaEditDialog.vue` / `FormulaTab.vue` /
   `useFormulaScopeCatalog.ts` / `useFormulaIssueHint.ts`）。首轮只查了
   `FormulaStatusPanel.vue` 与 `useFormulaStatus.ts` 两个文件就下了「六字段全为 0」
   的结论，属过度概括。**真正零消费的只有 `lifecycle_state` 与 `definition_version`**。
2. **`useFormulaStatus` 端点错配是新发现的 P0**，比「字段没展示」严重得多，故提为 Wave 1。
3. **48 格已逐格确认**：`本期借方` 19 + `本期贷方` 17 + `贷方发生额` 7 + `借方发生额` 5，
   波及 25 个 mapping 块。
4. **`wp_user_formula` 表与 ORM 模型都不存在**：`WpUserFormula(` 全仓 0 命中，
   用户公式只落 `parsed_data`。故 R1 是「建立存储」不是「迁移存储」。

### 待用户裁决（不阻塞 Wave 1/2）

1. **旧 `parsed_data['user_formulas']` 读兼容分支保留多久**？建议永久保留 + 守卫钉死
   （0 行状态下它是纯保险，删了将来某环境有存量就静默丢数据）。
2. **`cross_check_results` 落库要不要带 `year`**？表已有 `year` 列，但
   `execute_report_cross_checks` 的入参需确认能否拿到。
