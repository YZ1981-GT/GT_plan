# Requirements Document

## Introduction

G6其他债权投资(main组)底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g6-other-bond-investment-main`，覆盖源模板21个sheet中的8个sheet（核心组）。科目1503其他债权投资（借方/资产类）。**G循环中公允价值计量最复杂的科目**，同时包含公允价值变动和ECL减值的双重影响，审定表需同时反映公允价值调整和减值准备。

源模板按三组拆分，本spec覆盖主体部分（程序表+审定表+附注+明细+坏账准备+调整分录+底稿目录）。

**三组拆分边界**：
| 组 | spec | 覆盖sheet |
|----|------|-----------|
| main(本spec) | g6-other-bond-investment-main | G6A+G6-1+附注(上市/国企)+G6-2+G6-3+G6-4+底稿目录（8sheet） |
| SPPI | g6-other-bond-investment-sppi | G6-5公允价值+G6-6利息+G6-7业务模式+G6-8合同现金流+G6-9盘点+G6-10倒轧（6sheet） |
| ECL | g6-other-bond-investment-ecl | G6-11三阶段+G6-12减值测算+G6-13 ECL计量+G6-14转回核销+G6-15凭证检查（5sheet） |

**本组(main)sheet清单**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 29×8 | 目录页 |
| 2 | 其他债权投资实质性程序表G6A | 34×10 | a-program-console |
| 3 | 审定表G6-1 | 77×11 | 多层审定（成本+公允价值变动+减值+摊余成本） |
| 4 | 附注披露信息（上市公司） | 137×16 | **超大**上市公司附注 |
| 5 | 附注披露信息（国企） | 69×6 | 国企附注 |
| 6 | 明细表G6-2 | 36×33 | **33列超宽表** |
| 7 | 坏账准备明细表G6-3 | 40×20 | 坏账准备按组合/单项 |
| 8 | 调整分录汇总G6-4 | 23×10 | AJE/RJE |

**科目属性**：
- 科目代码：1503 其他债权投资
- 方向：借方（资产类）
- 计量属性：**以公允价值计量且变动计入其他综合收益（FVOCI-Debt）**
- 双重影响：账面价值同时受公允价值变动(OCI)和ECL减值(损益)影响
- 借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额

**关键特色（区别于G4债权投资）**：
1. **FVOCI-Debt双重计量**：公允价值变动→OCI + ECL减值→损益（G4仅摊余成本+ECL）
2. **77行超大审定表**：按成本/利息调整/应计利息/小计/公允价值变动/减值/报表数多层
3. **33列超宽明细表**：比G4(44列)少但仍需3区段Tab拆分
4. **137行超大附注(上市)**：最长的附注表，必须虚拟滚动

**宽表处理策略**：
- G6-1审定表(11列)：分组折叠，77行虚拟滚动
- G6-2明细表(33列)：3区段Tab（基础信息/期初+变动/期末+OCI+减值）
- G6-3坏账准备(20列)：2区段Tab（未审+调整/审定数，同G5-3）

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎(G6A) / ✅ 截止自动提取 / ✅ 附注EventBus / ❌ 行级OCR(本组无凭证表) / ✅ 复核对话

## Glossary

- **Other_Bond_Investment**: 其他债权投资，以公允价值计量且变动计入其他综合收益的债权工具（FVOCI-Debt）
- **FVOCI_Debt**: 公允价值计量且变动计入OCI的债权工具，同时需要计提ECL减值
- **Dual_Impact**: 双重影响，其他债权投资账面同时受OCI(公允价值)和P&L(ECL)影响
- **Amortized_Cost_Basis**: 摊余成本基础，其他债权投资的减值按摊余成本口径计算（非公允价值口径）
- **OCI_Cumulative**: OCI累计变动，公允价值变动计入其他综合收益的累计金额

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to G6其他债权投资(main组)按sheetName prop分发。

#### Acceptance Criteria

1.1 THE G6-main组件 SHALL 注册componentType: `g6-other-bond-investment-main`，主入口GtG6OtherBondInvestmentMain.vue
1.2 THE G6-main组件 SHALL defineAsyncComponent懒加载8个子组件
1.3 THE G6-main组件 SHALL 注册四件套（8条wp_code_overrides）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: G6A 实质性程序表

**User Story:** As a 审计助理, I want to 执行其他债权投资实质性程序。

#### Acceptance Criteria

2.1 THE G6A SHALL 复用a-program-console（34行×10列+抽凭+截止自动提取）

### Requirement 3: 审定表G6-1（77行多层，FVOCI-Debt双重计量）

**User Story:** As a 审计助理, I want to 填写其他债权投资审定表, so that 汇总成本/公允价值变动/减值的审定数据。

#### Acceptance Criteria

3.1 THE G6-1审定表 SHALL 77行×11列多层结构：
   - **一、成本**（按投资项目分列）
   - **二、利息调整**
   - **三、应计利息**
   - **四、小计**（=成本+利息调整+应计利息）
   - **五、公允价值变动**（计入OCI）
   - **六、减值准备**
   - **七、报表列示数**（=小计+公允价值变动-减值，或公允价值-减值取较高）
   - **八、一年内到期重分类**
3.2 THE G6-1 SHALL 列结构：项目|期初(未审|调整|审定)|期末(未审|调整|审定)|变动额|变动率|原因分析
3.3 THE G6-1 SHALL 借方科目公式+审定数公式+TB取数(1503)+差异校验+EventBus(accountCode='1503')
3.4 THE G6-1 SHALL 77行启用虚拟滚动+分组折叠
3.5 WHEN |变动率|>20% SHALL 橙色高亮+原因分析必填

### Requirement 4: 附注披露(上市137行/国企69行)

**User Story:** As a 审计助理, I want to 编辑其他债权投资附注披露。

#### Acceptance Criteria

4.1 THE 附注(上市) SHALL 137行×16列（**必须**虚拟滚动）
4.2 THE 附注(国企) SHALL 69行×6列（虚拟滚动）
4.3 THE 附注 SHALL EventBus subscribe/publish联动+AI辅助

### Requirement 5: 明细表G6-2（33列→3区段Tab）

**User Story:** As a 审计助理, I want to 查看其他债权投资逐笔明细, so that 检查每笔投资的成本/公允价值/OCI/减值。

#### Acceptance Criteria

5.1 THE G6-2明细表 SHALL 36行×33列，3区段Tab：
   - **Tab1: 基础信息(10列)**：投资项目|投资种类|面值|票面利率|实际利率|到期日|初始投资日|持有数量|合同条件|公允价值层次
   - **Tab2: 期初+本期变动(12列)**：投资项目|期初成本|期初利息调整|期初应计利息|期初小计|期初公允价值|期初OCI累计|本期增加|本期减少|本期利息收入|本期公允价值变动|本期减值
   - **Tab3: 期末+审定(11列)**：投资项目|期末成本|期末利息调整|期末应计利息|期末小计|期末公允价值|OCI累计|减值准备|审定调整|审定数|索引
5.2 THE Formula_Engine SHALL 计算期末小计 = 期初小计 + 增加 - 减少 + 利息收入
5.3 THE G6-2 SHALL 行同步+动态行增删+导入导出

### Requirement 6: 坏账准备明细表G6-3（20列→2区段Tab）

**User Story:** As a 审计助理, I want to 填写坏账准备明细。

#### Acceptance Criteria

6.1 THE G6-3 SHALL 40行×20列，2区段Tab（未审+调整/审定数），结构同G5-3
6.2 THE Formula_Engine SHALL ECL公式链：③=①×② / ⑥=⑤×②A+①×(②A-②) / ⑦=①+⑤ / ⑧=③+⑥ / ⑨=⑦-⑧
6.3 THE G6-3 SHALL 按Stage分组+行同步+动态行增删+导入导出

### Requirement 7: 调整分录G6-4 + 公式引擎 + 联动 + UI

**User Story:** As a 开发者, I want to 完成G6-main全部技术栈。

#### Acceptance Criteria

7.1 THE G6-4 SHALL 23行×10列标准AJE/RJE+借贷平衡+回写G6-1+动态行+导入导出
7.2 THE Formula_Engine SHALL：calcDebitBalance/calcAdjustedAmount/calcSubtotal(cost,interestAdj,accrued)/calcECLChain/calcChangeRate/isDebitCreditBalanced/parseNum
7.3 THE 5大集成 SHALL（版本链/抽凭/截止/附注EventBus/复核，无OCR因本组无凭证表）
7.4 THE Import_Export SHALL G6-2/G6-3/G6-4（3张表）
7.5 THE AI辅助 SHALL：adjudication-analysis/disclosure-text
7.6 THE 虚拟滚动 SHALL G6-1(77行)/附注上市(137行)/附注国企(69行)
7.7 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 借方余额** — opening + debit - credit

**P2: 审定数** — unadjusted + aje + rje

**P3: 小计=成本+利息调整+应计利息** — calcSubtotal(a,b,c) === a+b+c

**P4: ECL公式链** — ⑥=⑤×②A+①×(②A-②)

**P5: 变动率** — calcChangeRate(0, any) === null

**P6: 借贷平衡** — |SUM(debits)-SUM(credits)| < 0.01

**P7: parseNum** — null/undefined/NaN → 0
