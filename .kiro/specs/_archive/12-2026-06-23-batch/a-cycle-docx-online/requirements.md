# Requirements Document

## Introduction

A 循环约有 25 个 docx 模板底稿当前未在 `wp_code_overrides.json` 中注册，导致用户只能下载/上传离线编辑。平台已具备 `word-template` componentType（通过 OnlyOffice 9.4.0 实现浏览器内 docx 编辑），且 A16 已作为该类型的成功案例运行。本功能将批量在线化剩余 A 循环 docx 底稿，并补充模板预填、签署状态跟踪、智能模板选择等配套能力，同时将若干非 docx 缺失底稿注册到正确的 componentType。

## Glossary

- **Override_Registry**: `wp_code_overrides.json` 文件，wp_code→componentType 的精确映射表（mtime 热重载）
- **Word_Template_Renderer**: 后端 `word-template` componentType 对应的渲染策略，通过 OnlyOffice DocumentServer 提供浏览器内 docx 编辑
- **Template_Prefiller**: 首次打开 word-template 底稿时，自动将项目信息占位符替换为实际值的后端服务
- **Sign_Status**: 底稿签署状态字段（draft/pending/signed），存储于 field_overrides 表，scope 格式 `word_template:{parent_wp_code}:{version_wp_code}`
- **Template_Selector**: 根据项目类型（IPO/上市/普通）自动判定应使用哪个 A16 变体版本的逻辑
- **Project_Info**: 项目基本信息，包含 entity_name（被审计单位名称）、period_end（审计期末日期）、preparer（编制人）、current_date（编制日期）
- **OnlyOffice_DocServer**: OnlyOffice Document Server 9.4.0，提供 docx/xlsx 浏览器端协同编辑

## Requirements

### Requirement 1: 批量注册 A 循环 docx 底稿为 word-template

**User Story:** As a 审计助理, I want 打开 A 循环的 docx 底稿时直接在浏览器内编辑, so that 无需下载/上传即可完成文档编制工作。

#### Acceptance Criteria

1. THE Override_Registry SHALL contain mappings for the following wp_codes to "word-template": A10-1, A11-1, A12-1, A16-1, A16-2, A16-3, A16-4, A16-5, A16-6, A16-7, A17-2-1, A17-3, A17-3-1, A17-4, A17-6, A18-1, A26-1, A26-2, A26-3, A26-4, A27-1, A8-1, A8-2, A9-1, A9-2.
2. WHEN a user opens any of the 25 registered wp_codes, THE Word_Template_Renderer SHALL return a render-config with componentType "word-template" and a valid OnlyOffice editor URL.
3. THE Override_Registry SHALL NOT modify existing mappings for A16 (parent), A17-1 (a17-summary), or A17-7 (independence-signing).
4. WHEN a wp_code is registered as word-template, THE Word_Template_Renderer SHALL locate the corresponding .docx template file from `backend/wp_templates/A/` by wp_code matching.
5. FOR ALL 25 newly registered wp_codes, the corresponding .docx template file SHALL exist in `backend/wp_templates/A/` directory.

### Requirement 2: 非 docx 缺失底稿的 Override 注册

**User Story:** As a 现场经理, I want A30/A28/A4-1/A7-1/A10/A12 等底稿使用正确的结构化组件渲染, so that 这些底稿不再降级为默认 OnlyOffice-sheet 而是用最合适的交互方式呈现。

#### Acceptance Criteria

1. THE Override_Registry SHALL map A30 to "checklist-table".
2. THE Override_Registry SHALL map A28 to "d-form-table".
3. THE Override_Registry SHALL map A4-1 to "audit-sheet".
4. THE Override_Registry SHALL map A7-1 to "audit-sheet".
5. THE Override_Registry SHALL map A10 to "a-program-console".
6. THE Override_Registry SHALL map A12 to "a-program-console".
7. WHEN a user opens any of the above 6 wp_codes, THE system SHALL render the workpaper using the specified componentType without fallback to default.

### Requirement 3: 模板预填项目信息

**User Story:** As a 审计助理, I want 首次打开 docx 底稿时项目名称、期末日期、编制人、日期等信息已自动填入, so that 无需手动输入重复的项目基本信息。

#### Acceptance Criteria

1. WHEN a word-template workpaper is opened for the first time in a project (no saved snapshot exists), THE Template_Prefiller SHALL replace placeholder tokens in the docx template with actual Project_Info values before serving to OnlyOffice.
2. THE Template_Prefiller SHALL support the following placeholder tokens: `{{entity_name}}` (被审计单位), `{{period_end}}` (审计期末日期, format: YYYY年MM月DD日), `{{preparer}}` (当前用户姓名), `{{current_date}}` (当前日期, format: YYYY年MM月DD日).
3. WHEN a placeholder token exists in the template but the corresponding Project_Info value is empty or unavailable, THE Template_Prefiller SHALL leave the token as-is (not replace with blank).
4. WHEN a saved snapshot already exists for the workpaper (user has previously edited), THE Template_Prefiller SHALL NOT re-apply placeholder replacement and SHALL serve the existing snapshot.
5. THE Template_Prefiller SHALL perform replacement on a per-project copy of the template, preserving the original template file unchanged.
6. WHEN placeholder replacement is performed, THE Template_Prefiller SHALL log the replaced fields for audit trail purposes.

### Requirement 4: 签署状态跟踪

**User Story:** As a 业务合伙人, I want 查看和更新 docx 底稿的签署状态（草稿/待签/已签）, so that 项目组成员清楚每份文档的签署进度。

#### Acceptance Criteria

1. THE system SHALL support three sign_status values for word-template workpapers: "draft" (草稿), "pending" (待签署), "signed" (已签署).
2. WHEN a word-template workpaper is first created, THE system SHALL default its sign_status to "draft".
3. WHEN a user updates the sign_status of a word-template workpaper, THE system SHALL persist the value via field_overrides with scope format `word_template:{parent_wp_code}:{wp_code}`.
4. THE render-config response for word-template workpapers SHALL include the current sign_status value.
5. WHEN sign_status is "signed", THE Word_Template_Renderer SHALL serve the document in read-only mode (OnlyOffice permissions.edit = false).
6. WHEN sign_status transitions from "signed" back to "draft" or "pending", THE Word_Template_Renderer SHALL restore edit permissions (requires 业务合伙人 or higher role).
7. THE system SHALL record the user_id and timestamp of each sign_status transition for audit trail.

### Requirement 5: A16 智能模板选择

**User Story:** As a 现场经理, I want 系统根据项目类型（IPO/上市公司/普通企业）自动推荐正确的管理层声明书版本, so that 无需手动判断使用 A16-1~A16-7 中的哪个变体。

#### Acceptance Criteria

1. WHEN a user opens A16 (parent workpaper), THE Template_Selector SHALL determine the recommended A16 variant based on project.business_category.
2. THE Template_Selector SHALL apply the following mapping rules:
   - business_category contains "IPO" → recommend A16-3 (IPO声明书)
   - business_category contains "上市" or "listed" → recommend A16-2 (整合审计声明书)
   - business_category contains "新三板" → recommend A16-5 (新三板声明书)
   - business_category contains "企业债" or "债券" → recommend A16-6 (企业债声明书)
   - otherwise → recommend A16-1 (企业会计准则通用声明书)
3. THE Template_Selector SHALL always recommend A16-7 (关联交易声明书) as an additional required document regardless of project type.
4. WHEN a recommended variant has not been created in the project, THE Template_Selector SHALL display a prompt suggesting creation with one-click action.
5. THE Template_Selector recommendation SHALL be overridable — the user MAY select any A16 variant regardless of the system recommendation.
6. THE render-config for A16 SHALL include a `recommended_version` field containing the wp_code of the recommended variant and a `all_versions` list of available A16-x variants.

### Requirement 6: 前端 word-template 编辑器统一体验

**User Story:** As a 审计助理, I want 所有 word-template 底稿有一致的编辑器 UI（工具栏、状态指示、保存行为）, so that 切换不同 docx 底稿时无学习成本。

#### Acceptance Criteria

1. THE Word_Template_Renderer SHALL display a unified toolbar above the OnlyOffice editor containing: sign_status indicator (color-coded badge), save status indicator, and export-to-local button.
2. WHEN the OnlyOffice editor triggers a save callback, THE system SHALL persist the document snapshot and update the workpaper's last_modified timestamp.
3. WHEN a network disconnection is detected during editing, THE Word_Template_Renderer SHALL display a warning banner and attempt reconnection.
4. THE Word_Template_Renderer SHALL display the document title (derived from wp_code + template name) in the toolbar area.
5. WHEN the user clicks export-to-local, THE system SHALL download the current document snapshot as a .docx file with filename format `{wp_code}_{entity_name}_{period_end}.docx`.

