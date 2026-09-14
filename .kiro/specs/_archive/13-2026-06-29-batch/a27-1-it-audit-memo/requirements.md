# Requirements Document

## Introduction

为 A27-1（IT审计总结备忘录）创建专属 HTML 组件。原模板 61P/5T，结构化 IT 审计报告。

核心结构：备忘录抬头(日期/致/发自/主题) → 目的段(固定说明) → IT团队表(6行动态) → 七个章节(textarea/三选一radio/条件展开+GtIndexChip跳转) → 联动(B22A-4-3、C22、C21-1、B23-15)。

章节三和六含三选一结论（部分有效/没有有效/已有效），选择非"已有效"时条件展开缺陷描述段。

新增 componentType: `a27-1-it-audit-memo`，通过 wp_code_overrides 保持 skip 状态。

## Glossary

- **GtA271ItAuditMemo**: 前端主组件（~500 行），渲染 IT 团队表 + 7 章节卡片
- **useA271ItAuditMemo**: 前端 composable，管理数据加载/保存/结论选择
- **A271_Render_Strategy**: 后端渲染策略（`_a271_it_audit_memo.py`）
- **ITGC_Conclusion**: IT一般控制结论三选一（部分有效/没有有效/已有效）
- **IPC_Conclusion**: 信息处理控制结论三选一

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A27-1 to use a dedicated componentType.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A27-1" to componentType "a27-1-it-audit-memo" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a27-1-it-audit-memo" mapping to GtA271ItAuditMemo
3. THE RENDERER_DISPATCH SHALL include a "a27-1-it-audit-memo" strategy function
4. THE VALID_COMPONENT_TYPES list SHALL include "a27-1-it-audit-memo"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing.

#### Acceptance Criteria

1. WHEN the workpaper loads, THE GtA271ItAuditMemo SHALL display an el-segmented control with "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA271ItAuditMemo SHALL render GtOnlyOfficeSheet for the docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option
5. WHEN the user switches modes, THE useA271ItAuditMemo SHALL flush all pending saves before switching

### Requirement 3: 备忘录抬头

**User Story:** As a 审计助理, I want to fill in the memo header fields.

#### Acceptance Criteria

1. THE GtA271ItAuditMemo SHALL render a memo header with: 日期(el-date-picker), 致(el-input, auto-fill project partner), 发自(el-input, auto-fill current user), 主题(el-input, default "IT审计总结")
2. WHEN any header field changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-header-{field_id}`

### Requirement 4: 目的段

**User Story:** As a 审计助理, I want to see the purpose statement for reference.

#### Acceptance Criteria

1. THE GtA271ItAuditMemo SHALL render a purpose section as read-only text (el-alert info style)
2. THE Purpose_Section SHALL contain the standard IT audit memo purpose statement

### Requirement 5: IT团队表

**User Story:** As a 现场经理, I want to record the IT audit team members.

#### Acceptance Criteria

1. THE GtA271ItAuditMemo SHALL render a dynamic table with columns: 序号, 姓名, 职级
2. THE IT_Team_Table SHALL support adding new rows via "添加成员" button
3. THE IT_Team_Table SHALL support deleting rows via row-level delete icon (with confirmation)
4. THE IT_Team_Table SHALL display default 6 rows (expandable)
5. WHEN any row changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-team-{row_index}`

### Requirement 6: 章节一（了解信息系统环境）

**User Story:** As a 审计助理, I want to describe the IT system environment with cross-reference to B22A-4-3.

#### Acceptance Criteria

1. THE Chapter_1 card SHALL contain a textarea with autosize (min 4 rows) for system environment description
2. THE Chapter_1 card SHALL display a GtIndexChip linking to B22A-4-3
3. WHEN content changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-ch1-content`

### Requirement 7: 章节二（IT风险和一般控制）

**User Story:** As a 审计助理, I want to describe IT risks and general controls with cross-reference to C22.

#### Acceptance Criteria

1. THE Chapter_2 card SHALL contain a textarea with autosize (min 4 rows) for IT risk and control description
2. THE Chapter_2 card SHALL display a GtIndexChip linking to C22
3. WHEN content changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-ch2-content`

### Requirement 8: 章节三（IT一般控制结论）

**User Story:** As a 审计助理, I want to select the ITGC conclusion with conditional deficiency section.

#### Acceptance Criteria

1. THE Chapter_3 card SHALL contain an el-radio-group with 3 options: "部分有效", "没有有效", "已有效"
2. WHEN conclusion is NOT "已有效", THE Chapter_3 SHALL expand a textarea for deficiency description
3. WHEN conclusion is "已有效", THE deficiency textarea SHALL be hidden
4. WHEN conclusion changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-ch3-conclusion`
5. WHEN deficiency content changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-ch3-deficiency`

### Requirement 9: 章节四（IT一般控制缺陷）

**User Story:** As a 审计助理, I want to describe ITGC deficiencies with cross-reference to C21-1.

#### Acceptance Criteria

1. THE Chapter_4 card SHALL be conditionally visible: shown WHEN chapter 3 conclusion is NOT "已有效"
2. THE Chapter_4 card SHALL contain a textarea with autosize (min 4 rows) for deficiency details
3. THE Chapter_4 card SHALL display a GtIndexChip linking to C21-1
4. WHEN content changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-ch4-content`

### Requirement 10: 章节五（信息处理控制）

**User Story:** As a 审计助理, I want to describe information processing controls with cross-reference to B23-15.

#### Acceptance Criteria

1. THE Chapter_5 card SHALL contain a textarea with autosize (min 4 rows) for processing control description
2. THE Chapter_5 card SHALL display a GtIndexChip linking to B23-15
3. WHEN content changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-ch5-content`

### Requirement 11: 章节六（信息处理控制结论）

**User Story:** As a 审计助理, I want to select the IPC conclusion with conditional deficiency section.

#### Acceptance Criteria

1. THE Chapter_6 card SHALL contain an el-radio-group with 3 options: "部分有效", "没有有效", "已有效"
2. WHEN conclusion is NOT "已有效", THE Chapter_6 SHALL expand a textarea for deficiency description
3. WHEN conclusion is "已有效", THE deficiency textarea SHALL be hidden
4. WHEN conclusion changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-ch6-conclusion`
5. WHEN deficiency content changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-ch6-deficiency`

### Requirement 12: 章节七（缺陷评估）

**User Story:** As a 审计助理, I want to provide an overall deficiency assessment and conclusion.

#### Acceptance Criteria

1. THE Chapter_7 card SHALL contain a textarea with autosize (min 4 rows) for assessment description
2. THE Chapter_7 card SHALL contain an el-input for conclusion summary
3. WHEN content changes, THE useA271ItAuditMemo SHALL debounce-save (2s) with item_id `a271-ch7-{field_id}`

### Requirement 13: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A27-1 data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A27-1, THE A271_Render_Strategy SHALL return: meta_info, header, purpose_text, it_team_table, chapters (7 entries), cross_references (4 wp_ids), project_context
2. THE A271_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a271-%'
3. THE A271_Render_Strategy SHALL load cross-reference wp_ids for B22A-4-3, C22, C21-1, B23-15

### Requirement 14: 数据持久化

**User Story:** As a 审计助理, I want all edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA271ItAuditMemo SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a271-{section}-{field_id}`
3. WHEN a save succeeds, THE GtA271ItAuditMemo SHALL update save status indicator to "已保存"
4. IF a save fails, THEN THE GtA271ItAuditMemo SHALL display el-message error
5. THE IT team table rows SHALL serialize as JSON in checklist_responses remark field
