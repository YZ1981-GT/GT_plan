# Requirements Document

## Introduction

G11投资收益底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g11-investment-income`，覆盖1个xlsx源模板中的9个有效sheet（排除"修订前"sheet）。科目6111投资收益（**损益类/贷方**）。**G循环中投资回报核实的核心科目**，含收益率分析（投入产出比）等特色审计内容。

**源模板sheet清单（openpyxl实读确认，排除修订前sheet）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 21×7 | 目录页 |
| 2 | 投资收益实质性程序表G11A | 22×10 | a-program-console |
| 3 | 审定表G11-1 | 79×11 | 按投资类型分层（权益法/处置/交易性/债权/其他） |
| 4 | 附注披露信息（上市公司） | 34×5 | 上市公司附注 |
| 5 | 附注披露信息（国企） | 26×4 | 国企附注 |
| 6 | 明细分析表G11-2 | 39×13 | 投资收益分类明细 |
| 7 | 调整分录汇总G11-3 | 23×10 | AJE/RJE |
| 8 | 收益率分析表G11-4 | 31×10 | **特色**：投入产出+收益率验证 |
| 9 | 凭证检查表G11-5 | 45×17 | 凭证检查 |

**排除sheet**：投资收益实质性程序表G11A-修订前(34×11) — 历史版本不渲染

**科目属性**：
- 科目代码：6111 投资收益
- 方向：**贷方（损益类）**
- 损益类特殊：审定表列为"本期数/上期数"（非期初/期末），取发生额非余额
- **损益类公式：本期发生额从tb_ledger取**

**关键特色**：
1. **损益类审定表**：列为"本期(未审|调整|审定) / 上期(未审|调整|审定)"，非资产负债表科目的期初/期末模式
2. **79行多层按投资类型**：权益法/处置长投/交易性/债权/FVOCI处置/衍生等
3. **收益率分析(G11-4)**：各投资项目收益率 = 投资收益 / 平均投资余额，异常波动分析

**宽表处理策略**：
- G11-2明细分析(13列)：单表（列数适中，无需拆分）
- G11-4收益率分析(10列)：单表
- G11-5凭证检查(17列)：3区段Tab（凭证基础/核对内容/结论）

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎 / ✅ 截止自动提取 / ✅ 附注EventBus / ✅ 行级OCR(G11-5) / ✅ 复核对话

## Glossary

- **Investment_Income**: 投资收益，企业因投资活动产生的收入（权益法确认/处置利得/利息收入/股利收入等）
- **Income_Statement_Account**: 损益类科目，审定表按"本期/上期"比较，取发生额（非余额）
- **Return_Rate_Analysis**: 收益率分析，投资收益/平均投资余额×100%，用于识别异常投资回报
- **Equity_Method_Income**: 权益法确认的投资收益（长期股权投资按被投资单位净利润×持股比例）
- **Credit_Direction_PL**: 损益类贷方科目，本期发生额=贷方-借方

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to G11投资收益底稿按sheetName prop分发。

#### Acceptance Criteria

1.1 THE G11组件 SHALL 注册componentType: `g11-investment-income`，主入口GtG11InvestmentIncome.vue
1.2 THE G11组件 SHALL defineAsyncComponent懒加载9个子组件
1.3 THE G11组件 SHALL 注册四件套（10个wp_code条目，含排除修订前sheet）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: G11A 实质性程序表

**User Story:** As a 审计助理, I want to 执行投资收益实质性程序。

#### Acceptance Criteria

2.1 THE G11A程序表 SHALL 复用a-program-console（22行×10列+抽凭+截止自动提取）

### Requirement 3: 审定表G11-1（79行多层，损益类科目）

**User Story:** As a 审计助理, I want to 填写投资收益审定表, so that 我能按投资类型汇总本期收益审定数据。

#### Acceptance Criteria

3.1 THE G11-1审定表 SHALL 显示79行×11列，按投资类型分组：
   - 权益法核算的长期股权投资收益
   - 处置长期股权投资产生的投资收益
   - 处置划分为持有待售资产的长投收益
   - 交易性金融资产持有期间/处置收益
   - 债权投资持有期间/处置收益
   - 其他债权投资持有期间/处置/重分类收益
   - 其他权益工具投资股利收益
   - 其他非流动金融资产持有/处置收益
   - 合计
3.2 THE G11-1 SHALL 列结构：项目|本期(未审|账项调整|审定)|上期(未审|账项调整|审定)|变动额|变动率|原因分析|索引
3.3 THE G11-1 SHALL 实现**损益类公式**：本期审定 = 本期未审 + 账项调整（取发生额，不是余额递推）
3.4 THE G11-1 SHALL trial_balance取数（科目6111，取发生额字段）
3.5 THE G11-1 SHALL 变动率 = (本期审定 - 上期审定) / |上期审定|
3.6 WHEN 审定数变更 SHALL EventBus发布 `substantive:adjudicated`(accountCode='6111')
3.7 THE G11-1 SHALL 79行启用虚拟滚动+分组折叠
3.8 WHEN |变动率|>20% SHALL 橙色高亮+原因分析必填

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 编辑投资收益附注披露。

#### Acceptance Criteria

4.1 THE 附注(上市) SHALL 34行×5列
4.2 THE 附注(国企) SHALL 26行×4列
4.3 THE 附注 SHALL EventBus subscribe/publish联动+AI辅助

### Requirement 5: 明细分析表G11-2

**User Story:** As a 审计助理, I want to 查看投资收益分类明细, so that 能核实各类投资收益的来源和金额。

#### Acceptance Criteria

5.1 THE G11-2 SHALL 39行×13列：投资项目名称|投资类型(下拉)|被投资单位|持股比例|投资余额|本期投资收益|上期投资收益|变动额|变动率|收益来源说明(textarea)|是否关联方|索引|备注
5.2 THE G11-2 SHALL 按投资类型分组小计+总计
5.3 THE Formula_Engine SHALL 计算变动率 = (本期-上期)/|上期|
5.4 THE G11-2 SHALL 支持动态行增删+导入导出

### Requirement 6: 调整分录汇总G11-3

**User Story:** As a 审计助理, I want to 录入投资收益调整分录。

#### Acceptance Criteria

6.1 THE G11-3 SHALL 23行×10列标准AJE/RJE+借贷平衡+回写审定表+动态行增删+导入导出

### Requirement 7: 收益率分析表G11-4

**User Story:** As a 审计助理, I want to 分析各投资项目收益率, so that 我能识别异常投资回报并追查原因。

#### Acceptance Criteria

7.1 THE G11-4收益率分析表 SHALL 31行×10列：投资项目|投资类型|期初投资余额|期末投资余额|平均投资余额(公式)|本期投资收益|收益率(公式)|上期收益率|收益率变动|异常说明(textarea)
7.2 THE Formula_Engine SHALL 计算平均投资余额 = (期初+期末) / 2
7.3 THE Formula_Engine SHALL 计算收益率 = 本期投资收益 / 平均投资余额 × 100%（平均余额为0时返回null）
7.4 THE Formula_Engine SHALL 计算收益率变动 = 本期收益率 - 上期收益率
7.5 WHEN |收益率变动| > 5个百分点时, THE 系统 SHALL 橙色高亮该行提示"收益率异常波动"
7.6 THE G11-4 SHALL 底部包含审计结论textarea（带AI辅助）+ 编制提示details折叠区
7.7 THE G11-4 SHALL 支持动态行增删（ElMessageBox.prompt输入投资项目名称）+ 导入导出

### Requirement 8: 凭证检查表G11-5

**User Story:** As a 审计助理, I want to 检查投资收益凭证。

#### Acceptance Criteria

8.1 THE G11-5 SHALL 45行×17列，3区段Tab（凭证基础/核对内容/结论）
8.2 THE G11-5 SHALL 抽凭引擎+行级OCR+借贷平衡校验
8.3 THE G11-5 SHALL 动态行增删+导入导出+GtIndexChip

### Requirement 9: 公式引擎+联动+UI

**User Story:** As a 开发者, I want to 实现G11公式引擎和完整集成。

#### Acceptance Criteria

9.1 THE Formula_Engine SHALL 实现：calcAdjustedAmount / calcChangeRate / calcAverageBalance / calcReturnRate / isDebitCreditBalanced / parseNum
9.2 THE calcReturnRate(income, avgBalance) SHALL 返回 avgBalance===0 ? null : income/avgBalance
9.3 THE 6大集成 SHALL 全部集成
9.4 THE Import_Export SHALL 对G11-2/G11-3/G11-4/G11-5支持导入导出
9.5 THE AI辅助 SHALL：adjudication-analysis/return-rate-conclusion/voucher-conclusion
9.6 THE 虚拟滚动 SHALL G11-1(79行)
9.7 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 审定数公式** — ∀ unadjusted, adj ∈ ℝ: calcAdjustedAmount(unadjusted, adj) === unadjusted + adj

**P2: 平均余额** — ∀ opening, closing ∈ ℝ≥0: calcAverageBalance(opening, closing) === (opening+closing)/2

**P3: 收益率公式** — ∀ income ∈ ℝ, avgBalance > 0: calcReturnRate(income, avgBalance) === income/avgBalance

**P4: 收益率除零保护** — calcReturnRate(any, 0) === null

**P5: 变动率方向性** — calcChangeRate(0, any) === null

**P6: 借贷平衡恒等** — |SUM(debits)-SUM(credits)| < 0.01

**P7: parseNum健壮性** — null/undefined/NaN/'' → 0
