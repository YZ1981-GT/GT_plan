# Requirements Document

## Introduction

B1-4 为"业务承接阶段尽职调查（预备调查）报告"，是 IPO 审计项目承接前的核心输出物。当前以 word-template 模式注册，仅支持简单双模式编辑。本需求将其升级为专属精美展示组件，支持 11 章卡片式结构化视图、LLM 知识库辅助内容生成、标准版/简化版双变体切换。

源模板为大型 Word 文档（629 段落、39 表、11 章），包含两个变体：
- **标准版**：适用于 IPO 项目，含"上市条件分析"章节
- **简化版**：适用于非 IPO 项目，省略上市条件章节

## Glossary

- **Due_Diligence_Report**：B1-4 尽职调查报告专属展示组件（前端 Vue 组件 + 后端渲染器）
- **Chapter_Card**：章节卡片，每章以 el-card 折叠面板呈现，内含结构化表单字段
- **Knowledge_Base_Service**：知识库参考服务，通过 ReferenceDocService 从知识库检索相关文档注入 LLM prompt
- **LLM_Generate_Service**：LLM 内容生成服务，调用 vLLM (Qwen3.5-27B) 为各章节生成建议稿
- **Variant**：报告变体（standard=标准版/simplified=简化版），通过 el-segmented 切换
- **Section_Data**：各章节持久化数据，存储于 checklist_responses 表（item_id 模式：`b14-{chapter}-{field}`）
- **Composable**：Vue 3 composition API 逻辑复用单元（useB14DueDiligence）
- **Navigation_Panel**：左侧导航面板，显示 11 章完成状态（sticky 定位 + scrollspy）
- **AI_Button**：各章节内的 AI 辅助按钮，点击触发 LLM 生成或润色

## Requirements

### Requirement 1: 组件注册与双模式切换

**User Story:** As a 审计助理, I want to 在底稿列表点击 B1-4 时看到专属精美组件而非纯 Word 编辑器, so that I can 高效浏览和编辑尽调报告结构化内容。

#### Acceptance Criteria

1. THE Due_Diligence_Report SHALL 注册为新 componentType `b1-4-due-diligence-report` 并加入 VALID_COMPONENT_TYPES 和 htmlRendererRegistry
2. WHEN 用户打开 B1-4 底稿, THE Due_Diligence_Report SHALL 默认展示"结构化视图"模式
3. THE Due_Diligence_Report SHALL 通过 el-segmented 提供"结构化视图"和"在线编辑"两种模式切换
4. WHEN 用户切换到"在线编辑"模式, THE Due_Diligence_Report SHALL 先 flush 待保存数据再加载 GtOnlyOfficeSheet
5. IF OnlyOffice 健康检查失败, THEN THE Due_Diligence_Report SHALL 隐藏"在线编辑"选项仅保留"结构化视图"
6. WHEN htmlData prop 为 null（bundle 内嵌场景）, THE Due_Diligence_Report SHALL 在 onMounted 中自行调用 render-config?force_component_type=b1-4-due-diligence-report 加载数据

### Requirement 2: 章节卡片结构化展示

**User Story:** As a 审计助理, I want to 以卡片式分章浏览尽调报告的 11 个章节, so that I can 清晰定位和编辑各章节内容。

#### Acceptance Criteria

1. THE Due_Diligence_Report SHALL 在结构化视图中以 el-collapse 折叠卡片形式展示以下 11 章：序言、报告概要、释义、公司基本情况、公司经营情况、财务信息分析、同行业比较、税项、内部控制、关联方关系及交易、公司存在的主要问题及建议
2. WHERE Variant 为 standard, THE Due_Diligence_Report SHALL 额外展示"上市条件分析"章节（插入在"关联方"与"主要问题"之间）和"财务尽职调查的结果"章节
3. WHEN 用户首次打开报告, THE Due_Diligence_Report SHALL 默认展开"序言"和"报告概要"两章，其余折叠
4. THE Chapter_Card SHALL 根据章节类型渲染对应表单控件：textarea 型（叙述性章节）、table 型（人员/对标/财务数据表）、mixed 型（含文本和表格的复合章节）
5. WHEN 章节包含子节（如"公司基本情况"含历史沿革/组织架构/人力资源三个子节）, THE Chapter_Card SHALL 在卡片内以嵌套分区（el-divider + sub-section）呈现各子节

### Requirement 3: 左侧导航面板

**User Story:** As a 审计助理, I want to 通过左侧导航快速跳转到目标章节, so that I can 在大型报告中高效定位。

#### Acceptance Criteria

1. THE Navigation_Panel SHALL 以 sticky 定位显示在结构化视图左侧，列出所有章节标题
2. WHEN 用户点击导航项, THE Navigation_Panel SHALL 平滑滚动到对应章节卡片
3. WHILE 用户滚动内容区域, THE Navigation_Panel SHALL 通过 scrollspy 高亮当前可见章节
4. THE Navigation_Panel SHALL 在每个章节标题前显示完成状态指示点（绿色=已填/灰色=未填）
5. THE Navigation_Panel SHALL 在底部显示整体完成度百分比进度条

### Requirement 4: 变体切换（标准版/简化版）

**User Story:** As a 现场经理, I want to 根据项目类型（IPO/非IPO）切换报告变体, so that I can 生成符合项目类型的尽调报告。

#### Acceptance Criteria

1. THE Due_Diligence_Report SHALL 在工具栏提供 el-segmented 变体选择器（"标准版" / "简化版"）
2. WHEN 用户选择"简化版", THE Due_Diligence_Report SHALL 隐藏"上市条件分析"和"财务尽职调查的结果"两章
3. WHEN 用户切换变体, THE Due_Diligence_Report SHALL 保留所有已填写数据（仅控制可见性不删除数据）
4. THE Due_Diligence_Report SHALL 将当前变体选择持久化到 checklist_responses（item_id=`b14-meta-variant`）
5. WHEN 项目上下文已标记为 IPO 项目, THE Due_Diligence_Report SHALL 默认选择"标准版"

### Requirement 5: 数据持久化与自动保存

**User Story:** As a 审计助理, I want to 编辑内容后自动保存, so that I can 不丢失工作成果且无需手动保存。

#### Acceptance Criteria

1. WHEN 用户修改任何章节字段, THE Due_Diligence_Report SHALL 在 2 秒 debounce 后自动保存到 checklist_responses
2. THE Due_Diligence_Report SHALL 使用 item_id 模式 `b14-{chapter_number}-{field_id}` 持久化各章节数据
3. THE Due_Diligence_Report SHALL 在工具栏显示保存状态指示（"保存中..."/"✓ 已保存"/"○ 未保存"）
4. WHEN 用户切换到"在线编辑"模式或离开页面, THE Due_Diligence_Report SHALL 立即 flush 所有待保存数据
5. THE Due_Diligence_Report SHALL 将表格型章节数据以 JSON 格式存入 checklist_responses.remark 字段

### Requirement 6: LLM 内容生成（知识库参考）

**User Story:** As a 审计助理, I want to 点击 AI 按钮为各章节生成建议稿, so that I can 快速完成尽调报告初稿编写。

#### Acceptance Criteria

1. THE AI_Button SHALL 在每个 textarea 型章节右上角显示"🤖 AI 生成"按钮
2. WHEN 用户点击 AI_Button, THE LLM_Generate_Service SHALL 调用 vLLM 生成该章节建议内容
3. THE LLM_Generate_Service SHALL 通过 ReferenceDocService.load_from_knowledge_base 检索项目知识库中与当前章节相关的参考文档
4. THE LLM_Generate_Service SHALL 在 prompt 中注入以下上下文：当前章节标题、知识库参考文档（最多 3 篇）、已填写的其他章节摘要（跨章上下文）、项目基本信息（客户名/行业/报告期）
5. WHEN LLM 生成完成, THE Due_Diligence_Report SHALL 以 el-dialog 弹窗展示建议稿，用户确认后填入对应章节
6. THE LLM_Generate_Service SHALL 支持两种模式：generate（从头生成）和 polish（基于已有内容润色改进）
7. IF LLM 服务不可用, THEN THE AI_Button SHALL 显示为 disabled 状态并提示"AI 服务暂不可用"
8. THE LLM_Generate_Service SHALL 在 prompt 中使用尽调报告专属 system prompt，包含中国 CPA 行业尽调报告格式规范

### Requirement 7: 后端渲染器与解析器

**User Story:** As a 开发者, I want to B1-4 有专属渲染器从 checklist_responses 加载结构化数据, so that 前端组件可以正确渲染报告内容。

#### Acceptance Criteria

1. THE Due_Diligence_Report SHALL 在后端注册 `_b14_due_diligence` 渲染函数，从 checklist_responses 加载所有 `b14-*` 记录组装为 html_data
2. THE 渲染函数 SHALL 返回包含以下结构的 html_data：chapters（各章节数据）、variant（当前变体）、project_context（客户名/行业/报告期/事务所名）
3. THE 渲染函数 SHALL 从 projects 表加载项目上下文信息（客户名/行业/审计年度）
4. FOR ALL 有效的 B14RenderData 对象, 序列化后再反序列化 SHALL 产出等价对象（round-trip property）

### Requirement 8: 表格型章节编辑

**User Story:** As a 审计助理, I want to 在"公司基本情况"等章节中编辑结构化表格（如人员架构表、股东信息表）, so that I can 录入表格型尽调数据。

#### Acceptance Criteria

1. WHEN 章节包含表格型数据（如项目团队表/股东信息表/主要客户表）, THE Chapter_Card SHALL 渲染 el-table 支持行内编辑
2. THE Chapter_Card SHALL 为每个表格提供"+ 添加行"按钮和行级"删除"按钮
3. WHEN 用户修改表格单元格, THE Due_Diligence_Report SHALL 将整行数据更新后触发自动保存
4. THE Due_Diligence_Report SHALL 为以下章节预定义表格结构：项目团队分工表（角色/人员/职责）、股东信息表（股东/持股比例/出资方式）、主要客户表（客户/收入占比/账龄）、主要供应商表（供应商/采购占比）、同行业对比表（指标/目标公司/对标公司1/对标公司2）

### Requirement 9: 签字区

**User Story:** As a 业务合伙人, I want to 在报告末尾签字确认, so that I can 完成尽调报告的签发流程。

#### Acceptance Criteria

1. THE Due_Diligence_Report SHALL 在所有章节卡片下方显示签字区卡片
2. THE 签字区 SHALL 包含以下字段：项目合伙人签名+日期、项目经理签名+日期、报告日期
3. WHEN 用户填写签字信息, THE Due_Diligence_Report SHALL 持久化签字数据（item_id=`b14-signature-{field}`）

### Requirement 10: 跨底稿引用联动

**User Story:** As a 审计助理, I want to 从尽调报告快速跳转到相关底稿（如 B50 风险评估、B15 重要性）, so that I can 在底稿间高效导航。

#### Acceptance Criteria

1. THE Due_Diligence_Report SHALL 在"财务信息分析"章节显示 GtIndexChip 跳转到 B15（重要性水平）
2. THE Due_Diligence_Report SHALL 在"内部控制"章节显示 GtIndexChip 跳转到 B22A（内控矩阵）
3. THE Due_Diligence_Report SHALL 在"公司存在的主要问题"章节显示 GtIndexChip 跳转到 B50（风险评估）
4. WHEN 用户点击 GtIndexChip, THE Due_Diligence_Report SHALL 导航到对应底稿
