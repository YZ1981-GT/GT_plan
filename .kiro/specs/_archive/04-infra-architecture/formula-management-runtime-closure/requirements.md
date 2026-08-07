# Requirements Document

## Introduction

公式管理模块的**定义层与治理层建得完整，运行层在真实库里空转**。2026-08-06 全链只读实证：

| 判据 | 实测 |
|---|---|
| `wp_formula` 表（公式定义唯一持久化表） | **0 行** |
| `parsed_data ? 'user_formulas'`（用户公式落点） | **0 行** |
| `parsed_data ? 'cells'`（`WP()`/`PREV()` 取值源） | **0 行**（492 个有 `parsed_data` 的底稿） |
| `formula_runtime_outbox` / `draft_marker` / `draft_refresh_audit` / `cross_check_results` | **各 0 行** |
| `wp_user_formula` 表 / `WpUserFormula` 模型 | **都不存在** |

⇒ `FormulaRuntimeCoordinator._load_formulas` → `select(WpFormula)` 每次返回空列表并 early-return，
整条 mutation plan 流水线从未有真实数据流经过。公式管理页面能显示内容，是因为它读的是
**另外三条不经 `wp_formula` 的路**：`prefill_formula_mapping.json`（1191 个 cell）、
`report_config`（1222 行）、Tier A `extraction` 块。

本 spec 按「用户可见价值」逐一修复六类实证缺陷，不做整体重构。

### 六类缺陷（逐条实证）

**缺陷 1 —— 端点错配存在于一个零消费方孤儿里（2026-08-06 二次实证已修正定性）**

`useFormulaStatus.ts` 调的两个端点都不存在（`GET /api/projects/{pid}/workpapers/{wpId}/formulas`
与 `POST /api/projects/{pid}/workpapers/{wpId}/prefill` 在 `app/routers/**` 均零命中），
且读 `data?.formulas` 而后端返回键是 **`items`**。

🔴 **但它是零消费方孤儿** —— 全仓 import `useFormulaStatus` 的文件数 = **0**；
它 docstring 声称的三个消费方里 `FormulaTooltip.vue` / `FormulaSourceDrawer.vue` 同样零消费方，
唯一活着的 `FormulaStatusPanel.vue`（消费方 `WorkpaperSidePanel.vue`）**压根不 import 它**
（命中 0），而是自己直接请求**正确端点** `/api/workpapers/${props.wpId}/formulas` 并读 `items`
（17 处），其 docstring 明写「Task 4.1：修正端点错配」= 已由 spec
`d-cycle-four-table-extraction-formulas` 修好。

⇒ 真缺陷有两条，**都不是「修那个孤儿的 URL」**：
① **平台缺「前端公式端点 ⊆ 后端真实路由」的守卫** —— 错配能静默存在正是因为无人钉住；
② `FormulaStatusPanel.vue`（活面板）对 `issue_description` / `hint_text` /
`last_computed_at` / `refs` 命中数**均为 0**，且 `formula_type` 显示**裸英文值**
（`<el-tag>{{ it.formula_type }}</el-tag>`），而 `_formula_to_dict` 已下发前三者。

**注**：`issue_description`/`hint_text` 在**别处**有消费方（`GtFormulaHintPanel.vue` /
`GtFormulaEditDialog.vue` / `FormulaTab.vue` / `useFormulaScopeCatalog.ts` /
`useFormulaIssueHint.ts`），故不是平台级零消费；真正零消费的是 `lifecycle_state`(0) 与
`definition_version`(0)。

**缺陷 2 —— `COLUMN_ALIASES` 缺 4 键，两条求值路径都静默回退期末余额（数字错）**

`COLUMN_ALIASES` 只 8 键。`prefill_formula_mapping.json` 1191 个 cell 里 TB 第二实参分布：

| 列名 | 格数 | 是否注册 |
|---|---|---|
| 期末余额 | 235 | ✅ |
| 期初余额 | 189 | ✅ |
| 本期发生额 | 43 | ✅ |
| **本期借方** | **19** | ❌ |
| **本期贷方** | **17** | ❌ |
| **贷方发生额** | **7** | ❌ |
| **借方发生额** | **5** | ❌ |

合计 **48 格**。而两条求值路径都写
`account_data.get(resolved_col, account_data.get("期末余额", Decimal("0")))`：
`formula_engine.py` **L631**（`_handle_tb`，AST 路径）与 **L936**（`_execute_regex`，降级路径）
⇒ 「本期增加/本期减少/本期计提」列拿到**期末余额**，是数字错不是取不到。

**缺陷 3 —— 用户公式与 Tier A 公式是两套互不可见的存储**

| 路径 | 落点 |
|---|---|
| `wp_user_formulas.py::update_user_formulas` | `working_paper.parsed_data['user_formulas']`（16 处 `parsed_data` 操作，0 处 ORM 写入） |
| `wp_formula.py::save_formula` → `wp_formula_service.save` | `wp_formula` 表 |
| `coordinator._load_formulas`（运行时求值） | **只读 `wp_formula`** |

⇒ 用户在公式管理里编辑保存的公式**永远不会被 coordinator 求值**。两者共用同一入口，
落到两个互不可见的容器。且 `parsed_data['user_formulas']` 与 `wp_formula` 双方**当前都是 0 行**
⇒ 现在收敛零迁移压力，越晚越贵。

**缺陷 4 —— `WP()`/`PREV()` 死链有两份实现，修一份不会修另一份**

`prefill_engine._FORMULA_RESOLVERS['WP']` 读 `parsed_data['cells']`（全库 0 行 ⇒ 死）；
`formula_engine._REGISTRY['WP']` 读 `ctx.wp_data`（由调用方预载）。
死链修复本身已由 spec `prefill-wp-prev-resolution-repair` 承担（本 spec 不重复），
但**两份实现语义一致性无任何守卫**，属本 spec 新增缺口。

**缺陷 5 —— 三类型语义只有一类真正跑起来**

| 类型 | 执行入口 | 实证 |
|---|---|---|
| `auto_calc` | `_exec_auto_calc` / `_batch_exec_auto_calc` | 各定义 1 次，引用只在 `engine.py` 内部；唯一外部路径 `coordinator.execute_batch` 依赖空表 ⇒ 空转 |
| `logic_check` | `execute_report_cross_checks` | 调用链**连通**（见下方勘误）；但结果不落库，`cross_check_results` **0 行** |
| `reasonability` | `_exec_reasonability` | 同 auto_calc；产出字段 `hint_text` 在底稿面板不展示 |

🔴 **勘误（2026-08-06 二次实证）**：立项时记「`run_cross_checks` / `build_cross_check_formulas`
零调用方」**不成立**。逐个 grep `backend/app/**`（排除 tests）实测调用链是通的：

```
formula_logic_check.py::run_report_cross_check   (GET /api/projects/{pid}/formula/report-cross-check)
  └─ logic_check.py::execute_report_cross_checks   (L364)
       └─ logic_check.py::run_cross_checks          (L387 调用，L302 定义)
            └─ logic_check.py::build_cross_check_formulas  (L320 调用，L159 定义)
```

⇒ 真缺口只有一个：**结果不落库**。`logic_check.py` 只 `return CrossCheckResult(...)`
（L341），router 层 `await db.commit()` 但无 INSERT；全后端向 `cross_check_results` 表
写入的只有 `wp_cross_check_service.py`（L610/L622、L660/L672），与 logic_check 链路无关。

🔴 **且 `CrossCheckResult` 是同名双实体**（守卫易误判）：
`models/wp_optimization_models.py` 的 **ORM 模型**（表 `cross_check_results`）与
`services/formula_management/logic_check.py` 的 **`@dataclass` 聚合结果**同名。
按符号名 grep 会把两者混为一谈 —— 判「有无落库」必须看是否 `db.add(<ORM 实例>)`。

**缺陷 6 —— 端点散在 10 个 router，前端 41 个 distinct URL 只 14 个进 apiPaths**

未登记的 **27 个** URL 散在 **18 个**组件/composable 里（模板字符串硬编码），
改一个 prefix 要手工扫全仓 —— 缺陷 1 正是这种形态的直接后果。
按目录分布实测：`components/formula` 11 / `components/workpaper` 10 /
`useFormulaImportExport.ts` 5 / `useFormulaScopeCatalog.ts` 1 / `useFormulaStatus.ts` 1 /
`views/WorkpaperEditor.vue` 1 / `views/composables` 1。

且 `formula.py::/execute` 内部**自己写 SQL** 查 `trial_balance.unadjusted_amount` 全量累加拼
`tb_map`，与 `four_table` 的「语义定位 + 只汇总叶子」口径脱节 ⇒ **父子双算风险**。

**缺陷 7 —— 活代码里有两个后端零命中的 URL，其中一个是有意的前瞻占位（2026-08-06 新查出）**

立项只把坏端点归因到孤儿 `useFormulaStatus.ts`，实测另有两处：

| URL | 所在文件 | 可达性 | 定性 |
|---|---|---|---|
| `POST /api/projects/{pid}/formula/auto-generate` | `FormulaManagerDialog.vue` L657 | **可达**（4 个 views/layouts 消费方） | **有意占位** —— catch 里显式 `if status === 404` → 提示「自动生成公式功能尚未启用，请先使用…」；后端确无等价实现（`auto_generate` 全后端只命中合并/CFS/科目映射三处） |
| `GET /api/projects/{pid}/workpapers/formula-dependencies` | `FormulaDependencyGraph.vue` L40 | **不可达**（0 消费方） | 孤儿；`catch { /* Use empty graph */ }` 静默吞 |

⇒ 「前端 URL ⊆ 后端路由」守卫**必须带显式豁免登记**（否则会把有意的前瞻占位打红，
逼人删掉可用的降级提示）；豁免条目须写明「后端未实现 + 前端有 404 降级路径」两个判据。

## Requirements

### Requirement 1: 端点错配的孤儿清理与平台级存在性守卫

**User Story:** 作为平台维护者，我不希望仓库里躺着一个调用不存在端点的 composable
被下个会话当范式抄走，也不希望这类错配再次静默存在。

#### Acceptance Criteria

1. WHEN 交付 THEN 系统 SHALL 判定 `useFormulaStatus.ts` 的处置为**删除**或**接线**之一，
   不得保留「零消费方 + 调用不存在端点」的现状；
   WHERE 采取删除 THEN `FormulaTooltip.vue` / `FormulaSourceDrawer.vue` 两个同批孤儿
   SHALL 一并判定（各自带处置理由）
2. IF 判定为删除 THEN 删除 SHALL 附实证依据（全仓 import 命中数 = 0，排除
   `components.d.ts` 与 `__tests__`），并确认 `components.d.ts` 无残留自动注册条目
3. WHEN 交付 THEN 系统 SHALL 有**平台级守卫**断言：前端源码中所有公式相关 `/api/` URL
   （去掉 `${...}` 插值后）都能匹配到后端真实注册路由；
   反向自检：注入一个 `projects/{pid}/workpapers/{wpId}/formulas` 形态必打红
4. WHEN 该守卫运行 THEN 它 SHALL 读后端 router 源码抽取真实路径做交叉锁死，
   **不得**依赖手写的期望路径清单（那样会与后端漂移）
5. WHERE 活面板 `FormulaStatusPanel.vue` 已请求正确端点并读 `items`
   THEN 本 spec SHALL NOT 修改其端点与响应键（已由
   `d-cycle-four-table-extraction-formulas` Task 4.1 修好，重复改动会与该 spec 互相回退）
6. WHEN 交付 THEN 守卫 SHALL 断言活面板仍在读 `items` 且仍用无 `projects/` 前缀的端点，
   使该已修状态不可回退

### Requirement 2: 底稿公式面板展示 issue / hint / 计算时间

**User Story:** 作为质量控制复核合伙人，我需要在底稿上直接看到公式的逻辑判断说明与
合理性提示，而不是只看到一个英文类型标签。

**实证前提（2026-08-06）**：活面板是 **`components/workpaper/FormulaStatusPanel.vue`**
（唯一渲染宿主 `WorkpaperSidePanel.vue`；`components/formula/FormulaStatusPanel.vue`
**不存在**）。它的端点与响应键已修对，但 `issue_description` / `hint_text` /
`last_computed_at` / `refs` / `FORMULA_TYPE_LABEL` 命中数**全为 0**，且
`formula_type` 以裸英文值渲染（`<el-tag>{{ it.formula_type }}</el-tag>`）
⇒ 展示缺口是真实活缺陷，与 R1 的孤儿清理无关。

#### Acceptance Criteria

1. WHEN `FormulaStatusPanel` 渲染一条公式 THEN 它 SHALL 展示 `issue_description`（逻辑判断说明）
   与 `hint_text`（合理性提示），二者为空时不渲染该区域
2. WHEN 展示 `formula_type` THEN 它 SHALL 显示中文标签（自动运算 / 逻辑判断 / 合理性提示），
   不得显示裸英文值
3. WHEN `last_computed_at` 存在 THEN 面板 SHALL 展示可读的计算时间；为空时显示「未计算」
4. WHEN `refs` 非空 THEN 面板 SHALL 展示引用数量，并支持展开查看引用列表
5. WHERE 三类型中文标签需要引用 THEN 它 SHALL 复用既有单一真源
   `formulaEngineInventory.FORMULA_TYPE_LABEL`，不得新建第二份标签表
6. WHEN 交付 THEN 该面板 SHALL 有守卫断言四个字段（`issue_description`/`hint_text`/
   `last_computed_at`/`formula_type` 中文标签）在模板中真实被引用

### Requirement 3: `COLUMN_ALIASES` 补齐四键并消除静默回退

**User Story:** 作为审计助理，公式写「本期借方」时应取到借方发生额，
而不是静默拿到期末余额显示在「本期增加」列。

#### Acceptance Criteria

1. WHEN 交付 THEN `COLUMN_ALIASES` SHALL 注册 `本期借方` / `本期贷方` / `借方发生额` /
   `贷方发生额` 四个键，映射到规范列名
2. WHEN `_handle_tb`（L631，AST 路径）取不到解析后的列 THEN 它 SHALL **不再回退期末余额**，
   而是返回 `Decimal("0")` 并向 `trace` 与 `errors` 记录「列缺失」，使调用方可区分
   「该列无数据」与「取到了别的列的值」
3. WHEN `_execute_regex`（L936，降级路径）取不到解析后的列 THEN 它 SHALL 与 R3.2 同口径处理
4. WHEN 交付 THEN 守卫 SHALL 断言两条路径**都**已消除回退；变异检验中「只改 AST 路径」
   SHALL 仍然打红
5. WHEN 交付 THEN `tb_data` 的构造点 SHALL 产出借贷发生额两键（数据源
   `tb_balance.debit_amount` / `credit_amount`），使 48 格公式能真实取到数
6. IF 某构造点无法提供借贷发生额 THEN 该点 SHALL 显式不产出该键（而非产出 0），
   使 R3.2 的「列缺失」语义成立
7. WHEN 交付 THEN 守卫 SHALL 连库/连数据文件断言 `prefill_formula_mapping.json` 中
   TB 第二实参的**全部取值**都已在 `COLUMN_ALIASES` 注册，新增未注册列名即打红

### Requirement 4: 用户公式与 Tier A 公式存储收敛

**User Story:** 作为审计助理，我在公式管理里保存的公式应当被运行时真正求值，
而不是存进一个求值器看不到的地方。

#### Acceptance Criteria

1. WHEN 用户经 `PUT /api/workpapers/{wp_id}/user-formulas` 保存公式 THEN 系统 SHALL 写入
   `wp_formula` 表并置 `formula_source` 标识用户来源（该列已存在）
2. WHEN 读取用户公式 THEN 系统 SHALL 优先读 `wp_formula` 表；
   WHERE `parsed_data['user_formulas']` 存在遗留数据 THEN 系统 SHALL 读时兼容合并
3. WHEN 交付 THEN `coordinator._load_formulas` SHALL 能读到用户保存的公式
   （即两套存储收敛后同一张表）
4. WHEN 收敛后 THEN 既有三个端点（GET / PUT / DELETE user-formulas）的**响应形状** SHALL 不变
   （`cell_key` → formula 的 dict 形态保留），前端零改动
5. WHERE `cell_key` 形如 `sheet!cell_ref` 而 `wp_formula` 用 `(sheet_name, target_cell)` 两列
   THEN 转换 SHALL 由显式纯函数承担并双向可逆，且有 PBT 守卫
6. WHEN 交付 THEN 系统 SHALL 提供只读诊断脚本报告遗留 `parsed_data['user_formulas']` 的规模
   （当前实证 0 行），并由守卫钉死该规模只减不增
7. WHERE 数据迁移涉及既有项目 THEN 迁移 SHALL 幂等且提供回滚路径；
   IF 实证规模为 0 THEN 迁移脚本 SHALL 仍然存在并可空操作运行

### Requirement 5: 两份 `WP()` 实现语义一致性守卫

**User Story:** 作为平台维护者，我不希望修了一个引擎的 `WP()` 而另一个引擎仍是死链，
且没有任何东西提醒我。

#### Acceptance Criteria

1. WHEN 交付 THEN 系统 SHALL 有守卫断言 `prefill_engine` 与 `formula_engine` 两处 `WP`
   实现的**取值语义**一致（同一 `(wp_code, sheet, cell_ref)` 输入产出同一取值路径）
2. IF 两份实现的数据源不同 THEN 守卫 SHALL 要求该差异在源码中显式登记理由，
   未登记即打红
3. WHEN `prefill-wp-prev-resolution-repair` 修复其中一份 THEN 本守卫 SHALL 打红提醒
   同步另一份，而不是静默通过
4. WHERE 死链修复本身属另一 spec THEN 本 spec SHALL 只建立一致性守卫，
   不重复实现取值逻辑

### Requirement 6: 三类型执行链接通与定性

**User Story:** 作为业务合伙人，我需要「逻辑判断」类公式真的跑出勾稽结果，
而不是只有一个从不被调用的函数。

#### Acceptance Criteria

1. WHEN 交付 THEN `logic_check` 的执行结果 SHALL 落库 `cross_check_results`，
   使勾稽结论可查询、可归档
2. WHEN `run_cross_checks` / `build_cross_check_formulas` 仍无调用方 THEN 系统 SHALL
   要么接线要么在源码显式标注弃用理由，**不得**保持「函数在但零调用」的状态
3. WHEN `reasonability` 类公式求值产出 `hint_text` THEN 该提示 SHALL 经 R2 的面板对用户可见
4. WHEN 交付 THEN 守卫 SHALL 断言三类型各自的执行入口**都有非测试调用方**，
   并对「零调用方」情形打红
5. WHERE 某类型的执行依赖 `wp_formula` 有数据 THEN 守卫 SHALL 用替身数据验证执行链可达，
   不得因真实库为空而跳过断言
6. WHEN 交付 THEN 三张 0 行表（`cross_check_results` / `draft_marker` /
   `formula_runtime_outbox`）SHALL 各有明确定性：接线后会填充 / 显式登记为待接线并给出条件

### Requirement 7: 端点收敛与取数口径统一

**User Story:** 作为平台维护者，我改一个公式端点的路径时不应该需要手工扫全仓 20 个文件。

#### Acceptance Criteria

1. WHEN 交付 THEN 前端全部公式相关端点 SHALL 登记在 `apiPaths`，
   组件/composable 内不得再有硬编码的 `/api/...formula...` 模板字符串
2. WHEN 交付 THEN 守卫 SHALL 扫描前端源码断言「无未登记的公式端点硬编码」，
   并对新增硬编码打红
3. WHEN 交付 THEN 守卫 SHALL 交叉锁死「`apiPaths` 中登记的公式端点」⊆
   「后端真实注册的路由」，杜绝缺陷 1 那类端点不存在的错配
4. WHEN `formula.py::/execute` 构建 `tb_map` THEN 它 SHALL 复用 `four_table` 的
   叶子聚合口径，不得对 `trial_balance` 全量累加（父子双算）
5. IF `formula.py::/execute` 的改造影响面无法确定 THEN 该端点 SHALL 至少加上
   「父子双算风险」的显式告警与守卫，并在 Notes 登记待收敛
6. WHERE 端点数量众多 THEN 本 spec SHALL 不合并 router 文件（半径过大），
   只收敛前端引用侧与 apiPaths 登记

### Requirement 8: 缺陷不可回退

**User Story:** 作为平台维护者，我不希望下个会话把静默回退或错误端点改回来。

#### Acceptance Criteria

1. WHEN 运行守卫 THEN 系统 SHALL 断言 `formula_engine.py` 中两处求值路径都不含
   `account_data.get(..., account_data.get("期末余额"` 形态
2. WHEN 运行守卫 THEN 系统 SHALL 断言 `COLUMN_ALIASES` 键数 ≥ 12 且四个新键在册
3. WHEN 运行守卫 THEN 系统 SHALL 断言全仓（排除 `__tests__`）**不存在**请求
   `/api/projects/{...}/workpapers/{...}/formulas` 或 `.../prefill` 的代码，
   且 `useFormulaStatus.ts` / `FormulaTooltip.vue` / `FormulaSourceDrawer.vue`
   三个孤儿文件已删除（防被恢复后再次成为陷阱）
4. WHEN 对修复后的实现做变异（改回静默回退 / 改回错误端点 / 删掉中文标签映射 /
   让用户公式回写 `parsed_data`）THEN 守卫 SHALL 逐条打红
5. WHEN 守卫的判据本身失效（正则不命中 / 常量为空 / 文件路径错）THEN 守卫 SHALL
   通过反向自检打红，而非静默通过
6. WHEN 编写读源码型守卫 THEN 它 SHALL 先剥注释（`stripComments`）并配「剥注释确实生效」
   的自检，防止踩坑说明里的反例被数成真实代码

### Requirement 9: 零回归

**User Story:** 作为平台维护者，我需要确认修复不影响其余公式相关能力。

#### Acceptance Criteria

1. WHEN 修复后 THEN `formula_engine._REGISTRY` 的键集 SHALL 不变（15 个函数）
2. WHEN 修复后 THEN `prefill_engine._FORMULA_RESOLVERS` 的键集 SHALL 不变（9 个 resolver）
3. WHEN 修复后 THEN 使用已注册列名（期末余额 / 期初余额 / 本期发生额 等 8 键）的
   **467 格公式** SHALL 求值结果逐字不变
4. WHEN 修复后 THEN 三个 user-formulas 端点的响应形状 SHALL 不变
5. WHEN 修复后 THEN 既有公式相关测试 SHALL 全部通过，新增失败为 0
6. IF 某既有测试锁定了被修复的错误行为（静默回退 / 错误端点 / `parsed_data` 写入）
   THEN 该测试 SHALL 被诚实改写并在 Notes 说明原因，不得用跳过/放宽断言绕过

### Requirement 10: 真实库验收

**User Story:** 作为现场经理，我需要看到修复后真实项目里公式面板确实有数据、
48 格公式确实取到了借贷发生额。

#### Acceptance Criteria

1. WHEN 交付 THEN 系统 SHALL 提供只读诊断脚本，对真实项目输出：
   公式面板端点返回的 `items` 条数、48 格公式各自的取值与取值列名
2. WHEN 诊断脚本运行 THEN 它 SHALL 区分四态：**取到数** / **列缺失**（该科目无借贷发生额）/
   **科目缺失**（本项目无此科目）/ **公式未登记**，四态混同会让「本项目没数据」与
   「链路仍是死的」不可区分
3. WHEN 诊断脚本对某格取到数 THEN 它 SHALL 同时输出取值路径（科目码 + 解析后列名 + 数据源表），
   不只输出金额
4. WHEN 交付 THEN 浏览器实测 SHALL 覆盖：底稿公式面板可见 issue/hint/计算时间、
   三类型中文标签、用户公式保存后可被读回
5. WHERE 真实库 `wp_formula` 为 0 行 THEN 验收 SHALL 通过「保存一条用户公式 → 读回 → 复原」
   的往返实测证明链路可达，并在完成后按基线**逐字节复原**数据

## Glossary

| 术语 | 含义 |
|------|------|
| 定义层 | 公式的声明与存储：`wp_formula` 表 / `prefill_formula_mapping.json` / `report_config.formula` |
| 运行层 | 公式的求值与落库：`FormulaRuntimeCoordinator` → `execute_batch` → mutation plan → adapter |
| 治理层 | 公式的审计与刷新：`formula_audit_log` / `draft_refresh` / `refresh_scopes` / `formula_runtime_outbox` |
| 空转 | 代码路径存在且被调用，但因数据源为空而 early-return，无任何可观测产出且无告警 |
| 静默回退 | 取不到目标列时返回**别的列**的值（期末余额），使「数字错」伪装成「有数据」 |
| 两套存储 | 用户公式落 `parsed_data['user_formulas']`、Tier A 落 `wp_formula`，运行时只读后者 |
| 三类型 | `auto_calc`（自动运算）/ `logic_check`（逻辑判断）/ `reasonability`（合理性提示） |
| 48 格 | `prefill_formula_mapping.json` 中 TB 第二实参为四个未注册列名的公式格数（19+17+7+5） |
| Tier A / Tier B | Tier A = 可编辑公式（TB/SUM_TB/WP）；Tier B = 四表库自动预填（含 AUX/PREV/序时账） |
| 端点错配 | 前端请求的 URL 在后端不存在，被 `catch` 吞成空结果，四层验证全绿 |
| 父子双算 | 对 `trial_balance` 全量累加时父科目与子科目同时计入，违反「只汇总叶子」铁律 |
