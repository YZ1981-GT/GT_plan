# Requirements Document

## Introduction

A1-12（重大事项决定程序的履行情况检查表）需要实现双模式渲染：OnlyOffice DOCX 原始编辑模式 + HTML 结构化交互模式。用户可在两种模式间切换，OnlyOffice 编辑保存后 HTML 视图能刷新获取最新解析内容。

当前 A1-12 在 `wp_code_overrides.json` 中映射为 `skip`（由 A1 Dashboard 内嵌），`useA1SubWorkpapers.ts` 中 componentType 为 `checklist`，但后端未提供 `htmlData.template.sections` 数据导致空白渲染。本 spec 新增专属 componentType `a1-12-dual-checklist` 实现完整双模式。

## Glossary

- **Dual_Mode_Renderer**: A1-12 双模式渲染组件，提供 OnlyOffice 编辑和 HTML 结构化两种视图
- **DOCX_Mode**: OnlyOffice 在线编辑模式，保留原始 Word 文档格式可编辑
- **HTML_Mode**: 结构化 HTML 渲染模式，从 DOCX 内容解析为章节/条目结构，支持交互
- **Checklist_Parser**: 后端 DOCX 解析服务，将 A1-12 Word 文档解析为 `ChecklistHtmlData` 结构
- **Mode_Switcher**: 模式切换控件（Tab 或 SegmentedControl），控制 DOCX_Mode 与 HTML_Mode 切换
- **GtA1Dashboard**: A1 仪表盘主组件，A1-12 作为其内嵌 Tab 之一渲染
- **OnlyOffice**: 文档编辑服务（docx 在线编辑，JWT_ENABLED=false 开发环境）
- **ChecklistHtmlData**: GtChecklistTable 所需数据结构（template.sections/toc/stats + responses）

## Requirements

### Requirement 1: 双模式组件注册

**User Story:** 作为前端开发者，我需要一个专属 componentType 来区分 A1-12 的双模式渲染逻辑，使其不与通用 checklist 或 word-template 冲突。

#### Acceptance Criteria

1. THE Dual_Mode_Renderer SHALL 在 htmlRendererRegistry 中注册为 componentType `a1-12-dual-checklist`
2. THE wp_code_overrides.json SHALL 将 wp_code `A1-12` 映射为 `a1-12-dual-checklist`（替换当前 `skip`）
3. THE useA1SubWorkpapers SHALL 将 A1-12 Tab 的 componentType 更新为 `a1-12-dual-checklist`
4. THE GtA1Dashboard SHALL 识别 componentType `a1-12-dual-checklist` 并渲染对应的 Dual_Mode_Renderer 组件

### Requirement 2: OnlyOffice DOCX 编辑模式

**User Story:** 作为审计助理，我需要直接在浏览器中编辑 A1-12 原始 Word 文档，以便保留文档完整格式进行自由编辑。

#### Acceptance Criteria

1. WHEN 用户选择 DOCX_Mode, THE Dual_Mode_Renderer SHALL 加载 OnlyOffice 编辑器渲染 A1-12 底稿的 DOCX 文件
2. THE Dual_Mode_Renderer SHALL 通过 `/api/workpapers/{wpId}/onlyoffice-config` 获取 OnlyOffice 编辑器配置
3. WHILE DOCX_Mode 激活, THE OnlyOffice 编辑器 SHALL 支持文档内容编辑和保存
4. IF OnlyOffice 服务不可用, THEN THE Dual_Mode_Renderer SHALL 显示降级提示（下载/上传方式）
5. WHEN OnlyOffice 编辑器保存完成, THE Dual_Mode_Renderer SHALL 触发 `onDocumentSaved` 回调更新保存状态

### Requirement 3: HTML 结构化渲染模式

**User Story:** 作为审计助理，我需要以结构化 HTML 表格形式查看 A1-12 检查表内容，以便高效地逐项勾选、填写结论和备注。

#### Acceptance Criteria

1. WHEN 用户选择 HTML_Mode, THE Dual_Mode_Renderer SHALL 渲染 GtChecklistTable 组件
2. THE Dual_Mode_Renderer SHALL 将后端解析的 ChecklistHtmlData 传递给 GtChecklistTable
3. THE GtChecklistTable SHALL 渲染左侧目录导航树，支持章节快速跳转
4. THE GtChecklistTable SHALL 为每个 actionable 条目提供 Y/N/NA 勾选交互
5. THE GtChecklistTable SHALL 支持 ref_index chip 跳转到关联底稿
6. THE GtChecklistTable SHALL 显示实时进度统计（已填/总数 百分比）
7. THE GtChecklistTable SHALL 支持 debounce 2s 自动保存用户填写响应

### Requirement 4: 模式切换

**User Story:** 作为审计助理，我需要在 DOCX 原始编辑和 HTML 结构化视图之间自由切换，以便根据当前工作需要选择合适的编辑方式。

#### Acceptance Criteria

1. THE Dual_Mode_Renderer SHALL 在组件顶部提供模式切换控件（SegmentedControl 形态）
2. WHEN 用户点击 Mode_Switcher 的「Word 编辑」选项, THE Dual_Mode_Renderer SHALL 切换到 DOCX_Mode
3. WHEN 用户点击 Mode_Switcher 的「结构化视图」选项, THE Dual_Mode_Renderer SHALL 切换到 HTML_Mode
4. THE Mode_Switcher SHALL 默认选中 HTML_Mode（结构化视图为主要工作模式）
5. WHILE 模式切换进行中, THE Dual_Mode_Renderer SHALL 显示 loading 状态防止重复操作

### Requirement 5: 数据同步

**User Story:** 作为审计助理，我在 OnlyOffice 中编辑保存文档后，需要 HTML 结构化视图能反映最新内容，以便两种视图的数据保持一致。

#### Acceptance Criteria

1. WHEN 用户从 DOCX_Mode 切换到 HTML_Mode, THE Dual_Mode_Renderer SHALL 重新请求后端获取最新 ChecklistHtmlData
2. WHEN 后端返回更新的 ChecklistHtmlData, THE GtChecklistTable SHALL 刷新渲染最新章节内容
3. THE Dual_Mode_Renderer SHALL 保留用户在 HTML_Mode 中已填写的 checklist_responses（不因模式切换丢失）
4. IF 后端解析 DOCX 失败, THEN THE Dual_Mode_Renderer SHALL 显示错误提示并保持当前 HTML_Mode 数据不变

### Requirement 6: 后端 DOCX 解析服务

**User Story:** 作为系统，我需要将 A1-12 的 DOCX 文件内容解析为结构化的 ChecklistHtmlData 格式，以便前端 HTML_Mode 能正确渲染。

#### Acceptance Criteria

1. THE Checklist_Parser SHALL 从 A1-12 底稿关联的 DOCX 文件中提取章节结构（sections）
2. THE Checklist_Parser SHALL 为每个章节生成目录条目（toc）和统计信息（stats）
3. THE Checklist_Parser SHALL 将 DOCX 中的表格行解析为 ChecklistItem 列表（type: actionable/guidance/header）
4. THE Checklist_Parser SHALL 为每个 actionable 条目生成唯一 id（基于章节索引+行号）
5. WHEN render-config API 被请求且 componentType 为 `a1-12-dual-checklist`, THE 后端 SHALL 返回包含 `htmlData.template` 的完整 ChecklistHtmlData 结构
6. IF DOCX 文件不存在或格式异常, THEN THE Checklist_Parser SHALL 返回空 sections 并在日志中记录警告

### Requirement 7: 后端 DOCX 解析——Pretty Print 与 Round-Trip

**User Story:** 作为系统，我需要确保 DOCX 解析结果可以正确回写为 DOCX 格式，以保证数据完整性。

#### Acceptance Criteria

1. THE Checklist_Parser SHALL 提供 `format_to_docx` 方法将 ChecklistHtmlData 格式化回 DOCX 结构描述
2. FOR ALL 合法的 ChecklistHtmlData 对象, 解析然后格式化然后再解析 SHALL 产生等价的对象（round-trip property）
3. THE Checklist_Parser SHALL 保留 DOCX 中的原始章节标题文本（不截断不修改）
4. THE Checklist_Parser SHALL 保留 actionable 条目的完整描述文本（含换行和特殊字符）
