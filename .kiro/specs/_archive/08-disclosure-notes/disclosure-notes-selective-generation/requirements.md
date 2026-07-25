# Requirements Document

## Introduction

「交付件管理中心」(`DeliverableCenter.vue`) 现有「生成附注」按钮直接调用 `renderDisclosureNotes(projectId, {year})`（`deliverableApi.ts::goGenerateNotes`），**不传 `selected_sections`**，导致交付 docx 一次性生成全部章节。附注模板包含大量当期无业务发生的空科目章节（渲染为「本期无此项业务。」），全量生成使交付文档充斥无数据的空章节，缺乏针对性。

本功能在点击「生成附注」时弹出对话框，展示**附注模块当前项目的实时树形结构**（按 一/二/三…/五科目注释 顶层分组，每章节 + 对应内容/是否有数据），让审计师自定义勾选要生成进交付 docx 的章节，并提供「一键预设生成」（默认只勾有数据的科目章节）。生成更有针对性，避免空章节混入交付文档。

**与现有基础设施对齐（本会话已调研，本功能不重写导出逻辑）**：

- 后端 `POST /api/projects/{pid}/deliverables/disclosure-notes/render`（`deliverable.py::render_disclosure_notes`）**已接受** `selected_sections: list[str] | None`（`DeliverableExportRequest`），并已将其作为 `sections=` 透传给 `NoteWordExporter.export(...)`。
- `NoteWordExporter.export(..., sections=selected_sections, skip_empty=bool)` **已支持**按章节筛选与跳过空章节。
- `template_type` 由后端从 `Project.template_type` 权威解析（soe=「四、」前缀 / listed=「三、」前缀），前端无需传。
- 附注实时树 API：`GET /api/disclosure-notes/{project_id}/{year}`（`disclosure_notes.py::get_notes_tree` → `DisclosureEngine.get_notes_tree`）。当前每个节点返回 `{id, note_section, section_title, account_name, content_type, status, sort_order}`，**不含「是否有数据」标记**——这是预设预勾/置灰空章节所需的**唯一缺口**。

**核心设计约束（据已确认语义）**：

- **前端以 `has_data` 驱动预勾选/置灰，生成始终传 `selected_sections`（最终勾选集）**。「一键预设生成」= 把有数据的章节自动勾上、无数据章节不勾（可置灰但仍允许手动补勾）；用户可在此基础上再手动增/删勾选，然后确认生成。即预设与自定义可叠加——预设给出「一键推荐勾选集」，用户二次微调后再确认。
- **空章节仍允许用户手动勾选包含**（会渲染「本期无此项业务。」）——预设默认不勾但不禁止。
- 本功能主要是「把已有导出能力接出来 + 弹窗 + 树节点增 `has_data` 字段」，**不重写导出逻辑，不改 `template_type` 解析**。
- 权限与现有「生成附注」一致（`DeliverableAction.export`）。

## Glossary

- **交付中心 (Deliverable_Center)**：`DeliverableCenter.vue` 交付件管理界面，含「生成附注」入口。
- **附注选择对话框 (Selection_Dialog)**：点击「生成附注」后弹出的对话框，展示附注实时树并收集用户勾选。
- **附注树服务 (Notes_Tree_Service)**：后端 `GET /api/disclosure-notes/{project_id}/{year}`（`DisclosureEngine.get_notes_tree`），返回附注章节树。
- **附注导出器 (Note_Exporter)**：`NoteWordExporter.export`，按 `sections`/`skip_empty` 生成交付 docx。
- **交付渲染接口 (Render_Endpoint)**：`POST /api/projects/{pid}/deliverables/disclosure-notes/render`，接受 `selected_sections` 并调用附注导出器。
- **章节 (Note_Section)**：附注树节点，以 `note_section` 编号（如「五、1」「三、7」）唯一标识。
- **has_data**：章节是否含数据的布尔标记。判定口径与 `NoteWordExporter._has_content` / `should_skip_empty_section` 同源：`text_content` 非空，或 `table_data` 存在非空 rows（任一单元格值非空、非 0、非「-」）。
- **selected_sections**：用户在对话框最终勾选、要生成进交付 docx 的章节 `note_section` 列表，传给交付渲染接口。
- **一键预设 (Preset_Selection)**：把 `has_data=true` 的章节自动勾选、`has_data=false` 的章节不勾的推荐勾选集。
- **变体 (Variant)**：项目披露口径，`listed`（上市，「三、」前缀）或 `soe`（国企，「四、」前缀），由 `Project.template_type` 权威决定。
- **导出权限 (Export_Permission)**：`DeliverableAction.export`，现有「生成附注」所需权限。

## Requirements

### Requirement 1: 生成附注触发对话框并展示实时附注树

**User Story:** 作为审计师，我希望点击「生成附注」时弹出对话框展示附注模块当前项目的实时树形结构，以便在生成前看清有哪些章节及各章节是否有数据。

#### Acceptance Criteria

1. WHEN 用户在交付中心点击「生成附注」，THE 交付中心 SHALL 打开附注选择对话框，而非直接调用交付渲染接口。
2. WHEN 附注选择对话框打开，THE 附注选择对话框 SHALL 通过附注树服务 `GET /api/disclosure-notes/{project_id}/{year}` 获取当前项目当前年度的附注树。
3. THE 附注选择对话框 SHALL 按顶层分组（如「一、」「二、」「三、」「五、科目注释」）分层展示章节树，每个章节节点显示章节编号 `note_section`、章节标题 `section_title` 与是否有数据标记。
4. THE 附注选择对话框 SHALL 使用带复选框的分层树控件（`el-tree` `show-checkbox`），支持按分组与按单章节勾选。
5. WHILE 附注树正在加载，THE 附注选择对话框 SHALL 显示加载中状态，并禁用「确认生成」直至加载结束。

### Requirement 2: 附注树节点提供 has_data 标记

**User Story:** 作为审计师，我希望树上每个章节标明是否有数据，以便区分需要生成的实际业务章节与空章节。

#### Acceptance Criteria

1. THE 附注树服务 SHALL 为每个章节节点返回 `has_data` 布尔字段。
2. THE 附注树服务 SHALL 采用与 `NoteWordExporter._has_content` 一致的判定口径计算 `has_data`：WHERE 章节 `text_content` 非空 OR `table_data` 存在任一非空、非 0、非「-」的单元格值，THE `has_data` SHALL 为 `true`，否则为 `false`。
3. THE 附注树服务 SHALL 保留现有节点字段（`id`、`note_section`、`section_title`、`account_name`、`content_type`、`status`、`sort_order`），`has_data` 为附加字段。
4. WHERE 章节 `status` 为 `not_applicable`（`is_empty=true`），THE 附注树服务 SHALL 返回该章节 `has_data` 为 `false`。

### Requirement 3: 一键预设生成（默认只勾有数据的章节）

**User Story:** 作为审计师，我希望一键预设自动勾选有数据的章节、不勾空章节，以便快速得到一份只含实际业务的推荐勾选集。

#### Acceptance Criteria

1. WHEN 用户在附注选择对话框点击「一键预设生成」，THE 附注选择对话框 SHALL 把 `has_data=true` 的章节设为勾选、`has_data=false` 的章节设为不勾选。
2. THE 附注选择对话框 SHALL 对 `has_data=false` 的章节做视觉置灰以提示其为无数据章节。
3. WHERE 章节 `has_data=false` 且被置灰，THE 附注选择对话框 SHALL 仍允许用户手动补勾该章节（置灰不等于禁用）。
4. WHEN 一键预设完成，THE 附注选择对话框 SHALL 展示当前勾选章节的数量供用户确认。

### Requirement 4: 自定义勾选生成

**User Story:** 作为审计师，我希望按树形手动勾选要生成的章节，以便完全自定义交付文档的章节范围。

#### Acceptance Criteria

1. WHEN 用户在附注选择对话框手动勾选或取消勾选章节，THE 附注选择对话框 SHALL 实时更新最终勾选集 `selected_sections`。
2. WHEN 用户勾选某分组节点，THE 附注选择对话框 SHALL 将该分组下的全部子章节纳入勾选集。
3. WHERE 用户手动勾选了 `has_data=false` 的空章节，THE 附注选择对话框 SHALL 将该空章节纳入 `selected_sections`（该章节会渲染为「本期无此项业务。」）。

### Requirement 5: 预设与自定义叠加（二次修正）

**User Story:** 作为审计师，我希望在一键预设给出的推荐勾选集基础上再手动增删勾选，然后确认生成，以便预设与自定义可叠加。

#### Acceptance Criteria

1. WHEN 用户点击「一键预设生成」后再手动增/删勾选，THE 附注选择对话框 SHALL 在预设勾选集基础上应用用户的增删，得到最终 `selected_sections`。
2. THE 附注选择对话框 SHALL NOT 在用户二次修正后强制回退到预设勾选集（预设仅设置初始推荐勾选，不锁定后续修改）。
3. WHEN 用户在二次修正后确认生成，THE 附注选择对话框 SHALL 以当前最终勾选集作为 `selected_sections` 提交，而非预设的原始勾选集。

### Requirement 6: 生成调用传入 selected_sections

**User Story:** 作为审计师，我希望确认生成后交付文档只包含我勾选的章节，以便生成结果与勾选一致。

#### Acceptance Criteria

1. WHEN 用户在附注选择对话框点击「确认生成」，THE 交付中心 SHALL 调用交付渲染接口并传入 `selected_sections`（当前最终勾选集）与 `year`。
2. THE 交付中心 SHALL NOT 传入 `template_type`（由后端从 `Project.template_type` 权威解析）。
3. WHEN 交付渲染接口收到 `selected_sections`，THE 附注导出器 SHALL 仅生成 `selected_sections` 中的章节到交付 docx。
4. WHEN 生成成功，THE 交付中心 SHALL 关闭附注选择对话框并按现有生成成功流程（刷新交付件列表/进入编辑态）展示结果。

### Requirement 7: 空选守卫

**User Story:** 作为审计师，我希望在未勾选任何章节时无法触发生成，以便避免生成空交付文档。

#### Acceptance Criteria

1. WHILE 最终勾选集 `selected_sections` 为空，THE 附注选择对话框 SHALL 禁用「确认生成」。
2. IF 用户尝试在勾选集为空时提交，THEN THE 附注选择对话框 SHALL 完全阻止该次提交（不调用交付渲染接口）并提示「请至少选择一个章节」。

### Requirement 8: 树加载失败降级

**User Story:** 作为审计师，我希望在附注树加载失败时得到明确提示与可用的降级路径，以便不因树加载异常而完全无法生成。

#### Acceptance Criteria

1. IF 附注树服务返回 404（附注数据不存在，需先生成附注），THEN THE 附注选择对话框 SHALL 提示「附注数据不存在，请先生成附注」并禁用「确认生成」。
2. IF 附注树服务返回其他错误或超时，THEN THE 附注选择对话框 SHALL 显示加载失败提示并提供「重试」操作。
3. WHERE 附注树加载失败，THE 交付中心 SHALL NOT 以空 `selected_sections` 或未定义章节集触发交付渲染接口。

### Requirement 9: 国企与上市两变体均适用

**User Story:** 作为审计师，我希望本功能在国企与上市两种披露口径下都可用，以便所有项目都能选择性生成附注。

#### Acceptance Criteria

1. THE 附注树服务 SHALL 按项目实际变体（`listed` 或 `soe`）返回对应的章节树（章节编号前缀「三、」或「四、」由后端按项目决定）。
2. THE 附注选择对话框 SHALL 直接展示附注树服务返回的章节，不在前端硬编码变体或章节前缀。
3. WHEN 用户在任一变体下确认生成，THE 附注导出器 SHALL 使用后端解析的 `template_type` 生成，与 `selected_sections` 共同决定输出章节。

### Requirement 10: 权限与现有生成附注一致

**User Story:** 作为平台维护者，我要求本功能沿用现有「生成附注」的权限约束，以便不放宽或收紧访问控制。

#### Acceptance Criteria

1. WHERE 用户不具备导出权限 `DeliverableAction.export`，THE 交付中心 SHALL 完全隐藏「生成附注」入口（与现有行为一致）。
2. THE 交付渲染接口 SHALL 沿用现有 `DeliverableAction.export` 权限校验，不因新增对话框而改变服务端授权。
3. THE 附注树服务 SHALL 沿用其现有项目级访问控制，不因本功能新增放宽。
