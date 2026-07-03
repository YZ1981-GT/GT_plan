# Requirements Document

## Introduction

G14信用减值损失底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g14-credit-impairment-loss`，覆盖1个xlsx源模板中的6个有效sheet（排除"修订前"sheet）。科目6702信用减值损失（**损益类/借方**）。**G循环中信用风险管理核心科目**，汇总各金融资产ECL减值计提/转回的净损失，与D1/D5/G2/G4/G5/G6各科目减值数据交叉验证。

**源模板sheet清单（openpyxl实读确认，排除修订前sheet）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 21×8 | 目录页 |
| 2 | 信用减值损失审计程序表G14A | 22×10 | a-program-console |
| 3 | 审定表G14-1 | 36×11 | 按减值来源科目分层 |
| 4 | 附注披露信息（上市公司） | 18×5 | 上市公司附注 |
| 5 | 附注披露信息（国企） | 15×7 | 国企附注 |
| 6 | 明细表G14-2 | 36×13 | 减值损失来源明细 |
| 7 | 调整分录汇总G14-3 | 24×10 | AJE/RJE |

**排除sheet**：信用减值损失审计程序表G14A-修订前(46×9) — 历史版本不渲染

**科目属性**：
- 科目代码：6702 信用减值损失
- 方向：**借方（损益类/费用类）**
- 损益类公式：本期发生额=借方-贷方（损失为正）

**关键特色**：
1. **最简洁的G循环科目之一**：仅7个sheet（含排除），无凭证检查表
2. **交叉验证核心**：G14的明细应与D1应收票据/D5应收融资/G2应收利息/G4债权投资/G5长期应收款/G6其他债权投资各科目的减值计提数据勾稽
3. **按减值来源科目分层审定**：应收账款/其他应收/应收票据/应收融资/债权投资/其他债权投资/长期应收款/应收利息等

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎(G14A程序表) / ✅ 截止自动提取 / ✅ 附注EventBus / ❌ 行级OCR(无凭证检查表) / ✅ 复核对话

## Glossary

- **Credit_Impairment_Loss**: 信用减值损失，因金融资产预期信用损失(ECL)计提/转回产生的当期损益
- **ECL_Cross_Verification**: ECL交叉验证，G14明细与各源科目(D1/D5/G2/G4/G5/G6)的减值计提数据勾稽
- **Debit_Direction_PL**: 借方损益（费用类），本期发生额=借方-贷方

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to G14信用减值损失底稿按sheetName prop分发。

#### Acceptance Criteria

1.1 THE G14组件 SHALL 注册componentType: `g14-credit-impairment-loss`，主入口GtG14CreditImpairmentLoss.vue
1.2 THE G14组件 SHALL defineAsyncComponent懒加载6个子组件
1.3 THE G14组件 SHALL 注册四件套（7个wp_code条目）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: G14A + 审定表G14-1 + 附注

**User Story:** As a 审计助理, I want to 执行程序表并填写审定表。

#### Acceptance Criteria

2.1 THE G14A SHALL 复用a-program-console（22行×10列+抽凭+截止）
2.2 THE G14-1审定表 SHALL 36行×11列：项目|本期(未审|调整|审定)|上期(未审|调整|审定)|变动额|变动率|原因分析|索引
2.3 THE G14-1 SHALL 按减值来源科目分组：
   - 应收账款信用减值损失
   - 其他应收款信用减值损失
   - 应收票据信用减值损失
   - 应收款项融资信用减值损失
   - 债权投资信用减值损失
   - 其他债权投资信用减值损失
   - 长期应收款信用减值损失
   - 应收利息信用减值损失
   - 合计
2.4 THE G14-1 SHALL 损益类公式（借方费用类：审定=未审+调整）+trial_balance取数(6702)+EventBus发布(accountCode='6702')
2.5 WHEN |变动率|>20% SHALL 橙色高亮+原因分析必填
2.6 THE 附注(上市18行×5列/国企15行×7列) SHALL EventBus联动+AI辅助

### Requirement 3: 明细表G14-2

**User Story:** As a 审计助理, I want to 查看信用减值损失来源明细, so that 能核实各科目ECL计提/转回金额并与源科目交叉验证。

#### Acceptance Criteria

3.1 THE G14-2 SHALL 36行×13列：来源科目|来源科目代码|被评估资产|计提方式(组合/单项)|期初坏账准备|本期计提|本期转回|本期核销|期末坏账准备|本期信用减值损失(公式)|上期信用减值损失|源科目索引|交叉验证结论(下拉)
3.2 THE Formula_Engine SHALL 计算本期信用减值损失 = 本期计提 - 本期转回（即净计提额）
3.3 THE Formula_Engine SHALL 验证：期末坏账准备 = 期初 + 本期计提 - 本期转回 - 本期核销
3.4 WHEN 坏账准备滚动不平衡时（|期初+计提-转回-核销-期末| > 0.01）, THE 系统 SHALL 红色高亮
3.5 THE G14-2 SHALL 按来源科目分组小计+总计
3.6 THE G14-2 SHALL 总计信用减值损失应与G14-1审定表合计一致，不一致时红色提示
3.7 THE G14-2 SHALL 支持动态行增删+导入导出

### Requirement 4: 调整分录G14-3 + 公式引擎+联动+UI

**User Story:** As a 开发者, I want to 完成G14全部技术栈。

#### Acceptance Criteria

4.1 THE G14-3 SHALL 24行×10列标准AJE/RJE+借贷平衡+回写审定表+动态行增删+导入导出
4.2 THE Formula_Engine SHALL：calcAdjustedAmount / calcNetImpairmentLoss / calcProvisionRollForward / calcChangeRate / isDebitCreditBalanced / parseNum（6个纯函数）
4.3 THE calcNetImpairmentLoss(provision, reversal) SHALL 返回 provision - reversal（净计提=计提-转回）
4.4 THE calcProvisionRollForward(opening, provision, reversal, writeoff) SHALL 返回 opening + provision - reversal - writeoff（坏账准备滚动）
4.5 THE 5大集成 SHALL（版本链/抽凭/截止/附注EventBus/复核，无OCR因无凭证检查表）
4.6 THE Import_Export SHALL G14-2/G14-3（2张表）
4.7 THE AI辅助 SHALL：adjudication-analysis/impairment-conclusion
4.8 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 审定数** — ∀ unadjusted, adj ∈ ℝ: calcAdjustedAmount === unadjusted + adj

**P2: 净信用减值损失** — ∀ provision, reversal ∈ ℝ≥0: calcNetImpairmentLoss(provision, reversal) === provision - reversal

**P3: 坏账准备滚动恒等** — ∀ opening, provision, reversal, writeoff ∈ ℝ≥0: calcProvisionRollForward(opening, provision, reversal, writeoff) === opening + provision - reversal - writeoff

**P4: 坏账准备滚动验证** — WHEN calcProvisionRollForward(...) === 期末坏账准备 THEN 滚动平衡

**P5: 变动率方向性** — calcChangeRate(0, any) === null

**P6: 借贷平衡** — |SUM(debits)-SUM(credits)| < 0.01

**P7: parseNum健壮性** — null/undefined/NaN/'' → 0
