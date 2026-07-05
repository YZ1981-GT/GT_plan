# Requirements Document: L8 财务费用底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑权威来源。
2. **底稿模板库md**（`BCD类底稿md/L筹资循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **接收L1/L3/L4利息测算+L5摊销** + 截止测试自动提取 + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useL8ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

L8财务费用底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `l8-financial-expenses`，覆盖来自 `L8 财务费用.xlsx` 的10个有效sheet。科目覆盖6603财务费用（**损益类！取发生额**，从tb_ledger取本期发生额）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**L8核心特殊**：①**损益类科目**（取发生额，非余额！从tb_ledger取本期借贷发生额，与L1~L7负债类根本不同）②**利息支出测算**（接收L1短期借款/L3长期借款/L4应付债券利息测算+L5未确认融资费用摊销）③**截止性测试**（序时账±天数，自动提取样本）④**汇兑损益**（外币折算差额）。关键公式总数约150+。财务费用按明细项目：利息支出/利息收入/汇兑损益/手续费等列示。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_L8A**: 财务费用实质性程序表L8A（复用a-program-console）
- **Adjudication_L8_1**: 审定表L8-1，29×12，67公式，科目6603财务费用(损益类/取发生额)
- **Disclosure_Listed**: 附注披露信息（上市公司），20×9
- **Disclosure_SOE**: 附注披露信息（国有企业），18×21
- **Detail_L8_2**: 明细表L8-2，50×23，37公式，按费用明细项目列示（利息支出/收入/汇兑/手续费）
- **Adjustment_L8_3**: 调整分录L8-3
- **NonFinInterest_Calc_L8_4**: 非金融机构利息支出测算表L8-4，28×15，11公式
- **Cutoff_Test_L8_5**: 截止性测试L8-5，36×11（序时账±天数自动提取）
- **FinExpense_Check_L8_6**: 财务费用检查表L8-6
- **Formula_Engine**: 前端公式引擎composable（损益类！取发生额）
- **Interest_Engine**: 利息支出测算引擎（接收L1/L3/L4/L5，纯函数）
- **Cutoff_Engine**: 截止测试引擎（±天数窗口，纯函数）
- **Trial_Balance_Writeback**: 审定数回写（科目6603，发生额口径）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to L8财务费用底稿按sheetName分发, so that 10个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE L8 组件 SHALL 注册新componentType: `l8-financial-expenses`，主入口为 GtL8FinancialExpenses.vue
2. THE GtL8FinancialExpenses.vue SHALL 接收 `sheetName` prop，正则提取编码(L8-1)，v-if分发
3. THE L8 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE L8 组件 SHALL 拆为：l8/core/（审定+明细+调整+附注）、l8/interest/（非金融机构利息测算）、l8/cutoff/（截止测试）、l8/inspection/（检查表）
5. THE L8 组件 SHALL composable分层：useL8FormData + useL8FormulaEngine(纯函数) + useL8InterestEngine(纯函数) + useL8CutoffEngine(纯函数) + useL8CrossSheet + useL8DualMode + useL8ImportExport
6. THE L8 组件 SHALL 在htmlRendererRegistry中注册'l8-financial-expenses'
7. THE L8 组件 SHALL 在wp_code_overrides.json中将L8/L8-1~L8-6/L8A映射为'l8-financial-expenses'
8. THE L8 组件 SHALL 在VALID_COMPONENT_TYPES中注册'l8-financial-expenses'
9. THE GtL8FinancialExpenses.vue SHALL 支持selfLoad
10. THE L8 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"L8-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表L8-1（损益类！取发生额）

**User Story:** As a 审计助理, I want to 在精美审定表中查看财务费用数据, so that 我能验证损益类科目的本期发生额。

#### Acceptance Criteria

1. THE Adjudication_L8_1 SHALL 渲染为单区块：财务费用(损益类/取发生额，按费用明细项目分类+小计)
2. THE Adjudication_L8_1 SHALL 显示列：项目 | 本期发生额 | 上期发生额 | 变动 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL **损益类取发生额**：本期发生额从tb_ledger取（借方发生-贷方发生），**不是期末余额**（与L1~L7负债类根本不同）
5. THE Adjudication_L8_1 SHALL 与L8-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(6603，发生额口径)+发布'substantive:adjudicated'
7. THE Adjudication_L8_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表L8-2（按费用明细项目列示）

**User Story:** As a 审计助理, I want to 管理财务费用明细, so that 利息支出/收入/汇兑/手续费可追溯。

#### Acceptance Criteria

1. THE Detail_L8_2 SHALL 显示列：费用项目(利息支出/利息收入/汇兑损益/手续费/其他) | 本期发生额 | 上期发生额 | 变动 | 变动率 | 说明
2. THE Detail_L8_2 SHALL 自动计算：净财务费用=利息支出-利息收入+汇兑损益+手续费+其他
3. THE Detail_L8_2 SHALL 自动计算变动率=(本期-上期)/上期×100%
4. WHEN |变动率|>阈值时 SHALL 高亮（异常波动）
5. THE Detail_L8_2 SHALL 23列宽表拆分：费用项目/金额分析区段Tab（行同步）
6. THE Detail_L8_2 SHALL 与审定表L8-1交叉验证

### Requirement 4: 利息支出测算（接收L1/L3/L4/L5联动）

**User Story:** As a 审计助理, I want to 核对财务费用利息支出与筹资循环各底稿, so that 利息支出完整准确。

#### Acceptance Criteria

1. THE Interest_Engine SHALL 接收L1短期借款利息测算（订阅'l1:interest-calculated'）
2. THE Interest_Engine SHALL 接收L3长期借款利息测算（订阅'l3:interest-calculated'）
3. THE Interest_Engine SHALL 接收L4应付债券利息费用（订阅'l4:interest-calculated'）
4. THE Interest_Engine SHALL 接收L5未确认融资费用摊销（订阅'l5:amortization-calculated'）
5. THE L8 SHALL 汇总各来源利息 → 测算利息支出合计
6. THE L8 SHALL 计算测算利息支出vs账面利息支出差异
7. WHEN |差异|>阈值时 SHALL 红色高亮
8. THE L8 SHALL 通过cross_wp_references关联L1、L3、L4、L5，ref_index chip可跳转

### Requirement 5: 非金融机构利息支出测算表L8-4

**User Story:** As a 审计助理, I want to 测算非金融机构借款利息支出, so that 利息扣除限额合规性得到验证。

#### Acceptance Criteria

1. THE NonFinInterest_Calc_L8_4 SHALL 显示：借款方 | 本金 | 约定利率 | 同期金融机构利率 | 账载利息 | 可扣除利息 | 超标利息
2. THE Interest_Engine SHALL 计算可扣除利息=本金×同期金融机构利率×天数/360
3. THE Interest_Engine SHALL 计算超标利息=账载利息-可扣除利息
4. WHEN 超标利息>0时 SHALL 橙色高亮（税务调整提示）

### Requirement 6: 截止性测试L8-5（序时账±天数自动提取）

**User Story:** As a 审计助理, I want to 对财务费用做截止测试, so that 期末前后费用归属期间正确。

#### Acceptance Criteria

1. THE Cutoff_Test_L8_5 SHALL 集成截止自动提取（useCutoffAutoSampling→序时账±天数）
2. THE Cutoff_Engine SHALL 提取报告日前后N天的财务费用序时账明细
3. THE Cutoff_Test_L8_5 SHALL 显示：凭证号 | 日期 | 摘要 | 金额 | 应归属期间 | 实际入账期间 | 是否跨期
4. WHEN 应归属期间≠实际入账期间时 SHALL 红色高亮（跨期错误）
5. THE Cutoff_Test_L8_5 SHALL 支持行级抽凭（GtVoucherSamplingEngine）

### Requirement 7: 检查表L8-6 + 调整分录L8-3 + 附注

**User Story:** As a 审计助理, I want to 完成财务费用检查并管理调整和附注, so that 审计结论完整。

#### Acceptance Criteria

1. THE FinExpense_Check_L8_6 SHALL 提供核对清单+审计结论区（el-card包裹）+ AI辅助
2. THE FinExpense_Check_L8_6 SHALL 每个文本section标题行右侧放AI辅助按钮
3. THE Adjustment_L8_3 SHALL 借贷平衡校验+EventBus+双向同步L8-1
4. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
5. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 8: 引擎（损益类+利息+截止，纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现纯函数引擎并集成标准能力, so that 计算可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(u, a, r)=u+a+r
2. THE Formula_Engine SHALL **calcOccurrence(debitOccur, creditOccur)**：损益类本期发生额=借方发生-贷方发生（费用为借方）
3. THE Formula_Engine SHALL calcNetFinanceExpense(interestExp, interestInc, fx, fee, other)=利息支出-利息收入+汇兑+手续费+其他
4. THE Formula_Engine SHALL calcChangeRate(current, prior)=(current-prior)/prior×100
5. THE Interest_Engine SHALL calcDeductibleInterest(principal, benchmarkRate, days)=本金×基准利率×天数/360
6. THE Interest_Engine SHALL calcExcessInterest(booked, deductible)=booked-deductible
7. THE Cutoff_Engine SHALL isCrossPeriod(attributionPeriod, bookingPeriod): 是否跨期
8. THE L8 SHALL 支持双模式 + 导入导出三级（useL8ImportExport，http带Authorization）
9. THE L8 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
