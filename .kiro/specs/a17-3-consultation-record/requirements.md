# Requirements Document

## Introduction

为 A17-3（业务咨询记录）创建专属 HTML 组件，将原 21 页/8 表的 Word 模板转化为元信息表 + 4 章卡片的结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a173-{section}-{field_id}`）。

核心价值：结构化记录审计业务咨询的全过程——从咨询事项描述到专业技术部反馈再到技术委员会意见。AI 按钮预留：基于咨询问题自动查询相关准则。

新增 componentType: `a17-3-consultation-record`，通过 wp_code_overrides 保持 skip 状态（在 A17 bundle Tab 内嵌渲染）。

## Glossary

- **GtA173ConsultationRecord**: 前端主组件（~350 行），渲染元信息 + 4 章卡片
- **useA173ConsultationRecord**: 前端 composable，管理数据加载/保存
- **A173_Render_Strategy**: 后端渲染策略（`_a173_consultation_record.py`），从 checklist_responses 加载已填数据
- **Meta_Info_Table**: 顶部元信息表格（业务部门/客户/类型/期间）
- **Section_Card**: 章节卡片，含 textarea 内容区

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A17-3 to use a dedicated componentType, so that the structured consultation form replaces the generic word-template rendering.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A17-3" to componentType "a17-3-consultation-record" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a17-3-consultation-record" mapping to GtA173ConsultationRecord component
3. THE RENDERER_DISPATCH SHALL include a "a17-3-consultation-record" strategy function that invokes A173_Render_Strategy
4. THE VALID_COMPONENT_TYPES list SHALL include "a17-3-consultation-record"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A17-3, so that I can use the most efficient mode.

#### Acceptance Criteria

1. WHEN A17-3 workpaper loads, THE GtA173ConsultationRecord SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA173ConsultationRecord SHALL render GtOnlyOfficeSheet for the A17-3 docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option and display tooltip "在线编辑不可用"
5. WHEN the user switches modes, THE GtA173ConsultationRecord SHALL flush all pending saves before switching

### Requirement 3: 元信息表格

**User Story:** As a 审计助理, I want the meta information table auto-filled from project context, so that I don't need to manually type standard fields.

#### Acceptance Criteria

1. THE GtA173ConsultationRecord SHALL render a Meta_Info_Table with fields: 业务部门, 客户名称, 咨询类型(el-select), 审计期间
2. THE Meta_Info_Table SHALL auto-fill 客户名称 from project client_name and 审计期间 from project period
3. THE 咨询类型 el-select SHALL include options: 会计处理, 审计程序, 独立性, 职业道德, 其他
4. WHEN any meta field changes, THE useA173ConsultationRecord SHALL debounce-save (2s) with item_id `a173-meta-{field_id}`

### Requirement 4: 第一节 — 咨询事项描述

**User Story:** As a 审计助理, I want to describe the consultation matter in detail with three sub-sections, so that the consultation context is complete.

#### Acceptance Criteria

1. THE Section_Card 一 SHALL render 3 textarea sub-fields: 业务概况, 问题背景, 相关文件
2. EACH textarea SHALL have autosize (min 3 rows) and placeholder text
3. THE 相关文件 field SHALL support optional file reference tags (el-tag add/remove)
4. WHEN content changes, THE useA173ConsultationRecord SHALL debounce-save (2s) with item_id `a173-sec1-{sub_field}`
5. THE Section_Card 一 SHALL have an AI button (disabled, tooltip "AI 根据咨询问题自动查询相关准则即将上线")

### Requirement 5: 第二节 — 项目组初步讨论意见

**User Story:** As a 现场经理, I want to record the team's preliminary discussion, so that the initial position is documented before formal consultation.

#### Acceptance Criteria

1. THE Section_Card 二 SHALL render a single textarea for recording preliminary discussion opinion
2. THE textarea SHALL have autosize (min 4 rows)
3. WHEN content changes, THE useA173ConsultationRecord SHALL debounce-save (2s) with item_id `a173-sec2-opinion`

### Requirement 6: 第三节 — 专业技术部反馈

**User Story:** As a 审计助理, I want to record professional technical department feedback with standards references, so that the formal guidance is documented.

#### Acceptance Criteria

1. THE Section_Card 三 SHALL render 2 textarea sub-fields: 准则依据, 回复意见
2. THE 准则依据 field SHALL have placeholder "引用的会计准则/审计准则条款"
3. WHEN content changes, THE useA173ConsultationRecord SHALL debounce-save (2s) with item_id `a173-sec3-{sub_field}`

### Requirement 7: 第四节 — 专业技术委员会意见及所外咨询回复

**User Story:** As a 业务合伙人, I want to record committee opinions and external consultation results, so that all levels of consultation are documented.

#### Acceptance Criteria

1. THE Section_Card 四 SHALL render a single textarea for committee/external opinions
2. THE textarea SHALL have autosize (min 4 rows)
3. WHEN content changes, THE useA173ConsultationRecord SHALL debounce-save (2s) with item_id `a173-sec4-opinion`

### Requirement 8: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A17-3 data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A17-3, THE A173_Render_Strategy SHALL return: meta_info (4 fields), sections (4 sections with current values), project_context (client_name, period, preparer)
2. THE A173_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a173-%'
3. THE file reference tags (section 1) SHALL be stored as JSON array in remark column

### Requirement 9: 数据持久化

**User Story:** As a 审计助理, I want all my edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA173ConsultationRecord SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a173-meta-{field_id}`, `a173-sec{N}-{field_id}`
3. WHEN a save succeeds, THE GtA173ConsultationRecord SHALL update save status to "已保存"
4. IF a save fails, THEN THE GtA173ConsultationRecord SHALL display el-message error and mark status as "未保存"
