# Requirements Document

## Introduction

把附注模块的**公式数据**补全，使既有（但目前空转）的表内公式求值链路真正有对象可算，并把附注相关公式纳入公式管理中心的预设公式库，可见、可编、可一键套用。

本 spec 只补**数据 + 生成器 + 预设登记 + 守卫**，不重写附注引擎：`resolve_formula`（sum/report/aging）、`NoteFormulaEvaluator`、`refill_sections`、`NoteFormulaService`（`GET/PUT .../formulas`）与公式管理中心底稿/附注节点在 `disclosure-note-formula-and-report-sync` 已交付，缺的是喂给它们的数据。

### 实证现状（本轮读码 + 数据核实，非推测）

| 事实 | 证据 |
| --- | --- |
| `note_template_bindings.json` 4014 条单元格 binding 中 **`source='formula'` 为 0 条** | 按 source 统计：`manual 3221 / trial_balance 597 / prior_year_note 196`；`valid_sources` 声明支持 `formula` 但生成器从未产出 |
| **567 个 `row_type=total/subtotal` 行的 binding 为空** | 合计/小计行 binding source 组合分布仅 `[]`（合计目前靠生成时 `_backfill_totals` 回填，公式管理里看不到、也无 formula binding 可求值） |
| 3221 条 manual placeholder 带 `todo` | 语义分布：`closing_balance 1030 / opening_balance 631 / prior_year_value 377 / current_year_increase 296 / current_year_decrease 295 …`（生成器 `coverage_note` 自述"本期增减/计提比例/公式列均留 manual placeholder + todo"） |
| `report_note_linkage.json` **零业务条目** | 文件只有 `_schema` / `_rules` / `_example`；其 `_rules` 明写"禁止臆造大量报表行→附注单元格映射（映射错=写错披露），按 note_section 逐节依据源模板/审计口径增量维护" |
| 报表↔附注关系的**权威映射已存在于预设库** | `formula_presets_seed.json` 365 条中 `report:cross_check` 93 条形如 `ABS(ROUND(ROW('BS-002') - NOTE('五、1','合计'),2)) <= 1`（`cross_check_generator` 产出） |
| 附注页自身的预设公式几乎空白 | `page_key` 分布：`report:* 357 / workpaper:* 6 / note:* 仅 2`（五、4、五、5） |

### 🔴 需拍板的方向性纠偏（Decision 1）

「报表→附注同步 `cells_updated=0`」的根因**不是缺 linkage 数据，而是方向倒置**：附注是明细支撑、报表是汇总结果，正确数据流是 底稿/附注 → 报表；把 93 条 cross_check 反向派生成"报表值写进附注合计单元格"会**覆盖明细汇总真值**。

因此本 spec 主张：

- 那 93 条报表↔附注关系补成**附注侧 `logic_check` 预设**（差异校验，出现在公式管理附注节点），**不**据此批量生成 report→note 写值 linkage；
- `report_note_linkage.json` 维持 `_rules`（仅"附注章节确实引用报表行金额"的少数节逐节增量维护），本 spec **不批量填**，`ReportNoteSyncService` 在这些节之外保持 `cells_updated=0` 属**正确行为**而非缺陷。

若不采纳此纠偏（即坚持批量派生写值 linkage），Requirement 4 需改写，且必须先给出"报表值覆盖附注明细合计"的审计口径依据。

## Requirements

### Requirement 1: 合计/小计公式可见化（不改求值真源）

**User Story:** 作为审计师，我希望附注表格的合计/小计算法在公式管理里能看到、能核对，而不是黑箱回填值；但我不接受因此出现"公式算一个数、回填另一个数"的双真源。

#### Acceptance Criteria

> 实现约束（实证）：`refill_sections` 对 `row.is_total` 的行显式 `continue`，合计**始终**由 `_backfill_totals` 计算（生成路径与刷新末尾各一次）。故合计的求值真源保持 `_backfill_totals` 不动，本需求只补**可见性与追溯**。

1. WHEN 某附注表格存在 `row_type` 为 `total`/`subtotal` 的行 AND 该表有 `row_type='data'` 明细行 THEN 系统 SHALL 在预设库为该章节登记合计公式条目（`formula_type='auto_calc'`，表达式为机器可读的同列明细求和），供公式管理中心展示与核对
2. 系统 SHALL NOT 让合计行进入 `resolve_formula` 求值路径（保持 `_backfill_totals` 为唯一计算真源，避免双算/双真源）
3. WHEN 存在层级小计 THEN 登记的求和范围 SHALL 与 `_backfill_totals` 的实际口径一致；无法机械判定层级时 SHALL 跳过该行并登记原因
4. WHEN 某表格无 `row_type=data` 明细行 THEN 系统 SHALL NOT 为其合计行登记公式
5. 守卫 SHALL 断言"登记的合计公式表达式"与 `_backfill_totals` 口径等价（同一批模板下二者求和范围一致）

### Requirement 2: 变动表补会计恒等式公式绑定

**User Story:** 作为审计师，我希望变动表的期末余额是"期初 + 本期增加 − 本期减少"的公式，这样期初或增减一改，期末自动跟上，且算法在公式管理里可查。

#### Acceptance Criteria

> 实现约束（实证）：`refill_sections` 对 `row_type='data'` 行按 `source ∈ {sum,report,aging}` 走 `resolve_formula`（受灰度开关约束），故本需求的公式**真正可求值**。但既有 `_resolve_formula_sum` 只按 `cells` 做**加法求和**，不支持减项 → 恒等式需要引擎支持带符号项（见 Requirement 9）。

1. WHEN 某附注表格的列语义**同时**包含 `opening_balance`、`current_year_increase`、`current_year_decrease`、`closing_balance` THEN 系统 SHALL 为其数据行的 `closing_balance` 产出 `source='sum'` 的 binding（带符号项：期初 `+`、增加 `+`、减少 `−`），并在预设库登记同一公式
2. WHEN 该 `closing_balance` 单元格已被绑定为 `trial_balance` 自动取数 THEN 系统 SHALL NOT 用公式覆盖（试算表实际数优先于恒等式推算）
3. WHEN 缺少上述任一语义列 THEN 系统 SHALL NOT 产出恒等式公式（不推断缺失列的来源）
4. 系统 SHALL NOT 为 `current_year_increase` / `current_year_decrease` 本身产出取数绑定（无权威数据源，保持 manual + todo）
5. WHEN 同一表存在多组分列语义（如 `closing_balance_col2/col3`）THEN 系统 SHALL 仅在该组四列语义齐全时按组产出公式，跨组不混算

### Requirement 3: 附注相关公式纳入公式管理预设库

**User Story:** 作为审计师，我希望在公式管理中心的附注节点看到该章节的全部公式（合计、恒等式、与报表的勾稽），能编辑、能一键套用，而不是只有报表页有预设。

#### Acceptance Criteria

1. WHEN 附注章节存在 Requirement 1/2 产出的公式 THEN 预设库 SHALL 以 `page_key='note:{note_section}'` 登记对应条目，`formula_type='auto_calc'`
2. WHEN `formula_presets_seed.json` 的 `report:cross_check` 存在形如 `ROW(...) 与 NOTE('{章节}', ...)` 的关系 THEN 系统 SHALL 为该附注章节登记对应 `logic_check` 预设（同一关系在报表页与附注页各有入口，表达式与容差口径同源，不得各写一份）
3. WHEN 审计师在公式管理中心打开某附注章节节点 THEN 系统 SHALL 列出该章节预设公式并显示分类（自动计算/逻辑审核）与来源说明
4. 预设条目 SHALL 可被既有"一键刷新/套用预设"路径消费（不新造第二套套用机制）
5. WHEN 预设与项目级用户公式（`GET/PUT .../formulas`）并存 THEN 系统 SHALL 以用户公式优先，预设作为默认（读时收敛，不落库覆盖）

### Requirement 4: 报表→附注 linkage 口径明确化

**User Story:** 作为质量复核人，我需要清楚"报表→附注同步"到底会写哪些单元格，避免报表汇总值覆盖附注明细支撑数据。

#### Acceptance Criteria

1. 系统 SHALL 保持 `report_note_linkage.json` 的 `_rules` 约束：仅覆盖"附注章节确实引用报表行金额"的单元格，逐节增量维护
2. 系统 SHALL NOT 由 `report:cross_check` 预设批量派生 report→note 写值映射
3. WHEN 某附注章节无 linkage 条目且无内嵌 REPORT 单元格绑定 THEN `ReportNoteSyncService` 对该章节 `cells_updated=0` SHALL 被视为正确行为，并在响应/日志中可区分于"失败"
4. 系统 SHALL 提供只读诊断，列出"存在报表↔附注勾稽关系但无写值 linkage"的章节清单，供后续按节人工评估（诊断只呈现，不自动写入）

### Requirement 5: 禁止臆造与可追溯

**User Story:** 作为业务合伙人，我要求每条自动生成的公式都能说明依据，凡依据不足的一律留空，不能让平台自己编披露口径。

#### Acceptance Criteria

1. 每条本 spec 产出的 binding SHALL 携带派生依据标记（如"由 row_type=total 机械派生"/"由列语义四件套派生"）
2. WHEN 依据不足以机械派生 THEN 系统 SHALL 保持 `manual` + `todo` 原状，并计入"待人工标注"统计
3. 系统 SHALL NOT 新增或修改任何附注**披露内容**（行标签、表名、章节号、列头文案）
4. 生成器 SHALL 幂等：同输入重复运行产出逐字节一致，且不改动已有人工标注

### Requirement 6: 灰度与零回归

**User Story:** 作为平台维护者，我要求这批数据补全在灰度关闭时对现有生成结果零影响，开启后也不改变已有正确数值。

#### Acceptance Criteria

1. WHEN `DISCLOSURE_NOTE_FORMULA_ENABLED=False`（默认）THEN 附注生成/刷新结果 SHALL 与本 spec 前逐字节等价
2. WHEN 灰度开启 THEN 合计/期末单元格的数值 SHALL 与灰度关闭时的 `_backfill_totals` 结果一致（公式只是把黑箱回填显式化，不改数）
3. 新增 binding 字段 SHALL 为 additive，既有 `auto`/`manual`/`locked` 单元格行为不变
4. 系统 SHALL NOT 修改 `disclosure_notes` 表结构，SHALL NOT 需要 DB 迁移
5. 既有附注相关后端测试与前端 vitest SHALL 全绿；灰度开关两态各跑一遍

### Requirement 7: 覆盖率与守卫

**User Story:** 作为维护者，我需要一眼看到公式覆盖到什么程度、缺口在哪，并且任何一侧改动漂移能被 CI 拦住。

#### Acceptance Criteria

1. 系统 SHALL 产出覆盖率统计（按 soe/listed 分别统计：total 行公式覆盖数/总数、变动表恒等式覆盖数/候选数、仍为 manual+todo 的语义分布）
2. 契约守卫 SHALL 断言：预设库 `note:*` 条目与 binding 中 `source='formula'` 的章节集合一致（任一侧新增未同步即失败）
3. 契约守卫 SHALL 断言 `report:cross_check` 与附注侧 `logic_check` 预设的表达式/容差同源
4. 守卫 SHALL 以数据文件遍历为源，不硬编码逐条清单

### Requirement 8: 属性化可测

**User Story:** 作为维护者，我希望这批公式数据的正确性由属性测试和一次真实 round-trip 兜住，而不是靠"生成成功"就算过。

#### Acceptance Criteria

1. 每条 Requirement SHALL 有对应可测正确性属性（幂等、人工优先、无双算、开关零回归、坐标/语义合法性、覆盖率单调）
2. 生成器核心判定 SHALL 抽为纯函数以便 PBT（`max_examples=5`）
3. 端到端 SHALL 有一次真实项目 round-trip：灰度开启后生成/刷新某章节 → 合计与恒等式数值正确 → 公式管理附注节点可见对应预设 → 数据恢复原状不留污染

### Requirement 9: sum 求值支持带符号项（引擎最小扩展）

**User Story:** 作为审计师，我需要"期末 = 期初 + 增加 − 减少"这类恒等式能真正被求值，而不是只能表达纯加法。

#### Acceptance Criteria

1. WHEN `sum` binding 的项声明为减项 THEN `_resolve_formula_sum` SHALL 构造带减号的表达式交既有 `formula_parse_utils.evaluate_formula` 求值（不新造求值器）
2. 现有纯 `cells: ['R2C2','R3C2']` 写法 SHALL 逐字节保持原行为（新写法为 additive）
3. WHEN 某项坐标取不到值 THEN 系统 SHALL 跳过该项；全部取不到 → 返回 None（fail-open，不覆盖既有值）
4. 系统 SHALL NOT 扩大 `VALID_SOURCES`（`sum/report/aging` 继续经 `refill_sections` 分支进入 `resolve_formula`，不注册进 `SOURCE_RESOLVERS`）
5. `note_template_bindings.json` 的 `valid_sources` 声明 SHALL 同步纳入本 spec 实际产出的 source 值，并使既有 binding 守卫不误报

## Glossary

| 术语 | 含义 |
| --- | --- |
| Cell_Binding | `note_template_bindings.json` 中 `bindings[章节].tables[].rows[行标签].binding[列语义]` 的单元格取数声明，字段含 `source`/`field`/`account_codes`/`mode` |
| 列语义 | `header_normalize[].semantic`，如 `closing_balance`/`opening_balance`/`current_year_increase`/`prior_year_value` |
| row_type | 行类型：`data`（明细）/`total`（合计）/`subtotal`（小计） |
| Sum_Formula | Requirement 1 产出的合计公式绑定（同表同列明细行求和） |
| Movement_Identity | Requirement 2 产出的变动表恒等式（期末 = 期初 + 增 − 减） |
| Preset_Entry | `formula_presets_seed.json` 的一条预设公式，按 `page_key` 归属页面（本 spec 新增 `note:{章节}`） |
| Linkage_Entry | `report_note_linkage.json` 中一条"报表行 → 附注单元格"写值映射 |
| Cross_Check_Preset | `page_key='report:cross_check'` 的 `logic_check` 预设，表达报表行与附注章节应相等 |
| 灰度开关 | `DISCLOSURE_NOTE_FORMULA_ENABLED`（默认 False），控制表内公式求值与报表→附注同步 |
| 派生依据标记 | 每条自动产出 binding 上标注其机械派生规则，供追溯与人工复核 |
