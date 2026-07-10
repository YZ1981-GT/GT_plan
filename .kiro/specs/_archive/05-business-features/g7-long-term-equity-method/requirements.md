# Requirements Document

## Introduction

G7长期股权投资(权益法组)底稿专属HTML精美组件构建。组件 `g7-long-term-equity-method`，覆盖源模板22个sheet中的8个sheet（权益法测算+减值组）。**本组聚焦权益法核算全流程**：被投资方信息(G7-4/G7-5/G7-6)→投资成本测试(G7-13)→权益法测算(G7-14)→内部交易抵销(G7-15)→未确认损失(G7-16)→减值测试(G7-17)。

**本组sheet清单**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 被投资单位基本信息G7-4 | 43×25 | 被投资方工商+股权结构 |
| 2 | 被投资单位财务信息（合营、联营）G7-5 | 57×10 | 被投资方损益表+资产负债表 |
| 3 | 被投资公司会计政策G7-6 | 31×7 | 会计政策一致性检查 |
| 4 | 合营、联营企业投资成本测试表G7-13 | 68×17 | **特色**：初始投资成本vs享有份额 |
| 5 | 权益法测算表G7-14 | 54×20 | **特色**：权益法核心测算（最复杂） |
| 6 | 权益法未实现内部交易抵销测算表G7-15 | 41×14 | 未实现利润抵销 |
| 7 | 未确认投资损失测试表G7-16 | 40×17 | 超额亏损→未确认损失 |
| 8 | 减值测试表G7-17 | 33×9 | 可收回金额vs账面价值 |

**关键特色**：
1. **权益法测算(G7-14)**：20列×54行，是G7中最核心的计算表，含净利润调整→享有份额→投资收益确认
2. **投资成本测试(G7-13)**：68行×17列，初始投资成本与享有被投资方可辨认净资产公允价值份额的比较（商誉/营业外收入）
3. **内部交易抵销(G7-15)**：顺流/逆流交易未实现利润的抵销计算
4. **未确认损失(G7-16)**：投资方超额亏损时长期权益(长期应收款)的抵减顺序

**宽表处理策略**：
- G7-4基本信息(25列)：2区段Tab（工商信息/股权结构+管理层）
- G7-13投资成本(17列)：2区段Tab（初始计量/商誉计算）
- G7-14权益法测算(20列)：2区段Tab（净利润调整/权益法计算）
- G7-16未确认损失(17列)：2区段Tab（长期权益分析/超额亏损分配）

**六大集成联动**：
- ✅ 版本链 / ❌ 抽凭(本组无程序表/凭证表) / ❌ 截止 / ❌ 附注EventBus / ❌ OCR / ✅ 复核对话

## Glossary

- **Equity_Method_Calculation**: 权益法测算，按持股比例确认投资收益=被投资方调整后净利润×持股比例
- **Investment_Cost_Test**: 投资成本测试，初始投资成本vs享有可辨认净资产公允价值份额（差额=商誉或营业外收入）
- **Unrealized_Internal_Transaction**: 未实现内部交易，投资方与被投资方之间的未实现利润需在权益法核算中抵销
- **Unrecognized_Loss**: 未确认投资损失，被投资方累计亏损超过投资账面价值时，超额部分按长期权益(长应收)→其他实质长期权益→预计负债顺序
- **Impairment_Test**: 减值测试，可收回金额(公允价值-处置费用 与 使用价值取高)vs账面价值
- **Net_Profit_Adjustment**: 净利润调整，权益法核算前需将被投资方净利润调整为公允价值口径

## Requirements

### Requirement 1: 组件架构

**User Story:** As a 开发者, I want to G7长期股权投资(权益法组)按sheetName prop分发, so that 8个sheet通过统一入口组织。

#### Acceptance Criteria

1.1 THE G7-equity-method组件 SHALL 注册componentType: `g7-long-term-equity-method`，主入口GtG7LongTermEquityMethod.vue
1.2 THE G7-equity-method组件 SHALL defineAsyncComponent懒加载8个子组件
1.3 THE G7-equity-method组件 SHALL 注册四件套（8条wp_code_overrides）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: 被投资单位基本信息G7-4（25列→2区段Tab）

**User Story:** As a 审计助理, I want to 查看被投资单位基本信息。

#### Acceptance Criteria

2.1 THE G7-4 SHALL 43行×25列，2区段Tab：
   - **Tab1: 工商信息(12列)**：被投资单位|统一社会信用代码|成立日期|注册资本|实缴资本|注册地|行业|主营业务|法定代表人|控制类型(下拉)|持股比例|投票权比例
   - **Tab2: 股权结构+管理层(13列)**：被投资单位|其他股东名称|其他股东持股|董事会席位|派出董事|是否有否决权|是否参与决策|重大影响判断依据(textarea)|管理层组成|最新审计报告日|审计意见类型|关联关系|备注
2.2 THE G7-4 SHALL 行同步+动态行增删(ElMessageBox输入被投资单位名称)+导入导出

### Requirement 3: 被投资单位财务信息G7-5 + 会计政策G7-6

**User Story:** As a 审计助理, I want to 获取被投资方财务数据并检查会计政策一致性。

#### Acceptance Criteria

3.1 THE G7-5 SHALL 57行×10列：被投资单位|报表项目|上年金额|本年金额|变动额|变动率|分析说明|数据来源|审计状态|备注（按被投资单位分组，组内含资产/负债/净资产/收入/利润等关键指标）
3.2 THE G7-6 SHALL 31行×7列问卷：序号|会计政策事项|被投资方政策|投资方政策|是否一致(下拉)|调整金额|调整说明
3.3 THE G7-5 SHALL 57行虚拟滚动+按被投资单位分组
3.4 THE G7-5/G7-6 SHALL 动态行增删+导入导出

### Requirement 4: 合营联营投资成本测试G7-13（68行×17列→2区段Tab）

**User Story:** As a 审计助理, I want to 测试合营联营企业初始投资成本, so that 判断是否存在商誉或营业外收入。

#### Acceptance Criteria

4.1 THE G7-13 SHALL 68行×17列，2区段Tab：
   - **Tab1: 初始计量(9列)**：被投资单位|投资日期|合并/非合并|支付对价|直接相关费用|初始投资成本(公式)|被投资方可辨认净资产公允价值|享有份额(公式)|差额(公式)
   - **Tab2: 商誉计算+调整(8列)**：被投资单位|差额性质(商誉/营业外收入)|会计处理|公允价值调整明细(textarea)|调整后净资产|调整后享有份额|审计结论(下拉)|索引
4.2 THE Formula_Engine SHALL 初始投资成本 = 支付对价 + 直接相关费用
4.3 THE Formula_Engine SHALL 享有份额 = 被投资方可辨认净资产公允价值 × 持股比例
4.4 THE Formula_Engine SHALL 差额 = 初始投资成本 - 享有份额（正=商誉，负=营业外收入）
4.5 THE G7-13 SHALL 68行虚拟滚动+行同步+动态行增删+导入导出

### Requirement 5: 权益法测算表G7-14（54行×20列→2区段Tab，最核心）

**User Story:** As a 审计助理, I want to 测算权益法投资收益, so that 验证企业确认的投资收益是否正确。

#### Acceptance Criteria

5.1 THE G7-14 SHALL 54行×20列，2区段Tab：
   - **Tab1: 净利润调整(10列)**：被投资单位|被投资方报告净利润|内部交易抵销|公允价值折旧摊销|会计政策调整|其他调整|调整后净利润(公式)|持股比例|应享有份额(公式)|企业确认投资收益
   - **Tab2: 权益法计算(10列)**：被投资单位|投资收益差异(公式)|其他综合收益变动|享有OCI(公式)|其他权益变动|享有其他权益(公式)|利润分配(股利)|期初权益法余额|期末权益法余额(公式)|审计结论
5.2 THE Formula_Engine SHALL 调整后净利润 = 报告净利润 - 内部交易 - 公允价值折旧 ± 会计政策 ± 其他
5.3 THE Formula_Engine SHALL 应享有份额 = 调整后净利润 × 持股比例
5.4 THE Formula_Engine SHALL 投资收益差异 = 应享有份额 - 企业确认投资收益
5.5 THE Formula_Engine SHALL 享有OCI = OCI变动 × 持股比例
5.6 THE Formula_Engine SHALL 享有其他权益 = 其他权益变动 × 持股比例
5.7 THE Formula_Engine SHALL 期末权益法余额 = 期初 + 投资收益 + OCI + 其他权益 - 利润分配
5.8 WHEN |投资收益差异|>重要性水平 SHALL 红色高亮
5.9 THE G7-14 SHALL 54行虚拟滚动+行同步+按被投资单位分组+动态行增删+导入导出+AI辅助

### Requirement 6: 内部交易抵销G7-15 + 未确认损失G7-16 + 减值G7-17

**User Story:** As a 审计助理, I want to 计算内部交易抵销和未确认损失。

#### Acceptance Criteria

6.1 THE G7-15 SHALL 41行×14列：被投资单位|交易类型(顺流/逆流 下拉)|交易内容|交易金额|未实现利润(公式)|持股比例|应抵销金额(公式)|上年抵销|本年变动|抵销分录|是否关联交易|审计结论|索引|备注
6.2 THE Formula_Engine SHALL 未实现利润 = 交易金额 × 毛利率（或直接填写）
6.3 THE Formula_Engine SHALL 应抵销金额 = 未实现利润 × 持股比例（逆流交易） 或 未实现利润（顺流交易）
6.4 THE G7-16 SHALL 40行×17列，2区段Tab：
   - **Tab1: 长期权益分析(9列)**：被投资单位|投资账面|长期应收款|其他实质长期权益|预计负债|合计长期权益|累计亏损|超额亏损(公式)|分配顺序
   - **Tab2: 超额亏损分配(8列)**：被投资单位|冲减投资|冲减长应收|冲减其他权益|确认预计负债|未确认损失(公式)|本期变动|审计结论
6.5 THE G7-17减值测试 SHALL 33行×9列：被投资单位|账面价值|可收回金额|减值迹象(是/否)|减值金额(公式)|公允价值-处置费用|使用价值|审计结论(下拉)|索引
6.6 THE Formula_Engine SHALL 减值金额 = MAX(0, 账面价值 - 可收回金额)
6.7 THE G7-15/G7-16/G7-17 SHALL 动态行增删+导入导出

### Requirement 7: 公式引擎+联动+UI

**User Story:** As a 开发者, I want to 实现G7权益法组公式引擎和完整集成, so that 权益法/投资成本/减值等公式可PBT验证。

#### Acceptance Criteria

7.1 THE Formula_Engine SHALL：calcInvestmentCost/calcShareOfNetAssets/calcGoodwill/calcAdjustedNetProfit/calcEquityShare/calcEquityMethodBalance/calcUnrealizedProfit/calcImpairmentAmount/parseNum
7.2 THE 集成 SHALL（版本链+复核对话，本组无程序表/凭证/附注所以无抽凭/截止/EventBus/OCR）
7.3 THE Import_Export SHALL G7-4/G7-5/G7-13/G7-14/G7-15/G7-16/G7-17（7张表）
7.4 THE AI辅助 SHALL：cost-test-conclusion/equity-method-conclusion/internal-transaction-conclusion/impairment-conclusion
7.5 THE 虚拟滚动 SHALL G7-5(57行)/G7-13(68行)/G7-14(54行)
7.6 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 初始投资成本** — 支付对价 + 直接费用

**P2: 享有份额** — 可辨认净资产FV × 持股比例

**P3: 商誉/营业外** — 初始成本 - 享有份额（正=商誉,负=营业外收入）

**P4: 调整后净利润** — 报告净利润 - 内部交易 - FV折旧 ± 政策 ± 其他

**P5: 权益法投资收益** — 调整后净利润 × 持股比例

**P6: 权益法余额递推** — 期初 + 投资收益 + OCI + 其他权益 - 股利 = 期末

**P7: 减值金额** — MAX(0, 账面 - 可收回)

**P8: 减值非负** — calcImpairmentAmount(...) ≥ 0

**P9: parseNum** — null/undefined/NaN → 0
