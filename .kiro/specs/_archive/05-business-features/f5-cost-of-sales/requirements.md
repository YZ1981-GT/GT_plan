# Requirements Document

## Introduction

F5营业成本底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `f5-cost-of-sales`，覆盖1个xlsx源模板(183KB)/9个有效sheet。科目6401营业成本（借方/损益类）。

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **F5A 营业成本实质性程序表** | 31R×13C | a-program-console |
| 2 | **F5-1 审定表** | 60R×14C | 本期+上期对比（损益类） |
| 3 | **F5-2 主营业务成本月度明细** | 30R×24C | **24列宽表！**品种×12个月 |
| 4 | **F5-3 其他业务成本明细** | 37R×14C | 其他业务成本明细 |
| 5 | **F5-4 调整分录** | 22R×10C | AJE/RJE |
| 6 | **F5-5 与上年度比较分析表** | 30R×17C | 品种×本期/上期/变动/率+毛利率 |
| 7 | **F5-6 销售数量与结转成本数量核对** | 81R×16C | **特色**：数量核对差异分析 |
| 8 | **F5-7 成本倒轧表** | 36R×11C | **特色**：期初+购入-期末-其他=投入+制造=成本 |
| 9 | **F5-8 重大调整核查表** | 40R×8C | 重大成本调整核查 |

**宽表处理策略**：
- F5-2主营业务成本月度明细(24列)：拆为2区段Tab（上半年1-6月+合计 / 下半年7-12月+合计+上期合计）

**损益类公式**（与资产负债类不同）：
- 审定 = 未审 + AJE + RJE（无"期初期末"概念，只有"本期"和"上期"对比）
- 变动 = 本期审定 - 上期审定

核心特色：F5-7成本倒轧表（期初材料+购入-期末-其他发出=投入生产+制造费+完工转出=本期成本，结构化审计逻辑验证）、F5-6销售数量与结转成本数量核对（数量一致性验证）、月度成本波动分析。EventBus联动：publish substantive:adjudicated(accountCode='6401')。

## Glossary

- **Cost_of_Sales**: 营业成本 = 主营业务成本 + 其他业务成本
- **Main_Business_Cost**: 主营业务成本，按产品品种分类
- **Other_Business_Cost**: 其他业务成本，非主营业务发生的成本
- **Income_Statement_Account**: 损益类科目，无"期初期末"概念，只有本期发生额与上期对比
- **Cost_Rollforward**: 成本倒轧表，验证成本构成逻辑：期初+购入-期末-其他=投入+制造=成本
- **Quantity_Reconciliation**: 销售数量与结转成本数量核对，验证数量一致性
- **Monthly_Detail**: 月度明细，按品种×12个月展示成本分布
- **Gross_Margin**: 毛利率 = (收入-成本)/收入 × 100%
- **Major_Adjustment**: 重大调整，超过重要性水平的成本调整事项
- **Period_Comparison**: 本期/上期对比，损益类科目的基本分析维度

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to F5营业成本底稿按sheetName prop分发到独立子组件, so that 9个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE F5-Cost-of-Sales 组件 SHALL 注册新componentType: `f5-cost-of-sales`，主入口为 GtF5CostOfSales.vue（接收sheetName prop，v-if分发到子组件，未迁移sheet走OnlyOffice fallback）
1.2 THE F5-Cost-of-Sales 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（9个sheet按需加载）
1.3 THE F5-Cost-of-Sales 组件 SHALL 在htmlRendererRegistry中注册'f5-cost-of-sales'→GtF5CostOfSales映射
1.4 THE F5-Cost-of-Sales 组件 SHALL 在wp_code_overrides.json中将F5A/F5-1~F5-8的componentType统一映射为'f5-cost-of-sales'（9个wp_code条目）
1.5 THE F5-Cost-of-Sales 组件 SHALL 在VALID_COMPONENT_TYPES中注册'f5-cost-of-sales'
1.6 THE GtF5CostOfSales.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=f5-cost-of-sales）
1.7 THE GtF5CostOfSales.vue SHALL 用正则从sheetName提取编码(F5A/F5-1~F5-8)，匹配失败走OnlyOffice fallback
1.8 THE F5-Cost-of-Sales 组件 SHALL 采用el-tabs模式组织9个tab

### Requirement 2: F5A 营业成本实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中查看和执行营业成本实质性程序, so that 我能按步骤完成审计程序并记录执行情况。

#### Acceptance Criteria

2.1 THE F5A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE F5A程序表 SHALL 显示31行×13列的审计程序步骤（含auto_data_source自动取数）
2.3 THE F5A程序表 SHALL 支持执行人/执行日期/结论/索引字段编辑

### Requirement 3: F5-1 审定表（损益类：本期+上期对比）

**User Story:** As a 审计助理, I want to 在精美HTML中填写营业成本审定表, so that 我能汇总本期/上期的未审数、调整数及审定数。

#### Acceptance Criteria

3.1 THE F5-1审定表 SHALL 显示60行×14列，列结构：项目|本期(未审/账项调整/重分类/审定)|上期(同)|索引
3.2 THE F5-1审定表 SHALL 行结构：主营业务成本(品种1~N)/小计 + 其他业务成本(品种1~N)/小计 + 总计/试算表数/差异
3.3 THE F5-1审定表 SHALL 实现损益类公式：审定 = 未审 + 账项调整 + 重分类（无期初期末概念）
3.4 THE F5-1审定表 SHALL 主营小计=各品种SUM；其他小计=各品种SUM；总计=主营小计+其他小计
3.5 THE F5-1审定表 SHALL 试算表数从trial_balance自动取数（科目6401发生额）
3.6 THE F5-1审定表 SHALL 差异=审定-试算表数，差异≠0时红色高亮
3.7 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='6401', adjudicatedAmount=审定数）
3.8 THE F5-1审定表 SHALL 支持动态品种行增删（主营/其他各自独立增删）
3.9 THE F5-1审定表 SHALL 支持GtIndexChip索引列跳转

### Requirement 4: F5-2 主营业务成本月度明细（24列→2区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中查看各品种12个月的成本分布, so that 我能分析月度成本波动并发现异常。

#### Acceptance Criteria

4.1 THE F5-2月度明细 SHALL 拆为2区段Tab：
   - **上半年(13列)**：品种|1月|2月|3月|4月|5月|6月|上半年合计(公式)|上半年占比(公式)|上半年月均(公式)|上半年最高月|上半年最低月|波动系数(公式)
   - **下半年+合计(11列)**：7月|8月|9月|10月|11月|12月|下半年合计(公式)|全年合计(公式)|上期合计|变动额(公式)|变动率(公式)
4.2 THE Formula_Engine SHALL 计算上半年合计 = 1月+2月+...+6月
4.3 THE Formula_Engine SHALL 计算下半年合计 = 7月+8月+...+12月
4.4 THE Formula_Engine SHALL 计算全年合计 = 上半年合计 + 下半年合计
4.5 THE Formula_Engine SHALL 计算变动额 = 全年合计 - 上期合计
4.6 THE Formula_Engine SHALL 计算变动率 = 变动额 / 上期合计 × 100%
4.7 THE Formula_Engine SHALL 计算波动系数 = 标准差(月度数据) / 均值(月度数据)（衡量月度波动程度）
4.8 WHEN 变动率绝对值>20%时, THE 系统 SHALL 以橙色高亮该品种行
4.9 WHEN 波动系数>0.5时, THE 系统 SHALL 以橙色高亮提示月度波动异常
4.10 THE F5-2月度明细 SHALL 区段间保持行同步
4.11 THE F5-2月度明细 SHALL 底部合计行（各月合计/上半年/下半年/全年/上期）
4.12 THE F5-2月度明细 SHALL 支持动态品种行增删 + 导入导出

### Requirement 5: F5-3 其他业务成本明细

**User Story:** As a 审计助理, I want to 在精美HTML中查看其他业务成本明细, so that 我能分析非主营成本构成。

#### Acceptance Criteria

5.1 THE F5-3其他业务成本 SHALL 显示37行×14列：序号|成本项目|本期金额|上期金额|变动额(公式)|变动率(公式)|成本构成占比(公式)|对应收入|成本率(公式)|收入确认时点|成本结转时点|配比合理性|审计评价|备注
5.2 THE Formula_Engine SHALL 计算变动额 = 本期 - 上期
5.3 THE Formula_Engine SHALL 计算变动率 = (本期-上期)/上期 × 100%
5.4 THE Formula_Engine SHALL 计算成本率 = 本期金额 / 对应收入 × 100%
5.5 WHEN 变动率绝对值>30%时, THE 系统 SHALL 以橙色高亮
5.6 THE F5-3其他业务成本 SHALL 底部合计 + 审计说明textarea(AI辅助)
5.7 THE F5-3其他业务成本 SHALL 支持动态行增删 + 导入导出

### Requirement 6: F5-4 调整分录

**User Story:** As a 审计助理, I want to 录入营业成本调整分录, so that 记录AJE/RJE。

#### Acceptance Criteria

6.1 THE F5-4调整分录 SHALL 显示22行×10列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
6.2 THE F5-4调整分录 SHALL 借贷平衡校验
6.3 WHEN 借贷不平衡时, THE 系统 SHALL 以红色高亮并显示差额
6.4 THE F5-4调整分录 SHALL 支持动态行增删 + 导入导出

### Requirement 7: F5-5 与上年度比较分析表

**User Story:** As a 审计助理, I want to 在精美HTML中比较本期与上期成本和毛利率, so that 我能发现异常变动并分析原因。

#### Acceptance Criteria

7.1 THE F5-5比较分析 SHALL 显示30行×17列：品种|本期收入|本期成本|本期毛利(公式)|本期毛利率(公式)|上期收入|上期成本|上期毛利(公式)|上期毛利率(公式)|收入变动额(公式)|收入变动率(公式)|成本变动额(公式)|成本变动率(公式)|毛利率变动(公式)|变动原因|审计评价|备注
7.2 THE Formula_Engine SHALL 计算毛利 = 收入 - 成本
7.3 THE Formula_Engine SHALL 计算毛利率 = 毛利 / 收入 × 100%
7.4 THE Formula_Engine SHALL 计算变动额 = 本期 - 上期（收入/成本各自）
7.5 THE Formula_Engine SHALL 计算毛利率变动 = 本期毛利率 - 上期毛利率（百分点）
7.6 WHEN 毛利率变动绝对值>5个百分点时, THE 系统 SHALL 以橙色高亮该品种行
7.7 WHEN 成本变动率与收入变动率偏差>10%时, THE 系统 SHALL 以橙色提示收入成本不匹配
7.8 THE F5-5比较分析 SHALL 底部合计行 + 审计结论textarea(AI辅助)
7.9 THE F5-5比较分析 SHALL 支持动态品种行增删 + 导入导出

### Requirement 8: F5-6 销售数量与结转成本数量核对

**User Story:** As a 审计助理, I want to 在精美HTML中核对销售数量与结转成本数量, so that 我能验证收入与成本在数量维度上的配比关系。

#### Acceptance Criteria

8.1 THE F5-6数量核对 SHALL 显示81行×16列：序号|品种|规格|计量单位|销售数量|结转成本数量|数量差异(公式)|差异率(公式)|差异原因分类(下拉)|期初库存|本期产量|本期采购|可供销售量(公式)|期末库存|理论结转量(公式)|理论差异(公式)
8.2 THE Formula_Engine SHALL 计算数量差异 = 销售数量 - 结转成本数量
8.3 THE Formula_Engine SHALL 计算差异率 = 数量差异 / 销售数量 × 100%
8.4 THE Formula_Engine SHALL 计算可供销售量 = 期初库存 + 本期产量 + 本期采购
8.5 THE Formula_Engine SHALL 计算理论结转量 = 可供销售量 - 期末库存
8.6 THE Formula_Engine SHALL 计算理论差异 = 理论结转量 - 结转成本数量
8.7 WHEN |差异率|>5%时, THE 系统 SHALL 以橙色高亮
8.8 WHEN |差异率|>10%时, THE 系统 SHALL 以红色高亮
8.9 THE F5-6数量核对 SHALL 差异原因分类下拉：正常损耗/生产废品/计量误差/品种替换/系统错误/其他
8.10 THE F5-6数量核对 SHALL 底部汇总（总销售量/总结转量/总差异/差异品种数/红色警告品种数）+ 审计说明textarea(AI辅助)
8.11 THE F5-6数量核对 SHALL 支持动态行增删 + 导入导出 + 虚拟滚动(81行)

### Requirement 9: F5-7 成本倒轧表

**User Story:** As a 审计助理, I want to 在精美HTML中验证成本倒轧逻辑, so that 我能确认期初材料+购入-期末-其他发出=投入生产+制造费+完工转出=本期营业成本。

#### Acceptance Criteria

9.1 THE F5-7成本倒轧表 SHALL 显示36行×11列，结构化只读/半编辑表：
   - **材料流转区**：期初原材料|+本期购入|−期末原材料|−其他发出|=投入生产(公式)
   - **成本构成区**：投入生产(来自上行)|+直接人工|+制造费用|=产品总成本(公式)
   - **成本结转区**：期初在产品|+产品总成本|−期末在产品|=完工产品成本(公式)
   - **营业成本区**：期初产成品|+完工产品成本|−期末产成品|−其他发出|=本期营业成本(公式)
   - **校验区**：审定表营业成本|与倒轧差异(公式)|结论
9.2 THE Formula_Engine SHALL 计算投入生产 = 期初原材料 + 本期购入 - 期末原材料 - 其他发出
9.3 THE Formula_Engine SHALL 计算产品总成本 = 投入生产 + 直接人工 + 制造费用
9.4 THE Formula_Engine SHALL 计算完工产品成本 = 期初在产品 + 产品总成本 - 期末在产品
9.5 THE Formula_Engine SHALL 计算本期营业成本 = 期初产成品 + 完工产品成本 - 期末产成品 - 其他发出
9.6 THE Formula_Engine SHALL 计算与倒轧差异 = 审定表营业成本(从F5-1取) - 本期营业成本(倒轧)
9.7 WHEN |与倒轧差异|>重要性水平时, THE 系统 SHALL 以红色高亮差异行
9.8 THE F5-7成本倒轧表 SHALL 从trial_balance自动取数（期初/期末原材料1401、在产品1404、产成品1405）
9.9 THE F5-7成本倒轧表 SHALL 审计结论textarea(AI辅助) + 编制提示details折叠
9.10 THE F5-7成本倒轧表 SHALL 可编辑字段：购入/直接人工/制造费用/其他发出（其余为公式或TB取数）

### Requirement 10: F5-8 重大调整核查表

**User Story:** As a 审计助理, I want to 在精美HTML中核查营业成本重大调整事项, so that 我能评估调整的合理性和依据充分性。

#### Acceptance Criteria

10.1 THE F5-8重大调整 SHALL 显示40行×8列：序号|调整日期|调整事项|调整金额|调整原因|审批依据|凭证编号|审计评价
10.2 WHEN 调整金额>重要性水平时, THE 系统 SHALL 以橙色高亮
10.3 THE F5-8重大调整 SHALL 底部汇总（调整笔数/调整总额/超重要性笔数）+ 审计结论textarea(AI辅助)
10.4 THE F5-8重大调整 SHALL 支持动态行增删 + 导入导出

### Requirement 11: 公式引擎（F5专属）

**User Story:** As a 开发者, I want to 实现F5营业成本公式引擎, so that 损益类审定/成本倒轧/毛利率等公式可PBT验证。

#### Acceptance Criteria

11.1 THE Formula_Engine SHALL 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE，损益类）
11.2 THE Formula_Engine SHALL 实现 `calcChangeAmount`（变动额 = 本期 - 上期）
11.3 THE Formula_Engine SHALL 实现 `calcChangeRate`（变动率 = (本期-上期)/上期 × 100%）
11.4 THE Formula_Engine SHALL 实现 `calcGrossMargin`（毛利率 = (收入-成本)/收入 × 100%）
11.5 THE Formula_Engine SHALL 实现 `calcCostRollforward`（成本倒轧 = 期初+购入-期末-其他）
11.6 THE Formula_Engine SHALL 实现 `calcTotalProductionCost`（产品总成本 = 投入+人工+制造费）
11.7 THE Formula_Engine SHALL 实现 `calcFinishedGoodsCost`（完工成本 = 期初在产+总成本-期末在产）
11.8 THE Formula_Engine SHALL 实现 `calcCOGS`（营业成本 = 期初产成品+完工-期末产成品-其他）
11.9 THE Formula_Engine SHALL 实现 `calcQuantityVariance`（数量差异 = 销售量 - 结转量）
11.10 THE Formula_Engine SHALL 实现 `calcVarianceRate`（差异率 = 差异/销售量 × 100%）
11.11 THE Formula_Engine SHALL 实现 `calcCoeffOfVariation`（波动系数 = 标准差/均值）
11.12 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced`（借贷平衡校验）

### Requirement 12: 跨模块联动（6大集成）

**User Story:** As a 开发者, I want to F5底稿集成6大跨模块联动, so that 版本链/抽凭/附注/OCR/复核/截止全部可用。

#### Acceptance Criteria

12.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
12.2 THE 抽凭引擎 SHALL 在F5-8重大调整核查表集成GtVoucherSamplingEngine（dialog→选取重大成本调整凭证）
12.3 THE 附注EventBus SHALL subscribe `substantive:adjudicated` 刷新 + publish `disclosure:note-text-updated`
12.4 THE 行级OCR SHALL 在F5-6数量核对📎列POST contract-ocr→识别出库单数量→ElMessageBox确认→merge
12.5 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮
12.6 THE F5底稿 SHALL 不适用截止自动提取（useCutoffAutoSampling仅适用于有截止测试的底稿，F5无截止需求）

### Requirement 13: 导入导出与AI

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

13.1 THE Import_Export SHALL 对动态行表格支持导入导出：F5-2月度明细/F5-3其他成本/F5-4调整/F5-5比较分析/F5-6数量核对/F5-8重大调整（共6张）
13.2 THE Import_Export SHALL 使用useF5ImportExport composable（后端三端点）
13.3 THE AI_Assistant SHALL 提供5个section：cost-analysis/comparison-conclusion/quantity-reconciliation/rollforward-evaluation/adjustment-evaluation
13.4 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 14: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且81行数量核对表流畅, so that 所有表格操作体验一致。

#### Acceptance Criteria

14.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
14.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
14.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
14.4 THE UI SHALL 编制提示details折叠底部
14.5 THE Performance SHALL 对行数>50的表启用虚拟滚动（F5-6数量核对81行/F5-1审定表60行）
14.6 THE Performance SHALL defineAsyncComponent懒加载所有子组件

## Correctness Properties

> 以下性质将通过Property-Based Testing验证F5公式引擎的正确性。

**P1: 损益类审定公式** — ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje

**P2: 成本倒轧恒等** — ∀ opening, purchase, closing, other ∈ ℝ≥0: calcCostRollforward(opening, purchase, closing, other) === opening + purchase - closing - other

**P3: 毛利率公式** — ∀ revenue ∈ ℝ>0, cost ∈ ℝ≥0: calcGrossMargin(revenue, cost) === (revenue-cost)/revenue × 100

**P4: 完工成本恒等** — ∀ wipOpening, totalCost, wipClosing ∈ ℝ≥0: calcFinishedGoodsCost(wipOpening, totalCost, wipClosing) === wipOpening + totalCost - wipClosing

**P5: 营业成本倒轧全链** — ∀ inputs: calcCOGS(fgOpening, calcFinishedGoodsCost(...), fgClosing, other) ≥ 0（非负约束，合理性）

**P6: 数量差异公式** — ∀ salesQty, costQty ∈ ℝ: calcQuantityVariance(salesQty, costQty) === salesQty - costQty

**P7: 变动率公式** — ∀ current, prior ∈ ℝ, prior≠0: calcChangeRate(current, prior) === (current-prior)/prior × 100

**P8: 波动系数非负** — ∀ values[] ∈ ℝ[] (all≥0): calcCoeffOfVariation(values) ≥ 0

**P9: 月度合计恒等** — ∀ months[12] ∈ ℝ: SUM(months[0..5]) + SUM(months[6..11]) === SUM(months[0..11])

**P10: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (SUM(debits) === SUM(credits))
