# Requirements Document: J2 长期应付职工薪酬-设定受益计划净资产底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/J应付职工薪酬循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(**负债类贷方！**) + B51舞弊三因素联动（会计估计风险）
- **美观性**：分组配色 + 精算假设对比面板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 精算师工作利用说明
- **导入导出**：el-dropdown三级 + useJ2ImportExport
- **AI辅助**：精算假设合理性分析 + 审计说明
- **双模式**：el-segmented + OO降级
- **精算核心**：DBO精算现值 + 精算假设（折现率/工资增长率/离职率/死亡率）

## Introduction

J2长期应付职工薪酬-设定受益计划净资产底稿的专属HTML精美组件构建。覆盖来自 `J2 长期应付职工薪酬-设定受益计划净资产.xlsx` 的9个有效sheet。科目2221长期应付职工薪酬（**贷方/负债类！**期末=期初+贷方-借方，与H9/J1同款处理）。

**J2核心特殊**：①**负债类贷方科目！**②**精算假设是核心**（折现率/工资增长率/离职率/死亡率，属于会计估计）③精算师工作利用（ISA620专家利用）④DBO精算现值复杂公式（设定受益义务现值）⑤联动B51舞弊三因素（会计估计风险评估）。关键公式总数约90+（审定表67公式密度极高！）。

## Glossary

- **Tab_Index**: 底稿目录，19行5列
- **Procedure_Table_J2A**: 长期应付职工薪酬实质性程序表J2A，34行12列
- **Adjudication_J2_1**: 审定表J2-1，81行14列**67公式！**（负债类贷方！）
- **Disclosure_Listed**: 附注上市公司，99行4列16公式
- **Disclosure_SOE**: 附注国企，78行7列22公式
- **Detail_J2_2**: 明细表J2-2，90行14列7公式
- **Adjustment_J2_3**: 调整分录汇总J2-3，25行10列
- **Accrual_Check_J2_4**: 计提情况检查表J2-4，48行8列
- **Actuarial_Assumption**: 精算假设（核心！折现率/工资增长率/离职率/死亡率）
- **DBO_Present_Value**: 设定受益义务现值（Defined Benefit Obligation）
- **Plan_Assets**: 计划资产公允价值
- **Net_Liability**: 净负债=DBO-计划资产
- **Actuary_Reliance**: 精算师工作利用（ISA620专家评估）
- **B51_Linkage**: 联动B51舞弊三因素（会计估计重大风险）
- **Liability_Formula**: 负债类公式：期末=期初+贷方-借方

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to J2长期应付职工薪酬按sheetName分发, so that 9个sheet有序组织。

#### Acceptance Criteria

1. THE J2 组件 SHALL 注册componentType: `j2-defined-benefit-plan`，主入口GtJ2DefinedBenefitPlan.vue
2. THE GtJ2DefinedBenefitPlan.vue SHALL 接收sheetName prop，v-if分发
3. THE J2 组件 SHALL defineAsyncComponent懒加载
4. THE J2 组件 SHALL 子目录：j2/core/（审定+明细+调整+附注）、j2/actuarial/（精算相关+检查）
5. THE J2 组件 SHALL composable分层：useJ2FormData + useJ2FormulaEngine(**负债类！**) + useJ2ActuarialEngine(纯函数) + useJ2CrossSheet + useJ2DualMode + useJ2ImportExport
6. THE J2 组件 SHALL htmlRendererRegistry注册'j2-defined-benefit-plan'
7. THE J2 组件 SHALL wp_code_overrides: J2/J2-1~J2-4/J2A → 'j2-defined-benefit-plan'
8. THE J2 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE J2 组件 SHALL selfLoad支持
10. THE J2 组件 SHALL checklist_responses存储，前缀"J2-{sheet}-{field}"

### Requirement 2: 审定表J2-1（负债类贷方科目！67公式）

**User Story:** As a 审计助理, I want to 在审定表中查看长期应付职工薪酬, so that 我能验证设定受益计划的净负债正确。

#### Acceptance Criteria

1. THE Adjudication_J2_1 SHALL 显示列：项目|期初|贷方发生(义务增加)|借方发生(支付减少)|期末|未审|AJE|RJE|审定数|同期|变动率|变动额|差异|备注
2. THE Formula_Engine SHALL **负债类！**期末=期初+贷方-借方（2221贷方=义务增加，借方=支付/精算利得）
3. THE Formula_Engine SHALL 审定=未审+AJE+RJE
4. THE Adjudication_J2_1 SHALL 三区块：一、设定受益义务现值(DBO) → 二、计划资产公允价值 → 三、净负债/净资产(=DBO-计划资产)
5. THE Adjudication_J2_1 SHALL 变动率=(本期-同期)/同期×100%
6. THE Adjudication_J2_1 SHALL TB取数+差异+writebackTB(**期末余额**，科目2221)
7. THE Adjudication_J2_1 SHALL 审计说明+结论+复核对话
8. THE Adjudication_J2_1 SHALL 底部显示精算假设摘要面板（折现率/工资增长率/离职率）

### Requirement 3: 明细表J2-2（90行14列）

**User Story:** As a 审计助理, I want to 查看设定受益计划明细, so that 我能按项目追踪DBO和计划资产变动。

#### Acceptance Criteria

1. THE Detail_J2_2 SHALL 显示：计划名称|类型|期初DBO|当期服务成本|利息成本|精算损益|支付|期末DBO|计划资产|净负债
2. THE Formula_Engine SHALL 期末DBO=期初+服务成本+利息成本+精算损失-精算利得-支付
3. THE Formula_Engine SHALL 净负债=期末DBO-计划资产
4. THE Detail_J2_2 SHALL 底部合计行联动审定表
5. THE Detail_J2_2 SHALL 动态行+导入导出
6. THE Detail_J2_2 SHALL 占比=各计划/合计×100%

### Requirement 4: 精算假设核心（DBO计算引擎）

**User Story:** As a 审计助理, I want to 验证精算假设的合理性, so that 我能评价设定受益义务的计量是否可靠。

#### Acceptance Criteria

1. THE Actuarial_Engine SHALL calcDBO(serviceCost, interestCost, actuarialGainLoss, payments, beginDBO): 精算现值
2. THE Actuarial_Engine SHALL calcInterestCost(beginDBO, discountRate): 利息成本=期初DBO×折现率
3. THE Actuarial_Engine SHALL calcNetLiability(dbo, planAssets): 净负债=DBO-计划资产
4. THE Actuarial_Engine SHALL calcActuarialGainLoss(expected, actual): 精算损益=预期-实际
5. THE Actuarial_Engine SHALL 精算假设合理性检查：折现率∈[2%,8%]、工资增长率∈[3%,15%]、离职率∈[1%,20%]
6. WHEN 精算假设超出合理范围时 SHALL 红色警告+审计关注

### Requirement 5: 精算师工作利用（ISA620）

**User Story:** As a 审计助理, I want to 记录精算师工作利用的评价, so that 符合ISA620专家利用要求。

#### Acceptance Criteria

1. THE Accrual_Check_J2_4 SHALL 段落型检查含：精算师胜任能力/客观性/工作范围/假设合理性/结果使用
2. THE Accrual_Check_J2_4 SHALL 精算假设逐项对比：本期vs上期vs行业
3. THE Accrual_Check_J2_4 SHALL 逐项结论+方法论上下文（ISA620要求）
4. THE Accrual_Check_J2_4 SHALL AI辅助精算假设合理性分析

### Requirement 6: B51舞弊三因素联动

**User Story:** As a 项目经理, I want to J2精算假设联动B51风险评估, so that 会计估计重大风险得到恰当识别。

#### Acceptance Criteria

1. THE B51_Linkage SHALL GtIndexChip支持J2→B51跳转（会计估计风险）
2. THE B51_Linkage SHALL EventBus publish 'actuarial:assumption-changed'
3. WHEN 精算假设变更时 SHALL 联动B51刷新风险评估
4. THE J2 审定表 SHALL 底部显示"B51风险联动"状态面板

### Requirement 7: 附注披露（上市99×4 + 国企78×7）

**User Story:** As a 审计助理, I want to 生成长期薪酬附注, so that 设定受益计划披露完整。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市99×4/16公式 + 国企78×7/22公式）
2. THE Disclosure SHALL 自动取数（DBO/计划资产/精算假设）+ AI辅助 + EventBus
3. THE Disclosure SHALL 按CAS9要求披露：精算假设/敏感性分析/到期分析

### Requirement 8: 调整分录J2-3

**User Story:** As a 审计助理, I want to 管理调整分录, so that 联动审定表。

#### Acceptance Criteria

1. THE Adjustment_J2_3 SHALL 标准调整分录25行10列+借贷平衡+EventBus+导入导出
