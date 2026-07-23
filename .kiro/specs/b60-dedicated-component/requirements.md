# Requirements Document

## Introduction

B60（总体审计策略及具体审计计划）是一个多章节叙述式底稿，当前被映射为 `word-template` componentType。word-template 渲染器仅支持编辑 `${field_id}` 占位符或少量 legacy 中文标记（××公司、202X年），无法为审计师提供结构化的章节编辑界面。B60 主文档包含多个策略章节（审计总体策略、重大关注事项、审计方法、审计资源分配等），需要类似 A17 模式的 Bundle + 章节编辑器方案。

本 spec 将 B60 系列底稿从 `word-template` 迁移为专用 HTML 组件，参照 A17（GtA17Bundle/GtA17Summary）架构模式：顶层 Bundle 通过 el-tabs 管理子底稿，主文档通过章节编辑器提供左侧导航 + 右侧富文本的编辑体验。

## Glossary

- **B60_Bundle**: 顶层聚合组件，通过 el-tabs 分发渲染 B60 系列全部子底稿
- **B60_Chapter_Editor**: B60 主文档章节编辑器，提供左侧章节导航 + 右侧内容编辑区
- **Chapter_Definition**: 章节定义数据结构，描述 B60 主文档的章节树（id、标题、层级、是否必填、数据源提示）
- **Applicability_Matrix**: B60 适用性矩阵，控制子底稿（B60-2-x、B60-3、B60A~D）是否适用当前项目
- **htmlRendererRegistry**: 前端 componentType→Vue 组件映射注册表（单一来源）
- **wp_code_overrides**: 后端 wp_code→componentType 精确映射 JSON（热重载）
- **RENDERER_DISPATCH**: 后端 componentType→render 策略函数映射
- **checklist_responses**: 底稿数据持久化表（wp_id, item_id, conclusion, remark）
- **WpInlinePopup**: 现有弹窗组件，用于打开 docx 子底稿（OnlyOffice 编辑/模板下载）
- **B60_Series**: B60 全部 10 个子文档的集合（1 主文档 + 1 工时表 + 8 独立 docx）

## Requirements

### Requirement 1: B60 Bundle 组件注册与路由

**User Story:** As a 审计师, I want B60 底稿在平台中以专用组件渲染而非 word-template 模式, so that 我能通过结构化界面编辑审计策略内容。

#### Acceptance Criteria

1. WHEN B60 底稿被打开, THE B60_Bundle SHALL 通过 htmlRendererRegistry 中注册的 `b60-strategy` componentType 渲染，且该注册条目包含 defineAsyncComponent 懒加载引用和 contextProps 策略声明
2. THE wp_code_overrides SHALL 将 `B60` 以及全部 B60 系列子底稿编码（B60-1、B60-2-1、B60-2-2、B60-2-3、B60-3、B60A、B60B、B60C、B60D）映射为 `b60-strategy` componentType
3. THE RENDERER_DISPATCH SHALL 注册 `b60-strategy` 键对应的后端 render 策略函数，该函数返回包含 html_data 和 responses_snapshot 的渲染配置
4. WHEN B60_Bundle 加载完成, THE B60_Bundle SHALL 通过 `GET /api/workpapers/{wpId}/wp-index` 查询当前项目下全部 B60 系列子底稿（wp_code 前缀匹配 `B60-` 或精确匹配 `B60A`~`B60D`），并构建 wpIdMap（wp_code → wp_id 映射），映射值必须使用 item.wp_id 而非 item.id
5. IF wp_index 查询失败或返回空结果, THEN THE B60_Bundle SHALL 渲染空状态占位提示"B60 系列子底稿尚未生成"，且不阻断主文档 Tab 的编辑功能

### Requirement 2: B60 Bundle Tab 导航结构

**User Story:** As a 审计师, I want 一个统一的 Tab 界面浏览 B60 系列全部子底稿, so that 我不需要在多个底稿之间反复切换。

#### Acceptance Criteria

1. THE B60_Bundle SHALL 展示以下固定顺序的 Tab 定义：B60 主文档（审计策略章节编辑器）、B60-1（工时表）、B60-2-1（IT复杂性判断表）、B60-2-2（IT审计进场前通知表）、B60-2-3（IT审计计划备忘录）、B60-3（评估专家工作计划）、B60A（对内控审计的特殊考虑）、B60B（对IPO申报财务报表审计的特殊考虑）、B60C（对国有企业年度财务报表审计的特殊考虑）、B60D（向监管机构报送策略和计划的函副本），其中 B60 主文档 Tab 恒可见，其余 Tab 仅当 wpIdMap 中对应 wp_code 有值时显示
2. WHEN 某子底稿 wp_code 在 wpIdMap 中不存在对应 wp_id, THE B60_Bundle SHALL 隐藏该 Tab；IF 适用性矩阵标记该底稿为"适用"但 wp_id 不存在, THEN THE B60_Bundle SHALL 在 Tab 位置显示"该子底稿尚未生成"占位提示
3. WHEN B60-1 工时表 Tab 被点击, THE B60_Bundle SHALL emit `navigate-sheet` 事件并携带 B60-1 对应的 sheet_name，由 GtWpRenderer 跳转到工时表 sheet（复用现有 render-config xlsx 渲染）
4. WHEN docx 子底稿 Tab（B60-2-1、B60-2-2、B60-2-3、B60-3、B60A、B60B、B60C、B60D）被点击, THE B60_Bundle SHALL 将 wpIdMap 中对应的 wp_id 传递给内嵌的 WpInlinePopup 或 HTML 编辑器组件进行渲染
5. IF 子底稿渲染组件加载失败, THEN THE B60_Bundle SHALL 在对应 Tab 内容区显示 ErrorBoundary 错误提示，不影响其他 Tab 正常使用

### Requirement 3: B60 适用性矩阵

**User Story:** As a 审计师, I want 在 B60 顶部配置子底稿适用性, so that 不适用的子底稿不出现在编辑界面中。

#### Acceptance Criteria

1. THE B60_Bundle SHALL 在 Tab 区域上方展示适用性矩阵面板，以表格形式列出 B60-2-1、B60-2-2、B60-2-3、B60-3、B60A、B60B、B60C、B60D 共 8 个子底稿，每行包含子底稿编码、子底稿名称、适用条件描述文本（只读）及适用性勾选框（可编辑）
2. WHEN 审计师将某子底稿的适用性勾选框取消勾选（标记为"不适用"）, THE B60_Bundle SHALL 在 800ms 防抖后将全部适用性状态以 JSON 格式持久化到 checklist_responses（item_id = `B60-applicability`，remark 字段存储 `{[wp_code]: boolean}` 映射），并立即隐藏对应 Tab
3. WHEN B60_Bundle 加载时从 checklist_responses 中读取到 item_id = `B60-applicability` 的已存记录, THE B60_Bundle SHALL 解析其 remark 字段中的 JSON 映射并恢复各子底稿的适用性勾选状态，被标记为不适用的子底稿对应 Tab 隐藏
4. IF checklist_responses 中无 `B60-applicability` 记录或 remark 为空, THEN THE B60_Bundle SHALL 默认全部 8 个子底稿为"适用"状态（勾选框选中）

### Requirement 4: B60 主文档章节定义

**User Story:** As a 审计师, I want B60 主文档按标准章节结构呈现, so that 我能逐章编制审计策略且不遗漏必填内容。

#### Acceptance Criteria

1. WHEN B60 主文档 Tab 被激活, THE B60_Chapter_Editor SHALL 从后端 API `GET /api/b60/chapter-definitions` 加载章节定义列表，请求超时上限为 10 秒
2. THE Chapter_Definition SHALL 包含以下字段：chapter_id（唯一标识，格式 `B60-CH-{序号}`）、title（章节标题，最大 200 字符）、level（层级，取值 1、2 或 3）、required（是否必填，布尔值）、hint（编制提示文本，最大 2000 字符）、data_source（关联底稿提示，如"B50 风险评估"/"B10 项目基本信息"，最大 500 字符）
3. IF 后端 API 在 10 秒内未响应或返回非 2xx 状态码, THEN THE B60_Chapter_Editor SHALL 使用前端内置的默认章节定义数组作为降级数据源，并在界面顶部显示警告提示"章节定义加载失败，当前使用默认配置"
4. THE B60_Chapter_Editor SHALL 按 chapter_id 排序渲染章节列表，required 为 true 的章节标题旁显示红色必填标记，level=1 的章节作为顶级分组标题、level=2 作为子章节、level=3 作为细分条目

### Requirement 5: B60 章节编辑器 UI 布局

**User Story:** As a 审计师, I want 左侧章节导航 + 右侧内容编辑区的双栏布局, so that 我能快速定位和编辑各章节内容。

#### Acceptance Criteria

1. THE B60_Chapter_Editor SHALL 以左右双栏布局渲染：左侧章节导航面板（固定宽度 240px），右侧内容编辑区（flex: 1 自适应剩余宽度）
2. THE 左侧导航面板 SHALL 显示章节标题列表（按 level 缩进），每个章节标题左侧标注完成状态圆点指示器：已填写（remark 非空）= 绿色圆点、未填写且 required=false = 灰色圆点、必填未填（required=true 且 remark 为空）= 橙色圆点
3. WHEN 审计师点击左侧某章节标题, THE B60_Chapter_Editor SHALL 以 smooth 动画滚动右侧编辑区到对应章节 el-card 位置，并高亮该章节导航项 1 秒
4. THE 右侧编辑区 SHALL 为每个章节渲染独立的 el-card，卡片标题为章节 title，内含 el-input type="textarea" :autosize="{ minRows: 5, maxRows: 20 }" 用于编辑叙述内容
5. WHEN 章节 Chapter_Definition 的 hint 字段非空, THE B60_Chapter_Editor SHALL 在该章节 textarea 上方渲染编制提示（琥珀色左边线 details 折叠块，默认展开）

### Requirement 6: B60 章节内容持久化

**User Story:** As a 审计师, I want 编辑的章节内容自动保存, so that 我不会因为页面刷新丢失工作。

#### Acceptance Criteria

1. WHEN 审计师编辑章节 textarea 内容, THE B60_Chapter_Editor SHALL 以 800ms 防抖调用 `PUT /api/workpapers/{wpId}/checklist-responses` 保存，payload 为 `{ items: [{ item_id: chapter_id, conclusion: null, remark: 章节内容文本 }] }`
2. WHEN B60_Chapter_Editor 加载（onMounted）, THE B60_Chapter_Editor SHALL 从 render-config 返回的 responses_snapshot 或通过 `GET /api/workpapers/{wpId}/checklist-responses` 恢复各章节的已保存内容，按 item_id 匹配 chapter_id 填入对应 textarea
3. THE B60_Chapter_Editor SHALL 在章节编辑区顶部工具栏显示保存状态指示器：`saved`="✓ 已保存"（绿色）、`saving`="保存中…"（灰色动画）、`unsaved`="● 未保存"（橙色）
4. IF PUT 请求连续失败 3 次, THEN THE B60_Chapter_Editor SHALL 停止自动重试并显示 ElMessage.warning("保存失败，请检查网络后重试")

### Requirement 7: B60 章节 AI 辅助生成

**User Story:** As a 审计师, I want 每个章节旁有 AI 辅助按钮一键生成草稿, so that 我能快速完成策略文档初稿。

#### Acceptance Criteria

1. THE B60_Chapter_Editor SHALL 在每个章节 el-card 标题行右侧提供"🤖 AI 辅助"el-button（size=small, type=primary, plain）
2. WHEN 审计师点击 AI 辅助按钮, THE B60_Chapter_Editor SHALL 调用 `POST /api/workpapers/{wp_id}/ai/generate-text`，request body 包含 `{ section: chapter_id, prompt: chapter.hint, context: { client_name, audit_year, business_category, chapter_title } }`，context 值全部转为 string 类型
3. WHEN AI 生成成功返回, THE B60_Chapter_Editor SHALL 弹出确认对话框展示生成内容预览（el-dialog），审计师确认"采纳"后将内容填入对应章节 textarea（如已有内容则在末尾追加换行分隔），触发防抖保存
4. IF AI 生成请求失败或返回空内容, THEN THE B60_Chapter_Editor SHALL 显示 ElMessage.warning("AI 生成失败，请稍后重试")

### Requirement 8: B60 章节数据拉取

**User Story:** As a 审计师, I want 部分章节能从其他底稿自动拉取关键数据, so that 我不需要手工抄录已有信息。

#### Acceptance Criteria

1. WHERE Chapter_Definition 的 data_source 字段非空, THE B60_Chapter_Editor SHALL 在该章节 el-card 标题行显示"📥 从 {data_source.label} 带入"el-button（size=small）
2. WHEN 审计师点击"带入"按钮, THE B60_Chapter_Editor SHALL 调用 `POST /api/b60/chapters/{chapter_id}/pull`（request body 包含 project_id 和 wp_id），后端从关联底稿提取数据并返回 `{ content: string, source_label: string }`
3. WHEN pull 成功且 content 非空, THE B60_Chapter_Editor SHALL 将返回内容填入章节 textarea（追加模式，保留已有内容），并在章节标题下方显示数据来源标签（`GtIndexChip value="wp:{source_wp_code}"`）
4. IF pull 返回 content 为空或 API 返回 404, THEN THE B60_Chapter_Editor SHALL 显示 ElMessage.info("源底稿 {wp_code} 暂无数据，请先完成该底稿编制")

### Requirement 9: B60 后端 Render 策略

**User Story:** As a 开发者, I want 后端为 B60 提供专用 render 策略, so that 前端能获取章节定义和已保存数据。

#### Acceptance Criteria

1. THE RENDERER_DISPATCH SHALL 将 `b60-strategy` 键路由到 `backend/app/routers/wp_render_strategies/_b60_overall_strategy.py` 模块的 `render` 异步函数
2. WHEN render-config 被请求, THE render 策略 SHALL 返回 html_data dict 包含：`chapter_definitions`（章节定义列表，每项含 chapter_id/title/level/required/hint/data_source）、`responses_snapshot`（dict，key=item_id, value={conclusion, remark}，筛选 item_id 前缀 `B60-CH-` 或 `B60-applicability`）、`project_context`（dict 含 client_name/audit_year/business_category/partner_name）
3. THE render 策略 SHALL 通过 `SELECT item_id, conclusion, remark FROM checklist_responses WHERE wp_id = :wp_id AND (item_id LIKE 'B60-CH-%' OR item_id = 'B60-applicability')` 查询已保存内容
4. IF 查询 checklist_responses 异常, THEN render 策略 SHALL 记录 warning 日志并返回空 responses_snapshot（不阻断渲染）

### Requirement 10: B60 章节定义 API 端点

**User Story:** As a 开发者, I want 独立的章节定义 API, so that 前端可以动态加载章节结构而非硬编码。

#### Acceptance Criteria

1. THE 后端 SHALL 提供 `GET /api/b60/chapter-definitions` 端点，从静态 JSON 文件 `backend/app/data/b60_chapter_definitions.json` 加载并返回章节定义列表
2. THE 章节列表 SHALL 对齐 B60 源模板实际章节结构，至少包含以下一级章节：总体审计策略概述、重大关注事项与风险领域、审计方法与应对措施、审计范围（含组成部分）、时间安排与关键节点、审计资源分配、重要性水平确定、审计风险概述、其他需关注事项
3. THE 端点 SHALL 接受可选 query 参数 `project_id`（当前版本不做差异化处理，统一返回完整章节列表；为未来按项目类型 A/B/C 返回差异化章节预留接口）
4. THE 端点响应 SHALL 为 JSON 数组，HTTP 200，Content-Type: application/json

### Requirement 11: B60 版本链与复核接入

**User Story:** As a 审计师, I want B60 接入平台版本链和复核对话功能, so that 编辑历史可追溯且支持多人协作复核。

#### Acceptance Criteria

1. THE B60_Bundle SHALL 在 onMounted 中调用 useWorkpaperVersionToolbar(wpId) 接入版本链工具栏，渲染 GtWpVersionTrail 组件显示版本历史
2. WHEN 章节内容 PUT 保存成功后, THE B60_Chapter_Editor SHALL 调用 scheduleAutoSnapshot() 触发异步版本快照（与 A17 一致的 onAfterSave → scheduleAutoSnapshot 模式）
3. THE B60_Chapter_Editor SHALL 在每个章节 el-card 标题行右侧（AI 按钮之后）提供"💬"复核按钮，点击后调用 inject('openReviewDialog')(chapter_id) 打开复核对话（复用 useWorkpaperReviewProvide + GtWpReviewDialogHost）
4. THE B60_Bundle SHALL 在模板顶层挂载 GtWpReviewDialogHost 组件，provide openReviewDialog 函数供子组件 inject

### Requirement 12: B60 双模式支持

**User Story:** As a 审计师, I want 在 HTML 章节编辑器和 OnlyOffice 在线编辑之间切换, so that 我能在结构化编辑和自由排版之间灵活选择。

#### Acceptance Criteria

1. THE B60_Bundle SHALL 在主文档 Tab 内容区顶部提供 el-segmented 模式切换器，选项为 `['章节编辑', '在线编辑']`，默认选中"章节编辑"
2. WHEN 审计师选择"在线编辑"模式, THE B60_Bundle SHALL 先调用 B60_Chapter_Editor 的 flushPendingSaves()（确保未保存内容落盘），然后渲染 GtOnlyOfficeSheet 组件（:wp-id + :sheet-name 指向 B60 源 docx 对应的 sheet）
3. WHEN 从"在线编辑"切回"章节编辑"模式, THE B60_Chapter_Editor SHALL 重新从 `GET /api/workpapers/{wpId}/checklist-responses` 加载最新章节数据（OnlyOffice 编辑内容不自动同步到章节结构，两模式数据独立）
4. IF OnlyOffice 健康检查（`GET /api/workpapers/onlyoffice/health`）返回 unhealthy, THEN THE B60_Bundle SHALL 禁用"在线编辑"选项并在 el-tooltip 中显示"OnlyOffice 不可用"
