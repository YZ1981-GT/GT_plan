# Requirements Document

## Introduction

本规格是对现有 **B23 业务层面控制底稿**（`b23-process-control` componentType，历史 spec 已归档于 `_archive/13-2026-06-29-batch/b23-process-control/`）的系统性重做（rework）。

B23 位于风险导向审计的内控评价链上游，是 B 循环（审计计划阶段）的**业务层面 / 流程层面内部控制底稿**，处在 B22A（企业层面控制）下游。完整风险链为：

```
B22A 企业层面控制 → B23 业务层面控制（按 14 循环）→ B50 控制风险评估 → C 类控制测试 → D~N 实质性程序范围
```

致同 2025 修订版源模板（`基础数据/致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md/{cycle}/B23-N...业务层面控制底稿模板库.md`）显示 B23 覆盖 **14 个业务循环**，每个循环本身是一个 **9 张子底稿的小包**，核心审计逻辑为：

```
WCGW（容易出错领域）→ 关键控制点 → 穿行测试（验证控制设计是否得到执行）
   + 控制测试（验证控制运行有效性）→ 缺陷分级（按 A14-4）→ 影响实质性程序范围
```

### 本次重做要解决的核心问题（均已对照代码与源模板核实）

1. **假绿模板（P0）**：历史 spec 将任务 3.2~3.15 标记为 `[x]` 且 PBT/单元测试全绿，但这些测试仅覆盖 `useB23ProcessControl.ts` composable 的纯逻辑，渲染 UI 从未构建。`GtB23ProcessControl.vue` 的 template 是空壳（仅加载遮罩 + 附件 Tab，注释明写"template 由后续 spec 任务完善"）。composable 已写好的仪表盘 / 流程卡片 / 控制矩阵 / 穿行 / 联动面板从未渲染，审计师打开 B23 只能看到附件 Tab。
2. **附件 Tab 两个真实 Bug（P0）**：(a) `B23_ATTACHMENT_CODES` 标签全部错位（B23-9 薪酬标为"穿行测试-采购付款"、B23-10 管理标为"穿行测试-销售收款"、B23-11 税金标为"穿行测试-资金管理"等，无一匹配真实内容）；(b) 仅列出 B23-9~B23-15/XX-5，B23-1~B23-8（销售/货币资金/存货/投资/固资/在建/无形/研发）无任何入口，且在 `wp_code_overrides.json` 中全部映射为 `skip`。
3. **模型错位（P1）**：composable 使用通用的 **8 流程模型**（采购付款/销售收款/资金/生产存货/薪酬/固资/投资/其他），与源模板的 **14 循环模型**不匹配；薪酬/研发/税金/债务/租赁/关联方/无形无专属槽位。`ControlPoint` 仅 7 个字段（目标/描述/频率/执行人/方法/结论/备注），缺失 **认定、WCGW、控制属性、预防性/检查性、控制类型一级/二级、是否关键控制、是否执行控制测试**（这些字段恰是驱动控制可依赖性、是否执行 C 类控制测试、以及 D~N 范围调整的关键）。穿行测试（验设计）与控制测试（验运行）被合并为一个"穿行结论"。

### 目标

以 14 循环源模型为基准重建真实的 B23 能力，让 composable 逻辑真正被渲染，控制矩阵承载完整的审计关键列，并打通 B23 → B50 / C 类 / D~N 的联动。

## Glossary

- **B23_Component（B23 业务层面控制组件）**：componentType 为 `b23-process-control` 的前端专属渲染组件（`GtB23ProcessControl.vue`）及其 composable。
- **Business_Cycle（业务循环）**：B23 覆盖的 14 个业务流程之一，每个循环对应一组子底稿。取值集合见 Requirement 2。
- **Cycle_Package（循环子底稿包）**：单个业务循环对应的 9 张子底稿集合（程序表 / 整体控制汇总 / 流程图及描述 / 控制矩阵 / 穿行测试 / 控制测试 / 控制缺陷汇总 / 汇总 / 评价）。
- **WCGW（容易出错领域，What Can Go Wrong）**：某子流程中可能导致错报的风险点，在流程图描述中标注（如"收入1/WCGW1"）。
- **Control_Point（控制点）**：针对 WCGW 设计的内部控制，携带完整审计属性字段。
- **Key_Control（关键控制点）**：被标记为关键的控制点，是穿行测试与控制测试的对象。
- **Control_Matrix（控制矩阵）**：B23-x-3，登记每个控制点的完整属性（约 21 列），是 B23 的核心结构表。
- **Walkthrough_Test（穿行测试）**：B23-x-4，对每个控制点选取一笔交易全流程追踪，验证控制**设计是否得到执行**。
- **Control_Test（控制测试）**：B23-x-5，测试控制**运行有效性**，走 C 类底稿。
- **Deficiency（控制缺陷）**：B23-x-6，识别的控制缺陷，按 A14-4 分级为"缺乏控制 / 设计不合理 / 未执行"。
- **Deficiency_Severity（缺陷严重程度）**：按 A14-4 评价的缺陷等级。
- **Rendering_Model（渲染模型）**：B23 的单一连贯渲染方式，收敛为唯一的**聚合组件模式**（子底稿严格 skip），用于消除"composable 已完成 / template 为空 / 子底稿全 skip"三态矛盾。
- **Applicability（适用性）**：某循环子底稿是否适用当前项目的判断，参照 SCOT+/仅重大/其他 适用性自动判断逻辑。
- **B22A**：企业层面控制底稿（B23 上游）。
- **B50**：控制风险评估底稿（B23 下游），特别风险控制见 B50-4。
- **A14-4**：控制缺陷评价底稿，提供缺陷严重程度评价规则。
- **Cross_Ref_Chip（交叉引用芯片）**：GtIndexChip 形式的跨底稿跳转组件，指向 B22A-4/B18/B14/B50-4/A14-4/C 类等。
- **Attachment_Entry（附件入口）**：附件 Tab 中一个循环子底稿的附件上传/管理入口，由 `B23_ATTACHMENT_CODES` 定义。
- **Persistence_Store（持久化存储）**：`checklist_responses` 表，item_id 以 `B23-` 为前缀。
- **Review_State（复核状态）**：底稿的复核 / 只读 / 修订（amendment）机制状态。

## Requirements

### Requirement 1: 确定单一连贯的渲染模型（P0 决策）

**User Story:** As a 审计助理, I want B23 有一个单一连贯的渲染模型, so that 我不再面对"composable 已完成 / template 为空 / 子底稿全部 skip"三态互相矛盾的空白界面。

#### Acceptance Criteria

1. THE B23_Component SHALL 采用聚合组件模式作为唯一的 Rendering_Model 渲染 B23 全部内容，在单一组件内按 Business_Cycle 组织，且不提供 14 循环分别渲染模式作为可选项。
2. WHEN 审计助理打开 wp_code 为 B23 的底稿, THE B23_Component SHALL 渲染主体内容区（包含仪表盘、循环列表与循环详情），而不仅是附件 Tab。
3. THE B23_Component SHALL 使子底稿 B23-1~B23-15 及 B23-XX-5 一律严格保持 `skip`，不允许任何子底稿独立渲染，也不允许部分子底稿保持 active，以保持渲染模型一致并避免被 onlyoffice-sheet 兜底重复渲染。
4. THE wp_code_overrides SHALL 将 B23 主底稿映射到 `b23-process-control` componentType，并将子底稿 B23-1~B23-15 及 B23-XX-5 全部映射为 `skip`。
5. THE Rendering_Model SHALL 使 `useB23ProcessControl.ts` composable 中已实现的仪表盘、流程/循环卡片、控制矩阵、穿行、联动逻辑全部被至少一个已渲染的 UI 元素消费。

### Requirement 2: 对齐 14 业务循环源模型

**User Story:** As a 现场经理, I want B23 按致同源模板的 14 个业务循环组织, so that 薪酬、研发、税金、债务、租赁、关联方、无形等循环都有专属位置，与源模板底稿编码一一对应。

#### Acceptance Criteria

1. THE B23_Component SHALL 支持以下 14 个 Business_Cycle：销售循环(B23-1/D)、货币资金(B23-2/E)、存货(B23-3/F)、投资(B23-4/G)、固定资产(B23-5/H)、在建工程(B23-6/H)、无形资产(B23-7/I)、研发(B23-8/I)、职工薪酬(B23-9/J)、管理循环(B23-10/K)、税金(B23-11/N)、债务(B23-12/L)、租赁(B23-13/H)、关联方及交易(B23-14/Q)。
2. THE B23_Component SHALL 额外支持 B23-15 信息处理控制（IT，关联 C26/a27-1）与 B23-XX-5 职责分离通用模板。
3. THE B23_Component SHALL 使 Business_Cycle 集合可配置驱动，且每个循环的编码、名称、对应科目循环、子底稿编码来自单一配置来源。
4. WHERE Business_Cycle 配置来源被修改, THE B23_Component SHALL 使新增或调整的循环无需修改渲染组件代码即可显示。
5. THE B23_Component SHALL 为每个 Business_Cycle 呈现其 Cycle_Package 的 9 类子底稿视图（程序表、整体控制汇总、流程图及描述、控制矩阵、穿行测试、控制测试、控制缺陷汇总、控制测试汇总、评价）。

### Requirement 3: 渲染主组件 UI（修复假绿任务 3.2~3.15）

**User Story:** As a 审计助理, I want B23 主组件真实渲染仪表盘、循环卡片、控制矩阵、穿行、结论与联动面板, so that 我能在界面上完成业务层面控制的了解、评价与记录，而不是只看到附件 Tab。

#### Acceptance Criteria

1. THE B23_Component SHALL 渲染一个仪表盘区，展示各 Business_Cycle 的适用性、控制点数量、关键控制点数量、穿行测试完成度、控制测试完成度与缺陷数量的汇总。
2. THE B23_Component SHALL 渲染 Business_Cycle 列表或卡片，每个卡片显示循环名称、编码芯片、适用性状态标签与完成进度。
3. WHILE 审计助理尚未显式选择任何 Business_Cycle, THE B23_Component SHALL 使循环详情面板（控制矩阵、穿行测试、控制测试、缺陷汇总、联动面板）保持隐藏（默认不可见）。
4. WHEN 审计助理显式选择某个 Business_Cycle, THE B23_Component SHALL 渲染该循环的控制矩阵、穿行测试、控制测试、缺陷汇总与联动面板。
5. THE B23_Component SHALL 使控制矩阵、穿行测试、控制测试、缺陷汇总中的判断/枚举字段以下拉、单选或多选点选方式录入，长文本字段使用可自增高度的文本域并提供 AI 辅助按钮。
6. WHILE 底稿处于加载状态, THE B23_Component SHALL 显示加载指示，并在数据就绪后 10 秒内呈现主体内容。
7. IF 数据加载实际发生超时事件, THEN THE B23_Component SHALL 呈现降级提示而非空白；仅经过 10 秒经过时间但未发生超时事件时不呈现降级提示。
8. THE B23_Component SHALL 使主组件顶部提供编制进度指示（已完成子视图数 / 总子视图数）。

### Requirement 4: 控制矩阵完整字段

**User Story:** As a 现场经理, I want 控制矩阵登记完整的审计关键属性, so that 我能据此判断控制可依赖性、决定是否执行 C 类控制测试、并据以调整 D~N 实质性程序范围。

#### Acceptance Criteria

1. THE Control_Matrix SHALL 为每个 Control_Point 记录以下字段：子流程、控制编号、控制名称、详细控制描述、受影响的交易/账户/余额/披露、认定、WCGW、WCGW 详细记录、控制属性、控制频率、IT 应用名称、预防性或检查性、控制设计是否有效、控制类型一级、控制类型二级、执行人、执行人名称或服务机构、是否有文件记录、是否为关键控制点、是否执行控制测试。
2. THE Control_Matrix SHALL 使"认定""预防性或检查性""控制频率""控制类型一级""控制类型二级""是否有文件记录""是否为关键控制点""是否执行控制测试"字段以枚举点选方式录入。
3. WHEN 某 Control_Point 的"是否为关键控制点"被设为是, THE B23_Component SHALL 允许该控制点进入穿行测试与控制测试对象集合，但不强制将全部关键控制点自动纳入测试对象（由审计师选择）。
4. IF 某 Control_Point 的"控制设计是否有效"被设为否, THEN THE B23_Component SHALL 提示识别对应的控制缺陷。
5. THE Control_Matrix SHALL 使每个 Control_Point 的 WCGW 引用可追溯到流程图及描述中标注的对应 WCGW。

### Requirement 5: 穿行测试与控制测试分层

**User Story:** As a 审计助理, I want 穿行测试（验设计）与控制测试（验运行）作为两个独立层次记录, so that 我能分别评价控制设计是否得到执行与控制运行是否有效，符合致同审计逻辑。

#### Acceptance Criteria

1. THE Walkthrough_Test SHALL 独立于 Control_Test 记录，字段包含测试方法、访谈对象、实施程序、检查证据、结果、是否按设计执行、识别缺陷。
2. THE Control_Test SHALL 独立于 Walkthrough_Test 记录，字段包含拟测试控制、风险判断、测试性质、测试时间、测试范围、运行有效性结论、偏差、对实质性程序的影响。
3. WHEN 某 Key_Control 的 Walkthrough_Test 结果为"按设计执行", THE B23_Component SHALL 允许该控制进入 Control_Test。
4. IF 某 Key_Control 的 Walkthrough_Test 结果为"未按设计执行", THEN THE B23_Component SHALL 提示识别控制缺陷并提示对实质性程序范围的影响。
5. THE B23_Component SHALL 使 Walkthrough_Test 与 Control_Test 的结论分别持久化，不合并为单一"穿行结论"字段。

### Requirement 6: 缺陷分级（按 A14-4）

**User Story:** As a 业务合伙人, I want 控制缺陷按 A14-4 评价严重程度, so that 我能据缺陷等级判断对审计策略与实质性程序的影响。

#### Acceptance Criteria

1. THE Deficiency SHALL 按子流程识别，并记录缺陷描述、缺陷类型与 Deficiency_Severity。
2. THE Deficiency SHALL 使缺陷类型以枚举点选方式录入，取值为"缺乏控制""设计不合理""未执行"。
3. THE Deficiency SHALL 使 Deficiency_Severity 参照 A14-4 评价规则录入，并提供指向 A14-4 的 Cross_Ref_Chip。
4. WHEN 控制矩阵中"控制设计是否有效"为否或穿行测试结果为"未按设计执行", THE B23_Component SHALL 在缺陷汇总中提示可能存在对应缺陷，即使当前缺陷记录数为零时仍显示该缺陷提示。
5. THE B23_Component SHALL 汇总各 Business_Cycle 的缺陷数量并在仪表盘中呈现。

### Requirement 7: 跨底稿联动（B23 → B50 / C 类 / D~N）

**User Story:** As a 现场经理, I want B23 的关键控制、控制测试结论与缺陷向 B50、C 类控制测试与 D~N 实质性程序范围联动, so that 内控评价结果真正驱动下游审计范围决策，而不是孤立底稿。

#### Acceptance Criteria

1. WHEN 某 Control_Point 同时满足"是否为关键控制点"为是且穿行测试结果为"按设计执行", THE B23_Component SHALL 生成"建议执行控制测试"的联动提示并可关联到对应 C 类底稿。
2. WHEN Control_Test 的运行有效性结论发生变化, THE B23_Component SHALL 发布控制风险变化事件供 B50 消费（结论变化单独即足以触发，不要求缺陷同时发生变化）。
3. THE B23_Component SHALL 依据 `wp_dependency_service.CYCLE_DEPENDENCIES` 的循环→b_controls/c_tests 映射，为每个 Business_Cycle 呈现其关联的 C 类控制测试与 D~N 实质性程序底稿。
4. WHEN Control_Test 结论表明控制不可依赖, THE B23_Component SHALL 仅生成对应 D~N 实质性程序范围加大的建议提示供审计师复核决定是否采纳，而不自动扩大实质性程序范围。
5. THE B23_Component SHALL 保留既有 EventBus 事件 `process:control-concluded` 与 `process:walkthrough-completed` 的发布。
6. WHEN Control_Test 的识别缺陷发生变化, THE B23_Component SHALL 发布控制风险变化事件供 B50 消费。

### Requirement 8: 交叉引用芯片

**User Story:** As a 审计助理, I want B23 中呈现指向 B22A-4、B18、B14、B50-4、A14-4 与 C 类底稿的交叉引用芯片, so that 我能在了解与评价控制时一键跳转到相关底稿。

#### Acceptance Criteria

1. THE B23_Component SHALL 以 GtIndexChip 形式呈现指向 B22A-4（IT 控制）、B18（内部审计）、B14（外包/SOC 报告）、B50-4（特别风险控制）、A14-4（缺陷评价）的 Cross_Ref_Chip。
2. WHEN 审计助理点击某 Cross_Ref_Chip, THE B23_Component SHALL 触发跳转到对应目标底稿。
3. IF 某 Cross_Ref_Chip 被点击时其跳转目标暂不可用, THEN THE B23_Component SHALL 允许点击并显示错误提示，而不阻止点击操作。
4. THE B23_Component SHALL 始终呈现指向 C26/a27-1 的 Cross_Ref_Chip，无论该 Business_Cycle 是否涉及信息处理控制。
5. THE Cross_Ref_Chip SHALL 使用 canonical 索引语法（如 `wp:B50-4`）作为跳转目标值。

### Requirement 9: 适用性过滤

**User Story:** As a 现场经理, I want B23 按项目实际情况判断各循环子底稿的适用性, so that 不适用的循环不干扰编制，且不遗漏应做的循环。

#### Acceptance Criteria

1. THE B23_Component SHALL 参照 SCOT+/仅重大/其他 适用性自动判断逻辑，为每个 Business_Cycle 呈现适用性状态。
2. WHEN 某 Business_Cycle 被标记为不适用, THE B23_Component SHALL 在列表中以不适用状态标签标注该循环，并立即确保编制进度计算排除该不适用循环（将其从编制进度分母中剔除，而非阻止进度更新）。
3. WHEN 适用性判断发生变化, THE B23_Component SHALL 更新仪表盘中的适用循环计数与编制进度。
4. THE B23_Component SHALL 允许审计助理手动覆盖某循环的适用性判断，并将覆盖结果持久化。

### Requirement 10: 持久化往返

**User Story:** As a 审计助理, I want B23 录入的控制矩阵、穿行、控制测试、缺陷与适用性数据真正落库并在刷新后回显, so that 我的编制成果不会丢失。

#### Acceptance Criteria

1. THE B23_Component SHALL 将录入数据持久化至 Persistence_Store，item_id 以 `B23-` 为前缀。
2. WHEN 审计助理保存 B23 数据, THE B23_Component SHALL 通过带 `/api` 前缀的 checklist-responses 接口以 PUT 方式提交，且每条 item 携带 item_id。
3. WHEN 审计助理刷新或重新打开 B23, THE B23_Component SHALL 从 render-config 的 responses_snapshot 与 checklist-responses 载入数据并回显。
4. THE Persistence_Store SHALL 复用现有 `checklist_responses` 机制与后端 `B23-` 结论值白名单。
5. FOR ALL B23 录入数据，保存后再载入 SHALL 得到与保存前等价的数据（往返一致性）。

### Requirement 11: 复核 / 只读 / 修订机制

**User Story:** As a 质量控制复核合伙人, I want B23 保留复核、只读与修订机制, so that 复核锁定后底稿不被随意修改，符合质控要求。

#### Acceptance Criteria

1. WHILE 底稿处于只读状态, THE B23_Component SHALL 禁用全部录入控件且无例外，包括展开区块、切换显示选项等非修改类操作也一并在只读态禁用，仅允许查看。
2. THE B23_Component SHALL 保留既有的复核对话机制，允许在子视图标题栏发起复核。
3. WHERE 底稿处于复核锁定后的修订（amendment）状态, THE B23_Component SHALL 依据既有修订机制使录入控件可用（该修订状态不属于只读态，不受 Acceptance Criterion 1 的只读禁用约束）。
4. THE B23_Component SHALL 保留既有版本链与自动快照机制。

### Requirement 12: 附件入口正确性（P0 止血修复）

**User Story:** As a 审计助理, I want 附件 Tab 的每个循环入口标签正确、且覆盖 B23-1~B23-15 与 XX-5 全部循环, so that 我能为正确的循环上传正确的附件，不遗漏销售/货币资金/存货等前 8 个循环。

#### Acceptance Criteria

1. THE Attachment_Entry SHALL 为 B23-1~B23-15 与 B23-XX-5 每个子底稿提供入口，覆盖全部 14 循环及信息处理控制与职责分离通用模板。
2. THE Attachment_Entry SHALL 使每个入口的标签与其真实循环内容一致（B23-9 为职工薪酬、B23-10 为管理循环、B23-11 为税金等），不出现标签错位。
3. WHEN 审计助理在某循环入口上传附件, THE B23_Component SHALL 将附件关联到对应的循环子底稿。
4. THE `B23_ATTACHMENT_CODES` 配置 SHALL 与 Requirement 2 的 Business_Cycle 编码集合来自同一单一配置来源，避免标签与编码不一致。
5. IF 部分 Attachment_Entry 因系统错误或网络问题加载失败, THEN THE B23_Component SHALL 允许审计助理使用已成功加载的入口继续工作，而不阻塞操作，也不要求全部入口恢复后才能访问。

### Requirement 13: 注册与路由

**User Story:** As a 平台维护者, I want B23 的组件注册与路由配置正确一致, so that B23 及其子底稿被路由到正确的渲染组件，不被 onlyoffice-sheet 兜底。

#### Acceptance Criteria

1. THE B23_Component SHALL 在 `htmlRendererRegistry.ts` 注册 `b23-process-control` componentType 并以懒加载方式引入。
2. THE wp_code_overrides SHALL 将 B23 及各子底稿按选定 Rendering_Model 一致地映射到 componentType 或 `skip`。
3. WHERE 采用聚合组件模式且存在后端 render 策略, THE 后端 SHALL 为 `b23-process-control` 注册 RENDERER_DISPATCH 分派，避免被 onlyoffice-sheet 吞掉。
4. THE checklist_responses 保存端点 SHALL 在白名单中接受 `B23-` 前缀的 item_id。
5. THE 后端 render 策略 SHALL 复用既有 `b23_walkthrough_for_cycle`、`b23_walkthrough_progress` resolver 与 WORKPAPER_SAVED 事件处理器写入 `field_overrides scope=b23_walkthrough:{cycle}` 的机制。

### Requirement 14: 导入导出

**User Story:** As a 现场经理, I want B23 的控制矩阵等结构化数据支持导入导出, so that 我能批量编制与复用控制点数据。

#### Acceptance Criteria

1. THE B23_Component SHALL 通过 ExcelJS 提供导入导出能力，保留既有导入导出机制。
2. WHEN 审计助理导出 B23 数据, THE B23_Component SHALL 按 Business_Cycle 分 sheet 导出控制矩阵、穿行测试、控制测试与缺陷汇总。
3. WHEN 审计助理导入 B23 数据, THE B23_Component SHALL 校验列结构并将匹配的数据回写到对应循环子底稿，不匹配的列跳过并提示。
4. FOR ALL 控制矩阵数据，导出后再导入 SHALL 得到与导出前等价的数据（导入导出往返一致性）。

### Requirement 15: 流程图与 WCGW 结构化录入（P2）

**User Story:** As a 审计助理, I want B23-x-2 流程图及描述中的 WCGW 支持结构化录入, so that WCGW 能被控制矩阵引用并可追溯，而不再是自由文本 docx。

#### Acceptance Criteria

1. THE B23_Component SHALL 允许按子流程结构化录入流程描述与 WCGW 标注（如"收入1/WCGW1"）。
2. THE 结构化 WCGW SHALL 可被 Control_Matrix 的 WCGW 字段引用。
3. WHEN WCGW 被控制矩阵引用, THE B23_Component SHALL 允许从控制点追溯到对应 WCGW 描述。

### Requirement 16: 循环集群目录（P2）

**User Story:** As a 现场经理, I want B23 的 14 循环集群有一个目录导航, so that 我能快速在循环间切换并了解整体结构。

#### Acceptance Criteria

1. THE B23_Component SHALL 提供以 GtBArchitectureTree 形式呈现的循环集群目录，并显示数据中遇到的所有循环，即使循环数量达到 15 或更多也全部显示，而不强制 14 循环上限。
2. WHEN 审计助理在目录中选择某 Business_Cycle 或子底稿, THE B23_Component SHALL 切换到对应视图。
3. THE 目录 SHALL 显示每个循环的完成状态与适用性状态。

## Correctness Properties

以下为 B23 重做的高价值正确性属性，供设计阶段生成属性测试（PBT）参考。

### P1 — 持久化往返不变式（Round Trip）
对任意有效的 B23 录入数据（控制矩阵、穿行测试、控制测试、缺陷、适用性），执行"保存 → 载入"后得到的数据与保存前等价。`load(save(x)) == x`。（对应 Requirement 10）

### P2 — 导入导出往返不变式（Round Trip）
对任意有效的控制矩阵数据，执行"导出 → 导入"后得到的数据与导出前等价。`import(export(x)) == x`。（对应 Requirement 14）

### P3 — 循环集合与配置一致（Invariant）
渲染的 Business_Cycle 集合、附件入口编码集合、B50/C 类联动映射的循环键，三者恒等于单一配置来源定义的 14+2 循环集合。附件入口标签恒与其循环编码在配置中的名称一致。（对应 Requirement 2、Requirement 12）

### P4 — 关键控制驱动测试对象（Metamorphic）
控制测试对象集合 ⊆ 关键控制点集合 ⊆ 控制点全集。仅当控制点"是否为关键控制点"为是时才可进入穿行测试与控制测试。（对应 Requirement 4、Requirement 5）

### P5 — 穿行有效是控制测试前置（Metamorphic）
对任意关键控制点，仅当其穿行测试结果为"按设计执行"时，才生成"建议执行控制测试"联动提示。若穿行结果为"未按设计执行"，则必生成缺陷提示。（对应 Requirement 5、Requirement 7）

### P6 — 缺陷触发一致（Invariant）
对任意控制点，若"控制设计是否有效"为否，或穿行测试结果为"未按设计执行"，则缺陷汇总中必存在对应的缺陷提示。（对应 Requirement 4、Requirement 6）

### P7 — 适用性过滤幂等（Idempotence）
对任意循环集合应用适用性过滤两次的结果与应用一次相同；不适用循环恒不计入编制进度分母。`filter(filter(x)) == filter(x)`。（对应 Requirement 9）

### P8 — 穿行与控制测试结论分离（Invariant）
穿行测试结论与控制测试结论持久化为两个独立字段，任一方的写入不覆盖另一方。（对应 Requirement 5）

### P9 — 只读态禁写（Invariant）
在只读状态下，任意录入操作都不产生对 Persistence_Store 的写入。（对应 Requirement 11）

### P10 — item_id 前缀完整（Invariant）
B23 提交的每条持久化 item 都携带以 `B23-` 为前缀的非空 item_id。（对应 Requirement 10、Requirement 13）
