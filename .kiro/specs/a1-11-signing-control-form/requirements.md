# Requirements Document

## Introduction

A1-11 业务报告签发流转控制表是审计报告签发流程的核心控制表。当前实现 `wp-popup-signing` 仅包含 2-4 行签字区域，远不能覆盖原 Excel 模板（含 37 处合并单元格、完整字段区、签字流转区、报告管理区、修改区、注释区）的完整业务需求。

本 spec 定义一个精修 HTML 专用组件 `a1-11-signing-form`，替代 `wp-popup-signing`，完整还原 Excel 模板 "A1-11 报告签发" sheet 的所有字段和流转逻辑，注册到 `htmlRendererRegistry`，数据持久化复用 `checklist_responses` 表。

## Glossary

- **Signing_Form**: A1-11 业务报告签发流转控制表 Vue 组件（componentType = `a1-11-signing-form`）
- **Signing_Workflow**: 签字流转区，包含项目负责经理、项目合伙人、质控复核人、技术复核人、IT专家、税务专家六个签字槽位
- **Report_Management**: 报告管理区，包含部门、文号、份数、打字校对/打印/印章管理员签字
- **Amendment_Section**: 已签发报告修改区，记录修改原因和各级重新签字
- **Auto_Fill**: 从项目上下文（entity_name、audit_period_end 等）自动填充字段
- **checklist_responses**: 数据持久化表，通过 item_id 前缀分区标识各字段
- **htmlRendererRegistry**: 前端 componentType → Vue 组件的单一来源注册表
- **Project_Context**: 项目级元数据（委托人名称、业务约定书编号、企业性质等）

## Requirements

### Requirement 1: 完整字段渲染

**User Story:** As a 审计项目负责经理, I want 在 A1-11 中看到与原 Excel 模板完全一致的所有字段区域, so that 不再需要线下填写 Excel 再上传。

#### Acceptance Criteria

1. THE Signing_Form SHALL 渲染以下基本信息字段：委托人名称、业务约定书编号、企业性质、行业、鉴证业务分类、首次承接（是/否）
2. THE Signing_Form SHALL 渲染报告信息字段：报告标题、收件人全称、附送说明
3. THE Signing_Form SHALL 渲染签字流转区（Signing_Workflow）：项目负责经理、项目合伙人、质控复核人（质量控制复核合伙人）、技术复核人（EQCR）、IT专家、税务专家，每个槽位含签字人姓名、签字状态、日期
4. THE Signing_Form SHALL 渲染报告管理区（Report_Management）：部门、文号、份数（中文报告份数 + 外文报告份数）、打字校对签字+日期、打印签字+日期、印章管理员签字+日期
5. THE Signing_Form SHALL 渲染已签发报告修改区（Amendment_Section）：修改原因文本区 + 各级重新签字（项目经理/合伙人/质控/技术复核）
6. THE Signing_Form SHALL 渲染注释区：含审计报告日期与声明书日期相关的 CAS 准则引用说明（静态文本）
7. THE Signing_Form SHALL 使用中文 UI 标签，标签文字与原 Excel 模板完全一致

### Requirement 2: 项目上下文自动填充

**User Story:** As a 审计助理, I want 打开 A1-11 时系统自动从项目信息填入委托人名称等已知字段, so that 减少重复录入并保持数据一致。

#### Acceptance Criteria

1. WHEN Signing_Form 加载时, THE Signing_Form SHALL 从 Project_Context 自动填充委托人名称（entity_name）
2. WHEN Signing_Form 加载时, THE Signing_Form SHALL 从 Project_Context 自动填充审计期间截止日（audit_period_end）到相关日期字段
3. WHEN Signing_Form 加载时, THE Signing_Form SHALL 从 Project_Context 自动填充企业性质（entity_type）和行业（industry）字段
4. WHEN Signing_Form 加载时, THE Signing_Form SHALL 从 Project_Context 自动填充业务约定书编号（engagement_letter_no），若项目信息中存在该字段
5. WHEN 用户手动修改自动填充的字段值时, THE Signing_Form SHALL 保存用户输入值并不再覆盖该字段
6. WHEN Project_Context 中对应字段为空时, THE Signing_Form SHALL 保留字段为空白可编辑状态

### Requirement 3: 签字流转工作流

**User Story:** As a 项目合伙人, I want 按流程签字并看到其他角色的签字状态, so that 确保报告签发流程完整合规。

#### Acceptance Criteria

1. THE Signing_Form SHALL 为每个签字槽位提供"签字"按钮和日期选择器
2. WHEN 用户点击"签字"按钮时, THE Signing_Form SHALL 记录当前用户姓名、设置签字状态为已签、默认日期为当天
3. WHEN 签字流转区中某一级尚未签字时, THE Signing_Form SHALL 将该级签字按钮显示为可操作状态（不强制顺序签字，允许并行签字）
4. WHILE 某签字槽位已签字时, THE Signing_Form SHALL 将该槽位显示为已完成状态（显示签字人姓名+日期，签字按钮置灰）
5. WHEN 业务分类为 B 或 C 类项目时, THE Signing_Form SHALL 仅要求项目负责经理和项目合伙人签字，质控复核人和技术复核人标记为"不适用"
6. WHEN 业务分类为 A 类项目时, THE Signing_Form SHALL 要求全部六个签字槽位（含 IT 专家和税务专家根据项目实际需要选填）
7. THE Signing_Form SHALL 在签字流转区顶部显示整体签字完成进度（如"已签 3/6"）

### Requirement 4: 数据持久化

**User Story:** As a 现场经理, I want A1-11 的所有填写内容自动保存, so that 不会因意外关闭而丢失数据。

#### Acceptance Criteria

1. THE Signing_Form SHALL 将所有字段值存储到 checklist_responses 表，使用 item_id 前缀 `A1-11-` 区分不同字段（如 `A1-11-entity-name`、`A1-11-sign-pm`、`A1-11-report-title`）
2. WHEN 用户编辑任意文本字段后停止输入 2 秒时, THE Signing_Form SHALL 自动保存变更到后端（debounce 2000ms）
3. WHEN 用户执行签字操作时, THE Signing_Form SHALL 立即保存签字状态（不等待 debounce）
4. WHEN 保存失败时, THE Signing_Form SHALL 显示错误提示并保留本地编辑内容（不回滚）
5. WHEN Signing_Form 组件卸载时, THE Signing_Form SHALL 立即刷新未保存的变更
6. THE Signing_Form SHALL 通过 `PUT /api/workpapers/{wp_id}/checklist-responses` 接口批量保存，请求体包含 project_id 和 items 数组

### Requirement 5: 只读模式

**User Story:** As a 质量控制复核合伙人, I want 所有签字完成后表格自动锁定为只读, so that 防止已签发报告被意外修改。

#### Acceptance Criteria

1. WHEN 所有必填签字槽位均已完成签字时, THE Signing_Form SHALL 自动进入只读模式（所有字段不可编辑、签字按钮禁用）
2. WHILE Signing_Form 处于只读模式时, THE Signing_Form SHALL 在顶部显示"已完成签发"状态横幅（绿色）
3. WHEN 外部传入 `readonly` prop 为 true 时, THE Signing_Form SHALL 强制进入只读模式（无论签字是否完成）
4. WHILE Signing_Form 处于只读模式时, THE Signing_Form SHALL 仍允许查看所有字段内容但禁止编辑
5. WHEN 需要修改已签发报告时, THE Signing_Form SHALL 仅通过"已签发报告修改区"（Amendment_Section）流程进行，填写修改原因后开启重新签字

### Requirement 6: 打印与导出兼容

**User Story:** As a 审计助理, I want 将填写完成的 A1-11 打印为 A4 纸质版, so that 满足归档和客户要求。

#### Acceptance Criteria

1. THE Signing_Form SHALL 提供打印样式表（@media print），输出为 A4 竖版单页或双页
2. WHEN 用户触发打印时, THE Signing_Form SHALL 隐藏所有交互控件（按钮、输入框边框），仅保留文本内容和签字结果
3. THE Signing_Form SHALL 在打印输出中保持与原 Excel 模板一致的表格边框和布局结构
4. THE Signing_Form SHALL 在打印输出中正确显示签字人姓名和日期（替代签字按钮位置）

### Requirement 7: 组件注册与路由

**User Story:** As a 开发者, I want 新组件正确注册到 htmlRendererRegistry 并通过 wp_code_overrides 路由, so that 打开 A1-11 底稿时自动渲染新组件。

#### Acceptance Criteria

1. THE Signing_Form SHALL 在 htmlRendererRegistry 中注册 componentType 为 `a1-11-signing-form`，contextProps 为 `standard`
2. THE Signing_Form SHALL 在 wp_code_overrides.json 中将 `A1-11` 映射从 `wp-popup-signing` 更新为 `a1-11-signing-form`
3. THE Signing_Form SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly
4. THE Signing_Form SHALL emit `save` 事件（保存成功后）和 `completed` 事件（全部签字完成时）
5. WHEN 后端 render-config 返回 componentType 为 `a1-11-signing-form` 时, THE 前端路由 SHALL 正确加载 Signing_Form 组件

### Requirement 8: 响应式布局

**User Story:** As a 现场经理, I want 在不同屏幕尺寸下都能正常使用 A1-11 表格, so that 可以在笔记本和大屏显示器上流畅操作。

#### Acceptance Criteria

1. THE Signing_Form SHALL 采用表格布局还原原 Excel 合并单元格结构（使用 HTML table 或 CSS Grid）
2. WHEN 视窗宽度小于 768px 时, THE Signing_Form SHALL 将多列布局折叠为单列堆叠布局
3. THE Signing_Form SHALL 确保所有输入框在最小 320px 宽度下仍可正常操作
4. THE Signing_Form SHALL 在大屏（≥1200px）时保持与原 Excel 模板相近的视觉比例

### Requirement 9: 已签发报告修改流程

**User Story:** As a 项目合伙人, I want 在报告已签发后如需修改能走修改流程, so that 修改有据可查且合规。

#### Acceptance Criteria

1. WHEN 用户在已签发状态下点击"启动修改"时, THE Signing_Form SHALL 展开 Amendment_Section 区域
2. THE Amendment_Section SHALL 要求填写修改原因（必填文本域，不可为空）
3. WHEN 修改原因填写完成后, THE Amendment_Section SHALL 开启各级重新签字槽位（项目经理 → 合伙人 → 质控 → 技术复核）
4. WHEN Amendment_Section 中所有必填签字完成时, THE Signing_Form SHALL 重新进入只读模式
5. THE Signing_Form SHALL 保留修改历史（每次修改的原因+签字记录），item_id 使用 `A1-11-amend-{序号}-` 前缀
