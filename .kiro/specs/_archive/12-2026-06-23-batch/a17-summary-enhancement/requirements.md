# Requirements Document

## Introduction

A17-1「重大事项概要」是审计完成阶段最核心的底稿，包含 16 个章节汇总全审计项目的关键判断与结论。当前实现已具备章节导航、纯文本编辑、数据拉取、AI 生成初稿和自动保存功能。本增强聚焦六个维度：富文本 HTML 渲染、source_label 可点击跳转、跨章节一致性校验、LLM 生成增强（跨章上下文 + 润色模式）、A17-2 KAM 集成至 ch12、以及 A17 子文档快速导航。

## Glossary

- **A17_Editor**: A17-1 重大事项概要前端编辑器组件（GtA17Summary.vue）
- **Chapter_Content**: 单个章节的富文本内容（HTML 格式存储）
- **Ref_Chip**: 可点击的底稿引用标签，显示 wp_code 并支持跳转至目标底稿
- **Consistency_Checker**: 跨章节逻辑一致性校验服务
- **LLM_Service**: A17 章节 AI 辅助生成服务（a17_llm_service.py）
- **KAM_Panel**: ch12 章节内嵌的 KAM 条目摘要面板
- **Sub_Doc_Navigator**: A17 系列子文档快速导航栏组件
- **source_label**: 章节数据来源标识字符串（如 "A15+A15-1"）

## Requirements

### Requirement 1: 章节内容富文本 HTML 渲染

**User Story:** As a 业务合伙人, I want 章节内容支持标题、列表、表格、加粗斜体等富文本格式, so that 重大事项概要的表述更加结构化、可读性更强。

#### Acceptance Criteria

1. THE A17_Editor SHALL render Chapter_Content as rich HTML supporting headings (h3/h4), bullet lists, numbered lists, tables, bold, and italic formatting.
2. WHEN a user edits Chapter_Content, THE A17_Editor SHALL provide a lightweight toolbar with formatting controls for headings, lists, bold, italic, and table insertion.
3. THE A17_Editor SHALL store Chapter_Content as sanitized HTML strings in the existing checklist_responses.remark field.
4. WHEN Chapter_Content contains unsanitized HTML tags, THE A17_Editor SHALL strip dangerous tags (script, iframe, on* attributes) before rendering and before saving.
5. WHEN legacy plain-text content is loaded from the database, THE A17_Editor SHALL render the plain text as-is (preserving line breaks as `<br>`) without requiring migration.
6. WHEN the user exports A17-1 to Word via /api/a17/export-word, THE A17_Word_Exporter SHALL convert the HTML content of each chapter into corresponding Word paragraph styles (headings, lists, tables, bold/italic).

### Requirement 2: source_label 解析为可点击 Ref_Chip

**User Story:** As a 现场经理, I want source_label 中的底稿编码（如 "详见 B50"、"参考 A13"）显示为可点击的芯片, so that 我可以一键跳转到引用的底稿进行核对。

#### Acceptance Criteria

1. WHEN Chapter_Content or source_label contains a pattern matching a wp_code (regex: `[A-S]\d{1,2}(?:-\d{1,2})?(?:[A-Z])?`), THE A17_Editor SHALL parse the pattern and render it as a clickable Ref_Chip component.
2. WHEN a user clicks a Ref_Chip, THE A17_Editor SHALL navigate to the referenced workpaper using the project's existing workpaper routing mechanism (router push with wp_code query).
3. IF the referenced wp_code does not exist in the current project's wp_index, THEN THE A17_Editor SHALL display the Ref_Chip in a disabled/grey style with a tooltip "该底稿在当前项目中不存在".
4. THE A17_Editor SHALL parse source_label strings (e.g., "A15+A15-1", "A17-2-1") by splitting on `+` delimiter and rendering each segment as an individual Ref_Chip.
5. WHEN Chapter_Content is in edit mode, THE A17_Editor SHALL allow users to insert Ref_Chip via a shortcut (typing `@` followed by wp_code autocomplete) in addition to automatic detection.

### Requirement 3: 跨章节一致性校验

**User Story:** As a 质量控制复核合伙人, I want 系统自动检查各章节结论之间的逻辑一致性, so that 重大事项概要不存在自相矛盾的结论（如持续经营存疑却出无保留意见）。

#### Acceptance Criteria

1. WHEN a user triggers consistency checking (via toolbar button or upon export-word), THE Consistency_Checker SHALL validate logical relationships between chapter conclusions.
2. THE Consistency_Checker SHALL check the following cross-chapter rules:
   - ch10 (持续经营) mentions "重大不确定性" AND ch14 (审计结论) states "标准无保留" → WARNING: 需解释为何持续经营存疑但仍出具无保留意见
   - ch12 (KAM) is empty AND project.business_category is "上市公司" → ERROR: 上市公司审计必须披露 KAM
   - ch15 (舞弊) mentions fraud indicators AND ch14 has no corresponding qualification mention → WARNING: 舞弊线索未在审计结论中体现
   - ch06 (重大错报风险) references unresolved risks AND ch14 states unqualified → WARNING: 未应对风险与审计结论不一致
3. THE Consistency_Checker SHALL return a structured result containing: rule_id, severity (error/warning/info), affected_chapters (list of chapter IDs), and description.
4. THE A17_Editor SHALL display consistency check results in a collapsible alert panel below the toolbar, grouped by severity.
5. WHEN a consistency check result references specific chapters, THE A17_Editor SHALL render the chapter references as clickable links that navigate to the cited chapter.
6. IF no inconsistencies are detected, THEN THE Consistency_Checker SHALL return an empty result set and the A17_Editor SHALL display a success indicator.

### Requirement 4: LLM 生成增强（跨章上下文 + 润色模式）

**User Story:** As a 审计助理, I want AI 生成章节内容时参考其他章节已填写的结论作为上下文, so that 各章节表述协调统一、无矛盾；同时我希望有"润色改进"模式优化已有内容而非从头生成。

#### Acceptance Criteria

1. WHEN the user triggers AI generation for a chapter, THE LLM_Service SHALL collect the content of all other filled chapters as cross-chapter context and include it in the prompt.
2. THE LLM_Service SHALL support two generation modes: "generate" (从头生成, current behavior) and "polish" (润色改进, preserving the existing content structure while improving expression).
3. WHEN "polish" mode is selected, THE LLM_Service SHALL include the current chapter content in the prompt with instructions to refine language, improve structure, and ensure consistency with other chapters.
4. THE A17_Editor SHALL provide a mode selector (generate/polish) in the AI dialog, defaulting to "generate" when chapter content is empty and "polish" when content already exists.
5. WHEN cross-chapter context exceeds the model's context window budget, THE LLM_Service SHALL prioritize including logically related chapters (based on data_source overlap and adjacent chapters) over distant ones.
6. THE LLM_Service SHALL include the project's industry and audit period in the generation context to ensure domain-appropriate language.

### Requirement 5: A17-2 KAM 集成至 ch12

**User Story:** As a 业务合伙人, I want 在 ch12 章节中直接查看 A17-2 中确定的关键审计事项列表, so that 我无需切换底稿即可确认 KAM 内容与概要描述一致。

#### Acceptance Criteria

1. WHEN ch12 is the active chapter, THE A17_Editor SHALL display a KAM_Panel showing the list of KAM items from A17-2-1 (fetched via existing pull mechanism or dedicated API).
2. THE KAM_Panel SHALL display each KAM item's title, brief description, and associated wp_refs as Ref_Chips.
3. WHEN a user clicks a KAM item in the KAM_Panel, THE A17_Editor SHALL navigate to the corresponding A17-2-1 workpaper entry.
4. WHEN A17-2-1 KAM data changes (items added/removed/modified), THE KAM_Panel SHALL reflect updates upon ch12 re-selection or manual refresh.
5. IF no A17-2-1 workpaper exists in the project, THEN THE KAM_Panel SHALL display a placeholder message "尚未创建 KAM 底稿（A17-2-1），如属上市公司审计请先创建".

### Requirement 6: A17 子文档快速导航

**User Story:** As a 现场经理, I want 从 A17-1 快速导航到 A17-2/A17-3/A17-4/A17-5/A17-6/A17-7 子文档, so that 我可以高效切换重大事项概要模块下的各子文档而无需返回底稿目录。

#### Acceptance Criteria

1. THE A17_Editor SHALL display a Sub_Doc_Navigator bar (above or beside the chapter navigation) listing all A17 series sub-documents: A17-2 (KAM), A17-3 (业务咨询), A17-4 (分歧记录), A17-5 (完成核对表), A17-6 (总结会), A17-7 (独立性声明).
2. WHEN a user clicks a sub-document entry in the Sub_Doc_Navigator, THE A17_Editor SHALL navigate to that workpaper using the project's workpaper routing mechanism.
3. THE Sub_Doc_Navigator SHALL indicate availability status for each sub-document: "已创建" (exists in project wp_index) vs "不适用/未创建" (not exists), using distinct visual styling.
4. WHEN a sub-document is marked "不适用/未创建", THE Sub_Doc_Navigator SHALL disable the click navigation and show a tooltip explaining the status.
5. THE Sub_Doc_Navigator SHALL be fetched from the backend based on the project's wp_index (which A17-x workpapers exist for this project).
