# Requirements Document

## Introduction

C2~C15 是审计执行阶段的内部控制测试底稿（CAS 1231 控制测试），每个 Cx 对应一个业务循环的控制测试执行。当前实现使用通用 `d-form-table` 渲染，缺乏控制测试专属交互（样本管理、偏差率计算、结论联动）。

本 spec 定义一个可复用的 `c-control-test` HTML 专用组件，14 个循环（C2~C15）共用同一组件、通过 wp_code/cycle 上下文区分数据。组件提供：
- 卡片式控制点测试 UI（从 B23 引用控制点）
- 测试方法多选 + 样本管理 + 逐笔结果记录
- 偏差率自动计算 + 控制点结论自动建议
- 循环级整体结论 + EventBus 发布至 B50 风险修正
- Cx-2 证据明细嵌入 Tab + ref_chip 导航（B23/B50/D~N）
- 复核签字 + 只读锁定

核心价值：
- 14 循环统一组件，消除重复开发
- B23 控制了解→C 控制测试→B50 风险修正→D~N 程序范围，形成完整控制测试闭环
- 精美卡片 UI 替代枯燥表格，提升现场使用体验
- 偏差率自动计算减少手工错误

## Glossary

- **Control_Test_Component**: C 类控制测试 Vue 组件（componentType = `c-control-test`）
- **Control_Point_Card**: 控制点测试卡片，每个被测试控制点一张可折叠卡片
- **Test_Method**: 测试方法枚举（多选）：询问(inquiry)/观察(observation)/检查(inspection)/重新执行(reperformance)
- **Sample_Item**: 样本明细条目，包含凭证编号/日期/金额
- **Sample_Result**: 单笔样本测试结果枚举：有效/偏差/不适用
- **Deviation_Rate**: 偏差率 = 偏差数 / 有效样本总数（排除"不适用"）
- **Control_Point_Conclusion**: 控制点级结论枚举：控制有效运行/控制存在偏差但可接受/控制无效
- **Cycle_Conclusion**: 循环级整体结论枚举：全部有效/部分偏差/控制失效
- **B23_Reference**: 从 B23 业务流程与控制了解表引用的控制点数据（控制编号+控制目标）
- **Evidence_Tab**: 证据管理 Tab，嵌入渲染 Cx-2 明细底稿
- **Linkage_Panel**: 联动面板，ref_chip 跳转 B23/B50/DA~KA
- **checklist_responses**: 数据持久化表，通过 item_id 前缀 `C{n}-` 区分字段
- **htmlRendererRegistry**: 前端 componentType → Vue 组件的单一来源注册表
- **EventBus**: 进程内事件总线，C 组件发布 `control:test-concluded` 事件
- **Manager_Review**: 现场经理复核签字
- **Tolerable_Deviation_Rate**: 可容忍偏差率阈值（默认 10%，可由用户调整）

## Requirements

### Requirement 1: 组件注册与路由

**User Story:** As a 开发者, I want 新组件正确注册到 htmlRendererRegistry 并通过 wp_code_overrides 路由, so that 打开 C2~C15 底稿时自动渲染新组件。

#### Acceptance Criteria

1. THE Control_Test_Component SHALL 在 htmlRendererRegistry 中注册 componentType 为 `c-control-test`，contextProps 为 `standard`
2. THE Control_Test_Component SHALL 在 wp_code_overrides.json 中将 `C2`、`C3`、`C4`、`C5`、`C6`、`C7`、`C8`、`C9`、`C10`、`C11`、`C12`、`C13`、`C14`、`C15` 映射为 `c-control-test`
3. THE Control_Test_Component SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly
4. THE Control_Test_Component SHALL emit `save` 事件（保存成功后）和 `completed` 事件（复核完成时）
5. WHEN 后端 render-config 返回 componentType 为 `c-control-test` 时, THE 前端路由 SHALL 正确加载 Control_Test_Component
6. THE Control_Test_Component SHALL 根据 wpCode prop（C2~C15）确定当前测试的业务循环上下文

### Requirement 2: B23 控制点引用卡片

**User Story:** As a 审计助理, I want 看到从 B23 引用的该循环控制点清单, so that 明确知道需要测试哪些控制点。

#### Acceptance Criteria

1. THE Control_Test_Component SHALL 在顶部渲染 B23_Reference 面板，显示该循环对应的控制点清单（控制点编号 + 控制目标）
2. THE B23_Reference 面板 SHALL 通过 API 或 EventBus 从 B23 获取当前循环的控制点数据
3. WHEN B23 尚未完成该循环的控制了解时, THE B23_Reference 面板 SHALL 显示"B23 尚未录入该循环控制点"提示，并允许用户手动添加控制点
4. THE Control_Test_Component SHALL 为每个引用的控制点生成一张 Control_Point_Card
5. THE B23_Reference 面板 SHALL 提供 ref_chip 跳转到 B23 对应流程卡片
6. WHEN 用户手动新增控制点时, THE Control_Test_Component SHALL 分配递增编号并在 B23_Reference 面板下方追加新卡片

### Requirement 3: 测试方法选择

**User Story:** As a 审计助理, I want 为每个控制点选择测试方法, so that 记录实际执行的控制测试类型。

#### Acceptance Criteria

1. THE Control_Point_Card SHALL 提供 Test_Method 多选区域，选项为：询问、观察、检查、重新执行
2. THE Control_Test_Component SHALL 至少选择一种 Test_Method 后方可进入样本录入阶段
3. WHEN 用户选择"重新执行"时, THE Control_Point_Card SHALL 显示提示："重新执行需逐笔记录执行过程"
4. THE Test_Method 选择 SHALL 即时保存（不等待 debounce）

### Requirement 4: 样本管理

**User Story:** As a 审计助理, I want 为每个控制点添加/管理测试样本, so that 记录抽样范围和具体样本信息。

#### Acceptance Criteria

1. THE Control_Point_Card SHALL 在 Test_Method 下方提供样本管理区域，包含：样本量显示、样本明细列表
2. THE Control_Test_Component SHALL 支持逐条添加 Sample_Item（字段：凭证编号、日期、金额）
3. THE Control_Test_Component SHALL 支持删除已添加的 Sample_Item
4. THE Control_Test_Component SHALL 在样本管理区域顶部显示"样本量: N 笔"统计
5. WHEN 样本量为 0 时, THE Control_Point_Card SHALL 显示"请添加测试样本"占位提示
6. THE Control_Test_Component SHALL 支持批量添加样本（输入起止凭证号/日期范围快捷生成）

### Requirement 5: 逐笔样本测试结果记录

**User Story:** As a 审计助理, I want 为每笔样本记录测试结果, so that 逐笔追踪控制执行情况。

#### Acceptance Criteria

1. THE Control_Test_Component SHALL 在每条 Sample_Item 右侧提供 Sample_Result 选择：有效/偏差/不适用
2. WHEN Sample_Result 选择"偏差"时, THE Control_Test_Component SHALL 展开偏差描述文本框供填写
3. THE Control_Test_Component SHALL 对每条偏差样本以红色背景高亮显示
4. THE Sample_Result 选择 SHALL 即时保存（不等待 debounce）
5. THE 偏差描述文本框 SHALL 使用 debounce 2000ms 保存

### Requirement 6: 偏差自动计算

**User Story:** As a 现场经理, I want 系统自动计算每个控制点的偏差数和偏差率, so that 减少手工计算错误。

#### Acceptance Criteria

1. THE Control_Point_Card SHALL 实时显示偏差统计：偏差数 / 有效样本总数 = 偏差率
2. THE Deviation_Rate 计算 SHALL 排除 Sample_Result 为"不适用"的样本（偏差率 = 偏差数 ÷ (总样本 - 不适用样本)）
3. WHEN Deviation_Rate 超过 Tolerable_Deviation_Rate 时, THE Control_Point_Card SHALL 以红色高亮偏差率并显示"超出可容忍偏差率"警告
4. WHEN 所有样本均为"不适用"时, THE Control_Point_Card SHALL 显示"无有效样本，无法计算偏差率"
5. THE Control_Test_Component SHALL 在页面顶部提供 Tolerable_Deviation_Rate 设置（默认 10%，范围 0%~50%）

### Requirement 7: 控制点结论

**User Story:** As a 现场经理, I want 系统根据偏差率自动建议控制点结论, so that 减少主观判断偏差。

#### Acceptance Criteria

1. THE Control_Point_Card SHALL 在样本结果下方提供 Control_Point_Conclusion 选择区域：控制有效运行/控制存在偏差但可接受/控制无效
2. THE Control_Test_Component SHALL 根据 Deviation_Rate 自动建议 Control_Point_Conclusion
3. WHEN Deviation_Rate 为 0% 时, THE Control_Test_Component SHALL 建议"控制有效运行"
4. WHEN Deviation_Rate 在 0% 到 Tolerable_Deviation_Rate（含）之间时, THE Control_Test_Component SHALL 建议"控制存在偏差但可接受"
5. WHEN Deviation_Rate 超过 Tolerable_Deviation_Rate 时, THE Control_Test_Component SHALL 建议"控制无效"
6. THE Control_Test_Component SHALL 允许用户手动覆盖自动建议（覆盖时需填写理由）
7. WHEN 手动覆盖结论时, THE Control_Point_Card SHALL 显示"已手动调整"标识和覆盖理由

### Requirement 8: 循环级整体结论

**User Story:** As a 现场经理, I want 系统汇总各控制点结论给出循环级整体结论, so that 一目了然判断该循环控制测试总体结果。

#### Acceptance Criteria

1. THE Control_Test_Component SHALL 在所有 Control_Point_Card 下方提供 Cycle_Conclusion 汇总区域
2. THE Control_Test_Component SHALL 根据全部控制点的 Control_Point_Conclusion 自动建议 Cycle_Conclusion
3. WHEN 全部控制点结论为"控制有效运行"时, THE Control_Test_Component SHALL 建议 Cycle_Conclusion 为"全部有效"
4. WHEN 存在"控制存在偏差但可接受"但无"控制无效"时, THE Control_Test_Component SHALL 建议 Cycle_Conclusion 为"部分偏差"
5. WHEN 存在任一控制点结论为"控制无效"时, THE Control_Test_Component SHALL 建议 Cycle_Conclusion 为"控制失效"
6. THE Control_Test_Component SHALL 允许用户手动覆盖 Cycle_Conclusion（覆盖时需填写理由）
7. WHEN Cycle_Conclusion 变更时, THE Control_Test_Component SHALL 立即保存

### Requirement 9: ref_chip 联动面板

**User Story:** As a 现场经理, I want 在控制测试界面中快速跳转到相关底稿, so that 快速查阅控制了解、风险评估和实质性程序。

#### Acceptance Criteria

1. THE Control_Test_Component SHALL 提供 Linkage_Panel 显示关联底稿列表
2. THE Linkage_Panel SHALL 提供 ref_chip 跳转到 B23 对应流程（当前循环的控制了解）
3. THE Linkage_Panel SHALL 提供 ref_chip 跳转到 B50 风险评估（控制风险行）
4. THE Linkage_Panel SHALL 提供 ref_chip 跳转到对应 D~N 循环程序表（如 C2→DA, C3→EA）
5. WHEN Cycle_Conclusion 为"控制失效"时, THE Linkage_Panel SHALL 高亮 D~N 关联并显示"需扩大实质性程序范围"提示

### Requirement 10: EventBus 发布测试结论

**User Story:** As a 开发者, I want 控制测试结论通过 EventBus 通知 B50, so that 风险评估能实时反映控制测试结果。

#### Acceptance Criteria

1. WHEN Cycle_Conclusion 变更时, THE Control_Test_Component SHALL 通过 EventBus 发布 `control:test-concluded` 事件
2. THE `control:test-concluded` 事件载荷 SHALL 包含：wpCode（C2~C15）、cycleName（循环名称）、conclusion（Cycle_Conclusion）、deviationSummary（各控制点偏差率摘要）
3. THE Control_Test_Component SHALL 仅在 Cycle_Conclusion 实际变更（新旧值不同）时发布事件
4. THE Control_Test_Component SHALL 在组件卸载时注销 EventBus 监听

### Requirement 11: 证据管理 Tab

**User Story:** As a 审计助理, I want 在控制测试界面内查看和管理证据明细, so that 不必切换底稿即可关联证据。

#### Acceptance Criteria

1. THE Control_Test_Component SHALL 提供"证据明细"Tab，嵌入渲染对应的 Cx-2 底稿
2. THE Evidence_Tab SHALL 使用 GtWpRenderer 懒加载渲染 Cx-2 底稿内容
3. WHEN Cx-2 底稿不存在时, THE Evidence_Tab SHALL 显示"暂无证据明细底稿"占位提示
4. THE Evidence_Tab SHALL 与主测试区域通过 Tab 切换（默认显示主测试区域）

### Requirement 12: 数据持久化

**User Story:** As a 审计助理, I want 所有控制测试数据自动保存, so that 不会因意外关闭而丢失工作。

#### Acceptance Criteria

1. THE Control_Test_Component SHALL 将所有数据存储到 checklist_responses 表，使用 item_id 前缀 `C{n}-`（n 从 wpCode 提取）区分字段
2. WHEN 用户编辑文本字段后停止输入 2 秒时, THE Control_Test_Component SHALL 自动保存变更（debounce 2000ms）
3. WHEN 用户变更 Test_Method、Sample_Result、Control_Point_Conclusion 或 Cycle_Conclusion 时, THE Control_Test_Component SHALL 立即保存
4. WHEN 保存失败时, THE Control_Test_Component SHALL 显示错误提示并保留本地编辑内容
5. THE Control_Test_Component SHALL 通过 `PUT /api/workpapers/{wp_id}/checklist-responses` 接口批量保存
6. THE Control_Test_Component SHALL 通过 `GET /api/workpapers/{wp_id}/checklist-responses` 加载已保存数据并还原状态
7. THE Control_Test_Component SHALL 使用结构化 item_id 命名规则：`C{n}-ctrl-{m}-{field}`（如 `C2-ctrl-1-methods`、`C5-ctrl-3-sample-2-result`、`C8-cycle-conclusion`）

### Requirement 13: 复核签字

**User Story:** As a 现场经理, I want 控制测试完成后签字复核并锁定, so that 确保测试结论经审核后不被随意修改。

#### Acceptance Criteria

1. THE Control_Test_Component SHALL 在 Cycle_Conclusion 区域下方提供"现场经理复核"签字区域
2. WHEN 存在控制点未完成测试（无 Control_Point_Conclusion）时, THE Control_Test_Component SHALL 禁用复核签字按钮并显示待完成事项
3. WHEN 现场经理完成签字时, THE Control_Test_Component SHALL 将全组件转为只读模式并 emit `completed`
4. WHILE 处于已复核只读模式时, THE Control_Test_Component SHALL 在顶部显示"已复核"绿色横幅
5. WHEN 外部传入 readonly prop 为 true 时, THE Control_Test_Component SHALL 强制进入只读模式
6. THE Control_Test_Component SHALL 支持 Amendment 模式：填写修改原因后解锁编辑，完成后需重新复核

### Requirement 14: 后端白名单扩展

**User Story:** As a 开发者, I want 后端支持 C{n}- 前缀的结论值保存, so that 前端发送的控制测试数据能正常持久化。

#### Acceptance Criteria

1. THE 后端 checklist_responses 保存逻辑 SHALL 在结论白名单中支持 `C{n}-` 前缀的 item_id（n=2~15）
2. THE 后端 SHALL 接受以下结论值：控制有效运行、控制存在偏差但可接受、控制无效、有效、偏差、不适用、全部有效、部分偏差、控制失效、Y、N
3. THE 后端 SHALL 接受 Test_Method 结论值：询问、观察、检查、重新执行
4. IF 前端发送无效的 C{n}- 前缀结论值, THEN THE 后端 SHALL 返回 422 校验错误并拒绝保存

---

## Correctness Properties

### Property 1: 偏差率计算不变式

*For any* 控制点的样本集合变更（增/删/修改 Sample_Result），Deviation_Rate SHALL 始终等于 `偏差数 ÷ (总样本数 - 不适用样本数)`。当分母为 0 时返回 null（无法计算）。偏差数等于 Sample_Result="偏差" 的样本计数。

**Validates: Requirements 6.1, 6.2, 6.4**

### Property 2: Control_Point_Conclusion 自动建议一致性

*For any* 偏差率值和可容忍偏差率设置，自动建议 SHALL 满足：(a) 偏差率=0% → "控制有效运行"；(b) 0% < 偏差率 ≤ 可容忍率 → "控制存在偏差但可接受"；(c) 偏差率 > 可容忍率 → "控制无效"；(d) 无法计算偏差率时不给建议。

**Validates: Requirements 7.2, 7.3, 7.4, 7.5**

### Property 3: Cycle_Conclusion 汇总一致性

*For any* 控制点结论集合，Cycle_Conclusion 自动建议 SHALL 满足：(a) 全部"控制有效运行" → "全部有效"；(b) 存在"控制存在偏差但可接受"且无"控制无效" → "部分偏差"；(c) 存在任一"控制无效" → "控制失效"；(d) 无已完成控制点时不给建议。

**Validates: Requirements 8.2, 8.3, 8.4, 8.5**

### Property 4: EventBus 事件发射正确性

*For any* Cycle_Conclusion 变更操作且新旧值不同，系统 SHALL 发布 `control:test-concluded` 事件（含 wpCode/cycleName/conclusion/deviationSummary）。新旧值相同时不发射事件。

**Validates: Requirements 10.1, 10.2, 10.3**

### Property 5: 数据持久化往返一致性

*For any* 有效的控制测试数据（控制点 + 样本 + 结果 + 结论），通过 PUT 保存后再通过 GET 加载，所有字段值 SHALL 与保存前一致（round-trip property）。

**Validates: Requirements 12.1, 12.5, 12.6**

### Property 6: item_id 命名唯一性

*For any* 组合（循环编号 n × 控制点序号 m × 样本序号 s × 字段类型），生成的 item_id SHALL 唯一。不同业务含义的数据不可产生相同 item_id。

**Validates: Requirements 12.7**

### Property 7: 复核前置条件完备性

*For any* 控制点状态组合，复核签字按钮可用当且仅当：所有控制点均有 Control_Point_Conclusion，且 Cycle_Conclusion 已选择。

**Validates: Requirements 13.2**

### Property 8: 后端白名单校验正确性

*For any* item_id 以 `C{n}-`（n=2~15）开头的保存请求，conclusion 值在白名单内时 SHALL 返回 200；不在白名单内时 SHALL 返回 422。

**Validates: Requirements 14.1, 14.2, 14.3, 14.4**
