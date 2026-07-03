# Requirements Document

## Introduction

F3应付票据底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `f3-notes-payable`，覆盖1个xlsx源模板(77KB)/10个有效sheet。科目2201应付票据（贷方/负债类）。

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **F3A 应付票据实质性程序表** | 33R×13C | a-program-console |
| 2 | **F3-1 审定表** | 48R×12C | 期初/期末审定+试算表差异 |
| 3 | **附注披露(上市)** | 13R×16C | 上市公司附注格式 |
| 4 | **附注披露(国企)** | 16R×5C | 国企附注格式 |
| 5 | **F3-2 明细表** | 53R×25C | 25列宽表需拆分 |
| 6 | **F3-3 调整分录** | 24R×10C | AJE/RJE |
| 7 | **F3-4 带息票据利息测算表** | 38R×13C | 面值/票面利率/期限/应付利息 |
| 8 | **F3-5 逾期票据检查** | 32R×15C | 逾期天数/风险评估 |
| 9 | **F3-6 关联方检查表** | 26R×16C | 关联方应付票据 |
| 10 | **F3-7 应付票据检查表** | 97R×18C | 借方贷方检查区大表 |

**宽表处理策略**：
- F3-2明细表(25列)：拆为3区段Tab（基础信息/票据详情/审定调整）
- F3-7检查表(18列)：借方/贷方独立区块（类似F1-7）

**贷方科目公式**（与F1借方方向相反）：
- 期末未审 = 期初审定 + 贷方发生额 - 借方发生额

核心特色：带息票据利息测算（面值×利率×期限/360）、逾期票据天数计算与风险评估、关联方票据集中度分析。EventBus联动：publish substantive:adjudicated(accountCode='2201')。

## Glossary

- **Notes_Payable**: 应付票据，企业因商业交易开出的银行承兑汇票/商业承兑汇票
- **Bank_Acceptance**: 银行承兑汇票，银行承诺付款
- **Commercial_Acceptance**: 商业承兑汇票，企业承诺付款
- **Interest_Bearing_Note**: 带息票据，面值×票面利率×期限计算应付利息
- **Overdue_Note**: 逾期票据，到期未付的应付票据
- **Adjudication_Table**: 审定表(F3-1)，期初/期末审定额汇总，回写trial_balance
- **Credit_Direction**: 贷方科目，期末=期初+贷方-借方（与借方科目方向相反）
- **Segment_Tab**: 区段Tab宽表拆分模式，F3-2的25列拆为3区段
- **Debit_Credit_Block**: 借贷方独立区块，F3-7检查表借方/贷方分区展示

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to F3应付票据底稿按sheetName prop分发到独立子组件, so that 10个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE F3-Notes-Payable 组件 SHALL 注册新componentType: `f3-notes-payable`，主入口为 GtF3NotesPayable.vue（接收sheetName prop，v-if分发到子组件，未迁移sheet走OnlyOffice fallback）
1.2 THE F3-Notes-Payable 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（10个sheet按需加载）
1.3 THE F3-Notes-Payable 组件 SHALL 在htmlRendererRegistry中注册'f3-notes-payable'→GtF3NotesPayable映射
1.4 THE F3-Notes-Payable 组件 SHALL 在wp_code_overrides.json中将F3A/F3-1~F3-7/附注披露(上市)/附注披露(国企)的componentType统一映射为'f3-notes-payable'（10个wp_code条目）
1.5 THE F3-Notes-Payable 组件 SHALL 在VALID_COMPONENT_TYPES中注册'f3-notes-payable'
1.6 THE GtF3NotesPayable.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=f3-notes-payable）
1.7 THE GtF3NotesPayable.vue SHALL 用正则从sheetName提取编码(F3A/F3-1~F3-7/附注)，匹配失败走OnlyOffice fallback
1.8 THE F3-Notes-Payable 组件 SHALL 采用el-tabs模式组织10个tab

### Requirement 2: F3A 应付票据实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中查看和执行应付票据实质性程序, so that 我能按步骤完成审计程序并记录执行情况。

#### Acceptance Criteria

2.1 THE F3A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE F3A程序表 SHALL 显示33行×13列的审计程序步骤（含auto_data_source自动取数）
2.3 THE F3A程序表 SHALL 支持执行人/执行日期/结论/索引字段编辑

### Requirement 3: F3-1 审定表（贷方科目）

**User Story:** As a 审计助理, I want to 在精美HTML中填写应付票据审定表, so that 我能汇总期初/期末未审数、调整数及审定数并回写试算表。

#### Acceptance Criteria

3.1 THE F3-1审定表 SHALL 显示48行×12列，列结构：项目|期初(未审/账项调整/重分类/审定)|期末(同)|索引
3.2 THE F3-1审定表 SHALL 行结构：银行承兑汇票/商业承兑汇票/合计/试算表数/差异
3.3 THE F3-1审定表 SHALL 实现贷方科目公式：期末未审 = 期初审定 + 贷方发生额 - 借方发生额
3.4 THE F3-1审定表 SHALL 实现审定数公式：审定 = 未审 + 账项调整 + 重分类
3.5 THE F3-1审定表 SHALL 合计行自动汇总（银行承兑+商业承兑=合计）
3.6 THE F3-1审定表 SHALL 试算表数从trial_balance自动取数（科目2201）
3.7 THE F3-1审定表 SHALL 差异=审定-试算表数，差异≠0时红色高亮
3.8 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='2201', adjudicatedAmount=审定数）
3.9 THE F3-1审定表 SHALL 支持GtIndexChip索引列跳转

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 在精美HTML中编辑应付票据附注披露内容, so that 我能按上市/国企格式生成附注文本。

#### Acceptance Criteria

4.1 THE 附注披露(上市) SHALL 显示13行×16列结构化表格
4.2 THE 附注披露(国企) SHALL 显示16行×5列结构化表格
4.3 THE 附注披露 SHALL 监听EventBus `substantive:adjudicated`(accountCode='2201')自动刷新审定数据
4.4 THE 附注披露 SHALL 通过EventBus发布 `disclosure:note-text-updated` 联动附注模块
4.5 THE 附注披露 SHALL 支持编辑后保存

### Requirement 5: F3-2 明细表（25列宽表→3区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中查看应付票据逐笔明细, so that 我能检查每张票据的基本信息、到期状况和审定调整。

#### Acceptance Criteria

5.1 THE F3-2明细表 SHALL 拆为3区段Tab：
   - **基础信息(9列)**：序号|出票日期|到期日|票据类型(银行/商业)|出票人|收票人|面值|币种|用途
   - **票据详情(8列)**：票面利率|期限(天)|是否带息|是否逾期|逾期天数(公式)|承兑银行|票据状态(流通/到期/逾期/背书)|备注
   - **审定调整(8列)**：期初余额|本期增加|本期减少|期末余额(公式)|账项调整|重分类|审定余额(公式)|索引
5.2 THE Formula_Engine SHALL 计算期末余额 = 期初余额 + 本期增加(贷方) - 本期减少(借方)
5.3 THE Formula_Engine SHALL 计算审定余额 = 期末余额 + 账项调整 + 重分类
5.4 THE Formula_Engine SHALL 计算逾期天数 = MAX(0, 当前日期 - 到期日)
5.5 WHEN 逾期天数>0时, THE 系统 SHALL 以橙色高亮该行
5.6 THE F3-2明细表 SHALL 区段间保持行同步
5.7 THE F3-2明细表 SHALL 底部合计行（面值合计/期末余额合计/审定余额合计）
5.8 THE F3-2明细表 SHALL 支持动态行增删 + 导入导出

### Requirement 6: F3-3 调整分录

**User Story:** As a 审计助理, I want to 在精美HTML中录入应付票据调整分录, so that 我能记录AJE/RJE并回写审定表。

#### Acceptance Criteria

6.1 THE F3-3调整分录 SHALL 显示24行×10列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
6.2 THE F3-3调整分录 SHALL 借贷平衡校验（同一分录组借方合计=贷方合计）
6.3 WHEN 借贷不平衡时, THE 系统 SHALL 以红色高亮并显示差额
6.4 THE F3-3调整分录 SHALL 支持动态行增删 + 导入导出

### Requirement 7: F3-4 带息票据利息测算表

**User Story:** As a 审计助理, I want to 在精美HTML中测算带息票据的应付利息, so that 我能验证企业计提利息的正确性。

#### Acceptance Criteria

7.1 THE F3-4利息测算表 SHALL 显示38行×13列：序号|出票人|票据面值|票面利率(%)|出票日|到期日|期限(天)|计息起始日|计息截止日|应计天数(公式)|应付利息(公式)|企业计提利息|差异(公式)
7.2 THE Formula_Engine SHALL 计算应计天数 = 计息截止日 - 计息起始日
7.3 THE Formula_Engine SHALL 计算应付利息 = 票据面值 × 票面利率/100 × 应计天数/360
7.4 THE Formula_Engine SHALL 计算差异 = 应付利息 - 企业计提利息
7.5 WHEN |差异|>100元时, THE 系统 SHALL 以橙色高亮该行
7.6 THE F3-4利息测算表 SHALL 底部合计（面值合计/应付利息合计/企业计提合计/差异合计）
7.7 THE F3-4利息测算表 SHALL 支持动态行增删 + 导入导出
7.8 THE F3-4利息测算表 SHALL 审计结论textarea(AI辅助) + 编制提示details折叠

### Requirement 8: F3-5 逾期票据检查

**User Story:** As a 审计助理, I want to 在精美HTML中检查逾期票据, so that 我能评估逾期票据的风险并提出审计建议。

#### Acceptance Criteria

8.1 THE F3-5逾期票据检查 SHALL 显示32行×15列：序号|出票人|票据类型|面值|出票日|到期日|逾期天数(公式)|逾期原因|承兑方|承兑方信用等级|是否已转应付账款|催收情况|风险等级(下拉)|审计建议|备注
8.2 THE Formula_Engine SHALL 计算逾期天数 = 当前日期 - 到期日（仅到期日<当前日期时计算）
8.3 WHEN 逾期天数>90时, THE 系统 SHALL 风险等级自动建议"高"并以红色高亮
8.4 WHEN 逾期天数>30且≤90时, THE 系统 SHALL 以橙色高亮
8.5 THE F3-5逾期票据检查 SHALL 风险等级下拉：低/中/高/极高
8.6 THE F3-5逾期票据检查 SHALL 底部汇总（逾期笔数/逾期总金额/高风险笔数/已转应付笔数）
8.7 THE F3-5逾期票据检查 SHALL 支持动态行增删 + 导入导出 + 审计结论textarea(AI辅助)

### Requirement 9: F3-6 关联方检查表

**User Story:** As a 审计助理, I want to 在精美HTML中检查关联方应付票据, so that 我能评估关联方票据集中度和交易公允性。

#### Acceptance Criteria

9.1 THE F3-6关联方检查表 SHALL 显示26行×16列：序号|关联方名称|关联关系|票据类型|面值|出票日|到期日|期限|利率|用途|占比(公式)|是否正常结算|结算方式|定价公允性(下拉)|审计评价|备注
9.2 THE Formula_Engine SHALL 计算占比 = 该关联方面值 / 全部应付票据面值SUM × 100%
9.3 WHEN 单一关联方占比>30%时, THE 系统 SHALL 以橙色高亮提示集中度风险
9.4 THE F3-6关联方检查表 SHALL 定价公允性下拉：公允/基本公允/不公允/无法判断
9.5 THE F3-6关联方检查表 SHALL 底部汇总（关联方票据合计/占比/不公允笔数）+ 审计说明textarea(AI辅助)
9.6 THE F3-6关联方检查表 SHALL 支持动态行增删 + 导入导出

### Requirement 10: F3-7 应付票据检查表（97行大表，借方贷方检查区）

**User Story:** As a 审计助理, I want to 在精美HTML中执行应付票据借方贷方检查, so that 我能逐笔抽查票据增减变动的凭证支持。

#### Acceptance Criteria

10.1 THE F3-7检查表 SHALL 分为两个独立区块：借方检查区(减少) + 贷方检查区(增加)
10.2 THE 借方检查区 SHALL 显示：序号|摘要|对方科目|金额|凭证日期|凭证编号|付款方式|银行流水核对|是否逾期付款|审计结论|备注
10.3 THE 贷方检查区 SHALL 显示：序号|摘要|对方科目|金额|凭证日期|凭证编号|票据类型|承兑方|采购合同核对|商品验收核对|审计结论|备注
10.4 THE F3-7检查表 SHALL 借方区+贷方区各自独立动态行增删
10.5 THE F3-7检查表 SHALL 各区底部小计（金额合计/异常笔数）
10.6 THE F3-7检查表 SHALL 集成GtVoucherSamplingEngine抽凭引擎（对话框模式，预填科目2201）
10.7 WHEN 抽凭引擎返回样本时, THE 系统 SHALL 自动填入借方/贷方检查区行（根据借贷方向分配）
10.8 THE F3-7检查表 SHALL 已抽凭填入行显示来源tooltip"来自抽凭引擎 {algorithm}"
10.9 THE F3-7检查表 SHALL 支持导入导出 + 审计结论textarea(AI辅助)

### Requirement 11: 公式引擎（F3专属）

**User Story:** As a 开发者, I want to 实现F3应付票据公式引擎, so that 利息测算/逾期天数/贷方余额等公式可PBT验证。

#### Acceptance Criteria

11.1 THE Formula_Engine SHALL 实现 `calcInterest`（应付利息 = 面值 × 利率/100 × 天数/360）
11.2 THE Formula_Engine SHALL 实现 `calcOverdueDays`（逾期天数 = MAX(0, 当前日期 - 到期日)）
11.3 THE Formula_Engine SHALL 实现 `calcCreditBalance`（贷方余额 = 期初 + 贷方 - 借方）
11.4 THE Formula_Engine SHALL 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
11.5 THE Formula_Engine SHALL 实现 `calcConcentration`（集中度 = 单一方金额 / 总额 × 100%）
11.6 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced`（借贷平衡 = 借方SUM === 贷方SUM）

### Requirement 12: 跨模块联动（6大集成）

**User Story:** As a 开发者, I want to F3底稿集成6大跨模块联动, so that 版本链/抽凭/附注/OCR/复核/截止全部可用。

#### Acceptance Criteria

12.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
12.2 THE 抽凭引擎 SHALL 在F3-7检查表集成GtVoucherSamplingEngine（dialog→样本填入借方/贷方检查区）
12.3 THE 附注EventBus SHALL subscribe `substantive:adjudicated` 刷新 + publish `disclosure:note-text-updated`
12.4 THE 行级OCR SHALL 在F3-4利息测算表📎列POST contract-ocr→识别票据面值/利率/期限→ElMessageBox确认→merge
12.5 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮
12.6 THE F3底稿 SHALL 不适用截止自动提取（useCutoffAutoSampling仅适用于有截止测试的底稿）

### Requirement 13: 导入导出与AI

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

13.1 THE Import_Export SHALL 对动态行表格支持导入导出：F3-2明细表/F3-3调整/F3-4利息/F3-5逾期/F3-6关联方/F3-7检查表（共6张）
13.2 THE Import_Export SHALL 使用useF3ImportExport composable（后端三端点）
13.3 THE AI_Assistant SHALL 提供5个section：interest-conclusion/overdue-evaluation/related-evaluation/debit-check-conclusion/credit-check-conclusion
13.4 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 14: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且97行检查表流畅, so that 所有表格操作体验一致。

#### Acceptance Criteria

14.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
14.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
14.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
14.4 THE UI SHALL 编制提示details折叠底部
14.5 THE Performance SHALL 对行数>50的表启用虚拟滚动（F3-7检查表97行）
14.6 THE Performance SHALL defineAsyncComponent懒加载所有子组件

## Correctness Properties

> 以下性质将通过Property-Based Testing验证F3公式引擎的正确性。

**P1: 带息票据利息公式** — ∀ principal ∈ ℝ≥0, rate ∈ [0,100], days ∈ ℤ≥0: calcInterest(principal, rate, days) === principal × rate/100 × days/360

**P2: 贷方余额公式** — ∀ opening, credit, debit ∈ ℝ≥0: calcCreditBalance(opening, credit, debit) === opening + credit - debit

**P3: 审定数公式** — ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje

**P4: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) === (SUM(debits) === SUM(credits))

**P5: 集中度公式** — ∀ amount ∈ ℝ≥0, total ∈ ℝ>0: calcConcentration(amount, total) === amount/total × 100

**P6: 逾期天数非负** — ∀ currentDate, dueDate: calcOverdueDays(currentDate, dueDate) ≥ 0

**P7: 利息与面值正比** — ∀ p1, p2 ∈ ℝ≥0, rate, days固定: calcInterest(p1, rate, days) / calcInterest(p2, rate, days) === p1/p2 (p2≠0)

**P8: 贷方余额方向性** — ∀ opening, credit, debit: credit>debit → calcCreditBalance(opening, credit, debit) > opening
