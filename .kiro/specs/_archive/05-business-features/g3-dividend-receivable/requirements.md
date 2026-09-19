# Requirements Document

## Introduction

G3应收股利底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g3-dividend-receivable`，覆盖1个xlsx源模板(469KB)/7个有效sheet。科目1131应收股利（借方/资产类）。相对简单。

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **G3A 实质性程序表** | 26R×13C | a-program-console |
| 2 | **G3-1 审定表** | 48R×22C | 按被投资方×持股比例×应收股利 |
| 3 | **附注披露(上市)** | 36R×6C | 上市公司附注格式 |
| 4 | **附注披露(国企)** | 29R×5C | 国企附注格式 |
| 5 | **G3-2 明细表** | 43R×33C | **33列宽表！**按被投资方×持股×分红方案×应收 |
| 6 | **G3-3 调整分录** | 25R×10C | AJE/RJE |
| 7 | **G3-4 测算及检查表** | 48R×18C | 股利测算+凭证检查(宣告日/权利日/分配比例) |
| 8 | **G3-5 长期未收回检查** | 28R×13C | 长期未收回风险 |

**宽表处理策略**：
- G3-2明细表(33列)：拆为4区段Tab（被投资方信息/持股明细/分红方案/应收核算）
- G3-4测算及检查表(18列)：拆为2区段Tab（股利测算/凭证检查）

**借方科目公式**（资产类）：
- 期末未审 = 期初审定 + 借方发生额 - 贷方发生额

核心特色：股利测算(持股数×每股股利)、33列明细宽表(被投资方×持股×分红×应收)、长期未收回评估、实际分红率分析。EventBus联动：publish substantive:adjudicated(accountCode='1131')。

## Glossary

- **Dividend_Receivable**: 应收股利，因权益性投资确认的应收未收现金股利
- **Investee**: 被投资方，发放股利的被投资企业
- **Shareholding_Ratio**: 持股比例，投资方持有被投资方的股权比例
- **DPS**: 每股股利(Dividend Per Share)，被投资方宣告的每股分配金额
- **Declaration_Date**: 宣告日，股东大会决议分红的日期
- **Record_Date**: 权利日/股权登记日，确认有权获得股利的日期
- **Payout_Ratio**: 实际分红率 = 实际分红总额 / 净利润 × 100%
- **Long_Overdue_Dividend**: 长期未收回股利，超过约定期限未收到的应收股利
- **Adjudication_Table**: 审定表(G3-1)，按被投资方分行的审定额汇总
- **Debit_Direction**: 借方科目，期末=期初+借方-贷方（资产类）

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G3应收股利底稿按sheetName prop分发到独立子组件, so that 7个有效sheet通过统一入口有序组织。

#### Acceptance Criteria

1.1 THE G3-Dividend-Receivable 组件 SHALL 注册新componentType: `g3-dividend-receivable`，主入口为 GtG3DividendReceivable.vue（接收sheetName prop，v-if分发，未迁移sheet走OnlyOffice fallback）
1.2 THE G3-Dividend-Receivable 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（7个sheet按需加载）
1.3 THE G3-Dividend-Receivable 组件 SHALL 在htmlRendererRegistry中注册'g3-dividend-receivable'→GtG3DividendReceivable映射
1.4 THE G3-Dividend-Receivable 组件 SHALL 在wp_code_overrides.json中将G3A/G3-1~G3-5/附注披露(上市)/附注披露(国企)的componentType统一映射为'g3-dividend-receivable'（8个wp_code条目）
1.5 THE G3-Dividend-Receivable 组件 SHALL 在VALID_COMPONENT_TYPES中注册'g3-dividend-receivable'
1.6 THE GtG3DividendReceivable.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=g3-dividend-receivable）
1.7 THE GtG3DividendReceivable.vue SHALL 用正则从sheetName提取编码(G3A/G3-1~G3-5/附注)，匹配失败走OnlyOffice fallback
1.8 THE G3-Dividend-Receivable 组件 SHALL 采用el-tabs模式组织7个tab

### Requirement 2: G3A 实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中查看和执行应收股利实质性程序, so that 我能按步骤完成审计程序。

#### Acceptance Criteria

2.1 THE G3A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE G3A程序表 SHALL 显示26行×13列的审计程序步骤（含auto_data_source自动取数）
2.3 THE G3A程序表 SHALL 支持执行人/执行日期/结论/索引字段编辑

### Requirement 3: G3-1 审定表（借方科目，按被投资方分行）

**User Story:** As a 审计助理, I want to 在精美HTML中填写应收股利审定表, so that 我能汇总各被投资方的审定数并回写试算表。

#### Acceptance Criteria

3.1 THE G3-1审定表 SHALL 显示48行×22列，列结构：被投资方|持股比例|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|本期宣告|本期收回|备注|索引 + 合计行
3.2 THE G3-1审定表 SHALL 行结构：按被投资方名称逐行（支持动态行增删）+ 合计 + 试算表数 + 差异
3.3 THE G3-1审定表 SHALL 实现借方科目公式：期末未审 = 期初审定 + 借方(本期宣告) - 贷方(本期收回)
3.4 THE G3-1审定表 SHALL 实现审定数公式：审定 = 未审 + AJE + RJE
3.5 THE G3-1审定表 SHALL 合计行自动汇总
3.6 THE G3-1审定表 SHALL 试算表数从trial_balance自动取数（科目1131）
3.7 THE G3-1审定表 SHALL 差异=审定-试算表数，差异≠0时红色高亮
3.8 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='1131', adjudicatedAmount=审定数）
3.9 THE G3-1审定表 SHALL 支持GtIndexChip索引列跳转
3.10 THE G3-1审定表 SHALL 支持动态行增删（新增被投资方时弹ElMessageBox.prompt输入名称）

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 在精美HTML中编辑应收股利附注披露, so that 我能按格式生成附注文本。

#### Acceptance Criteria

4.1 THE 附注披露(上市) SHALL 显示36行×6列结构化表格
4.2 THE 附注披露(国企) SHALL 显示29行×5列结构化表格
4.3 THE 附注披露 SHALL 监听EventBus `substantive:adjudicated`(accountCode='1131')自动刷新
4.4 THE 附注披露 SHALL 通过EventBus发布 `disclosure:note-text-updated` 联动附注模块

### Requirement 5: G3-2 明细表（33列宽表→4区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中查看应收股利逐笔明细, so that 我能检查每项投资对应的股利分配方案和应收情况。

#### Acceptance Criteria

5.1 THE G3-2明细表 SHALL 拆为4区段Tab：
   - **被投资方信息(8列)**：序号|被投资方名称|统一社会信用代码|注册资本|行业|投资类型(长期股权/其他权益工具)|初始投资成本|投资日期
   - **持股明细(9列)**：持股数量(股)|持股比例(%)|被投资方净利润|被投资方净资产|投资方权益份额(公式)|账面值(成本法/权益法)|核算方法|是否上市|上市代码
   - **分红方案(8列)**：股东大会决议日|分红方案描述|每股股利(元)|宣告日|股权登记日|除权日|分红总额(公式)|实际分红率(公式)
   - **应收核算(8列)**：应收股利(公式)|已收金额|期末应收(公式)|收款日期|收款方式|是否逾期|逾期天数(公式)|备注
5.2 THE Formula_Engine SHALL 计算投资方权益份额 = 被投资方净资产 × 持股比例/100
5.3 THE Formula_Engine SHALL 计算分红总额 = 持股数量 × 每股股利
5.4 THE Formula_Engine SHALL 计算实际分红率 = 分红总额 / 被投资方净利润 × 100%（净利润≤0→N/A）
5.5 THE Formula_Engine SHALL 计算应收股利 = 持股数量 × 每股股利（=分红总额）
5.6 THE Formula_Engine SHALL 计算期末应收 = 应收股利 - 已收金额
5.7 THE Formula_Engine SHALL 计算逾期天数 = MAX(0, 当前日期 - 股权登记日 - 约定付款期限)
5.8 WHEN 逾期天数>0时, THE 系统 SHALL 以橙色高亮该行
5.9 THE G3-2明细表 SHALL 区段间保持行同步
5.10 THE G3-2明细表 SHALL 底部合计行（投资成本合计/分红总额合计/应收合计/已收合计/期末应收合计）
5.11 THE G3-2明细表 SHALL 支持动态行增删 + 导入导出

### Requirement 6: G3-3 调整分录

**User Story:** As a 审计助理, I want to 在精美HTML中录入应收股利调整分录, so that 记录AJE/RJE。

#### Acceptance Criteria

6.1 THE G3-3调整分录 SHALL 显示25行×10列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
6.2 THE G3-3调整分录 SHALL 借贷平衡校验
6.3 WHEN 借贷不平衡时, THE 系统 SHALL 以红色高亮并显示差额
6.4 THE G3-3调整分录 SHALL 支持动态行增删 + 导入导出

### Requirement 7: G3-4 测算及检查表（18列→2区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中测算股利并检查凭证, so that 我能验证股利计算正确性和交易真实性。

#### Acceptance Criteria

7.1 THE G3-4测算及检查表 SHALL 显示48行×18列，拆为2区段Tab：
   - **股利测算(9列)**：序号|被投资方|持股数量|每股股利|应收股利(公式)|宣告日|权利日|分红文件编号|测算差异(公式)
   - **凭证检查(9列)**：凭证日期|凭证编号|摘要|对方科目|金额|收款银行|到账日期|核对结果|审计结论
7.2 THE Formula_Engine SHALL 计算应收股利 = 持股数量 × 每股股利
7.3 THE Formula_Engine SHALL 计算测算差异 = 应收股利(测算) - 企业入账金额
7.4 WHEN |测算差异|>100元时, THE 系统 SHALL 以橙色高亮
7.5 THE G3-4测算及检查表 SHALL 区段间行同步（同一被投资方的测算和检查在同一行）
7.6 THE G3-4测算及检查表 SHALL 底部合计 + 审计结论textarea(AI) + 编制提示details
7.7 THE G3-4测算及检查表 SHALL 支持动态行增删 + 导入导出
7.8 THE G3-4测算及检查表 SHALL 集成GtVoucherSamplingEngine抽凭引擎（dialog模式，科目1131）
7.9 WHEN 抽凭引擎返回样本时, THE 系统 SHALL 自动填入凭证检查区段
7.10 THE G3-4 SHALL 已抽凭行显示来源tooltip

### Requirement 8: G3-5 长期未收回检查

**User Story:** As a 审计助理, I want to 在精美HTML中检查长期未收回的应收股利, so that 我能评估收回风险并提出审计建议。

#### Acceptance Criteria

8.1 THE G3-5长期未收回检查 SHALL 显示28行×13列：序号|被投资方|应收金额|宣告日|约定付款日|逾期天数(公式)|逾期原因|被投资方经营状况|历史分红记录|预计可收回性(下拉)|风险等级(下拉)|审计建议|备注
8.2 THE Formula_Engine SHALL 计算逾期天数 = MAX(0, 当前日期 - 约定付款日)
8.3 WHEN 逾期天数>180时, THE 系统 SHALL 以红色高亮
8.4 WHEN 逾期天数>90且≤180时, THE 系统 SHALL 以橙色高亮
8.5 THE G3-5 SHALL 预计可收回性下拉：全额可收回/部分可收回/很可能无法收回/无法收回
8.6 THE G3-5 SHALL 风险等级下拉：低/中/高/极高
8.7 THE G3-5 SHALL 底部汇总（逾期笔数/逾期总金额/高风险笔数）+ 审计结论textarea(AI)
8.8 THE G3-5 SHALL 支持动态行增删 + 导入导出

### Requirement 9: 公式引擎（G3专属）

**User Story:** As a 开发者, I want to 实现G3应收股利公式引擎, so that 股利测算/逾期/分红率等公式可PBT验证。

#### Acceptance Criteria

9.1 THE Formula_Engine SHALL 实现 `calcDividend`（应收股利 = 持股数量 × 每股股利）
9.2 THE Formula_Engine SHALL 实现 `calcPayoutRatio`（实际分红率 = 分红总额 / 净利润 × 100%，净利润≤0→0）
9.3 THE Formula_Engine SHALL 实现 `calcDebitBalance`（借方余额 = 期初 + 借方 - 贷方）
9.4 THE Formula_Engine SHALL 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
9.5 THE Formula_Engine SHALL 实现 `calcOverdueDays`（逾期天数 = MAX(0, 当前日期 - 约定日)）
9.6 THE Formula_Engine SHALL 实现 `calcNetReceivable`（期末应收 = 应收股利 - 已收金额）
9.7 THE Formula_Engine SHALL 实现 `calcEquityShare`（权益份额 = 净资产 × 持股比例/100）
9.8 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced`（借贷平衡校验）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证G3公式引擎的正确性。

**P1: 股利测算公式** — ∀ shares ∈ ℤ≥0, dps ∈ ℝ≥0: calcDividend(shares, dps) === shares × dps

**P2: 借方余额公式** — ∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit

**P3: 审定数公式** — ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje

**P4: 逾期天数非负** — ∀ currentDate, dueDate: calcOverdueDays(currentDate, dueDate) ≥ 0

**P5: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)

**P6: 分红率与分红总额正比** — ∀ d1, d2 ∈ ℝ≥0, netProfit>0固定: calcPayoutRatio(d1, netProfit) / calcPayoutRatio(d2, netProfit) === d1/d2 (d2≠0)

**P7: 股利与持股数正比** — ∀ s1, s2 ∈ ℤ>0, dps固定: calcDividend(s1, dps) / calcDividend(s2, dps) === s1/s2

**P8: 净应收=应收-已收** — ∀ receivable ∈ ℝ≥0, received ∈ ℝ≥0: calcNetReceivable(receivable, received) === receivable - received

**P9: 权益份额公式** — ∀ netAssets ∈ ℝ, ratio ∈ [0,100]: calcEquityShare(netAssets, ratio) === netAssets × ratio/100

**P10: 分红率≥0（净利润>0时）** — ∀ dividendTotal ∈ ℝ≥0, netProfit ∈ ℝ>0: calcPayoutRatio(dividendTotal, netProfit) ≥ 0
