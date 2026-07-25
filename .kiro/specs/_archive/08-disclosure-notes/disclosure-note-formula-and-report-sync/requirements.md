# Requirements Document

## Introduction

本 spec 收敛附注模块"报表 ↔ 附注金额/公式联动"主线上的三处**实测断裂**（附注四条管线逐行核实，非猜测）。四条管线（生成 `disclosure_engine.generate_notes`、底稿→附注 `wp_disclosure_sync_service.sync_from_workpaper`、报表→附注 `ReportNoteSyncService.sync_report_to_notes`、取数器 `note_source_resolvers.dispatch_resolver` 9 个 resolver）均已成熟；本 spec 只解决其中三处断裂：

### 断裂②：报表 → 附注「金额同步」是假的（用户最关心，对应"报表主要项目注释 ↔ 底稿披露表联动"）

`report_note_sync_service.sync_report_to_notes(project_id, year)` 的 docstring 声称"同步报表金额到关联附注章节的合计行、只更新公式驱动单元格、同步后自动执行校验"，但实测代码只做一件事——把 `note.is_stale = False` 清标记，`validation_run = True` 与 `skipped_sections: 0` 均为硬编码假值，**从不把 `FinancialReport.current_period_amount` 写进 note 的任何单元格**。

经查证：全平台**不存在**「报表行 row_code → 附注节 note_section → 合计单元格坐标」的权威映射。`useReportCrossCheck` 只做报表内恒等式（资产=负债+权益等），`useReportMapping` / `ReportLineMappingStep` 是 TB → 报表行映射，都不是报表 → 附注。

调用方：`backend/app/routers/chain_workflow.py`（`sync_notes_from_report` / `update_project_config`）。

### 断裂①：附注表内公式取数未实现（resolve_formula 仍是 stub）

`note_source_resolvers.py`：
- `resolve_formula(binding, ctx)`（line 651）恒 `return None`（注释写 "Sprint 1.5 实现，1.4 stub"）——附注表内单元格若配了公式引用（合计=分项之和 / PRIOR 上年数 / AGING 账龄段 / REPORT 报表行），全部取不到值 → 走 manual placeholder → 审计师手填。
- `resolve_prior_year_note(binding, ctx)` 的 `field="value"` 模式也返 `None`（只能取文本 `field="text"`，取不了上年单元格级金额）。缓存结构 `ctx["_prior_notes_cache"][note_section] = text_content (str)`——目前只存整段文本，无单元格级金额。
- `dispatch_resolver` 的 try/except 保护语义必须保持（任一 resolver 异常不得冒泡阻断整表求值）。

### 断裂⑤：附注校验 preset 加载/解析双重死（框架全绿但生产不产 findings）

`note_validation_engine` + `note_validation_executors`（11 类校验 executor：完整性/账龄衔接/交叉/跨科目/二级明细/LLM 审核等）已实现且测试全绿（`disclosure-note-validation-completion` 已交付，ValidationContext 已装配 report/tb/prior 数据），但生产从不产出 findings，因两处双重死：
- `load_preset_rules` 的 `base_dir` 拼路径缺 `基础数据/` 前缀（preset.md 实际在 `基础数据/附注模版/…`）→ **路径永远找不到**。
- preset.md 里的规则写在 **markdown 表格**（`| 编号 | 校验公式 | … |`）+ 散文，但 `_parse_preset_md` 只匹配 `- [类型] expr` bullet 行（`^-\s*\[` 零匹配）→ **即使修路径也解析不出规则**（双重死）。
- 另有：完整性校验缺 `account_code → note_section` 直接映射源（现只能 section-scope 粗校验，非逐科目"有余额漏披露"）；inline `_check_presets` / `_validation_rules` 是否真被写入 `note.table_data`（`collect_inline_rules_for_note` 读它）需在校验里明确验证。

三者围绕同一主线"附注单元格的自动取数与勾稽"，故合并一次做透。

### 边界（明确排除，不做）

- 不改附注表结构 / 生成模板骨架 / 底稿 → 附注同步的 `manual_override` 守卫与空载荷 no-op（`wp_disclosure_sync_service`）。
- 不做知识库 RAG 接入 AI 叙述填充（那是 `disclosure-note-knowledge-ai-enrichment` spec）。
- 不做 `_sub_table_columns` 列头投影覆盖率补全（那是 `disclosure-table-sync-convergence` spec 的 backlog）。
- 不做底稿 → 附注的双向回流（另议）。
- 不改 report 内部恒等式勾稽（`logic_check` 报表侧）。

### 关键约束 / 铁律（贯穿全部验收准则）

- **审计正确性**：往披露里写金额必须来源可溯（报表数 / resolver / 底稿），映射错=写错披露，故 linkage 须单一权威 + 可测。
- **灰度可回退**：报表 → 附注真同步应有开关，默认行为不破坏现有链路（零回归）。
- **fail-open**：resolver / 公式求值 / preset 加载任一失败都不得阻断附注生成或报表流程。
- **Skip 优于误报**：校验缺数据源时跳过不误报。
- **复用而非另造**：公式求值复用既有引擎（`formula_management/engine` 或 `formula_parse_utils.evaluate_formula`）；单元格保留复用 `note_cell_merge.merge_table_data_preserving_cell_modes`。

## Glossary

| 术语 | 含义 |
|------|------|
| resolve_formula | `note_source_resolvers.py:651` 中按 binding 求值附注表内公式引用的 resolver（当前 stub 恒返 None） |
| resolve_prior_year_note | 取上年附注的 resolver；`field="text"` 取文本（现有），`field="value"` 取单元格金额（当前返 None，本 spec 落地） |
| dispatch_resolver | 按 `binding.source` 路由到对应 resolver 的分发器（含 try/except 保护，语义须保持） |
| Cell_Binding | 附注 `table_data` 单元格上的公式绑定 `{source, field?, …}`（source ∈ sum/aging/report/prior_year_note/manual/…） |
| Formula_Cell | 带 Cell_Binding 的公式驱动单元格（区别于 manual/locked 人工单元格） |
| Cell_Mode | 单元格模式：formula（公式驱动，可被同步覆盖）/ manual（人工录入）/ locked（锁定）；后二者均不覆盖 |
| note_cell_merge | `merge_table_data_preserving_cell_modes` — 合并 table_data 时保留 manual/locked（已存在，复用） |
| Report_Note_Linkage | 「报表行 row_code → 附注节 note_section + 单元格坐标」的单一真源映射（当前全平台缺失） |
| REPORT source | Cell_Binding.source=='report' 时按 row_code 取 `FinancialReport.current_period_amount` |
| PRIOR source | 取上年同坐标附注单元格值（经 resolve_prior_year_note 的 value 模式） |
| AGING source | 取账龄段聚合值（复用既有账龄配置，不新造） |
| SUM source | 对同表指定单元格区间求和（合计=分项之和） |
| _prior_notes_cache | `disclosure_engine._preload_data_for_notes` 预加载的上年附注缓存；现为 `{note_section: text_content}`，本 spec 需支持单元格级反查 |
| ValidationContext | 附注校验上下文，已装配 note_data/report_data/tb_data/prior_note_data（`disclosure-note-validation-completion` Wave0 已交付） |
| load_preset_rules | 从 preset.md 加载附注校验规则（当前 base_dir 缺 `基础数据/` 前缀 + 解析器不认 markdown 表格） |
| _parse_preset_md | 解析 preset.md 为规则的函数（当前只认 `- [类型] expr` bullet，不认 markdown 表格） |
| collect_inline_rules_for_note | 从 `note.table_data` 读 inline `_check_presets` / `_validation_rules` 供校验执行 |
| Skip_On_Missing | 缺数据源时校验 passed=true + details.skipped，不产生误报（审计铁律：漏报优于误报） |
| account↔section 映射 | account_code → note_section，供完整性校验落到科目粒度 |
| DISCLOSURE_NOTE_FORMULA_ENABLED | 表内公式求值 / 报表 → 附注同步的灰度开关（默认关，零回归） |

## Requirements

### Requirement 1: 附注表内公式求值（resolve_formula 落地）

**User Story:** 作为审计助理，我希望附注表内配了公式的单元格（合计 / 上年数 / 账龄 / 报表行）能自动算出并回填，这样我不必手填、也不会因手填算错。

#### Acceptance Criteria

1. WHEN 附注单元格 Cell_Binding.source ∈ {sum, aging, report}，THEN 系统 SHALL 经 `resolve_formula`（或对应 source 的专属 resolver）求值并返回数值。
2. WHEN Cell_Binding 引用同表单元格区间做 SUM，THEN 系统 SHALL 复用既有公式内核（`formula_parse_utils.evaluate_formula` / `formula_management` 引擎）求和，禁止新造求值内核。
3. WHEN Cell_Binding.source=='report' 且带 row_code，THEN 系统 SHALL 从 ctx 提供的报表数据取 `current_period_amount`；IF row_code 不存在，THEN 系统 SHALL 返回 None（不抛错）。
4. IF 求值过程抛异常或依赖数据缺失，THEN 系统 SHALL fail-open 返回 None、记一条 issue，不阻塞其余单元格、不抛出到调用方。
5. WHEN 对整表求值，THEN 系统 SHALL 对相同输入产生确定性结果（幂等，二次求值不变）。
6. WHEN resolve_formula 落地后，THE `dispatch_resolver` 的 try/except 保护语义 SHALL 保持不变（单个 resolver 异常被隔离，不影响其余 binding）。

### Requirement 2: 上年附注单元格级取数（resolve_prior_year_note value 模式）

**User Story:** 作为现场经理，我希望附注的"上年数"列能自动从上年附注对应单元格取值，而不是只能取整段文本或留空。

#### Acceptance Criteria

1. WHEN Cell_Binding.field=='value' 且引用上年附注单元格（section + 坐标），THEN 系统 SHALL 从上年 note 的 `table_data` 按坐标反查金额（`_prior_notes_cache` 需扩为可承载单元格级数据，不破坏既有 text 模式）。
2. IF 上年无该 section 数据 或 坐标不存在，THEN 系统 SHALL 静默返回 None（不抛错），caller 走 manual placeholder。
3. WHEN Cell_Binding.field=='text'，THEN 系统 SHALL 保持既有行为返回文本（不回归）。
4. WHERE 上年 note.table_data 存在多表（`_tables`），THE 系统 SHALL 支持按表索引 + 坐标定位单元格。

### Requirement 3: 报表 → 附注金额真同步

**User Story:** 作为业务合伙人，我希望报表数调整后，附注对应合计 / 公式行能真正跟着更新，而不只是清了个 stale 旗。

#### Acceptance Criteria

1. WHEN 触发报表 → 附注同步（`sync_report_to_notes`），THEN 系统 SHALL 经 Report_Note_Linkage 把报表行金额写入关联附注节的 Formula_Cell（公式驱动 / 合计单元格）。
2. IF 目标单元格 Cell_Mode ∈ {manual, locked}，THEN 系统 SHALL 保留不覆盖（复用 `note_cell_merge.merge_table_data_preserving_cell_modes` 语义）。
3. WHEN 同步完成，THEN 系统 SHALL 返回真实统计 `{synced_sections, skipped_sections, cells_updated, validation_run}`，其中 `validation_run` 反映实际是否跑了校验、`skipped_sections` 反映实际跳过数，均不得硬编码。
4. IF 某报表行无 Report_Note_Linkage 目标，THEN 系统 SHALL 跳过并计入 `skipped_sections`（可审计，不静默漏、不写错单元格）。
5. WHEN 同步后，THEN 系统 SHALL 触发附注校验（Req6）并按实际结果清除 stale 标记。
6. WHEN 报表行金额发生变更，THE 系统 SHALL 保持既有的关联附注节 stale 标记行为（`mark_notes_stale`）不回归。
7. THE 报表 → 附注同步 SHALL 幂等（相同报表数二次同步不产生额外副作用）、fail-open（异常不阻断 `chain_workflow` 流程），且对现有 `sync_from_workpaper` 链路零回归。

### Requirement 4: 报表 ↔ 附注 linkage 单一真源

**User Story:** 作为质控复核人，我希望"哪个报表行对应哪个附注单元格"只有一处权威定义，避免多处硬编码漂移、避免把金额写错格子。

#### Acceptance Criteria

1. THE 系统 SHALL 有唯一的 Report_Note_Linkage 真源：附注单元格自带的 REPORT Cell_Binding（row_code）优先；对未内嵌绑定的章节，回退 data-driven `report_note_linkage` 配置（`{report_row_code → [{note_section, cell}]}`）。
2. IF 同一报表行在两处都有目标定义，THEN 系统 SHALL 以 Cell_Binding 为准（就地绑定优先于集中配置）。
3. IF linkage 配置缺失或坐标非法，THEN 系统 SHALL 跳过该项并记录（不抛错、不写入非目标单元格）。
4. THE 报表 → 附注同步（Req3）与表内 REPORT 公式求值（Req1.3）SHALL 共用同一 linkage 语义，不得各自维护一套映射。

### Requirement 5: 附注校验 preset 加载 / 解析修复

**User Story:** 作为审计助理，我希望附注校验规则能真正被加载和解析，这样校验能跑出结果而不是永远空。

#### Acceptance Criteria

1. WHEN 加载附注校验 preset，THEN 系统 SHALL 从正确路径解析（补齐 `基础数据/` 前缀，或改用可靠的 base_dir 解析），使 preset.md 文件能被找到。
2. WHEN preset.md 规则以 markdown 表格形式书写（`| 编号 | 校验公式 | … |`），THEN 系统 SHALL 正确解析为可执行规则（不仅识别 `- [类型] expr` bullet 行）。
3. IF preset 文件不存在或解析失败，THEN 系统 SHALL fail-open 返回空规则集 + 记 warning（不抛错、不阻塞生成 / 同步）。
4. IF 同一规则同时以 bullet 与表格两种格式存在，THEN 系统 SHALL 去重（不重复执行同一校验）。

### Requirement 6: 校验规则真正装配并产出 findings

**User Story:** 作为质控复核人，我希望附注生成 / 同步后能自动跑出勾稽问题清单（合计不平、附注 ↔ 报表不符、变动表期初+增-减≠期末等），而不是框架空转。

#### Acceptance Criteria

1. WHEN 生成 / 同步附注后运行校验，THEN 系统 SHALL 把 preset 规则 + inline `_check_presets` / `_validation_rules` 装配进 `note.table_data`，供 `collect_inline_rules_for_note` 与 executor 执行。
2. WHEN 校验执行，THEN 系统 SHALL 产出真实 findings，至少覆盖：合计=分项之和、附注合计 ↔ 报表行、附注内部变动表（期初+增-减=期末）、分类小计=合计。
3. IF 某校验所依赖的数据源缺失（报表未生成 / 上年无数据 / 科目映射缺），THEN 系统 SHALL Skip_On_Missing（passed=true + details.skipped），不得误报 false fail。
4. THE 校验 SHALL 只读不写（不修改 note.table_data 单元格值），LLM 类校验 SHALL fail-open（LLM 不可用时跳过不阻断）。
5. WHEN 校验产出 findings，THE 前端校验面板（DisclosureEditor）SHALL 能消费展示（既有面板，不重建）。

### Requirement 7: 完整性校验 account↔section 映射

**User Story:** 作为业务合伙人，我希望"有余额但未披露"能落到具体科目粒度校验，而不是只做章节非空的粗检。

#### Acceptance Criteria

1. THE 系统 SHALL 提供 account_code → note_section 映射来源（复用 ACNR NOTE 域 / 披露模板 account_name，不新造孤立真源）。
2. WHEN 某科目有 TB 余额但对应 note_section 无披露行，THEN 完整性校验 SHALL 产出 finding（科目粒度）。
3. IF account↔section 映射缺失，THEN 完整性校验 SHALL 回退 section-scope（章节非空）粗检，不误报。

### Requirement 8: 零回归、fail-open 与灰度开关

**User Story:** 作为平台维护者，我希望这些改动默认不影响现有附注渲染 / 生成 / 同步，可灰度开启、可回退。

#### Acceptance Criteria

1. THE 所有变更 SHALL 向后兼容既有 `note.table_data` 结构与既有生成 / 同步 / 校验链路（无 Cell_Binding 的单元格行为不变）。
2. IF 公式求值 / 报表同步出现任何异常，THEN 系统 SHALL fail-open，不阻塞附注树 / 详情渲染，也不阻断 `chain_workflow` 报表流程。
3. THE 表内公式求值与报表 → 附注同步的新行为 SHALL 受 `DISCLOSURE_NOTE_FORMULA_ENABLED` 开关控制（默认 False），关闭时逐字节等价于当前行为。
4. WHEN 开关关闭，THEN `resolve_formula` / `sync_report_to_notes` SHALL 保持当前可观察行为（stub 返 None / 仅清 stale），不产生新副作用。
5. THE 变更 SHALL 不改动底稿 → 附注同步的 `manual_override` 守卫与空载荷 no-op 行为。

### Requirement 9: 正确性属性可测（PBT）

**User Story:** 作为平台维护者，我希望核心不变量有属性测试守卫，防止回归。

#### Acceptance Criteria

1. THE spec SHALL 定义覆盖以下不变量的正确性属性并以 hypothesis PBT 验证：公式求值幂等、fail-open 返 None 不抛、manual/locked 保留、linkage 单一真源（Cell_Binding 优先）、Skip_On_Missing 优于误报、开关关闭零回归、同步幂等。
2. WHEN 运行全量测试，THEN 新增 / 既有 note 相关测试 SHALL 全绿，且 `disclosure-note-validation-completion` / 既有 disclosure 测试无回归。
