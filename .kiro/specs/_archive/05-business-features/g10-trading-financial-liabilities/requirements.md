# Requirements Document

## Introduction

G10交易性金融负债底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g10-trading-financial-liabilities`，覆盖1个xlsx源模板中的12个有效sheet。科目2201交易性金融负债（**贷方/负债类**）。**G循环中唯一的金融负债科目**，包含衍生金融工具核查（78行复杂问卷）、第三层次公允价值调节等特色审计内容。

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 25×8 | 目录页 |
| 2 | 交易性金融负债实质性程序表G10A | 30×10 | a-program-console |
| 3 | 审定表G10-1 | 63×12 | 多层审定（初始金额+公允价值变动分组） |
| 4 | 附注披露信息（上市公司） | 42×5 | 上市公司附注 |
| 5 | 附注披露信息（国企） | 79×5 | 国企附注（79行，启用虚拟滚动） |
| 6 | 明细表G10-2 | 39×24 | 24列宽表 |
| 7 | 调整分录汇总G10-3 | 23×10 | AJE/RJE |
| 8 | 分类的适当性检查表G10-4 | 28×9 | 分类合规检查 |
| 9 | 公允价值测试表G10-5 | 39×18 | Level1/2/3测试 |
| 10 | 第三层次公允价值计量的调节表G10-6 | 23×13 | L3调节表 |
| 11 | 凭证检查表G10-7 | 99×17 | 凭证检查+OCR |
| 12 | 衍生金融工具核查表G10-8 | 78×10 | **特色**：衍生工具复杂问卷 |

**科目属性**：
- 科目代码：2201 交易性金融负债
- 方向：**贷方（负债类）**
- 计量属性：公允价值计量且变动计入当期损益
- **贷方科目公式：期末未审 = 期初审定 + 贷方发生额 - 借方发生额**

**关键特色**：
1. **贷方科目**：公式方向与借方科目相反（期末=期初+贷方-借方）
2. **衍生金融工具核查(G10-8)**：78行复杂问卷式，含嵌入衍生工具判断、套期关系检查
3. **63行多层审定**：按初始金额/公允价值变动分组
4. **分类适当性检查(G10-4)**：问卷式，验证负债分类合规性

**宽表处理策略**：
- G10-2明细表(24列)：2区段Tab（基础信息/公允价值+分类）
- G10-5公允价值测试(18列)：2区段Tab（基础+审定/估值详情）
- G10-7凭证检查(17列)：3区段Tab（凭证基础/核对内容/结论）

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎 / ✅ 截止自动提取 / ✅ 附注EventBus / ✅ 行级OCR / ✅ 复核对话

## Glossary

- **Trading_Financial_Liabilities**: 交易性金融负债，以公允价值计量且变动计入当期损益的金融负债（发行的交易性债券、卖出回购、衍生金融负债等）
- **Derivative_Financial_Instrument**: 衍生金融工具，价值随标的资产变动的金融合约（远期/期权/互换/期货）
- **Embedded_Derivative**: 嵌入衍生工具，嵌入非衍生工具主合同中的衍生金融工具成分
- **Credit_Direction**: 贷方科目，期末=期初+贷方-借方（负债类）
- **Classification_Appropriateness**: 分类适当性，金融负债是否正确分类为以公允价值计量
- **Level3_Reconciliation**: 第三层次调节表

## Requirements

### Requirement 1: 组件架构与sheetName分发设计

**User Story:** As a 开发者, I want to G10交易性金融负债底稿按sheetName prop分发, so that 12个有效sheet通过统一入口有序组织。

#### Acceptance Criteria

1.1 THE G10组件 SHALL 注册新componentType: `g10-trading-financial-liabilities`，主入口GtG10TradingFinancialLiabilities.vue
1.2 THE G10组件 SHALL defineAsyncComponent懒加载12个子组件
1.3 THE G10组件 SHALL 注册四件套（htmlRendererRegistry + wp_code_overrides(12条) + VALID_COMPONENT_TYPES + RENDERER_DISPATCH）
1.4 IF htmlData为null THEN selfLoad模式；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: G10A 实质性程序表

**User Story:** As a 审计助理, I want to 执行交易性金融负债实质性程序, so that 按步骤完成审计程序。

#### Acceptance Criteria

2.1 THE G10A程序表 SHALL 复用a-program-console（30行×10列+抽凭+截止自动提取）

### Requirement 3: 审定表G10-1（63行多层结构，贷方科目）

**User Story:** As a 审计助理, I want to 填写交易性金融负债审定表, so that 汇总审定数据并回写试算表。

#### Acceptance Criteria

3.1 THE G10-1审定表 SHALL 显示63行×12列，按分组：
   - **(一)初始金额**：交易性金融负债/卖出回购/衍生金融负债等
   - **(二)公允价值变动**
   - **合计**
3.2 THE G10-1 SHALL 列结构：项目|期初(未审|账项调整|审定)|期末(未审|账项调整|审定)|变动额|变动率|原因分析|索引
3.3 THE G10-1 SHALL 实现**贷方科目公式**：期末未审 = 期初审定 + 贷方发生额 - 借方发生额
3.4 THE G10-1 SHALL 审定数 = 未审 + 账项调整
3.5 THE G10-1 SHALL trial_balance取数（科目2201）+ 差异红色高亮
3.6 WHEN 审定数变更 SHALL EventBus发布 `substantive:adjudicated`(accountCode='2201')
3.7 THE G10-1 SHALL 63行启用虚拟滚动+分组折叠
3.8 WHEN |变动率|>20% SHALL 橙色高亮+原因分析必填

### Requirement 4: 附注披露(上市/国企)

**User Story:** As a 审计助理, I want to 编辑交易性金融负债附注披露。

#### Acceptance Criteria

4.1 THE 附注(上市) SHALL 42行×5列
4.2 THE 附注(国企) SHALL 79行×5列（启用虚拟滚动）
4.3 THE 附注 SHALL EventBus subscribe/publish联动

### Requirement 5: 明细表G10-2（24列→2区段Tab）

**User Story:** As a 审计助理, I want to 查看交易性金融负债逐笔明细。

#### Acceptance Criteria

5.1 THE G10-2 SHALL 39行×24列，2区段Tab：
   - **Tab1: 基础信息(12列)**：负债名称|负债类型(下拉)|对手方|合同日|到期日|初始金额|期初余额|期初审定|本期增加|本期减少|期末余额|审定数
   - **Tab2: 公允价值+分类(12列)**：负债名称|公允价值层次|估值方法|期初公允价值|期末公允价值|公允价值变动|计入损益金额|是否衍生工具|主合同描述|嵌入衍生判断|发函情况|备注
5.2 THE G10-2 SHALL 行同步+动态行增删+导入导出

### Requirement 6: 调整分录汇总G10-3 + 分类适当性检查G10-4

**User Story:** As a 审计助理, I want to 录入调整分录并检查分类适当性。

#### Acceptance Criteria

6.1 THE G10-3 SHALL 23行×10列标准AJE/RJE+借贷平衡+回写审定表
6.2 THE G10-4分类检查表 SHALL 28行×9列问卷式：
   - 列结构：序号|检查项目|审计要求|管理层回复(textarea)|是否合规(下拉)|结论(textarea)|索引
6.3 THE G10-4 SHALL 顶部方法论上下文+每section AI辅助+底部审计结论
6.4 THE G10-3 SHALL 动态行增删+导入导出

### Requirement 7: 公允价值测试G10-5 + 第三层次调节表G10-6

**User Story:** As a 审计助理, I want to 测试公允价值并编制L3调节表。

#### Acceptance Criteria

7.1 THE G10-5 SHALL 39行×18列，2区段Tab（基础+审定/估值详情），Level3必填校验
7.2 THE G10-6 SHALL 23行×13列L3调节表：负债名称|期初|本期新增|本期终止|转入L3|转出L3|公允价值变动|利息费用|其他|期末|差异(公式)
7.3 THE Formula_Engine SHALL calcL3Reconciliation = 期初+新增-终止+转入-转出+FV变动+利息+其他
7.4 THE G10-5/G10-6 SHALL 动态行增删+导入导出+AI辅助

### Requirement 8: 凭证检查表G10-7（17列→3区段Tab）

**User Story:** As a 审计助理, I want to 检查交易性金融负债凭证。

#### Acceptance Criteria

8.1 THE G10-7 SHALL 99行×17列，3区段Tab（凭证基础/核对内容/结论）
8.2 THE G10-7 SHALL 抽凭引擎+行级OCR+虚拟滚动(99行)+借贷平衡校验
8.3 THE G10-7 SHALL 动态行增删+导入导出+GtIndexChip

### Requirement 9: 衍生金融工具核查表G10-8（78行问卷式）

**User Story:** As a 审计助理, I want to 核查衍生金融工具, so that 我能验证衍生工具分类、嵌入判断和套期关系。

#### Acceptance Criteria

9.1 THE G10-8衍生工具核查表 SHALL 显示78行×10列，分为多个检查section（问卷式）：
   - **(一) 衍生金融工具基本信息**：工具类型/对手方/合同条款
   - **(二) 嵌入衍生工具判断**：主合同分析+拆分必要性
   - **(三) 公允价值计量**：估值方法+输入值验证
   - **(四) 套期关系检查**：是否指定套期+有效性测试
   - **(五) 披露完整性**：衍生工具相关披露检查
9.2 THE G10-8 SHALL 列结构：序号|检查区域|检查项目|审计要求(方法论)|检查结果(textarea)|是否合规(下拉)|风险等级|审计结论|索引|备注
9.3 THE G10-8 SHALL 78行启用虚拟滚动
9.4 THE G10-8 SHALL 每个section标题行右侧AI辅助按钮
9.5 THE G10-8 SHALL 底部包含综合审计结论textarea + 编制提示details折叠区
9.6 THE G10-8 SHALL 顶部方法论上下文（琥珀色左边线）显示衍生工具五要素定义

### Requirement 10: 公式引擎+联动+导入导出+UI

**User Story:** As a 开发者, I want to 实现G10完整技术栈。

#### Acceptance Criteria

10.1 THE Formula_Engine SHALL 实现：**calcCreditBalance**(opening, credit, debit) = opening + credit - debit（贷方公式）/ calcAdjustedAmount / calcChangeRate / isDebitCreditBalanced / calcL3Reconciliation / parseNum
10.2 THE 6大集成 SHALL 全部集成
10.3 THE Import_Export SHALL 对G10-2/G10-3/G10-5/G10-6/G10-7支持导入导出
10.4 THE AI辅助 SHALL：adjudication-analysis/classification-conclusion/fair-value-conclusion/derivative-conclusion/voucher-conclusion
10.5 THE 虚拟滚动 SHALL G10-1(63行)/G10-7(99行)/G10-8(78行)/附注国企(79行)
10.6 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 贷方余额公式** — ∀ opening, credit, debit ∈ ℝ≥0: calcCreditBalance(opening, credit, debit) === opening + credit - debit

**P2: 审定数公式** — ∀ unadjusted, adjustment ∈ ℝ: calcAdjustedAmount(unadjusted, adjustment) === unadjusted + adjustment

**P3: L3调节表恒等** — ∀ 各变动项: calcL3Reconciliation === 期初+新增-终止+转入-转出+FV变动+利息+其他

**P4: 贷方与借方方向相反** — ∀ opening, amount ∈ ℝ≥0: calcCreditBalance(opening, amount, 0) === calcDebitBalance(opening, 0, -amount) + 2*amount（验证方向逻辑）

**P5: 变动率方向性** — calcChangeRate(0, any) === null

**P6: 借贷平衡恒等** — |SUM(debits)-SUM(credits)| < 0.01

**P7: parseNum健壮性** — null/undefined/NaN/'' → 0
