# Requirements Document

## Introduction

B22A 内部控制了解程序表是审计计划阶段（B循环）的核心底稿，系统执行对被审计单位内部控制五要素的了解程序，评估控制环境质量和各要素设计的有效性（CAS 1211 / CAS 1231）。B22A 的控制结论直接输入 B50 控制风险评估，并通过 B23 系列流程层面了解形成完整的内控画像。

当前实现使用 10+ 个独立 `d-form-table` 底稿（B22A-1 至 B22A-5，加 B22A-4-1 至 B22A-4-5 的 IT 控制子表），用户必须打开多达 11 个底稿才能完成内部控制了解。本 spec 定义一个统一的 `b22a-control-matrix` HTML 专用组件，将全部 B22A 子底稿聚合为 5-element tab + IT 子区 + 汇总 tab 界面，提供结构化检查项评估、自动汇总矩阵、跨底稿联动和现场经理复核流程。

核心价值：
- 将 11 次打开 → 1 次打开，消除碎片体验
- COSO 五要素 tab 直观对应审计准则框架
- IT 控制子区按依赖程度自动决定执行范围
- 控制设计有效性自动汇总矩阵（替代 B22C 手工汇总）
- 控制结论 → B50 控制风险输入自动联动

## Glossary

- **Control_Matrix_Component**: B22A 内部控制了解程序表 Vue 组件（componentType = `b22a-control-matrix`）
- **COSO_Element**: 内部控制五要素（控制环境/风险评估过程/信息系统与沟通/控制活动/监督）
- **Tab_1**: 控制环境（B22A-1 内容）
- **Tab_2**: 风险评估过程（B22A-2 内容）
- **Tab_3**: 信息系统与沟通（B22A-3 内容）
- **Tab_4**: 控制活动（B22A-4 + IT 子表 B22A-4-1~4-5 内容）
- **Tab_5**: 监督（B22A-5 内容）
- **Summary_Tab**: 控制矩阵汇总（B22C 等价功能）
- **Check_Item**: 检查项目，每个要素下的具体控制要点（行单位）
- **Conclusion**: 检查项结论枚举：设计有效/设计无效/已实施/未实施/不适用
- **Understanding_Method**: 了解程序类型：询问/观察/检查文件/穿行测试
- **Element_Score**: 要素层面有效性评分，由该要素下检查项结论自动汇总
- **IT_Dependency**: IT 依赖程度（高/中/低），决定 IT 控制子区执行范围
- **ITGC**: IT 通用控制（IT General Controls）
- **IT_App_Control**: IT 应用控制
- **Design_Effectiveness**: 控制设计有效性（本底稿仅评估设计，不测试运行有效性）
- **Control_Deficiency**: 控制缺陷，设计无效或未实施的检查项
- **checklist_responses**: 数据持久化表，通过 item_id 前缀 `B22A-` 区分字段
- **htmlRendererRegistry**: 前端 componentType → Vue 组件的单一来源注册表
- **Manager_Review**: 现场经理复核签字
- **Prior_Year_Carry_Forward**: 续审项目从上年工作底稿继承数据

## Requirements

### Requirement 1: 5-Element Tab + 汇总统一界面

**User Story:** As a 现场经理, I want 在一个界面中完成全部内控五要素了解工作, so that 不再需要在 11 个底稿间切换。

#### Acceptance Criteria

1. THE Control_Matrix_Component SHALL 渲染 6 个 tab 页签：Tab_1"控制环境"、Tab_2"风险评估过程"、Tab_3"信息系统与沟通"、Tab_4"控制活动"、Tab_5"监督"、Summary_Tab"控制矩阵汇总"
2. THE Control_Matrix_Component SHALL 默认激活 Tab_1（控制环境）作为首个工作区
3. WHEN 用户切换 tab 时, THE Control_Matrix_Component SHALL 保留其他 tab 的编辑状态（不丢失未保存数据）
4. THE Control_Matrix_Component SHALL 在各 tab 页签上显示该要素的完成状态指示（未填/部分填写/已完成）
5. THE Control_Matrix_Component SHALL 使用中文标签，所有 UI 文字与审计准则术语一致
6. THE Control_Matrix_Component SHALL 在 tab 栏右侧显示整体内控了解完成进度（已完成要素数/5）

### Requirement 2: 检查项评估表结构（Tab 1~5 通用）

**User Story:** As a 审计助理, I want 每个要素下有结构化的检查项列表供逐项评估, so that 了解程序执行有据可查且不遗漏。

#### Acceptance Criteria

1. THE Control_Matrix_Component SHALL 为每个 COSO_Element tab 渲染检查项表格，每行包含：序号、控制要点、控制活动描述、了解方法（Understanding_Method 多选）、结论（Conclusion 下拉）、参考依据/索引
2. THE Control_Matrix_Component SHALL 提供 Understanding_Method 多选选项：询问、观察、检查文件、穿行测试
3. THE Control_Matrix_Component SHALL 提供 Conclusion 下拉选项：设计有效、设计无效、已实施、未实施、不适用
4. WHEN 用户新增检查项行时, THE Control_Matrix_Component SHALL 自动分配行序号并提供空白可编辑行
5. THE Control_Matrix_Component SHALL 支持删除用户新增的检查项行（预置检查项不可删除，需确认后执行）
6. THE Control_Matrix_Component SHALL 为每个要素 tab 底部提供"审计说明"文本区域和"要素整体结论"下拉（有效/部分有效/无效）
7. WHEN 某检查项 Conclusion 为"设计无效"或"未实施"时, THE Control_Matrix_Component SHALL 在该行显示红色警告标识并标注为 Control_Deficiency

### Requirement 3: Tab 4 IT 控制子区

**User Story:** As a 现场经理, I want 控制活动 tab 内嵌 IT 控制子区域, so that IT 环境了解和 ITGC 评估在同一上下文中完成。

#### Acceptance Criteria

1. THE Tab_4 SHALL 在常规控制活动检查项下方提供可展开/收起的 IT 控制子区（默认展开状态由 IT_Dependency 决定）
2. THE Tab_4 IT 子区 SHALL 包含 6 个子面板（手风琴或子 tab）：IT环境了解、ITGC、IT应用控制、变更管理、访问安全、职责分离
3. WHEN IT_Dependency 为"高"时, THE Tab_4 SHALL 默认展开 IT 子区且所有子面板标记为"必填"
4. WHEN IT_Dependency 为"低"时, THE Tab_4 SHALL 默认收起 IT 子区并标注"可简化执行"提示
5. THE Tab_4 SHALL 在子区顶部提供 IT_Dependency 选择控件（高/中/低下拉），供现场经理设定
6. THE Tab_4 IT 子区各子面板 SHALL 使用与主检查项表格相同的行结构（序号/控制要点/描述/方法/结论/引用）
7. WHEN ITGC 整体结论为"无效"时, THE Tab_4 SHALL 在 IT 应用控制子面板顶部显示警告："ITGC 无效，IT 应用控制依赖程度降低"

### Requirement 4: 控制矩阵汇总（Summary Tab）

**User Story:** As a 业务合伙人, I want 在汇总 tab 一目了然查看五要素整体有效性评价, so that 快速判断控制环境对审计策略的影响。

#### Acceptance Criteria

1. THE Summary_Tab SHALL 渲染交叉汇总表：行=控制目标/检查维度，列=5个 COSO_Element，单元格=该要素该维度的评价结论
2. THE Summary_Tab SHALL 从 Tab_1~5 的各检查项结论自动聚合计算每个要素的 Element_Score
3. THE Summary_Tab SHALL 对单元格进行颜色编码：有效=绿色、部分有效=黄色、无效=红色、不适用=灰色
4. THE Summary_Tab SHALL 在汇总表底部显示"企业层面控制整体结论"下拉（有效/部分有效/无效）和说明文本区域
5. WHEN 任一要素的 Element_Score 为"无效"时, THE Summary_Tab SHALL 在整体结论区域显示醒目警告："存在无效要素，需提高整体风险评估"
6. THE Summary_Tab SHALL 显示各要素的统计信息：有效项数/无效项数/未实施项数/总检查项数
7. THE Summary_Tab SHALL 支持打印输出为 A4 横版格式

### Requirement 5: 要素有效性自动计算

**User Story:** As a 现场经理, I want 系统根据各检查项结论自动计算要素层面有效性, so that 减少手工汇总的错误和工作量。

#### Acceptance Criteria

1. THE Control_Matrix_Component SHALL 根据各要素下检查项的 Conclusion 分布自动计算 Element_Score
2. WHEN 某要素全部检查项 Conclusion 为"设计有效"或"已实施"或"不适用"时, THE Control_Matrix_Component SHALL 将该要素 Element_Score 设为"有效"
3. WHEN 某要素存在"设计无效"或"未实施"的检查项但占比不超过 20% 时, THE Control_Matrix_Component SHALL 将该要素 Element_Score 建议为"部分有效"
4. WHEN 某要素存在"设计无效"或"未实施"的检查项且占比超过 20% 时, THE Control_Matrix_Component SHALL 将该要素 Element_Score 建议为"无效"
5. THE Control_Matrix_Component SHALL 允许现场经理手动覆盖自动计算的 Element_Score（覆盖时需填写说明理由）
6. WHEN 手动覆盖 Element_Score 时, THE Control_Matrix_Component SHALL 在该要素 tab 显示"已手动调整"标识

### Requirement 6: 控制缺陷联动

**User Story:** As a 现场经理, I want 标记为设计无效的检查项自动关联到 B22B 控制缺陷评价, so that 缺陷发现与评价流程衔接无缝。

#### Acceptance Criteria

1. THE Control_Matrix_Component SHALL 自动收集所有 Conclusion 为"设计无效"或"未实施"的检查项，生成控制缺陷清单
2. THE Control_Matrix_Component SHALL 在 Summary_Tab 底部显示"控制缺陷汇总"区域，列出全部缺陷项（来源要素 + 控制要点 + 缺陷类型）
3. WHEN 存在控制缺陷时, THE Control_Matrix_Component SHALL 通过 EventBus 发布控制缺陷变更事件，供 B22B 底稿接收
4. THE Control_Matrix_Component SHALL 支持从缺陷条目生成 ref_chip 引用，供 B22B 关联使用
5. WHEN 缺陷检查项的 Conclusion 被修改为"设计有效"时, THE Control_Matrix_Component SHALL 从缺陷清单中移除该项并触发联动更新

### Requirement 7: 跨底稿联动

**User Story:** As a 现场经理, I want B22A 控制结论自动输入 B50 控制风险评估, so that 风险评估与内控了解保持一致性。

#### Acceptance Criteria

1. WHEN Summary_Tab 的企业层面控制整体结论变更时, THE Control_Matrix_Component SHALL 通过 EventBus 发布控制结论变更事件（含五要素各自结论 + 整体结论）
2. THE Control_Matrix_Component SHALL 发布的事件格式包含：各要素 Element_Score、IT_Dependency 等级、ITGC 结论、整体结论
3. WHEN Tab_4 IT_Dependency 或 ITGC 结论变更时, THE Control_Matrix_Component SHALL 触发 IT 控制结论变更事件
4. THE Control_Matrix_Component SHALL 支持从各 tab 检查项生成 ref_chip 引用，供 B23 系列和 B50 关联使用
5. THE Control_Matrix_Component SHALL 在 Tab_1 控制环境结论为"无效"时，触发控制环境薄弱事件，提示 B50 需提高整体风险评估

### Requirement 8: 首年审计与续审逻辑

**User Story:** As a 现场经理, I want 续审项目可从上年底稿继承内控了解数据并仅更新变化部分, so that 减少重复工作量。

#### Acceptance Criteria

1. THE Control_Matrix_Component SHALL 识别项目审计类型（首年审计/续审项目），通过项目元数据判断
2. WHEN 项目为首年审计时, THE Control_Matrix_Component SHALL 要求全部 5 个要素的检查项必须逐项完成（不允许跳过）
3. WHEN 项目为续审项目时, THE Control_Matrix_Component SHALL 支持从上年 checklist_responses 加载历史数据作为初始值
4. WHEN 续审项目加载上年数据后, THE Control_Matrix_Component SHALL 在各检查项行标注"上年结论"提示（灰色文字）
5. THE Control_Matrix_Component SHALL 在续审模式下允许用户标记"本年无变化"快速确认检查项（保留上年结论）
6. WHEN 续审项目标记"本年无变化"时, THE Control_Matrix_Component SHALL 记录确认人和确认日期

### Requirement 9: 数据持久化

**User Story:** As a 审计助理, I want 所有内控了解数据自动保存, so that 不会因意外关闭而丢失工作。

#### Acceptance Criteria

1. THE Control_Matrix_Component SHALL 将所有数据存储到 checklist_responses 表，使用 item_id 前缀 `B22A-` 区分字段
2. WHEN 用户编辑任意字段后停止输入 2 秒时, THE Control_Matrix_Component SHALL 自动保存变更到后端（debounce 2000ms）
3. WHEN 用户变更 Conclusion 或 Element_Score 选择时, THE Control_Matrix_Component SHALL 立即保存（不等待 debounce）
4. WHEN 保存失败时, THE Control_Matrix_Component SHALL 显示错误提示并保留本地编辑内容（不回滚）
5. THE Control_Matrix_Component SHALL 通过 `PUT /api/workpapers/{wp_id}/checklist-responses` 接口批量保存
6. THE Control_Matrix_Component SHALL 通过 `GET /api/workpapers/{wp_id}/checklist-responses` 加载已保存数据并还原各 tab 状态
7. THE Control_Matrix_Component SHALL 使用结构化 item_id 命名规则区分 tab、子区和字段（如 `B22A-T1-item-{n}-conclusion`、`B22A-T4-IT-ITGC-{n}-conclusion`）

### Requirement 10: 现场经理复核与只读流程

**User Story:** As a 现场经理, I want 内控了解完成后签字复核并锁定, so that 后续控制测试和风险评估基于经复核的控制了解。

#### Acceptance Criteria

1. THE Control_Matrix_Component SHALL 在 Summary_Tab 底部提供"现场经理复核"签字区域
2. WHEN 存在未完成评估的要素（任一要素有检查项 Conclusion 为空）时, THE Control_Matrix_Component SHALL 禁用复核签字按钮并显示待完成事项清单
3. WHEN 现场经理完成签字时, THE Control_Matrix_Component SHALL 将全部 tab 转为只读模式
4. WHILE Control_Matrix_Component 处于已复核只读模式时, THE Control_Matrix_Component SHALL 在顶部显示"已复核"状态横幅（绿色）和复核人/日期信息
5. WHEN 外部传入 `readonly` prop 为 true 时, THE Control_Matrix_Component SHALL 强制进入只读模式
6. WHEN 已复核后需要修改内控了解时, THE Control_Matrix_Component SHALL 要求填写修改原因并重新走复核流程

### Requirement 11: 组件注册与路由

**User Story:** As a 开发者, I want 新组件正确注册到 htmlRendererRegistry 并通过 wp_code_overrides 路由, so that 打开 B22A 底稿时自动渲染新组件。

#### Acceptance Criteria

1. THE Control_Matrix_Component SHALL 在 htmlRendererRegistry 中注册 componentType 为 `b22a-control-matrix`，contextProps 为 `standard`
2. THE Control_Matrix_Component SHALL 在 wp_code_overrides.json 中新增 `B22A` 映射为 `b22a-control-matrix`
3. THE Control_Matrix_Component SHALL 在 wp_code_overrides.json 中将 `B22A-1`、`B22A-2`、`B22A-3`、`B22A-4`、`B22A-4-1`、`B22A-4-2`、`B22A-4-3`、`B22A-4-4-1`、`B22A-4-4-2`、`B22A-4-5`、`B22A-5` 映射为 `skip`（由 B22A 统一渲染）
4. THE Control_Matrix_Component SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly
5. THE Control_Matrix_Component SHALL emit `save` 事件（保存成功后）和 `completed` 事件（复核完成时）
6. WHEN 后端 render-config 返回 componentType 为 `b22a-control-matrix` 时, THE 前端路由 SHALL 正确加载 Control_Matrix_Component

### Requirement 12: 响应式布局与打印

**User Story:** As a 审计助理, I want 在不同屏幕和打印场景下正常使用内控了解表, so that 现场笔记本和归档打印都能满足。

#### Acceptance Criteria

1. THE Control_Matrix_Component SHALL 在 ≥1024px 宽度下完整显示检查项表格和汇总矩阵（主适配）
2. WHEN 视窗宽度在 768px~1024px 时, THE Control_Matrix_Component SHALL 通过水平滚动支持表格查看，不截断内容
3. THE Control_Matrix_Component SHALL 提供打印样式表（@media print），Summary_Tab 汇总矩阵输出为 A4 横版
4. WHEN 用户触发打印时, THE Control_Matrix_Component SHALL 隐藏交互控件，仅保留检查项数据、结论和颜色编码
5. THE Control_Matrix_Component SHALL 在打印输出中保持有效性评价的颜色区分（绿/黄/红）

### Requirement 13: 控制环境薄弱业务规则

**User Story:** As a 质量控制复核合伙人, I want 系统在控制环境薄弱时自动预警, so that 不会遗漏对整体风险评估的影响。

#### Acceptance Criteria

1. WHEN Tab_1 控制环境的 Element_Score 为"无效"或"部分有效"且存在管理层诚信/治理层独立性相关检查项为"设计无效"时, THE Control_Matrix_Component SHALL 在 Summary_Tab 顶部显示红色警告横幅："控制环境薄弱——建议提高整体风险评估"
2. THE Control_Matrix_Component SHALL 在控制环境薄弱警告中提供跳转链接到 B50 风险评估底稿
3. WHEN 控制环境从薄弱恢复为有效时, THE Control_Matrix_Component SHALL 移除警告横幅并通知 B50
4. THE Control_Matrix_Component SHALL 在 IT_Dependency 为"高"且 ITGC 结论为"无效"时，在 Tab_4 和 Summary_Tab 显示 IT 控制薄弱警告

---

## Correctness Properties

### Property 1: 汇总矩阵同步不变式

*For any* Tab_1~5 检查项状态变更，Summary_Tab 中各要素的统计数据（有效项数/无效项数/未实施项数）SHALL 始终等于对应 tab 中检查项 Conclusion 的实际分布计数。添加/修改/删除检查项后，Summary_Tab 应同步更新。

**Validates: Requirements 4.2, 4.6, 5.1**

### Property 2: Element_Score 自动计算一致性

*For any* 要素下的检查项 Conclusion 分布，自动计算的 Element_Score SHALL 满足：(a) 全部为有效/已实施/不适用 → "有效"；(b) 存在无效/未实施且占比≤20% → "部分有效"；(c) 占比>20% → "无效"。手动覆盖不影响计算逻辑，仅覆盖显示值。

**Validates: Requirements 5.2, 5.3, 5.4**

### Property 3: 控制缺陷清单同步不变式

*For any* 检查项 Conclusion 变更，缺陷清单 SHALL 始终等于所有 Conclusion 为"设计无效"或"未实施"的检查项集合。将缺陷项修改为"设计有效"后应从清单移除；将有效项修改为"设计无效"后应加入清单。

**Validates: Requirements 6.1, 6.5, 2.7**

### Property 4: IT 依赖程度作用域约束

*For any* IT_Dependency 等级值，Tab_4 IT 子区的必填/选填状态 SHALL 满足：高 → 全部子面板必填且展开；中 → 子面板可选择性执行；低 → 子面板默认收起且标注"可简化"。IT_Dependency 切换不改变已填写的数据。

**Validates: Requirements 3.3, 3.4, 3.5**

### Property 5: ITGC 结论传递约束

*For any* ITGC 子面板结论状态，WHEN ITGC 结论为"无效"时，IT 应用控制子面板 SHALL 显示依赖程度降低警告。ITGC 结论变更 SHALL 触发 EventBus 事件。此为单向传递：IT 应用控制结论不影响 ITGC 结论。

**Validates: Requirements 3.7, 7.3**

### Property 6: 复核前置条件完备性

*For any* 五要素检查项状态组合，现场经理签字按钮可用当且仅当：所有要素的全部检查项（不含标记为"不适用"的）均已设置 Conclusion，且 Summary_Tab 整体结论已选择。条件不满足时按钮必须禁用。

**Validates: Requirements 10.2**

### Property 7: 复核后只读不变式

*For any* 已通过现场经理复核（签字 conclusion='Y'）的组件状态，所有 tab 的所有字段 SHALL 处于只读模式。除非通过修改原因重置复核状态，否则任何编辑操作应被阻止。

**Validates: Requirements 10.3, 10.4, 10.6**

### Property 8: 数据持久化往返一致性

*For any* 有效的内控了解数据（包含 Tab_1~5 + IT 子区全部字段），通过 PUT 保存后再通过 GET 加载，所有字段值（item_id、conclusion、remark、wp_ref）SHALL 与保存前一致（round-trip property）。

**Validates: Requirements 9.1, 9.5, 9.6**

### Property 9: item_id 命名唯一性

*For any* 组合（tab 编号 × 子区标识 × 行序号 × 字段类型），生成的 item_id SHALL 唯一。不同业务含义的数据不可产生相同 item_id，同一业务含义的数据重复保存应覆盖而非新增。

**Validates: Requirements 9.7**

### Property 10: Tab 切换数据保持不变式

*For any* tab 切换操作序列，切换前各 tab 中未保存的编辑内容 SHALL 在切换回后仍然存在。Tab 切换不得触发数据丢失或重置。

**Validates: Requirements 1.3**

### Property 11: 颜色编码双射

*For any* Conclusion 或 Element_Score 值，汇总矩阵单元格的背景色 SHALL 满足：有效→绿色系、部分有效→黄色系、无效→红色系、不适用→灰色系。该映射为双射，不存在同色不同级或同级不同色。

**Validates: Requirements 4.3**

### Property 12: 续审数据继承完整性

*For any* 续审项目加载上年数据的操作，加载后各检查项的初始值 SHALL 等于上年对应 item_id 的存储值。加载过程不改变当年项目的已有编辑内容（仅填充空白项）。

**Validates: Requirements 8.3, 8.4**

### Property 13: EventBus 控制结论变更事件发射

*For any* Summary_Tab 整体结论或要素 Element_Score 变更操作且新旧值不同，系统 SHALL 发布包含 `{ element, oldScore, newScore, overallConclusion }` 的控制结论变更事件。未变更时不发射事件。

**Validates: Requirements 7.1, 7.2**
