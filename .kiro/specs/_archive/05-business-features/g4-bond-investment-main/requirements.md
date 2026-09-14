# Requirements Document

## Introduction

G4债权投资底稿专属HTML精美组件构建（main组）。将现有通用渲染升级为独立专属组件 `g4-bond-investment-main`，覆盖1个xlsx源模板(1022KB)中的8个sheet。科目1501债权投资（借方/资产类）。**G循环中最复杂的科目之一**，源模板19个sheet按三组拆分，本spec覆盖主体部分。

**三组拆分方案**：
- **本spec (main)**: 程序表+审定表+附注+明细表+调整分录+利息测算（8个sheet）
- g4-bond-investment-sppi: 业务模式分析+SPPI+盘点（另一个spec）
- g4-bond-investment-ecl: 三阶段划分+减值测算+ECL+凭证检查（另一个spec）

**源模板sheet清单（本spec覆盖，openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 27×8 | 目录页 |
| 2 | 债权投资实质性程序表G4A | 41×10 | a-program-console |
| 3 | 审定表G4-1 | 46×11 | 债权投资原值+减值+摊余成本+一年内到期 |
| 4 | 附注披露信息（上市公司） | 130×11 | 上市公司附注格式 |
| 5 | 附注披露信息（国企） | 71×7 | 国企附注格式 |
| 6 | 明细表G4-2 | 44×44 | **44列超宽表！**按投资种类×摊余成本分解 |
| 7 | 调整分录汇总G4-3 | 22×10 | AJE/RJE标准格式 |
| 8 | 利息测算表G4-4 | 49×11 | 实际利率法利息收入测算 |

**宽表处理策略**：
- G4-2明细表(44列)：拆为5区段Tab（基础信息/期初余额/本期变动/期末余额+减值/摊余成本+审定）
- G4-4利息测算表：按(一)初始入账+(二)利息计算双section

**借方科目公式**（资产类）：
- 期末未审 = 期初审定 + 借方发生额 - 贷方发生额

**子目录组织**：
- core/: 审定表G4-1 + 明细表G4-2 + 调整分录G4-3 + 附注
- measurement/: 利息测算表G4-4

**六大集成联动**：
- ✅ 版本链(useVersionTrail): 主入口集成+autoSnapshot
- ✅ 抽凭引擎: G4A程序表集成GtVoucherSamplingEngine dialog
- ✅ 截止自动提取: useCutoffAutoSampling
- ✅ 附注EventBus: subscribe substantive:adjudicated / publish disclosure:note-text-updated
- ❌ 行级OCR: G4-2明细表不需要（非凭证表）
- ✅ 复核对话: provide openReviewDialog→section标题栏右侧按钮

## Glossary

- **Bond_Investment**: 债权投资，以摊余成本计量的金融资产（CAS22分类为AC类）
- **Amortized_Cost**: 摊余成本 = 初始入账金额 - 已收回本金 ± 累计摊销（利息调整）- 减值准备
- **Effective_Interest_Rate**: 实际利率，使金融资产预期未来现金流量的现值等于初始确认金额的利率
- **Interest_Adjustment**: 利息调整，债权投资面值与初始入账价值的差额，通过实际利率法在存续期内摊销
- **Accrued_Interest**: 应计利息，已计提但尚未收取的利息收入（= 面值 × 票面利率 × 计息天数/365）
- **Impairment_Provision**: 减值准备，预期信用损失(ECL)计提的资产减值
- **One_Year_Maturity**: 一年内到期非流动资产，到期日距资产负债表日不超过一年的债权投资部分（需重分类列报）
- **Adjudication_Table**: 审定表(G4-1)，三层结构：原值/减值/摊余成本，含一年内到期重分类
- **Detail_Table**: 明细表(G4-2)，44列超宽表，按投资种类×摊余成本分解(成本/利息调整/应计利息)
- **Interest_Calculation**: 利息测算表(G4-4)，实际利率法验证：利息收入 = 摊余成本 × 实际利率
- **Debit_Direction**: 借方科目，期末=期初+借方-贷方（资产类）
- **Stage_Classification**: ECL三阶段划分（Stage1/2/3），影响利息计算基数（另一spec覆盖）
- **G4_Main_Component**: g4-bond-investment-main专属组件，覆盖8个sheet的主体部分

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G4债权投资底稿(main组)按sheetName prop分发到独立子组件, so that 8个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE G4-Bond-Investment-Main 组件 SHALL 注册新componentType: `g4-bond-investment-main`，主入口为 GtG4BondInvestmentMain.vue（接收sheetName prop，v-if分发到子组件）
1.2 THE G4-Bond-Investment-Main 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（8个sheet：G4A、G4-1、G4-2、G4-3、G4-4、附注披露(上市)、附注披露(国企)、底稿目录，按需加载）
1.3 THE G4-Bond-Investment-Main 组件 SHALL 在htmlRendererRegistry中注册'g4-bond-investment-main'→GtG4BondInvestmentMain映射
1.4 THE G4-Bond-Investment-Main 组件 SHALL 在wp_code_overrides.json中将G4A、G4-1、G4-2、G4-3、G4-4、附注披露(上市)、附注披露(国企)、底稿目录的componentType统一映射为'g4-bond-investment-main'（8个wp_code条目）
1.5 THE G4-Bond-Investment-Main 组件 SHALL 在VALID_COMPONENT_TYPES中注册'g4-bond-investment-main'
1.6 IF htmlData prop为null, THEN THE GtG4BondInvestmentMain.vue SHALL 自行调用render-config?force_component_type=g4-bond-investment-main获取渲染数据（selfLoad模式）
1.7 IF sheetName正则提取编码失败或提取的编码不在已迁移子组件列表中, THEN THE GtG4BondInvestmentMain.vue SHALL 渲染OnlyOffice fallback组件
1.8 THE G4-Bond-Investment-Main 组件 SHALL 采用sheetName v-if dispatch模式（非el-tabs），通过正则从sheetName提取编码(G4A/G4-1/G4-2/G4-3/G4-4/附注披露(上市)/附注披露(国企)/底稿目录)分发到对应子组件
1.9 THE 子组件 SHALL 按子目录组织：core/(G4A+G4-1~G4-3+附注披露(上市)+附注披露(国企)+底稿目录) / measurement/(G4-4)

### Requirement 2: G4A 实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中查看和执行债权投资实质性程序, so that 我能按步骤完成审计程序并记录执行情况。

#### Acceptance Criteria

2.1 THE G4A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE G4A程序表 SHALL 显示41行×10列的审计程序步骤（含auto_data_source自动取数）
2.3 THE G4A程序表 SHALL 支持执行人/执行日期/结论/索引字段编辑
2.4 THE G4A程序表 SHALL 集成GtVoucherSamplingEngine抽凭引擎（dialog模式）

### Requirement 12: 底稿目录（索引跳转）

**User Story:** As a 审计助理, I want to 在精美HTML中查看G4底稿目录, so that 我能快速定位和跳转到各子底稿。

#### Acceptance Criteria

12.1 THE 底稿目录 SHALL 显示27行×8列，左侧为编制信息区（被审计单位/截止日/编制人/复核人），右侧为目录列表（序号/内容/索引号/备注）
12.2 THE 底稿目录 SHALL 目录列表中索引号列（G4A/G4-1~G4-13/G0-1~G0-8）渲染为GtIndexChip可点击跳转
12.3 THE 底稿目录 SHALL 左侧编制信息区包含"关于工作底稿与审计程序索引号对应的说明"文本（只读方法论上下文）
12.4 THE 底稿目录 SHALL 自动标记已完成/未完成的底稿状态（通过查询各sheet是否有数据来判断）

### Requirement 3: 审定表G4-1（三层结构，借方科目）

**User Story:** As a 审计助理, I want to 在精美HTML中填写债权投资审定表, so that 我能汇总原值/减值/摊余成本的审定数据并回写试算表。

#### Acceptance Criteria

3.1 THE G4-1审定表 SHALL 显示46行×11列三层结构，按数据分组：
   - **一、债权投资原值**：单项计提/按组合计提/小计/减：一年内到期
   - **二、债权投资减值准备**：单项计提/按组合计提/小计
   - **三、债权投资净值**（= 原值小计 - 减值小计，即摊余成本概念）
   - **附加：一年内到期非流动资产列报数**
3.2 THE G4-1审定表 SHALL 列结构：项目|期初(未审/账项调整/审定)|期末(未审/账项调整/审定)|变动额|变动率|原因分析
3.3 THE G4-1审定表 SHALL 实现借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
3.4 THE G4-1审定表 SHALL 实现审定数公式：审定 = 未审 + AJE + RJE
3.5 THE Formula_Engine SHALL 计算债权投资净值 = 原值小计 - 减值小计（即摊余成本）
3.6 THE G4-1审定表 SHALL 分组小计自动汇总（原值小计/减值小计/摊余成本合计）
3.7 THE G4-1审定表 SHALL 试算表数从trial_balance自动取数（科目1501）
3.8 THE G4-1审定表 SHALL 差异=审定-试算表数，差异≠0时红色高亮
3.9 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='1501', adjudicatedAmount=摊余成本审定数，即"三、债权投资摊余成本"行的审定数）
3.10 THE G4-1审定表 SHALL 变动率公式：变动率 = (期末审定 - 期初审定) / 期初审定 × 100%
3.11 WHEN |变动率|>20%时, THE 系统 SHALL 以橙色高亮并要求填写原因分析
3.12 THE G4-1审定表 SHALL 支持GtIndexChip索引列跳转
3.13 THE G4-1审定表 SHALL 支持展开/折叠分组（默认展开）

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 在精美HTML中编辑债权投资附注披露, so that 我能按上市/国企格式生成附注文本。

#### Acceptance Criteria

4.1 THE 附注披露(上市) SHALL 显示130行×11列结构化表格（启用虚拟滚动）
4.2 THE 附注披露(国企) SHALL 显示71行×7列结构化表格
4.3 THE 附注披露 SHALL 监听EventBus `substantive:adjudicated`(accountCode='1501')自动刷新审定数据
4.4 THE 附注披露 SHALL 通过EventBus发布 `disclosure:note-text-updated` 联动附注模块
4.5 THE 附注披露(上市) SHALL 启用虚拟滚动（130行超长附注）
4.6 THE 附注披露 SHALL 每个文本区提供AI辅助按钮（section标题行右侧）

### Requirement 5: 明细表G4-2（44列超宽表→5区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中查看债权投资逐笔明细, so that 我能检查每项投资的成本/利息调整/应计利息和摊余成本分解。

#### Acceptance Criteria

5.1 THE G4-2明细表 SHALL 拆为5区段Tab：
   - **基础信息(6列)**：投资种类|投资项目|面值|票面利率|实际利率|到期日
   - **期初余额(10列)**：期初成本|期初利息调整|期初应计利息|期初小计|期初减值准备|期初摊余成本|减期初一年内到期|期初调整数|期初审定数|备注
   - **本期变动(4列)**：本期成本变动|本期利息调整变动|本期应计利息变动|本期变动小计
   - **期末余额+减值(10列)**：期末成本|期末利息调整|期末应计利息|期末小计|减值准备期末数|阶段划分(Stage1/2/3)|信用组合方式|信用组合名称|减值准备审定|备注
   - **摊余成本+审定(8列)**：摊余成本|减一年内到期账面余额|减一年内到期减值|一年内到期小计|期末账面价值|发函情况|审定调整|索引
5.2 THE Formula_Engine SHALL 计算期初小计 = 期初成本 + 期初利息调整 + 期初应计利息，结果保留2位小数（四舍五入）
5.3 THE Formula_Engine SHALL 计算期初摊余成本 = 期初小计 - 期初减值准备，结果保留2位小数（四舍五入）
5.4 THE Formula_Engine SHALL 计算本期变动小计 = 本期成本变动 + 本期利息调整变动 + 本期应计利息变动，结果保留2位小数（四舍五入）
5.5 THE Formula_Engine SHALL 计算期末成本 = 期初成本 + 本期成本变动，结果保留2位小数（四舍五入）
5.6 THE Formula_Engine SHALL 计算期末利息调整 = 期初利息调整 + 本期利息调整变动，结果保留2位小数（四舍五入）
5.7 THE Formula_Engine SHALL 计算期末应计利息 = 期初应计利息 + 本期应计利息变动，结果保留2位小数（四舍五入）
5.8 THE Formula_Engine SHALL 计算期末小计 = 期末成本 + 期末利息调整 + 期末应计利息，结果保留2位小数（四舍五入）
5.9 THE Formula_Engine SHALL 计算摊余成本 = 期末小计 - 减值准备期末数，结果保留2位小数（四舍五入）
5.10 THE Formula_Engine SHALL 计算一年内到期小计 = 一年内到期账面余额 - 一年内到期减值，结果保留2位小数（四舍五入）
5.11 THE Formula_Engine SHALL 计算期末账面价值 = 摊余成本 - 一年内到期小计，结果保留2位小数（四舍五入）
5.12 THE G4-2明细表 SHALL 按到期日与资产负债表日比较进行数据分类：
   - 一、购入的以摊余成本计量的一年内到期的债权投资（到期日 ≤ 资产负债表日后1年，列报为"其他流动资产"）
   - 二、购入的以摊余成本计量的到期期限超过一年的债权投资（到期日 > 资产负债表日后1年）
5.13 WHEN 用户切换区段Tab时, THE G4-2明细表 SHALL 保持当前选中行的行索引不变（若切换前选中第N行，切换后第N行仍处于选中高亮状态）
5.14 THE G4-2明细表 SHALL 在底部显示合计行，对所有金额列按投资种类分类小计并显示总计行
5.15 THE G4-2明细表 SHALL 支持动态行增删 + 导入导出（ElMessageBox.prompt输入投资项目名称），单表最大行数不超过500行
5.16 IF 公式计算的输入列值为空或非数字, THEN THE Formula_Engine SHALL 将该输入视为0参与计算
5.17 IF 用户新增行时未输入投资项目名称或输入为空白字符, THEN THE G4-2明细表 SHALL 阻止行创建并保持ElMessageBox.prompt打开状态

### Requirement 6: 调整分录汇总G4-3

**User Story:** As a 审计助理, I want to 在精美HTML中录入债权投资调整分录, so that 我能记录AJE/RJE并回写审定表。

#### Acceptance Criteria

6.1 THE G4-3调整分录 SHALL 显示22行×10列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
6.2 THE G4-3调整分录 SHALL 借贷平衡校验
6.3 WHEN 借贷不平衡时, THE 系统 SHALL 以红色高亮并显示差额
6.4 THE G4-3调整分录 SHALL 支持动态行增删 + 导入导出（ElMessageBox.prompt输入摘要）
6.5 WHEN 调整分录保存时, THE 系统 SHALL 自动汇总AJE/RJE金额回写G4-1审定表

### Requirement 7: 利息测算表G4-4（实际利率法）

**User Story:** As a 审计助理, I want to 在精美HTML中测算债权投资利息收入, so that 我能验证企业使用实际利率法确认利息收入的正确性。

#### Acceptance Criteria

7.1 THE G4-4利息测算表 SHALL 分为两个section：
   - **(一) 确定初始入账价值(9列)**：投资项目|面值总额|初始计量日|到期日|购买对价|交易费用|初始入账价值(公式)|票面利率|实际利率
   - **(二) 计算利息收入(10列)**：截止日|期初账面总额|期初减值准备余额|期初摊余成本余额(公式)|实际利息收入(公式)|现金流入(公式)|已收回的本金|期末账面总额(公式)|计息天数|减值阶段(Stage1/Stage2/Stage3下拉选择)
7.2 THE Formula_Engine SHALL 计算初始入账价值 = 购买对价 + 交易费用，金额精度保留2位小数，利率精度保留至少4位小数
7.3 THE Formula_Engine SHALL 计算期初摊余成本余额 = 期初账面总额 - 期初减值准备余额
7.4 IF 该行减值阶段为Stage1或Stage2, THEN THE Formula_Engine SHALL 计算实际利息收入 = 期初摊余成本余额 × 实际利率 × 计息天数 / 365
7.5 IF 该行减值阶段为Stage3（已发生信用减值）, THEN THE Formula_Engine SHALL 计算实际利息收入 = 期初摊余成本余额 × 实际利率 × 计息天数 / 365（计算公式与Stage1/2相同，区别在于Stage3的减值准备通常更大，导致"期初摊余成本余额=期初账面-减值"基数显著更低）
7.6 IF 计息天数等于365（或366闰年整年）, THEN THE Formula_Engine SHALL 计算现金流入 = 面值总额 × 票面利率；IF 计息天数小于365（非整年期间）, THEN THE Formula_Engine SHALL 计算现金流入 = 面值总额 × 票面利率 × 计息天数 / 365
7.7 THE Formula_Engine SHALL 计算期末账面总额 = 期初账面总额 + 实际利息收入 - 现金流入 - 已收回的本金
7.8 THE G4-4利息测算表 SHALL 每个投资项目独立成组，组间以分隔线和项目名称标题区分，每组内section(二)支持多行（每行代表一个计息期间），各组纵向排列
7.9 THE G4-4利息测算表 SHALL 底部包含审计结论textarea（带AI辅助按钮）及编制提示details折叠区
7.10 THE G4-4利息测算表 SHALL 支持section(二)动态行增删，新增投资项目时通过ElMessageBox.prompt输入投资项目名称确认后创建新组；支持导入导出（el-dropdown"导入导出▾"含导出模板/导出数据/导入数据）
7.11 WHEN 利息测算计算完成, THE G4-4利息测算表 SHALL 将各投资项目的实际利息收入合计与G4-1审定表中对应科目的利息收入审定数进行比对，差异金额超过0.01元时以红色高亮显示差异行并展示差异金额

### Requirement 8: 公式引擎（G4-main专属）

**User Story:** As a 开发者, I want to 实现G4债权投资(main组)公式引擎, so that 摊余成本/利息测算/余额分解等公式可PBT验证。

#### Acceptance Criteria

8.1 THE Formula_Engine SHALL 实现 `calcDebitBalance(opening: number, debit: number, credit: number): number`，返回 `opening + debit - credit`（借方余额 = 期初 + 借方发生 - 贷方发生），浮点误差容忍度 < 1e-6
8.2 THE Formula_Engine SHALL 实现 `calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number`，返回 `unadjusted + aje + rje`（审定数 = 未审数 + AJE净额 + RJE净额），输入范围 -1e9 至 1e9
8.3 THE Formula_Engine SHALL 实现 `calcAmortizedCost(bookBalanceSubtotal: number, impairment: number): number`，返回 `bookBalanceSubtotal - impairment`（摊余成本 = 账面余额小计 - 减值准备）
8.4 THE Formula_Engine SHALL 实现 `calcBalanceSubtotal(cost: number, interestAdjustment: number, accruedInterest: number): number`，返回 `cost + interestAdjustment + accruedInterest`（余额小计 = 成本 + 利息调整 + 应计利息）
8.5 THE Formula_Engine SHALL 实现 `calcEffectiveInterest(amortizedCost: number, effectiveRate: number, days?: number): number`，当 days 未提供时返回 `amortizedCost * effectiveRate`（整年计息），当 days 为正整数时返回 `amortizedCost * effectiveRate * days / 365`（按天数计息），effectiveRate 为小数形式（如 0.05 表示 5%），days 取值范围 1~366
8.6 THE Formula_Engine SHALL 实现 `calcCashInflow(faceValue: number, couponRate: number, days?: number): number`，当 days 未提供时返回 `faceValue * couponRate`，当 days 为正整数时返回 `faceValue * couponRate * days / 365`，days 取值范围 1~366
8.7 THE Formula_Engine SHALL 实现 `calcEndingBalance(opening: number, effectiveInterest: number, cashInflow: number, principalRepaid: number): number`，返回 `opening + effectiveInterest - cashInflow - principalRepaid`
8.8 THE Formula_Engine SHALL 实现 `calcInitialCarryingAmount(purchasePrice: number, transactionCost: number): number`，返回 `purchasePrice + transactionCost`
8.9 THE Formula_Engine SHALL 实现 `calcChangeRate(prior: number, current: number): number | null`，当 prior=0 时返回 null（不得抛出除零异常），其他情况返回 `(current - prior) / prior`
8.10 THE Formula_Engine SHALL 实现 `calcOneYearMaturity(bookBalanceSubtotal: number, impairment: number): number`，返回 `bookBalanceSubtotal - impairment`
8.11 THE Formula_Engine SHALL 实现 `calcBookValue(amortizedCost: number, oneYearMaturity: number): number`，返回 `amortizedCost - oneYearMaturity`
8.12 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced(debits: number[], credits: number[]): boolean`，当 `|SUM(debits) - SUM(credits)| < 0.01` 时返回 true
8.13 THE Formula_Engine SHALL 实现 `calcPeriodEndComponent(openingComponent: number, periodChange: number): number`，返回 `openingComponent + periodChange`，分别用于成本、利息调整、应计利息三项
8.14 IF 任一公式函数接收到 null、undefined、空串或 NaN 作为数值参数, THEN THE Formula_Engine SHALL 通过 `parseNum` 将其转换为 0 后参与计算，不得抛出异常或返回 NaN
8.15 THE Formula_Engine SHALL 导出所有公式函数为纯函数（无副作用、无 Vue 响应式依赖、无外部状态访问），支持 fast-check PBT 以 numRuns≥100 验证各公式的代数恒等性

### Requirement 9: 跨模块联动（6大集成）

**User Story:** As a 开发者, I want to G4(main组)底稿集成跨模块联动, so that 版本链/抽凭/截止/附注/复核全部可用。

#### Acceptance Criteria

9.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
9.2 THE 抽凭引擎 SHALL 在G4A程序表集成GtVoucherSamplingEngine（dialog→样本填入）
9.3 THE 截止自动提取 SHALL 集成useCutoffAutoSampling（序时账±5天自动提取截止测试样本）
9.4 THE 附注EventBus SHALL subscribe `substantive:adjudicated`(accountCode='1501') 刷新 + publish `disclosure:note-text-updated`
9.5 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮
9.6 THE G4(main组) SHALL 不集成行级OCR（明细表非凭证表，无需OCR）

### Requirement 10: 导入导出与AI

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

10.1 THE Import_Export SHALL 对动态行表格支持导入导出：G4-2明细表/G4-3调整分录/G4-4利息测算表（共3张）
10.2 THE Import_Export SHALL 使用useG4MainImportExport composable（后端三端点：导出模板/导出数据/导入数据）
10.3 THE Import_Export SHALL G4-2明细表按5区段分sheet导出（多区块分sheet导出）
10.4 THE AI_Assistant SHALL 提供AI辅助section：adjudication-analysis（审定分析）/interest-conclusion（利息测算结论）/disclosure-text（附注文本）/overall-opinion（总体意见）
10.5 THE AI_Assistant SHALL 在每个文本区section标题行右侧提供AI辅助按钮
10.6 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 11: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且超长附注和大表流畅, so that 所有表格操作体验一致。

#### Acceptance Criteria

11.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
11.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源（如"摊余成本 = 小计 - 减值"）
11.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
11.4 THE UI SHALL 编制提示details折叠底部
11.5 THE UI SHALL 动态行新增需ElMessageBox.prompt输入名称确认后创建
11.6 THE Performance SHALL 对行数>50的表启用虚拟滚动（附注(上市)130行/附注(国企)71行）
11.7 THE Performance SHALL defineAsyncComponent懒加载所有子组件
11.8 THE UI SHALL G4-2明细表44列区段Tab切换流畅（Tab切换无闪烁/行同步无延迟）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证G4(main组)公式引擎的正确性。

**P1: 借方余额公式** — ∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit

**P2: 审定数公式** — ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje

**P3: 余额小计公式** — ∀ cost, interestAdj, accruedInterest ∈ ℝ: calcBalanceSubtotal(cost, interestAdj, accruedInterest) === cost + interestAdj + accruedInterest

**P4: 摊余成本公式** — ∀ subtotal ∈ ℝ, impairment ∈ ℝ≥0: calcAmortizedCost(subtotal, impairment) === subtotal - impairment

**P5: 实际利息收入公式（整年）** — ∀ amortizedCost ∈ ℝ≥0, rate ∈ (0,1): calcEffectiveInterest(amortizedCost, rate) === amortizedCost × rate；**按天数**：∀ days ∈ [1,366]: calcEffectiveInterest(amortizedCost, rate, days) === amortizedCost × rate × days / 365

**P6: 现金流入公式** — ∀ faceValue ∈ ℝ≥0, couponRate ∈ (0,1): calcCashInflow(faceValue, couponRate) === faceValue × couponRate

**P7: 期末账面余额公式** — ∀ opening, interest, cashInflow, principalRepaid ∈ ℝ≥0: calcEndingBalance(opening, interest, cashInflow, principalRepaid) === opening + interest - cashInflow - principalRepaid

**P8: 初始入账价值公式** — ∀ price, fees ∈ ℝ≥0: calcInitialCarryingAmount(price, fees) === price + fees

**P9: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)

**P10: 期末分项一致性** — ∀ opening, change ∈ ℝ: calcPeriodEndComponent(opening, change) === opening + change（适用于成本/利息调整/应计利息三项，具备加法交换律）

**P11: 变动率方向性** — ∀ end > start > 0: calcChangeRate(end, start) > 0; ∀ end < start, start > 0: calcChangeRate(end, start) < 0

**P12: 一年内到期小计公式** — ∀ balance ∈ ℝ≥0, impairment ∈ ℝ≥0: calcOneYearMaturity(balance, impairment) === balance - impairment

**P13: 账面价值=摊余-一年内** — ∀ amortized ∈ ℝ≥0, oneYear ∈ ℝ≥0: calcBookValue(amortized, oneYear) === amortized - oneYear
