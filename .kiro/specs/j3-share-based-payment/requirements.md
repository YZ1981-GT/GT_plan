# Requirements Document: J3 股份支付底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。
2. **底稿模板库md**（`BCD类底稿md/J应付职工薪酬循环底稿模板库.md`）：获取业务语义。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **无独立科目！跨多科目**（资本公积/管理费用/应付职工薪酬） + M4资本公积联动
- **美观性**：分组配色 + 期权到期时间轴 + 进度条
- **跳转溯源**：GtIndexChip跳转M4 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + Black-Scholes参数说明
- **导入导出**：el-dropdown三级 + useJ3ImportExport
- **AI辅助**：期权定价参数合理性 + 审计说明
- **双模式**：el-segmented + OO降级
- **期权定价核心**：Black-Scholes模型 + 等待期费用分摊

## Introduction

J3股份支付底稿的专属HTML精美组件构建。覆盖来自 `J3 股份支付.xlsx` 的6个有效sheet。**无独立科目**（分散在资本公积3002/管理费用6602/应付职工薪酬2211等多科目）。

**J3核心特殊**：①**无独立科目！跨多科目**（股份支付不在单一科目，分散记账）②**期权定价模型(Black-Scholes)**是核心计算③**等待期费用分摊**（总公允价值÷等待期×已服务期间）④权益结算vs现金结算两种模式⑤联动M4资本公积（权益结算贷方）⑥IPO企业适用性。关键公式总数约50+。

## Glossary

- **Tab_Index**: 底稿目录，19行7列
- **Procedure_Table_J3A**: 股份支付实质性程序表J3A，39行12列
- **Detail_J3_1**: 股份支付情况表J3-1，43行18列7公式（明细表）
- **Check_J3_2**: 股份支付检查表J3-2，43行19列
- **Black_Scholes**: Black-Scholes期权定价模型（核心！）
- **Vesting_Period**: 等待期（授予日到可行权日之间的期间）
- **Fair_Value**: 权益工具公允价值（授予日确定）
- **Expense_Allocation**: 等待期费用分摊=总公允价值÷等待期×已服务期间
- **Equity_Settled**: 权益结算股份支付（贷记资本公积-其他资本公积）
- **Cash_Settled**: 现金结算股份支付（贷记应付职工薪酬）
- **Cross_Account**: 跨多科目：资本公积3002 / 管理费用6602 / 应付职工薪酬2211
- **M4_Linkage**: 联动M4资本公积（权益结算贷方）
- **IPO_Relevance**: IPO企业股权激励特别关注

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to J3股份支付按sheetName分发, so that 6个sheet有序组织。

#### Acceptance Criteria

1. THE J3 组件 SHALL 注册componentType: `j3-share-based-payment`，主入口GtJ3ShareBasedPayment.vue
2. THE GtJ3ShareBasedPayment.vue SHALL 接收sheetName prop，v-if分发
3. THE J3 组件 SHALL defineAsyncComponent懒加载
4. THE J3 组件 SHALL 子目录：j3/core/（情况表+检查表）
5. THE J3 组件 SHALL composable分层：useJ3FormData + useJ3FormulaEngine + useJ3OptionPricingEngine(纯函数) + useJ3CrossSheet + useJ3DualMode + useJ3ImportExport
6. THE J3 组件 SHALL htmlRendererRegistry注册'j3-share-based-payment'
7. THE J3 组件 SHALL wp_code_overrides: J3/J3-1~J3-2/J3A → 'j3-share-based-payment'
8. THE J3 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE J3 组件 SHALL selfLoad支持
10. THE J3 组件 SHALL checklist_responses存储，前缀"J3-{sheet}-{field}"

### Requirement 2: 股份支付情况表J3-1（43行18列，明细表）

**User Story:** As a 审计助理, I want to 查看股份支付各期方案明细, so that 我能掌握每个股权激励计划的关键要素。

#### Acceptance Criteria

1. THE Detail_J3_1 SHALL 显示列：方案名|类型(权益/现金)|授予日|行权价|标的股数|等待期|可行权日|有效期|公允价值|已确认费用|本期费用|累计费用|剩余费用|状态
2. THE Formula_Engine SHALL 本期费用=总公允价值÷等待期×本期已服务（等待期费用分摊）
3. THE Formula_Engine SHALL 累计费用=Σ(各期已确认费用)
4. THE Formula_Engine SHALL 剩余费用=总公允价值-累计费用
5. THE Detail_J3_1 SHALL 权益结算→标注"贷记资本公积" / 现金结算→标注"贷记应付职工薪酬"
6. THE Detail_J3_1 SHALL 底部合计行+联动检查表
7. THE Detail_J3_1 SHALL 动态行+导入导出

### Requirement 3: 期权定价引擎（Black-Scholes模型，核心！）

**User Story:** As a 审计助理, I want to 验证期权公允价值的定价计算, so that 我能确认Black-Scholes模型参数合理。

#### Acceptance Criteria

1. THE Option_Pricing_Engine SHALL calcBlackScholes(S, K, T, r, sigma): BS期权定价
  - S=标的价格, K=行权价, T=到期时间(年), r=无风险利率, sigma=波动率
2. THE Option_Pricing_Engine SHALL calcD1(S, K, T, r, sigma): d1=(ln(S/K)+(r+σ²/2)×T)/(σ×√T)
3. THE Option_Pricing_Engine SHALL calcD2(d1, sigma, T): d2=d1-σ×√T
4. THE Option_Pricing_Engine SHALL 参数合理性检查：sigma∈[10%,100%], r∈[1%,10%], T>0
5. WHEN 参数超出合理范围时 SHALL 黄色警告+审计关注
6. THE Option_Pricing_Engine SHALL 支持二叉树模型作为替代验证

### Requirement 4: 等待期费用分摊

**User Story:** As a 审计助理, I want to 验证等待期费用分摊的正确性, so that 我能确认各期确认的薪酬费用准确。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcVestingExpense(totalFV, vestingPeriod, serviceYears): 本期费用
  - 公式：总公允价值 × (已服务年数/等待期) - 以前年度累计确认
2. THE Formula_Engine SHALL calcCumulativeExpense(totalFV, vestingPeriod, serviceYears): 累计费用
  - 公式：总公允价值 × MIN(已服务年数/等待期, 1)
3. THE Formula_Engine SHALL 等待期内逐年递增确认，等待期满后不再确认
4. THE Formula_Engine SHALL 处理提前失效（员工离职→冲回已确认费用）

### Requirement 5: 股份支付检查表J3-2（43行19列）

**User Story:** As a 审计助理, I want to 执行股份支付检查程序, so that 我能完整核验授予/确认/行权各环节。

#### Acceptance Criteria

1. THE Check_J3_2 SHALL 段落型检查含：授予条件核验/公允价值确定/等待期费用/行权/修改/取消
2. THE Check_J3_2 SHALL 权益结算 vs 现金结算分类检查
3. THE Check_J3_2 SHALL 逐项结论+方法论上下文（CAS11要求）
4. THE Check_J3_2 SHALL Black-Scholes参数逐项验证（波动率/无风险利率/到期时间/股息率）
5. THE Check_J3_2 SHALL AI辅助参数合理性分析

### Requirement 6: 跨多科目联动

**User Story:** As a 审计助理, I want to 股份支付联动相关科目, so that 权益结算和现金结算的记账正确。

#### Acceptance Criteria

1. THE Cross_Account SHALL 权益结算：借管理费用6602，贷资本公积3002→联动M4
2. THE Cross_Account SHALL 现金结算：借管理费用6602，贷应付职工薪酬2211→联动J1
3. THE Cross_Account SHALL GtIndexChip支持J3→M4资本公积/J3→J1应付职工薪酬跳转
4. THE Cross_Account SHALL EventBus publish 'share-payment:expense-recognized'

### Requirement 7: IPO企业适用性

**User Story:** As a 项目经理, I want to 系统标识IPO企业特殊关注点, so that 股权激励审计满足IPO审核要求。

#### Acceptance Criteria

1. THE J3 组件 SHALL 在项目类型为IPO时显示"IPO审计重点提示"面板
2. THE IPO面板 SHALL 显示：股份支付费用对利润影响/对每股收益稀释/信息披露充分性
3. THE IPO面板 SHALL 可折叠（非IPO项目默认隐藏）
