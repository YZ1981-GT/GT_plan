# Requirements Document

## Introduction

为 A9-2（向治理层通报内部控制缺陷沟通函）复用现有 GtA91DeficiencyLetter 组件，通过 `variant` prop 区分管理层/治理层两种模式。治理层模式差异：收件人=董事会/监事会/审计委员会；缺陷只列重大+重要（无"一般缺陷"段落）；无管理层回复区（Section 7 隐藏）。

新增 componentType: `a9-2-deficiency-letter-governance`，映射到同一 GtA91DeficiencyLetter 组件（传 `variant='governance'`），后端共用渲染策略（参数化 variant）。

## Glossary

- **GtA91DeficiencyLetter**: 前端主组件，通过 `variant` prop 支持 management/governance 两种模式
- **Variant**: 组件模式标识，`'management'`（A9-1）或 `'governance'`（A9-2）
- **Governance_Addressee**: 治理层收件人（董事会/监事会/审计委员会）
- **A92_Render_Strategy**: 后端渲染策略，复用 A91 逻辑但返回 variant='governance' + 过滤一般缺陷

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A9-2 to use a dedicated componentType mapped to the same component with governance variant, so that the governance letter reuses the management letter logic.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A9-2" to componentType "a9-2-deficiency-letter-governance"
2. THE htmlRendererRegistry SHALL register componentType "a9-2-deficiency-letter-governance" mapping to GtA91DeficiencyLetter component
3. THE RENDERER_DISPATCH SHALL include an "a9-2-deficiency-letter-governance" strategy function that invokes A92_Render_Strategy
4. THE VALID_COMPONENT_TYPES list SHALL include "a9-2-deficiency-letter-governance"

### Requirement 2: variant prop 传递

**User Story:** As a 前端开发者, I want htmlRendererRegistry to pass variant='governance' when rendering A9-2, so that the component hides governance-irrelevant sections.

#### Acceptance Criteria

1. WHEN htmlRendererRegistry resolves componentType "a9-2-deficiency-letter-governance", THE registry SHALL pass prop `variant="governance"` to GtA91DeficiencyLetter
2. THE GtA91DeficiencyLetter SHALL accept a new prop `variant` with type `'management' | 'governance'` defaulting to `'management'`

### Requirement 3: 治理层收件人差异

**User Story:** As a 审计助理, I want the governance letter addressee to show "董事会/监事会/审计委员会", so that the letter is correctly addressed.

#### Acceptance Criteria

1. WHILE variant is "governance", THE Section 1 (收件人) SHALL display format: `{client_name}董事会\监事会\审计委员会：`
2. WHILE variant is "management", THE Section 1 (收件人) SHALL display format: `{client_name}总经理\财务总监\…：`

### Requirement 4: 缺陷分组限制（无一般缺陷）

**User Story:** As a 审计助理, I want the governance letter to only show major and significant deficiencies, so that it complies with CAS requirements for governance communication.

#### Acceptance Criteria

1. WHILE variant is "governance", THE Section 4 (内部控制缺陷) SHALL render only two severity sub-groups: (一) 重大缺陷, (二) 重要缺陷
2. WHILE variant is "governance", THE Section 4 SHALL hide the (三) 一般缺陷 sub-group entirely
3. WHILE variant is "governance", THE A92_Render_Strategy SHALL return deficiency_list with only "major" and "significant" keys (no "general")
4. WHILE variant is "management", THE Section 4 SHALL render all three severity sub-groups as before

### Requirement 5: 管理层回复区隐藏

**User Story:** As a 审计助理, I want the governance letter to omit the management response section, so that the form matches the CAS requirement that governance letters do not require management sign-back.

#### Acceptance Criteria

1. WHILE variant is "governance", THE GtA91DeficiencyLetter SHALL hide Section 7 (管理层回复区) entirely
2. WHILE variant is "governance", THE left navigation SHALL display only 6 section links (excluding 管理层回复区)
3. WHILE variant is "management", THE Section 7 SHALL render normally

### Requirement 6: 后端渲染策略参数化

**User Story:** As a 前端开发者, I want the render strategy to return variant-appropriate data, so that the frontend receives only relevant data for each mode.

#### Acceptance Criteria

1. WHEN render-config is requested for A9-2, THE A92_Render_Strategy SHALL return the same structure as A91 but with: variant="governance", deficiency_list excluding "general" key, section_data excluding "response" key
2. THE A92_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a92-%' (separate namespace from A9-1)
3. IF the B22B workpaper does not exist for the project, THEN THE A92_Render_Strategy SHALL return an empty deficiency_list with a warning message "未找到B22B内控缺陷评价表"

### Requirement 7: 数据持久化（独立命名空间）

**User Story:** As a 审计助理, I want A9-2 edits saved independently from A9-1, so that both letters can coexist without data collision.

#### Acceptance Criteria

1. WHEN any editable field in A9-2 changes, THE useA91DeficiencyLetter composable SHALL save to checklist_responses with item_id format `a92-{section}-{field_id}`
2. THE A9-2 deficiency list SHALL be serialized with item_id `a92-deficiency-{severity}` (only major and significant)
