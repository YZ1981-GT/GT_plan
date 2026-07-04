# Implementation Plan: F2 存货底稿核心组专属HTML精美组件

## Overview

实现F2存货底稿核心组专属组件`f2-inventory-main`。按依赖顺序：注册→公式引擎→基础设施→通用组件→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtF2InventoryMain.vue + 17个子组件（含2通用） + 12个composable + 后端4个py文件。科目1401~1412存货（借方/资产类），核心公式：期末=期初+增加-减少；净值=原值-跌价准备；审定=未审+AJE；库龄合计=Σ4段。三大块审定表(148行) + 11张通用明细表 + 4张通用截止测试 + 3张分析表 + 3张检查表。F循环最大科目底稿(35 sheet)。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3"] },
    { "id": "wave5", "tasks": ["6.1", "7.1", "8.1"] },
    { "id": "wave6", "tasks": ["10.1", "11.1", "12.1", "12.2", "13.1"] },
    { "id": "wave7", "tasks": ["15.1", "15.2", "15.3", "15.4", "15.5", "15.6"] },
    { "id": "wave8", "tasks": ["16.1", "16.2"] },
    { "id": "wave9", "tasks": ["17.1", "17.2", "17.3", "17.4"] },
    { "id": "wave10", "tasks": ["18.1", "18.2", "18.3", "18.4"] },
    { "id": "wave11", "tasks": ["19.1", "19.2"] },
    { "id": "wave12", "tasks": ["20.1", "20.2", "20.3"] },
    { "id": "wave13", "tasks": ["21.1"] },
    { "id": "wave14", "tasks": ["23.1"] },
    { "id": "wave15", "tasks": ["24.1", "24.2"] },
    { "id": "wave16", "tasks": ["25.1"] }
  ]
}
```

> **代码同步（2026-07-04）**：下列 `[x]` 已与仓库实现对齐；`[ ]*` 为可选 PBT；Checkpoint/最终验收/性能打磨仍待人工确认。


## Notes

- F2-3~F2-13共11张明细表使用通用组件F2DetailSheet.vue（config驱动差异），仅F2-10开发产品因35列特殊用F2DetailSheetDev.vue
- F2-29~F2-32共4张截止测试使用通用组件F2CutoffSheet.vue（config驱动差异）
- 审定表三大块结构(原值/跌价/净值)是F2特有设计，不同于D4/F1的单级或两级结构
- 13类别存货→1401~1412科目映射是TB回写的关键，需逐一确认映射关系
- F2-7委托加工287行是全spec最多行的表，必须验证虚拟滚动性能
- F2-10开发产品35列是全spec最宽的表，5区段Tab必须验证切换流畅性

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将F2/F2-1~F2-14/F2-16/F2-18~F2-20/F2-29~F2-35映射为'f2-inventory-main'（约30个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'f2-inventory-main'
    - 在 `htmlRendererRegistry.ts` 中注册 'f2-inventory-main' → GtF2InventoryMain 映射
    - 创建 `GtF2InventoryMain.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy + selfLoad逻辑 + OnlyOffice fallback）
    - _Requirements: 1.1, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [x]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'f2-inventory-main'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证F2/F2-1~F2-14/F2-16/F2-18~F2-20/F2-29~F2-35共30个映射
    - _Requirements: 1.5, 1.6, 1.7_

- [x] 2. 实现共享公式引擎 useF2FormulaEngine.ts
  - [x] 2.1 创建 `composables/useF2FormulaEngine.ts`，实现全部纯函数
    - 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN/Infinity → 0）
    - 实现 `calcEndBalance`（期末 = 期初 + 增加 - 减少）
    - 实现 `calcNetValue`（净值 = 原值 - 跌价准备）
    - 实现 `calcAuditedAmount`（审定 = 未审 + AJE）
    - 实现 `calcUnitPrice`（单价 = 金额/数量，数量=0→'-'）
    - 实现 `calcAgingTotal`（库龄合计 = Σ4段）
    - 实现 `calcSubtotal`（合计 = SUM数组）
    - 实现 `calcChangeRate`（变动率：期初=0且期末=0→''/期初=0→'N/A'/其他→(期末-期初)/期初）
    - 实现 `calcTurnoverRate`（周转率 = 营业成本/平均存货余额）
    - 实现 `calcCoverageRatio`（检查比例 = 检查金额/账面金额×100）
    - 实现 `calcProductionSalesRate`（产销率 = 销量/产量×100%）
    - 实现 `calcDaysBetween`（日期差天数计算）
    - 实现 `isCutoffCorrect`（截止正确判定：入库/记账日期 vs 期末）
    - _Requirements: 18.1~18.13_

  - [x]* 2.2 编写 Property 1 PBT：期末余额公式
    - 生成器：`fc.float({min:-1e9, max:1e9})` × opening/increase/decrease
    - 断言：calcEndBalance(opening, increase, decrease) === opening + increase - decrease
    - **Property 1: 期末=期初+增加-减少**
    - **Validates: Requirements 18.2, 5.3, 5.4**

  - [x]* 2.3 编写 Property 2 PBT：净值=原值-跌价准备
    - 生成器：`fc.float({min:0, max:1e9})` × 2
    - 断言：calcNetValue(originalValue, impairment) === originalValue - impairment
    - **Property 2: 净值=原值-跌价准备**
    - **Validates: Requirements 18.3, 2.5**

  - [x]* 2.4 编写 Property 3 PBT：审定数=未审+AJE
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 2
    - 断言：calcAuditedAmount(unadjusted, aje) === unadjusted + aje
    - **Property 3: 审定数=未审+AJE**
    - **Validates: Requirements 18.4, 2.3**

  - [x]* 2.5 编写 Property 4 PBT：合计行=SUM(明细行)
    - 生成器：`fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:50})`
    - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
    - **Property 4: 合计行=SUM(明细行)**
    - **Validates: Requirements 18.7, 5.6**

  - [x]* 2.6 编写 Property 5 PBT：库龄合计=Σ4段
    - 生成器：`fc.float({min:0, max:1e9})` × 4
    - 断言：calcAgingTotal(a,b,c,d) === a+b+c+d
    - **Property 5: 库龄合计=Σ4段**
    - **Validates: Requirements 18.6, 5.7**

  - [x]* 2.7 编写 Property 6 PBT：单价=金额/数量
    - 生成器：`fc.float({min:-1e9, max:1e9})` amount + `fc.float({min:0.001, max:1e6})` qty（避免0）
    - 断言：calcUnitPrice(amount, qty) === amount/qty；calcUnitPrice(x, 0) === '-'
    - **Property 6: 单价=金额/数量**
    - **Validates: Requirements 18.5, 5.5**

  - [x]* 2.8 编写 Property 7 PBT：变动率边界处理
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 2（含0边界策略）
    - 断言：calcChangeRate(0,0)===''; calcChangeRate(0,x)==='N/A'(x≠0); calcChangeRate(a,b)===(b-a)/a(a≠0)
    - **Property 7: 变动率边界处理**
    - **Validates: Requirements 18.8**

  - [x]* 2.9 编写 Property 8 PBT：产销率公式
    - 生成器：`fc.float({min:0.1, max:1e6})` × sales/production
    - 断言：calcProductionSalesRate(sales, production) === sales/production*100
    - **Property 8: 产销率=销量/产量×100%**
    - **Validates: Requirements 18.11, 9.5**

  - [x]* 2.10 编写 Property 9 PBT：检查比例公式
    - 生成器：`fc.float({min:0, max:1e9})` checked + `fc.float({min:0.01, max:1e9})` total
    - 断言：calcCoverageRatio(checked, total) === checked/total*100
    - **Property 9: 检查比例=检查金额/账面金额×100**
    - **Validates: Requirements 18.10, 12.3**

- [x] 3. 实现 useF2FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useF2FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate（PUT单条response）
    - 实现 debouncedSave（2秒debounce版本）
    - 实现 saveBatch（批量保存）
    - 实现 writebackTrialBalance（回写存货科目组1401~1412，按类别映射）
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=f2-inventory-main）
    - _Requirements: 1.8, 3.8_

- [x] 4. 实现 useF2CrossSheet.ts 跨Sheet联动
  - [x] 4.1 创建 `composables/useF2CrossSheet.ts`
    - 实现 detailToSummaryAggregation computed（F2-3~F2-13各表合计行→F2-2汇总表各行）
    - 实现 summaryToAdjudicationAggregation computed（F2-2汇总→F2-1原值区各类别未审数行）
    - 实现 adjustmentToAdjudication computed（F2-14 AJE合计→F2-1账项调整行）
    - 实现 netValueComputed computed（F2-1原值审定 - F2-1跌价审定 → F2-1净值区）
    - 实现 adjudicationToDisclosure computed（F2-1审定数→附注引用）
    - 实现 detailAgingToDisclosure computed（明细表库龄→附注库龄分布）
    - 实现 detailToOverallAnalysis computed（明细数据→F2-18总体分析取数）
    - _Requirements: 3.1~3.10, 4.2, 8.8, 15.4, 15.5_

  - [x]* 4.2 编写 Property 10 PBT：明细→汇总聚合正确性
    - 生成器：自定义多张DetailRow[]生成器（11种类别随机行数）
    - 断言：汇总表各类别行 === 对应明细表合计行数据
    - **Property 10: 明细→汇总聚合正确性**
    - **Validates: Requirements 3.1, 4.2**

  - [x]* 4.3 编写 Property 11 PBT：审定表净值=原值-跌价
    - 生成器：自定义13类别原值+跌价审定数生成器
    - 断言：∀ 13类别: netValueRow[i].endAmount === originalRow[i].endAudited - impairmentRow[i].endAudited
    - **Property 11: 审定表净值=原值-跌价（13类别）**
    - **Validates: Requirements 2.5, 2.10, 3.10**

- [ ] 5. Checkpoint - 公式引擎与基础设施验证
  - Ensure all PBT tests pass, ask the user if questions arise.

- [x] 6. 实现 useF2Adjudication.ts 审定表F2-1（三大块结构）
  - [x] 6.1 创建 `composables/useF2Adjudication.ts`
    - 定义 `AdjudicationRow` 类型（rowKey/label/category/section/rowType/期初数/本期增加/本期减少/期末数/索引/isDynamic/isTotal）
    - 定义三大块固定行配置：
      - section='originalValue'：13类别×3行(未审/账项调整/审定) + 合计行
      - section='impairment'：13类别×3行(同结构) + 合计行
      - section='netValue'：13类别审定净值行(只读) + 合计行
      - 底部：试算平衡表数行 + 差异数行
    - 13类别常量：原材料/材料采购在途/周转材料/自制半成品/委托加工/库存商品/发出商品/开发产品/开发成本/合同履约成本/消耗性生物资产/商品进销差价/存货跌价准备
    - 实现 `originalValueRows` computed + `impairmentRows` computed + `netValueRows` computed
    - 实现 `originalTotalRow` computed + `impairmentTotalRow` computed + `netValueTotalRow` computed
    - 实现 公式链：审定=未审+账项调整；期末=期初+增加-减少；净值=原值审定-跌价审定
    - 实现 trialBalanceAmounts（从TB auto_data取数科目组1401~1412）+ trialBalanceDiff
    - 实现 netValueValidation computed（净值合计===原值合计-跌价合计，否则红色警告）
    - 实现 auditNote + auditConclusion 双向绑定（textarea+AI按钮）
    - 实现 updateCell（编辑 → 公式重算 → debouncedSave）
    - 实现 publishAdjudicated（EventBus: substantive:adjudicated）
    - 实现 EventBus 监听 `adjustment:created`
    - 实现 writebackTrialBalance（按类别映射回写1401~1412）
    - 实现序列化/反序列化（JSON.stringify → F2-adjudication remark字段）
    - _Requirements: 2.1~2.10, 3.1~3.10_

- [x] 7. 实现 useF2DetailSheet.ts 通用明细表逻辑
  - [x] 7.1 创建 `composables/useF2DetailSheet.ts`
    - 定义 `DetailRow` 通用类型（品名/规格/期初数量/期初单价/期初金额/增加数量/增加单价/增加金额/减少数量/减少单价/减少金额/期末数量/期末单价/期末金额/库龄1年以内/库龄1-2年/库龄2-3年/库龄3年以上 + 扩展字段map）
    - 实现 `createDetailSheetComposable(config: DetailSheetConfig)` 工厂函数
    - 实现 `rows` reactive（从 F2-{code}-detail-rows remark JSON加载）
    - 实现 `totalRow` computed（SUM全部行各金额/数量列）
    - 实现 `filterByName` + `filteredRows` computed（按品名搜索）
    - 实现行公式链：期末数量=期初+增加-减少；期末金额=期初+增加-减少；单价=金额/数量
    - 实现 `agingValidation` computed（库龄合计 vs 期末金额校验）
    - 实现 `updateCell`（编辑→公式重算→debounce保存）
    - 实现 `addRow(name)`（先弹ElMessageBox.prompt输入品名）
    - 实现 `removeRow(rowId)`
    - 实现序列化/反序列化
    - 实现区段Tab配置导出（segmentConfigs）
    - 实现长期积压标记（库龄3年以上有值→isLongTerm）
    - _Requirements: 5.1~5.15_

- [x] 8. 实现 useF2Adjustment.ts 调整分录
  - [x] 8.1 创建 `composables/useF2Adjustment.ts`
    - 定义 `AdjustmentRow` 类型（序号/调整事项说明/科目编码/科目名称/借方金额/贷方金额/分录类型/索引/备注/附注项目）
    - 实现 `rows` reactive + `totalRow` computed + `balanceCheck` computed
    - 实现 `updateCell` + `addRow` + `removeRow`
    - 实现 EventBus 发布 `adjustment:created`
    - 实现序列化/反序列化
    - _Requirements: 6.1~6.8_

- [ ] 9. Checkpoint - 审定表+明细表+调整分录验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. 实现 useF2Policy.ts 会计政策
  - [x] 10.1 创建 `composables/useF2Policy.ts`
    - 定义政策区域结构（5个区域：分类确认/初始计量/发出计价/跌价政策/盘点制度）
    - 每区域：政策描述/是否变更/变更原因/审计评价/索引
    - 实现 `sections` reactive + `updateSection`
    - 实现变更联动（是否变更=是→展开变更原因）
    - 实现序列化/反序列化
    - _Requirements: 7.1~7.6_

- [x] 11. 实现 useF2Analysis.ts 分析组通用
  - [x] 11.1 创建 `composables/useF2Analysis.ts`
    - F2-18总体分析：结构分析/周转分析/趋势分析/异常识别4区块
    - F2-19产销量变动：产量/销量/库存3区段Tab + 产销率计算
    - F2-20成本比较：本期/上期成本+变动分析2区段Tab + 变动率计算
    - 实现 `overallAnalysis` computed（从F2-1+F2-2取数）
    - 实现 `productionSalesRows` reactive + `costComparisonRows` reactive
    - 实现图表数据computed（结构饼图/趋势折线图/周转柱状图）
    - 实现AI生成分析结论
    - 实现序列化/反序列化
    - _Requirements: 8.1~8.8, 9.1~9.9, 10.1~10.7_

- [x] 12. 实现 useF2CutoffTest.ts 截止测试通用
  - [x] 12.1 创建 `composables/useF2CutoffTest.ts`
    - 定义 `CutoffRow` 类型（入库版15列/出库版10列差异）
    - 实现 `createCutoffComposable(config: CutoffSheetConfig)` 工厂函数
    - 实现 `rows` reactive + `totalRow` computed
    - 实现 `isCutoffCorrect` 自动判定（入库日期/记账日期 vs 期末日期）
    - 实现 `cutoffSummary` computed（正确笔数/错误笔数/涉及金额）
    - 实现 `updateCell` + `addRow` + `removeRow`
    - 实现序列化/反序列化
    - _Requirements: 11.1~11.8_

  - [x]* 12.2 编写 Property 12 PBT：截止判定幂等性
    - 生成器：自定义日期组合生成器（入库日期/记账日期/期末日期）
    - 断言：isCutoffCorrect结果确定且幂等（同输入多次调用同结果）
    - **Property 12: 截止判定幂等**
    - **Validates: Requirements 18.13, 11.4**

- [x] 13. 实现 useF2PurchaseInspection.ts 检查组
  - [x] 13.1 创建 `composables/useF2InspectionCheck.ts`（F2-33/34/35，wp 路由至 valuation bundle）
    - F2-33采购入库检查（22列固定+滚动）
    - F2-34材料领用检查（15列）
    - F2-35委托加工核查（9列+在外天数计算）
    - 实现 `purchaseRows` reactive + `materialUsageRows` reactive + `subcontractingRows` reactive
    - 实现 `coverageRatio` computed（检查比例=检查金额/账面金额）
    - 实现 `isCoverageLow` computed（<50%预警）
    - 实现 `daysOutstanding` computed（F2-35在外天数=收回日期-委托日期）
    - 实现 `isLongOutstanding` computed（>180天高亮）
    - 实现 `updateCell` + `addRow` + `removeRow`
    - 实现行级OCR上传（复用/d4/contract-ocr端点）
    - 实现序列化/反序列化
    - _Requirements: 12.1~12.8, 13.1~13.7, 14.1~14.7_

- [ ] 14. Checkpoint - 分析+截止+检查验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. 实现 Vue子组件 - core/目录
  - [x] 15.1 创建 `f2/core/F2TabProcedure.vue`（F2A程序表）
    - 复用 GtAProgramConsole 组件 + selfLoad逻辑
    - _Requirements: 1.1_

  - [x] 15.2 创建 `f2/core/F2TabAdjudication.vue`（F2-1审定表三大块）
    - 调用 useF2Adjudication.ts
    - 渲染三个可折叠el-card（原值/跌价/净值）
    - 每块内el-table：项目 | 期初数 | 本期增加 | 本期减少 | 期末数 | 索引
    - 13类别×3行(未审/调整/审定) per块 + 合计行
    - 净值区只读（=原值审定-跌价审定）
    - 底部试算表数+差异(≠0红色) + 审计说明+结论(el-card+AI按钮右对齐)
    - 净值校验（合计不一致红色警告条）
    - GtIndexChip索引列 + 公式列虚线下划线tooltip
    - UI铁律：13px/min-width自适应/编制提示details折叠
    - _Requirements: 2.1~2.10_

  - [x] 15.3 创建 `f2/core/F2TabDetailSummary.vue`（F2-2明细汇总）
    - 调用 useF2CrossSheet.detailToSummaryAggregation
    - 只读el-table 17列 + 合计行
    - GtIndexChip点击类别行跳转明细表
    - 库龄合计≠期末时橙色高亮
    - _Requirements: 4.1~4.7_

  - [x] 15.4 创建 `f2/core/F2TabAdjustment.vue`（F2-14调整分录）
    - 调用 useF2Adjustment.ts
    - el-table 10列 + 动态行增删 + 借贷不平衡红色警告
    - 科目名称下拉(1401~1412+对方科目) + GtIndexChip索引列
    - _Requirements: 6.1~6.8_

  - [x] 15.5 创建 `f2/core/F2TabDisclosureListed.vue`（附注上市版）
    - 存货分类明细表 + 库龄分析表 + 跌价准备变动表
    - 从F2-1+明细表自动取数 + 占比计算
    - _Requirements: 15.1~15.7_

  - [x] 15.6 创建 `f2/core/F2TabDisclosureSoe.vue`（附注国企版）
    - 简化版存货分类表 + 跌价准备情况
    - _Requirements: 15.1, 15.3_

- [x] 16. 实现 Vue子组件 - detail/目录
  - [x] 16.1 创建 `f2/detail/F2DetailSheet.vue`（通用明细表组件）
    - 接收 `config: DetailSheetConfig` prop
    - 渲染区段Tab切换（期初/增加/减少/期末/库龄，每区段≤8列）
    - 区段间行同步（切换保持当前行选中）
    - 动态行增删（ElMessageBox.prompt输入品名后创建）
    - 合计行 + 公式自动计算（期末=期初+增加-减少/单价=金额÷数量）
    - 库龄合计校验（≠期末金额橙色高亮）
    - 长期积压标记（3年以上有值橙色背景行）
    - 虚拟滚动（>100行，F2-7委托加工287行）
    - 搜索筛选（品名模糊搜索）
    - 导入导出按钮（el-dropdown三选项）
    - UI铁律：13px/公式列虚线/min-width/编制提示
    - _Requirements: 5.1~5.13, 5.15_

  - [x] 16.2 创建 `f2/detail/F2DetailSheetDev.vue`（F2-10开发产品专用35列→5区段）
    - 继承F2DetailSheet.vue逻辑但区段不同：基础信息/土地成本/建安成本/资本化利息/其他+结转
    - 每区段6-8列
    - _Requirements: 5.14_

- [x] 17. 实现 Vue子组件 - analysis/目录
  - [x] 17.1 创建 `f2/analysis/F2TabPolicy.vue`（F2-16会计政策）
    - 调用 useF2Policy.ts
    - 5个结构化区域（el-card per区域）
    - 每区域：政策描述textarea/是否变更下拉/变更原因(条件展示)/审计评价textarea/GtIndexChip
    - 底部政策评价结论textarea + AI按钮
    - _Requirements: 7.1~7.6_

  - [x] 17.2 创建 `f2/analysis/F2TabOverallAnalysis.vue`（F2-18总体分析）
    - 调用 useF2Analysis.ts
    - 4区块：结构分析(饼图+表格)/周转分析(柱状图)/趋势分析(折线图)/异常识别(标记列表)
    - 从F2-1+F2-2自动取数
    - 异常自动标记（周转下降>20%/库龄占比>10%/增长率异常）
    - 底部分析结论textarea + AI按钮
    - _Requirements: 8.1~8.8_

  - [x] 17.3 创建 `f2/analysis/F2TabProductionSales.vue`（F2-19产销量变动）
    - 调用 useF2Analysis.ts
    - 3区段Tab（产量变动/销量变动/库存变动）
    - 产销率<80%橙色高亮（滞销风险）
    - 库存平衡校验（期初+入库-出库≠期末红色高亮）
    - 动态行增删 + 合计行 + 分析结论textarea + AI
    - _Requirements: 9.1~9.9_

  - [x] 17.4 创建 `f2/analysis/F2TabCostComparison.vue`（F2-20成本比较）
    - 调用 useF2Analysis.ts
    - 2区段Tab（本期成本/上期+变动分析）
    - 变动率>20%红色高亮+要求填写异常说明
    - 动态行增删 + AI辅助异常说明
    - _Requirements: 10.1~10.7_

- [x] 18. 实现 Vue子组件 - inspection/目录
  - [x] 18.1 创建 `f2/inspection/F2CutoffSheet.vue`（通用截止测试组件）
    - 接收 `config: CutoffSheetConfig` prop
    - 入库版15列/出库版10列差异渲染
    - 截止不正确红色高亮行
    - 动态行增删 + 合计行
    - 底部汇总（正确/错误笔数/涉及金额）+ 截止结论textarea + AI
    - _Requirements: 11.1~11.8_

  - [x] 18.2~18.4 采购/领用/委托加工检查（`f2/valuation/F2TabPurchaseInboundCheck` 等，wp F2-33~35 → valuation bundle）
    - useF2InspectionCheck + GtVoucherSamplingEngine + 📎OCR
    - _Requirements: 12.1~14.7（见 f2-inventory-valuation-impairment）_

- [x] 19. 实现导入导出 composable + 后端端点
  - [x] 19.1 创建 `composables/useF2ImportExport.ts`
    - el-dropdown"导入导出▾"（导出模板/导出数据/导入数据）
    - axios调用后端三端点（export-template/export-data/import-data）
    - 支持sheet参数（F2-3~F2-13/F2-14/F2-19/F2-20/F2-29~F2-35）
    - 导入预览+确认弹窗
    - 进度条显示
    - _Requirements: 16.1~16.6_

  - [x] 19.2 创建 `backend/app/routers/wp_render_strategies/_f2_import_export.py`
    - 实现 `export_f2_template` 端点（POST /api/workpapers/{wp_id}/f2/export-template?sheet={code}）
    - 实现 `import_f2_data` 端点（POST /api/workpapers/{wp_id}/f2/import-data?sheet={code}，multipart）
    - 实现 `export_f2_data` 端点（POST /api/workpapers/{wp_id}/f2/export-data?sheet={code}）
    - openpyxl生成/解析，数据校验（列头+类型+库龄合计）
    - StreamingResponse中文文件名RFC5987编码
    - 导出模板含填写说明sheet
    - _Requirements: 16.1~16.6_

- [x] 20. 实现后端Render策略 + AI生成 + Resolvers
  - [x] 20.1 创建 `backend/app/routers/wp_render_strategies/_f2_inventory_main.py`
    - 实现 `render_f2_inventory_main` 函数
    - 注册 RENDERER_DISPATCH['f2-inventory-main'] = render_f2_inventory_main
    - 返回 componentType='f2-inventory-main' + sheets配置
    - 支持 force_component_type 参数
    - _Requirements: 1.5, 1.8_

  - [x] 20.2 创建 `backend/app/routers/wp_render_strategies/_f2_ai_generate.py`
    - 实现5个AI section端点：adj-note/adj-conclusion/analysis-conclusion/cutoff-conclusion/policy-evaluation
    - POST /api/workpapers/F2/ai/{section}
    - 集成AI服务+超时30秒
    - _Requirements: 19.1~19.6_

  - [x] 20.3 创建 `backend/app/routers/wp_render_strategies/_f2_resolvers.py`（可选，按需）
    - resolver: f2_tb_inventory（从TB取存货科目组1401~1412审定数）
    - resolver: f2_detail_aggregation（明细表→汇总表聚合）
    - resolver: f2_aging_distribution（库龄分布统计）
    - 注册到 _REGISTRY
    - _Requirements: 2.6, 8.8_

- [x] 21. 实现双模式切换
  - [x] 21.1 创建 `composables/useF2DualMode.ts`
    - 实现模式状态管理（reactive mode: 'html' | 'onlyoffice'）
    - 实现切换逻辑（HTML→OO: 隐藏Vue组件显示GtOnlyOfficeSheet / OO→HTML: 重载Vue组件）
    - 实现OO sheet名匹配（必须与源xlsx tab名完全一致）
    - 实现OO健康检查（health.data?.data?.healthy双层兼容）
    - 实现localStorage持久化
    - 实现加载失败降级（自动回HTML+toast提示）
    - _Requirements: 17.1~17.7_

- [ ] 22. Checkpoint - 全组件+后端验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 23. 集成测试
  - [x] 23.1 编写集成测试
    - 测试sheetName分发正确性（35个sheet名→对应子组件）
    - 测试审定表三大块联动（净值=原值-跌价全13类别）
    - 测试明细表→汇总表→审定表聚合链（编辑明细→汇总自动更新→审定表自动更新）
    - 测试调整分录联动（F2-14→F2-1 AJE自动更新）
    - 测试通用明细表组件（11种config渲染正确）
    - 测试通用截止测试组件（4种config渲染正确）
    - 测试导入导出流程（导出模板→导入数据→校验通过）
    - 测试双模式切换（HTML↔OO数据同步）
    - 测试TB回写（13类别→1401~1412科目正确映射）
    - _Requirements: 全部_

- [ ] 24. 性能优化与UI打磨
  - [x] 24.1 实现性能优化
    - F2-7委托加工(287行)虚拟滚动验证
    - F2-10开发产品(35列)5区段Tab渲染验证
    - 跨sheet debounce 2秒验证
    - defineAsyncComponent lazy验证（首屏仅加载当前sheet组件）
    - 公式缓存命中率验证
    - _Requirements: 20.5~20.8_

  - [x] 24.2 UI规范验证
    - 13px字体全局验证
    - AI+复核按钮右对齐验证
    - 公式列虚线下划线+tooltip验证
    - min-width自适应验证
    - 审计说明el-card包裹验证
    - 编制提示details折叠验证
    - _Requirements: 20.1~20.4_

- [ ] 25. 最终验收
  - [x] 25.1 最终验收检查
    - 所有PBT测试通过（P1~P12）
    - 所有集成测试通过
    - 35个sheet逐一验证渲染正确
    - 三大块审定表13类别公式全正确
    - 导入导出11张明细表+7张检查表
    - 双模式切换稳定
    - TB回写13科目正确
    - 代码审查通过


- [ ] 26. 抽凭引擎集成（F2-33/34 已实现在 f2-inventory-valuation，见该 spec Task 17）
  - [x] 26.1 F2-33/F2-34检查表集成GtVoucherSamplingEngine
    - 在F2TabPurchaseInspection.vue和F2TabMaterialUsage.vue抽样参数区添加"使用抽凭引擎"按钮
    - import GtVoucherSamplingEngine组件（dialog模式）
    - 点击按钮打开dialog，F2-33预填总体金额+存货科目1401~1412借方发生；F2-34预填贷方发生
    - 用户确认后将选中样本映射到检查表动态行（供应商名称/日期/凭证编号/金额等字段）
    - 自动更新抽样参数区（样本量/抽样方法）
    - 已填入行添加tooltip来源标记"来自抽凭引擎 {algorithm}"
    - _Requirements: 21_

- [x] 27. 截止测试自动提取
  - [x] 27.1 F2-29~F2-32集成useCutoffAutoSampling
    - 在F2CutoffSheet.vue表格上方添加"自动提取"按钮（el-button type="primary" icon="lightning-bolt"）
    - import useCutoffAutoSampling composable
    - 点击按钮调用useCutoffAutoSampling.extract({direction, periodEndDate, daysBefore:5, daysAfter:5})
    - 根据config.type决定direction：F2-29/F2-30→'inbound'；F2-31/F2-32→'outbound'
    - 正向(F2-29/F2-31)：提取期末后N天单据检查是否入账；反向(F2-30/F2-32)：提取期末前N天入账检查是否有单据
    - 提取结果显示ElMessageBox预览（列表形式，显示日期/凭证号/金额/供应商）
    - 用户确认后批量填入截止测试表动态行
    - 已填入行添加tooltip来源标记"自动提取 {date_range}"
    - 无序时账数据时按钮disabled + tooltip提示
    - _Requirements: 22_

- [x] 28. 版本链集成
  - [x] 28.1 集成useVersionTrail到GtF2InventoryMain主入口
    - import useVersionTrail composable并调用useVersionTrail(wpId)
    - 在save成功后调用versionTrail.autoSnapshot()
    - 工具栏右侧添加"版本历史"按钮（el-button icon="Clock"）
    - 点击打开GtWpVersionTrail drawer
    - 支持手动创建命名快照
    - _Requirements: 23_

- [x] 29. 附注模块EventBus联动
  - [x] 29.1 附注Tab订阅substantive:adjudicated事件
    - 在F2TabDisclosureListed.vue和F2TabDisclosureSoe.vue中subscribe EventBus `substantive:adjudicated`
    - 回调检查payload.wpCode==='F2' && accountCodes含1401~1412
    - 匹配则刷新附注数据 + 显示蓝色info bar "数据已更新"（3秒消失）
    - _Requirements: 24_

  - [x] 29.2 审定表发布disclosure:note-text-updated事件
    - 在useF2Adjudication.ts中watch auditNote/auditConclusion变更
    - 变更时debounce 2秒后publish `disclosure:note-text-updated`
    - _Requirements: 24_

  - [x] 29.3 GtF2InventoryMain provide openReviewDialog
    - provide('openReviewDialog', openReviewDialog)
    - 子组件inject使用，section标题栏右对齐复核按钮
    - _Requirements: 24_

- [ ] 30. 行级OCR集成（F2-33 📎 已实现在 f2-inventory-valuation Task 19）
  - [x] 30.1 F2-33采购入库检查表📎OCR列
    - 在F2TabPurchaseInspection.vue每行添加📎列（el-upload按钮）
    - 上传文件POST /api/workpapers/{wp_id}/f2/contract-ocr（multipart/form-data）
    - 后端复用D4 contract-ocr端点模式（OCR识别→返回extracted_fields JSON）
    - 前端收到结果后弹出ElMessageBox.confirm确认弹窗：显示识别出的字段（采购订单号/日期/金额/供应商/发票号）
    - 置信度<80%字段橙色高亮提示人工核对
    - 确认后merge到当前行对应列（采购订单号→采购订单号列/发票号→发票号列/金额→金额列等）
    - 上传成功后📎列显示Document图标，hover预览
    - _Requirements: 25_
