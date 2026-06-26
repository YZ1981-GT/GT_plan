# Requirements Document

## Introduction

B50 重大错报风险评估汇总是审计计划阶段（B循环）的核心底稿，是"风险导向审计"的中枢——B50 的风险结论直接驱动 D~N 循环实质性程序的性质、时间和范围，并反馈至 A13 错报评价。

当前实现使用 `a-program-console`（B50 主表）+ 4 个 `d-form-table`（B50-1~4 子表）的碎片化方案，用户必须打开 5 个独立底稿才能完成风险评估。本 spec 定义一个统一的 `b50-risk-assessment` HTML 专用组件，将 B50 及其 4 个子底稿聚合为单一 4-tab 界面，提供风险矩阵可视化、业务规则强制、跨底稿联动和合伙人审批流程。
核心价值：
- 将 5 次打开 → 1 次打开，消除碎片体验
- 认定层面风险矩阵可视化（科目×认定交叉表 + 红黄绿色标）
- CAS 1211 业务规则自动强制（舞弊推定、管理层凌驾、特别风险约束）
- 风险评估结论 → D~N 程序表强度自动联动

## Glossary

- **Risk_Assessment_Component**: B50 重大错报风险评估汇总 Vue 组件（componentType = `b50-risk-assessment`）
- **Risk_Matrix**: 认定层面风险矩阵，行=重要科目/披露，列=认定（存在/完整性/准确性/截止/分类/列报），单元格=风险等级
- **Risk_Level**: 风险等级枚举，高（High）/中（Medium）/低（Low）
- **Inherent_Risk**: 固有风险，不考虑内部控制时错报发生的可能性×影响程度
- **Control_Risk**: 控制风险，内部控制未能防止或发现错报的风险
- **Combined_Risk**: 重大错报风险，固有风险与控制风险的综合评估结果
- **Special_Risk**: 特别风险，需要特殊审计考虑的已识别重大错报风险（CAS 1211）
- **Fraud_Presumption**: 舞弊推定，收入确认默认视为舞弊风险（CAS 要求），除非经合伙人批准反驳
- **Management_Override**: 管理层凌驾控制，永远作为特别风险（不可降级）
- **Assertion**: 认定，管理层对财务报表各要素的声明（存在/完整性/准确性/截止/分类/列报）
- **FS_Level_Risk**: 报表层面重大错报风险，影响财务报表整体的风险
- **Tab_1**: 风险因素识别（B50-1 内容）
- **Tab_2**: 报表层面重大错报风险（B50-2 内容）
- **Tab_3**: 认定层面风险矩阵（B50-3 内容）——核心 tab
- **Tab_4**: 特别风险汇总（B50-4 内容）
- **checklist_responses**: 数据持久化表，通过 item_id 前缀 `B50-` 区分字段
- **htmlRendererRegistry**: 前端 componentType → Vue 组件的单一来源注册表
- **Partner_Approval**: 业务合伙人审批签字，风险评估终审
- **D_N_Programs**: D~N 循环程序表，根据 B50 风险结论确定程序强度

## Requirements

### Requirement 1: 4-Tab 统一界面

**User Story:** As a 现场经理, I want 在一个界面中完成全部风险评估工作（识别→报表层面→认定层面→特别风险）, so that 不再需要在 5 个底稿间切换。

#### Acceptance Criteria

1. THE Risk_Assessment_Component SHALL 渲染 4 个 tab 页签：Tab_1"风险因素识别"、Tab_2"报表层面重大错报风险"、Tab_3"认定层面风险矩阵"、Tab_4"特别风险汇总"
2. THE Risk_Assessment_Component SHALL 默认激活 Tab_3（认定层面风险矩阵）作为核心工作区
3. WHEN 用户切换 tab 时, THE Risk_Assessment_Component SHALL 保留其他 tab 的编辑状态（不丢失未保存数据）
4. THE Risk_Assessment_Component SHALL 在各 tab 页签上显示该 tab 的完成状态指示（已填/未填/部分填写）
5. THE Risk_Assessment_Component SHALL 使用中文标签，所有 UI 文字与审计准则术语一致
6. THE Risk_Assessment_Component SHALL 在 tab 栏右侧显示整体风险评估完成进度

### Requirement 2: 风险因素识别（Tab 1）

**User Story:** As a 审计助理, I want 系统化记录风险识别来源和因素, so that 风险评估有据可查且来源清晰。

#### Acceptance Criteria

1. THE Tab_1 SHALL 提供风险因素录入表格，每行包含：风险因素描述、来源类型（下拉选择）、影响科目/认定、初步风险判断
2. THE Tab_1 SHALL 提供来源类型下拉选项：B22A内控了解、B23流程了解、行业分析、项目组讨论、前期审计经验、管理层访谈、其他
3. WHEN 用户新增风险因素行时, THE Tab_1 SHALL 自动分配行序号并提供空白可编辑行
4. THE Tab_1 SHALL 支持删除已录入的风险因素行（需确认）
5. WHEN 风险因素的来源类型为"B22A内控了解"或"B23流程了解"时, THE Tab_1 SHALL 显示关联底稿 ref_chip（可点击跳转）
6. THE Tab_1 SHALL 支持将识别的风险因素标记为"已转入矩阵"（表示已在 Tab_3 体现）

### Requirement 3: 报表层面重大错报风险（Tab 2）

**User Story:** As a 现场经理, I want 评估影响财务报表整体的风险并记录应对策略, so that 总体审计策略有明确依据。

#### Acceptance Criteria

1. THE Tab_2 SHALL 提供报表层面风险录入表格，每行包含：风险描述、风险类别（内控环境/管理层诚信/经济环境/行业因素/其他）、风险等级（Risk_Level）、总体应对措施
2. WHEN 用户设置风险等级时, THE Tab_2 SHALL 提供高/中/低三级下拉选项并以对应颜色显示（高=红/中=黄/低=绿）
3. THE Tab_2 SHALL 为每个报表层面风险提供"总体应对措施"文本区域
4. THE Tab_2 SHALL 在底部显示报表层面风险的汇总统计（高 N 项/中 N 项/低 N 项）
5. WHEN 报表层面存在高风险时, THE Tab_2 SHALL 在风险条目旁显示醒目提示，提醒需关注对 B60 总体策略的影响

### Requirement 4: 认定层面风险矩阵（Tab 3）

**User Story:** As a 现场经理, I want 通过交叉矩阵直观展示每个科目各认定的风险等级, so that 一目了然掌握项目整体风险版图。

#### Acceptance Criteria

1. THE Tab_3 SHALL 渲染交叉表格：行=重要科目/披露项目，列=6个认定（存在/完整性/准确性/截止/分类/列报）
2. THE Tab_3 SHALL 在每个矩阵单元格中显示三层信息：Inherent_Risk 等级、Control_Risk 等级、Combined_Risk 等级
3. WHEN 用户点击矩阵单元格时, THE Tab_3 SHALL 弹出编辑面板，允许设置该单元格的固有风险、控制风险和综合风险等级
4. THE Tab_3 SHALL 对矩阵单元格进行颜色编码：Combined_Risk 高=红色背景、中=黄色背景、低=绿色背景
5. THE Tab_3 SHALL 在矩阵中用特殊标识（⚠️图标 + 红色边框）标记 Special_Risk 单元格
6. THE Tab_3 SHALL 支持动态添加/删除科目行（用户可维护重要科目清单）
7. THE Tab_3 SHALL 在矩阵顶部显示科目总数和各风险等级的单元格计数统计
8. WHEN 用户未对某重要科目的全部相关认定完成评估时, THE Tab_3 SHALL 在该科目行显示"未完成"警告标识

### Requirement 5: 特别风险汇总（Tab 4）

**User Story:** As a 业务合伙人, I want 集中查看所有特别风险及其应对方案, so that 确认每个特别风险都有充分的审计应对。

#### Acceptance Criteria

1. THE Tab_4 SHALL 自动汇总所有在 Tab_3 中标记为 Special_Risk 的单元格，生成特别风险清单
2. THE Tab_4 SHALL 为每项特别风险显示：关联科目、关联认定、风险描述、应对程序描述、关联底稿引用
3. THE Tab_4 SHALL 标识收入确认舞弊推定风险条目（系统自动生成，标注"CAS推定"标签）
4. THE Tab_4 SHALL 标识管理层凌驾控制风险条目（系统自动生成，标注"强制特别风险"标签）
5. WHEN 某特别风险缺少应对程序描述时, THE Tab_4 SHALL 在该条目旁显示"待补充应对"警告
6. THE Tab_4 SHALL 支持为每项特别风险手动添加关联底稿引用（ref_chip 格式，如 D2A-步骤5）

### Requirement 6: CAS 1211 业务规则强制

**User Story:** As a 质量控制复核合伙人, I want 系统自动执行审计准则强制要求, so that 风险评估不会遗漏法定义务。

#### Acceptance Criteria

1. THE Risk_Assessment_Component SHALL 在 Tab_3 中自动预置"收入确认"科目行，其相关认定的 Inherent_Risk 默认为"高"（Fraud_Presumption）
2. WHEN 用户尝试将收入确认相关认定的固有风险降低至非高等级时, THE Risk_Assessment_Component SHALL 弹出 Fraud_Presumption 反驳确认弹窗，要求填写反驳理由
3. THE Risk_Assessment_Component SHALL 要求 Fraud_Presumption 反驳必须经业务合伙人签字确认方可生效
4. THE Risk_Assessment_Component SHALL 自动生成"管理层凌驾控制"作为固定特别风险条目（不可删除、不可降级）
5. WHEN 某风险被标记为 Special_Risk 时, THE Risk_Assessment_Component SHALL 在 Tab_4 中自动验证其应对程序不得仅为实质性分析程序（须包含细节测试）
6. THE Risk_Assessment_Component SHALL 验证所有重要科目的全部相关认定均已完成评估（无遗漏认定）

### Requirement 7: 跨底稿联动

**User Story:** As a 现场经理, I want B50 风险结论自动驱动后续程序表设计, so that 风险评估与程序执行保持一致性。

#### Acceptance Criteria

1. WHEN B50 风险矩阵中某科目某认定的 Combined_Risk 变更时, THE Risk_Assessment_Component SHALL 通过 EventBus 发布风险变更事件（含科目、认定、新风险等级）
2. THE Risk_Assessment_Component SHALL 在 Tab_1 显示来自 B22A/B23 的控制结论摘要（只读引用），供用户参考控制风险评估
3. WHEN Tab_4 特别风险新增或变更时, THE Risk_Assessment_Component SHALL 触发事件通知关联 D~N 程序表需更新应对措施
4. THE Risk_Assessment_Component SHALL 在 Tab_2 报表层面风险变更时，触发 B60 总体策略同步事件
5. THE Risk_Assessment_Component SHALL 支持从 Tab_3/Tab_4 生成 ref_chip 引用，供 D~N 程序表步骤关联

### Requirement 8: 数据持久化

**User Story:** As a 审计助理, I want 所有风险评估数据自动保存, so that 不会因意外关闭而丢失工作。

#### Acceptance Criteria

1. THE Risk_Assessment_Component SHALL 将所有数据存储到 checklist_responses 表，使用 item_id 前缀 `B50-` 区分字段
2. WHEN 用户编辑任意字段后停止输入 2 秒时, THE Risk_Assessment_Component SHALL 自动保存变更到后端（debounce 2000ms）
3. WHEN 用户变更风险等级选择时, THE Risk_Assessment_Component SHALL 立即保存（不等待 debounce）
4. WHEN 保存失败时, THE Risk_Assessment_Component SHALL 显示错误提示并保留本地编辑内容（不回滚）
5. THE Risk_Assessment_Component SHALL 通过 `PUT /api/workpapers/{wp_id}/checklist-responses` 接口批量保存
6. THE Risk_Assessment_Component SHALL 通过 `GET /api/workpapers/{wp_id}/checklist-responses` 加载已保存数据并还原各 tab 状态
7. THE Risk_Assessment_Component SHALL 使用结构化 item_id 命名规则区分 tab 和字段（如 `B50-T1-factor-{n}`、`B50-T3-matrix-{account}-{assertion}`）

### Requirement 9: 合伙人审批与只读流程

**User Story:** As a 业务合伙人, I want 风险评估完成后签字确认并锁定, so that 后续程序设计基于经批准的风险结论。

#### Acceptance Criteria

1. THE Risk_Assessment_Component SHALL 在界面底部提供"合伙人审批"签字区域
2. WHEN 存在未完成评估的科目认定或未填写应对的特别风险时, THE Risk_Assessment_Component SHALL 禁用合伙人签字按钮并显示待完成事项清单
3. WHEN 业务合伙人完成签字时, THE Risk_Assessment_Component SHALL 将全部 tab 转为只读模式
4. WHILE Risk_Assessment_Component 处于已审批只读模式时, THE Risk_Assessment_Component SHALL 在顶部显示"已审批"状态横幅（绿色）和审批人/日期信息
5. WHEN 外部传入 `readonly` prop 为 true 时, THE Risk_Assessment_Component SHALL 强制进入只读模式
6. WHEN 已审批后需要修改风险评估时, THE Risk_Assessment_Component SHALL 要求填写修改原因并重新走合伙人审批流程（通过 Amendment 机制）

### Requirement 10: 组件注册与路由

**User Story:** As a 开发者, I want 新组件正确注册到 htmlRendererRegistry 并通过 wp_code_overrides 路由, so that 打开 B50 底稿时自动渲染新组件。

#### Acceptance Criteria

1. THE Risk_Assessment_Component SHALL 在 htmlRendererRegistry 中注册 componentType 为 `b50-risk-assessment`，contextProps 为 `standard`
2. THE Risk_Assessment_Component SHALL 在 wp_code_overrides.json 中将 `B50` 映射从 `a-program-console` 更新为 `b50-risk-assessment`
3. THE Risk_Assessment_Component SHALL 在 wp_code_overrides.json 中将 `B50-1`、`B50-2`、`B50-3`、`B50-4` 映射为 `skip`（由 B50 统一渲染）
4. THE Risk_Assessment_Component SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly
5. THE Risk_Assessment_Component SHALL emit `save` 事件（保存成功后）和 `completed` 事件（合伙人审批完成时）
6. WHEN 后端 render-config 返回 componentType 为 `b50-risk-assessment` 时, THE 前端路由 SHALL 正确加载 Risk_Assessment_Component

### Requirement 11: 风险矩阵可视化与交互

**User Story:** As a 现场经理, I want 风险矩阵提供直观的可视化效果和高效交互, so that 能快速定位高风险区域并完成评估。

#### Acceptance Criteria

1. THE Risk_Matrix SHALL 使用固定表头（行表头=科目名冻结、列表头=认定名冻结），矩阵内容区域可滚动
2. THE Risk_Matrix SHALL 支持按 Combined_Risk 等级筛选显示（如仅显示"高"风险单元格）
3. THE Risk_Matrix SHALL 在单元格悬停时显示 tooltip，包含完整的三层风险信息和评估备注
4. THE Risk_Matrix SHALL 支持快捷键批量设置：选中多个单元格后一次性设置同一风险等级
5. THE Risk_Matrix SHALL 在右侧提供风险分布统计面板：按科目汇总和按认定汇总的风险计数

### Requirement 12: 响应式布局与打印

**User Story:** As a 审计助理, I want 在不同屏幕和打印场景下正常使用风险矩阵, so that 现场笔记本和归档打印都能满足。

#### Acceptance Criteria

1. THE Risk_Assessment_Component SHALL 在 ≥1024px 宽度下完整显示风险矩阵交叉表（主适配）
2. WHEN 视窗宽度在 768px~1024px 时, THE Risk_Assessment_Component SHALL 通过水平滚动支持矩阵查看，不截断内容
3. THE Risk_Assessment_Component SHALL 提供打印样式表（@media print），Tab_3 风险矩阵输出为 A4 横版
4. WHEN 用户触发打印时, THE Risk_Assessment_Component SHALL 隐藏交互控件，仅保留矩阵数据、颜色编码和统计信息
5. THE Risk_Assessment_Component SHALL 在打印输出中保持风险等级的颜色区分（红/黄/绿）

---

## Correctness Properties

### Property 1: 特别风险 Tab_4 同步不变式

*For any* 矩阵状态，Tab_4 中的特别风险条目集合 SHALL 始终等于 Tab_3 中标记为 Special_Risk 的单元格集合的并集加上系统强制条目（管理层凌驾控制）。添加或移除 Special_Risk 标记后，Tab_4 条目应同步更新。

**Validates: Requirements 5.1, 5.3, 5.4, 6.4**

### Property 2: 收入确认舞弊推定不变式

*For any* 操作序列，收入确认科目相关认定的 Inherent_Risk 等级 SHALL 为"高"，除非存在有效的反驳记录（含反驳理由非空 + 合伙人签字 conclusion='Y'）。无有效反驳时，任何尝试降低该等级的操作应被拒绝。

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 3: 管理层凌驾控制不可变式

*For any* 操作序列，管理层凌驾控制条目 SHALL 始终存在于特别风险清单中，且不可被删除或降级为非特别风险。该条目的 item_id 在持久化后读回应始终存在。

**Validates: Requirements 6.4**

### Property 4: 风险矩阵颜色编码一致性

*For any* Combined_Risk 等级值，矩阵单元格的背景色 SHALL 满足：等级="高" → 红色系、等级="中" → 黄色系、等级="低" → 绿色系。该映射为双射（bijective），不存在同色不同级或同级不同色。

**Validates: Requirements 4.4**

### Property 5: 审批前置条件完备性

*For any* 矩阵状态和 Tab_4 状态的组合，合伙人签字按钮可用当且仅当：(a) 所有重要科目的全部相关认定均已设置 Combined_Risk，且 (b) 所有 Special_Risk 条目均已填写应对程序描述。条件不满足时按钮必须禁用。

**Validates: Requirements 9.2**

### Property 6: 审批后只读不变式

*For any* 已通过合伙人审批（签字 conclusion='Y'）的组件状态，所有 tab 的所有字段 SHALL 处于只读模式。除非通过 Amendment 机制重置审批状态，否则任何编辑操作应被阻止。

**Validates: Requirements 9.3, 9.4, 9.6**

### Property 7: 数据持久化往返一致性

*For any* 有效的风险评估数据（包含 Tab_1~4 全部字段），通过 PUT 保存后再通过 GET 加载，所有字段值（item_id、conclusion、remark、wp_ref）SHALL 与保存前一致（round-trip property）。

**Validates: Requirements 8.1, 8.5, 8.6**

### Property 8: item_id 命名唯一性

*For any* 组合（tab 编号 × 科目 × 认定 × 字段类型），生成的 item_id SHALL 唯一。不同业务含义的数据不可产生相同 item_id，同一业务含义的数据重复保存应覆盖而非新增。

**Validates: Requirements 8.7**

### Property 9: 特别风险应对程序约束

*For any* 标记为 Special_Risk 的风险条目，其应对程序描述中 SHALL 不得仅包含"分析程序"/"分析性程序"/"实质性分析程序"类关键词而无"细节测试"/"函证"/"检查"/"观察"/"询问"等词。此为 CAS 1211 强制要求的形式化约束。

**Validates: Requirements 6.5**

### Property 10: Tab 切换数据保持不变式

*For any* tab 切换操作序列，切换前各 tab 中未保存的编辑内容 SHALL 在切换回后仍然存在。Tab 切换不得触发数据丢失或重置。

**Validates: Requirements 1.3**
