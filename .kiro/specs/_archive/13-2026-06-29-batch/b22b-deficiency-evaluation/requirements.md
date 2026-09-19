# Requirements Document

## Introduction

B22B 内部控制缺陷评价表是审计计划阶段（B循环）的控制缺陷严重程度评价底稿。B22B 位于 B22A（内控了解）下游：当 B22A 识别出控制缺陷（结论="设计无效"或"未实施"）后，缺陷条目自动流入 B22B 进行严重程度评价。评价结果（重大缺陷/重要缺陷/一般缺陷）反馈 B50 控制风险评估，影响实质性程序范围和审计报告意见类型（CAS 1211 / CAS 1231 / CAS 1251）。

业务链路：
- B22A 发现缺陷 → EventBus `control:deficiency-changed` → B22B 自动同步缺陷条目
- B22B 逐项评价严重程度 → EventBus `deficiency:severity-evaluated` → B50 调整控制风险
- 重大缺陷/重要缺陷 → 直接影响审计报告意见类型判断

核心价值：
- 缺陷来源自动同步，消除手工抄录
- 多维度评价框架（报表项目范围/潜在错报金额/补偿性控制/纠正措施）
- 严重程度与重要性水平（B15）自动对比
- 整体评价结论汇总 + 跨底稿联动
- 现场经理复核签字 + 只读 + Amendment 流程

## Glossary

- **Deficiency_Evaluation_Component**: B22B 内部控制缺陷评价表 Vue 组件（componentType = `b22b-deficiency-evaluation`）
- **DeficiencyItem**: 从 B22A 导入的缺陷条目（含 tab/subPanel/index/controlPoint/deficiencyType/elementName）
- **Severity_Level**: 缺陷严重程度枚举：重大缺陷(Material Weakness) / 重要缺陷(Significant Deficiency) / 一般缺陷(Deficiency)
- **Deficiency_Category**: 缺陷分类：设计缺陷 / 运行缺陷
- **Evaluation_Dimension**: 评价维度，包括：报表项目范围/潜在错报金额/补偿性控制/纠正措施
- **Materiality_Level**: 重要性水平（来自 B15 底稿），用于对比潜在错报金额
- **Overall_Conclusion**: 整体评价结论，等于所有缺陷中最高严重程度
- **Compensating_Control**: 补偿性控制，降低缺陷严重程度的替代控制措施
- **Corrective_Action**: 管理层已采取的纠正措施
- **checklist_responses**: 数据持久化表，通过 item_id 前缀 `B22B-` 区分字段
- **htmlRendererRegistry**: 前端 componentType → Vue 组件的单一来源注册表
- **Manager_Review**: 现场经理复核签字
- **EventBus**: 进程内事件总线，用于跨底稿联动

## Requirements

### Requirement 1: 缺陷条目自动同步

**User Story:** As a 现场经理, I want B22A 识别的控制缺陷自动同步到 B22B 评价表, so that 不需要手工抄录缺陷信息且保持两表一致。

#### Acceptance Criteria

1. THE Deficiency_Evaluation_Component SHALL 监听 EventBus `control:deficiency-changed` 事件，自动接收 B22A 发布的缺陷变更数据
2. WHEN 收到 `control:deficiency-changed` 事件中的 `added` 缺陷时, THE Deficiency_Evaluation_Component SHALL 在缺陷评价列表中新增对应条目，预填来源信息（要素名称/控制要点/缺陷类型）
3. WHEN 收到 `control:deficiency-changed` 事件中的 `removed` 缺陷时, THE Deficiency_Evaluation_Component SHALL 从缺陷评价列表中移除对应条目（若已评价则提示确认）
4. THE Deficiency_Evaluation_Component SHALL 在组件初始化时从 B22A 的 checklist_responses 中加载全部现有缺陷条目（item_id 前缀 `B22A-` 中 conclusion 为"设计无效"或"未实施"的记录）
5. THE Deficiency_Evaluation_Component SHALL 在每条缺陷旁显示来源标注：所属要素 Tab 编号 + 要素名称 + 控制要点（只读，不可编辑）
6. WHEN B22A 中缺陷检查项被修改为"设计有效"或"已实施"后, THE Deficiency_Evaluation_Component SHALL 将对应条目标记为"已消除"并从待评价列表移至历史区

### Requirement 2: 缺陷分类

**User Story:** As a 现场经理, I want 对每项缺陷进行分类（设计缺陷/运行缺陷）, so that 后续评价维度和严重程度判断有据可循。

#### Acceptance Criteria

1. THE Deficiency_Evaluation_Component SHALL 为每条缺陷提供"缺陷分类"下拉选项：设计缺陷、运行缺陷
2. WHEN 缺陷来源 deficiencyType 为"设计无效"时, THE Deficiency_Evaluation_Component SHALL 默认将缺陷分类设为"设计缺陷"
3. WHEN 缺陷来源 deficiencyType 为"未实施"时, THE Deficiency_Evaluation_Component SHALL 默认将缺陷分类设为"运行缺陷"
4. THE Deficiency_Evaluation_Component SHALL 允许现场经理修改默认分类（需要时可手动调整）

### Requirement 3: 多维度严重程度评价

**User Story:** As a 现场经理, I want 从多个维度评价每项缺陷的严重程度, so that 评价结论有充分的判断依据且符合审计准则要求。

#### Acceptance Criteria

1. THE Deficiency_Evaluation_Component SHALL 为每条缺陷提供 4 个评价维度输入区域：可能影响的报表项目范围、潜在错报金额、是否存在补偿性控制、管理层是否已采取纠正措施
2. THE Deficiency_Evaluation_Component SHALL 在"可能影响的报表项目范围"维度提供多选控件，列出主要报表项目（资产/负债/所有者权益/收入/费用）
3. THE Deficiency_Evaluation_Component SHALL 在"潜在错报金额"维度提供数值输入框，金额单位为元
4. WHEN 潜在错报金额输入后, THE Deficiency_Evaluation_Component SHALL 自动与重要性水平（B15）进行对比，并显示对比结果（超过/未超过重要性水平）
5. THE Deficiency_Evaluation_Component SHALL 在"补偿性控制"维度提供是/否选择和补偿性控制描述文本区域
6. THE Deficiency_Evaluation_Component SHALL 在"纠正措施"维度提供是/否选择和纠正措施描述文本区域
7. THE Deficiency_Evaluation_Component SHALL 在各评价维度填写完成后提供"严重程度"下拉选项：重大缺陷、重要缺陷、一般缺陷

### Requirement 4: 严重程度判定建议

**User Story:** As a 审计助理, I want 系统根据评价维度输入自动建议严重程度等级, so that 减少人为判断偏差并提高效率。

#### Acceptance Criteria

1. THE Deficiency_Evaluation_Component SHALL 根据评价维度数据自动建议严重程度等级
2. WHEN 潜在错报金额超过重要性水平且无补偿性控制且无纠正措施时, THE Deficiency_Evaluation_Component SHALL 建议严重程度为"重大缺陷"
3. WHEN 潜在错报金额超过重要性水平但存在有效的补偿性控制或已采取纠正措施时, THE Deficiency_Evaluation_Component SHALL 建议严重程度为"重要缺陷"
4. WHEN 潜在错报金额未超过重要性水平时, THE Deficiency_Evaluation_Component SHALL 建议严重程度为"一般缺陷"
5. THE Deficiency_Evaluation_Component SHALL 允许现场经理覆盖自动建议的严重程度（覆盖时需填写调整理由）
6. WHEN 手动覆盖严重程度时, THE Deficiency_Evaluation_Component SHALL 在该条目显示"已手动调整"标识

### Requirement 5: 整体评价结论

**User Story:** As a 业务合伙人, I want 看到全部缺陷评价的汇总结论, so that 快速判断内控缺陷对审计策略的整体影响。

#### Acceptance Criteria

1. THE Deficiency_Evaluation_Component SHALL 在底部汇总区域显示整体评价结论，等于所有缺陷中最高严重程度
2. WHEN 存在任一"重大缺陷"时, THE Deficiency_Evaluation_Component SHALL 将整体评价结论自动设为"存在重大缺陷"
3. WHEN 无"重大缺陷"但存在"重要缺陷"时, THE Deficiency_Evaluation_Component SHALL 将整体评价结论自动设为"存在重要缺陷"
4. WHEN 全部缺陷均为"一般缺陷"时, THE Deficiency_Evaluation_Component SHALL 将整体评价结论自动设为"仅存在一般缺陷"
5. WHEN 无任何缺陷条目时, THE Deficiency_Evaluation_Component SHALL 将整体评价结论设为"未发现控制缺陷"
6. THE Deficiency_Evaluation_Component SHALL 在整体结论旁显示各严重程度缺陷的数量统计（重大N项/重要N项/一般N项）
7. THE Deficiency_Evaluation_Component SHALL 提供"整体评价说明"文本区域供现场经理补充说明

### Requirement 6: 跨底稿联动（B50 风险调整）

**User Story:** As a 现场经理, I want 缺陷评价结论自动通知 B50 调整控制风险, so that 风险评估反映内控缺陷的实际影响。

#### Acceptance Criteria

1. WHEN 任一缺陷的严重程度评定完成或变更时, THE Deficiency_Evaluation_Component SHALL 通过 EventBus 发布 `deficiency:severity-evaluated` 事件
2. THE Deficiency_Evaluation_Component SHALL 发布的事件载荷包含：各缺陷的严重程度列表、整体评价结论、重大/重要缺陷数量
3. WHEN 整体评价结论为"存在重大缺陷"时, THE Deficiency_Evaluation_Component SHALL 在事件载荷中标记 `impactsAuditOpinion: true`
4. WHEN 整体评价结论为"存在重要缺陷"时, THE Deficiency_Evaluation_Component SHALL 在事件载荷中标记 `requiresExtendedProcedures: true`
5. THE Deficiency_Evaluation_Component SHALL 在存在重大缺陷或重要缺陷时显示醒目提示："影响审计报告意见类型，需与业务合伙人沟通"

### Requirement 7: 数据持久化

**User Story:** As a 审计助理, I want 所有缺陷评价数据自动保存, so that 不会因意外关闭而丢失评价工作。

#### Acceptance Criteria

1. THE Deficiency_Evaluation_Component SHALL 将所有数据存储到 checklist_responses 表，使用 item_id 前缀 `B22B-` 区分字段
2. WHEN 用户编辑任意文本字段后停止输入 2 秒时, THE Deficiency_Evaluation_Component SHALL 自动保存变更到后端（debounce 2000ms）
3. WHEN 用户变更缺陷分类、严重程度选择或是否选项时, THE Deficiency_Evaluation_Component SHALL 立即保存（不等待 debounce）
4. WHEN 保存失败时, THE Deficiency_Evaluation_Component SHALL 显示错误提示并保留本地编辑内容（不回滚）
5. THE Deficiency_Evaluation_Component SHALL 通过 `PUT /api/workpapers/{wp_id}/checklist-responses` 接口批量保存
6. THE Deficiency_Evaluation_Component SHALL 通过 `GET /api/workpapers/{wp_id}/checklist-responses` 加载已保存数据并还原评价状态
7. THE Deficiency_Evaluation_Component SHALL 使用结构化 item_id 命名规则（如 `B22B-def-{idx}-severity`、`B22B-def-{idx}-category`、`B22B-overall-conclusion`）

### Requirement 8: 现场经理复核与只读流程

**User Story:** As a 现场经理, I want 缺陷评价完成后签字复核并锁定, so that 后续风险评估基于经复核的缺陷评价结论。

#### Acceptance Criteria

1. THE Deficiency_Evaluation_Component SHALL 在底部提供"现场经理复核"签字区域
2. WHEN 存在未完成严重程度评定的缺陷时, THE Deficiency_Evaluation_Component SHALL 禁用复核签字按钮并显示待完成事项清单
3. WHEN 现场经理完成签字时, THE Deficiency_Evaluation_Component SHALL 将全部内容转为只读模式
4. WHILE Deficiency_Evaluation_Component 处于已复核只读模式时, THE Deficiency_Evaluation_Component SHALL 在顶部显示"已复核"状态横幅（绿色）和复核人/日期信息
5. WHEN 外部传入 `readonly` prop 为 true 时, THE Deficiency_Evaluation_Component SHALL 强制进入只读模式
6. WHEN 已复核后需要修改缺陷评价时, THE Deficiency_Evaluation_Component SHALL 要求填写修改原因并重新走复核流程（Amendment 机制）

### Requirement 9: 组件注册与路由

**User Story:** As a 开发者, I want 新组件正确注册到 htmlRendererRegistry 并通过 wp_code_overrides 路由, so that 打开 B22B 底稿时自动渲染新组件。

#### Acceptance Criteria

1. THE Deficiency_Evaluation_Component SHALL 在 htmlRendererRegistry 中注册 componentType 为 `b22b-deficiency-evaluation`，contextProps 为 `standard`
2. THE Deficiency_Evaluation_Component SHALL 在 wp_code_overrides.json 中新增 `B22B` 映射为 `b22b-deficiency-evaluation`
3. THE Deficiency_Evaluation_Component SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly
4. THE Deficiency_Evaluation_Component SHALL emit `save` 事件（保存成功后）和 `completed` 事件（复核完成时）
5. WHEN 后端 render-config 返回 componentType 为 `b22b-deficiency-evaluation` 时, THE 前端路由 SHALL 正确加载 Deficiency_Evaluation_Component

### Requirement 10: 后端 conclusion 白名单扩展

**User Story:** As a 开发者, I want 后端正确校验 B22B 前缀的 conclusion 值, so that 非法数据无法写入数据库。

#### Acceptance Criteria

1. THE 后端 checklist_responses 校验逻辑 SHALL 识别 item_id 前缀 `B22B-` 并应用 B22B 专用白名单
2. THE B22B conclusion 白名单 SHALL 包含：重大缺陷、重要缺陷、一般缺陷、设计缺陷、运行缺陷、Y、N、存在重大缺陷、存在重要缺陷、仅存在一般缺陷、未发现控制缺陷
3. WHEN B22B 前缀的 item_id 收到不在白名单中的 conclusion 值时, THE 后端 SHALL 返回 HTTP 422 错误和描述性错误信息
4. THE 后端 SHALL 允许 B22B 前缀 item_id 的 remark 字段存储任意文本（用于评价维度描述、调整理由等）

### Requirement 11: 重要性水平对比

**User Story:** As a 现场经理, I want 潜在错报金额自动与重要性水平对比, so that 严重程度判断有量化依据。

#### Acceptance Criteria

1. THE Deficiency_Evaluation_Component SHALL 从项目的 B15 重要性水平数据中获取当前重要性水平金额
2. WHEN 用户输入潜在错报金额时, THE Deficiency_Evaluation_Component SHALL 实时显示与重要性水平的对比结果（"超过重要性水平 X 元"或"未超过重要性水平"）
3. THE Deficiency_Evaluation_Component SHALL 在对比结果中使用颜色区分：超过=红色、未超过=绿色
4. IF 无法获取 B15 重要性水平数据时, THEN THE Deficiency_Evaluation_Component SHALL 显示提示"请先完成 B15 重要性水平确定"并允许手动输入重要性水平作为对比基准

---

## Correctness Properties

### Property 1: 缺陷来源同步不变式

*For any* B22A `control:deficiency-changed` 事件序列，B22B 的缺陷条目列表 SHALL 始终等于 B22A 当前全部 Conclusion 为"设计无效"或"未实施"的检查项集合（不含已消除条目）。added 事件增加条目，removed 事件移除条目，最终状态与 B22A deficiencyList 一致。

**Validates: Requirements 1.1, 1.2, 1.3, 1.6**

### Property 2: 缺陷分类默认映射一致性

*For any* 导入的 DeficiencyItem，缺陷分类默认值 SHALL 满足双射：deficiencyType="设计无效" → 分类="设计缺陷"；deficiencyType="未实施" → 分类="运行缺陷"。手动修改后默认映射不再适用，但不影响其他条目的映射。

**Validates: Requirements 2.2, 2.3**

### Property 3: 严重程度建议逻辑一致性

*For any* 评价维度输入组合（潜在错报金额 M、重要性水平 T、补偿性控制 C、纠正措施 A），自动建议 SHALL 满足：(a) M > T 且 C=否 且 A=否 → 重大缺陷；(b) M > T 且 (C=是 或 A=是) → 重要缺陷；(c) M ≤ T → 一般缺陷。手动覆盖不影响建议计算逻辑。

**Validates: Requirements 4.2, 4.3, 4.4**

### Property 4: 整体评价结论汇总不变式

*For any* 缺陷条目的严重程度集合，整体评价结论 SHALL 等于最高严重程度：存在任一重大缺陷 → "存在重大缺陷"；无重大有重要 → "存在重要缺陷"；全部一般 → "仅存在一般缺陷"；空集 → "未发现控制缺陷"。严重程度变更后整体结论同步更新。

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

### Property 5: EventBus 事件发射正确性

*For any* 缺陷严重程度评定或变更操作，系统 SHALL 发布 `deficiency:severity-evaluated` 事件。事件载荷中 `impactsAuditOpinion` 为 true 当且仅当整体结论为"存在重大缺陷"；`requiresExtendedProcedures` 为 true 当且仅当整体结论为"存在重大缺陷"或"存在重要缺陷"。

**Validates: Requirements 6.1, 6.3, 6.4**

### Property 6: 复核前置条件完备性

*For any* 缺陷条目状态集合，现场经理签字按钮可用当且仅当：所有缺陷条目均已完成严重程度评定（severity 非空）。条件不满足时按钮必须禁用。

**Validates: Requirements 8.2**

### Property 7: 复核后只读不变式

*For any* 已通过现场经理复核（签字 conclusion='Y'）的组件状态或外部 readonly=true，所有字段 SHALL 处于只读模式。除非通过 Amendment 机制重置复核状态，否则任何编辑操作应被阻止。

**Validates: Requirements 8.3, 8.4, 8.5, 8.6**

### Property 8: 数据持久化往返一致性

*For any* 有效的缺陷评价数据（item_id 以 `B22B-` 开头，conclusion 在白名单范围内），通过 PUT 保存后再通过 GET 加载，返回的 { item_id, conclusion, remark, wp_ref } 四元组 SHALL 与保存前完全一致。

**Validates: Requirements 7.1, 7.5, 7.6**

### Property 9: item_id 命名唯一性

*For any* 组合（缺陷序号 × 字段类型），生成的 item_id SHALL 唯一。不同业务含义的数据不可产生相同 item_id，同一业务含义的数据重复保存应覆盖而非新增。

**Validates: Requirements 7.7**

### Property 10: 重要性水平对比幂等性

*For any* 相同的（潜在错报金额, 重要性水平）输入对，对比结果 SHALL 始终一致："超过"当且仅当金额 > 重要性水平；"未超过"当且仅当金额 ≤ 重要性水平。重要性水平变更后所有条目的对比结果 SHALL 同步重新计算。

**Validates: Requirements 11.2, 3.4**

### Property 11: 缺陷数量统计准确性

*For any* 缺陷条目集合及其严重程度分布，汇总区域显示的各严重程度数量统计 SHALL 等于对应严重程度的实际条目计数之和。统计在任何条目严重程度变更后同步更新。

**Validates: Requirements 5.6**
