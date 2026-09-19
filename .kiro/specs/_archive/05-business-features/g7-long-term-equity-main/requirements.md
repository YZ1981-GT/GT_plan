# Requirements Document

## Introduction

G7长期股权投资(main组)底稿专属HTML精美组件构建。组件 `g7-long-term-equity-main`，覆盖源模板22个sheet中的7个sheet（核心组）。科目1511长期股权投资（借方/资产类）。**G循环中合并会计最复杂的科目**，审定表97行是投资循环中最大的审定表，明细表54列是投资循环中最宽的表。

源模板按三组拆分，本spec覆盖主体部分（程序表+审定表+附注+明细+调整分录+底稿目录）。

**三组拆分边界**：
| 组 | spec | 覆盖sheet |
|----|------|-----------|
| main(本spec) | g7-long-term-equity-main | G7A+G7-1+附注(上市/国企)+G7-2+G7-3+底稿目录（7sheet） |
| equity-method | g7-long-term-equity-method | G7-4基本信息+G7-5财务信息+G7-6会计政策+G7-13成本测试+G7-14权益法+G7-15内部交易+G7-16未确认损失+G7-17减值（8sheet） |
| subsidiary | g7-long-term-equity-subsidiary | G7-7初始判断+G7-8同控+G7-9非同控+G7-10后续计量+G7-11处置(非一揽子)+G7-12处置(一揽子)+G7-18凭证检查（7sheet） |

**本组(main)sheet清单**：

| # | Sheet名 | 行×列 | 说明 |
|---|---------|-------|------|
| 1 | 底稿目录 | 24×8 | 目录页 |
| 2 | 长期股权投资实质性程序表G7A | 32×14 | a-program-console |
| 3 | 长期股权投资审定表G7-1 | 97×12 | **最大审定表**（子公司/合营/联营分层） |
| 4 | 附注披露信息（上市公司） | 253×13 | **超大**253行附注 |
| 5 | 附注披露信息（国企） | 355×17 | **极大**355行附注 |
| 6 | 明细表G7-2 | 103×54 | **最宽**54列超宽表 |
| 7 | 调整分录汇总G7-3 | 23×10 | AJE/RJE |

**科目属性**：
- 科目代码：1511 长期股权投资
- 方向：借方（资产类）
- 计量属性：成本法(子公司) / 权益法(合营/联营)
- 借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额

**关键特色**：
1. **97行最大审定表**：按控制类型分层（子公司成本法/合营联营权益法/合计/减值/净值）
2. **54列最宽明细表**：需5区段Tab拆分（基础/期初/变动/期末/权益法详情）
3. **253行/355行超大附注**：上市公司253行+国企355行，都必须虚拟滚动
4. **控制类型决定计量**：子公司用成本法、合营联营用权益法，审定逻辑不同

**宽表处理策略**：
- G7-1审定表(12列)：分组折叠(子公司/合营/联营/合计)，97行虚拟滚动
- G7-2明细表(54列)：5区段Tab（基础6列/期初10列/变动10列/期末+减值14列/权益法详情14列）
- 附注(上市253行/国企355行)：虚拟滚动

**六大集成联动**：
- ✅ 版本链 / ✅ 抽凭引擎(G7A) / ✅ 截止自动提取 / ✅ 附注EventBus / ❌ 行级OCR(本组无凭证表) / ✅ 复核对话

## Glossary

- **Long_Term_Equity_Investment**: 长期股权投资，对子公司/合营企业/联营企业的投资
- **Subsidiary**: 子公司，投资方对其实施控制的被投资方（持股>50%或实质控制）
- **Joint_Venture**: 合营企业，投资方与其他参与方共同控制的安排
- **Associate**: 联营企业，投资方对其具有重大影响的被投资方（通常持股20%-50%）
- **Cost_Method**: 成本法，对子公司投资的后续计量方法（个别报表中）
- **Equity_Method**: 权益法，对合营/联营投资的后续计量方法
- **Control_Type**: 控制类型(控制/共同控制/重大影响)，决定计量方法

## Requirements

### Requirement 1: 组件架构

**User Story:** As a 开发者, I want to G7长期股权投资(main组)按sheetName prop分发, so that 7个sheet通过统一入口组织。

#### Acceptance Criteria

1.1 THE G7-main组件 SHALL 注册componentType: `g7-long-term-equity-main`，主入口GtG7LongTermEquityMain.vue
1.2 THE G7-main组件 SHALL defineAsyncComponent懒加载7个子组件
1.3 THE G7-main组件 SHALL 注册四件套（7条wp_code_overrides）
1.4 IF htmlData为null THEN selfLoad；IF sheetName不匹配 THEN OnlyOffice fallback

### Requirement 2: G7A 实质性程序表

**User Story:** As a 审计助理, I want to 执行长期股权投资实质性程序, so that 按步骤完成审计程序。

#### Acceptance Criteria

2.1 THE G7A SHALL 复用a-program-console（32行×14列+抽凭+截止自动提取）

### Requirement 3: 审定表G7-1（97行最大，按控制类型分层）

**User Story:** As a 审计助理, I want to 填写长期股权投资审定表, so that 按控制类型汇总子公司/合营/联营的审定数据。

#### Acceptance Criteria

3.1 THE G7-1审定表 SHALL 97行×12列多层结构：
   - **一、对子公司投资（成本法）**：按被投资单位逐项
   - **二、对合营企业投资（权益法）**：按被投资单位逐项
   - **三、对联营企业投资（权益法）**：按被投资单位逐项
   - **四、投资合计**
   - **五、减值准备**
   - **六、长期股权投资净值**（=合计-减值）
3.2 THE G7-1 SHALL 列结构：项目|控制类型|期初(未审|AJE|RJE|审定)|期末(未审|AJE|RJE|审定)|变动额|变动率
3.3 THE G7-1 SHALL 借方科目公式+审定数公式+TB取数(1511)+差异校验+EventBus(accountCode='1511')
3.4 THE G7-1 SHALL 97行启用虚拟滚动+分组折叠(子公司/合营/联营/合计/减值/净值)
3.5 WHEN |变动率|>20% SHALL 橙色高亮

### Requirement 4: 附注披露(上市253行/国企355行)

**User Story:** As a 审计助理, I want to 编辑长期股权投资附注披露。

#### Acceptance Criteria

4.1 THE 附注(上市) SHALL 253行×13列（**必须**虚拟滚动）
4.2 THE 附注(国企) SHALL 355行×17列（**必须**虚拟滚动）
4.3 THE 附注 SHALL EventBus subscribe/publish联动+每section AI辅助

### Requirement 5: 明细表G7-2（54列→5区段Tab，最宽表）

**User Story:** As a 审计助理, I want to 查看长期股权投资逐笔明细, so that 检查每笔投资的完整信息和权益法调整。

#### Acceptance Criteria

5.1 THE G7-2明细表 SHALL 103行×54列，拆为5区段Tab：
   - **Tab1: 基础信息(8列)**：被投资单位|控制类型(子公司/合营/联营 下拉)|持股比例|投票权比例|行业|注册地|主营业务|是否关联方
   - **Tab2: 期初余额(10列)**：被投资单位|期初投资成本|期初权益法调整|期初减值准备|期初账面价值|期初审定成本|期初审定权益法|期初审定减值|期初审定净值|备注
   - **Tab3: 本期变动(12列)**：被投资单位|本期增加(新增投资)|本期增加(权益法)|本期减少(处置)|本期减少(权益法调整)|本期减值计提|本期减值转回|被投资单位净利润|持股比例调整|其他综合收益|其他权益变动|利润分配
   - **Tab4: 期末+减值(12列)**：被投资单位|期末投资成本|期末权益法调整|期末小计|期末减值准备|期末账面价值|审定调整|审定数|可收回金额|减值测试结论|发函情况|索引
   - **Tab5: 权益法详情(12列)**：被投资单位|被投资方净资产|享有份额|商誉|内部交易抵销|未确认损失|权益法投资收益|本期OCI|股利收入|计量方法确认|处置损益|备注
5.2 THE G7-2 SHALL 103行启用虚拟滚动
5.3 THE Formula_Engine SHALL 期末投资成本 = 期初 + 新增 - 处置
5.4 THE Formula_Engine SHALL 期末权益法调整 = 期初 + 权益法增加 - 权益法减少
5.5 THE Formula_Engine SHALL 期末账面价值 = 期末小计 - 期末减值
5.6 THE G7-2 SHALL 5区段Tab行同步+动态行增删(ElMessageBox输入被投资单位)+导入导出

### Requirement 6: 调整分录G7-3 + 公式引擎 + 联动 + UI

**User Story:** As a 开发者, I want to 完成G7-main全部技术栈, so that 调整分录/公式引擎/集成联动/UI规范齐备。

#### Acceptance Criteria

6.1 THE G7-3 SHALL 23行×10列标准AJE/RJE+借贷平衡+回写G7-1+动态行+导入导出
6.2 THE Formula_Engine SHALL：calcDebitBalance/calcAdjustedAmount/calcEndingCost(opening,increase,decrease)/calcEndingEquityAdj/calcBookValue(subtotal,impairment)/calcChangeRate/isDebitCreditBalanced/parseNum
6.3 THE 5大集成 SHALL（版本链+抽凭+截止+附注EventBus+复核）
6.4 THE Import_Export SHALL G7-2/G7-3（2张表）；G7-2按5区段分sheet导出
6.5 THE AI辅助 SHALL：adjudication-analysis/disclosure-text
6.6 THE 虚拟滚动 SHALL G7-1(97行)/G7-2(103行)/附注上市(253行)/附注国企(355行)
6.7 THE UI SHALL 统一底稿规范+双模式切换

## Correctness Properties

**P1: 借方余额** — opening + debit - credit

**P2: 审定数** — unadjusted + aje + rje

**P3: 期末成本** — opening + increase - decrease

**P4: 账面价值** — subtotal - impairment

**P5: 变动率** — calcChangeRate(0, any) === null

**P6: 借贷平衡** — |SUM(debits)-SUM(credits)| < 0.01

**P7: parseNum** — null/undefined/NaN → 0

**P8: 5区段Tab行同步** — 切换Tab时selectedRowIndex保持一致
