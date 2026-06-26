# Requirements Document

## Introduction

B23 业务流程与控制了解表是审计计划阶段（B循环）的流程层面内控底稿，系统执行对被审计单位各主要业务流程及其关键控制点的了解和穿行测试（CAS 1231）。B23 是 B22A 实体层面内控了解的下游深化——从整体控制环境聚焦到具体业务流程的控制设计与执行有效性。

当前实现使用 8 个独立 `d-form-table` 底稿（B23-1 采购与付款 至 B23-8 其他流程），用户必须打开 8 个底稿才能完成全部流程了解。本 spec 定义一个统一的 `b23-process-control` HTML 专用组件，将全部 B23 子底稿聚合为流程卡片 + 穿行测试 + 状态仪表盘界面，提供结构化控制点评估、穿行测试记录、跨底稿联动和现场经理复核流程。

核心价值：
- 将 8 次打开 → 1 次打开，消除碎片体验
- 流程卡片可视化：每个业务流程一张可展开卡片，内含控制点表格 + 穿行测试区
- 穿行测试结论直接驱动 D~N 循环实质性程序决策（CAS 1231）
- 状态仪表盘：顶部汇总各流程完成度/有效性分布/待穿行数量
- 三方联动闭环：B22A（实体层面）→ B23（流程层面）→ B50（控制风险）→ D~N（程序）

## Glossary

- **Process_Control_Component**: B23 业务流程与控制了解表 Vue 组件（componentType = `b23-process-control`）
- **Business_Process**: 业务流程分类，8 个标准流程：采购与付款循环/销售与收款循环/资金管理循环/生产与存货循环/薪酬与人力循环/固定资产循环/投资循环/其他流程
- **Process_Card**: 流程卡片，每个 Business_Process 对应一张可视化卡片（可展开/收起），内含控制点表格和穿行测试区
- **Control_Point**: 控制点，每个流程下的关键控制活动（如三单匹配、审批层级、对账、银行余额调节等）
- **Walkthrough_Test**: 穿行测试，对每个控制点选取一笔交易全流程追踪，验证控制实际运行（CAS 1231 要求）
- **Understanding_Method**: 了解方法枚举（多选）：询问/观察/检查文件/穿行测试/重新执行
- **Process_Conclusion**: 流程级控制结论枚举：设计有效且已实施/设计有效但未有效实施/设计无效/不适用
- **Control_Frequency**: 控制频率枚举：每笔/每日/每周/每月/每季/每年/不定期
- **Status_Dashboard**: 状态仪表盘，顶部汇总面板，显示各流程完成度/有效性分布/待穿行数量
- **Linkage_Panel**: 联动面板，显示与 B22A/B50/D~N 的关联状态和 ref_chip 跳转链接
- **Process_Applicability**: 流程适用性，根据项目特征筛选适用的业务流程（不适用流程标记为"不适用"并折叠）
- **Walkthrough_Sample**: 穿行测试样本，穿行测试选取的具体交易/凭证编号/日期/金额
- **Entity_Level_Context**: 从 B22A 接收的实体层面控制结论摘要（只读参考区域）
- **checklist_responses**: 数据持久化表，通过 item_id 前缀 `B23-` 区分字段
- **htmlRendererRegistry**: 前端 componentType → Vue 组件的单一来源注册表
- **Manager_Review**: 现场经理复核签字
- **EventBus**: 进程内事件总线，B23 发布 `process:control-concluded` + `process:walkthrough-completed`
- **Color_Coding**: 颜色编码规则：有效=绿/部分有效（设计有效但未有效实施）=黄/无效=红/不适用=灰/待测试=蓝
- **Import_Export**: 三级导入导出：空白模板导出 → 离线填写 → 数据导入回系统（复用 ExcelJS）
- **Linkage_Flow_Diagram**: 关联流程图，展示 B22A→B23→B50→D~N 审计链路的可视化节点连线图
- **Cycle_Procedure_Linkage**: C~N 循环程序表关联，B23 各流程结论→对应 D~N 程序表的控制依赖建议

## Requirements

### Requirement 1: 流程卡片统一界面与状态仪表盘

**User Story:** As a 现场经理, I want 在一个界面中查看和管理全部业务流程的控制了解工作, so that 不再需要在 8 个底稿间切换，且一目了然掌握整体进度。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 渲染 Status_Dashboard 顶部汇总面板，显示：各流程完成状态分布（已完成/进行中/未开始/不适用）、有效性分布饼图/条形图、待穿行测试数量
2. THE Process_Control_Component SHALL 在 Status_Dashboard 下方渲染 8 张 Process_Card（采购与付款/销售与收款/资金管理/生产与存货/薪酬与人力/固定资产/投资/其他），每张卡片可独立展开/收起
3. WHEN 用户展开某张 Process_Card 时, THE Process_Control_Component SHALL 显示该流程的控制点表格和穿行测试区域
4. THE Process_Control_Component SHALL 在每张 Process_Card 的标题栏显示：流程名称、Process_Conclusion 状态标签（颜色编码）、控制点完成比例（N/M）、穿行测试完成状态图标
5. THE Process_Control_Component SHALL 支持全部展开/全部收起的快捷操作按钮
6. THE Process_Control_Component SHALL 使用中文标签，所有 UI 文字与审计准则术语一致
7. THE Status_Dashboard SHALL 实时响应各 Process_Card 内的数据变更，自动更新统计数据

### Requirement 2: 流程适用性筛选

**User Story:** As a 现场经理, I want 根据被审计单位实际情况标记不适用的流程, so that 审计助理只需关注适用流程，不浪费精力在无关流程上。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 在每张 Process_Card 标题栏提供"适用性"开关（适用/不适用）
2. WHEN 用户将某流程标记为"不适用"时, THE Process_Control_Component SHALL 将该卡片折叠并以灰色样式显示，标题栏附加"不适用"标签
3. WHEN 流程标记为"不适用"时, THE Process_Control_Component SHALL 将该流程的 Process_Conclusion 自动设为"不适用"
4. THE Process_Control_Component SHALL 在 Status_Dashboard 中将"不适用"流程排除出"待完成"计数
5. WHEN 用户将"不适用"流程恢复为"适用"时, THE Process_Control_Component SHALL 清除之前自动设置的"不适用"结论并展开卡片
6. THE Process_Control_Component SHALL 默认全部 8 个流程为"适用"状态

### Requirement 3: 控制点评估表格

**User Story:** As a 审计助理, I want 每个流程下有结构化的控制点表格供逐项评估, so that 流程控制了解有据可查且不遗漏关键控制。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 为每个适用流程渲染控制点表格，每行包含：序号、控制目标、控制活动描述、Control_Frequency（下拉）、执行人/部门（文本）、Understanding_Method（多选）、穿行测试结论（下拉）、备注/索引
2. THE Process_Control_Component SHALL 提供 Understanding_Method 多选选项：询问、观察、检查文件、穿行测试、重新执行
3. THE Process_Control_Component SHALL 提供 Control_Frequency 下拉选项：每笔、每日、每周、每月、每季、每年、不定期
4. THE Process_Control_Component SHALL 提供穿行测试结论下拉选项：控制有效运行、控制未有效运行、未执行穿行、不适用
5. WHEN 用户新增控制点行时, THE Process_Control_Component SHALL 自动分配行序号并提供空白可编辑行
6. THE Process_Control_Component SHALL 支持删除用户新增的控制点行（预置控制点需确认后方可删除）
7. WHEN 某控制点穿行测试结论为"控制未有效运行"时, THE Process_Control_Component SHALL 在该行显示红色警告标识

### Requirement 4: 穿行测试记录区

**User Story:** As a 审计助理, I want 为每个控制点独立记录穿行测试的样本选取和测试路径, so that 穿行测试过程有据可查且满足 CAS 1231 要求。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 在每张 Process_Card 的控制点表格下方提供可展开的"穿行测试详细记录"区域
2. THE 穿行测试区域 SHALL 为每个已执行穿行测试的控制点提供记录字段：样本选取（凭证编号/交易日期/金额）、测试路径描述（文本区）、发现与结论（文本区）、证据引用（ref_chip）
3. WHEN 控制点的 Understanding_Method 包含"穿行测试"时, THE Process_Control_Component SHALL 在穿行测试区域自动创建对应的测试记录条目
4. THE Process_Control_Component SHALL 支持为同一控制点记录多笔穿行测试样本（至少支持 3 笔）
5. THE 穿行测试区域 SHALL 在折叠状态下显示摘要信息：已测试控制点数/总控制点数、穿行完成率
6. WHEN 所有适用控制点的穿行测试均已完成时, THE Process_Control_Component SHALL 在该流程卡片标题栏显示"穿行已完成"绿色徽标

### Requirement 5: 流程级结论与自动建议

**User Story:** As a 现场经理, I want 系统根据各控制点穿行结论自动建议流程级结论, so that 减少主观判断偏差和手工汇总错误。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 在每张 Process_Card 底部提供 Process_Conclusion 选择区域（设计有效且已实施/设计有效但未有效实施/设计无效/不适用）
2. THE Process_Control_Component SHALL 根据该流程下控制点的穿行测试结论分布自动建议 Process_Conclusion
3. WHEN 某流程全部控制点穿行结论为"控制有效运行"或"不适用"时, THE Process_Control_Component SHALL 建议 Process_Conclusion 为"设计有效且已实施"
4. WHEN 某流程存在"控制未有效运行"的控制点但占比不超过 30% 时, THE Process_Control_Component SHALL 建议 Process_Conclusion 为"设计有效但未有效实施"
5. WHEN 某流程"控制未有效运行"的控制点占比超过 30% 时, THE Process_Control_Component SHALL 建议 Process_Conclusion 为"设计无效"
6. THE Process_Control_Component SHALL 允许现场经理手动覆盖自动建议的 Process_Conclusion（覆盖时需填写说明理由）
7. WHEN 手动覆盖 Process_Conclusion 时, THE Process_Control_Component SHALL 在该卡片底部显示"已手动调整"标识和覆盖理由

### Requirement 6: B22A 实体层面控制上下文参考

**User Story:** As a 现场经理, I want 在流程了解界面中看到 B22A 实体层面控制结论摘要, so that 流程层面了解能结合整体控制环境进行判断。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 在 Status_Dashboard 区域提供 Entity_Level_Context 只读参考面板
2. THE Entity_Level_Context 面板 SHALL 显示 B22A 五要素各自的 Element_Score（有效/部分有效/无效）和整体结论，使用颜色编码
3. THE Process_Control_Component SHALL 通过监听 EventBus 事件 `control:conclusion-changed` 实时更新 Entity_Level_Context 面板内容
4. WHEN B22A 控制环境（要素1）结论为"无效"时, THE Entity_Level_Context 面板 SHALL 显示醒目警告："实体层面控制环境薄弱，流程控制有效性可能受限"
5. THE Entity_Level_Context 面板 SHALL 提供 ref_chip 跳转链接到 B22A 底稿
6. WHILE B22A 底稿尚未完成时, THE Entity_Level_Context 面板 SHALL 显示"B22A 未完成，实体层面结论待定"灰色提示

### Requirement 7: 跨底稿联动（B50 + D~N）

**User Story:** As a 现场经理, I want B23 流程控制结论自动输入 B50 控制风险评估并通知 D~N 程序表, so that 穿行测试结论能自动驱动后续审计程序决策。

#### Acceptance Criteria

1. WHEN 任一流程的 Process_Conclusion 变更时, THE Process_Control_Component SHALL 通过 EventBus 发布 `process:control-concluded` 事件（含流程编号、流程名称、旧结论、新结论）
2. WHEN 任一流程的所有穿行测试完成时, THE Process_Control_Component SHALL 通过 EventBus 发布 `process:walkthrough-completed` 事件（含流程编号、控制点数量、有效率）
3. THE Process_Control_Component SHALL 在 Linkage_Panel 中显示各流程结论对应的 B50 控制风险影响提示（如"采购流程设计无效→B50 采购循环控制风险=高"）
4. THE Linkage_Panel SHALL 显示各流程对应的 D~N 循环程序表映射关系（如"采购与付款→DA 程序表"）并提供 ref_chip 跳转
5. THE Process_Control_Component SHALL 在 Linkage_Panel 中显示 B22A 关联状态（已完成/未完成/Entity_Level_Context 摘要）
6. WHEN 某流程 Process_Conclusion 为"设计无效"时, THE Linkage_Panel SHALL 高亮该流程与 B50/D~N 的关联行并附加"需扩大实质性程序"提示

### Requirement 8: 数据持久化

**User Story:** As a 审计助理, I want 所有流程控制了解和穿行测试数据自动保存, so that 不会因意外关闭而丢失工作。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 将所有数据存储到 checklist_responses 表，使用 item_id 前缀 `B23-` 区分字段
2. WHEN 用户编辑任意文本字段后停止输入 2 秒时, THE Process_Control_Component SHALL 自动保存变更到后端（debounce 2000ms）
3. WHEN 用户变更 Process_Conclusion、穿行测试结论、或适用性开关时, THE Process_Control_Component SHALL 立即保存（不等待 debounce）
4. WHEN 保存失败时, THE Process_Control_Component SHALL 显示错误提示并保留本地编辑内容（不回滚）
5. THE Process_Control_Component SHALL 通过 `PUT /api/workpapers/{wp_id}/checklist-responses` 接口批量保存
6. THE Process_Control_Component SHALL 通过 `GET /api/workpapers/{wp_id}/checklist-responses` 加载已保存数据并还原各流程卡片状态
7. THE Process_Control_Component SHALL 使用结构化 item_id 命名规则：`B23-P{n}-ctrl-{m}-{field}`（如 `B23-P1-ctrl-3-conclusion`、`B23-P2-wt-1-sample`、`B23-P5-applicability`、`B23-P3-process-conclusion`）

### Requirement 9: 现场经理复核与只读流程

**User Story:** As a 现场经理, I want 全部流程控制了解完成后签字复核并锁定, so that 后续风险评估和实质性程序基于经复核的流程控制了解。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 在 Status_Dashboard 下方提供"现场经理复核"签字区域
2. WHEN 存在未完成评估的适用流程（任一适用流程的 Process_Conclusion 为空或存在控制点穿行结论为空）时, THE Process_Control_Component SHALL 禁用复核签字按钮并显示待完成事项清单
3. WHEN 现场经理完成签字时, THE Process_Control_Component SHALL 将全部流程卡片转为只读模式
4. WHILE Process_Control_Component 处于已复核只读模式时, THE Process_Control_Component SHALL 在顶部显示"已复核"状态横幅（绿色）和复核人/日期信息
5. WHEN 外部传入 `readonly` prop 为 true 时, THE Process_Control_Component SHALL 强制进入只读模式
6. WHEN 已复核后需要修改流程控制了解时, THE Process_Control_Component SHALL 支持 Amendment 模式：填写修改原因后解锁编辑，完成后需重新走复核流程

### Requirement 10: 组件注册与路由

**User Story:** As a 开发者, I want 新组件正确注册到 htmlRendererRegistry 并通过 wp_code_overrides 路由, so that 打开 B23 底稿时自动渲染新组件。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 在 htmlRendererRegistry 中注册 componentType 为 `b23-process-control`，contextProps 为 `standard`
2. THE Process_Control_Component SHALL 在 wp_code_overrides.json 中新增 `B23` 映射为 `b23-process-control`
3. THE Process_Control_Component SHALL 在 wp_code_overrides.json 中将 `B23-1`、`B23-2`、`B23-3`、`B23-4`、`B23-5`、`B23-6`、`B23-7`、`B23-8` 映射为 `skip`（由 B23 统一渲染）
4. THE Process_Control_Component SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly
5. THE Process_Control_Component SHALL emit `save` 事件（保存成功后）和 `completed` 事件（复核完成时）
6. WHEN 后端 render-config 返回 componentType 为 `b23-process-control` 时, THE 前端路由 SHALL 正确加载 Process_Control_Component

### Requirement 11: 后端结论白名单扩展

**User Story:** As a 开发者, I want 后端 checklist_responses 保存逻辑支持 B23- 前缀的结论值, so that 前端发送的流程控制结论能正常持久化。

#### Acceptance Criteria

1. THE 后端 checklist_responses 保存逻辑 SHALL 在结论白名单中支持 B23- 前缀的 item_id
2. THE 后端 SHALL 接受 B23- 前缀 item_id 的以下结论值：设计有效且已实施、设计有效但未有效实施、设计无效、不适用、控制有效运行、控制未有效运行、未执行穿行
3. THE 后端 SHALL 对 B23- 前缀 item_id 的保存请求执行与现有 B22A-/B22B-/B50- 前缀相同的权限校验
4. IF 前端发送无效的 B23- 前缀结论值, THEN THE 后端 SHALL 返回 422 校验错误并拒绝保存

### Requirement 12: 颜色编码与视觉设计

**User Story:** As a 业务合伙人, I want 通过颜色直观区分各流程控制有效性状态, so that 快速判断哪些流程存在控制缺陷需要关注。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 对 Process_Conclusion 使用颜色编码：设计有效且已实施=绿色(#52c41a)、设计有效但未有效实施=黄色(#faad14)、设计无效=红色(#ff4d4f)、不适用=灰色(#bfbfbf)
2. THE Process_Control_Component SHALL 对未开始穿行测试的控制点使用蓝色(#1890ff)标识"待测试"
3. THE Status_Dashboard SHALL 使用与 Process_Conclusion 相同的颜色编码渲染统计分布图
4. THE Process_Card 标题栏 SHALL 使用左侧色带（4px 宽）标识该流程的 Process_Conclusion 对应颜色
5. THE Process_Control_Component SHALL 在打印输出中保持颜色编码区分（@media print 保留背景色）

### Requirement 13: 响应式布局与打印

**User Story:** As a 审计助理, I want 在不同屏幕和打印场景下正常使用流程控制了解表, so that 现场笔记本和归档打印都能满足。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 在 ≥1024px 宽度下完整显示 Status_Dashboard 和 Process_Card 内容
2. WHEN 视窗宽度在 768px~1024px 时, THE Process_Control_Component SHALL 通过水平滚动支持控制点表格查看，不截断内容
3. THE Process_Control_Component SHALL 提供打印样式表（@media print），每个流程卡片的控制点表格和结论区域适配 A4 纵版
4. WHEN 用户触发打印时, THE Process_Control_Component SHALL 隐藏交互控件（展开/收起按钮、适用性开关），仅保留数据和结论
5. THE Process_Control_Component SHALL 在打印输出中自动展开所有适用流程的卡片内容

---

### Requirement 14: 导入导出功能（三级）

**User Story:** As a 审计助理, I want 导出空白模板/已填数据到 Excel 并支持从 Excel 导入, so that 支持离线填写和与其他系统的数据交换。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 在工具栏提供"导出模板"按钮，生成包含 8 个流程 Sheet 的空白 Excel 模板（含列标题：控制目标/控制活动/频率/执行人/了解方法/穿行结论/备注）
2. THE Process_Control_Component SHALL 在工具栏提供"导出数据"按钮，将当前全部已填写数据导出为 Excel（结构与模板一致，含已填内容 + 结论 + 穿行记录）
3. THE Process_Control_Component SHALL 在工具栏提供"导入"按钮，支持从符合模板格式的 Excel 文件导入数据到对应流程卡片
4. WHEN 导入数据时存在与现有数据的冲突（同一控制点已有值）, THE Process_Control_Component SHALL 弹出确认弹窗让用户选择"覆盖"或"跳过"
5. WHEN 导入的 Excel 格式不符合模板结构时, THE Process_Control_Component SHALL 显示错误提示并拒绝导入（不写入任何数据）
6. THE 导出模板和导出数据 SHALL 使用项目已有的 ExcelJS 库（不引入新依赖）

### Requirement 15: 关联流程图可视化

**User Story:** As a 业务合伙人, I want 在页面中看到 B23 与其他底稿（B22A/B50/D~N）关联关系的可视化流程图, so that 快速理解审计工作链路和各底稿间的数据流转关系。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 在 Status_Dashboard 和 Linkage_Panel 之间渲染"审计链路流程图"区域，展示 B22A→B23→B50→D~N 四方关系
2. THE 流程图 SHALL 使用 SVG/Canvas 或 CSS 实现的可视化节点+连线图（不引入新可视化库，用 HTML/CSS 实现轻量版）
3. THE 流程图中每个节点 SHALL 显示底稿编号 + 名称 + 当前状态（已完成/进行中/未开始，对应颜色标识）
4. THE 流程图中 B23 节点到各 D~N 循环的连线 SHALL 按实际流程映射关系（P1→DA/P2→EA/...）动态渲染，仅显示适用流程的连线
5. THE 流程图 SHALL 在点击节点时通过 ref_chip 跳转到对应底稿
6. THE 流程图 SHALL 可折叠/展开（默认展开），折叠时仅显示一行摘要文字

### Requirement 16: C~N 循环底稿实质性关联

**User Story:** As a 现场经理, I want B23 的控制结论能直接关联到对应循环的实质性程序表, so that 穿行测试结果能驱动后续审计程序决策。

#### Acceptance Criteria

1. THE Process_Control_Component SHALL 为每个适用流程在 Process_Card 底部显示"关联程序表"区域，列出该流程对应的 D~N 循环程序表（wp_code + 名称 + 完成状态）
2. THE 关联程序表区域 SHALL 根据流程编号自动映射对应循环：P1→D循环(DA)/P2→E循环(EA)/P3→F循环(FA)/P4→G循环(GA)/P5→H循环(HA)/P6→I循环(IA)/P7→J循环(JA)/P8→K循环(KA)
3. WHEN 某流程 Process_Conclusion 为"设计无效"或"设计有效但未有效实施"时, THE 关联程序表区域 SHALL 显示建议文案："控制不可依赖——建议扩大实质性程序范围和样本量"
4. THE Process_Control_Component SHALL 在"关联程序表"区域提供 ref_chip 跳转到对应 D~N 程序表底稿
5. WHEN 流程穿行测试完成且结论为"设计有效且已实施"时, THE 关联程序表区域 SHALL 显示建议文案："控制可依赖——可适当缩小实质性程序范围"

---

## Correctness Properties

### Property 1: 状态仪表盘同步不变式

*For any* Process_Card 内的控制点或 Process_Conclusion 变更，Status_Dashboard 中的统计数据（完成数/有效数/待穿行数）SHALL 始终等于各流程卡片中数据的实际分布计数。添加/修改/删除控制点或切换适用性后，Status_Dashboard 应同步更新。

**Validates: Requirements 1.1, 1.7, 2.4**

### Property 2: Process_Conclusion 自动建议一致性

*For any* 流程下控制点穿行测试结论分布，自动建议的 Process_Conclusion SHALL 满足：(a) 全部为"控制有效运行"或"不适用" → "设计有效且已实施"；(b) 存在"控制未有效运行"且占比≤30% → "设计有效但未有效实施"；(c) 占比>30% → "设计无效"。手动覆盖不影响计算逻辑，仅覆盖显示值。

**Validates: Requirements 5.2, 5.3, 5.4, 5.5**

### Property 3: 流程适用性约束

*For any* 流程适用性切换操作，标记为"不适用"的流程 SHALL 自动将 Process_Conclusion 设为"不适用"；恢复为"适用"时 SHALL 清除该自动结论。不适用流程不计入 Status_Dashboard 的"待完成"统计。适用性切换不删除已填写的控制点数据。

**Validates: Requirements 2.2, 2.3, 2.4, 2.5**

### Property 4: 穿行测试与了解方法联动

*For any* 控制点的 Understanding_Method 选择变更，WHEN Understanding_Method 包含"穿行测试"时，穿行测试区域 SHALL 存在对应的测试记录条目。WHEN Understanding_Method 不包含"穿行测试"时，已创建的测试记录 SHALL 保留但不再强制填写。

**Validates: Requirements 4.3**

### Property 5: 复核前置条件完备性

*For any* 流程卡片状态组合，现场经理签字按钮可用当且仅当：所有适用流程的 Process_Conclusion 均已选择，且所有适用流程中 Understanding_Method 包含"穿行测试"的控制点均有穿行测试结论。条件不满足时按钮必须禁用。

**Validates: Requirements 9.2**

### Property 6: 复核后只读不变式

*For any* 已通过现场经理复核的组件状态，所有流程卡片的所有字段 SHALL 处于只读模式。除非通过 Amendment 模式解锁，否则任何编辑操作应被阻止。Amendment 解锁后需重新走复核流程。

**Validates: Requirements 9.3, 9.4, 9.6**

### Property 7: 数据持久化往返一致性

*For any* 有效的流程控制了解数据（包含 8 个流程的全部控制点 + 穿行测试 + 结论字段），通过 PUT 保存后再通过 GET 加载，所有字段值（item_id、conclusion、remark）SHALL 与保存前一致（round-trip property）。

**Validates: Requirements 8.1, 8.5, 8.6**

### Property 8: item_id 命名唯一性

*For any* 组合（流程编号 P{n} × 控制点序号 {m} × 字段类型），生成的 item_id SHALL 唯一。不同业务含义的数据不可产生相同 item_id，同一业务含义的数据重复保存应覆盖而非新增。

**Validates: Requirements 8.7**

### Property 9: EventBus 事件发射正确性

*For any* Process_Conclusion 变更操作且新旧值不同，系统 SHALL 发布 `process:control-concluded` 事件（含流程编号、流程名称、旧结论、新结论）。未变更时不发射事件。WHEN 某流程全部穿行测试完成时 SHALL 发布 `process:walkthrough-completed` 事件。

**Validates: Requirements 7.1, 7.2**

### Property 10: 颜色编码双射

*For any* Process_Conclusion 值，对应的颜色编码 SHALL 满足：设计有效且已实施→绿色、设计有效但未有效实施→黄色、设计无效→红色、不适用→灰色。该映射为单射，不存在同色不同结论。待测试状态→蓝色不与任何结论色冲突。

**Validates: Requirements 12.1, 12.2, 12.4**

### Property 11: Entity_Level_Context 只读不变式

*For any* 用户交互操作，Entity_Level_Context 面板中显示的 B22A 数据 SHALL 始终为只读状态，用户不可编辑。该面板数据仅通过 EventBus 事件或初始加载更新，不受本组件内部编辑操作影响。

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 12: 适用性与复核状态交互约束

*For any* 已复核状态下的适用性开关操作，系统 SHALL 阻止修改。适用性变更仅在非复核状态（或 Amendment 解锁后）允许执行。

**Validates: Requirements 2.1, 9.3, 9.6**

### Property 13: 导入导出数据一致性

*For any* 已填写的流程控制数据，通过"导出数据"生成的 Excel 再通过"导入"操作加载后，所有控制点字段值（控制目标/描述/频率/执行人/了解方法/穿行结论/备注）SHALL 与导出前一致。导入操作不影响未涉及流程的已有数据。

**Validates: Requirements 14.1, 14.2, 14.3**

### Property 14: 关联流程图节点状态同步

*For any* B23 流程结论变更或 B22A EventBus 事件，关联流程图中对应节点的状态（颜色/标签）SHALL 同步更新。流程图仅展示适用流程的连线，不适用流程不出现连线。

**Validates: Requirements 15.3, 15.4**
