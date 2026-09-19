# Requirements Document: I2 开发支出底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/I无形资产循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **I6↔I2双向联动（核心！）** + I1资本化转入 + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + CAS6五条件引导面板 + 编制提示
- **导入导出**：el-dropdown三级 + useI2ImportExport
- **AI辅助**：多section AI（资本化时点判断AI建议）
- **双模式**：el-segmented + OO降级

## Introduction

I2开发支出底稿的专属HTML精美组件构建。覆盖来自 `I2 开发支出.xlsx` 的21个有效sheet。科目1717开发支出（借方/资产类）。

**I2核心特殊**：①CAS6资本化五条件检查（I2-6核心sheet！）②I6↔I2双向联动（同一研发活动的费用化vs资本化）③资本化→I1转入联动 ④研发项目台账极宽表(73列) ⑤4类检查表（材料/人员认定/工时/委外）⑥截止性测试双向。关键公式总数约150+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_I2A**: 开发支出实质性程序表I2A
- **Adjudication_I2_1**: 审定表I2-1，32行10列61公式
- **Disclosure_Listed**: 附注上市公司，58行7列
- **Disclosure_SOE**: 附注国企，17行8列41公式
- **Detail_I2_2**: 明细表I2-2，51行61列7公式 — 极宽表需拆分
- **Adjustment_I2_3**: 调整分录汇总I2-3
- **Policy_Check_I2_4**: 会计政策检查I2-4
- **Analysis_I2_5**: 实质性分析I2-5，51行16列31公式
- **Capitalization_I2_6**: 研发项目资本化时点判断I2-6，45行66列7公式 — **CAS6五条件核心！**
- **Project_Detail_I2_7**: 研发项目构成明细表I2-7，25行73列8公式 — 极宽表
- **Material_Check_I2_8**: 研发材料投入检查表I2-8
- **Staff_Check_I2_9**: 研发人员认定检查表I2-9
- **WorkHour_Check_I2_10**: 研发人员工时检查表I2-10
- **Outsource_Check_I2_11**: 委外研发检查表I2-11
- **Targeted_Check_I2_12**: 针对性检查表I2-12
- **Cutoff_Forward_I2_13**: 截止性测试（账到单据）I2-13
- **Cutoff_Backward_I2_14**: 截止性测试（单据到账）I2-14
- **Impairment_I2_15**: 减值准备测试表I2-15
- **Recoverable_I2_16**: 可收回金额测试I2-16
- **CAS6_Five_Conditions**: CAS6资本化五条件（技术可行性/完成意图/使用或出售能力/未来经济利益/资源充足）
- **Cross_WP_I6_I2**: I6↔I2双向联动（VR-I6-01: 研发总额=费用化I6+资本化I2）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to I2开发支出底稿按sheetName分发, so that 21个sheet有序组织。

#### Acceptance Criteria

1. THE I2 组件 SHALL 注册componentType: `i2-development-expenditure`，主入口GtI2DevelopmentExpenditure.vue
2. THE GtI2DevelopmentExpenditure.vue SHALL 接收sheetName prop，v-if分发
3. THE I2 组件 SHALL defineAsyncComponent懒加载
4. THE I2 组件 SHALL 子目录：i2/core/、i2/inspection/、i2/cutoff/、i2/impairment/
5. THE I2 组件 SHALL composable分层：useI2FormData + useI2FormulaEngine + useI2CapitalizationEngine + useI2CrossSheet + useI2DualMode + useI2ImportExport
6. THE I2 组件 SHALL 在htmlRendererRegistry注册
7. THE I2 组件 SHALL wp_code_overrides: I2/I2-1~I2-16/I2A → 'i2-development-expenditure'
8. THE I2 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE I2 组件 SHALL 支持selfLoad
10. THE I2 组件 SHALL checklist_responses存储，前缀"I2-{sheet}-{field}"

### Requirement 2: 审定表I2-1（61公式）

**User Story:** As a 审计助理, I want to 在审定表中查看开发支出审定数据, so that 我能验证资本化金额和期末余额。

#### Acceptance Criteria

1. THE Adjudication_I2_1 SHALL 显示：项目|期初余额|本期增加(资本化)|本期减少(转无形/转费用)|期末余额|未审|AJE|RJE|审定数|备注
2. THE Formula_Engine SHALL 期末=期初+增加-减少（资产类借方1717）
3. THE Formula_Engine SHALL 审定=未审+AJE+RJE
4. THE Adjudication_I2_1 SHALL 三角勾稽校验+红色高亮
5. THE Adjudication_I2_1 SHALL TB取数+差异行+writebackTB(1717)
6. THE Adjudication_I2_1 SHALL "本期减少-转无形资产"列联动I1增加检查
7. THE Adjudication_I2_1 SHALL 审计说明+结论+复核对话

### Requirement 3: 明细表I2-2（61列极宽表拆分）

**User Story:** As a 审计助理, I want to 管理研发项目开发支出明细, so that 我能按项目追踪资本化金额。

#### Acceptance Criteria

1. THE Detail_I2_2 SHALL 将61列拆分为4区段Tab：基础(项目名/立项日/阶段) | 本期投入(材料/人工/折旧/其他) | 资本化(资本化起点/金额/转入I1) | 期末汇总
2. THE Detail_I2_2 SHALL Tab切换行同步 + 合计行
3. THE Detail_I2_2 SHALL 联动审定表
4. THE Detail_I2_2 SHALL 动态行+导入导出

### Requirement 4: 实质性分析I2-5（31公式）

**User Story:** As a 审计助理, I want to 对开发支出进行实质性分析, so that 我能识别异常波动。

#### Acceptance Criteria

1. THE Analysis_I2_5 SHALL 显示：项目|期初|本期增加|本期减少|期末|同比变动率|预期值|差异|超阈值标记
2. THE Formula_Engine SHALL 计算变动率/预期值/差异
3. THE Analysis_I2_5 SHALL 差异超重要性水平时红色标记
4. THE Analysis_I2_5 SHALL AI辅助分析异常原因

### Requirement 5: CAS6资本化时点判断I2-6（核心！）

**User Story:** As a 审计助理, I want to 对每个研发项目逐项检查CAS6五条件, so that 我能判断资本化时点是否恰当。

#### Acceptance Criteria

1. THE Capitalization_I2_6 SHALL 按研发项目逐行显示五条件检查矩阵
2. THE CAS6五条件 SHALL 包含：①技术可行性 ②完成意图 ③使用或出售能力 ④未来经济利益 ⑤资源充足（技术/财务/其他）
3. THE Capitalization_I2_6 SHALL 每条件提供：是/否/不适用 勾选 + 证据描述 + 支撑附件
4. WHEN 五条件全部为"是"时, THE 结论 SHALL 自动显示"满足资本化条件"绿色
5. WHEN 任一条件为"否"时, THE 结论 SHALL 显示"不满足资本化条件"红色+具体缺失条件
6. THE Capitalization_I2_6 SHALL 顶部蓝色引导面板展示CAS6第9条原文+五条件逐项解读
7. THE Capitalization_I2_6 SHALL AI辅助按钮：根据项目描述自动建议各条件判断
8. THE Capitalization_I2_6 SHALL 资本化时点日期字段联动I2-2明细表"资本化起点"列

### Requirement 6: 研发项目构成明细表I2-7（73列极宽表）

**User Story:** As a 审计助理, I want to 查看研发项目费用构成, so that 我能验证各类费用归集的完整性。

#### Acceptance Criteria

1. THE Project_Detail_I2_7 SHALL 将73列拆分为5区段Tab：基础|材料费|人工费|折旧摊销|其他费用
2. THE Project_Detail_I2_7 SHALL 合计行+交叉验证I2-2
3. THE Project_Detail_I2_7 SHALL 虚拟滚动（25行但极宽）

### Requirement 7: 4类检查表（I2-8~I2-11）

**User Story:** As a 审计助理, I want to 检查研发投入各类费用, so that 我能验证材料/人员/工时/委外费用的真实性。

#### Acceptance Criteria

1. THE Material_Check_I2_8 SHALL 检查研发材料领用：品名/数量/单价/金额/领用单号/审核结论
2. THE Staff_Check_I2_9 SHALL 检查研发人员认定：姓名/岗位/资质/参与项目/认定结论
3. THE WorkHour_Check_I2_10 SHALL 检查工时分配：人员/项目/月份/工时/占比/结论
4. THE Outsource_Check_I2_11 SHALL 检查委外研发：供应商/合同号/金额/交付物/验收结论
5. 所有检查表 SHALL 支持动态行+OCR+抽凭引擎

### Requirement 8: 截止性测试双向（I2-13/I2-14）

**User Story:** As a 审计助理, I want to 执行开发支出截止性测试, so that 我能验证费用归属期间正确。

#### Acceptance Criteria

1. THE Cutoff_Forward_I2_13 SHALL 从账簿出发→核对原始单据（期末±5天）
2. THE Cutoff_Backward_I2_14 SHALL 从单据出发→核对账簿记录（期末±5天）
3. 截止测试 SHALL 支持useCutoffAutoSampling自动提取序时账样本
4. 截止测试 SHALL 显示：日期|金额|记账期间|单据日期|归属期间|是否跨期|结论

### Requirement 9: I6↔I2双向联动

**User Story:** As a 审计助理, I want to I6研发费用与I2开发支出双向联动, so that 费用化+资本化=研发总额校验。

#### Acceptance Criteria

1. THE Cross_WP_I6_I2 SHALL 通过cross_wp_references建立双向引用
2. THE Cross_WP_I6_I2 SHALL EventBus subscribe I6的'research:expense-updated'事件
3. THE Cross_WP_I6_I2 SHALL 校验：I6费用化金额 + I2资本化金额 = 研发总额（VR-I6-01）
4. WHEN 校验失败时, THE 组件 SHALL 显示红色警告"费用化+资本化≠研发总额，差额xxx"
5. THE Cross_WP_I6_I2 SHALL GtIndexChip支持I2→I6 / I6→I2双向跳转

### Requirement 10: 减值测试（I2-15/I2-16）

**User Story:** As a 审计助理, I want to 对开发支出执行减值测试, so that 我能验证资本化项目可回收性。

#### Acceptance Criteria

1. THE Impairment_I2_15 SHALL 显示：项目|账面|可收回金额|应计提|已计提|差额
2. THE Recoverable_I2_16 SHALL DCF测算（复用I1-13模式）
3. THE 减值 SHALL 联动审定表减值准备列

### Requirement 11: I2→I1资本化转入联动

**User Story:** As a 审计助理, I want to 开发支出转无形资产时自动联动, so that I1增加检查表自动接收转入项。

#### Acceptance Criteria

1. THE 转入联动 SHALL 通过EventBus发布'development:capitalized-to-intangible'
2. THE 转入联动 SHALL cross_wp_references: I2→I1-5(增加)
3. THE 转入联动 SHALL 转入金额=I2审定表"本期减少-转无形"列合计

### Requirement 12: 附注披露（上市+国企）

**User Story:** As a 审计助理, I want to 自动生成开发支出附注, so that 披露信息完整准确。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市58×7/国企17×8）
2. THE Disclosure SHALL 从审定表+明细表自动取数
3. THE Disclosure SHALL AI辅助+EventBus附注联动

### Requirement 13: 针对性检查表I2-12

**User Story:** As a 审计助理, I want to 执行针对性检查, so that 我能关注特定风险领域。

#### Acceptance Criteria

1. THE Targeted_Check_I2_12 SHALL 段落型检查+逐项结论
2. THE Targeted_Check_I2_12 SHALL 关注：研发费用加计扣除合规性/资本化比例合理性/项目进度

### Requirement 14: 会计政策检查I2-4

**User Story:** As a 审计助理, I want to 检查研发支出会计政策, so that 我能验证资本化政策的适当性。

#### Acceptance Criteria

1. THE Policy_Check_I2_4 SHALL CAS6相关条款段落型检查
2. THE Policy_Check_I2_4 SHALL 重点检查：研究vs开发阶段划分标准/资本化条件/摊销政策
3. THE Policy_Check_I2_4 SHALL 琥珀色方法论+引导区
