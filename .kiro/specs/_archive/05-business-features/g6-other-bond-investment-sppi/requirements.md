# Requirements Document

## Introduction

G6其他债权投资(SPPI组)底稿专属HTML精美组件构建。组件 `g6-other-bond-investment-sppi`，覆盖源模板21个sheet中的6个sheet（SPPI+公允价值+利息+盘点组）。**本组聚焦IFRS9分类三要素验证**：业务模式分析(G6-7)、合同现金流量特征(SPPI)分析(G6-8)、公允价值测试(G6-5)、利息测算(G6-6)、有价证券盘点(G6-9/G6-10)。

**本组(SPPI)sheet清单**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 公允价值测试表G6-5 | 40×18 | Level1/2/3公允价值测试 |
| 2 | 利息测算表G6-6 | 32×11 | 实际利率法利息测算 |
| 3 | 业务模式分析G6-7 | 49×8 | IFRS9业务模式三类判断 |
| 4 | 合同现金流量特征分析G6-8 | 80×10 | **特色**：SPPI测试（仅本金+利息） |
| 5 | 有价证券盘点表G6-9 | 29×7 | 证券盘点 |
| 6 | 盘点倒轧表G6-10 | 39×18 | 盘点日→基准日倒轧 |

**关键特色**：
1. **SPPI测试(G6-8)**：80行详细问卷，验证合同现金流量是否仅包含本金和利息（SPPI=Solely Payments of Principal and Interest）
2. **业务模式三类(G6-7)**：收取合同现金流量/出售/两者兼有
3. **公允价值测试(G6-5)**：18列，同G8/G9结构
4. **利息测算(G6-6)**：实际利率法，同G4-4结构

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎(无，本组无程序表) / ❌ 截止 / ❌ 附注EventBus / ❌ OCR / ✅ 复核对话

## Glossary

- **SPPI_Test**: 合同现金流量特征测试，验证金融资产的合同现金流量是否仅为对本金和以未偿付本金金额为基础的利息的支付
- **Business_Model**: 业务模式，企业管理金融资产的方式：①持有以收取合同现金流量 ②既收取又出售 ③其他
- **Fair_Value_Test**: 公允价值测试，验证报表日公允价值计量的正确性
- **Effective_Interest_Method**: 实际利率法，按实际利率计算利息收入
- **Securities_Inventory**: 有价证券盘点，实物/电子证券的期末存在性验证

## Requirements

### Requirement 1: 组件架构

**User Story:** As a 开发者, I want to G6其他债权投资(SPPI组)按sheetName prop分发, so that 6个sheet通过统一入口组织。

#### Acceptance Criteria

1.1 THE G6-SPPI组件 SHALL 注册componentType: `g6-other-bond-investment-sppi`，主入口GtG6OtherBondInvestmentSppi.vue
1.2 THE G6-SPPI组件 SHALL defineAsyncComponent懒加载6个子组件
1.3 THE G6-SPPI组件 SHALL 注册四件套（6条wp_code_overrides）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: 公允价值测试表G6-5（18列→2区段Tab）

**User Story:** As a 审计助理, I want to 测试其他债权投资公允价值。

#### Acceptance Criteria

2.1 THE G6-5 SHALL 40行×18列，2区段Tab：
   - **Tab1: 基础+审定(10列)**：投资项目|面值|期末未审(数量/单价/公允价值)|期末审定(数量/单价/公允价值)|差异|公允价值层次(下拉)
   - **Tab2: 估值详情(8列)**：投资项目|估值方法|与上期一致性|来源机构|输入值来源|估值技术|不可观察输入值|估值文件索引
2.2 THE G6-5 SHALL Level3必填校验+差异红色高亮+行同步+动态行增删+导入导出+AI辅助

### Requirement 3: 利息测算表G6-6（实际利率法）

**User Story:** As a 审计助理, I want to 测算其他债权投资利息收入。

#### Acceptance Criteria

3.1 THE G6-6 SHALL 32行×11列，分组结构（每项目：初始信息+多期利息计算）：
   - 投资项目|面值|票面利率|实际利率|截止日|期初摊余成本|实际利息收入(公式)|现金流入(公式)|期末摊余成本(公式)|计息天数|备注
3.2 THE Formula_Engine SHALL 实际利息 = 摊余成本 × 实际利率 × days/365
3.3 THE Formula_Engine SHALL 现金流入 = 面值 × 票面利率 × days/365
3.4 THE Formula_Engine SHALL 期末摊余 = 期初 + 实际利息 - 现金流入
3.5 THE G6-6 SHALL 底部与G6-1利息调整审定数交叉验证+AI辅助+动态行增删+导入导出

### Requirement 4: 业务模式分析G6-7

**User Story:** As a 审计助理, I want to 分析其他债权投资业务模式, so that 判断分类为FVOCI是否合理。

#### Acceptance Criteria

4.1 THE G6-7 SHALL 49行×8列问卷式：序号|检查项目|审计要求|管理层说明(textarea)|是否满足(下拉)|审计结论(textarea)|风险评级|索引
4.2 THE G6-7 SHALL 分为三个section：
   - **(一) 业务模式确定**：收取目的/出售频率/业绩评价方式
   - **(二) 出售情况分析**：出售频率/金额/原因是否改变业务模式
   - **(三) 综合判断**：最终分类结论(持有收取/兼有/其他)
4.3 THE G6-7 SHALL 顶部方法论上下文(CAS22业务模式三类定义)+每section AI辅助

### Requirement 5: 合同现金流量特征分析G6-8（SPPI测试，80行问卷）

**User Story:** As a 审计助理, I want to 分析合同现金流量特征, so that 判断金融资产是否满足SPPI条件。

#### Acceptance Criteria

5.1 THE G6-8 SHALL 80行×10列问卷式，分多section：
   - **(一) 本金定义**：初始确认时的公允价值
   - **(二) 利息定义**：货币时间价值+信用风险+流动性风险+管理成本+利润
   - **(三) 修改时间价值**：是否存在期限错配/利率重置不匹配
   - **(四) 提前还款条款**：是否包含提前还款/延期权
   - **(五) 合同关联工具**：是否存在优先/次级结构
   - **(六) 综合判断**：是否满足SPPI
5.2 THE G6-8 SHALL 列结构：序号|检查区域|检查项目|CAS要求|企业合同条款摘要(textarea)|是否满足SPPI(是/否/不适用)|判断依据(textarea)|风险等级|索引|备注
5.3 THE G6-8 SHALL 80行启用虚拟滚动
5.4 THE G6-8 SHALL 顶部方法论上下文(SPPI定义)+每section AI辅助+底部综合结论
5.5 WHEN 任一section综合判断为"否"时, THE 系统 SHALL 红色高亮并提示"不满足SPPI，需重分类"

### Requirement 6: 有价证券盘点G6-9 + 盘点倒轧G6-10

**User Story:** As a 审计助理, I want to 盘点有价证券并编制倒轧表。

#### Acceptance Criteria

6.1 THE G6-9 SHALL 29行×7列：序号|证券名称|证券代码|面值|数量(盘点)|数量(账面)|差异
6.2 THE G6-10盘点倒轧表 SHALL 39行×18列，2区段Tab：
   - **Tab1: 倒轧计算(10列)**：证券名称|盘点日数量|盘点日-基准日增减|基准日数量(公式)|账面数量|差异|差异原因|差异结论|索引|备注
   - **Tab2: 增减明细(8列)**：证券名称|日期|交易类型(买入/卖出/到期/转让)|数量|金额|凭证号|经办人|备注
6.3 THE Formula_Engine SHALL 基准日数量 = 盘点日数量 ± 盘点日到基准日的增减
6.4 THE G6-9/G6-10 SHALL 动态行增删+导入导出

### Requirement 7: 公式引擎+联动+UI

**User Story:** As a 开发者, I want to 实现G6-SPPI组公式引擎和完整集成, so that 利息测算/公允价值/盘点等公式可PBT验证。

#### Acceptance Criteria

7.1 THE Formula_Engine SHALL：calcEffectiveInterest(amortized,rate,days)/calcCashInflow(face,coupon,days)/calcEndingAmortized(opening,interest,cashInflow)/calcFairValueDiff/calcInventoryRollForward/parseNum
7.2 THE 集成 SHALL（版本链+复核对话，本组无程序表/附注/凭证所以无抽凭/截止/EventBus/OCR）
7.3 THE Import_Export SHALL G6-5/G6-6/G6-9/G6-10（4张表）
7.4 THE AI辅助 SHALL：fair-value-conclusion/interest-conclusion/business-model-conclusion/sppi-conclusion
7.5 THE 虚拟滚动 SHALL G6-8(80行)
7.6 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 实际利息** — amortizedCost × rate × days/365

**P2: 现金流入** — faceValue × couponRate × days/365

**P3: 期末摊余** — opening + interest - cashInflow

**P4: 盘点倒轧** — 基准日数量 = 盘点日数量 ± 增减

**P5: 公允价值差异** — audited - unadjusted

**P6: parseNum** — null/undefined/NaN → 0
