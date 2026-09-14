# Requirements Document

## Introduction

G1交易性金融资产底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g1-trading-financial-assets`，覆盖1个xlsx源模板(153KB)/16个有效sheet。科目1501交易性金融资产（借方/资产类）。**最复杂的投资科目底稿**。

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **G1A 实质性程序表** | 34R×10C | a-program-console |
| 2 | **G1-1 审定表** | 98R×11C | 多层结构(股票/基金/债券/衍生/其他×成本/公允变动/处置损益) |
| 3 | **附注披露(上市)** | 198R×12C | 超长附注！ |
| 4 | **附注披露(国企)** | 32R×5C | 国企附注格式 |
| 5 | **G1-2 明细表** | 53R×35C | **35列宽表！**按投资品种×持有明细×公允价值 |
| 6 | **G1-3 调整分录** | 21R×10C | AJE/RJE |
| 7 | **G1-4 结存表** | 46R×21C | 期初/增加/减少/期末结存(数量+成本+公允) |
| 8 | **G1-5 收益测算表** | 36R×18C | 投资收益/利息收入/处置损益测算 |
| 9 | **G1-6 公允价值测试表** | 41R×19C | **特色**：市场报价/估值模型Level1-3 |
| 10 | **G1-7 第三层次调节表** | 22R×13C | Level3公允价值变动调节 |
| 11 | **G1-8 业务模式分析** | 54R×8C | CAS22分类：持有至收取/出售/兼有 |
| 12 | **G1-9 分类适当性检查** | 31R×21C | SPPI测试+业务模式判定 |
| 13 | **G1-10 合同现金流量特征** | 80R×9C | SPPI详细分析(合同条款逐项检查) |
| 14 | **G1-11 有价证券监盘表** | 41R×10C | 证券盘点 |
| 15 | **G1-12 盘点倒轧表** | 23R×18C | 证券盘点倒轧 |
| 16 | **G1-13 检查表** | 48R×17C | 凭证核对检查 |
| 17 | **G1-14 衍生金融工具核查表** | 45R×10C | 衍生工具合规性 |

**宽表处理策略**：
- G1-2明细表(35列)：拆为5区段Tab（基础信息/持有明细/公允价值/损益/审定调整）
- G1-9分类适当性检查(21列)：拆为2区段Tab（SPPI测试/业务模式判定）
- G1-5收益测算(18列)：拆为2区段Tab（投资收益测算/处置损益测算）

**借方科目公式**（资产类）：
- 期末未审 = 期初审定 + 借方发生额 - 贷方发生额

**子目录组织**（16 sheets > 12 threshold → sheetName v-if dispatch + 子目录分组）：
- core/: 审定表+明细表+调整+附注（G1-1~G1-3 + 附注）
- valuation/: 公允价值测试+第三层次调节（G1-6~G1-7）
- classification/: 业务模式+分类适当性+合同现金流（G1-8~G1-10）
- inspection/: 证券监盘+盘点倒轧+检查表+衍生工具（G1-11~G1-14）

核心特色：公允价值Level1-3测试、SPPI分析、业务模式分类、证券监盘+倒轧、衍生工具核查。EventBus联动：publish substantive:adjudicated(accountCode='1501')。

## Glossary

- **Trading_Financial_Assets**: 交易性金融资产，以公允价值计量且变动计入当期损益的金融资产
- **Fair_Value_Level**: 公允价值层级：Level1=活跃市场报价/Level2=可观察输入/Level3=不可观察输入
- **SPPI_Test**: 合同现金流量特征测试(Solely Payments of Principal and Interest)，判断金融资产分类
- **Business_Model**: 业务模式分析(CAS22)：持有至收取合同现金流/出售/兼有
- **Securities_Count**: 证券监盘，实物证券/电子证券的盘点确认
- **Count_Reconciliation**: 盘点倒轧，盘点日余额→资产负债表日余额的调节
- **Derivative_Instrument**: 衍生金融工具（期权/期货/互换/远期），需特殊合规核查
- **Unrealized_Gain**: 未实现损益 = 公允价值 - 成本
- **Realized_Gain**: 已实现损益 = 处置收入 - 成本
- **Adjudication_Table**: 审定表(G1-1)，多层结构：按投资品种×损益分类
- **Debit_Direction**: 借方科目，期末=期初+借方-贷方（资产类）

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G1交易性金融资产底稿按sheetName prop分发到独立子组件, so that 16个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE G1-Trading-Financial-Assets 组件 SHALL 注册新componentType: `g1-trading-financial-assets`，主入口为 GtG1TradingFinancialAssets.vue（接收sheetName prop，v-if分发到子组件，未迁移sheet走OnlyOffice fallback）
1.2 THE G1-Trading-Financial-Assets 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（16个sheet按需加载）
1.3 THE G1-Trading-Financial-Assets 组件 SHALL 在htmlRendererRegistry中注册'g1-trading-financial-assets'→GtG1TradingFinancialAssets映射
1.4 THE G1-Trading-Financial-Assets 组件 SHALL 在wp_code_overrides.json中将G1A/G1-1~G1-14/附注披露(上市)/附注披露(国企)的componentType统一映射为'g1-trading-financial-assets'（17个wp_code条目）
1.5 THE G1-Trading-Financial-Assets 组件 SHALL 在VALID_COMPONENT_TYPES中注册'g1-trading-financial-assets'
1.6 THE GtG1TradingFinancialAssets.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=g1-trading-financial-assets）
1.7 THE GtG1TradingFinancialAssets.vue SHALL 用正则从sheetName提取编码(G1A/G1-1~G1-14/附注)，匹配失败走OnlyOffice fallback
1.8 THE G1-Trading-Financial-Assets 组件 SHALL 采用sheetName v-if dispatch模式（16 sheets > 12 threshold，不用el-tabs）
1.9 THE 子组件 SHALL 按子目录组织：core/(G1-1~G1-3+附注) / valuation/(G1-6~G1-7) / classification/(G1-8~G1-10) / inspection/(G1-11~G1-14)

### Requirement 2: G1A 实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中查看和执行交易性金融资产实质性程序, so that 我能按步骤完成审计程序并记录执行情况。

#### Acceptance Criteria

2.1 THE G1A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE G1A程序表 SHALL 显示34行×10列的审计程序步骤（含auto_data_source自动取数）
2.3 THE G1A程序表 SHALL 支持执行人/执行日期/结论/索引字段编辑

### Requirement 3: G1-1 审定表（多层结构，借方科目）

**User Story:** As a 审计助理, I want to 在精美HTML中填写交易性金融资产审定表, so that 我能汇总按投资品种和损益分类的审定数据并回写试算表。

#### Acceptance Criteria

3.1 THE G1-1审定表 SHALL 显示98行×11列多层结构，按投资品种分组：股票/基金/债券/衍生/其他
3.2 THE G1-1审定表 SHALL 每品种含子层：成本(期初/期末) + 公允价值变动(期初/期末) + 处置损益(本期)
3.3 THE G1-1审定表 SHALL 列结构：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|索引
3.4 THE G1-1审定表 SHALL 实现借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
3.5 THE G1-1审定表 SHALL 实现审定数公式：审定 = 未审 + AJE + RJE
3.6 THE G1-1审定表 SHALL 品种小计+全部合计自动汇总
3.7 THE G1-1审定表 SHALL 试算表数从trial_balance自动取数（科目1501）
3.8 THE G1-1审定表 SHALL 差异=审定-试算表数，差异≠0时红色高亮
3.9 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='1501', adjudicatedAmount=审定数）
3.10 THE G1-1审定表 SHALL 支持GtIndexChip索引列跳转
3.11 THE G1-1审定表 SHALL 支持展开/折叠品种分组（默认展开）

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 在精美HTML中编辑交易性金融资产附注披露, so that 我能按上市/国企格式生成附注文本。

#### Acceptance Criteria

4.1 THE 附注披露(上市) SHALL 显示198行×12列结构化表格（超长附注需虚拟滚动）
4.2 THE 附注披露(国企) SHALL 显示32行×5列结构化表格
4.3 THE 附注披露 SHALL 监听EventBus `substantive:adjudicated`(accountCode='1501')自动刷新审定数据
4.4 THE 附注披露 SHALL 通过EventBus发布 `disclosure:note-text-updated` 联动附注模块
4.5 THE 附注披露(上市) SHALL 启用虚拟滚动（198行超长附注）

### Requirement 5: G1-2 明细表（35列宽表→5区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中查看交易性金融资产逐笔明细, so that 我能检查每项投资的持有情况、公允价值和损益。

#### Acceptance Criteria

5.1 THE G1-2明细表 SHALL 拆为5区段Tab：
   - **基础信息(7列)**：序号|投资品种名称|证券代码|投资类型(股票/基金/债券/衍生/其他)|交易市场|初始取得日期|初始取得成本
   - **持有明细(7列)**：期初持有数量|本期买入数量|本期卖出数量|期末持有数量(公式)|期初成本|本期增加成本|本期减少成本
   - **公允价值(7列)**：期末单位公允值|期末公允价值(公式)|公允价值来源(Level1/2/3)|期初公允价值|公允价值变动(公式)|累计公允变动|报价日期
   - **损益(7列)**：本期处置收入|处置成本|已实现损益(公式)|利息/股利收入|投资收益合计(公式)|公允变动损益(本期)|备注
   - **审定调整(7列)**：期末成本(公式)|未审余额|AJE|RJE|审定余额(公式)|差异|索引
5.2 THE Formula_Engine SHALL 计算期末持有数量 = 期初 + 买入 - 卖出
5.3 THE Formula_Engine SHALL 计算期末公允价值 = 期末持有数量 × 期末单位公允值
5.4 THE Formula_Engine SHALL 计算公允价值变动 = 期末公允价值 - 期初公允价值
5.5 THE Formula_Engine SHALL 计算已实现损益 = 处置收入 - 处置成本
5.6 THE Formula_Engine SHALL 计算投资收益合计 = 已实现损益 + 利息/股利收入
5.7 THE Formula_Engine SHALL 计算期末成本 = 期初成本 + 本期增加成本 - 本期减少成本
5.8 THE Formula_Engine SHALL 计算审定余额 = 未审 + AJE + RJE
5.9 THE G1-2明细表 SHALL 区段间保持行同步
5.10 THE G1-2明细表 SHALL 底部合计行（按投资类型分类小计+总计）
5.11 THE G1-2明细表 SHALL 支持动态行增删 + 导入导出

### Requirement 6: G1-3 调整分录

**User Story:** As a 审计助理, I want to 在精美HTML中录入交易性金融资产调整分录, so that 我能记录AJE/RJE。

#### Acceptance Criteria

6.1 THE G1-3调整分录 SHALL 显示21行×10列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
6.2 THE G1-3调整分录 SHALL 借贷平衡校验
6.3 WHEN 借贷不平衡时, THE 系统 SHALL 以红色高亮并显示差额
6.4 THE G1-3调整分录 SHALL 支持动态行增删 + 导入导出

### Requirement 7: G1-4 结存表

**User Story:** As a 审计助理, I want to 在精美HTML中编辑证券结存表, so that 我能掌握每项投资的期初/增减/期末结存。

#### Acceptance Criteria

7.1 THE G1-4结存表 SHALL 显示46行×21列：证券名称|代码|类型 + 期初(数量/成本/公允) + 增加(数量/成本) + 减少(数量/成本/处置收入) + 期末(数量/成本/公允/未实现损益)
7.2 THE Formula_Engine SHALL 计算期末数量 = 期初数量 + 增加数量 - 减少数量
7.3 THE Formula_Engine SHALL 计算期末成本 = 期初成本 + 增加成本 - 减少成本
7.4 THE Formula_Engine SHALL 计算未实现损益 = 期末公允 - 期末成本
7.5 THE G1-4结存表 SHALL 品种分组小计+总计
7.6 THE G1-4结存表 SHALL 21列→2区段Tab（基础+期初增减 / 期末+损益）
7.7 THE G1-4结存表 SHALL 支持动态行增删 + 导入导出

### Requirement 8: G1-5 收益测算表

**User Story:** As a 审计助理, I want to 在精美HTML中测算投资收益, so that 我能验证企业确认投资收益/利息收入/处置损益的正确性。

#### Acceptance Criteria

8.1 THE G1-5收益测算表 SHALL 显示36行×18列，拆为2区段Tab：
   - **投资收益测算(9列)**：证券名称|持有数量|每股股利/利率|应收金额(公式)|实收金额|差异|确认日期|来源|备注
   - **处置损益测算(9列)**：证券名称|卖出数量|成交价|成交金额|原始成本|处置损益(公式)|手续费|净损益(公式)|备注
8.2 THE Formula_Engine SHALL 计算应收金额 = 持有数量 × 每股股利（或面值×利率×天数/365）
8.3 THE Formula_Engine SHALL 计算处置损益 = 成交金额 - 原始成本
8.4 THE Formula_Engine SHALL 计算净损益 = 处置损益 - 手续费
8.5 THE G1-5收益测算表 SHALL 底部合计+审计结论textarea(AI)
8.6 THE G1-5收益测算表 SHALL 支持动态行增删 + 导入导出

### Requirement 9: G1-6 公允价值测试表

**User Story:** As a 审计助理, I want to 在精美HTML中测试公允价值Level1-3, so that 我能验证企业公允价值计量的适当性。

#### Acceptance Criteria

9.1 THE G1-6公允价值测试表 SHALL 显示41行×19列：证券名称|代码|持仓数量|期末账面值|Level层级(1/2/3) + Level1(市场报价日期/报价来源/报价值/计算市值/差异) + Level2(可观察输入描述/估值方法/估值结果/差异) + Level3(不可观察输入/估值假设/估值结果/差异) + 结论|备注
9.2 THE Formula_Engine SHALL 计算Level1差异 = 计算市值(持仓×报价) - 账面值
9.3 THE Formula_Engine SHALL Level1计算市值 = 持仓数量 × 市场报价值
9.4 WHEN Level为1时, THE 系统 SHALL 只启用Level1列（Level2/3列灰色禁用）
9.5 WHEN Level为2时, THE 系统 SHALL 只启用Level2列
9.6 WHEN Level为3时, THE 系统 SHALL 只启用Level3列
9.7 WHEN |差异|>1%×账面值时, THE 系统 SHALL 以橙色高亮
9.8 THE G1-6公允价值测试表 SHALL 底部统计（Level1笔数/Level2笔数/Level3笔数/差异超阈值笔数）
9.9 THE G1-6公允价值测试表 SHALL 审计结论textarea(AI) + 编制提示details
9.10 THE G1-6公允价值测试表 SHALL 支持动态行增删 + 导入导出

### Requirement 10: G1-7 第三层次调节表

**User Story:** As a 审计助理, I want to 在精美HTML中编制Level3公允价值变动调节表, so that 我能追踪第三层次公允价值的变动明细。

#### Acceptance Criteria

10.1 THE G1-7第三层次调节表 SHALL 显示22行×13列：项目名称|期初余额|本期增加(新确认/转入)|本期减少(终止确认/转出)|本期公允变动|期末余额(公式)|累计变动|估值方法|关键假设|敏感性分析|审计评价|备注
10.2 THE Formula_Engine SHALL 计算期末余额 = 期初 + 增加 - 减少 + 本期公允变动
10.3 THE G1-7调节表 SHALL 合计行+审计结论textarea(AI)
10.4 THE G1-7调节表 SHALL 支持动态行增删

### Requirement 11: G1-8~G1-10 金融工具分类（SPPI+业务模式）

**User Story:** As a 审计助理, I want to 在精美HTML中分析金融工具分类适当性, so that 我能验证CAS22分类判定的合理性。

#### Acceptance Criteria

11.1 THE G1-8业务模式分析 SHALL 显示54行×8列叙述式：投资项目|业务模式描述|持有目的|历史交易频率|管理层意图|KPI考核关联|分类结论(持有至收取/出售/兼有)|审计评价
11.2 THE G1-9分类适当性检查 SHALL 显示31行×21列，拆为2区段Tab：
   - **SPPI测试(11列)**：投资项目|合同条款|基本借贷安排|仅为本金和利息|提前还款特征|信用风险|杠杆特征|非标准特征|SPPI通过/不通过|审计评价|备注
   - **业务模式判定(10列)**：投资项目|管理目标|资产组合管理方式|报酬机制|出售频率/规模|出售原因|是否符合持有收取|是否符合既收取又出售|最终分类|审计评价
11.3 THE G1-10合同现金流量特征 SHALL 显示80行×9列叙述式：投资项目|合同条款描述|是否含本金|利息构成分析|修改的货币时间价值|提前还款/展期条款|非追索权特征|SPPI结论|审计评价
11.4 THE G1-8/G1-10 SHALL 为叙述式表格（autosize textarea每格）
11.5 THE G1-9 SHALL SPPI通过/不通过下拉 + 最终分类下拉(FVTPL/FVOCI/AC)
11.6 THE G1-8~G1-10 SHALL 各自底部审计结论textarea(AI)

### Requirement 12: G1-11~G1-14 检查与盘点

**User Story:** As a 审计助理, I want to 在精美HTML中执行证券监盘和凭证检查, so that 我能验证证券存在性和交易真实性。

#### Acceptance Criteria

12.1 THE G1-11有价证券监盘表 SHALL 显示41行×10列：序号|证券名称|代码|类型|账面数量|盘点数量|差异(公式)|差异原因|保管机构|监盘日期
12.2 THE Formula_Engine SHALL 计算盘点差异 = 盘点数量 - 账面数量
12.3 WHEN |差异|>0时, THE 系统 SHALL 以橙色高亮
12.4 THE G1-12盘点倒轧表 SHALL 显示23行×18列：证券名称|监盘日余额(数量/金额)|盘点日至报表日增加(数量/金额)|盘点日至报表日减少(数量/金额)|报表日推算余额(公式)|账面余额|差异(公式)|结论
12.5 THE Formula_Engine SHALL 计算推算余额 = 监盘日余额 + 增加 - 减少
12.6 THE Formula_Engine SHALL 计算倒轧差异 = 推算余额 - 账面余额
12.7 THE G1-13检查表 SHALL 显示48行×17列凭证核对，集成GtVoucherSamplingEngine抽凭引擎
12.8 WHEN 抽凭引擎返回样本时, THE 系统 SHALL 自动填入检查表行
12.9 THE G1-13检查表 SHALL 已抽凭行显示来源tooltip
12.10 THE G1-14衍生金融工具核查表 SHALL 显示45行×10列：序号|工具名称|类型(期权/期货/互换/远期)|名义金额|期限|对手方|保证金|是否套期|会计处理适当性(下拉)|合规结论
12.11 THE G1-11~G1-14 SHALL 各自支持动态行增删 + 导入导出 + 审计结论textarea(AI)
12.12 THE G1-12盘点倒轧表(18列) SHALL 拆为2区段Tab（监盘日数据/倒轧计算）

### Requirement 13: 公式引擎（G1专属）

**User Story:** As a 开发者, I want to 实现G1交易性金融资产公式引擎, so that 公允价值/损益/结存/盘点等公式可PBT验证。

#### Acceptance Criteria

13.1 THE Formula_Engine SHALL 实现 `calcDebitBalance`（借方余额 = 期初 + 借方 - 贷方）
13.2 THE Formula_Engine SHALL 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
13.3 THE Formula_Engine SHALL 实现 `calcFairValue`（公允价值 = 数量 × 单位公允值）
13.4 THE Formula_Engine SHALL 实现 `calcUnrealizedGain`（未实现损益 = 公允价值 - 成本）
13.5 THE Formula_Engine SHALL 实现 `calcRealizedGain`（已实现损益 = 处置收入 - 成本）
13.6 THE Formula_Engine SHALL 实现 `calcNetGain`（净损益 = 已实现损益 - 手续费）
13.7 THE Formula_Engine SHALL 实现 `calcLevel1Diff`（Level1差异 = 持仓×报价 - 账面值）
13.8 THE Formula_Engine SHALL 实现 `calcCountDiff`（盘点差异 = 盘点数量 - 账面数量）
13.9 THE Formula_Engine SHALL 实现 `calcReconciliation`（倒轧余额 = 监盘日余额 + 增加 - 减少）
13.10 THE Formula_Engine SHALL 实现 `calcClosingQuantity`（期末数量 = 期初 + 买入 - 卖出）
13.11 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced`（借贷平衡校验）
13.12 THE Formula_Engine SHALL 实现 `calcFairValueChange`（公允变动 = 期末公允 - 期初公允）

### Requirement 14: 跨模块联动（6大集成）

**User Story:** As a 开发者, I want to G1底稿集成6大跨模块联动, so that 版本链/抽凭/附注/OCR/复核全部可用。

#### Acceptance Criteria

14.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
14.2 THE 抽凭引擎 SHALL 在G1-13检查表集成GtVoucherSamplingEngine（dialog→样本填入）
14.3 THE 附注EventBus SHALL subscribe `substantive:adjudicated` 刷新 + publish `disclosure:note-text-updated`
14.4 THE 行级OCR SHALL 在G1-13检查表📎列POST contract-ocr→识别凭证信息→确认merge
14.5 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮
14.6 THE G1底稿 SHALL 不适用截止自动提取（投资科目无截止测试需求）

### Requirement 15: 导入导出与AI

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

15.1 THE Import_Export SHALL 对动态行表格支持导入导出：G1-2明细表/G1-3调整/G1-4结存/G1-5收益/G1-6公允价值/G1-7调节/G1-11监盘/G1-12倒轧/G1-13检查/G1-14衍生（共10张）
15.2 THE Import_Export SHALL 使用useG1ImportExport composable（后端三端点）
15.3 THE AI_Assistant SHALL 提供8个section：adjudication-summary/fair-value-conclusion/sppi-analysis/business-model-conclusion/counting-conclusion/voucher-check-conclusion/derivative-conclusion/overall-opinion
15.4 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 16: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且超长附注和大表流畅, so that 所有表格操作体验一致。

#### Acceptance Criteria

16.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
16.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
16.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
16.4 THE UI SHALL 编制提示details折叠底部
16.5 THE Performance SHALL 对行数>50的表启用虚拟滚动（附注(上市)198行/G1-10合同80行）
16.6 THE Performance SHALL defineAsyncComponent懒加载所有子组件

## Correctness Properties

> 以下性质将通过Property-Based Testing验证G1公式引擎的正确性。

**P1: 借方余额公式** — ∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit

**P2: 公允价值计算** — ∀ quantity ∈ ℤ≥0, unitFV ∈ ℝ≥0: calcFairValue(quantity, unitFV) === quantity × unitFV

**P3: 未实现损益公式** — ∀ fairValue, cost ∈ ℝ≥0: calcUnrealizedGain(fairValue, cost) === fairValue - cost

**P4: 已实现损益公式** — ∀ proceeds, cost ∈ ℝ≥0: calcRealizedGain(proceeds, cost) === proceeds - cost

**P5: Level1差异公式** — ∀ qty ∈ ℤ≥0, quote, bookValue ∈ ℝ≥0: calcLevel1Diff(qty, quote, bookValue) === qty×quote - bookValue

**P6: 盘点差异公式** — ∀ counted, booked ∈ ℤ: calcCountDiff(counted, booked) === counted - booked

**P7: 倒轧余额公式** — ∀ countDay, increase, decrease ∈ ℝ≥0: calcReconciliation(countDay, increase, decrease) === countDay + increase - decrease

**P8: 期末数量公式** — ∀ opening, bought, sold ∈ ℤ≥0: calcClosingQuantity(opening, bought, sold) === opening + bought - sold

**P9: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)

**P10: 净损益=已实现-手续费** — ∀ realizedGain ∈ ℝ, fee ∈ ℝ≥0: calcNetGain(realizedGain, fee) === realizedGain - fee

**P11: 公允价值变动方向性** — ∀ endFV > startFV: calcFairValueChange(endFV, startFV) > 0

**P12: 审定数公式** — ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
