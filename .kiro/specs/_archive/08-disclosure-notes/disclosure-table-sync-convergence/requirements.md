# Requirements Document

## Introduction

本规格解决"修订底稿后附注科目表格丢失"的**第二层根因：渲染断裂**。前序已直接修复的**数据销毁类活跃 bug**（`sync_from_workpaper` / `sync_from_html` 空载荷清空 `sub_table_data`、`sync-html` 路由死链）不重复，仅作为回归保证纳入（Requirement 8）。

### 已证实的证据链（grep + 读码 + 端点核实）

- `*TabDisclosureListed.vue` / `*TabDisclosureSoe.vue`（G/H/I/K 共 50+ 组件）与 `GtCNoteTable.vue` 通过 `POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper`（及 batch）把披露表推进 `disclosure_notes.table_data.sub_table_data`。
- **后端**：全仓 grep `sub_table_data` 仅被 `wp_disclosure_sync_service` 写入；`get_note_detail`（`disclosure_notes.py:242`）原样透传 `table_data`，无投影；`refill_sections` 只改旧 `table_data.rows`，从不读/写 `sub_table_data`。
- **附注模块前端**：`DisclosureEditor.vue::currentNoteTables`（`:1427`）只读 `table_data._tables` 或 `table_data.headers/rows`，**完全不读 `sub_table_data`**。
- **Word 导出**：`note_word_exporter.py` 只渲染 `_tables` / 单表 `rows`，**不读 `sub_table_data`**。
- **唯一读 `sub_table_data` 的是底稿侧 `GtCNoteTable.vue`**（读自身 htmlData，靠 `props.schema` 的列定义渲染）。

**结论**：sync 推入 `sub_table_data` 的表，对附注模块渲染与 Word 导出而言是**孤立只写字段**——数据在库里，但附注模块看不见、导不出。

### 为何不能 ad-hoc 通用投影（关键约束）

读 `f2DisclosureSyncPayload.ts` 核实：同步载荷的行只有 `label`（或 `group_name`/`project_name`/`kind`）+ **snake_case 英文字段键**（`end_gross` / `increase_provision` / `prior_net` …）+ 可选 `is_total`，**无任何中文列头元数据**。附注渲染器需要 `{name, headers[中文], rows:[{label, values[], is_total}]}`。把英文字段键直接当列头 = **自造披露列头**，违反"禁止凭常识自造披露内容、须对照致同 2025 源模板"铁律。正确的中文列头当前散落在各披露组件模板的 `<el-table-column label="…">` 与 C 类 schema 的 `columns[]` 里——它们本就是对照源模板编制的、是列头的**权威来源**。

### 数据流目标

```
披露表组件(源对齐列头) ──sync payload(rows + _columns)──▶ disclosure_notes.table_data
                                                          │  {sub_table_data, _sub_table_columns, _source='workpaper'}
                                                          ▼
                          后端读时投影器(单一实现) sub_table_data + _columns ──▶ 可渲染 _tables[]
                                                          │
                                        ┌─────────────────┴─────────────────┐
                                        ▼                                   ▼
                            附注模块 currentNoteTables 渲染          note_word_exporter 导出
```

### 目标

让披露表推送的 `sub_table_data` 在**附注模块可见、Word 可导出**，上市版/国企版各自忠实呈现源模板表样，全程**列头源自组件既有源对齐定义、零自造**，且**零回归**既有 DisclosureEngine 模板填充路径、A9 缺陷函联动与底稿侧 `GtCNoteTable` 渲染。

## Glossary

- **Disclosure_Module**：附注模块编辑器 `DisclosureEditor.vue`（读 `disclosure_notes`）。
- **CNote_Component**：底稿侧 C 类附注组件 `GtCNoteTable.vue`（唯一现读 `sub_table_data` 者，schema 驱动）。
- **Disclosure_Tab_Component**：各科目底稿的 `*TabDisclosureListed.vue` / `*TabDisclosureSoe.vue`，构造 sync 载荷推送附注。
- **Sync_Endpoint**：`sync-from-workpaper` / `sync-batch-from-workpaper`（正式结构化同步，走 `sync_from_workpaper`）。
- **sub_table_data**：`table_data.sub_table_data`，形如 `{子表中文名: [行对象]}`，行对象携带 `label` + 英文字段键 + 可选 `is_total`。
- **Column_Meta（列头元数据）**：本规格新增 `ColumnDef = {key, label, is_label?, align?, format?}`；`_columns: {子表key: ColumnDef[]}`。`label` 为对照致同源模板的中文列头。
- **Projected_Tables**：投影器把 `sub_table_data` + `Column_Meta` 转成渲染器可消费的 `_tables[]`（`{name, headers[], columns[], rows:[{label, values[], is_total?}], _source_sub_table_key}`）。
- **Projector**：后端单一投影实现，供 Disclosure_Module 详情读取与 Word 导出共用。
- **Renderer_Format**：`currentNoteTables` / `note_word_exporter` 现消费的 `_tables[]` / 单表 `{headers, rows}` 结构。
- **Engine_Fill_Path**：`DisclosureEngine` 模板绑定填充产出的 `_tables`/`rows`（既有路径，不改）。
- **Variant（变体）**：上市版 `listed` / 国企版 `soe`；已由不同 `note_section` 天然隔离（如 G14 `G14_NOTE_SECTION.listed` vs `.soe`）。
- **Source_Template**：致同通用审计程序及底稿模板（2025 修订版），列头/表样权威来源。
- **Coverage_Ledger**：全部 Disclosure_Tab_Component + CNote_Component 的 `_columns` 覆盖清单 + CI 漂移守卫。

## Requirements

### Requirement 1: 附注模块与 Word 导出必须渲染 sub_table_data 同步的表格

**User Story:** 作为审计师，我在披露表底稿录入的表格数据推送到附注后，应能在附注模块看到完整表格并导出到 Word，而不是看到空白。

#### Acceptance Criteria

1. WHEN 某 `disclosure_notes` 记录的 `table_data` 含非空 `sub_table_data` 且带 Column_Meta THEN Disclosure_Module 的章节详情 SHALL 渲染出对应表格（表名、中文列头、数据行、合计行）。
2. WHEN 同一记录被 Word 导出 THEN 导出文档 SHALL 包含与模块渲染一致的表格（同表名、同列头、同行）。
3. WHEN `sub_table_data` 含多张子表 THEN 系统 SHALL 逐张渲染为独立表格（表名取子表 key），保持 `sub_table_data` 的键顺序。
4. WHEN 行对象含 `is_total: true` THEN 该行 SHALL 渲染为合计行（沿用渲染器既有合计样式）。
5. WHERE 记录同时存在 Engine_Fill_Path 的 `_tables`/`rows` 与 workpaper 来源的 `sub_table_data`，THEN 优先级规则 SHALL 在 design 明确并在 Projector 单点实现（见 Requirement 6），不得产生重复表或互相覆盖。

### Requirement 2: 同步载荷携带源对齐列头元数据

**User Story:** 作为系统，我需要在推送表格数据的同时携带列头定义，才能在附注模块忠实还原源模板表样。

#### Acceptance Criteria

1. WHEN Disclosure_Tab_Component / CNote_Component 构造 sync 载荷 THEN 载荷 SHALL 含 `_columns: {子表key: ColumnDef[]}`，每个子表 key 与 `sub_table_data` 同名对应。
2. WHERE 某 ColumnDef 是标签列（承载 `label`/行名），THEN 其 `is_label` SHALL 为 true，且投影时作为表格第一列。
3. WHEN `_columns[key]` 的某 ColumnDef.key 在 `sub_table_data[key]` 的行对象中不存在 THEN 投影 SHALL 对该单元格输出空值（不报错、不丢列）。
4. WHEN 行对象含 `_columns` 未声明的字段键 THEN 投影 SHALL 忽略该字段（不擅自新增列）。
5. IF 载荷未携带 `_columns`（旧版本组件尚未接入）THEN 系统 SHALL 走降级路径（见 Requirement 7），不得报错、不得清空既有数据。

### Requirement 3: 列头必须源自致同 2025 源模板，禁止自造

**User Story:** 作为质控合伙人，我要求附注表格列头与致同源模板一致，不允许出现英文字段名或凭常识杜撰的列头。

#### Acceptance Criteria

1. WHEN 定义某组件的 `_columns` THEN `label` SHALL 取自该组件既有 `<el-table-column label="…">` / C 类 schema `columns[].label`（这些是对照源模板编制的既有中文列头）。
2. WHEN 无法从组件既有定义取得某列的中文列头 THEN 该列 SHALL 保持不接入（宁缺毋滥），不得以英文字段键或推测文案充数。
3. WHEN 投影缺失 Column_Meta THEN 系统 SHALL NOT 使用英文字段键作为列头（走降级路径而非杜撰）。
4. WHERE 上市版与国企版列结构不同（源模板本就不同），THEN 各自的 `_columns` SHALL 分别对照各自源模板 sheet。

### Requirement 4: 上市版 / 国企版互不覆盖且各自表样正确

**User Story:** 作为审计师，上市版和国企版披露表必须各自映射到正确的附注章节与表样，任一变体的同步不得覆盖另一变体。

#### Acceptance Criteria

1. WHEN 上市版组件同步 THEN 其目标 `note_section` SHALL 为该科目的 listed 章节（如 `G14_NOTE_SECTION.listed`）；国企版同步目标 SHALL 为 soe 章节。
2. WHEN 上市版与国企版目标 `note_section` 相同（若存在此类科目）THEN design SHALL 定义子表 key 或记录级命名空间隔离规则，确保两变体数据不互相覆盖。
3. WHEN 投影渲染 THEN 变体差异 SHALL 完全由各自 `note_section` 记录承载，Projector 不做跨变体合并。
4. WHILE 单个项目只有一种报告准则（listed 或 soe）THEN 系统 SHALL 依 `current_standard` 呈现对应变体，不得同屏混渲两套。

### Requirement 5: 全组件 _columns 覆盖 + CI 守卫

**User Story:** 作为维护者，我需要确保所有披露表组件都接入了列头元数据，避免漏接导致个别科目仍渲染空白。

#### Acceptance Criteria

1. WHEN 规格实施完成 THEN 全部调用 Sync_Endpoint 的 Disclosure_Tab_Component 与 CNote_Component SHALL 在载荷中携带 `_columns`。
2. WHEN 新增/修改披露组件未携带 `_columns` THEN Coverage_Ledger CI 守卫 SHALL 失败并列出漏接组件。
3. WHEN CI 守卫运行 THEN 其 SHALL 通过静态扫描识别所有 `sync-from-workpaper` 调用点并核对是否含 `_columns`（或在 allowlist 中显式豁免并注明原因）。

### Requirement 6: 投影优先级与来源标识

**User Story:** 作为系统，我需要明确当一条附注同时有引擎填充表与底稿同步表时，渲染哪一个，避免重复或覆盖。

#### Acceptance Criteria

1. WHERE `table_data._source == 'workpaper'`（或 `workpaper_html`）且存在非空 `sub_table_data`，THEN Projector SHALL 以 `sub_table_data` + Column_Meta 投影为权威 `_tables`。
2. WHERE 无 workpaper 来源标识但存在 Engine_Fill_Path 的 `_tables`/`rows`，THEN 系统 SHALL 沿用既有渲染（不投影 `sub_table_data`）。
3. WHEN 两者并存 THEN Projector SHALL 依据 `_source` 单点决策，绝不同时输出两套导致重复表。
4. WHEN 投影执行 THEN 其 SHALL 为纯函数（同输入同输出、无副作用、不写库），供详情读取与 Word 导出复用同一实现。

### Requirement 7: 降级与向后兼容（零回归）

**User Story:** 作为维护者，规格上线不得破坏既有已渲染的附注、A9 缺陷函联动、底稿侧 GtCNoteTable，以及尚未接入 `_columns` 的历史数据。

#### Acceptance Criteria

1. WHEN 记录只有 Engine_Fill_Path 的 `_tables`/`rows`（无 `sub_table_data`）THEN 渲染 SHALL 与规格实施前完全一致。
2. WHEN `sub_table_data` 存在但无 Column_Meta（历史数据/未接入组件）THEN 系统 SHALL 走降级：优先复用行对象中若已带 `label` 则以其为唯一可读列渲染，其余字段**不以英文键当列头呈现**（可折叠为"待配置列头"提示或不渲染值列），且 SHALL NOT 报错、SHALL NOT 清空数据。
3. WHEN 底稿侧 CNote_Component 读取自身 htmlData THEN 其行为 SHALL 不受本规格影响（`GtCNoteTable` 渲染路径不变）。
4. WHEN A9-1/A9-2 缺陷函读取缺陷 THEN 其数据源 SHALL 不受本规格影响。
5. WHEN 空载荷同步 THEN `sub_table_data` SHALL 保持 no-op 不清空（前序已修复，纳入回归测试锁定）。

### Requirement 8: 前序数据销毁修复的回归锁定

**User Story:** 作为质控，我要求已修复的表格销毁类 bug 有测试守卫，防止回归。

#### Acceptance Criteria

1. WHEN 对已有多表的附注传入空 `sub_table_data={}` THEN 既有表格 SHALL 全部保留（回归测试锁定）。
2. WHEN 部分推送 `{t1: [...]}` THEN 未推送的 `t2` SHALL 完整保留、`t1` 被新值覆盖。
3. WHEN 显式推送 `{t1: []}` THEN `t1` SHALL 为空行有效状态、其余子表保留。
4. WHEN 访问 `sync-html` 端点 THEN 其 SHALL 位于 `/api/wp-disclosure-sync/{wp_id}/sync-html`（非双前缀死链）。
