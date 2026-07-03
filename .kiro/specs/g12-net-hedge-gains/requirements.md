# Requirements Document

## Introduction

G12净敞口套期收益底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g12-net-hedge-gains`，覆盖1个xlsx源模板中的9个有效sheet（排除"修订前"sheet）。科目6103净敞口套期收益/损失（**损益类**）。**G循环中套期会计审计最复杂的科目**，含风险净敞口检查（79行复杂问卷）、套期公允价值测试等特色审计内容。

**源模板sheet清单（openpyxl实读确认，排除修订前sheet）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 23×8 | 目录页 |
| 2 | 净敞口套期收益审计程序表G12A | 35×10 | a-program-console |
| 3 | 审定表G12-1 | 23×11 | 套期收益审定 |
| 4 | 附注披露信息（上市公司） | 12×5 | 上市公司附注 |
| 5 | 附注披露信息（国企） | 11×5 | 国企附注 |
| 6 | 明细表G12-2 | 25×15 | 套期关系明细 |
| 7 | 调整分录汇总G12-3 | 23×10 | AJE/RJE |
| 8 | 公允价值测试表G12-4 | 29×18 | 套期工具公允价值测试 |
| 9 | 风险净敞口检查表G12-5 | 79×10 | **特色**：套期有效性+净敞口问卷 |
| 10 | 凭证检查表G12-6 | 90×19 | 凭证检查+OCR |

**排除sheet**：净敞口套期收益审计程序表G12A-修订前(63×11) — 历史版本不渲染

**科目属性**：
- 科目代码：6103 净敞口套期收益/损失
- 方向：损益类（借贷双向）
- 损益类公式：本期发生额=贷方-借方（净收益为正）

**关键特色**：
1. **风险净敞口检查(G12-5)**：79行复杂问卷，检查套期关系指定/有效性测试/净敞口计算
2. **套期公允价值测试(G12-4)**：18列测试套期工具和被套期项目公允价值变动
3. **套期会计三要素**：被套期项目+套期工具+套期关系指定文档

**宽表处理策略**：
- G12-2明细表(15列)：单表（列数适中，可直接渲染）
- G12-4公允价值测试(18列)：2区段Tab（套期工具/被套期项目）
- G12-6凭证检查(19列)：3区段Tab（凭证基础/核对内容/结论）

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎 / ✅ 截止自动提取 / ✅ 附注EventBus / ✅ 行级OCR(G12-6) / ✅ 复核对话

## Glossary

- **Net_Hedge_Gains**: 净敞口套期收益，企业进行净敞口套期产生的公允价值变动损益
- **Hedging_Instrument**: 套期工具，企业用于对冲风险的金融工具（衍生工具或非衍生金融资产/负债）
- **Hedged_Item**: 被套期项目，使企业面临公允价值或现金流量变动风险的资产/负债/承诺/预期交易
- **Hedge_Effectiveness**: 套期有效性，套期工具公允价值变动能否抵销被套期项目的变动
- **Net_Position**: 净敞口/净头寸，被套期项目组合中多头与空头的净额
- **Designation_Documentation**: 套期关系指定文档，企业正式指定套期关系时的书面文件

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to G12净敞口套期收益底稿按sheetName prop分发。

#### Acceptance Criteria

1.1 THE G12组件 SHALL 注册componentType: `g12-net-hedge-gains`，主入口GtG12NetHedgeGains.vue
1.2 THE G12组件 SHALL defineAsyncComponent懒加载9个子组件
1.3 THE G12组件 SHALL 注册四件套（10个wp_code条目）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: G12A + 审定表G12-1 + 附注

**User Story:** As a 审计助理, I want to 执行程序表并填写审定表。

#### Acceptance Criteria

2.1 THE G12A SHALL 复用a-program-console（35行×10列+抽凭+截止）
2.2 THE G12-1审定表 SHALL 23行×11列：项目|本期(未审|调整|审定)|上期(未审|调整|审定)|变动额|变动率|原因分析|索引
2.3 THE G12-1 SHALL 损益类公式+trial_balance取数(6103)+EventBus发布
2.4 THE 附注(上市12行/国企11行) SHALL EventBus联动+AI辅助

### Requirement 3: 明细表G12-2 + 调整分录G12-3

**User Story:** As a 审计助理, I want to 查看套期关系明细并录入调整分录。

#### Acceptance Criteria

3.1 THE G12-2 SHALL 25行×15列：套期关系编号|套期类型(公允价值/现金流量/净投资 下拉)|被套期项目|套期工具|指定日期|到期日|被套期风险|套期比率|本期套期工具FV变动|本期被套期项目FV变动|套期无效部分(公式)|计入损益金额|有效性评估结论(下拉)|索引|备注
3.2 THE Formula_Engine SHALL 计算套期无效部分 = 套期工具FV变动 - 被套期项目FV变动（绝对值）
3.3 THE G12-2 SHALL 动态行增删+导入导出
3.4 THE G12-3 SHALL 23行×10列标准AJE/RJE+借贷平衡+回写审定表

### Requirement 4: 公允价值测试表G12-4（18列→2区段Tab）

**User Story:** As a 审计助理, I want to 测试套期工具和被套期项目公允价值。

#### Acceptance Criteria

4.1 THE G12-4 SHALL 29行×18列，2区段Tab：
   - **Tab1: 套期工具(9列)**：套期关系编号|套期工具名称|工具类型|期初公允价值|期末公允价值|FV变动(公式)|估值方法|公允价值层次|估值来源
   - **Tab2: 被套期项目(9列)**：套期关系编号|被套期项目名称|项目类型|期初公允价值|期末公允价值|FV变动(公式)|风险因素|测试方法|有效性结论
4.2 THE Formula_Engine SHALL 计算FV变动 = 期末公允价值 - 期初公允价值
4.3 THE G12-4 SHALL 行同步+动态行增删+导入导出+AI辅助

### Requirement 5: 风险净敞口检查表G12-5（79行问卷式）

**User Story:** As a 审计助理, I want to 检查风险净敞口和套期有效性, so that 我能验证套期关系的合规性和有效性。

#### Acceptance Criteria

5.1 THE G12-5 SHALL 79行×10列，分为多个检查section（问卷式）：
   - **(一) 套期关系指定**：指定文档完整性/套期目标/风险管理策略
   - **(二) 套期有效性测试**：前瞻性/回顾性测试方法和结果
   - **(三) 净敞口头寸计算**：多头/空头/净敞口金额验证
   - **(四) 再平衡和终止**：套期比率调整/终止确认条件
   - **(五) 会计处理检查**：套期收益/损失的会计处理正确性
5.2 THE G12-5 SHALL 列结构：序号|检查区域|检查项目|审计要求|检查结果(textarea)|是否合规(下拉)|风险等级|结论|索引|备注
5.3 THE G12-5 SHALL 79行启用虚拟滚动
5.4 THE G12-5 SHALL 每section AI辅助+顶部方法论上下文+底部审计结论
5.5 THE G12-5 SHALL 顶部方法论上下文显示CAS24套期会计三要素和有效性条件

### Requirement 6: 凭证检查表G12-6 + 公式引擎+联动+UI

**User Story:** As a 开发者, I want to 完成G12全部技术栈。

#### Acceptance Criteria

6.1 THE G12-6 SHALL 90行×19列，3区段Tab+抽凭+OCR+虚拟滚动+GtIndexChip
6.2 THE Formula_Engine SHALL：calcAdjustedAmount / calcChangeRate / calcFVChange / calcHedgeIneffectiveness / isDebitCreditBalanced / parseNum
6.3 THE calcHedgeIneffectiveness(instrumentChange, itemChange) SHALL 返回 |instrumentChange - itemChange|（套期无效部分=绝对差）
6.4 THE 6大集成 SHALL 全部集成
6.5 THE Import_Export SHALL G12-2/G12-3/G12-4/G12-6（4张表）
6.6 THE AI辅助 SHALL：adjudication-analysis/hedge-effectiveness-conclusion/net-position-conclusion/voucher-conclusion
6.7 THE 虚拟滚动 SHALL G12-5(79行)/G12-6(90行)
6.8 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 审定数公式** — ∀ unadjusted, adj ∈ ℝ: calcAdjustedAmount === unadjusted + adj

**P2: FV变动** — ∀ opening, closing ∈ ℝ: calcFVChange(opening, closing) === closing - opening

**P3: 套期无效部分** — ∀ instChange, itemChange ∈ ℝ: calcHedgeIneffectiveness(instChange, itemChange) === |instChange - itemChange|

**P4: 套期无效部分非负** — ∀ inputs: calcHedgeIneffectiveness(...) ≥ 0

**P5: 变动率方向性** — calcChangeRate(0, any) === null

**P6: 借贷平衡恒等** — |SUM(debits)-SUM(credits)| < 0.01

**P7: parseNum健壮性** — null/undefined/NaN/'' → 0
