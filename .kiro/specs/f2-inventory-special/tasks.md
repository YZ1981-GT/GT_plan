# Implementation Plan: F2 存货底稿特殊组（合同履约成本 + IPO/舞弊应对）专属HTML精美组件

## Overview

实现F2存货底稿特殊组专属组件`f2-inventory-special`。按依赖顺序：注册→公式引擎→基础设施→合同组composable+Vue→IPO组composable+Vue→后端→双模式→集成测试。主入口GtF2InventorySpecial.vue + 18个子组件 + 10个composable + 后端3个py文件。覆盖2个xlsx源模板/18有效sheet。合同履约成本组(F2-55~F2-58)对所有项目可见；IPO/舞弊应对组(F2-61~F2-72)仅IPO/上市/新三板/重组项目可见（business_category控制）。核心公式：减值=max(0,账面-可收回)；亏损判定=总成本>总收入；预计损失=(总成本-总收入)×(1-完工进度)。F2-55最宽(37列→6区段Tab)；F2-64最多行(232行虚拟滚动+产品折叠)；F2-68固定+滚动(25列)；F2-70/F2-72多公司Master-Detail。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3"] },
    { "id": "wave5", "tasks": ["5.1", "5.2", "5.3"] },
    { "id": "wave6", "tasks": ["7.1", "7.2", "7.3", "7.4"] },
    { "id": "wave7", "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5"] },
    { "id": "wave8", "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5", "10.6", "10.7", "10.8"] },
    { "id": "wave9", "tasks": ["11.1", "11.2"] },
    { "id": "wave10", "tasks": ["12.1", "12.2"] },
    { "id": "wave11", "tasks": ["13.1", "13.2", "13.3"] },
    { "id": "wave12", "tasks": ["14.1"] }
  ]
}
```

## Notes

- F2-55合同履约成本明细(37列)是全spec最宽表，必须拆为6区段Tab确保可操作性
- F2-64单耗分析(232行)是全spec最多行的表，必须虚拟滚动+按产品分组折叠
- F2-70供应商信息核查+F2-72供应商访谈记录采用多公司Master-Detail卡片模式（参照D4合同检查）
- IPO组(F2-61~F2-72)必须有条件可见性控制，非IPO项目不应看到这些底稿
- F2-57减值测算与F2-58亏损判定共享项目数据（总收入/总成本/完工进度），需联动
- F2-68供应商结构(25列)采用固定列(5)+滚动列(20)模式
- 合同履约成本组(F2-55~F2-58)的减值/亏损公式链是核心审计逻辑，PBT优先验证

## Tasks

- [ ] 1. 组件注册与基础配置
  - [ ] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将F2-55A/F2-55~F2-58/F2-61A/F2-61~F2-72映射为'f2-inventory-special'（共18个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'f2-inventory-special'
    - 在 `htmlRendererRegistry.ts` 中注册 'f2-inventory-special' → GtF2InventorySpecial 映射
    - 创建 `GtF2InventorySpecial.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy + selfLoad逻辑 + OnlyOffice fallback + IPO条件可见性computed）
    - _Requirements: 1.1, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9, 2.1_

  - [ ]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'f2-inventory-special'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证F2-55A/F2-55~F2-58/F2-61A/F2-61~F2-72共18个映射
    - IPO可见性单元测试（business_category ∈ IPO类别集合→true；其他→false）
    - _Requirements: 1.5, 1.6, 1.7, 2.1, 2.2_

- [ ] 2. 实现共享公式引擎 useF2SpecialFormulaEngine.ts
  - [ ] 2.1 创建 `composables/useF2SpecialFormulaEngine.ts`，实现全部纯函数
    - 实现 `calcRemainingCost`（待发生成本 = 预计总成本 - 已发生成本）
    - 实现 `calcImpairment`（减值 = max(0, 账面价值 - 可收回金额)）
    - 实现 `calcRecoverableAmount`（可收回金额 = (已确认收入/预计总收入) × 预计总成本；预计总收入=0→0）
    - 实现 `isLossContract`（亏损判定 = 预计总成本 > 预计总收入）
    - 实现 `calcExpectedLoss`（预计损失 = (总成本-总收入) × (1-完工进度)；非亏损→0）
    - 实现 `calcCompletionRate`（完工进度 = 已确认收入/预计总收入；总收入=0→'N/A'）
    - 实现 `calcCapacityUtilization`（产能利用率 = 实际产量/设计产能；设计产能=0→'N/A'）
    - 实现 `calcUnitConsumption`（单位能耗 = 能耗总量/产量；产量=0→'-'）
    - 实现 `calcPriceDeviation`（价差率 = (实际价-参考价)/参考价；参考价=0→'N/A'）
    - 实现 `calcConcentrationRatio`（集中度 = 供应商金额/采购总额）
    - 实现 `calcChecklistCompletion`（核查完成度 = 已完成/(总数-不适用)×100）
    - 实现 `calcSubtotalByCategory`（分类小计 = 设备材料+建安分包+人工+其他）
    - 实现 `calcEndBalance`（期末 = 期初 + 增加 - 减少）
    - 实现 `calcAuditedAmount`（审定 = 期末 + 审计调整）
    - 实现 `calcInputOutputRatio`（投入产出比 = 投入量/产出量；产出量=0→'-'）
    - _Requirements: 18.1~18.15_

  - [ ]* 2.2 编写 Property 1 PBT：待发生成本公式
    - 生成器：`fc.float({min:0, max:1e9})` × totalCost/incurredCost
    - 断言：calcRemainingCost(totalCost, incurredCost) === totalCost - incurredCost
    - **Property 1: 待发生成本=预计总成本-已发生成本**
    - **Validates: Requirements 18.1, 5.3**

  - [ ]* 2.3 编写 Property 2 PBT：减值公式非负性
    - 生成器：`fc.float({min:0, max:1e9})` × bookValue/recoverableAmount
    - 断言：calcImpairment(bookValue, recoverableAmount) >= 0
    - **Property 2: 减值≥0**
    - **Validates: Requirements 18.2, 5.5**

  - [ ]* 2.4 编写 Property 3 PBT：亏损判定一致性
    - 生成器：`fc.float({min:0, max:1e9})` × totalRevenue/totalCost
    - 断言：isLossContract(totalRevenue, totalCost) === (totalCost > totalRevenue)
    - **Property 3: 亏损判定=总成本>总收入**
    - **Validates: Requirements 18.4, 6.2**

  - [ ]* 2.5 编写 Property 4 PBT：预计损失公式
    - 生成器：totalCost > totalRevenue（constrained）+ completionRate ∈ [0,1]
    - 断言：calcExpectedLoss(totalRevenue, totalCost, completionRate) === (totalCost - totalRevenue) × (1 - completionRate)
    - **Property 4: 预计损失=(总成本-总收入)×(1-完工进度)**
    - **Validates: Requirements 18.5, 6.4**

  - [ ]* 2.6 编写 Property 5 PBT：完工进度范围
    - 生成器：recognizedRevenue ∈ [0, 2e9], totalRevenue ∈ (0, 1e9]
    - 断言：calcCompletionRate(recognizedRevenue, totalRevenue) === recognizedRevenue/totalRevenue
    - **Property 5: 完工进度=已确认收入/预计总收入**
    - **Validates: Requirements 18.6, 5.2**

  - [ ]* 2.7 编写 Property 6 PBT：产能利用率公式
    - 生成器：`fc.float({min:0.1, max:1e6})` × actual/designed
    - 断言：calcCapacityUtilization(actual, designed) === actual/designed
    - **Property 6: 产能利用率=实际/设计**
    - **Validates: Requirements 18.7, 9.2**

  - [ ]* 2.8 编写 Property 7 PBT：价差率公式
    - 生成器：actualPrice ∈ ℝ + refPrice ∈ ℝ\{0}
    - 断言：calcPriceDeviation(actualPrice, refPrice) === (actualPrice - refPrice)/refPrice
    - **Property 7: 价差率=(实际-参考)/参考**
    - **Validates: Requirements 18.9, 11.3**

  - [ ]* 2.9 编写 Property 8 PBT：集中度公式
    - 生成器：supplierAmount ∈ (0, 1e9], totalAmount ∈ (0, 1e9]
    - 断言：calcConcentrationRatio(supplierAmount, totalAmount) === supplierAmount/totalAmount
    - **Property 8: 集中度=供应商/总额**
    - **Validates: Requirements 18.10, 13.2**

  - [ ]* 2.10 编写 Property 9 PBT：期末余额公式
    - 生成器：`fc.float({min:-1e9, max:1e9})` × opening/increase/decrease
    - 断言：calcEndBalance(opening, increase, decrease) === opening + increase - decrease
    - **Property 9: 期末=期初+增加-减少**
    - **Validates: Requirements 18.13, 3.2**

  - [ ]* 2.11 编写 Property 10 PBT：分类小计公式
    - 生成器：`fc.float({min:-1e9, max:1e9})` × equipment/construction/labor/other
    - 断言：calcSubtotalByCategory(equipment, construction, labor, other) === equipment + construction + labor + other
    - **Property 10: 小计=设备+建安+人工+其他**
    - **Validates: Requirements 18.12, 3.4**

  - [ ]* 2.12 编写 Property 11 PBT：投入产出比公式
    - 生成器：`fc.float({min:0.1, max:1e6})` × input/output
    - 断言：calcInputOutputRatio(input, output) === input/output
    - **Property 11: 投入产出比=投入/产出**
    - **Validates: Requirements 18.15, 10.4**

  - [ ]* 2.13 编写 Property 12 PBT：核查完成度公式
    - 生成器：completed ∈ [0,10], total ∈ [1,10], notApplicable ∈ [0, total-1]（constrained: total>notApplicable）
    - 断言：calcChecklistCompletion(completed, total, notApplicable) === completed/(total-notApplicable)×100
    - **Property 12: 完成度=已完成/(总数-不适用)×100**
    - **Validates: Requirements 18.11, 14.3**

- [ ] 3. 实现 useF2SpecialFormData.ts 基础数据加载/保存
  - [ ] 3.1 创建 `composables/useF2SpecialFormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate（PUT单条response）
    - 实现 debouncedSave（2秒debounce版本）
    - 实现 saveBatch（批量保存）
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=f2-inventory-special）
    - 实现 isIpoProject computed（从project info获取business_category判定）
    - _Requirements: 1.8, 2.1, 2.4_

- [ ] 4. 实现合同履约成本组composable
  - [ ] 4.1 创建 `composables/useF2ContractCost.ts`（F2-55/F2-56）
    - 定义 `ContractCostRow` 类型（37列完整字段：项目编码/名称/合同名称/金额 + 4阶段×4子类+小计 + 审计调整5列 + 审定5列 + 2判定列 + 备注）
    - 实现 `rows` reactive（从 F2-55-contract-cost-rows remark JSON加载）
    - 实现 `totalRow` computed（SUM全部行各金额列）
    - 实现六区段Tab配置导出（segmentConfigs）
    - 实现行公式链：
      - 各阶段小计 = 设备材料 + 建安分包 + 人工 + 其他
      - 期末各列 = 期初 + 增加 - 减少
      - 审定各列 = 期末 + 审计调整
    - 实现 `addRow(projectName)` + `removeRow(rowId)`
    - 实现 `updateCell` → 公式重算 → debounce保存
    - 实现序列化/反序列化
    - 定义 `ContractCostCheckRow` 类型（F2-56 23列）
    - 实现 F2-56 抽样参数区 + 凭证核对表逻辑
    - 实现 `checkCoverageRatio` computed
    - _Requirements: 3.1~3.12, 4.1~4.9_

  - [ ] 4.2 创建 `composables/useF2Impairment.ts`（F2-57）
    - 定义 `ImpairmentRow` 类型（14列）
    - 实现 `rows` reactive + `totalRow` computed
    - 实现公式链：
      - 完工进度 = 已确认收入/预计总收入
      - 待发生成本 = 预计总成本 - 已发生成本
      - 可收回金额 = (已确认收入/预计总收入) × 预计总成本
      - 减值金额 = max(0, 账面价值 - 可收回金额)
      - 差异 = 减值金额 - 管理层计提
    - 实现 `addRow`/`removeRow`/`updateCell`
    - 实现序列化/反序列化
    - _Requirements: 5.1~5.10_

  - [ ] 4.3 创建 `composables/useF2LossContract.ts`（F2-58）
    - 定义 `LossContractRow` 类型（15列）
    - 实现 `rows` reactive + `totalRow` computed
    - 实现公式链：
      - 是否亏损 = 预计总成本 > 预计总收入
      - 亏损金额 = max(0, 总成本 - 总收入)
      - 应确认预计损失 = 亏损金额 × (1 - 完工进度)
      - 本期应计提 = 应确认预计损失 - 已确认预计损失
      - 差异 = 本期应计提 - 管理层计提
      - 是否需调整 = 差异≠0
    - 实现与F2-57共享项目数据联动（项目编码/名称/总收入/总成本/完工进度）
    - 实现 `addRow`/`removeRow`/`updateCell`
    - 实现序列化/反序列化
    - _Requirements: 6.1~6.11_

- [ ] 5. 实现IPO组composable
  - [ ] 5.1 创建 `composables/useF2IpoPurchaseAnalysis.ts`（F2-61/62/63/64）
    - F2-61原材料采购价格分析：逐月数据reactive + 年度均价/变动率computed + 异常标记
    - F2-62原材料单价分析：多年趋势reactive + 偏离度computed + 异常高亮
    - F2-63产能能耗分析：产能利用率/单位能耗computed + 异常标记
    - F2-64单耗分析：按产品分组数据结构 + 差异率/投入产出比/单耗变动率/金额影响computed
    - 实现各表 `rows` reactive + `addRow`/`removeRow`/`updateCell`
    - 实现 F2-64 groupByProduct computed + 折叠状态管理
    - 实现序列化/反序列化
    - _Requirements: 7.1~7.10, 8.1~8.6, 9.1~9.8, 10.1~10.11_

  - [ ] 5.2 创建 `composables/useF2SupplierAnalysis.ts`（F2-65~F2-72）
    - F2-65/66关联方定价核查：价差率computed + 公允性判定
    - F2-67未披露关联方：核查数据reactive + 风险等级高亮
    - F2-68供应商结构：集中度/排名/变动率/新增退出computed + 前5大/前10大汇总
    - F2-69供应商核查清单：完成度computed + 进度汇总
    - F2-71访谈汇总：访谈统计computed
    - 实现各表 `rows` reactive + `addRow`/`removeRow`/`updateCell`
    - 实现序列化/反序列化
    - _Requirements: 11.1~11.7, 12.1~12.8, 13.1~13.9, 14.1~14.6, 16.1~16.7_

  - [ ] 5.3 创建 `composables/useF2MasterDetail.ts`（F2-70/F2-72通用）
    - 定义 `MasterDetailConfig` 类型（entityLabel/listWidth/searchable/groupBy/detailSections）
    - 实现 `entities` reactive（供应商/访谈实体列表）
    - 实现 `currentEntity` ref + `selectEntity(id)` 切换
    - 实现 `filteredEntities` computed（搜索过滤）
    - 实现 F2-72 groupBySupplier computed（按供应商分组）
    - 实现 `addEntity(name)` + `removeEntity(id)` + `updateField`
    - 实现 F2-72 QA pair 动态增删
    - 实现序列化/反序列化
    - _Requirements: 15.1~15.8, 17.1~17.7_

- [ ] 6. Checkpoint - 公式引擎与composable验证
  - Ensure all PBT tests pass, ask the user if questions arise.

- [ ] 7. 实现 Vue子组件 - contract/目录
  - [ ] 7.1 创建 `f2-special/contract/F2TabContractProcedure.vue`（F2-55A程序表）
    - 复用 GtAProgramConsole 组件 + selfLoad逻辑
    - _Requirements: 1.1_

  - [ ] 7.2 创建 `f2-special/contract/F2TabContractCostDetail.vue`（F2-55 合同履约成本明细 37列→6区段Tab）
    - 调用 useF2ContractCost.ts
    - 渲染6区段Tab切换：基础信息(4列)/期初(5列)/本期增加(5列)/本期减少(5列)/期末(5列)/审计调整+审定(13列)
    - 区段间行同步（切换保持当前行选中）
    - 动态行增删（ElMessageBox.prompt输入项目名称后创建）
    - 合计行 + 公式自动计算
    - "是否预期能收回"=否→橙色高亮行
    - 导入导出按钮
    - UI铁律：13px/公式列虚线tooltip/min-width/编制提示details折叠
    - _Requirements: 3.1~3.12_

  - [ ] 7.3 创建 `f2-special/contract/F2TabContractCostCheck.vue`（F2-56 检查表 23列固定+滚动）
    - 调用 useF2ContractCost.ts
    - 上部抽样参数设定区（总体金额/重要性/可容忍错报/预计错报/样本量/方法/范围）
    - 下部凭证核对表：固定列(6)+滚动列(17)
    - 动态行增删 + 合计行 + 检查比例
    - 异常行红色高亮
    - 行级OCR上传（📎列）
    - 底部审计说明+结论textarea + AI
    - 导入导出
    - _Requirements: 4.1~4.9_

  - [ ] 7.4 创建 `f2-special/contract/F2TabImpairment.vue` + `F2TabLossContract.vue`
    - F2-57减值准备测算：调用useF2Impairment.ts，14列el-table，差异≠0红色高亮，动态行增删(ElMessageBox.prompt)，合计行+审计说明textarea+AI
    - F2-58亏损合同测算：调用useF2LossContract.ts，15列el-table，亏损行红色高亮+差异橙色高亮，动态行增删，合计行+审计说明textarea+AI，与F2-57共享项目数据联动
    - UI铁律：13px/公式列虚线tooltip/min-width
    - _Requirements: 5.1~5.10, 6.1~6.11_

- [ ] 8. 实现 Vue子组件 - ipo/目录（采购+产能+单耗）
  - [ ] 8.1 创建 `f2-special/ipo/F2TabIpoProcedure.vue`（F2-61A程序表）
    - 复用 GtAProgramConsole 组件 + selfLoad逻辑
    - _Requirements: 1.1_

  - [ ] 8.2 创建 `f2-special/ipo/F2TabPurchasePrice.vue`（F2-61 采购价格 118行虚拟滚动）
    - 调用 useF2IpoPurchaseAnalysis.ts
    - 4区段Tab：材料基础(3列)/上半年(6列按月金额数量单价)/下半年(6列)/年度汇总(2列)
    - 虚拟滚动(118行) + 按材料搜索
    - 单价异常(±30%年度均价)橙色高亮
    - 动态行增删 + 导入导出
    - 底部审计说明textarea + AI
    - _Requirements: 7.1~7.10_

  - [ ] 8.3 创建 `f2-special/ipo/F2TabUnitPrice.vue`（F2-62 单价趋势）
    - 调用 useF2IpoPurchaseAnalysis.ts
    - 18列表格 + 偏离度>20%红色高亮
    - 动态行增删 + 导入导出
    - 底部分析结论textarea + AI
    - _Requirements: 8.1~8.6_

  - [ ] 8.4 创建 `f2-special/ipo/F2TabCapacityEnergy.vue`（F2-63 产能能耗）
    - 调用 useF2IpoPurchaseAnalysis.ts
    - 16列表格
    - 产能利用率>100%红色高亮 + 单位能耗变动>20%橙色高亮
    - 动态行增删 + 导入导出
    - 底部分析结论textarea + AI
    - _Requirements: 9.1~9.8_

  - [ ] 8.5 创建 `f2-special/ipo/F2TabUnitConsumption.vue`（F2-64 单耗分析 232行虚拟滚动+产品折叠）
    - 调用 useF2IpoPurchaseAnalysis.ts
    - 18列表格 + 虚拟滚动(232行) + 按产品分组折叠（默认折叠）
    - 差异率>10%橙色高亮 + 投入产出比异常红色高亮
    - 动态行增删 + 导入导出
    - 底部分析结论textarea + AI
    - _Requirements: 10.1~10.11_

- [ ] 9. Checkpoint - 合同组+IPO采购分析验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. 实现 Vue子组件 - ipo/目录（关联方+供应商）
  - [ ] 10.1 创建 `f2-special/ipo/F2TabRelatedPartyInquiry.vue`（F2-65 询价函）
    - 调用 useF2SupplierAnalysis.ts
    - 8列表格 + 价差率>10%红色高亮
    - 结论下拉（公允/基本公允/不公允/待核实）
    - 动态行增删 + 底部结论textarea + AI
    - _Requirements: 11.1~11.7_

  - [ ] 10.2 创建 `f2-special/ipo/F2TabRelatedPartyMarket.vue`（F2-66 市场价）
    - 调用 useF2SupplierAnalysis.ts
    - 7列表格 + 价差率>10%红色高亮
    - 结论下拉 + 动态行增删 + 底部结论textarea + AI
    - _Requirements: 11.1~11.7_

  - [ ] 10.3 创建 `f2-special/ipo/F2TabUndisclosedRelated.vue`（F2-67 未披露关联方 20列）
    - 调用 useF2SupplierAnalysis.ts
    - 20列表格 + 关联类型/核查来源/风险等级下拉
    - 风险"高"红色高亮 + 未披露确认关联橙色高亮
    - 动态行增删 + 导入导出 + 底部结论textarea + AI
    - _Requirements: 12.1~12.8_

  - [ ] 10.4 创建 `f2-special/ipo/F2TabSupplierStructure.vue`（F2-68 供应商结构 25列固定+滚动）
    - 调用 useF2SupplierAnalysis.ts
    - 固定列(5)+滚动列(20)模式
    - 占比>30%橙色高亮 + 新增前5名红色高亮
    - 排名自动计算 + 新增/退出自动标记
    - 底部前5大/前10大集中度汇总 + 分析结论textarea + AI
    - 动态行增删 + 导入导出
    - _Requirements: 13.1~13.9_

  - [ ] 10.5 创建 `f2-special/ipo/F2TabSupplierChecklist.vue`（F2-69 核查清单 19列）
    - 调用 useF2SupplierAnalysis.ts
    - 19列表格 + 核查项下拉(已完成/进行中/未开始/不适用)
    - 完成度自动计算 + 逾期未完橙色高亮
    - 底部进度汇总（已完成/进行中/未开始数量）
    - 动态行增删
    - _Requirements: 14.1~14.6_

  - [ ] 10.6 创建 `f2-special/ipo/F2TabSupplierInfoCheck.vue`（F2-70 供应商核查 Master-Detail）
    - 调用 useF2MasterDetail.ts
    - 左侧供应商列表面板(260px) + 搜索 + 当前选中高亮
    - 右侧3个el-card区域：基础工商信息(6项)/经营情况(4项)/审计核查(4项)
    - 新增供应商(ElMessageBox.prompt) + 删除(确认弹窗)
    - 底部核查结论textarea + AI
    - 导入导出（批量）
    - _Requirements: 15.1~15.8_

  - [ ] 10.7 创建 `f2-special/ipo/F2TabInterviewSummary.vue`（F2-71 访谈汇总）
    - 调用 useF2SupplierAnalysis.ts
    - 9列表格 + 访谈方式/结论下拉
    - 异常/存疑橙色高亮
    - GtIndexChip点击供应商跳转F2-72
    - 底部汇总统计 + 动态行增删
    - _Requirements: 16.1~16.7_

  - [ ] 10.8 创建 `f2-special/ipo/F2TabInterviewDetail.vue`（F2-72 访谈记录 Master-Detail）
    - 调用 useF2MasterDetail.ts
    - 左侧按供应商分组列表 + 搜索+折叠
    - 右侧访谈详情：基本信息(供应商/日期/受访人/主题) + QA pair动态增删(问题textarea+回答textarea) + 审计关注点+结论textarea
    - 新增访谈(选供应商→输入日期) + AI
    - 导入导出
    - _Requirements: 17.1~17.7_

- [ ] 11. 实现导入导出 composable + 后端端点
  - [ ] 11.1 创建 `composables/useF2SpecialImportExport.ts`
    - el-dropdown"导入导出▾"（导出模板/导出数据/导入数据）
    - axios调用后端三端点（export-template/export-data/import-data）
    - 支持sheet参数（F2-55~F2-72全部动态行表格）
    - 导入预览+确认弹窗
    - 进度条显示
    - _Requirements: 19.1~19.6_

  - [ ] 11.2 创建 `backend/app/routers/wp_render_strategies/_f2_special_import_export.py`
    - 实现 `export_f2_special_template` 端点（POST /api/workpapers/{wp_id}/f2-special/export-template?sheet={code}）
    - 实现 `import_f2_special_data` 端点（POST /api/workpapers/{wp_id}/f2-special/import-data?sheet={code}，multipart）
    - 实现 `export_f2_special_data` 端点（POST /api/workpapers/{wp_id}/f2-special/export-data?sheet={code}）
    - openpyxl生成/解析，数据校验（列头+类型+公式验证）
    - StreamingResponse中文文件名RFC5987编码
    - 导出模板含填写说明sheet
    - _Requirements: 19.1~19.6_

- [ ] 12. 实现后端Render策略 + AI生成
  - [ ] 12.1 创建 `backend/app/routers/wp_render_strategies/_f2_special.py`
    - 实现 `render_f2_special` 函数
    - 注册 RENDERER_DISPATCH['f2-inventory-special'] = render_f2_special
    - 返回 componentType='f2-inventory-special' + sheets配置
    - 实现IPO可见性过滤（检查project.business_category，非IPO类别过滤F2-61~F2-72）
    - 支持 force_component_type 参数
    - _Requirements: 1.5, 1.8, 2.1, 2.3_

  - [ ] 12.2 创建 `backend/app/routers/wp_render_strategies/_f2_special_ai.py`
    - 实现8个AI section端点：contract-cost-note/impairment-analysis/loss-analysis/price-analysis/capacity-analysis/consumption-analysis/related-party-conclusion/supplier-analysis
    - POST /api/workpapers/F2-special/ai/{section}
    - 集成AI服务+超时30秒
    - _Requirements: 20.1~20.8_

- [ ] 13. 实现双模式切换 + 性能优化 + UI打磨
  - [ ] 13.1 创建 `composables/useF2SpecialDualMode.ts`
    - 实现模式状态管理（reactive mode: 'html' | 'onlyoffice'）
    - 实现切换逻辑（HTML→OO/OO→HTML）
    - 实现OO sheet名匹配+健康检查+localStorage持久化+降级
    - _Requirements: 21.1~21.7_

  - [ ] 13.2 性能优化验证
    - F2-64单耗分析(232行)虚拟滚动+产品分组折叠验证
    - F2-61采购价格(118行)虚拟滚动验证
    - F2-55(37列)6区段Tab切换流畅性验证
    - F2-68(25列)固定列+滚动列渲染验证
    - defineAsyncComponent lazy验证（首屏仅加载当前sheet组件）
    - 公式缓存命中率验证
    - _Requirements: 22.5~22.8_

  - [ ] 13.3 UI规范验证
    - 13px字体全局验证
    - AI+复核按钮右对齐验证
    - 公式列虚线下划线+tooltip验证
    - min-width自适应验证
    - 审计说明el-card包裹验证
    - 编制提示details折叠验证
    - _Requirements: 22.1~22.4_

- [ ] 14. 集成测试与最终验收
  - [ ] 14.1 编写集成测试 + 最终验收
    - 测试sheetName分发正确性（18个sheet名→对应子组件）
    - 测试IPO可见性（business_category控制F2-61~F2-72显示/隐藏）
    - 测试合同履约成本公式链（F2-55期末=期初+增加-减少→F2-57减值→F2-58亏损判定）
    - 测试F2-55六区段Tab切换+行同步
    - 测试F2-57/F2-58共享项目数据联动
    - 测试F2-64虚拟滚动+产品分组折叠
    - 测试F2-68固定列+滚动列
    - 测试F2-70/F2-72 Master-Detail CRUD
    - 测试导入导出round-trip（全16张动态行表格）
    - 测试双模式切换
    - 所有PBT测试通过（P1~P12）
    - 18个sheet逐一验证渲染正确
    - _Requirements: 全部_


- [ ] 15. 抽凭引擎集成
  - [ ] 15.1 F2-56合同履约成本检查表集成GtVoucherSamplingEngine
    - 在F2TabContractCostCheck.vue抽样参数设定区添加"使用抽凭引擎"按钮
    - import GtVoucherSamplingEngine组件（dialog模式）
    - 点击按钮打开dialog，预填总体金额（从抽样参数区取）+ 科目代码1405合同履约成本
    - 用户确认后将选中样本映射到F2-56凭证核对表动态行（项目名称/凭证日期/编号/金额）
    - 自动更新抽样参数区（样本量/抽样方法）
    - 已填入行添加tooltip来源标记"来自抽凭引擎 {algorithm}"
    - _Requirements: 23_

- [ ] 16. 版本链集成
  - [ ] 16.1 集成useVersionTrail到GtF2InventorySpecial主入口
    - import useVersionTrail composable并调用useVersionTrail(wpId)
    - 在save成功后调用versionTrail.autoSnapshot()
    - 工具栏右侧添加"版本历史"按钮（el-button icon="Clock"）
    - 点击打开GtWpVersionTrail drawer
    - 支持手动创建命名快照
    - provide('openReviewDialog', openReviewDialog) 供子组件inject
    - _Requirements: 24_

- [ ] 17. 附注模块联动
  - [ ] 17.1 F2-55/F2-57 publish substantive:adjudicated事件
    - 在useF2ContractCost.ts中watch审定金额computed变更
    - 变更时publish EventBus `substantive:adjudicated`（payload: {wpCode:'F2-special', accountCode:'1405', auditedAmount}）
    - 在useF2Impairment.ts中watch减值金额确定
    - publish payload增加impairmentAmount字段
    - 事件去重（2秒debounce，同payload不重复发布）
    - _Requirements: 25_

  - [ ] 17.2 F2-55/F2-57 publish disclosure:note-text-updated事件
    - watch审计结论textarea变更
    - debounce 2秒后publish `disclosure:note-text-updated`（payload: {wpCode:'F2-special', section:'contract-cost'/immpairment', text}）
    - _Requirements: 25_

  - [ ] 17.3 subscribe substantive:adjudicated事件
    - GtF2InventorySpecial subscribe `substantive:adjudicated`来自其他模块
    - 用于刷新F2-55/F2-57中引用的外部审定数据
    - _Requirements: 25_

- [ ] 18. 行级OCR集成（F2-56检查表）
  - [ ] 18.1 F2-56合同履约成本检查表📎OCR列
    - 在F2TabContractCostCheck.vue每行添加📎列（el-upload按钮）
    - 上传POST /api/workpapers/{wp_id}/f2-special/contract-ocr
    - 后端复用D4 contract-ocr端点模式，识别合同/发票
    - 返回extracted_fields（合同编号/金额/供应商/发票号/日期）
    - ElMessageBox.confirm确认弹窗，置信度<80%橙色高亮
    - 确认后merge到当前行
    - 上传成功📎列显示Document图标+hover预览
    - _Requirements: 26_
