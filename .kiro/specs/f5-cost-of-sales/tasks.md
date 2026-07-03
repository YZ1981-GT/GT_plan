# Implementation Plan: F5 营业成本专属HTML精美组件

## Overview

实现F5营业成本专属组件`f5-cost-of-sales`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtF5CostOfSales.vue + 8个子组件 + 11个composable + 后端3个py文件。核心公式：审定=未审+AJE+RJE（损益类）；成本倒轧=期初+购入-期末-其他=投入+人工+制造=完工=营业成本；毛利率=(收入-成本)/收入×100。9个有效sheet，1个xlsx源模板(183KB)。科目6401营业成本（借方/损益类）。特色：F5-7成本倒轧表(结构化逻辑验证) + F5-6数量核对(数量一致性) + F5-2月度明细(24列2区段)。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2"] },
    { "id": "wave5", "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5"] },
    { "id": "wave6", "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5"] },
    { "id": "wave7", "tasks": ["7.1"] },
    { "id": "wave8", "tasks": ["8.1", "8.2"] },
    { "id": "wave9", "tasks": ["9.1", "9.2", "9.3"] },
    { "id": "wave10", "tasks": ["10.1"] }
  ]
}
```

## Notes

- F5是借方/损益类科目，无"期初期末"概念，只有"本期"和"上期"对比
- 审定公式：审定=未审+AJE+RJE（与F3/F4贷方科目的审定公式相同，但语义不同——损益类是发生额）
- F5-2月度明细(24列)拆为2区段Tab：上半年(1~6月+统计13列) / 下半年+合计(7~12月+汇总11列)
- F5-7成本倒轧表是本循环最核心审计逻辑：4区结构化验证（材料→成本构成→结转→营业成本）
- F5-6数量核对(81行)是另一特色：非金额维度的一致性验证
- F5无附注披露独立sheet（营业成本在利润表附注中披露）
- 截止自动提取(useCutoffAutoSampling)不适用于F5（无截止测试需求）
- 抽凭引擎集成在F5-8（重大调整核查），OCR集成在F5-6（出库单数量识别）
- F5A程序表直接复用a-program-console组件
- 品种行动态增删需先ElMessageBox.prompt输入品种名

## Tasks

- [ ] 1. 组件注册与基础配置
  - [ ] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将F5A/F5-1~F5-8映射为'f5-cost-of-sales'（9个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'f5-cost-of-sales'
    - 在 `htmlRendererRegistry.ts` 中注册 'f5-cost-of-sales' → GtF5CostOfSales 映射
    - 创建 `GtF5CostOfSales.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy + selfLoad逻辑 + el-tabs 9 tabs + OnlyOffice fallback）
    - _Requirements: 1.1~1.8_

  - [ ]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'f5-cost-of-sales'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证9个映射条目
    - _Requirements: 1.3, 1.4, 1.5_

- [ ] 2. 实现公式引擎 useF5FormulaEngine.ts
  - [ ] 2.1 创建 `composables/useF5FormulaEngine.ts`，实现全部12个纯函数
    - 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE，损益类发生额）
    - 实现 `calcChangeAmount`（变动额 = 本期 - 上期）
    - 实现 `calcChangeRate`（变动率 = (本期-上期)/上期 × 100，上期=0→'N/A'）
    - 实现 `calcGrossMargin`（毛利率 = (收入-成本)/收入 × 100，收入=0→'N/A'）
    - 实现 `calcCostRollforward`（投入生产 = 期初原材料 + 购入 - 期末原材料 - 其他发出）
    - 实现 `calcTotalProductionCost`（产品总成本 = 投入 + 人工 + 制造费）
    - 实现 `calcFinishedGoodsCost`（完工成本 = 期初在产 + 总成本 - 期末在产）
    - 实现 `calcCOGS`（营业成本 = 期初产成品 + 完工 - 期末产成品 - 其他）
    - 实现 `calcQuantityVariance`（数量差异 = 销售量 - 结转量）
    - 实现 `calcVarianceRate`（差异率 = 差异/销售量 × 100，销售量=0→'N/A'）
    - 实现 `calcCoeffOfVariation`（波动系数 = stddev(values)/mean(values)，mean=0→0）
    - 实现 `isDebitCreditBalanced`（借贷平衡 = |SUM(debits)-SUM(credits)| < 0.01）
    - _Requirements: 11.1~11.12_

  - [ ]* 2.2 编写 Property 1 PBT：损益类审定公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` × unadjusted/aje/rje
    - 断言：calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
    - **Property 1: 审定=未审+AJE+RJE**
    - **Validates: Requirements 11.1, 3.3**

  - [ ]* 2.3 编写 Property 2 PBT：成本倒轧恒等
    - 生成器：`fc.float({min:0, max:1e8})` × opening/purchase/closing/other
    - 断言：calcCostRollforward(opening, purchase, closing, other) === opening + purchase - closing - other
    - **Property 2: 投入=期初+购入-期末-其他**
    - **Validates: Requirements 11.5, 9.2**

  - [ ]* 2.4 编写 Property 3 PBT：毛利率公式
    - 生成器：`fc.float({min:0.01, max:1e8})` revenue + `fc.float({min:0, max:revenue})` cost
    - 断言：calcGrossMargin(revenue, cost) === (revenue-cost)/revenue × 100
    - **Property 3: 毛利率=(收入-成本)/收入×100**
    - **Validates: Requirements 11.4, 7.3**

  - [ ]* 2.5 编写 Property 4 PBT：完工成本恒等
    - 生成器：`fc.float({min:0, max:1e8})` × wipOpening/totalCost/wipClosing
    - 断言：calcFinishedGoodsCost(wipOpening, totalCost, wipClosing) === wipOpening + totalCost - wipClosing
    - **Property 4: 完工=期初在产+总成本-期末在产**
    - **Validates: Requirements 11.7, 9.4**

  - [ ]* 2.6 编写 Property 5 PBT：营业成本倒轧全链非负
    - 生成器：构造合理输入使 fgOpening+finishedCost ≥ fgClosing+other
    - 断言：calcCOGS(fgOpening, finishedCost, fgClosing, other) ≥ 0
    - **Property 5: 合理输入下营业成本≥0**
    - **Validates: Requirements 11.8, 9.5**

  - [ ]* 2.7 编写 Property 6 PBT：数量差异公式
    - 生成器：`fc.float({min:0, max:1e6})` × salesQty/costQty
    - 断言：calcQuantityVariance(salesQty, costQty) === salesQty - costQty
    - **Property 6: 数量差异=销售量-结转量**
    - **Validates: Requirements 11.9, 8.2**

  - [ ]* 2.8 编写 Property 7 PBT：变动率公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` current + `fc.float({min:0.01, max:1e8})` prior
    - 断言：calcChangeRate(current, prior) === (current-prior)/prior × 100
    - **Property 7: 变动率=(本期-上期)/上期×100**
    - **Validates: Requirements 11.3, 7.4**

  - [ ]* 2.9 编写 Property 8 PBT：波动系数非负
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:2, maxLength:12})` 且 mean>0
    - 断言：calcCoeffOfVariation(values) ≥ 0
    - **Property 8: 波动系数恒≥0**
    - **Validates: Requirements 11.11, 4.7**

  - [ ]* 2.10 编写 Property 9 PBT：月度合计恒等
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:12, maxLength:12})`
    - 断言：SUM(months[0..5]) + SUM(months[6..11]) === SUM(months[0..11])
    - **Property 9: 上半年+下半年=全年**
    - **Validates: Requirements 4.2, 4.3, 4.4**

  - [ ]* 2.11 编写 Property 10 PBT：借贷平衡恒等
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:1, maxLength:20})` × debits/credits
    - 断言：isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
    - **Property 10: 借贷平衡=SUM借方===SUM贷方**
    - **Validates: Requirements 11.12, 6.2**

- [ ] 3. 实现 useF5FormData.ts 基础数据加载/保存
  - [ ] 3.1 创建 `composables/useF5FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate / debouncedSave / saveBatch
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=f5-cost-of-sales）
    - _Requirements: 1.6_

- [ ] 4. 实现审定表 composable
  - [ ] 4.1 创建 `composables/useF5Adjudication.ts`
    - 定义损益类审定结构：mainBusinessRows[] + otherBusinessRows[] + subtotals + grandTotal
    - 实现损益类公式：审定=未审+AJE+RJE（本期/上期各自独立计算）
    - 实现主营小计/其他小计/总计 computed
    - 实现试算表自动取数（科目6401发生额）+ 差异计算
    - 实现动态品种行增删（ElMessageBox.prompt输入品种名）
    - 实现EventBus发布 `substantive:adjudicated`(accountCode='6401')
    - 实现序列化/反序列化
    - _Requirements: 3.1~3.9_

  - [ ]* 4.2 编写审定表单元测试
    - 验证损益类审定公式（无期初期末，只有本期/上期）
    - 验证总计=主营小计+其他小计
    - 验证差异=审定-试算表数
    - _Requirements: 3.3~3.6_

- [ ] 5. 实现各sheet composable
  - [ ] 5.1 创建 `composables/useF5MonthlyDetail.ts`（F5-2月度明细2区段逻辑）
    - 定义 `MonthlyDetailRow` 类型（24列分2区段）
    - 实现2区段列配置导出（上半年13列 / 下半年+合计11列）
    - 实现公式链：上半年合计=1~6月SUM / 下半年合计=7~12月SUM / 全年=上半年+下半年 / 变动额/率
    - 实现波动系数=stddev/mean + 波动>0.5橙色标记
    - 实现区段间行同步 + 动态品种行增删 + 合计行
    - _Requirements: 4.1~4.12_

  - [ ] 5.2 创建 `composables/useF5OtherCost.ts`（F5-3其他业务成本逻辑）
    - 定义行类型（14列）
    - 实现公式链：变动额/率/占比/成本率
    - 实现变动>30%橙色标记 + 合计行 + 动态行增删
    - _Requirements: 5.1~5.7_

  - [ ] 5.3 创建 `composables/useF5Comparison.ts`（F5-5比较分析逻辑）
    - 定义 `ComparisonRow` 类型（17列）
    - 实现公式链：毛利=收入-成本 / 毛利率 / 变动额/率 / 毛利率变动
    - 实现毛利率变动>5百分点橙色 + 成本收入不匹配橙色
    - 实现合计行 + 动态品种行增删
    - _Requirements: 7.1~7.9_

  - [ ] 5.4 创建 `composables/useF5QuantityRecon.ts`（F5-6数量核对逻辑）
    - 定义 `QuantityReconRow` 类型（16列）
    - 实现公式链：差异=销售-结转 / 差异率 / 可供销售=期初+产量+采购 / 理论结转=可供-期末 / 理论差异
    - 实现高亮标记（>5%橙色，>10%红色）
    - 实现差异原因分类下拉
    - 实现底部汇总（总销售/结转/差异/异常品种数）+ 动态行增删
    - _Requirements: 8.1~8.11_

  - [ ] 5.5 创建 `composables/useF5CostRollforward.ts`（F5-7成本倒轧逻辑）
    - 定义 `CostRollforwardData` 类型（4区结构化数据）
    - 实现4区公式链：
      - 材料流转：投入=期初+购入-期末-其他
      - 成本构成：总成本=投入+人工+制造费
      - 成本结转：完工=期初在产+总成本-期末在产
      - 营业成本：COGS=期初产成品+完工-期末产成品-其他
    - 实现TB自动取数（1401原材料/1404在产品/1405产成品，期初/期末）
    - 实现校验区：从F5-1取审定营业成本 → 计算差异 → 差异>重要性红色
    - 实现可编辑字段标记（购入/人工/制造/其他）vs只读字段（TB取数/公式）
    - _Requirements: 9.1~9.10_

- [ ] 6. 实现 Vue子组件
  - [ ] 6.1 创建 `f5-cost-of-sales/F5TabAdjudication.vue`（F5-1审定表 损益类）
    - 调用useF5Adjudication
    - el-table渲染（主营品种行+小计 + 其他品种行+小计 + 总计+TB数+差异）
    - 动态品种行增删（ElMessageBox.prompt） + GtIndexChip索引列
    - EventBus发布 + 虚拟滚动(60行)
    - _Requirements: 3.1~3.9_

  - [ ] 6.2 创建 `f5-cost-of-sales/F5TabMonthlyDetail.vue`（F5-2月度明细 24列→2区段Tab）
    - 调用useF5MonthlyDetail
    - 2区段Tab切换（上半年/下半年+合计）+ 区段间行同步
    - 变动>20%橙色 / 波动系数>0.5橙色
    - 动态品种行增删 + 底部合计 + 导入导出
    - _Requirements: 4.1~4.12_

  - [ ] 6.3 创建 `f5-cost-of-sales/F5TabQuantityRecon.vue`（F5-6数量核对 81行）
    - 调用useF5QuantityRecon
    - el-table 16列 + >5%橙色/>10%红色
    - 差异原因分类下拉 + 理论结转验证
    - 📎OCR列（POST contract-ocr识别出库单数量→确认merge）
    - 底部汇总 + 动态行增删 + 导入导出 + 虚拟滚动(81行)
    - 审计说明textarea(AI)
    - _Requirements: 8.1~8.11, 12.4_

  - [ ] 6.4 创建 `f5-cost-of-sales/F5TabCostRollforward.vue`（F5-7成本倒轧表 结构化）
    - 调用useF5CostRollforward
    - 蓝色渐变引导区（4步骤序号）
    - 4区结构化布局（el-card per区，公式行虚线+tooltip）
    - TB取数字段只读标记 / 可编辑字段高亮边框
    - 校验区：审定vs倒轧差异（绿色通过/红色异常）
    - 审计结论textarea(AI) + 编制提示details折叠
    - _Requirements: 9.1~9.10_

  - [ ] 6.5 创建其余Vue子组件
    - F5TabOtherCost.vue（F5-3其他业务成本）：14列 + 变动>30%橙色 + 导入导出
    - F5TabAdjustment.vue（F5-4调整分录）：借贷平衡校验 + 动态行 + 导入导出
    - F5TabComparison.vue（F5-5比较分析）：17列 + 毛利率变动>5%橙色 + 品种增删 + 导入导出
    - F5TabMajorAdjustment.vue（F5-8重大调整）：8列 + >重要性橙色 + 抽凭引擎 + 导入导出
    - _Requirements: 5.1~5.7, 6.1~6.4, 7.1~7.9, 10.1~10.4_

- [ ] 7. Checkpoint - 公式引擎+组件验证
  - Ensure all PBT tests pass (P1~P10), ask the user if questions arise.

- [ ] 8. 实现后端 + 导入导出 + AI
  - [ ] 8.1 创建后端3个py文件
    - `_f5_cost_of_sales.py`：render策略函数 + 注册RENDERER_DISPATCH['f5-cost-of-sales']
    - `_f5_cost_of_sales_import_export.py`：3端点 + 6张动态行表格支持
    - `_f5_cost_of_sales_ai.py`：5个AI section端点 + 30秒超时
    - _Requirements: 1.3, 13.1~13.4_

  - [ ] 8.2 创建 `composables/useF5ImportExport.ts` + `composables/useF5DualMode.ts`
    - useF5ImportExport：el-dropdown"导入导出▾" + axios三端点 + 6张表参数
    - useF5DualMode：模式状态(html/onlyoffice) + 切换逻辑 + localStorage持久化
    - _Requirements: 13.1~13.4_

- [ ] 9. 跨模块联动集成
  - [ ] 9.1 版本链集成
    - 主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 12.1, 12.5_

  - [ ] 9.2 抽凭引擎 + OCR集成
    - F5-8: GtVoucherSamplingEngine dialog集成（科目6401，选取重大成本调整凭证）
    - F5-6: 📎OCR列（POST contract-ocr→出库单数量识别→确认弹窗→merge）
    - _Requirements: 12.2, 12.4_

  - [ ] 9.3 附注EventBus集成
    - F5-1审定表发布 `substantive:adjudicated`(accountCode='6401')
    - F5-7成本倒轧表监听此事件获取审定营业成本用于校验区
    - （F5无独立附注sheet，不publish disclosure:note-text-updated）
    - _Requirements: 12.3_

- [ ] 10. 集成测试与验收
  - [ ] 10.1 编写集成测试
    - sheetName分发正确性（9个sheet→对应组件）
    - 损益类审定公式链（本期/上期各自计算）
    - F5-7成本倒轧全链路（4区公式→校验区差异）
    - F5-7 TB自动取数（1401/1404/1405）
    - F5-6数量核对（销售vs结转+理论结转）
    - F5-2两区段Tab行同步 + 月度合计=上半年+下半年
    - F5-5毛利率计算+变动高亮
    - F5-8抽凭引擎选取
    - EventBus(substantive:adjudicated)传递 + F5-7消费
    - 导入导出round-trip
    - _Requirements: 全部_
