# Requirements Document

## Introduction

F4应付账款底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `f4-accounts-payable`，覆盖1个xlsx源模板(105KB)/12个有效sheet。科目2202应付账款（贷方/负债类）。

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | **F4A 应付账款实质性程序表** | 41R×13C | a-program-console |
| 2 | **F4-1 审定表** | 31R×12C | 按性质+按账龄两级结构 |
| 3 | **附注披露(上市)** | 41R×4C | 上市公司附注格式 |
| 4 | **附注披露(国企)** | 26R×5C | 国企附注格式 |
| 5 | **F4-2 明细表** | 54R×27C | **27列宽表！**需拆为3区段Tab |
| 6 | **F4-3 调整分录** | 24R×10C | AJE/RJE |
| 7 | **F4-4 实质性分析** | 49R×8C | 实质性分析程序 |
| 8 | **F4-5 长期挂账检查** | 21R×11C | 1年以上应付账款检查 |
| 9 | **F4-6 关联方检查表** | 25R×15C | 关联方应付账款 |
| 10 | **F4-7 未入账检查表** | 104R×13C | **特色**：期后截止测试 |
| 11 | **F4-8 应付账款检查表** | 73R×18C | 借方贷方检查区 |
| 12 | **F4-9 供应商融资检查表** | 84R×16C | **特色**：保理/票据/供应链融资 |

**宽表处理策略**：
- F4-2明细表(27列)：拆为3区段Tab（基础信息/发生额与余额/账龄与审定）
- F4-8检查表(18列)：借方/贷方独立区块（类似F1-7/F3-7）

**贷方科目公式**（与F1借方方向相反）：
- 期末未审 = 期初审定 + 贷方发生额 - 借方发生额

核心特色：F4-7未入账检查（反向截止测试：期后采购/入库/收票→检查是否应入当期应付）、F4-9供应商融资检查（保理/票据融资/供应链融资合规性）、按性质+按账龄两级审定结构。EventBus联动：publish substantive:adjudicated(accountCode='2202')。

## Glossary

- **Accounts_Payable**: 应付账款，企业因采购商品/接受服务而应支付的款项
- **Aging_Structure**: 账龄结构，按1年以内/1-2年/2-3年/3年以上分段
- **Nature_Structure**: 性质结构，按货款/工程款/服务费等分类
- **Unrecorded_Liability**: 未入账负债，期后发生但应归属当期的应付款项
- **Cutoff_Test_Reverse**: 反向截止测试，从期后凭证反查是否有应入当期的应付
- **Supplier_Financing**: 供应商融资，包括保理/票据融资/供应链融资
- **Factoring**: 保理，应收账款转让融资
- **Supply_Chain_Finance**: 供应链融资，基于核心企业信用的融资安排
- **Long_Outstanding**: 长期挂账，1年以上未清偿的应付账款
- **Adjudication_Two_Level**: 两级审定结构，按性质汇总+按账龄汇总双维度
- **Credit_Direction**: 贷方科目，期末=期初+贷方-借方

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to F4应付账款底稿按sheetName prop分发到独立子组件, so that 12个有效sheet通过统一入口有序组织且代码可维护。

#### Acceptance Criteria

1.1 THE F4-Accounts-Payable 组件 SHALL 注册新componentType: `f4-accounts-payable`，主入口为 GtF4AccountsPayable.vue（接收sheetName prop，v-if分发到子组件，未迁移sheet走OnlyOffice fallback）
1.2 THE F4-Accounts-Payable 组件 SHALL 使用defineAsyncComponent懒加载所有子组件（12个sheet按需加载）
1.3 THE F4-Accounts-Payable 组件 SHALL 在htmlRendererRegistry中注册'f4-accounts-payable'→GtF4AccountsPayable映射
1.4 THE F4-Accounts-Payable 组件 SHALL 在wp_code_overrides.json中将F4A/F4-1~F4-9/附注披露(上市)/附注披露(国企)的componentType统一映射为'f4-accounts-payable'（12个wp_code条目）
1.5 THE F4-Accounts-Payable 组件 SHALL 在VALID_COMPONENT_TYPES中注册'f4-accounts-payable'
1.6 THE GtF4AccountsPayable.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=f4-accounts-payable）
1.7 THE GtF4AccountsPayable.vue SHALL 用正则从sheetName提取编码(F4A/F4-1~F4-9/附注)，匹配失败走OnlyOffice fallback
1.8 THE F4-Accounts-Payable 组件 SHALL 采用el-tabs模式组织12个tab

### Requirement 2: F4A 应付账款实质性程序表

**User Story:** As a 审计助理, I want to 在精美HTML中查看和执行应付账款实质性程序, so that 我能按步骤完成审计程序并记录执行情况。

#### Acceptance Criteria

2.1 THE F4A程序表 SHALL 使用a-program-console componentType渲染（复用GtAProgramConsole组件）
2.2 THE F4A程序表 SHALL 显示41行×13列的审计程序步骤（含auto_data_source自动取数）
2.3 THE F4A程序表 SHALL 支持执行人/执行日期/结论/索引字段编辑

### Requirement 3: F4-1 审定表（按性质+按账龄两级结构）

**User Story:** As a 审计助理, I want to 在精美HTML中填写应付账款审定表, so that 我能从性质和账龄两个维度汇总审定数。

#### Acceptance Criteria

3.1 THE F4-1审定表 SHALL 显示31行×12列，列结构：项目|期初(未审/账项调整/重分类/审定)|期末(同)|索引
3.2 THE F4-1审定表 SHALL 行结构分两级：
   - **按性质**：货款/工程款/服务费/其他/小计
   - **按账龄**：1年以内/1-2年/2-3年/3年以上/小计
   - **合计/试算表数/差异**
3.3 THE F4-1审定表 SHALL 实现贷方科目公式：期末未审 = 期初审定 + 贷方发生额 - 借方发生额
3.4 THE F4-1审定表 SHALL 实现审定数公式：审定 = 未审 + 账项调整 + 重分类
3.5 THE F4-1审定表 SHALL 按性质小计=各性质行SUM；按账龄小计=各账龄段SUM；合计=按性质小计（=按账龄小计，交叉校验）
3.6 THE F4-1审定表 SHALL 试算表数从trial_balance自动取数（科目2202）
3.7 THE F4-1审定表 SHALL 差异=审定-试算表数，差异≠0时红色高亮
3.8 WHEN 按性质小计≠按账龄小计时, THE 系统 SHALL 红色高亮并显示交叉校验失败
3.9 WHEN 审定数变更时, THE 系统 SHALL 通过EventBus发布 `substantive:adjudicated`（accountCode='2202', adjudicatedAmount=审定数）
3.10 THE F4-1审定表 SHALL 支持GtIndexChip索引列跳转

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 在精美HTML中编辑应付账款附注披露内容, so that 我能按格式生成附注。

#### Acceptance Criteria

4.1 THE 附注披露(上市) SHALL 显示41行×4列结构化表格（含前5大供应商明细）
4.2 THE 附注披露(国企) SHALL 显示26行×5列结构化表格
4.3 THE 附注披露 SHALL 监听EventBus `substantive:adjudicated`(accountCode='2202')自动刷新
4.4 THE 附注披露 SHALL 通过EventBus发布 `disclosure:note-text-updated` 联动附注模块
4.5 THE 附注披露 SHALL 支持编辑后保存

### Requirement 5: F4-2 明细表（27列宽表→3区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML中查看应付账款逐笔明细, so that 我能检查每个债权人的余额变动和账龄分布。

#### Acceptance Criteria

5.1 THE F4-2明细表 SHALL 拆为3区段Tab：
   - **基础信息(9列)**：序号|债权人|公司代码|关联方类型(下拉)|款项性质(下拉)|期初审定|本期借方|本期贷方|期末余额(公式)
   - **账龄与核对(10列)**：账龄1年以内|1-2年|2-3年|3年以上|账龄合计(公式)|是否函证|函证结果|期后付款金额|期后付款日期|备注
   - **调整与审定(8列)**：账项调整|重分类|审定余额(公式)|审定账龄1年内|1-2年|2-3年|3年以上|索引
5.2 THE Formula_Engine SHALL 计算期末余额 = 期初审定 + 本期贷方 - 本期借方（贷方科目）
5.3 THE Formula_Engine SHALL 计算账龄合计 = 1年以内+1-2年+2-3年+3年以上（=期末余额，交叉校验）
5.4 THE Formula_Engine SHALL 计算审定余额 = 期末余额 + 账项调整 + 重分类
5.5 WHEN 账龄合计≠期末余额时, THE 系统 SHALL 以红色高亮该行账龄合计列
5.6 THE F4-2明细表 SHALL 区段间保持行同步
5.7 THE F4-2明细表 SHALL 底部合计行（期初合计/借方合计/贷方合计/期末合计/各账龄合计/审定合计）
5.8 THE F4-2明细表 SHALL 支持动态行增删 + 导入导出

### Requirement 6: F4-3 调整分录

**User Story:** As a 审计助理, I want to 录入应付账款调整分录, so that 我能记录AJE/RJE。

#### Acceptance Criteria

6.1 THE F4-3调整分录 SHALL 显示24行×10列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
6.2 THE F4-3调整分录 SHALL 借贷平衡校验
6.3 WHEN 借贷不平衡时, THE 系统 SHALL 以红色高亮并显示差额
6.4 THE F4-3调整分录 SHALL 支持动态行增删 + 导入导出

### Requirement 7: F4-4 实质性分析

**User Story:** As a 审计助理, I want to 在精美HTML中执行应付账款实质性分析, so that 我能通过趋势分析发现异常波动。

#### Acceptance Criteria

7.1 THE F4-4实质性分析 SHALL 显示49行×8列：分析项目|本期金额|上期金额|变动额(公式)|变动率(公式)|预期值|预期差异(公式)|分析说明
7.2 THE Formula_Engine SHALL 计算变动额 = 本期 - 上期
7.3 THE Formula_Engine SHALL 计算变动率 = (本期 - 上期) / 上期 × 100%
7.4 THE Formula_Engine SHALL 计算预期差异 = 本期 - 预期值
7.5 WHEN 变动率绝对值>20%时, THE 系统 SHALL 以橙色高亮该行
7.6 THE F4-4实质性分析 SHALL 审计结论textarea(AI辅助) + 编制提示details折叠

### Requirement 8: F4-5 长期挂账检查

**User Story:** As a 审计助理, I want to 在精美HTML中检查1年以上长期挂账的应付账款, so that 我能评估是否存在无需支付的款项。

#### Acceptance Criteria

8.1 THE F4-5长期挂账 SHALL 显示21行×11列：序号|债权人|挂账金额|挂账起始日|挂账天数(公式)|款项性质|挂账原因|是否有合同纠纷|是否需转营业外收入|处理建议|备注
8.2 THE Formula_Engine SHALL 计算挂账天数 = 当前日期 - 挂账起始日
8.3 WHEN 挂账天数>365×2时, THE 系统 SHALL 以橙色高亮（2年以上高关注）
8.4 WHEN 挂账天数>365×3时, THE 系统 SHALL 以红色高亮（3年以上需转收入评估）
8.5 THE F4-5长期挂账 SHALL 底部汇总（长期挂账总额/2年以上金额/3年以上金额/建议转收入金额）
8.6 THE F4-5长期挂账 SHALL 支持动态行增删 + 导入导出 + 审计结论textarea(AI辅助)

### Requirement 9: F4-6 关联方检查表

**User Story:** As a 审计助理, I want to 在精美HTML中检查关联方应付账款, so that 我能评估关联交易公允性。

#### Acceptance Criteria

9.1 THE F4-6关联方检查表 SHALL 显示25行×15列：序号|关联方名称|关联关系|款项性质|期初余额|本期增加|本期减少|期末余额(公式)|占比(公式)|结算周期|是否超期|定价公允性(下拉)|账龄|审计评价|备注
9.2 THE Formula_Engine SHALL 计算期末余额 = 期初 + 贷方增加 - 借方减少
9.3 THE Formula_Engine SHALL 计算占比 = 该关联方余额 / 应付账款总余额 × 100%
9.4 WHEN 单一关联方占比>30%时, THE 系统 SHALL 以橙色高亮
9.5 THE F4-6关联方检查表 SHALL 底部汇总（关联方应付合计/占比/超期笔数）+ 审计说明textarea(AI辅助)
9.6 THE F4-6关联方检查表 SHALL 支持动态行增删 + 导入导出

### Requirement 10: F4-7 未入账检查表（反向截止测试）

**User Story:** As a 审计助理, I want to 在精美HTML中执行未入账应付检查, so that 我能通过期后采购/入库/收票反查是否有应归属当期但未入账的应付款项。

#### Acceptance Criteria

10.1 THE F4-7未入账检查 SHALL 显示104行×13列，分3个检查区域：
   - **期后采购检查**：序号|采购日期|供应商|金额|采购单号|商品/服务|是否应入当期|入账建议|备注
   - **期后入库检查**：序号|入库日期|供应商|金额|入库单号|商品名称|是否应入当期|入账建议|备注
   - **期后收票检查**：序号|收票日期|开票方|金额|发票号|服务期间|是否应入当期|入账建议|备注
10.2 THE F4-7未入账检查 SHALL 集成useCutoffAutoSampling（从序时账自动提取资产负债表日±5天的采购/入库/收票凭证）
10.3 WHEN useCutoffAutoSampling提取完成时, THE 系统 SHALL 自动填入对应检查区域（按凭证类型分配）
10.4 THE F4-7未入账检查 SHALL 各区域独立动态行增删
10.5 THE F4-7未入账检查 SHALL 各区域底部小计（总金额/应入当期笔数/应入当期金额）
10.6 THE F4-7未入账检查 SHALL 底部总结：未入账应付合计 + 建议调整金额 + 审计结论textarea(AI辅助)
10.7 WHEN "是否应入当期"="是"时, THE 系统 SHALL 以橙色高亮该行
10.8 THE F4-7未入账检查 SHALL 支持导入导出 + 虚拟滚动(104行)

### Requirement 11: F4-8 应付账款检查表（借方贷方检查区）

**User Story:** As a 审计助理, I want to 在精美HTML中执行应付账款借方贷方检查, so that 我能逐笔抽查余额增减变动的凭证支持。

#### Acceptance Criteria

11.1 THE F4-8检查表 SHALL 分为两个独立区块：借方检查区(减少/付款) + 贷方检查区(增加/采购)
11.2 THE 借方检查区 SHALL 显示：序号|摘要|对方科目|金额|凭证日期|凭证编号|付款方式|银行流水|付款审批|审计结论|备注
11.3 THE 贷方检查区 SHALL 显示：序号|摘要|对方科目|金额|凭证日期|凭证编号|采购订单|入库单|发票核对|三单匹配|审计结论|备注
11.4 THE F4-8检查表 SHALL 借方区+贷方区各自独立动态行增删
11.5 THE F4-8检查表 SHALL 各区底部小计（金额合计/异常笔数）
11.6 THE F4-8检查表 SHALL 集成GtVoucherSamplingEngine抽凭引擎（dialog模式，预填科目2202）
11.7 WHEN 抽凭引擎返回样本时, THE 系统 SHALL 自动填入借方/贷方检查区行（根据借贷方向分配）
11.8 THE F4-8检查表 SHALL 已抽凭填入行显示来源tooltip
11.9 THE F4-8检查表 SHALL 支持导入导出 + 审计结论textarea(AI辅助)

### Requirement 12: F4-9 供应商融资检查表

**User Story:** As a 审计助理, I want to 在精美HTML中检查供应商融资安排, so that 我能评估保理/票据融资/供应链融资的合规性和列报适当性。

#### Acceptance Criteria

12.1 THE F4-9供应商融资检查 SHALL 显示84行×16列，分3个检查区域：
   - **保理融资**：序号|供应商|保理公司|保理金额|保理日期|到期日|保理费率|是否有追索权|是否终止确认|列报科目|审计评价|备注
   - **票据融资**：序号|供应商|票据类型|票据金额|出票日|到期日|贴现金额|贴现利率|是否背书转让|列报适当性|审计评价|备注
   - **供应链融资**：序号|供应商|核心企业|融资金额|融资日期|到期日|融资利率|平台名称|是否修改付款条件|是否应重分类|审计评价|备注
12.2 THE F4-9供应商融资检查 SHALL 各区域独立动态行增删
12.3 THE F4-9供应商融资检查 SHALL 各区域底部小计（融资总金额/到期未付笔数）
12.4 WHEN "是否应重分类"="是" 或 "终止确认"="否" 时, THE 系统 SHALL 以橙色高亮
12.5 THE F4-9供应商融资检查 SHALL 底部总结：融资合计+建议重分类金额+审计结论textarea(AI辅助)
12.6 THE F4-9供应商融资检查 SHALL 支持导入导出 + 虚拟滚动(84行)

### Requirement 13: 公式引擎（F4专属）

**User Story:** As a 开发者, I want to 实现F4应付账款公式引擎, so that 贷方余额/账龄/挂账天数等公式可PBT验证。

#### Acceptance Criteria

13.1 THE Formula_Engine SHALL 实现 `calcCreditBalance`（贷方余额 = 期初 + 贷方 - 借方）
13.2 THE Formula_Engine SHALL 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
13.3 THE Formula_Engine SHALL 实现 `calcAgingTotal`（账龄合计 = 各账龄段SUM）
13.4 THE Formula_Engine SHALL 实现 `calcConcentration`（占比 = 金额 / 总额 × 100%）
13.5 THE Formula_Engine SHALL 实现 `calcOutstandingDays`（挂账天数 = 当前日期 - 起始日）
13.6 THE Formula_Engine SHALL 实现 `calcChangeRate`（变动率 = (本期 - 上期) / 上期 × 100%）
13.7 THE Formula_Engine SHALL 实现 `isDebitCreditBalanced`（借贷平衡校验）
13.8 THE Formula_Engine SHALL 实现 `calcAgingCrossCheck`（账龄合计===期末余额交叉校验）

### Requirement 14: 跨模块联动（6大集成）

**User Story:** As a 开发者, I want to F4底稿集成6大跨模块联动, so that 版本链/抽凭/附注/OCR/复核/截止全部可用。

#### Acceptance Criteria

14.1 THE 版本链 SHALL 集成useVersionTrail（主入口autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
14.2 THE 抽凭引擎 SHALL 在F4-8检查表集成GtVoucherSamplingEngine（dialog→样本填入借方/贷方检查区）
14.3 THE 附注EventBus SHALL subscribe `substantive:adjudicated` 刷新 + publish `disclosure:note-text-updated`
14.4 THE 行级OCR SHALL 在F4-2明细表📎列POST contract-ocr→识别发票金额/供应商→ElMessageBox确认→merge
14.5 THE 复核对话 SHALL 主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮
14.6 THE 截止自动提取 SHALL 在F4-7未入账检查集成useCutoffAutoSampling（序时账±5天自动提取）

### Requirement 15: 导入导出与AI

**User Story:** As a 审计助理, I want to 支持Excel导入导出和AI辅助, so that 我能离线填写后导入并快速生成审计结论。

#### Acceptance Criteria

15.1 THE Import_Export SHALL 对动态行表格支持导入导出：F4-2明细/F4-3调整/F4-5长期挂账/F4-6关联方/F4-7未入账/F4-8检查/F4-9融资（共7张）
15.2 THE Import_Export SHALL 使用useF4ImportExport composable（后端三端点）
15.3 THE AI_Assistant SHALL 提供6个section：substantive-analysis/long-outstanding/related-evaluation/unrecorded-conclusion/voucher-check/financing-evaluation
15.4 THE Dual_Mode SHALL 支持HTML↔OnlyOffice切换 + localStorage持久化

### Requirement 16: UI规范与性能

**User Story:** As a 开发者, I want to 统一UI规范且104行未入账表流畅, so that 所有表格操作体验一致。

#### Acceptance Criteria

16.1 THE UI SHALL 表格字体13px；AI+复核按钮右对齐在section标题同行
16.2 THE UI SHALL 公式列虚线下划线+cursor:help+tooltip显示公式来源
16.3 THE UI SHALL 列宽min-width自适应；审计说明/结论el-card包裹
16.4 THE UI SHALL 编制提示details折叠底部
16.5 THE Performance SHALL 对行数>50的表启用虚拟滚动（F4-7未入账104行/F4-9融资84行/F4-8检查73行）
16.6 THE Performance SHALL defineAsyncComponent懒加载所有子组件

## Correctness Properties

> 以下性质将通过Property-Based Testing验证F4公式引擎的正确性。

**P1: 贷方余额公式** — ∀ opening, credit, debit ∈ ℝ≥0: calcCreditBalance(opening, credit, debit) === opening + credit - debit

**P2: 审定数公式** — ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje

**P3: 账龄交叉校验** — ∀ aging1, aging2, aging3, aging4, closingBalance ∈ ℝ≥0: calcAgingCrossCheck(aging1+aging2+aging3+aging4, closingBalance) ↔ (aging1+aging2+aging3+aging4 === closingBalance)

**P4: 集中度公式** — ∀ amount ∈ ℝ≥0, total ∈ ℝ>0: calcConcentration(amount, total) === amount/total × 100

**P5: 变动率公式** — ∀ current, prior ∈ ℝ, prior≠0: calcChangeRate(current, prior) === (current-prior)/prior × 100

**P6: 借贷平衡恒等** — ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (SUM(debits) === SUM(credits))

**P7: 挂账天数非负** — ∀ currentDate, startDate: calcOutstandingDays(currentDate, startDate) ≥ 0

**P8: 两级审定交叉校验** — ∀ natureSubtotal, agingSubtotal: natureSubtotal === agingSubtotal（按性质小计必须等于按账龄小计）
