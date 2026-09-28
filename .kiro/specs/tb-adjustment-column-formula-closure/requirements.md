# 试算平衡表调整列取数收口（tb-adjustment-column-formula-closure）

## 缘起

用户在试算表 →「试算平衡表」→「利润表」tab 点公式管理，发现右侧只列出**未审数**一列的
取数公式，而「审计调整借/贷」「重分类调整借/贷」这四列——同样是**跨表取数**（来源
`adjustments` 表）——在公式管理里完全不可见、不可配。

追查后确认这不是接线漏了，而是**数据模型只支持一列公式** + **调整列口径未收口**两个叠加问题，
并在追查过程中实测发现**三个正在产生错误数字的缺陷**。

## 现状实证（全部现算，2026-09-28）

> 铁律②：计数类现算或标「现算值 + 禁写死」。下列数字均为本轮探针实测，非引用历史快照。

### E1 公式引擎分层与函数清单

| 项 | 实测值 |
|---|---|
| `formula_engine._REGISTRY` 函数数 | **14**：ABS/AUX/IF/MAX/MIN/NOTE/PREV/REPORT/ROUND/ROW/SUM_ROW/SUM_TB/TB/WP |
| 其中含 `ADJ` | **否** |
| `validate_formula("ADJ('6001','aje_net')")` | `['未知函数: ADJ()']` |
| 同一调用对 `TB('6001','本期发生额')` | `[]`（合法） |
| 同一调用对 `NOSUCHFUNC('x','y')` | `['未知函数: NOSUCHFUNC()']` |
| `formula_grammar` 的 `*_PATTERN` 数 | **9**（AUX/NOTE/PREV/REPORT/ROW/SUM_ROW/SUM_TB/TB/WP），**无 ADJ_PATTERN** |
| `prefill_engine._FORMULA_RESOLVERS` 函数数 | **9**：ADJ/AUX/COUNT_LEDGER/LEDGER/LEDGER_DETAIL/NOTE/PREV/TB_AUX/WP |
| 其中含 `ADJ` | **是** |

**双向变异证明**：`TB()` 合法 + `NOSUCHFUNC()` 被拒 ⇒ `ADJ()` 被拒不是扫描器误报，
而是真的未注册（铁律㉒）。

`formula_state._classify` 的白名单**从 `_REGISTRY` 派生**（实测源码 `known_functions =
_REGISTRY.known_function_names()`）⇒ 注册一处即同步生效，**不存在第二份白名单要改**。

### E2 两条求值路径不对称（本 spec 的技术核心）

L1 内核 `execute(formula, ctx)` 是**纯同步函数**，所有取数由 L2 预载进 `FormulaContext`
（字段实测：`tb_data` / `row_cache` / `prior_tb_data` / `note_data` / `wp_data` / `aux_data`）。
但两个域的 L2 实现方式**不同**：

| 域 | L2 实现 | 调整列能否取到数 |
|---|---|---|
| 报表（`report_engine.evaluate_formula`） | **预替换**：`TB`/`SUM_TB` 经 `resolver.resolve_tb` 取数后替换成数值字面量；`PREV`/`NOTE`/`WP`/`AUX` 一律替换成 `"0"`；再调 L1 | **能**（`_COLUMN_MAP` 有 `AJE调整`→`aje_adjustment`） |
| 试算平衡表（`trial_balance_service.summary_with_adjustments`） | **ctx 注入**：`execute_formula(f, tb_map, row_values)` → `FormulaContext.from_simple_map(tb_map)` | **不能** |
| 底稿审定表（`adjudication_writeback`） | **ctx 注入**，手工构造 6 键含 `AJE调整`/`RJE调整` | **能** |

`from_simple_map` 实测只产 **3 键**：
```
tb_data['6001'] = {'期末余额': 1000, '审定数': 1000, '未审数': 1000}
```

因此实测：
```
execute_formula("TB('6001','未审数')",   tb_map={'6001': 1000}) = 1000
execute_formula("TB('6001','AJE调整')", tb_map={'6001': 1000}) = 0      ← 恒 0
execute_formula("TB('6001','RJE调整')", tb_map={'6001': 1000}) = 0      ← 恒 0
```

**变异证明**（铁律⑰：读出 0 必先排除"列名不认"）：手工把 `AJE调整` 填进 ctx 后，
**同一条公式**得 `777`、`errors=[]` ⇒ 恒 0 的根因是**数据没填**，不是列名未注册。

### E3 三份列名映射表（实测**一致**，不漂移）

最初怀疑多源漂移，实测否证——三份都含调整列，只是映射目标不同（各自职责不同，属正交）：

| 映射表 | 键数 | `AJE调整` 映射到 | 职责 |
|---|---|---|---|
| `formula_engine.COLUMN_ALIASES` | 14 | `'AJE调整'`（自身） | ctx.tb_data 的键名归一 |
| `report_engine._COLUMN_MAP` | 8 | `'aje_adjustment'` | ORM 字段名 |
| `address_registry._TB_LEGACY_COLUMNS` | 5 | 在册 | 地址目录列名清单 |

> 🔴 **扫描口径勘误**：本轮第一版探针只扫 `build_trial_balance_entries` **函数体**，
> 得「address_registry 不含 AJE调整」的**假阴**。真相是该清单已被
> `formula-management-runtime-closure` Task 18 改造为「动态派生自 `COLUMN_ALIASES` +
> `_TB_LEGACY_COLUMNS` 模块级常量保底」。既有测试注释描述的是**改造前**状态。
> 教训：扫描"某清单是否含 X"必须先确认清单的**真实载体**（模块常量 vs 函数内字面量）。

### E4 数据模型

| 项 | 实测值 |
|---|---|
| `report_config` 列数 | **18** |
| 其中公式类 | **4**：`formula` / `formula_category` / `formula_description` / `formula_source` |
| **每行公式数** | **1** ← 本问题的数据模型根因 |
| 调整列专属字段 | **0** |
| `trial_balance` 调整列 | `aje_adjustment` / `rje_adjustment`（`Numeric(20,2)`, `server_default 0`, NOT NULL） |
| 当前最高迁移版本 | **V165** ← 🔴 memory.md 记的 V044 已过期，新迁移用 **V166** |

### E5 真库数据（项目 `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` / 2025）

| 项 | 实测值 |
|---|---|
| 该项目 `trial_balance` 行数 | 196 |
| 其中 `aje_adjustment` ≠ 0 | **0**（sum = `0.00`） |
| 全库 `trial_balance` 行数 | 1386 |
| 全库 `aje_adjustment` ≠ 0 / `rje_adjustment` ≠ 0 | **0 / 0** |
| `report_config` 有公式行数 | **761** |
| 其中引用调整列或 `ADJ()` 的 | **0** |
| `adjustments` 唯一 approved 分录 | `1122 应收账款 / 借方 10,000 / origin=manual` |
| 其余分录 | 全部 `draft`（含多条 `origin=workpaper`） |
| `IS-001` 公式（5 个 standard 版本一致） | `SUM_TB('6001~6099','本期发生额')` |

⇒ **持久化列 `trial_balance.aje_adjustment` 是 stale 的**（写入者是 `trial_balance_service`
L415-416 的 recalc 路径，真库未跑过）。所以报表域 `TB(code,'AJE调整')` 虽**能求值**，
取到的却是 **0**，而试算平衡表列显示的是**实时汇总值**——两个数。

## 🔴 本轮新发现的三个缺陷（正在产生错误数字）

`summary_with_adjustments`（`trial_balance_service.py` L663-691）的调整汇总查询，
WHERE 子句实测**只有** `project_id` / `year` / `account_code.in_(...)` / `is_deleted == false`：

| 编号 | 缺陷 | 后果 | 对照（已合规处） |
|---|---|---|---|
| **B1** | 无 `review_status` 过滤 | **draft 分录被算进试算平衡表调整列**；TB 持久化列只算 approved | `adj_net` 默认 `DEFAULT_INCLUDE_STATUSES = {approved}`（ADR-ADJ-003） |
| **B2** | 无 `origin` 过滤 | workpaper 来源被算进来，与审定表 writeback **双计** | 同文件 L364-367 显式 `origin != 'workpaper'`（V124 / ADR-ADJ-002） |
| **B3** | 用主表 `Adjustment.__table__` 的 `account_code`/`debit_amount`/`credit_amount` 遗留冗余列 | 主表单科目字段 ≠ 明细表多行借贷，科目错配 | ADR-ADJ-001 要求走 `adjustment_entries.standard_account_code` + JOIN；同文件 recalc 路径 L344-347 **已改造** |

**B1+B2+B3 合并解释了截图里的错误数字**：真库唯一 approved 的是 `1122 应收账款`
**借方** 10,000，而截图 `IS-001 一、营业收入`（公式 `SUM_TB('6001~6099',...)`，
1122 根本不在此科目区间）的**审计调整贷方**显示 10,000、审定数 −10,000。

### 口径收敛的第四处遗漏

已完成的 `adj-formula-repair-and-approval-gate-wiring` spec 把三套口径收敛到 `adj_net`：

| # | 调用点 | 状态 |
|---|---|---|
| 1 | TB 调整列（recalc） | ✅ 已收敛 |
| 2 | `ADJ()` 底稿呈现 | ✅ 已收敛 |
| 3 | 交叉核对 | ✅ 已收敛 |
| 4 | **`summary_with_adjustments`** | 🔴 **漏了** ← 本 spec 补 |

## 需求

### 需求 1 — 调整列口径收敛到 `adj_net`（第四处）

**用户故事**：作为审计师，我在试算平衡表看到的调整数，必须与底稿审定表、交叉核对、
TB 持久化列**同源同口径**，不能一处含 draft 一处只含 approved。

#### 验收判据

1. WHEN `summary_with_adjustments` 汇总调整 THEN 必须委托 `adjustment_amount_source`
   而非自写 SQL；`Adjustment.__table__` 的 `account_code`/`debit_amount`/`credit_amount`
   三个遗留冗余列在本方法内**引用数为 0**
2. WHEN 存在 `review_status='draft'` 的分录 THEN 该分录**不得**计入调整列（与 ADR-ADJ-003 一致）
3. WHEN 存在 `origin='workpaper'` 的 approved 分录 THEN 该分录**不得**计入试算平衡表调整列
   （与 L364-367 的 V124 防双计约定一致，ADR-ADJ-002）
4. WHEN 同一项目同一年度 THEN 试算平衡表调整列合计 **==** 按 `adj_net` 同参数独立算出的值
   （口径等价，禁"两套算法碰巧结果相同"式验证——必须调同一函数）
5. 🔴 本需求**独立于需求 2~4 可交付**，且必须**最先**交付（它修的是错误数字）

### 需求 2 — `ADJ()` 收敛进统一内核

**用户故事**：作为公式配置者，我在底稿域已经能写 `=ADJ('1521','aje_net')`，
在报表/试算平衡表域也应该能写同一语法，不该有两套词汇表。

#### 验收判据

1. WHEN 在 `formula_engine._REGISTRY` 注册 `ADJ` THEN `validate_formula("ADJ('6001','aje_net')")`
   返回 `[]`；且 `formula_state` 不再把它判为 `BLOCKED`（白名单派生于 `_REGISTRY`，无需二次改动）
2. WHEN L1 内核求值 `ADJ()` THEN 必须从 `FormulaContext` 新增字段读取，**不得**在内核内
   `await` 或触碰 DB（L1 纯同步契约，需求 3.3/3.4 · 属性 Q2 既有约束）
3. WHEN 底稿域既有 `=ADJ('1521','aje_net')` 公式 THEN 行为**零变化**
   （`prefill_engine` 路径不动，只加不改）
4. WHEN `adj_type` 传入非 `aje_net`/`rje_net` 的值 THEN 归一逻辑复用
   `adjustment_amount_source.normalize_adj_type`，**禁**在内核另写一份归一
5. 🔴 既有测试 `test_k1_formula_presets._KNOWN_ADJ_EXEMPT = {"AJE调整","RJE调整"}` 的
   豁免必须**删除**并改为正向断言——该豁免的注释自称"两套并存的既有平台缺口"，
   本需求就是来消除它的。豁免留着 = 假绿。

### 需求 3 — 试算平衡表路径支持调整列取数

**用户故事**：同一条公式 `TB('6001','AJE调整')` 在报表域和试算平衡表域必须得到同一个数。

#### 验收判据

1. WHEN 试算平衡表 L2 构造 `FormulaContext` THEN 必须填充 `AJE调整`/`RJE调整` 键
   （现状 `from_simple_map` 只产 3 键）
2. WHEN 同一 `(project, year, formula)` 分别走报表路径与试算平衡表路径 THEN 两者结果**相等**
3. 🔴 WHEN 持久化列 `trial_balance.aje_adjustment` 与 `adj_net` 实时值不一致 THEN
   必须有**显式可观测信号**（不得静默取其中一个）。本需求**不承诺**自动 recalc，
   但必须让不一致可被发现——真库现状就是持久化列全 0 而实时值非 0
4. WHEN `from_simple_map` 被其他调用方复用 THEN 不得因新增键而改变既有行为
   （新增键只增不改，既有 3 键的值与语义不变）

### 需求 4 — `report_config` 支持调整列公式

**用户故事**：作为审计师，我要能为某一行单独配置"这一行的审计调整从哪来"，
而不是让它寄生在未审数公式的科目范围上。

#### 验收判据

1. WHEN 新增迁移 THEN 版本号为 **V166**（现算最高 V165），且 `V166`/`R166` 配对、
   `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
2. WHEN 某行未配置调整列公式 THEN 行为**完全退回**现有"从未审数公式反解科目码汇总"
   路径（零回归；761 条既有公式不受影响）
3. WHEN 某行配置了调整列公式 THEN 以该公式为准，不再反解科目码
4. WHEN 合计行公式是纯行间引用（如 `ROW('IS-019')-ROW('IS-020')`）THEN 调整列
   现状取不到数（`get_formula_account_codes` 反解不出科目码）——配置了调整列公式后应能取到
5. 三层一致校验：迁移 + ORM `Mapped[]` + service 读写，任一缺失即伪绿

### 需求 5 — 公式管理展示调整列

#### 验收判据

1. WHEN 打开「试算平衡表 > 利润表」THEN 右侧表格能看到该行的调整列公式（不止未审数一列）
2. WHEN 某行调整列未配置 THEN 显式区分「未配置（走默认推导）」与「配置为空」
3. WHEN 统计「N 个公式 / 健康度 X%」THEN 分母口径必须明示是"未审数列"还是"全部列"
   （现状 `37 个公式 / 51%` 只是未审数列，界面未说明 ⇒ 误导）
4. 🔴 禁用百分比阈值式验收（铁律㉓）；例外一律逐条白名单

## 非目标

- **不做**自动 recalc 触发（持久化列刷新时机是另一议题，本 spec 只要求不一致可观测）
- **不做**调整列的 origin/status 口径**按行自定义**（需求 1 先把全局口径统一；按行定制是后续议题）
- **不改** `prefill_engine` 的底稿域 `ADJ()` 行为（只加不改）
- **不改** `report_engine` 的预替换架构（本 spec 不重构 L2 分层）

## 风险

| 风险 | 缓解 |
|---|---|
| 需求 1 会**改变现有显示数字**（draft 不再计入 ⇒ 截图里的 10,000 会消失） | 这是**修正**不是回归。交付时必须在 PR 说明中明确"此变更会使含 draft 分录的项目调整列数字下降"，并给出前后对账脚本 |
| `_KNOWN_ADJ_EXEMPT` 豁免删除可能打红既有测试 | 先跑基线记录红项，用 `git stash` 区分"本轮引入"与"预存失败"（铁律㉔归因纪律） |
| 真库 0 个非零调整列 ⇒ 无法用真实数据验证需求 3 | 需求 1 交付后真库会产出非零值（唯一 approved 的 1122 那笔）；在此之前用 seed 脚本造最小集 |
| 前端全量 `vue-tsc` 在本仓库 OOM（既有环境限制） | 用单区域 tsconfig（先例 `tsconfig._g-single-region.json`）+ 变异证明（铁律㉔） |
