# Requirements Document

## Introduction

G2应收利息底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g2-interest-receivable`，覆盖1个xlsx源模板(97KB)/10个有效sheet。科目1132应收利息（借方/资产类）。中等复杂度。

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **G2A 实质性程序表** | 29R×13C | a-program-console |
| 2 | **G2-1 审定表** | 41R×11C | 标准审定表(期初/期末) |
| 3 | **附注披露(上市)** | 29R×16C | 上市公司附注格式 |
| 4 | **附注披露(国企)** | 39R×5C | 国企附注格式 |
| 5 | **G2-2 明细表** | 32R×16C | 按投资标的×利率×应收利息 |
| 6 | **G2-3 坏账准备明细** | 28R×20C | ECL减值 |
| 7 | **G2-4 调整分录** | 22R×10C | AJE/RJE |
| 8 | **G2-5 利息测算表** | 19R×11C | **特色**：面值×利率×天数/365 |
| 9 | **G2-6 长期未收回检查** | 25R×13C | 逾期检查 |
| 10 | **G2-7 坏账准备测算** | 72R×18C | ECL三阶段测算 |
| 11 | **G2-8 凭证检查表** | 103R×21C | 大表，借方贷方检查 |

**宽表处理策略**：
- G2-7坏账准备测算(18列)：拆为2区段Tab（阶段划分/ECL测算）
- G2-8凭证检查表(21列)：借方/贷方独立区块（类似F3-7）

**借方科目公式**（资产类）：
- 期末未审 = 期初审定 + 借方发生额 - 贷方发生额

核心特色：利息测算(面值×票面利率×天数/365)、ECL三阶段减值测算、长期未收回风险评估。EventBus联动：publish substantive:adjudicated(accountCode='1132')。

## Glossary

- **Interest_Receivable**: 应收利息，因债权投资/其他债权投资等确认的应收未收利息
- **Face_Value**: 面值/本金，计算利息的基数
- **Coupon_Rate**: 票面利率，债券/存款约定的年利率
- **Accrued_Days**: 计息天数，本计息期内的实际天数
- **ECL_Three_Stage**: ECL三阶段模型：Stage1(12个月ECL)/Stage2(整个存续期ECL,未减值)/Stage3(整个存续期ECL,已减值)
- **Long_Overdue**: 长期未收回，超过约定期限未收回的应收利息
- **Adjudication_Table**: 审定表(G2-1)，期初/期末审定额汇总
- **Debit_Direction**: 借方科目，期末=期初+借方-贷方（资产类）

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G2应收利息底稿按sheetName prop分发到独立子组件, so that 10个有效sheet通过统一入口有序组织。

#### Acceptance Criteria

1.1 THE G2-Interest-Receivable 组件 SHALL 注册新componentType: `g2-interest-receivable`，主入口为 GtG2InterestReceivable.vue（接收sheetName prop，v-if分发，未迁移sheet走OnlyOffice fallback）
1.2 THE G2-Interest-Receivable 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（10个sheet按需加载）
1.3 THE G2-Interest-Receivable 组件 SHALL 在htmlRendererRegistry中注册'g2-interest-receivable'→GtG2InterestReceivable映射
1.4 THE G2-Interest-Receivable 组件 SHALL 在wp_code_overrides.json中将G2A/G2-1~G2-8/附注披露(上市)/附注披露(国企)的componentType统一映射为'g2-interest-receivable'（11个wp_code条目）
1.5 THE G2-Interest-Receivable 组件 SHALL 在VALID_COMPONENT_TYPES中注册'g2-interest-receivable'
1.6 THE GtG2InterestReceivable.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=g2-interest-receivable）
1.7 THE GtG2InterestReceivable.vue SHALL 用正则从sheetName提取编码(G2A/G2-1~G2-8/附注)，匹配失败走OnlyOffice fallback
1.8 THE G2-Interest-Receivable 组件 SHALL 采用el-tabs模式组织10个tab

### Requirement 2: G2A 实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中查看和执行应收利息实质性程序, so that 我能按步骤完成审计程序。

#### Acceptance Criteria

2.1 THE G2A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE G2A程序表 SHALL 显示29行×13列的审计程序步骤（含auto_data_source自动取数）
2.3 THE G2A程序表 SHALL 支持执行人/执行日期/结论/索引字段编辑

### Requirement 3: G2-1 审定表（借方科目）

**User Story:** As a 审计助理, I want to 在精美HTML中填写应收利息审定表, so that 我能汇总期初/期末审定数并回写试算表。

#### Acceptance Criteria

3.1 THE G2-1审定表 SHALL 显示41行×11列，列结构：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|索引
3.2 THE G2-1审定表 SHALL 行结构：按投资标的（债权投资利息/其他债权投资利息/定期存款利息/其他）+合计+试算表数+差异
3.3 THE G2-1审定表 SHALL 实现借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
3.4 THE G2-1审定表 SHALL 实现审定数公式：审定 = 未审 + AJE + RJE
3.5 THE G2-1审定表 SHALL 合计行自动汇总
3.6 THE G2-1审定表 SHALL 试算表数从trial_balance自动取数（科目1132）
3.7 THE G2-1审定表 SHALL 差异=审定-试算表数，差异≠0时红色高亮
3.8 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='1132', adjudicatedAmount=审定数）
3.9 THE G2-1审定表 SHALL 支持GtIndexChip索引列跳转

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 在精美HTML中编辑应收利息附注披露, so that 我能按格式生成附注文本。

#### Acceptance Criteria

4.1 THE 附注披露(上市) SHALL 显示29行×16列结构化表格
4.2 THE 附注披露(国企) SHALL 显示39行×5列结构化表格
4.3 THE 附注披露 SHALL 监听EventBus `substantive:adjudicated`(accountCode='1132')自动刷新
4.4 THE 附注披露 SHALL 通过EventBus发布 `disclosure:note-text-updated` 联动附注模块

### Requirement 5: G2-2 明细表

**User Story:** As a 审计助理, I want to 在精美HTML中查看应收利息逐笔明细, so that 我能检查每笔投资对应的利息计提。

#### Acceptance Criteria

5.1 THE G2-2明细表 SHALL 显示32行×16列：序号|投资标的|投资类型|面值/本金|票面利率(%)|计息起始日|计息截止日|计息天数(公式)|应计利息(公式)|已收利息|期末应收(公式)|企业账面值|差异(公式)|减值阶段|备注|索引
5.2 THE Formula_Engine SHALL 计算计息天数 = 计息截止日 - 计息起始日
5.3 THE Formula_Engine SHALL 计算应计利息 = 面值 × 票面利率/100 × 计息天数/365
5.4 THE Formula_Engine SHALL 计算期末应收 = 应计利息 - 已收利息
5.5 THE Formula_Engine SHALL 计算差异 = 期末应收 - 企业账面值
5.6 WHEN |差异|>100元时, THE 系统 SHALL 以橙色高亮
5.7 THE G2-2明细表 SHALL 底部合计行（面值合计/应计利息合计/期末应收合计/差异合计）
5.8 THE G2-2明细表 SHALL 支持动态行增删 + 导入导出

### Requirement 6: G2-3 坏账准备明细

**User Story:** As a 审计助理, I want to 在精美HTML中查看应收利息减值明细, so that 我能按ECL要求检查减值计提。

#### Acceptance Criteria

6.1 THE G2-3坏账准备明细 SHALL 显示28行×20列：序号|投资标的|期末应收余额|减值阶段(Stage1/2/3)|阶段转移方向|12个月PD|整个存续期PD|LGD|EAD|ECL金额(公式)|企业计提|差异(公式)|上期ECL|本期变动(公式)|转入金额|转出金额|核销|收回|备注|索引
6.2 THE Formula_Engine SHALL 计算ECL金额 = EAD × PD × LGD（Stage1用12个月PD，Stage2/3用整个存续期PD）
6.3 THE Formula_Engine SHALL 计算差异 = ECL金额 - 企业计提
6.4 THE Formula_Engine SHALL 计算本期变动 = 期末ECL - 上期ECL
6.5 THE G2-3坏账准备明细 SHALL 阶段下拉(Stage1/Stage2/Stage3) + 转移方向下拉(无变化/1→2/2→3/2→1/3→2)
6.6 THE G2-3坏账准备明细 SHALL 底部合计+审计结论textarea(AI)
6.7 THE G2-3坏账准备明细 SHALL 支持动态行增删 + 导入导出

### Requirement 7: G2-4 调整分录

**User Story:** As a 审计助理, I want to 在精美HTML中录入应收利息调整分录, so that 记录AJE/RJE。

#### Acceptance Criteria

7.1 THE G2-4调整分录 SHALL 显示22行×10列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
7.2 THE G2-4调整分录 SHALL 借贷平衡校验
7.3 WHEN 借贷不平衡时, THE 系统 SHALL 以红色高亮并显示差额
7.4 THE G2-4调整分录 SHALL 支持动态行增删 + 导入导出

### Requirement 8: G2-5 利息测算表

**User Story:** As a 审计助理, I want to 在精美HTML中测算应收利息, so that 我能验证企业利息计提的正确性。

#### Acceptance Criteria

8.1 THE G2-5利息测算表 SHALL 显示19行×11列：序号|投资标的|面值/本金|票面利率(%)|计息起始日|计息截止日|计息天数(公式)|应收利息(公式)|企业计提|差异(公式)|备注
8.2 THE Formula_Engine SHALL 计算计息天数 = 计息截止日 - 计息起始日
8.3 THE Formula_Engine SHALL 计算应收利息 = 面值 × 票面利率/100 × 计息天数/365
8.4 THE Formula_Engine SHALL 计算差异 = 应收利息 - 企业计提
8.5 WHEN |差异|>100元时, THE 系统 SHALL 以橙色高亮
8.6 THE G2-5利息测算表 SHALL 底部合计（面值合计/应收利息合计/企业计提合计/差异合计）
8.7 THE G2-5利息测算表 SHALL 审计结论textarea(AI辅助) + 编制提示details折叠
8.8 THE G2-5利息测算表 SHALL 支持动态行增删 + 导入导出

### Requirement 9: G2-6 长期未收回检查

**User Story:** As a 审计助理, I want to 在精美HTML中检查长期未收回的应收利息, so that 我能评估收回风险并提出审计建议。

#### Acceptance Criteria

9.1 THE G2-6长期未收回检查 SHALL 显示25行×13列：序号|投资标的|应收金额|约定收回日|逾期天数(公式)|逾期原因|债务方信用状况|催收措施|预计可收回性(下拉)|是否需转Stage2/3|风险等级(下拉)|审计建议|备注
9.2 THE Formula_Engine SHALL 计算逾期天数 = MAX(0, 当前日期 - 约定收回日)
9.3 WHEN 逾期天数>180时, THE 系统 SHALL 以红色高亮并建议转Stage3
9.4 WHEN 逾期天数>90且≤180时, THE 系统 SHALL 以橙色高亮并建议转Stage2
9.5 THE G2-6 SHALL 预计可收回性下拉：全额可收回/部分可收回/很可能无法收回/无法收回
9.6 THE G2-6 SHALL 风险等级下拉：低/中/高/极高
9.7 THE G2-6 SHALL 底部汇总（逾期笔数/逾期总金额/高风险笔数）+ 审计结论textarea(AI)
9.8 THE G2-6 SHALL 支持动态行增删 + 导入导出

### Requirement 10: G2-7 坏账准备测算（72行×18列→2区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中测算ECL三阶段坏账准备, so that 我能验证企业减值计提的充分性。

#### Acceptance Criteria

10.1 THE G2-7坏账准备测算 SHALL 显示72行×18列，拆为2区段Tab：
   - **阶段划分(9列)**：序号|投资标的|期末余额|信用风险等级|是否信用风险显著增加|是否已发生减值|划分阶段(公式)|上期阶段|阶段变动说明
   - **ECL测算(9列)**：12个月PD|整个存续期PD|适用PD(公式)|LGD|EAD|ECL金额(公式)|企业计提|差异(公式)|测算结论
10.2 THE Formula_Engine SHALL 划分阶段逻辑：已减值→Stage3；信用风险显著增加→Stage2；否则→Stage1
10.3 THE Formula_Engine SHALL 适用PD = Stage1用12个月PD / Stage2/3用整个存续期PD
10.4 THE Formula_Engine SHALL ECL金额 = EAD × 适用PD × LGD
10.5 THE Formula_Engine SHALL 差异 = ECL金额 - 企业计提
10.6 WHEN |差异|/企业计提>10%时, THE 系统 SHALL 以橙色高亮
10.7 THE G2-7坏账准备测算 SHALL 区段间行同步 + 底部合计
10.8 THE G2-7坏账准备测算 SHALL 审计结论textarea(AI) + 编制提示details
10.9 THE G2-7坏账准备测算 SHALL 支持动态行增删 + 导入导出
10.10 THE G2-7坏账准备测算 SHALL 虚拟滚动（72行大表）

### Requirement 11: G2-8 凭证检查表（103行×21列→借方/贷方区块）

**User Story:** As a 审计助理, I want to 在精美HTML中执行应收利息借方贷方检查, so that 我能逐笔抽查利息增减的凭证支持。

#### Acceptance Criteria

11.1 THE G2-8检查表 SHALL 分为两个独立区块：借方检查区(增加/利息确认) + 贷方检查区(减少/收回)
11.2 THE 借方检查区 SHALL 显示：序号|摘要|对方科目|金额|凭证日期|凭证编号|投资标的|面值|利率|计息天数|测算利息(公式)|差异|审计结论|备注
11.3 THE 贷方检查区 SHALL 显示：序号|摘要|对方科目|金额|凭证日期|凭证编号|收款银行|收款日期|是否到期收回|逾期天数|审计结论|备注
11.4 THE Formula_Engine SHALL 借方区测算利息 = 面值 × 利率/100 × 计息天数/365
11.5 THE G2-8检查表 SHALL 借方区+贷方区各自独立动态行增删
11.6 THE G2-8检查表 SHALL 各区底部小计（金额合计/异常笔数）
11.7 THE G2-8检查表 SHALL 集成GtVoucherSamplingEngine抽凭引擎（dialog模式，预填科目1132）
11.8 WHEN 抽凭引擎返回样本时, THE 系统 SHALL 自动填入借方/贷方检查区行（根据借贷方向分配）
11.9 THE G2-8检查表 SHALL 已抽凭行显示来源tooltip"来自抽凭引擎 {algorithm}"
11.10 THE G2-8检查表 SHALL 支持导入导出 + 审计结论textarea(AI)
11.11 THE G2-8检查表 SHALL 虚拟滚动（103行大表）

### Requirement 12: 公式引擎（G2专属）

**User Story:** As a 开发者, I want to 实现G2应收利息公式引擎, so that 利息测算/ECL/逾期等公式可PBT验证。

#### Acceptance Criteria

12.1 THE Formula_Engine SHALL 实现 `calcInterest365`（应收利息 = 面值 × 利率/100 × 天数/365）
12.2 THE Formula_Engine SHALL 实现 `calcAccruedDays`（计息天数 = 截止日 - 起始日，天数）
12.3 THE Formula_Engine SHALL 实现 `calcDebitBalance`（借方余额 = 期初 + 借方 - 贷方）
12.4 THE Formula_Engine SHALL 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
12.5 THE Formula_Engine SHALL 实现 `calcECL`（ECL = EAD × PD × LGD）
12.6 THE Formula_Engine SHALL 实现 `calcOverdueDays`（逾期天数 = MAX(0, 当前日期 - 约定日)）
12.7 THE Formula_Engine SHALL 实现 `determineStage`（阶段判定：已减值→3/显著增加→2/否则→1）
12.8 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced`（借贷平衡校验）
12.9 THE Formula_Engine SHALL 实现 `calcNetReceivable`（期末应收 = 应计利息 - 已收利息）
12.10 THE Formula_Engine SHALL 实现 `calcECLVariance`（ECL差异 = 测算ECL - 企业计提）

### Requirement 13: 跨模块联动（6大集成）

**User Story:** As a 开发者, I want to G2底稿集成6大跨模块联动, so that 版本链/抽凭/附注/OCR/复核全部可用。

#### Acceptance Criteria

13.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
13.2 THE 抽凭引擎 SHALL 在G2-8检查表集成GtVoucherSamplingEngine（dialog→样本填入借方/贷方区）
13.3 THE 附注EventBus SHALL subscribe `substantive:adjudicated` 刷新 + publish `disclosure:note-text-updated`
13.4 THE 行级OCR SHALL 在G2-8检查表📎列POST contract-ocr→识别凭证信息→确认merge
13.5 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮
13.6 THE G2底稿 SHALL 不适用截止自动提取（应收利息无截止测试需求）

### Requirement 14: 导入导出与AI

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

14.1 THE Import_Export SHALL 对动态行表格支持导入导出：G2-2明细/G2-3坏账明细/G2-4调整/G2-5利息测算/G2-6长期未收回/G2-7坏账测算/G2-8检查表（共7张）
14.2 THE Import_Export SHALL 使用useG2ImportExport composable（后端三端点）
14.3 THE AI_Assistant SHALL 提供5个section：interest-calc-conclusion/ecl-conclusion/overdue-evaluation/voucher-check-conclusion/overall-opinion
14.4 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 15: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且103行检查表流畅, so that 所有表格操作体验一致。

#### Acceptance Criteria

15.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
15.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
15.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
15.4 THE UI SHALL 编制提示details折叠底部
15.5 THE Performance SHALL 对行数>50的表启用虚拟滚动（G2-7坏账测算72行/G2-8检查表103行）
15.6 THE Performance SHALL defineAsyncComponent懒加载所有子组件

## Correctness Properties

> 以下性质将通过Property-Based Testing验证G2公式引擎的正确性。

**P1: 利息测算公式(365天基准)** — ∀ principal ∈ ℝ≥0, rate ∈ [0,100], days ∈ ℤ≥0: calcInterest365(principal, rate, days) === principal × rate/100 × days/365

**P2: 借方余额公式** — ∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit

**P3: 审定数公式** — ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje

**P4: ECL公式** — ∀ EAD ∈ ℝ≥0, PD ∈ [0,1], LGD ∈ [0,1]: calcECL(EAD, PD, LGD) === EAD × PD × LGD

**P5: 逾期天数非负** — ∀ currentDate, dueDate: calcOverdueDays(currentDate, dueDate) ≥ 0

**P6: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)

**P7: 利息与面值正比** — ∀ p1, p2 ∈ ℝ≥0, p2≠0, rate, days固定: calcInterest365(p1, rate, days) / calcInterest365(p2, rate, days) === p1/p2

**P8: ECL与EAD正比** — ∀ e1, e2 ∈ ℝ>0, PD, LGD固定: calcECL(e1, PD, LGD) / calcECL(e2, PD, LGD) === e1/e2

**P9: 阶段判定确定性** — ∀ impaired ∈ bool, significantIncrease ∈ bool: determineStage(impaired, significantIncrease) ∈ {1, 2, 3} 且 impaired=true → Stage3

**P10: 净应收=应计-已收** — ∀ accrued ∈ ℝ≥0, received ∈ ℝ≥0: calcNetReceivable(accrued, received) === accrued - received
