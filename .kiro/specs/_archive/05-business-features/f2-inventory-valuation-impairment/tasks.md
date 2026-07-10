# Implementation Plan: F2 计价测试 + 跌价准备测试 + 关联交易专属HTML精美组件

## Overview

实现F2存货底稿Group 2专属组件`f2-inventory-valuation`。按依赖顺序：注册→扩展公式引擎→基础设施→通用计价组件→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtF2InventoryValuation.vue + 11个子组件（含1通用） + 10个composable + 后端3个py文件。核心公式：NRV=售价-完工成本-销售费用-税金；应计提跌价=MAX(0,账面-NRV)；加权平均单价=(期初额+入库额)/(期初量+入库量)；标准成本差异=价格差异+数量差异；转回≤累计计提。13个有效sheet，3个xlsx源模板。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2", "6.3"] },
    { "id": "wave7", "tasks": ["8.1", "8.2", "8.3", "8.4"] },
    { "id": "wave8", "tasks": ["9.1", "9.2", "9.3", "9.4"] },
    { "id": "wave9", "tasks": ["10.1", "10.2"] },
    { "id": "wave10", "tasks": ["11.1", "11.2", "11.3"] },
    { "id": "wave11", "tasks": ["13.1"] },
    { "id": "wave12", "tasks": ["14.1", "14.2"] }
  ]
}
```

> **代码同步（2026-07-04）**：下列 `[x]` 已与仓库实现对齐；`[ ]*` 为可选 PBT；Checkpoint/最终验收/性能打磨仍待人工确认。


## Notes

- F2-38~F2-40共3张计价测试表使用通用组件F2ValuationTestSheet.vue（config驱动差异：加权平均/先进先出/标准成本）
- F2-47跌价准备测试(28列)是本spec最复杂的sheet，拆为3区段Tab(基础信息10列/NRV测算10列/跌价结论8列)
- F2-49跌价转回(24列)拆为2区段Tab(上期跌价12列/本期NRV+转回12列)
- F2-44成本分配从F2-41/F2-42/F2-43通过allResponses computed链自动取数（不走EventBus）
- F2-47测试完成后通过EventBus(impairment:calculated)联动f2-inventory-main的F2-1审定表跌价区
- 扩展公式引擎复用useF2FormulaEngine的parseNum/calcSubtotal等基础函数，不重复实现
- 本spec与f2-inventory-main完全独立注册componentType，但运行时通过EventBus联动

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将F2-38~F2-40/F2-41~F2-44/F2-47~F2-49/F2-52映射为'f2-inventory-valuation'（13个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'f2-inventory-valuation'
    - 在 `htmlRendererRegistry.ts` 中注册 'f2-inventory-valuation' → GtF2InventoryValuation 映射
    - 创建 `GtF2InventoryValuation.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy + selfLoad逻辑 + el-tabs 4 group + OnlyOffice fallback）
    - _Requirements: 1.1~1.8_

  - [ ]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'f2-inventory-valuation'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证F2-38~F2-40/F2-41~F2-44/F2-47~F2-49/F2-52共13个映射
    - _Requirements: 1.3, 1.4, 1.5_

- [x] 2. 实现扩展公式引擎 useF2ValuationFormulaEngine.ts
  - [x] 2.1 创建 `composables/useF2ValuationFormulaEngine.ts`，实现全部12个纯函数
    - 导入并复用 useF2FormulaEngine 的 parseNum/calcSubtotal/calcChangeRate 基础函数
    - 实现 `calcNRV`（NRV = 售价 - 完工成本 - 销售费用 - 销售税金）
    - 实现 `calcImpairmentProvision`（应计提跌价 = MAX(0, 账面成本 - NRV)）
    - 实现 `calcWeightedAvgPrice`（加权平均单价 = (期初金额+入库金额)/(期初数量+入库数量)，总数量=0→0）
    - 实现 `calcStandardCost`（标准成本 = 标准单价 × 标准数量）
    - 实现 `calcPriceVariance`（价格差异 = (实际单价-标准单价) × 实际数量）
    - 实现 `calcQuantityVariance`（数量差异 = (实际数量-标准数量) × 标准单价）
    - 实现 `calcTotalVariance`（总差异 = 实际成本 - 标准成本 = 实际单价×实际数量 - 标准单价×标准数量）
    - 实现 `calcReversalAmount`（转回金额 = MIN(MAX(0, 已计提-应计提), 转回上限)）
    - 实现 `calcAllocationRatio`（分配比例 = 本品基准/全部基准SUM × 100）
    - 实现 `calcFairnessDeviation`（公允性差异率 = (关联价-可比价)/可比价 × 100，可比价=0→'N/A'）
    - 实现 `isExpired`（超保质期判定 = 库龄 > 保质期 → true/false）
    - 实现 `calcRemainingShelfDays`（剩余保质天数 = 保质期 - 库龄）
    - _Requirements: 13.1~13.12_

  - [ ]* 2.2 编写 Property 1 PBT：NRV公式
    - 生成器：`fc.float({min:0, max:1e8})` × price/completionCost/sellingExpense/tax
    - 断言：calcNRV(price, completionCost, sellingExpense, tax) === price - completionCost - sellingExpense - tax
    - **Property 1: NRV=售价-完工成本-销售费用-税金**
    - **Validates: Requirements 13.1, 9.5**

  - [ ]* 2.3 编写 Property 2 PBT：跌价计提公式
    - 生成器：`fc.float({min:0, max:1e8})` × bookCost/nrv
    - 断言：calcImpairmentProvision(bookCost, nrv) === Math.max(0, bookCost - nrv)
    - **Property 2: 应计提跌价=MAX(0, 账面-NRV)**
    - **Validates: Requirements 13.2, 9.6**

  - [ ]* 2.4 编写 Property 3 PBT：加权平均单价
    - 生成器：`fc.float({min:-1e8, max:1e8})` amounts + `fc.float({min:0.01, max:1e6})` quantities
    - 断言：calcWeightedAvgPrice(openAmt, inAmt, openQty, inQty) === (openAmt+inAmt)/(openQty+inQty)
    - **Property 3: 加权平均单价=(期初额+入库额)/(期初量+入库量)**
    - **Validates: Requirements 13.3, 2.4**

  - [ ]* 2.5 编写 Property 4 PBT：标准成本差异恒等式
    - 生成器：`fc.float({min:-1e6, max:1e6})` × stdPrice/stdQty/actPrice/actQty
    - 断言：calcPriceVariance(...) + calcQuantityVariance(...) === calcTotalVariance(...)
    - **Property 4: 价格差异+数量差异=总差异**
    - **Validates: Requirements 13.5, 13.6, 13.7, 4.5~4.7**

  - [ ]* 2.6 编写 Property 5 PBT：跌价转回金额约束
    - 生成器：`fc.float({min:0, max:1e8})` × provision/required/cap
    - 断言：0 ≤ calcReversalAmount(provision, required, cap) ≤ cap
    - **Property 5: 转回金额∈[0, 转回上限]**
    - **Validates: Requirements 13.8, 11.5, 11.6**

  - [ ]* 2.7 编写 Property 6 PBT：分配比例合计=100%
    - 生成器：`fc.array(fc.float({min:0.01, max:1e6}), {minLength:2, maxLength:20})`
    - 断言：|SUM(quantities.map(q => calcAllocationRatio(q, SUM(quantities)))) - 100| < 1e-10
    - **Property 6: 分配比例合计=100%**
    - **Validates: Requirements 13.9, 8.2**

  - [ ]* 2.8 编写 Property 7 PBT：公允性差异率公式
    - 生成器：`fc.float({min:-1e6, max:1e6})` relatedPrice + `fc.float({min:0.01, max:1e6})` comparablePrice
    - 断言：calcFairnessDeviation(relatedPrice, comparablePrice) === (relatedPrice-comparablePrice)/comparablePrice×100
    - **Property 7: 公允性差异率=(关联价-可比价)/可比价×100**
    - **Validates: Requirements 13.10, 12.4**

  - [ ]* 2.9 编写 Property 8 PBT：超保质期判定幂等
    - 生成器：`fc.nat({max:3650})` × ageDays/shelfDays
    - 断言：isExpired(ageDays, shelfDays) === isExpired(ageDays, shelfDays)（幂等）+ ageDays>shelfDays ↔ true
    - **Property 8: 超保质期判定幂等且确定**
    - **Validates: Requirements 13.11, 10.2**

  - [ ]* 2.10 编写 Property 9 PBT：NRV≥账面时无需计提
    - 生成器：`fc.float({min:0, max:1e8})` bookCost + `fc.float`使nrv≥bookCost
    - 断言：calcImpairmentProvision(bookCost, nrv) === 0 当 nrv ≥ bookCost
    - **Property 9: NRV≥账面→应计提=0**
    - **Validates: Requirements 13.2, 9.6**

  - [ ]* 2.11 编写 Property 10 PBT：计价差异可加性
    - 生成器：`fc.float({min:-1e6, max:1e6})` × 4 (actPrice/actQty/stdPrice/stdQty)
    - 断言：calcTotalVariance === calcPriceVariance + calcQuantityVariance（数值等价）
    - **Property 10: 总差异=价格差异+数量差异（可加性）**
    - **Validates: Requirements 13.5, 13.6, 13.7**

- [x] 3. 实现 useF2ValuationFormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useF2ValuationFormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate / debouncedSave / saveBatch
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=f2-inventory-valuation）
    - 实现抽样参数区加载/保存（通用6字段）
    - _Requirements: 1.6_

- [x] 4. 实现 useF2ValuationTest.ts 通用计价测试逻辑
  - [x] 4.1 创建 `composables/useF2ValuationTest.ts`
    - 定义 `ValuationTestRow` 通用类型（支持3种计价方法的差异字段）
    - 定义 `ValuationTestConfig` 接口（sheetCode/method/columns/formulaType/thresholdRate）
    - 实现 `createValuationTestComposable(config)` 工厂函数
    - 实现 `samplingParams` reactive（6字段抽样参数区）
    - 实现 `rows` reactive + `totalRow` computed + `exceedCount` computed
    - 实现公式链：
      - weighted-avg: 加权平均单价→审计发出金额→差异额→差异率
      - fifo: FIFO应发单价→审计发出金额→差异额→差异率
      - standard-cost: 标准成本→实际成本→价格差异→数量差异→总差异→差异率
    - 实现 `updateCell` + `addRow` + `removeRow`
    - 实现 `isExceedThreshold(row)` computed（差异率>阈值）
    - 实现 EventBus 发布 `valuation:tested`
    - 实现序列化/反序列化
    - _Requirements: 2.1~2.11, 3.1~3.7, 4.1~4.10_

  - [ ]* 4.2 编写计价测试通用逻辑单元测试
    - 验证3种method的公式链正确性
    - 验证阈值判定（1%/1%/5%）
    - 验证动态行增删+合计行
    - _Requirements: 2.4~2.8, 3.3~3.5, 4.3~4.8_

- [x] 5. 实现 useF2ProductionCost.ts 生产成本组逻辑
  - [x] 5.1 创建 `composables/useF2ProductionCost.ts`
    - F2-41 生产成本明细：ProductionCostRow[] + PeriodData结构 + 合计行 + 成本要素合计公式
    - F2-42 直接人工分析：DirectLaborRow[] + 计算人工费/差异/合计/占比公式链
    - F2-43 制造费用明细：OverheadRow[] + 变动额/率/预算差异/分配合计公式链
    - F2-44 成本分配：CostAllocationRow[] + 基准占比/各要素分配/差异公式 + 从F2-41/42/43自动取总额
    - 实现 `productionCostRows` / `directLaborRows` / `overheadRows` / `allocationRows` reactive
    - 实现各表 `totalRow` computed + `updateCell` + `addRow` + `removeRow`
    - 实现 F2-44 autoFetchTotals（从allResponses取F2-41/42/43合计数据）
    - 实现 分配合计≠发生额红色标记
    - 实现序列化/反序列化
    - _Requirements: 5.1~5.6, 6.1~6.8, 7.1~7.8, 8.1~8.8_

  - [ ]* 5.2 编写生产成本组单元测试
    - 验证期末=期初+投入-转出
    - 验证成本合计=直接材料+人工+制造费用
    - 验证人工费计算=人数×工时×工资率
    - 验证分配合计=发生额（各产品分配之和=费用发生额）
    - _Requirements: 5.2, 5.3, 6.2, 7.5, 8.3_

- [x] 6. 实现 useF2ImpairmentTest.ts + useF2ObsoleteInventory.ts + useF2ImpairmentReversal.ts
  - [x] 6.1 创建 `composables/useF2ImpairmentTest.ts`（F2-47跌价NRV测试，最复杂）
    - 定义 `ImpairmentTestRow` 类型（28列全字段，分3区段）
    - 实现 `samplingParams` reactive（6字段抽样参数区）
    - 实现 `rows` reactive + 3区段列配置导出
    - 实现NRV公式链：账面成本=数量×单位成本 → NRV=售价-完工-销售费-税 → 应计提=MAX(0,账面-NRV) → 应补提=MAX(0,应计提-已计提) → 应转回=MAX(0,已计提-应计提) → 与企业差异
    - 实现 `totalSummary` computed（合计账面/合计NRV/合计应计提/合计已计提/净差异）
    - 实现 `updateCell` + `addRow` + `removeRow`
    - 实现区段间行同步（activeRowIndex reactive）
    - 实现 EventBus 发布 `impairment:calculated`（payload含各类别应计提跌价合计map）
    - 实现应计提>0且结论空→橙色高亮标记
    - 实现序列化/反序列化
    - _Requirements: 9.1~9.15_

  - [x] 6.2 创建 `composables/useF2ObsoleteInventory.ts`（F2-48呆滞存货）
    - 定义 `ObsoleteInventoryRow` 类型（14列）
    - 实现 `rows` reactive + `summary` computed（长库龄笔数/呆滞笔数/超保质笔数/跌价建议合计）
    - 实现公式链：是否超保质期=库龄>保质期 / 剩余保质天数=保质期-库龄
    - 实现高亮标记（超保质或呆滞→橙色）
    - 实现 `updateCell` + `addRow` + `removeRow`
    - 实现处理方案下拉（正常销售/促销/报废/退货/转跌价）
    - 实现序列化/反序列化
    - _Requirements: 10.1~10.8_

  - [x] 6.3 创建 `composables/useF2ImpairmentReversal.ts`（F2-49跌价转回）
    - 定义 `ImpairmentReversalRow` 类型（24列分2区段）
    - 实现 `rows` reactive + 2区段列配置导出
    - 实现公式链：本期NRV=售价-完工-销售费 → 本期应计提=MAX(0,账面-NRV) → 是否应转回=(已计提>应计提) → 转回金额=MIN(已计提-应计提, 转回上限) → 转回上限=累计计提
    - 实现 `summary` computed（转回笔数/转回总额/超限笔数）
    - 实现区段间行同步
    - 实现转回合理性未填橙色高亮
    - 实现 `updateCell` + `addRow` + `removeRow`
    - 实现序列化/反序列化
    - _Requirements: 11.1~11.10_

- [x] 7. Checkpoint - 公式引擎+composable验证
  - Ensure all PBT tests pass (P1~P10), ask the user if questions arise.

- [x] 8. 实现 Vue子组件 - valuation-test/目录
  - [x] 8.1 创建 `f2-valuation/valuation-test/F2ValuationTestSheet.vue`（通用计价测试组件）
    - 接收 `config: ValuationTestConfig` prop
    - 渲染抽样参数区（6字段横排el-form-item）
    - 渲染动态行检查表（el-table按config.columns渲染）
    - 差异率>阈值红色高亮行
    - 动态行增删 + 合计行 + 超差异笔数统计
    - 底部测试结论textarea + AI按钮右对齐
    - 导入导出按钮（el-dropdown三选项）
    - UI铁律：13px/公式列虚线/min-width/编制提示details折叠
    - 虚拟滚动（>50行）
    - _Requirements: 2.1~2.3, 2.9~2.11, 3.1~3.2, 3.6~3.7, 4.1~4.2, 4.9~4.10_

  - [x] 8.2 创建 `f2-valuation/valuation-test/F2TabValuationAvg.vue`（F2-38加权平均）
    - 传入weighted-avg config到F2ValuationTestSheet
    - 15列config定义（含加权平均单价/审计发出金额/差异额/差异率4公式列）
    - thresholdRate=1
    - _Requirements: 2.1~2.11_

  - [x] 8.3 创建 `f2-valuation/valuation-test/F2TabValuationFIFO.vue`（F2-39先进先出）
    - 传入fifo config到F2ValuationTestSheet
    - 15列config定义（含FIFO发出/审计金额/差异3公式列）
    - thresholdRate=1
    - _Requirements: 3.1~3.7_

  - [x] 8.4 创建 `f2-valuation/valuation-test/F2TabValuationStdCost.vue`（F2-40标准成本差异）
    - 传入standard-cost config到F2ValuationTestSheet
    - 16列config定义（含标准成本/实际成本/价格差异/数量差异/总差异5公式列）
    - thresholdRate=5
    - _Requirements: 4.1~4.10_

- [x] 9. 实现 Vue子组件 - production-cost/目录
  - [x] 9.1 创建 `f2-valuation/production-cost/F2TabProductionCost.vue`（F2-41生产成本明细）
    - 调用 useF2ProductionCost
    - el-table 17列（产品名称 + 直接材料4列 + 直接人工4列 + 制造费用4列 + 合计4列 + 备注）
    - 期末=期初+投入-转出公式自动计算
    - 动态行增删 + 合计行 + 审计说明textarea(AI)
    - _Requirements: 5.1~5.6_

  - [x] 9.2 创建 `f2-valuation/production-cost/F2TabDirectLabor.vue`（F2-42直接人工）
    - 调用 useF2ProductionCost
    - el-table 17列
    - 计算人工费=人数×工时×工资率
    - 差异>5%橙色高亮 + 占比列
    - 动态行增删 + 合计行 + 审计说明 + 导入导出
    - _Requirements: 6.1~6.8_

  - [x] 9.3 创建 `f2-valuation/production-cost/F2TabManufacturingOverhead.vue`（F2-43制造费用）
    - 调用 useF2ProductionCost
    - el-table 16列
    - 变动率>20%橙色高亮 + 分配合计≠发生额红色高亮
    - 动态行增删 + 合计行 + 审计说明 + 导入导出
    - _Requirements: 7.1~7.8_

  - [x] 9.4 创建 `f2-valuation/production-cost/F2TabCostAllocation.vue`（F2-44成本分配）
    - 调用 useF2ProductionCost
    - el-table 15列
    - 从F2-41/42/43 allResponses自动取数（直接材料/人工/制造费用总额）
    - 基准占比+分配额公式 + 差异率>3%橙色高亮
    - 分配基准下拉(工时/产量/机器小时/材料成本)
    - 动态行增删 + 合计行 + 审计说明 + 导入导出
    - _Requirements: 8.1~8.8_

- [x] 10. 实现 Vue子组件 - impairment/目录
  - [x] 10.1 创建 `f2-valuation/impairment/F2TabImpairmentTest.vue`（F2-47跌价NRV测试 28列→3区段Tab）
    - 调用 useF2ImpairmentTest
    - 顶部抽样参数区（6字段el-form-item横排）
    - 3区段Tab切换（基础信息10列/NRV测算10列/跌价结论8列）
    - 区段间行同步（切换不丢行位置）
    - NRV公式链全自动计算（账面→NRV→应计提→补提/转回→差异）
    - 应计提>0且结论空→橙色提醒
    - 动态行增删 + 底部汇总(5项) + 测试结论textarea(AI)
    - EventBus发布impairment:calculated
    - 导入导出 + 虚拟滚动(>50行)
    - UI铁律：13px/公式列虚线tooltip/min-width/编制提示
    - _Requirements: 9.1~9.15_

  - [x] 10.2 创建 `f2-valuation/impairment/F2TabObsoleteInventory.vue`（F2-48呆滞存货）
    - 调用 useF2ObsoleteInventory
    - el-table 14列
    - 超保质期/呆滞自动判定 + 橙色高亮
    - 处理方案下拉 + 剩余保质天数公式
    - 底部汇总（长库龄/呆滞/超保质笔数/跌价建议合计）
    - 动态行增删 + 审计说明textarea(AI) + 导入导出
    - _Requirements: 10.1~10.8_

- [x] 11. 实现 Vue子组件 - impairment/(续) + related-party/
  - [x] 11.1 创建 `f2-valuation/impairment/F2TabImpairmentReversal.vue`（F2-49跌价转回 24列→2区段Tab）
    - 调用 useF2ImpairmentReversal
    - 2区段Tab（上期跌价12列/本期NRV+转回判定12列）
    - 区段间行同步
    - 转回公式链（本期NRV→应计提→是否应转回→转回金额→转回上限校验）
    - 应转回且合理性未填→橙色高亮
    - 底部汇总(转回笔数/总额/超限) + 审计说明textarea(AI)
    - 动态行增删 + 导入导出
    - _Requirements: 11.1~11.10_

  - [x] 11.2 创建 `f2-valuation/related-party/F2TabRelatedPurchase.vue`（F2-52关联采购）
    - 调用 useF2RelatedPurchase
    - el-table 17列
    - 采购金额=数量×单价 / 占比 / 差异率 / 非关联差异率 公式自动计算
    - 差异率>10%红色高亮
    - 定价方式下拉(市场/协议/成本加成/参照同类) + 公允性结论下拉(公允/基本公允/不公允/无法判断)
    - GtIndexChip索引列
    - 底部汇总（关联采购总额/占比/不公允笔数）+ 审计说明textarea(AI)
    - 动态行增删 + 导入导出
    - _Requirements: 12.1~12.10_

  - [x] 11.3 创建 `composables/useF2RelatedPurchase.ts`（F2-52关联采购逻辑）
    - 定义 `RelatedPurchaseRow` 类型（17列字段）
    - 实现 `rows` reactive + `totalRow` computed
    - 实现公式链：采购金额=数量×单价 / 占比=金额/总金额SUM / 差异率=(单价-可比价)/可比价 / 非关联差异率
    - 实现 `summary` computed（关联采购总额/占比/不公允笔数）
    - 实现 `updateCell` + `addRow` + `removeRow`
    - 实现 isUnfair 高亮标记（差异率>10%）
    - 实现序列化/反序列化
    - _Requirements: 12.1~12.10_

- [x] 12. Checkpoint - 全组件验证
  - Ensure all PBT tests pass and components render correctly, ask the user if questions arise.

- [x] 13. 实现后端Render策略 + 导入导出 + AI
  - [x] 13.1 创建后端3个py文件
    - `_f2_valuation.py`：render策略函数 + 注册RENDERER_DISPATCH['f2-inventory-valuation'] + 支持force_component_type
    - `_f2_valuation_import_export.py`：3端点（export-template/export-data/import-data）+ openpyxl生成/解析 + 数据校验(NRV公式/差异率) + StreamingResponse中文文件名RFC5987编码 + 导出模板含填写说明sheet
    - `_f2_valuation_ai.py`：6个AI section端点(valuation-conclusion/impairment-evaluation/reversal-evaluation/fairness-evaluation/cost-analysis/labor-analysis) + 30秒超时
    - _Requirements: 1.3, 14.1~14.6, 16.1~16.6_

- [x] 14. 实现双模式 + 导入导出composable + 集成测试
  - [x] 14.1 创建 `composables/useF2ValuationImportExport.ts` + `composables/useF2ValuationDualMode.ts`
    - useF2ValuationImportExport：el-dropdown"导入导出▾" + axios三端点 + 支持11张sheet参数 + 导入预览确认 + 进度条
    - useF2ValuationDualMode：模式状态(html/onlyoffice) + 切换逻辑 + OO健康检查 + localStorage持久化 + 失败降级
    - _Requirements: 14.1~14.6, 17.1~17.6_

  - [x] 14.2 编写集成测试
    - 测试sheetName分发正确性（13个sheet名→对应子组件）
    - 测试NRV公式链全路径（输入售价/扣减→NRV→跌价→EventBus发布）
    - 测试计价测试3种method差异计算
    - 测试F2-44从F2-41/42/43自动取数（allResponses链）
    - 测试F2-47三区段Tab切换+行同步
    - 测试F2-49两区段Tab切换+转回上限约束
    - 测试F2-52关联交易差异率高亮
    - 测试导入导出round-trip（导出模板→导入数据→校验通过）
    - 测试EventBus(impairment:calculated)跨组件传递
    - _Requirements: 全部_

- [x] 15. 性能优化与UI打磨
  - 虚拟滚动验证（F2-38计价94行/F2-39先进先出75行/F2-40标准成本64行/F2-47跌价测试59行）
  - 区段Tab切换debounce 300ms验证
  - defineAsyncComponent lazy验证
  - 13px字体/AI按钮右对齐/公式列虚线tooltip/min-width/el-card包裹/details折叠 全验证
  - _Requirements: 18.1~18.8_

- [x] 16. 最终验收
  - 所有PBT测试通过（P1~P10）
  - 所有集成测试通过
  - 13个sheet逐一验证渲染正确
  - NRV公式链→EventBus→F2-1联动正确
  - 宽表拆分(F2-47三区段/F2-49两区段)行同步正确
  - 导入导出11张表round-trip
  - 双模式切换稳定
  - 代码审查通过


- [x] 17. 抽凭引擎集成
  - [x] 17.1 F2-38~F2-40计价测试表集成GtVoucherSamplingEngine
    - 在F2ValuationTestSheet.vue通用组件抽样参数区添加"使用抽凭引擎"按钮
    - import GtVoucherSamplingEngine组件（dialog模式）
    - 点击按钮打开dialog，预填总体金额（从samplingParams取）+ 科目代码（存货科目1401~1412）
    - 用户确认后将选中样本映射到计价测试动态行（品名/期初数量/金额/凭证编号等字段）
    - 自动更新抽样参数区字段（样本量/抽样方法/置信水平）
    - 已填入行添加tooltip来源标记"来自抽凭引擎 {algorithm}"
    - 因F2ValuationTestSheet为通用组件，3种计价方法(F2-38/39/40)自动继承此能力
    - _Requirements: 19_

- [x] 18. 版本链集成
  - [x] 18.1 集成useVersionTrail到GtF2InventoryValuation主入口
    - import useVersionTrail composable并调用useVersionTrail(wpId)
    - 在save成功后调用versionTrail.autoSnapshot()
    - 工具栏右侧添加"版本历史"按钮（el-button icon="Clock"）
    - 点击打开GtWpVersionTrail drawer（direction="rtl" size="400px"）
    - 支持手动创建命名快照
    - provide('openReviewDialog', openReviewDialog) 供子组件inject
    - _Requirements: 20_

- [x] 19. 行级OCR集成（F2-47跌价测试）
  - [x] 19.1 F2-47跌价准备测试表📎OCR列
    - 在F2TabImpairmentTest.vue NRV测算区段每行添加📎列（el-upload按钮）
    - 上传文件POST /api/workpapers/{wp_id}/f2-valuation/contract-ocr（multipart/form-data）
    - 后端端点识别采购发票→返回extracted_fields（估计售价/品名/规格/数量）
    - 弹出ElMessageBox.confirm确认弹窗显示识别结果
    - 置信度<80%字段橙色高亮
    - 确认后merge到当前行（估计售价→估计售价列/品名→品名列等）
    - 上传成功后📎列显示Document图标，hover预览
    - _Requirements: 21_
