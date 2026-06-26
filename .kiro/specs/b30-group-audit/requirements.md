# Requirements Document

## Introduction

B30 集团审计范围确定底稿是集团审计计划阶段（B循环）的核心底稿，系统执行对集团审计范围的确定工作（CAS 1401 集团审计准则）。该底稿涵盖：集团结构树建立、组成部分分类（重要/非重要/不重要）、集团重要性逐级分配、各组成部分审计范围确定（全面审计/特定项目审计/分析性程序/不执行程序）、组成部分审计师委派与胜任能力/独立性确认、范围覆盖率热力图可视化。

当前实现使用 `a-program-console`（B30 主表）+ 多个 `d-form-table`/`audit-sheet` 子底稿（B30-1~B30-15），用户需在多个底稿间切换。本 spec 定义一个统一的 `b30-group-audit` HTML 专用组件，将集团审计范围确定全流程聚合为：集团结构树 + 组成部分表格 + 重要性分配 + 审计范围确定 + 组成部分审计师管理 + 覆盖率热力图 + 现场经理复核签字界面。

核心价值：
- 集团结构可视化：树形展示母公司与所有子公司/分支/合营/联营的层级关系
- 组成部分分类与重要性分配：基于 B15 集团重要性基数自动计算建议分配
- 范围覆盖率热力图：直观展示审计范围对集团财务数据的覆盖程度
- 与 B50 风险评估联动：重要组成部分 scope 确定后自动通知 B50
- 三方联动闭环：B15（重要性）→ B30（范围）→ B50（风险）→ D~N（程序）

## Glossary

- **Group_Audit_Component**: B30 集团审计范围确定底稿 Vue 组件（componentType = `b30-group-audit`）
- **Group_Structure_Tree**: 集团结构树，层级展示母公司及所有组成部分（子公司/分公司/合营企业/联营企业/分部）的隶属关系
- **Component_Entity**: 组成部分实体，集团内的每个独立核算单位（子公司/分公司/合营企业/联营企业/分部）
- **Component_Classification**: 组成部分分类枚举：重要组成部分(Significant)/非重要组成部分(Non-significant)/不重要组成部分(Insignificant)
- **Classification_Criteria**: 分类标准，基于财务指标（总资产/营业收入/利润占集团比例）判定组成部分重要性
- **Group_Materiality**: 集团重要性水平，从 B15 底稿获取的集团整体重要性金额
- **Allocated_Materiality**: 分配重要性，将 Group_Materiality 按比例/规则分配到各重要组成部分的重要性金额
- **Scope_Type**: 审计范围类型枚举：全面审计/特定项目审计/分析性程序/不执行程序
- **Component_Auditor**: 组成部分审计师，负责执行组成部分审计工作的注册会计师/事务所
- **Coverage_Heatmap**: 范围覆盖率热力图，按财务指标（总资产/营业收入/利润）显示审计范围对集团整体的覆盖比例
- **Coverage_Rate**: 覆盖率，各组成部分按其审计范围类型贡献的覆盖百分比之和（全面审计=100%/特定项目=部分/分析性程序=有限/不执行=0%）
- **Financial_Data**: 组成部分财务数据（总资产/营业收入/利润），来自 trial_balance 聚合或手工录入
- **Scope_Dashboard**: 范围确定仪表盘，顶部汇总面板，显示：组成部分总数/各分类分布/范围类型分布/整体覆盖率
- **Independence_Confirmation**: 组成部分审计师独立性确认（已确认/未确认/不适用）
- **Competence_Assessment**: 组成部分审计师胜任能力评估（充分/需补充/不充分）
- **checklist_responses**: 数据持久化表，通过 item_id 前缀 `B30-` 区分字段
- **htmlRendererRegistry**: 前端 componentType → Vue 组件的单一来源注册表
- **Manager_Review**: 现场经理复核签字
- **EventBus**: 进程内事件总线，B30 发布 `group:scope-determined` 事件
- **Import_Export**: 三级导入导出：空白模板导出 → 离线填写 → 数据导入回系统（复用 ExcelJS）
- **Parent_Company**: 母公司节点，集团结构树的根节点
- **Materiality_Allocation_Rule**: 重要性分配规则：按组成部分规模比例分配，单个组成部分分配重要性不超过集团重要性的 85%，不低于 15%

## Requirements

### Requirement 1: 集团结构树管理

**User Story:** As a 现场经理, I want 在统一界面中建立和管理集团组织结构树, so that 直观展示母公司与所有组成部分的层级关系，支撑后续范围确定。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 渲染 Group_Structure_Tree 区域，以树形结构展示母公司（根节点）及所有 Component_Entity 的层级关系
2. THE Group_Structure_Tree SHALL 支持添加 Component_Entity 节点，每个节点包含：组成部分名称、类型（子公司/分公司/合营企业/联营企业/分部）、持股比例（百分比）
3. THE Group_Structure_Tree SHALL 支持拖拽调整节点层级关系（变更父节点）
4. THE Group_Structure_Tree SHALL 支持删除叶子节点（有子节点的节点需先删除或移动子节点）
5. WHEN 用户添加新节点时, THE Group_Audit_Component SHALL 自动为该节点创建对应的 Component_Entity 数据行
6. THE Group_Structure_Tree SHALL 在每个节点标题旁显示 Component_Classification 对应的颜色标识（重要=红/非重要=黄/不重要=灰）
7. THE Group_Structure_Tree SHALL 支持展开/折叠子树操作，默认全部展开
8. THE Group_Structure_Tree SHALL 在节点旁显示 Scope_Type 简写标签（全面/特定/分析/无）

### Requirement 2: 组成部分表格与分类

**User Story:** As a 现场经理, I want 以结构化表格管理所有组成部分的分类信息和财务数据, so that 基于量化指标确定各组成部分的重要性分类。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 在 Group_Structure_Tree 下方渲染组成部分明细表格，每行包含：序号、名称、类型、持股比例、总资产、营业收入、利润、总资产占比、营收占比、利润占比、Component_Classification（下拉）、备注
2. THE 组成部分表格 SHALL 与 Group_Structure_Tree 双向同步：树中添加/删除节点时表格自动增减行，表格中编辑名称/类型时树节点同步更新
3. THE Group_Audit_Component SHALL 自动计算各组成部分的总资产占比、营收占比、利润占比（占集团合并数的百分比）
4. THE Group_Audit_Component SHALL 提供 Component_Classification 自动建议：当任一占比超过 15% 时建议"重要组成部分"；超过 5% 但不超过 15% 时建议"非重要组成部分"；均不超过 5% 时建议"不重要组成部分"
5. THE Group_Audit_Component SHALL 允许现场经理手动覆盖 Classification_Criteria 自动建议的分类（覆盖时附注说明理由）
6. WHEN 组成部分的 Financial_Data 变更时, THE Group_Audit_Component SHALL 重新计算占比并更新分类建议
7. THE 组成部分表格 SHALL 支持按 Component_Classification 筛选显示（全部/仅重要/仅非重要/仅不重要）
8. THE Group_Audit_Component SHALL 在表格底部显示集团合计行（总资产合计/营收合计/利润合计）

### Requirement 3: 重要性水平分配

**User Story:** As a 现场经理, I want 将集团重要性水平分配到各重要组成部分, so that 各组成部分审计师有明确的重要性标准执行审计。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 从 B15 底稿获取 Group_Materiality 金额并在重要性分配区域顶部显示
2. THE Group_Audit_Component SHALL 为每个分类为"重要组成部分"的 Component_Entity 提供 Allocated_Materiality 输入字段
3. THE Group_Audit_Component SHALL 自动建议各重要组成部分的 Allocated_Materiality：按该组成部分占集团合并数的比例 × Group_Materiality × 调整系数（默认 0.75）
4. THE Group_Audit_Component SHALL 校验各重要组成部分的 Allocated_Materiality 不超过 Group_Materiality 的 85%
5. THE Group_Audit_Component SHALL 校验各重要组成部分的 Allocated_Materiality 不低于 Group_Materiality 的 15%
6. WHEN Allocated_Materiality 超出合理范围时, THE Group_Audit_Component SHALL 在对应字段旁显示黄色警告提示
7. THE Group_Audit_Component SHALL 允许现场经理手动调整 Allocated_Materiality 金额（调整后保存覆盖值）
8. WHILE B15 底稿尚未完成时, THE Group_Audit_Component SHALL 在重要性分配区域显示"B15 未完成，集团重要性待定"灰色提示，并禁用自动建议功能
9. THE Group_Audit_Component SHALL 为"非重要组成部分"和"不重要组成部分"显示"不分配"标注

### Requirement 4: 审计范围确定

**User Story:** As a 现场经理, I want 为每个组成部分确定审计工作类型, so that 明确各组成部分执行的审计程序级别。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 为每个 Component_Entity 提供 Scope_Type 下拉选择：全面审计/特定项目审计/分析性程序/不执行程序
2. THE Group_Audit_Component SHALL 自动建议 Scope_Type：重要组成部分→全面审计；非重要组成部分→特定项目审计或分析性程序；不重要组成部分→不执行程序
3. THE Group_Audit_Component SHALL 允许现场经理手动覆盖自动建议的 Scope_Type（覆盖时附注说明理由）
4. WHEN 组成部分为"重要组成部分"且 Scope_Type 不为"全面审计"时, THE Group_Audit_Component SHALL 显示橙色警告："重要组成部分通常应执行全面审计"
5. WHEN Scope_Type 为"特定项目审计"时, THE Group_Audit_Component SHALL 提供"特定项目说明"文本区供用户描述具体审计范围
6. THE Group_Audit_Component SHALL 在 Scope_Dashboard 中按 Scope_Type 显示组成部分数量分布
7. WHEN 任一组成部分的 Scope_Type 变更时, THE Group_Audit_Component SHALL 重新计算 Coverage_Rate 并更新 Coverage_Heatmap

### Requirement 5: 组成部分审计师管理

**User Story:** As a 现场经理, I want 为需要执行审计的组成部分指派审计师并记录其胜任能力和独立性, so that 满足 CAS 1401 对组成部分审计师的要求。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 为 Scope_Type 非"不执行程序"的 Component_Entity 提供 Component_Auditor 管理区域
2. THE Component_Auditor 区域 SHALL 包含字段：审计师姓名/事务所名称、Independence_Confirmation（已确认/未确认/不适用）、Competence_Assessment（充分/需补充/不充分）、备注
3. WHEN Independence_Confirmation 为"未确认"时, THE Group_Audit_Component SHALL 在该行显示红色警告标识
4. WHEN Competence_Assessment 为"不充分"时, THE Group_Audit_Component SHALL 在该行显示红色警告并附加提示"需采取额外措施或变更组成部分审计师"
5. THE Group_Audit_Component SHALL 在 Scope_Dashboard 中显示"独立性未确认"和"胜任能力不充分"的组成部分数量
6. WHEN 组成部分 Scope_Type 变更为"不执行程序"时, THE Group_Audit_Component SHALL 清空该组成部分的 Component_Auditor 信息并标注"无需指派"
7. THE Group_Audit_Component SHALL 支持同一审计师指派给多个组成部分（审计师姓名/事务所可复用选择）

### Requirement 6: 范围覆盖率热力图

**User Story:** As a 业务合伙人, I want 通过热力图直观看到审计范围对集团财务的覆盖程度, so that 快速判断审计范围是否充分。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 渲染 Coverage_Heatmap 区域，以矩阵形式展示：行=各组成部分、列=三个财务指标（总资产/营业收入/利润）、单元格=覆盖率贡献百分比
2. THE Coverage_Heatmap SHALL 使用颜色深浅表示覆盖率贡献大小：深绿色=高覆盖(≥15%)/浅绿色=中覆盖(5%~15%)/浅灰色=低覆盖(<5%)/白色=不执行(0%)
3. THE Coverage_Heatmap SHALL 在底部显示各列合计覆盖率百分比（全面审计覆盖+特定项目覆盖+分析性程序覆盖的加权合计）
4. THE Group_Audit_Component SHALL 定义覆盖率加权规则：全面审计=100%权重、特定项目审计=50%权重、分析性程序=25%权重、不执行程序=0%
5. WHEN 任一组成部分的 Scope_Type 或 Financial_Data 变更时, THE Coverage_Heatmap SHALL 实时重新计算并更新渲染
6. THE Coverage_Heatmap SHALL 在任一财务指标的加权覆盖率低于 60% 时显示红色警告："覆盖率不足，建议扩大审计范围"
7. THE Coverage_Heatmap SHALL 支持鼠标悬停查看单元格详情（组成部分名称 + 指标金额 + 占比 + 范围类型 + 加权后覆盖贡献）
8. THE Coverage_Heatmap SHALL 在打印输出中保持颜色区分（@media print 保留背景色），布局适配 A4 横版

### Requirement 7: 范围确定仪表盘

**User Story:** As a 现场经理, I want 在顶部仪表盘一目了然掌握集团审计范围确定的整体状态, so that 快速定位需要关注的组成部分和未完成事项。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 渲染 Scope_Dashboard 顶部汇总面板，显示：组成部分总数、各 Component_Classification 分布（重要N/非重要N/不重要N）、各 Scope_Type 分布（全面N/特定N/分析N/不执行N）
2. THE Scope_Dashboard SHALL 显示三个财务指标的加权覆盖率进度条（总资产覆盖率/营收覆盖率/利润覆盖率），覆盖率≥80%显示绿色、60%~80%显示黄色、<60%显示红色
3. THE Scope_Dashboard SHALL 显示"待确认事项"计数：包括未分类组成部分数、未确定范围数、独立性未确认数
4. THE Scope_Dashboard SHALL 实时响应各区域的数据变更，自动更新统计数据
5. THE Scope_Dashboard SHALL 显示 Group_Materiality 金额（从 B15 获取）和已分配重要性组成部分数量
6. THE Scope_Dashboard SHALL 显示集团结构树节点总数和层级深度

### Requirement 8: 跨底稿联动（B15 + B50）

**User Story:** As a 现场经理, I want B30 范围确定结论自动通知 B50 风险评估, so that 重要组成部分的审计范围能驱动后续风险评估决策。

#### Acceptance Criteria

1. WHEN 全部组成部分的 Scope_Type 确定完毕（所有组成部分均有非空 Scope_Type）时, THE Group_Audit_Component SHALL 通过 EventBus 发布 `group:scope-determined` 事件（含重要组成部分列表、各组成部分范围类型、整体覆盖率）
2. THE Group_Audit_Component SHALL 从 B15 底稿获取 Group_Materiality 数据（通过 EventBus 监听 `materiality:determined` 事件或初始化时 API 获取）
3. THE Group_Audit_Component SHALL 在联动面板中显示 B15 关联状态（已完成/未完成 + Group_Materiality 金额）和 B50 关联状态（已接收 scope-determined 事件/未接收）
4. THE 联动面板 SHALL 提供 ref_chip 跳转链接到 B15 底稿和 B50 底稿
5. WHEN Group_Materiality 变更（B15 更新）时, THE Group_Audit_Component SHALL 自动重新计算 Allocated_Materiality 建议并提示用户确认
6. THE Group_Audit_Component SHALL 在联动面板中显示审计链路摘要：B15(重要性)→B30(范围)→B50(风险)

### Requirement 9: 数据持久化

**User Story:** As a 审计助理, I want 所有集团审计范围确定数据自动保存, so that 不会因意外关闭而丢失工作。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 将所有数据存储到 checklist_responses 表，使用 item_id 前缀 `B30-` 区分字段
2. WHEN 用户编辑任意文本字段后停止输入 2 秒时, THE Group_Audit_Component SHALL 自动保存变更到后端（debounce 2000ms）
3. WHEN 用户变更 Component_Classification、Scope_Type、Independence_Confirmation、Competence_Assessment 时, THE Group_Audit_Component SHALL 立即保存（不等待 debounce）
4. WHEN 保存失败时, THE Group_Audit_Component SHALL 显示错误提示并保留本地编辑内容（不回滚）
5. THE Group_Audit_Component SHALL 通过 `PUT /api/workpapers/{wp_id}/checklist-responses` 接口批量保存
6. THE Group_Audit_Component SHALL 通过 `GET /api/workpapers/{wp_id}/checklist-responses` 加载已保存数据并还原集团结构树 + 组成部分表格 + 范围确定状态
7. THE Group_Audit_Component SHALL 使用结构化 item_id 命名规则：`B30-comp-{n}-{field}`（如 `B30-comp-1-name`、`B30-comp-3-classification`、`B30-comp-2-scope`、`B30-comp-1-auditor-name`、`B30-tree-structure`、`B30-group-materiality`）

### Requirement 10: 现场经理复核与只读流程

**User Story:** As a 现场经理, I want 全部组成部分范围确定完成后签字复核并锁定, so that 后续风险评估基于经复核的集团审计范围。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 在 Scope_Dashboard 下方提供"现场经理复核"签字区域
2. WHEN 存在未完成事项（任一组成部分 Classification 为空、Scope_Type 为空、或重要组成部分的 Independence_Confirmation 为"未确认"）时, THE Group_Audit_Component SHALL 禁用复核签字按钮并显示待完成事项清单
3. WHEN 现场经理完成签字时, THE Group_Audit_Component SHALL 将全部区域转为只读模式
4. WHILE Group_Audit_Component 处于已复核只读模式时, THE Group_Audit_Component SHALL 在顶部显示"已复核"状态横幅（绿色）和复核人/日期信息
5. WHEN 外部传入 `readonly` prop 为 true 时, THE Group_Audit_Component SHALL 强制进入只读模式
6. WHEN 已复核后需要修改集团审计范围时, THE Group_Audit_Component SHALL 支持 Amendment 模式：填写修改原因后解锁编辑，完成后需重新走复核流程

### Requirement 11: 组件注册与路由

**User Story:** As a 开发者, I want 新组件正确注册到 htmlRendererRegistry 并通过 wp_code_overrides 路由, so that 打开 B30 底稿时自动渲染新组件。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 在 htmlRendererRegistry 中注册 componentType 为 `b30-group-audit`，contextProps 为 `standard`
2. THE Group_Audit_Component SHALL 在 wp_code_overrides.json 中将 `B30` 映射为 `b30-group-audit`（替换现有 `a-program-console`）
3. THE Group_Audit_Component SHALL 在 wp_code_overrides.json 中将 `B30-1`、`B30-2`、`B30-3`、`B30-4`、`B30-5` 映射为 `skip`（由 B30 统一渲染）
4. THE Group_Audit_Component SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly
5. THE Group_Audit_Component SHALL emit `save` 事件（保存成功后）和 `completed` 事件（复核完成时）
6. WHEN 后端 render-config 返回 componentType 为 `b30-group-audit` 时, THE 前端路由 SHALL 正确加载 Group_Audit_Component

### Requirement 12: 后端结论白名单扩展

**User Story:** As a 开发者, I want 后端 checklist_responses 保存逻辑支持 B30- 前缀的结论值, so that 前端发送的集团审计范围数据能正常持久化。

#### Acceptance Criteria

1. THE 后端 checklist_responses 保存逻辑 SHALL 在结论白名单中支持 B30- 前缀的 item_id
2. THE 后端 SHALL 接受 B30- 前缀 item_id 的以下结论值：重要组成部分、非重要组成部分、不重要组成部分、全面审计、特定项目审计、分析性程序、不执行程序、已确认、未确认、不适用、充分、需补充、不充分、Y、N
3. THE 后端 SHALL 对 B30- 前缀 item_id 的保存请求执行与现有 B22A-/B22B-/B23-/B50- 前缀相同的权限校验
4. IF 前端发送无效的 B30- 前缀结论值, THEN THE 后端 SHALL 返回 422 校验错误并拒绝保存

### Requirement 13: 颜色编码与视觉设计

**User Story:** As a 业务合伙人, I want 通过颜色直观区分组成部分的分类和审计范围, so that 快速判断集团审计范围布局是否合理。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 对 Component_Classification 使用颜色编码：重要组成部分=红色(#ff4d4f)、非重要组成部分=黄色(#faad14)、不重要组成部分=灰色(#bfbfbf)
2. THE Group_Audit_Component SHALL 对 Scope_Type 使用颜色编码：全面审计=深绿(#52c41a)、特定项目审计=浅绿(#95de64)、分析性程序=蓝色(#1890ff)、不执行程序=灰色(#d9d9d9)
3. THE Scope_Dashboard SHALL 使用与 Component_Classification 相同的颜色编码渲染分布统计
4. THE Group_Structure_Tree 节点 SHALL 使用左侧色带（4px 宽）标识该节点的 Component_Classification 对应颜色
5. THE Group_Audit_Component SHALL 在打印输出中保持颜色编码区分（@media print 保留背景色）

### Requirement 14: 响应式布局与打印

**User Story:** As a 审计助理, I want 在不同屏幕和打印场景下正常使用集团审计范围底稿, so that 现场笔记本和归档打印都能满足。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 在 ≥1024px 宽度下完整显示 Scope_Dashboard、Group_Structure_Tree 和组成部分表格
2. WHEN 视窗宽度在 768px~1024px 时, THE Group_Audit_Component SHALL 通过水平滚动支持表格查看，不截断内容
3. THE Group_Audit_Component SHALL 提供打印样式表（@media print），Group_Structure_Tree 和 Coverage_Heatmap 适配 A4 横版，组成部分表格适配 A4 纵版
4. WHEN 用户触发打印时, THE Group_Audit_Component SHALL 隐藏交互控件（拖拽手柄、添加/删除按钮、筛选器），仅保留数据和结论
5. THE Group_Audit_Component SHALL 在打印输出中自动展开集团结构树全部节点

### Requirement 15: 导入导出功能（三级）

**User Story:** As a 审计助理, I want 导出空白模板/已填数据到 Excel 并支持从 Excel 导入, so that 支持离线填写和与其他系统的数据交换。

#### Acceptance Criteria

1. THE Group_Audit_Component SHALL 在工具栏提供"导出模板"按钮，生成包含 2 个 Sheet 的空白 Excel 模板（Sheet1=集团结构：名称/类型/持股比例/父节点名称；Sheet2=组成部分明细：名称/总资产/营收/利润/分类/范围/审计师/独立性/胜任能力）
2. THE Group_Audit_Component SHALL 在工具栏提供"导出数据"按钮，将当前全部已填写数据导出为 Excel（结构与模板一致，含已填内容 + 分类 + 范围 + 重要性分配 + 覆盖率）
3. THE Group_Audit_Component SHALL 在工具栏提供"导入"按钮，支持从符合模板格式的 Excel 文件导入数据
4. WHEN 导入数据时存在与现有数据的冲突（同名组成部分已存在）, THE Group_Audit_Component SHALL 弹出确认弹窗让用户选择"覆盖"或"跳过"
5. WHEN 导入的 Excel 格式不符合模板结构时, THE Group_Audit_Component SHALL 显示错误提示并拒绝导入（不写入任何数据）
6. THE 导出模板和导出数据 SHALL 使用项目已有的 ExcelJS 库（不引入新依赖）

---

## Correctness Properties

### Property 1: 仪表盘同步不变式

*For any* 组成部分的 Classification、Scope_Type 或 Financial_Data 变更，Scope_Dashboard 中的统计数据（分类分布/范围分布/覆盖率/待确认计数）SHALL 始终等于各组成部分中数据的实际分布计数。添加/删除/修改组成部分后，Scope_Dashboard 应同步更新。

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 2: 覆盖率计算一致性

*For any* 组成部分集合及其 Financial_Data 和 Scope_Type 组合，Coverage_Rate 按各指标 SHALL 满足：各组成部分贡献 = 该组成部分指标金额 / 集团合计 × 权重（全面=1.0/特定=0.5/分析=0.25/不执行=0.0），总覆盖率 = 所有组成部分贡献之和。覆盖率范围在 [0%, 100%] 区间内。

**Validates: Requirements 6.3, 6.4, 6.5**

### Property 3: 分类自动建议一致性

*For any* 组成部分的 Financial_Data 及其占比，分类自动建议 SHALL 满足：(a) 任一占比>15% → "重要组成部分"；(b) 任一占比>5%且均≤15% → "非重要组成部分"；(c) 全部占比≤5% → "不重要组成部分"。手动覆盖不影响建议计算逻辑本身。

**Validates: Requirements 2.4, 2.5, 2.6**

### Property 4: 重要性分配约束

*For any* 重要组成部分的 Allocated_Materiality 值，SHALL 满足：(a) 不超过 Group_Materiality × 85%；(b) 不低于 Group_Materiality × 15%。超出范围时必须显示警告。非重要/不重要组成部分不分配重要性。

**Validates: Requirements 3.4, 3.5, 3.6, 3.9**

### Property 5: 树表双向同步不变式

*For any* Group_Structure_Tree 节点的添加/删除/名称修改操作，组成部分表格 SHALL 同步反映变更（行数一致、名称一致）。反之，表格中名称/类型编辑也 SHALL 同步到树节点。树节点数量始终等于表格行数。

**Validates: Requirements 1.5, 2.2**

### Property 6: 复核前置条件完备性

*For any* 组成部分状态组合，现场经理签字按钮可用当且仅当：(a) 所有组成部分 Classification 非空；(b) 所有组成部分 Scope_Type 非空；(c) 所有"重要组成部分"的 Independence_Confirmation 为"已确认"或"不适用"。条件不满足时按钮必须禁用。

**Validates: Requirements 10.2**

### Property 7: 复核后只读不变式

*For any* 已通过现场经理复核的组件状态，所有区域的所有字段 SHALL 处于只读模式。除非通过 Amendment 模式解锁，否则任何编辑操作应被阻止。Amendment 解锁后需重新走复核流程。

**Validates: Requirements 10.3, 10.4, 10.6**

### Property 8: 数据持久化往返一致性

*For any* 有效的集团审计范围数据（包含树结构 + 组成部分明细 + 分类 + 范围 + 审计师 + 重要性分配），通过 PUT 保存后再通过 GET 加载，所有字段值（item_id、conclusion、remark）SHALL 与保存前一致（round-trip property）。

**Validates: Requirements 9.1, 9.5, 9.6**

### Property 9: item_id 命名唯一性

*For any* 组合（组成部分编号 {n} × 字段类型），生成的 item_id SHALL 唯一。不同业务含义的数据不可产生相同 item_id，同一业务含义的数据重复保存应覆盖而非新增。

**Validates: Requirements 9.7**

### Property 10: EventBus 事件发射正确性

*For any* 组成部分 Scope_Type 状态组合，WHEN 全部组成部分均有非空 Scope_Type 时 SHALL 发布 `group:scope-determined` 事件。WHEN 存在任一组成部分 Scope_Type 为空时 SHALL 不发布事件。事件载荷中重要组成部分列表 SHALL 等于 Classification="重要组成部分"的组成部分集合。

**Validates: Requirements 8.1**

### Property 11: 颜色编码单射

*For any* Component_Classification 值，对应的颜色编码 SHALL 满足单射：重要→红色、非重要→黄色、不重要→灰色。不存在同色不同分类。Scope_Type 颜色集与 Classification 颜色集不冲突（全面=深绿/特定=浅绿/分析=蓝/不执行=浅灰 vs 重要=红/非重要=黄/不重要=深灰）。

**Validates: Requirements 13.1, 13.2, 13.4**

### Property 12: 后端白名单校验正确性

*For any* item_id 以 `B30-` 开头的保存请求，conclusion 值在白名单内时 SHALL 返回 200；conclusion 值不在白名单内时 SHALL 返回 HTTP 422。remark 字段接受任意文本。

**Validates: Requirements 12.1, 12.2, 12.4**

### Property 13: Scope_Type 自动建议与分类关联

*For any* 组成部分 Classification 值，Scope_Type 自动建议 SHALL 满足：重要组成部分→"全面审计"；非重要组成部分→"特定项目审计"或"分析性程序"；不重要组成部分→"不执行程序"。Classification 变更时 Scope_Type 建议同步更新。

**Validates: Requirements 4.2, 4.4**

### Property 14: 导入导出数据一致性

*For any* 已填写的集团审计范围数据，通过"导出数据"生成的 Excel 再通过"导入"操作加载后，所有组成部分字段值（名称/类型/持股比例/财务数据/分类/范围/审计师）SHALL 与导出前一致。导入操作不影响未涉及组成部分的已有数据。

**Validates: Requirements 15.1, 15.2, 15.3**
