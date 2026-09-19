# Requirements Document

## Introduction

基于 projects 表已有的三个字段（company_code / parent_company_code / ultimate_company_code）构建集团架构树形结构，提供合并入口页面树形展示、项目列表页树形切换、批量建项 Excel 模板导入三大能力。树形结构纯运行时动态构建，不缓存死结构。Phase 1 聚焦只读树形展示+搜索定位+批量导入。

## Glossary

- **Tree_Builder**：运行时树形构建服务，负责将扁平项目数据按 company_code/parent_company_code/ultimate_company_code 三字段组装为树形结构
- **ConsolidationHub**：合并入口页面（/consolidation），展示所有 report_scope='consolidated' 的项目
- **Project_List**：项目列表页面（Projects.vue），支持扁平列表与树形展示切换
- **Batch_Importer**：批量建项导入服务，解析 Excel 模板并创建项目同时维护树形关系
- **Detached_Node**：脱挂节点，parent_company_code 指向不存在企业时挂在 ultimate 根节点下的节点
- **Independent_Node**：独立节点，ultimate_company_code 为空的项目，不属于任何集团
- **Company_Code**：企业代码，18 位统一社会信用代码
- **Ultimate_Root**：最终控制方对应的合并项目（report_scope='consolidated'），作为树形根节点

## Requirements

### Requirement 1: 树形结构动态构建

**User Story:** As a 审计经理, I want 集团架构树形结构在每次加载时动态构建, so that 企业代码字段修改后树形结构实时反映最新关系。

#### Acceptance Criteria

1. WHEN 用户打开合并入口页面或项目列表树形视图, THE Tree_Builder SHALL 从当前所有项目的 company_code、parent_company_code、ultimate_company_code 字段实时构建树形结构
2. THE Tree_Builder SHALL 按 ultimate_company_code 分组，将相同最终控制方的项目归入同一棵树
3. THE Tree_Builder SHALL 根据 parent_company_code 与其他项目的 company_code 的匹配关系确定父子层级
4. THE Tree_Builder SHALL 按年度（audit_period_end 提取年份）区分构建树形，不同年度的树形可能不同（同一企业在不同年度可能属于不同集团或不再纳入）
5. WHEN 用户切换年度筛选条件时, THE Tree_Builder SHALL 仅用该年度项目重新构建树形
6. THE Tree_Builder SHALL 在每次页面加载或数据变更时重新构建树形，不使用缓存的历史结构
7. THE Tree_Builder SHALL 以 projects 表的三个企业代码字段为树形构建的唯一权威数据源（非 consolidation_company 表）

### Requirement 9: 合并范围校对（树形 vs consol_scope 表）

**User Story:** As a 审计经理, I want 当树形结构与合并模块已配置的合并范围存在差异时收到提示, so that 及时发现并纠正两处数据不一致。

#### Acceptance Criteria

1. WHEN 树形构建完成后, THE Tree_Builder SHALL 对每个 ultimate_company_code 对应的合并项目查询其 consol_scope 表中已配置的合并范围
2. IF 树形中的子节点（由 parent_company_code 链推导）与 consol_scope 表中的成员不一致, THEN THE Tree_Builder SHALL 在对应集团树的根节点显示"⚠️ 合并范围差异"警示标签
3. WHEN 用户点击差异警示标签, THE Tree_Builder SHALL 展示差异明细：哪些企业在树形中有但合并范围中没有（待纳入），哪些在合并范围中有但树形中没有（待移除或缺少项目）
4. THE Tree_Builder SHALL 提供"一键同步到合并范围"操作，**仅增量添加**树形中有但 consol_scope 表中没有的子企业（用户确认后执行）；**不自动删除** consol_scope 中多出的条目（移除交用户手动确认，避免误删手工配置的合并范围）
5. THE Tree_Builder SHALL 以 projects 表三代码为权威源，consol_scope 表作为校对参考，差异提示不阻塞树形展示

### Requirement 2: 树形结构容错处理

**User Story:** As a 审计经理, I want 树形构建在数据不完整时依然正确呈现, so that 存在脏数据或部分缺失时不会导致页面崩溃。

#### Acceptance Criteria

1. IF parent_company_code 指向一个在当前项目集中不存在的企业代码, THEN THE Tree_Builder SHALL 将该节点作为 Detached_Node 挂在对应 ultimate_company_code 的根节点下
2. IF ultimate_company_code 为空, THEN THE Tree_Builder SHALL 将该项目作为 Independent_Node 展示在独立节点分组中
3. IF 树形构建过程中检测到循环引用（A→B→C→A）, THEN THE Tree_Builder SHALL 打断循环并将参与循环的节点标记为异常，不抛出错误
4. IF company_code 为空, THEN THE Tree_Builder SHALL 将该项目排除在树形结构之外并在独立分组中以扁平方式展示

### Requirement 3: ConsolidationHub 树形展示

**User Story:** As a 审计经理, I want 合并入口页面按集团架构树形展示合并项目, so that 一眼看清集团层级关系和子公司归属。

#### Acceptance Criteria

1. WHEN 用户进入合并入口页面（/consolidation）, THE ConsolidationHub SHALL 按 ultimate_company_code 分组将 report_scope='consolidated' 的项目以树形结构展示
2. THE ConsolidationHub SHALL 在每棵集团树的根节点显示最终控制方企业名称和企业代码
3. WHEN 用户点击树中任意企业节点, THE ConsolidationHub SHALL 导航到该最终控制方的合并详情页（/projects/:id/consolidation）
4. THE ConsolidationHub SHALL 在每个节点显示企业名称、企业代码和当前状态标签
5. THE ConsolidationHub SHALL 保留现有统计概览区域（合并项目数、子公司数、执行中数、已完成数）

### Requirement 4: 项目列表树形视图切换

**User Story:** As a 审计人员, I want 在项目列表页面切换扁平列表和集团树形视图, so that 按需选择合适的项目浏览方式。

#### Acceptance Criteria

1. THE Project_List SHALL 在筛选栏的视图切换区域增加"树形"选项，与现有"列表"和"按客户"并列
2. WHEN 用户选择"树形"视图模式, THE Project_List SHALL 将所有项目按 ultimate_company_code 分组以树形结构展示
3. WHEN 用户在树形视图中点击某企业节点, THE Project_List SHALL 导航到该项目详情页
4. WHILE 处于树形视图模式, THE Project_List SHALL 支持现有搜索框对企业名称和企业代码的实时筛选
5. THE Project_List SHALL 记住用户最后选择的视图模式，下次进入时恢复

### Requirement 5: 树形搜索与高亮定位

**User Story:** As a 审计人员, I want 在树形视图中搜索企业名称或代码并定位到目标节点, so that 在大型集团架构中快速找到目标企业。

#### Acceptance Criteria

1. WHEN 用户在搜索框输入文本, THE Tree_Builder SHALL 对所有节点的企业名称和企业代码进行实时模糊匹配
2. WHEN 搜索匹配到结果, THE Tree_Builder SHALL 自动展开匹配节点的所有祖先节点使其可见
3. WHEN 搜索匹配到结果, THE Tree_Builder SHALL 高亮显示匹配节点的匹配文字部分
4. IF 搜索无匹配结果, THEN THE Tree_Builder SHALL 显示"未找到匹配企业"的空状态提示
5. WHEN 用户清空搜索框, THE Tree_Builder SHALL 恢复树形的默认展开/折叠状态

### Requirement 6: 批量建项 Excel 模板导出

**User Story:** As a 审计经理, I want 下载包含集团架构代码字段的批量建项 Excel 模板, so that 批量录入项目时能正确填写层级关系。

#### Acceptance Criteria

1. WHEN 用户点击下载建项模板, THE Batch_Importer SHALL 生成包含"企业代码(company_code)"、"上级企业代码(parent_company_code)"、"最终控制方企业代码(ultimate_company_code)"三列的 Excel 模板
2. THE Batch_Importer SHALL 在模板的"说明事项"sheet 中说明三代码字段的填写规则和 18 位统一社会信用代码格式要求
3. THE Batch_Importer SHALL 在模板中提供示例数据行展示正确的集团层级填写方式

### Requirement 7: 批量建项导入与树形关系识别

**User Story:** As a 审计经理, I want 批量导入项目后系统自动识别树形关系, so that 不需要逐个手动设置企业层级。

#### Acceptance Criteria

1. WHEN 用户上传填写好的批量建项 Excel, THE Batch_Importer SHALL 解析每行的 company_code、parent_company_code、ultimate_company_code 字段并创建项目
2. THE Batch_Importer SHALL 支持同批次内的 parent-child 互引（A 行的 parent 指向 B 行的 company_code，即使 B 尚未入库）
3. WHEN company_code 字段非空, THE Batch_Importer SHALL 校验其符合 18 位统一社会信用代码格式
4. IF ultimate_company_code 对应的合并项目（report_scope='consolidated'）在系统中不存在, THEN THE Batch_Importer SHALL 自动创建一个 report_scope='consolidated' 的根项目
5. WHEN 批量导入完成后, THE Batch_Importer SHALL 触发树形重建，使合并模块即时展示完整集团架构
6. IF 同批次中存在重复的 company_code, THEN THE Batch_Importer SHALL 拒绝该批次并返回重复行号信息

### Requirement 8: 批量导入预校验

**User Story:** As a 审计经理, I want 批量导入前先预览树形结构确认层级正确, so that 避免错误数据入库后难以修正。

#### Acceptance Criteria

1. WHEN 用户上传 Excel 文件, THE Batch_Importer SHALL 先执行预校验（干跑不入库），返回解析结果和树形预览
2. THE Batch_Importer SHALL 在预览中展示构建出的树形结构，标注错误行（格式不合规、循环引用、parent 指向不存在等）
3. WHEN 用户确认预校验结果无误后点击"确认导入", THE Batch_Importer SHALL 正式将数据写入数据库
4. IF 预校验发现格式错误, THEN THE Batch_Importer SHALL 在对应行标注错误原因且不允许确认导入
