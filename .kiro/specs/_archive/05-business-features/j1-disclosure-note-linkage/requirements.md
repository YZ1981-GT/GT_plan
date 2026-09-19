# Requirements Document

## Introduction

J1 应付职工薪酬（科目 2211）的两张披露表（上市/国企）当前与附注模块**零联动**：既没有 sync payload 构建器（无「同步到附注」）、也没有正向跳转（附注→披露表）与反向跳转（披露表→附注），更没有在 `useNoteRefresh` 登记 2211 → 底稿改了披露表附注不动、附注里点「跳转至披露表」没有目标。本 spec 把 J1 接入平台已 proven 的附注联动三链（D1/E1/F3/N1 同款），使「审定表 J1-1 → 披露表 → 附注五、40 / 八、40」形成端到端可追溯闭环。

范围仅限**联动链路**：附注章节映射冻结、sync payload 构建器（表格 + 说明文本）、双向跳转、刷新登记、覆盖率守卫登记。不改附注模板、不改后端 `wp_disclosure_sync_service`、不改 J1 披露表已有的行结构与录入交互。

**现状基线（已核实，2026-07-26）**

- 权威章节（`backend/data/note_template_variant_matrix.json` → `ying_fu_zhi_gong_xin_chou`）：`listed_standalone/listed_consolidated = 五、40`；`soe_standalone/soe_consolidated = 八、40`。
- 附注模板 `五、40`（listed）三张子表：`应付职工薪酬` / `短期薪酬` / `设定提存计划`，列头均为 `['项目','期初余额','本期增加','本期减少','期末余额']`。
- 附注模板 `八、40`（soe）三张子表：`应付职工薪酬列示` / `短期薪酬列示` / **`短期薪酬列示`（第三张表名与第二张重复，模板笔误；其 `text_sections` 章节标题为「设定提存计划列示」）**。
- J1 披露表组件列头与模板存在差异：listed 组件用「上年年末数」，模板用「期初余额」。
- J1 披露 sheet 在 render 策略 `J1_SHEETS` 中登记为 `附注披露信息（上市公司）` / `附注披露信息（国有企业）`（国企后缀为「国有企业」，与 D1/N1 的「国企」不同）。
- `noteDisclosureJump.ts` / `noteDisclosureReverseJump.ts` / `useNoteRefresh.ts` 中 J1 与 2211 均零匹配。
- 前置依赖已就绪：J1 两张披露表已具备持久化（`J1-disc-{variant}-*` 键）与合计聚合。

## Glossary

- **Note_Section**：附注章节号，`五、40`（上市）/ `八、40`（国企），取自权威变体矩阵，禁止臆造。
- **Sub_Table_Key**：`sub_table_data` 的子表键，逐字取自附注模板 `tables[].name`。
- **Column_Def**：`disclosureColumnDefs.ts` 的列定义（key/label/format/is_label），label 逐字取自附注模板 `tables[].headers`。
- **Sync_Payload**：`POST /api/disclosure-notes/{pid}/{year}/{section}/sync-from-workpaper` 的请求体（wp_id / sheet_name / section_id / current_standard / sub_table_data / columns）。
- **Note_Texts**：混在 `sub_table_data._note_texts` 的说明文本数组（`[{section,title,text}]`），服务端 pop 后写入 `text_content`。
- **Forward_Jump**：附注模块 →底稿披露表（`noteDisclosureJump.resolveNoteDisclosureJumpTarget`）。
- **Reverse_Jump**：底稿披露表 →附注模块（`noteDisclosureReverseJump.buildNoteJumpRoute`）。
- **Duplicate_Table_Name**：附注模板中同一章节出现重复 `tables[].name`（本章节 soe 第二/三张表），需消歧后才能作为 Sub_Table_Key 使用。
- **Coverage_Guard**：`backend/scripts/check/check_disclosure_columns_coverage.py` 的 `COLUMN_BUILDERS` 登记表。

## Requirements

### Requirement 1: 附注章节与 sheet 名冻结映射

**User Story:** 作为审计助理，我希望 J1 披露表与附注章节的对应关系由权威源冻结，避免跳转到错误章节。

#### Acceptance Criteria

1. THE SYSTEM SHALL 将 J1 的 Note_Section 固定为 listed `五、40`、soe `八、40`，取值依据权威变体矩阵 `ying_fu_zhi_gong_xin_chou`。
2. THE SYSTEM SHALL 将 J1 披露 sheet 名以 `workpaper_sheet_classification`（wp_code=J1）实测值为准登记，不得凭其他循环的命名习惯推断。
3. WHEN 实测 sheet 名与 render 策略 `J1_SHEETS` 声明不一致 THEN THE SYSTEM SHALL 以 `workpaper_sheet_classification` 实测值为准并在映射文件注明差异。
4. THE SYSTEM SHALL 依据项目 `applicable_standards` 解析 `current_standard` 为 `listed_standalone|listed_consolidated|soe_standalone|soe_consolidated` 四值之一。
5. THE SYSTEM SHALL 把章节号、sheet 名、子表键、列头的权威来源在映射文件头部注明（模板路径 + 矩阵键），便于后续核对。

### Requirement 2: 披露表 → 附注 结构化同步（表格）

**User Story:** 作为审计助理，我希望在披露表点一次按钮就把三张子表推到附注，不用在附注里重新录一遍。

#### Acceptance Criteria

1. THE SYSTEM SHALL 为两个变体各提供一个 Sync_Payload 构建器，输出三张子表：汇总表、短期薪酬表、设定提存计划表。
2. THE SYSTEM SHALL 使 Sub_Table_Key 与附注模板 `tables[].name` 逐字一致；WHERE 存在 Duplicate_Table_Name THEN 按 Requirement 3 消歧。
3. THE SYSTEM SHALL 使每张子表的 `columns` 键集合与该子表数据行的字段键集合完全一致（投影器按键名匹配，键不一致会渲染空列）。
4. THE SYSTEM SHALL 使 Column_Def 的 label 逐字取自附注模板 headers（listed/soe 均为 `项目/期初余额/本期增加/本期减少/期末余额`），不得使用底稿组件列头（如 listed 组件的「上年年末数」）。
5. THE SYSTEM SHALL 把合计行标记为 `is_total`，其余为数据行；缩进子项（「其中：」）作为数据行推送并保留原标签。
6. WHEN 某数值为空或不可用 THEN THE SYSTEM SHALL 推送 `null` 而不是 `0`（0 会被读作「已核实为零」）。
7. THE SYSTEM SHALL 在披露表工具栏提供「同步到附注」入口，成功后提示同步行数、失败后提示可重试且不静默。
8. WHEN 项目处于只读态 THEN THE SYSTEM SHALL 禁用同步入口。

### Requirement 3: 重复子表名消歧

**User Story:** 作为质量控制复核人，我希望国企版第三张表推到附注后不会把第二张表覆盖掉。

#### Acceptance Criteria

1. THE SYSTEM SHALL 识别 soe `八、40` 的第二/三张表模板 name 重复（均为「短期薪酬列示」）这一事实。
2. THE SYSTEM SHALL 为第三张表采用消歧后的 Sub_Table_Key「设定提存计划列示」，依据为该表在模板 `text_sections` 中的章节标题。
3. THE SYSTEM SHALL 在映射文件中把该消歧记为「允许偏离模板 name 的情形」并写明依据与影响，供后续核对。
4. THE SYSTEM SHALL 保证一次同步中两张表都能落地（不因同名键互相覆盖而丢表）。
5. THE SYSTEM SHALL NOT 修改附注模板文件来解决重名（模板变更不在本 spec 范围）。

### Requirement 4: 披露表 → 附注 说明文本同步

**User Story:** 作为审计助理，我希望披露表里写的说明与附注正文一致，不用两处维护。

#### Acceptance Criteria

1. THE SYSTEM SHALL 把披露表各段说明（listed：短期薪酬 / 设定提存计划 / 辞退福利；soe：单段说明）作为 Note_Texts 随同步载荷提交。
2. THE SYSTEM SHALL 为每段文本提供稳定的 section 标识与中文标题。
3. WHEN 某段说明为空 THEN THE SYSTEM SHALL 跳过该段而不推送空标题块。
4. THE SYSTEM SHALL NOT 在同步链路中调用 AI 生成文本（AI 起草仍由披露表内既有按钮完成，人工确认后才同步）。

### Requirement 5: 附注 → 披露表 正向跳转

**User Story:** 作为审计助理，我在附注五、40 想一键跳到 J1 披露表核对来源。

#### Acceptance Criteria

1. THE SYSTEM SHALL 为 `五、40`/`八、40` 提供跳转目标解析，落到 J1 底稿对应变体的披露 sheet。
2. THE SYSTEM SHALL 使章节判定为**精确匹配**（`===`），不得使用前缀匹配（否则 `五、40` 会误伤 `五、4`/`五、49` 等）。
3. THE SYSTEM SHALL 在附注模块的族标签映射中登记 J1 为「应付职工薪酬」。
4. THE SYSTEM SHALL NOT 影响既有其他科目的跳转判定结果。

### Requirement 6: 披露表 → 附注 反向跳转

**User Story:** 作为现场经理，我在披露表想一键跳回附注确认最终列示。

#### Acceptance Criteria

1. THE SYSTEM SHALL 在反向映射中登记 J1 的两个变体章节号，且与正向判定同源（单一真源）。
2. THE SYSTEM SHALL 在两张披露表提供「跳转回附注」入口，默认跳转与当前变体一致的章节。
3. WHEN 项目上下文缺失（无 projectId）THEN THE SYSTEM SHALL 禁用该入口而不是跳到错误路由。
4. THE SYSTEM SHALL 仅做导航，不在反向链路写任何附注数据。

### Requirement 7: 附注定向刷新登记

**User Story:** 作为审计助理，我在披露表改完说明，正在看的附注章节应自动刷新。

#### Acceptance Criteria

1. THE SYSTEM SHALL 在 `useNoteRefresh` 中登记 J1（科目 2211）的匹配分支，使当前查看章节为 `五、40`/`八、40` 时收到事件即刷新。
2. THE SYSTEM SHALL 使披露表发出的事件载荷携带 `accountCode`、`projectId`、`sectionIds`（对齐平台既有范式）。
3. THE SYSTEM SHALL 使重复刷新是幂等的（重复触发不产生数据变更）。

### Requirement 8: 覆盖率守卫与零回归

**User Story:** 作为质量控制复核人，我需要 J1 的同步载荷被守卫纳管，且本次改动不破坏任何既有底稿。

#### Acceptance Criteria

1. THE SYSTEM SHALL 把 J1 的 Sync_Payload 构建器登记进 Coverage_Guard 的 `COLUMN_BUILDERS`，使 `--strict` 通过。
2. THE SYSTEM SHALL 保持后端 `wp_disclosure_sync_service` 与附注模板文件逐字节不变。
3. THE SYSTEM SHALL 保持 J1 披露表既有行结构、录入交互与持久化键不变（新增仅为工具栏入口与映射文件）。
4. THE SYSTEM SHALL 保证既有其他科目的正向/反向跳转与刷新测试全绿。
5. WHEN 同步接口返回失败 THEN THE SYSTEM SHALL 不改动本地披露表数据（失败不产生半同步状态）。

### Requirement 9: 正确性属性可测

**User Story:** 作为开发者，我需要这些映射与载荷规则有可执行的属性测试，防止后续漂移。

#### Acceptance Criteria

1. THE SYSTEM SHALL 为章节号、子表键、列头 label 提供冻结断言测试。
2. THE SYSTEM SHALL 为 Sub_Table_Key 与 columns 键一致性提供测试。
3. THE SYSTEM SHALL 为章节精确匹配（不误伤相邻章节号）提供测试。
4. THE SYSTEM SHALL 为正向判定与反向映射的一致性提供交叉守卫测试。
5. THE SYSTEM SHALL 为空值推 `null` 而非 `0` 提供测试。
