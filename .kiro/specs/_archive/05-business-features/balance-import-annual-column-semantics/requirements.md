# Requirements Document

## Introduction

账套导入的余额表（`table_type == "balance"`）在列识别与落库两个环节都没有区分「年度维度」与「月度维度」的列，导致年度审计口径下的数据可能出错：

1. **多个表头映射层都把语义不同的列合并了**（复盘核对真实代码确认有四层，需一并处理）：
   - **（a）双行合并表头点号路径**：`identifier.py::_MERGED_HEADER_MAPPING`（`_match_merged_header`，在 `_match_header` 中**最先命中**）对点号形式的合并表头（如「年初余额.借方金额」「本年累计.借方金额」）映射时，把「年初余额」→ `opening_debit`/`opening_credit`、「本年累计」/「累计发生额」→ `debit_amount`/`credit_amount`——**与期初/本期合并**。这是账套导入截图（双行表头）实际走的路径。
   - **（b）JSON 单行表头别名**：`data/ledger_recognition_rules.json` 顶层 `column_aliases`（经 `identifier._build_header_alias_table`/`_rebuild_aliases` 读取，是识别层 header→field 匹配的**权威真源**）把「年初借方」和「期初借方」都映射到 `opening_debit`、把「年初余额」和「期初余额」都映射到 `opening_balance`；且「本年累计借方/贷方」**没有任何别名**，不被识别（靠 `debit_amount` 的模糊别名"借方"误命中）。
   - **（b2）identifier 内置别名兜底**：`identifier.py::_RAW_HEADER_ALIASES`（Python 内置 dict）**同样合并**了年初/期初（`opening_balance:["年初余额","期初余额"]`、`opening_debit:["年初借方","期初借方"]`）。`_build_header_alias_table` 逻辑为 `source = _RULES.get("column_aliases", _RAW_HEADER_ALIASES)`——JSON 存在时用 JSON、**JSON 缺失/加载失败时回退 `_RAW_HEADER_ALIASES`**。shipped JSON 含 `column_aliases` 故生产走 (b)，但测试用最小 rules_path `reload_rules` 或 JSON 加载失败时会命中 (b2)，为一致性与鲁棒性需同步修正。
   - **（c）参照真源**：`smart_import_engine.py::_MERGED_HEADER_MAP`（legacy/向导转换路径的合并表头映射，用 `_` 下划线分隔而非 `.`）**已正确区分** `year_opening_debit`/`year_debit` 等——**legacy 的表头映射无需改动**，仅作为 (a)(b)(b2) 修正的对齐参照。
   - **（非匹配用）** `table_signatures.{type}.{key_columns,recommended_columns}.*.aliases` 是第三处别名定义，但**不被 header→field 匹配读取**（识别层只读顶层 `column_aliases`）；仅 `.alternatives` 与 `.content_validator` 被 `_get_alternatives`/内容验证器读取。故这些 `.aliases` 对本 spec 是**匹配层惰性数据**，不修改（避免"改了没用"的误判）。

2. **转换器落库时优先用月度列**（复盘核对：v2 `converter.py::convert_balance_rows` 第 353-361/425 行 与 legacy `smart_import_engine.py::convert_balance_rows` 第 1038-1047/1080 行 **两处逻辑完全相同、均有此 bug**）：计算 `trial_balance` 的期初/发生额时——期初**优先取 `opening_debit`/`opening_credit`/`opening_balance`（期初）**，`year_opening_debit`/`year_opening_credit`（年初）仅在期初三列**全空**时才兜底；发生额**只取 `debit_amount`/`credit_amount`（本期）**，`year_debit`/`year_credit`（本年累计）**从不读取、被丢弃**。两处须同步改为年度优先。

**后果**：当 ERP 导出的余额表里「期初 / 本期」是按月的（例如结束期间为 12 期时，这两列是 12 月的期初与 12 月发生额），而「年初 / 本年累计 / 期末」才是全年数时，系统会把 12 月的期初 + 12 月的发生额落进 `trial_balance`，损益类"取发生额"只拿到一个月、滚存（期初 + 借 − 贷 = 期末）也对不上。

**领域口径（审计师确认）**：年度审计中，**年初借/贷、本年累计借/贷、期末借/贷** 是关键列（年度维度的真实数据）；**期初借/贷、本期借/贷** 是按月来的（月度维度）。按年导出的余额表里 **年初 = 期初、本年累计 = 本期**（数值相等），因此"年度优先 + 月度兜底"对整年单期导出无影响、对月度导出是修正。

**本 spec 目标**：让余额表导入按"**年度优先 + 月度兜底（替代组）**"处理——
- 识别层：区分年初/期初、识别本年累计；
- 分类层：年初/本年累计/期末为关键列，期初/本期为推荐，且**不因缺少年度列而误阻断**（月度列经替代组仍可识别并满足要求）；
- 落库层：期初优先取年初、发生额优先取本年累计，月度作兜底。

**零回归红线**：
- 整年单期导出（只有期初/本期，或年初=期初、本年累计=本期）落库到 `trial_balance` 的 `opening_balance`/`debit_amount`/`credit_amount`/`closing_balance` 数值**不变**。
- 只有月度列（期初/本期/期末，无年初/本年累计）的余额表**仍被识别为 balance**、仍能通过关键列校验导入。
- 不改 `trial_balance` 表结构（无新增列）；不改序时账（ledger）识别/转换；不改 `SubmitGate` 之外的下游取数契约。

**范围边界**：
- 本 spec 仅改 `table_type == "balance"`（科目余额表）。**`aux_balance`（辅助余额表）不在范围**——其 `KEY_COLUMNS` 保持现状（opening_balance/closing_balance/debit/credit）；若辅助余额表同有年初/本年累计维度问题，另立 spec。
- 前端第二个导入 UI（项目向导「数据导入」`AccountImportStep.vue`）的分类标签对齐（year_debit/year_credit 计入 key、期初/本期降为 important）为**可选**：其后端走 `smart_import_engine`，落库正确性已由需求 4（转换层 legacy 同步）覆盖；且其硬性 required 只有 `account_code`（不会误阻断），故 UI 标签不对齐**不产生数据错误**，仅为外观/提示一致性。

**范围边界**：
- 仅改 `table_type == "balance"`。**`aux_balance`（辅助余额表）不在范围**——若其同有年初/本年累计问题，另立 spec。
- 平台有两个导入 UI：`ColumnMappingEditor.vue`（LedgerImportPage，其 tier 来自后端，已覆盖）与 `AccountImportStep.vue`（项目向导"数据导入"，走 `smart_import_engine` 后端，落库正确性由转换层改动覆盖）。后者有**独立硬编码的前端分类标签/提示**（`_KEY_FIELDS_BY_TYPE` 等），其硬性 required 仅 `account_code`（不会误阻断），故其前端标签与新语义的一致性对齐列为**可选**（不做也不产生数据错误）。

## Glossary

| 术语 | 含义 |
|------|------|
| 余额表 / balance | 科目余额表，`table_type == "balance"` |
| trial_balance | 落库目标表，列含 `opening_balance` / `debit_amount` / `credit_amount` / `closing_balance`（无年度/月度分列） |
| 年初 (year opening) | 年初余额（借/贷），标准字段 `year_opening_debit` / `year_opening_credit`；年度维度 |
| 期初 (period opening) | 期初余额（借/贷），标准字段 `opening_debit` / `opening_credit` / 净额 `opening_balance`；月度维度 |
| 本年累计 (year cumulative) | 本年累计发生额（借/贷），标准字段 `year_debit` / `year_credit`；年度维度 |
| 本期 (current period) | 本期发生额（借/贷），标准字段 `debit_amount` / `credit_amount`；月度维度 |
| 期末 (closing) | 期末余额（借/贷），标准字段 `closing_debit` / `closing_credit` / 净额 `closing_balance` |
| column_aliases | `ledger_recognition_rules.json` 中「表头文本→标准字段」映射，识别层权威真源（`_rebuild_aliases` 读取） |
| KEY_COLUMNS / RECOMMENDED_COLUMNS | `detection_types.py` 中「标准字段→列分层(key/recommended/extra)」的判定集合，驱动前端「关键列（必填）/次关键列」分区与识别打分 |
| classify_column_tier | 依据 KEY_COLUMNS/RECOMMENDED_COLUMNS 判定单列 tier 的函数 |
| alternatives（替代组） | 某关键列的可替代字段组合，`_get_alternatives`（JSON 优先、`_BUILTIN_ALTERNATIVES` 兜底）；用于识别打分与 key 提升 |
| 组合型替代 | 形如 `closing_debit+closing_credit` 的含 `+` 替代组，需各半齐备才能重构净额 |
| 单字段替代 | 形如 `opening_debit` 的单字段替代组，表示"月度兜底可满足年度要求" |
| _alt_to_key | `identifier.py` 中把替代组成分提升为 key tier 的机制（当前对所有替代组生效，本 spec 收敛为仅组合型生效） |
| 年度优先 + 月度兜底 | 年度列存在时优先用年度列；缺失时用月度列兜底；两者对整年导出相等 |
| convert_balance_rows | `ledger_import/converter.py` 的余额行→trial_balance 行转换器（v2 生效实现） |
| SubmitGate | 提交导入前的关键列硬校验（`submit_gate.py`，`CRITICAL_COLUMNS` 支持替代组"任一满足"） |

## Requirements

### Requirement 1: 列别名区分年度与月度（识别层）

**User Story:** 作为导入识别引擎，我需要把年初/期初/本年累计/本期识别为不同的标准字段，以便区分年度维度与月度维度的数据。

#### Acceptance Criteria

1. WHEN 表头文本为「年初借方」「年初贷方」（及其常见变体如 年初借方余额） THEN 系统 SHALL 映射到 `year_opening_debit` / `year_opening_credit`（不再映射到 `opening_debit` / `opening_credit`）。
2. WHEN 表头文本为「期初借方」「期初贷方」 THEN 系统 SHALL 映射到 `opening_debit` / `opening_credit`。
3. WHEN 表头文本为「本年累计借方」「本年累计贷方」「累计借方」「累计贷方」 THEN 系统 SHALL 映射到 `year_debit` / `year_credit`。
4. WHEN 表头文本为「本期借方」「本期贷方」「借方发生额」「贷方发生额」 THEN 系统 SHALL 映射到 `debit_amount` / `credit_amount`。
5. WHEN 表头为净额列「年初余额」 THEN 系统 SHALL 映射到 `opening_balance`（无独立年度净额字段，年度净额并入 opening_balance 语义，由后续替代组/转换器处理）；WHEN 表头为「期末余额」 THEN 映射到 `closing_balance`。
6. WHEN 一份余额表同时含年初列与期初列 THEN 系统 SHALL 将其识别为**两个不同的标准字段**（不再合并为同一个），使审计师可分别映射或忽略。
7. WHEN 表头为双行合并的点号形式（如「年初余额.借方金额」「本年累计.借方金额」，经 `_match_merged_header`） THEN 系统 SHALL 与单行别名一致地区分年度/月度：年初余额→`year_opening_debit`/`year_opening_credit`、本年累计/累计发生额→`year_debit`/`year_credit`、期初余额→`opening_debit`/`opening_credit`、本期发生额→`debit_amount`/`credit_amount`、期末余额→`closing_debit`/`closing_credit`。
8. WHEN 单独出现净额合并组「年初余额」（`_default`，无借贷子列且无独立年度净额字段） THEN 系统 SHALL 映射到 `opening_balance`（作为已知边界；年度净额单列少见，由转换器年度优先逻辑在有年度分列时优先处理）。
9. WHEN JSON `column_aliases` 缺失或加载失败而回退到 `identifier.py::_RAW_HEADER_ALIASES`（Python 内置兜底） THEN 系统 SHALL 与 (b) 一致地区分年度/月度（`_RAW_HEADER_ALIASES` 的年初别名同步拆出 `year_opening_*`/`year_debit`/`year_credit`，从 `opening_*`/`opening_balance` 移除「年初*」）——保证 fallback 路径与 JSON 路径口径一致，测试用最小 rules_path 或加载失败时不回归旧的合并语义。

### Requirement 2: 关键列分层——年度关键、月度推荐（分类层）

**User Story:** 作为审计师，我需要年初/本年累计/期末被标为关键列（必填、优先映射），期初/本期被标为推荐（可忽略），以聚焦年度维度的真实数据。

#### Acceptance Criteria

1. WHEN 对 balance 表判定列分层 THEN 系统 SHALL 将 `year_opening_debit`、`year_opening_credit`、`year_debit`、`year_credit`、期末（`closing_balance` 或其组合 `closing_debit`+`closing_credit`）、`account_code` 归为 key。
2. WHEN 对 balance 表判定列分层 THEN 系统 SHALL 将 `opening_debit`、`opening_credit`、`opening_balance`、`debit_amount`、`credit_amount` 归为 recommended（不硬阻断）。
3. WHEN 一份余额表同时含年度列与月度列 THEN 系统 SHALL 只把年度列显示为「关键列（必填）」、月度列显示为「次关键列（推荐）」，使审计师可映射年度列、忽略月度列而不被阻断。
4. WHEN 一份余额表**只有**月度列（期初/本期/期末，无年初/本年累计列） THEN 系统 SHALL 仍能通过关键列校验（月度列经替代组满足年度关键列要求），不因缺少年度列而阻断导入。
5. WHEN 提交导入经 `SubmitGate`（`CRITICAL_COLUMNS["balance"]` 硬校验，任一替代组满足即过） THEN 系统 SHALL 使**年度分列文件**（如仅 `account_code`+`year_opening_debit`+`year_opening_credit`，或 `account_code`+`closing_debit`+`closing_credit`，或 `account_code`+`year_debit`+`year_credit`）也能通过——即 `CRITICAL_COLUMNS["balance"]` 须补充年度/分列替代组，避免年度分列表被硬拦。
6. （可选）WHEN 前端第二个导入 UI（`AccountImportStep.vue`）判定 balance 字段分类 THEN 系统 SHOULD 将 `year_debit`/`year_credit` 计入 key 与发生额校验、将 `opening_*`/`debit_amount`/`credit_amount` 归为 important，使标签/提示与后端新语义一致（不改其硬性 required=`account_code`，不影响落库；不做仅标签不一致，无数据风险）。

### Requirement 3: 替代组与 key 提升守卫（识别打分 vs 必填提升分离）

**User Story:** 作为导入引擎，我需要"月度兜底"只影响识别与是否满足要求，而不把月度列强制变成必填，以免同时存在年度与月度列时两者都被要求映射。

#### Acceptance Criteria

1. WHEN 计算表类型识别得分（`_score_table_type`） THEN 系统 SHALL 用替代组扩展"已满足的关键列"：`year_opening_debit` 可由 `opening_debit` 替代满足、`year_opening_credit` 由 `opening_credit`、`year_debit` 由 `debit_amount`、`year_credit` 由 `credit_amount`、`closing_balance` 由 `closing_debit`+`closing_credit`。
2. WHEN 把替代组成分提升为 key tier（`_alt_to_key`） THEN 系统 SHALL **仅对组合型替代（含 `+`，如 `closing_debit`+`closing_credit`）**提升；对单字段替代（月度兜底，如 `opening_debit`）**不提升**。
3. WHEN 一份余额表同时含 `year_opening_debit`（年初借）与 `opening_debit`（期初借） THEN 系统 SHALL NOT 把 `opening_debit` 提升为 key（它保持 recommended、可忽略）。
4. WHEN 净额列缺失而分列齐备（如无 `closing_balance` 但有 `closing_debit`+`closing_credit`） THEN 系统 SHALL 将该两分列提升为 key（组合型替代，重构净额需两半齐备）。

### Requirement 4: 落库取数——年度优先、月度兜底（转换层）

**User Story:** 作为转换器，我需要把 trial_balance 的期初与发生额优先取自年度列、月度列兜底，以确保年度审计拿到全年数据。

#### Acceptance Criteria

1. WHEN `convert_balance_rows` 计算 `opening_balance`/期初借贷 THEN 系统 SHALL 按优先级取数：`year_opening_debit`/`year_opening_credit`（年初）→ 缺失则 `opening_debit`/`opening_credit`（期初）→ 缺失则净额 `opening_balance`。
2. WHEN `convert_balance_rows` 计算发生额 `debit_amount`/`credit_amount`（落库列） THEN 系统 SHALL 按优先级取数：`year_debit`/`year_credit`（本年累计）→ 缺失则 `debit_amount`/`credit_amount`（本期）。
3. WHEN 期末计算 THEN 系统 SHALL 保持现有逻辑（`closing_debit`/`closing_credit` 优先，净额 `closing_balance` 次之）不变。
4. WHEN 一行仅有月度列（无年度列） THEN 系统 SHALL 用月度列落库（兜底），结果与当前实现一致。
5. WHEN 生效实现（`converter.py::convert_balance_rows`）修改后 THEN 系统 SHALL 对 legacy 实现（`smart_import_engine.py::convert_balance_rows`）应用相同取数优先级，避免两条导入路径口径分叉。
6. （可选，legacy 向导路径完整性）WHEN legacy 引擎判定余额表字段完整性（`smart_import_engine._RECOMMENDED_FIELD_GROUPS["balance"]` 的 debit_amount/credit_amount 组、`has_debit`/`has_credit` 校验） THEN 系统 SHOULD 把 `year_debit`/`year_credit` 计入满足条件（现仅认 `debit_amount`/`credit_amount`），使**仅有本年累计、无本期发生额**的年度导出文件在向导路径不被误报"缺发生额"警告（opening 组已含 year_opening_*，此为对齐发生额组；warning 级非阻断，不影响落库）。

### Requirement 5: 零回归与等价性

**User Story:** 作为平台维护者，我需要整年单期导出的落库结果不变、既有导入不被误阻断，以确保变更安全。

#### Acceptance Criteria

1. WHEN 余额表为整年单期导出（年初 = 期初、本年累计 = 本期，或仅有期初/本期列） THEN 落库到 `trial_balance` 的 `opening_balance`/`debit_amount`/`credit_amount`/`closing_balance` SHALL 与变更前逐值相等。
2. WHEN 余额表仅含月度列（无年度列） THEN 系统 SHALL 仍识别为 balance 且通过 `SubmitGate` 关键列校验。
3. WHEN 变更完成 THEN 现有 `backend/tests/ledger_import/` 测试套件 SHALL 全部通过（必要时按新语义更新断言，但不得放宽/跳过用于绕过真实回归）。
4. WHEN 变更完成 THEN 系统 SHALL NOT 改变 `trial_balance` 表结构、序时账识别/转换、以及下游底稿取数字段契约。

### Requirement 6: 正确性属性（可测）

**User Story:** 作为质量保障，我需要以属性测试锁定"年度优先/月度兜底/等价性"，防止回归。

#### Acceptance Criteria

1. WHEN 同一行的年初 = 期初、本年累计 = 本期（整年导出模拟） THEN 转换结果 SHALL 与"仅用月度列"转换结果逐值相等（等价性）。
2. WHEN 同一行年初 ≠ 期初、本年累计 ≠ 本期（月度导出模拟） THEN 转换结果的 `opening_balance` SHALL 由年初派生、发生额 SHALL 由本年累计派生（年度优先）。
3. WHEN 一行仅有月度列 THEN 转换结果 SHALL 由月度列派生（月度兜底）。
4. WHEN 同时含年度列与月度列 THEN 月度列的 `column_tier` SHALL 为 recommended、年度列为 key（分类正确）。
5. WHEN 仅含月度列 THEN 该 balance 表 SHALL 被识别为 balance 且关键列校验通过（不误阻断）。
6. WHEN JSON `column_aliases` 缺失（`reload_rules` 传最小 rules_path）而回退 `_RAW_HEADER_ALIASES` THEN `_match_header("年初借方")` SHALL 返回 `year_opening_debit`、`_match_header("期初借方")` SHALL 返回 `opening_debit`（fallback 路径与 JSON 路径口径一致）。
