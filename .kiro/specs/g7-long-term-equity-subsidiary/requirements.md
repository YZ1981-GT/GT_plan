# Requirements Document

## Introduction

G7长期股权投资(子公司组)底稿专属HTML精美组件构建。组件 `g7-long-term-equity-subsidiary`，覆盖源模板22个sheet中的7个sheet（子公司投资全流程+凭证检查）。**本组聚焦子公司投资的初始→后续→处置全生命周期测试**：初始判断(G7-7)→同控取得(G7-8)/非同控取得(G7-9)→后续计量(G7-10)→处置(G7-11/G7-12)→凭证检查(G7-18)。

**本组sheet清单**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 长期股权投资初始判断G7-7 | 47×9 | 控制判断决策树 |
| 2 | 子公司初始计量测试（同控）G7-8 | 52×9 | 同一控制下企业合并 |
| 3 | 子公司初始计量测试（非同控）G7-9 | 53×9 | 非同一控制下企业合并 |
| 4 | 子公司后续计量测试表G7-10 | 48×9 | 成本法后续计量(股利+减值) |
| 5 | 处置子公司测试表（不包含一揽子交易）G7-11 | 47×14 | 单次处置损益计算 |
| 6 | 处置子公司测试表（一揽子交易）G7-12 | 54×14 | 多次交易构成一揽子处置 |
| 7 | 凭证检查表G7-18 | 99×19 | 凭证检查+OCR |

**关键特色**：
1. **初始判断决策树(G7-7)**：47行问卷判断控制/共同控制/重大影响→决定计量方法
2. **同控vs非同控差异**：同控合并用账面价值(G7-8)，非同控用公允价值(G7-9)
3. **处置判断复杂(G7-11/G7-12)**：单次处置vs一揽子交易，后者需追溯调整
4. **14列处置测试表**：含合并报表层面处置损益计算

**宽表处理策略**：
- G7-11处置(非一揽子)(14列)：单表（14列可接受）
- G7-12处置(一揽子)(14列)：单表
- G7-18凭证检查(19列)：3区段Tab

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎(G7-18) / ❌ 截止 / ❌ 附注EventBus / ✅ 行级OCR(G7-18) / ✅ 复核对话

## Glossary

- **Control_Judgment**: 控制判断，判断投资方是否对被投资方实施控制（权力+可变回报+联系）
- **Business_Combination_Same_Control**: 同一控制下企业合并，合并前后均受同一方最终控制（按账面价值计量）
- **Business_Combination_Not_Same**: 非同一控制下企业合并（按公允价值计量，差额确认商誉）
- **Cost_Method_Subsequent**: 成本法后续计量，子公司投资不调整账面价值，仅确认股利和减值
- **Disposal_Single**: 单次处置（非一揽子），一次交易丧失控制权
- **Disposal_Package**: 一揽子交易处置，多次交易实质上构成一项处置安排（需追溯调整）
- **Disposal_Gain_Loss**: 处置损益=处置对价-处置日长投账面-应收股利+原OCI中可转损益部分

## Requirements

### Requirement 1: 组件架构

**User Story:** As a 开发者, I want to G7长期股权投资(子公司组)按sheetName prop分发, so that 7个sheet通过统一入口组织。

#### Acceptance Criteria

1.1 THE G7-subsidiary组件 SHALL 注册componentType: `g7-long-term-equity-subsidiary`，主入口GtG7LongTermEquitySubsidiary.vue
1.2 THE G7-subsidiary组件 SHALL defineAsyncComponent懒加载7个子组件
1.3 THE G7-subsidiary组件 SHALL 注册四件套（7条wp_code_overrides）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: 初始判断G7-7

**User Story:** As a 审计助理, I want to 判断对被投资方的控制类型, so that 确定正确的计量方法。

#### Acceptance Criteria

2.1 THE G7-7 SHALL 47行×9列问卷式决策树：序号|判断维度|判断标准|被投资单位|判断结果(控制/共同控制/重大影响/无 下拉)|判断依据(textarea)|风险标识|审计结论|索引
2.2 THE G7-7 SHALL 顶部方法论上下文：控制三要素(权力+可变回报+权力与回报的联系)
2.3 THE G7-7 SHALL 每section AI辅助+底部综合结论

### Requirement 3: 子公司初始计量测试(同控G7-8/非同控G7-9)

**User Story:** As a 审计助理, I want to 测试子公司初始计量, so that 验证同控/非同控合并的初始入账金额正确。

#### Acceptance Criteria

3.1 THE G7-8同控 SHALL 52行×9列：被投资单位|合并日|合并方式|被合并方账面净资产|享有份额(公式)|初始投资成本(=享有份额)|支付对价|差额处理(资本公积)|审计结论
3.2 THE G7-9非同控 SHALL 53行×9列：被投资单位|购买日|合并方式|支付对价|直接费用|初始投资成本(公式)|被购买方可辨认净资产FV|享有份额(公式)|商誉(公式)
3.3 THE Formula_Engine SHALL 同控：初始投资成本 = 被合并方账面净资产 × 持股比例
3.4 THE Formula_Engine SHALL 非同控：初始投资成本 = 支付对价 + 直接费用；商誉 = 初始成本 - 享有份额
3.5 THE G7-8/G7-9 SHALL 每项被投资单位独立成组+动态行增删+导入导出

### Requirement 4: 子公司后续计量G7-10

**User Story:** As a 审计助理, I want to 测试子公司投资后续计量, so that 验证成本法核算正确。

#### Acceptance Criteria

4.1 THE G7-10 SHALL 48行×9列：被投资单位|期初账面|本期增加(追加投资)|本期减值|被投资方宣告股利|应确认投资收益(公式)|期末账面(公式)|企业期末数|差异
4.2 THE Formula_Engine SHALL 成本法投资收益 = 被投资方宣告股利 × 持股比例
4.3 THE Formula_Engine SHALL 期末账面 = 期初 + 追加 - 减值（成本法不含权益法调整）
4.4 THE G7-10 SHALL 动态行增删+导入导出+AI辅助

### Requirement 5: 处置测试表(非一揽子G7-11/一揽子G7-12)

**User Story:** As a 审计助理, I want to 测试子公司处置损益, so that 验证处置会计处理正确性。

#### Acceptance Criteria

5.1 THE G7-11非一揽子处置 SHALL 47行×14列：被投资单位|处置日|处置比例|处置对价|处置日长投账面|处置日应收股利|处置前OCI累计|可转损益OCI|个别报表处置损益(公式)|合并报表调整|合并层面净资产份额|合并处置损益(公式)|审计结论|索引
5.2 THE G7-12一揽子处置 SHALL 54行×14列：被投资单位|各次交易日期|各次交易对价|各次交易持股变动|累计对价|累计持股变动|丧失控制权日|丧失日长投账面|丧失日剩余投资FV|追溯调整金额(公式)|合并处置损益(公式)|一揽子判断依据(textarea)|审计结论|索引
5.3 THE Formula_Engine SHALL 个别处置损益 = 处置对价 - 处置日账面 - 应收股利 + 可转损益OCI
5.4 THE Formula_Engine SHALL 一揽子追溯：各次交易在丧失控制权日统一确认，之前确认的损益需追溯调整
5.5 THE G7-11/G7-12 SHALL 动态行增删+导入导出+AI辅助

### Requirement 6: 凭证检查表G7-18（19列→3区段Tab）

**User Story:** As a 审计助理, I want to 检查长期股权投资凭证。

#### Acceptance Criteria

6.1 THE G7-18 SHALL 99行×19列，3区段Tab：
   - Tab1(7列)：日期|凭证号|业务内容|对方科目|借方|贷方|📎附件
   - Tab2(7列)：支持性文件|核对1-原始凭证|核对2-授权|核对3-账务|核对4-金额|核对5-分类|核对6-投资收益
   - Tab3(5列)：索引|是否异常|异常说明|风险等级|备注
6.2 THE G7-18 SHALL 抽凭引擎+行级OCR+虚拟滚动(99行)+借贷平衡+GtIndexChip
6.3 THE G7-18 SHALL 动态行增删+导入导出

### Requirement 7: 公式引擎+联动+UI

**User Story:** As a 开发者, I want to 实现G7子公司组公式引擎和完整集成, so that 同控/非同控/处置等公式可PBT验证。

#### Acceptance Criteria

7.1 THE Formula_Engine SHALL：calcSameControlCost(netAssets,ratio)/calcNotSameControlCost(price,fees)/calcGoodwill(cost,share)/calcCostMethodIncome(dividend,ratio)/calcDisposalGain(price,bookValue,dividend,oci)/isDebitCreditBalanced/parseNum
7.2 THE 集成 SHALL（版本链+抽凭(G7-18)+OCR(G7-18)+复核）
7.3 THE Import_Export SHALL G7-8/G7-9/G7-10/G7-11/G7-12/G7-18（6张表）
7.4 THE AI辅助 SHALL：control-judgment-conclusion/initial-measurement-conclusion/subsequent-conclusion/disposal-conclusion/voucher-conclusion
7.5 THE 虚拟滚动 SHALL G7-7(47行)/G7-8(52行)/G7-9(53行)/G7-18(99行)
7.6 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 同控初始成本** — calcSameControlCost(netAssets, ratio) === netAssets × ratio

**P2: 非同控初始成本** — calcNotSameControlCost(price, fees) === price + fees

**P3: 商誉** — calcGoodwill(cost, share) === cost - share（可为负→营业外收入）

**P4: 成本法投资收益** — calcCostMethodIncome(dividend, ratio) === dividend × ratio

**P5: 处置损益** — 处置对价 - 账面 - 应收股利 + 可转损益OCI

**P6: 商誉非负判断** — cost > share → 商誉；cost < share → 营业外收入

**P7: 借贷平衡** — |SUM(debits)-SUM(credits)| < 0.01

**P8: parseNum** — null/undefined/NaN → 0
