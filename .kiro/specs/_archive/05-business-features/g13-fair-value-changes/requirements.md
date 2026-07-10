# Requirements Document

## Introduction

G13公允价值变动收益底稿专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `g13-fair-value-changes`，覆盖1个xlsx源模板中的6个有效sheet（排除"修订前"sheet）。科目6101公允价值变动收益/损失（**损益类**）。**G循环中公允价值计量联动核心科目**，与G1/G8/G9/G10的公允价值变动数据交叉验证。

**源模板sheet清单（openpyxl实读确认，排除修订前sheet）**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 21×8 | 目录页 |
| 2 | 公允价值变动收益审计程序表G13A | 23×10 | a-program-console |
| 3 | 审定表G13-1 | 35×11 | 按金融资产/负债类型分层 |
| 4 | 附注披露信息（上市公司） | 18×5 | 上市公司附注 |
| 5 | 附注披露信息（国企） | 17×5 | 国企附注 |
| 6 | 明细表G13-2 | 34×12 | 公允价值变动来源明细 |
| 7 | 调整分录汇总G13-3 | 22×10 | AJE/RJE |

**排除sheet**：公允价值变动收益审计程序表G13A-修订前(46×11) — 历史版本不渲染

**科目属性**：
- 科目代码：6101 公允价值变动收益/损失
- 方向：损益类（借贷双向，净收益为贷方）
- 损益类公式：本期发生额=贷方-借方

**关键特色**：
1. **最简洁的G循环科目之一**：仅7个sheet（含排除），无凭证检查表
2. **交叉验证核心**：G13的明细应与G1/G8/G9/G10各科目的公允价值变动数据勾稽
3. **明细表(12列)**：列数适中，无需拆分

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎(G13A程序表) / ✅ 截止自动提取 / ✅ 附注EventBus / ❌ 行级OCR(无凭证检查表) / ✅ 复核对话

## Glossary

- **Fair_Value_Changes_PL**: 公允价值变动收益/损失，以公允价值计量且变动计入当期损益的金融资产/负债公允价值变动金额
- **Cross_Verification**: 交叉验证，G13明细与G1/G8/G9/G10各科目公允价值变动数据勾稽一致

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to G13公允价值变动收益底稿按sheetName prop分发。

#### Acceptance Criteria

1.1 THE G13组件 SHALL 注册componentType: `g13-fair-value-changes`，主入口GtG13FairValueChanges.vue
1.2 THE G13组件 SHALL defineAsyncComponent懒加载6个子组件
1.3 THE G13组件 SHALL 注册四件套（7个wp_code条目）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: G13A + 审定表G13-1 + 附注

**User Story:** As a 审计助理, I want to 执行程序表并填写审定表。

#### Acceptance Criteria

2.1 THE G13A SHALL 复用a-program-console（23行×10列+抽凭+截止）
2.2 THE G13-1审定表 SHALL 35行×11列：项目|本期(未审|调整|审定)|上期(未审|调整|审定)|变动额|变动率|原因分析|索引
2.3 THE G13-1 SHALL 按金融资产/负债类型分组：
   - 交易性金融资产公允价值变动
   - 交易性金融负债公允价值变动
   - 指定以公允价值计量的金融资产变动
   - 衍生金融工具公允价值变动
   - 其他
   - 合计
2.4 THE G13-1 SHALL 损益类公式+trial_balance取数(6101)+EventBus发布(accountCode='6101')
2.5 WHEN |变动率|>20% SHALL 橙色高亮+原因分析必填
2.6 THE 附注(上市18行/国企17行) SHALL EventBus联动+AI辅助

### Requirement 3: 明细表G13-2

**User Story:** As a 审计助理, I want to 查看公允价值变动来源明细, so that 能核实各金融工具的公允价值变动金额并与源科目交叉验证。

#### Acceptance Criteria

3.1 THE G13-2 SHALL 34行×12列：金融工具名称|所属科目(G1/G8/G9/G10 下拉)|金融工具类型|期初公允价值|期末公允价值|公允价值变动(公式)|本期未审数|调整数|审定数(公式)|源科目索引|交叉验证结论(下拉)|备注
3.2 THE Formula_Engine SHALL 计算公允价值变动 = 期末公允价值 - 期初公允价值
3.3 THE Formula_Engine SHALL 计算审定数 = 本期未审 + 调整数
3.4 WHEN 公允价值变动 ≠ 审定数时, THE 系统 SHALL 红色高亮提示"FV变动与审定数不一致"
3.5 THE G13-2 SHALL 按所属科目分组小计+总计
3.6 THE G13-2 SHALL 支持动态行增删+导入导出

### Requirement 4: 调整分录G13-3 + 公式引擎+联动+UI

**User Story:** As a 开发者, I want to 完成G13全部技术栈。

#### Acceptance Criteria

4.1 THE G13-3 SHALL 22行×10列标准AJE/RJE+借贷平衡+回写审定表+动态行增删+导入导出
4.2 THE Formula_Engine SHALL：calcAdjustedAmount / calcFVChange / calcChangeRate / isDebitCreditBalanced / parseNum（5个纯函数）
4.3 THE 5大集成 SHALL（版本链/抽凭/截止/附注EventBus/复核，无OCR因无凭证检查表）
4.4 THE Import_Export SHALL G13-2/G13-3（2张表）
4.5 THE AI辅助 SHALL：adjudication-analysis/fv-change-conclusion
4.6 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 审定数** — ∀ unadjusted, adj ∈ ℝ: calcAdjustedAmount === unadjusted + adj

**P2: FV变动** — ∀ opening, closing ∈ ℝ: calcFVChange(opening, closing) === closing - opening

**P3: FV变动与审定一致** — WHEN calcFVChange(opening, closing) === calcAdjustedAmount(unadjusted, adj) THEN 交叉验证通过

**P4: 变动率方向性** — calcChangeRate(0, any) === null

**P5: 借贷平衡** — |SUM(debits)-SUM(credits)| < 0.01

**P6: parseNum健壮性** — null/undefined/NaN/'' → 0
