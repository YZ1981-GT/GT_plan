# Implementation Plan: G6其他债权投资(SPPI组)专属HTML精美组件

## Overview

基于D~N专属组件标准开发模式，实现G6-SPPI组6个sheet的完整HTML组件。采用sheetName v-if分发架构，composable分层设计，公式引擎6纯函数PBT验证，集成版本链+复核对话。

## Tasks

- [ ] 1. 公式引擎与核心composable
  - [ ] 1.1 实现 useG6SppiFormulaEngine.ts 公式引擎（6纯函数+parseNum）
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiFormulaEngine.ts`
    - 实现 parseNum / calcEffectiveInterest / calcCashInflow / calcEndingAmortized / calcFairValueDiff / calcInventoryRollForward / calcInventoryVariance
    - 所有函数为纯函数，2dp四舍五入，parseNum兜底null/undefined/NaN/''→0
    - _Requirements: 7.1, 3.2, 3.3, 3.4, 6.3_

  - [ ]* 1.2 PBT验证公式引擎 Property 1: 实际利息收入公式
    - **Property 1: 实际利息收入 = amortizedCost × effectiveRate × days / 365（2dp）**
    - **Validates: Requirements 3.2**
    - fast-check生成器: fc.float({min:0,max:1e9,noNaN:true}), fc.float({min:0,max:0.3,noNaN:true}), fc.integer({min:1,max:365})

  - [ ]* 1.3 PBT验证公式引擎 Property 2: 现金流入公式
    - **Property 2: 现金流入 = faceValue × couponRate × days / 365（2dp）**
    - **Validates: Requirements 3.3**

  - [ ]* 1.4 PBT验证公式引擎 Property 3: 期末摊余成本恒等式
    - **Property 3: 期末摊余 = opening + interest - cashInflow（2dp）**
    - **Validates: Requirements 3.4**

  - [ ]* 1.5 PBT验证公式引擎 Property 4: 盘点倒轧加法恒等
    - **Property 4: 基准日数量 = 盘点日数量 + 增减**
    - **Validates: Requirements 6.3**

  - [ ]* 1.6 PBT验证公式引擎 Property 5: 公允价值差异公式
    - **Property 5: 差异 = audited - unadjusted（2dp）**
    - **Validates: Requirements 2.2, 7.1**

  - [ ]* 1.7 PBT验证公式引擎 Property 6: parseNum健壮性
    - **Property 6: null/undefined/NaN/''→0，有限数透传**
    - **Validates: Requirements 7.1**

  - [ ] 1.8 实现 useG6SppiFormData.ts 数据加载/保存composable
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiFormData.ts`
    - selfLoad逻辑（bundle内嵌htmlData为null时从render-config加载）
    - save逻辑（POST content JSON）+ 重试3次指数退避 + localStorage暂存
    - _Requirements: 1.4, 7.2_

  - [ ] 1.9 实现 useG6SppiDualMode.ts 双模式切换composable
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiDualMode.ts`
    - HTML↔OnlyOffice模式切换，OnlyOffice fallback逻辑
    - _Requirements: 1.4, 7.6_

- [ ] 2. Checkpoint - 公式引擎验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. 主入口与注册四件套
  - [ ] 3.1 实现主入口 GtG6OtherBondInvestmentSppi.vue（sheetName v-if分发）
    - 创建 `frontend/src/components/workpaper/GtG6OtherBondInvestmentSppi.vue`
    - 接收 htmlData/sheetName/wpId/projectId/readonly props
    - 正则提取sheetCode `/G6-(5|6|7|8|9|10)/`，v-if分发6个defineAsyncComponent子组件
    - 集成 useVersionTrail（autoSnapshot）+ provide openReviewDialog
    - 未匹配sheetName → OnlyOffice fallback
    - _Requirements: 1.1, 1.2, 1.4, 7.2_

  - [ ] 3.2 注册四件套
    - htmlRendererRegistry 注册 `g6-other-bond-investment-sppi`
    - wp_code_overrides.json 添加6条映射（G6-5~G6-10）
    - 后端 VALID_COMPONENT_TYPES 添加 `g6-other-bond-investment-sppi`
    - 后端 RENDERER_DISPATCH 注册 render_g6_other_bond_investment_sppi
    - _Requirements: 1.1, 1.3_

  - [ ] 3.3 实现后端 render 策略 _g6_other_bond_investment_sppi.py
    - 创建 `backend/app/routers/wp_render_strategies/_g6_other_bond_investment_sppi.py`
    - render_g6_other_bond_investment_sppi 函数返回 componentType + sheets配置
    - _Requirements: 1.1, 1.3_

- [ ] 4. G6-5 公允价值测试表（18列→2区段Tab）
  - [ ] 4.1 实现 useG6SppiFairValue.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiFairValue.ts`
    - FairValueTestData/FairValueItem数据模型，activeTab/selectedRowIndex状态
    - calcFairValueDiff调用，差异红色高亮逻辑（|审定-未审|>0）
    - Level3必填校验（层次=L3时Tab2字段必填），动态行增删
    - _Requirements: 2.1, 2.2, 7.1_

  - [ ] 4.2 实现 G6TabFairValueTest.vue 组件
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-sppi/fair-value/G6TabFairValueTest.vue`
    - 2区段Tab切换（基础+审定 / 估值详情），行同步selectedRowIndex
    - Tab1: 10列表格（投资项目/面值/未审3列/审定3列/差异/公允价值层次下拉）
    - Tab2: 8列表格（投资项目/估值方法/一致性/来源机构/输入值来源/估值技术/不可观察输入值/估值文件索引）
    - Level3红框+toast提示，差异红色背景，动态行(ElMessageBox.prompt)
    - 审计结论textarea + AI辅助按钮 + 编制提示details + 复核按钮
    - _Requirements: 2.1, 2.2_

  - [ ]* 4.3 Write unit tests for G6-5 公允价值
    - Level3必填校验逻辑、差异红色高亮条件、Tab行同步
    - _Requirements: 2.2_

- [ ] 5. G6-6 利息测算表（实际利率法分组）
  - [ ] 5.1 实现 useG6SppiInterest.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiInterest.ts`
    - InterestCalculationData/InterestGroup/InterestPeriod数据模型
    - 分组结构管理（新增项目ElMessageBox.prompt/新增期间/删除）
    - 公式调用: calcEffectiveInterest/calcCashInflow/calcEndingAmortized
    - 合计计算、交叉验证差异（G6-1审定数）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 7.1_

  - [ ] 5.2 实现 G6TabInterestCalculation.vue 组件
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-sppi/interest/G6TabInterestCalculation.vue`
    - 方法论上下文（琥珀色: 实际利率法公式说明）
    - 分组卡片：每项目header(名称/面值/票面利率/实际利率) + 多期表格
    - 公式列虚线下划线+cursor:help+tooltip来源
    - 底部交叉验证区（利息合计 vs G6-1审定, 差异红/绿色）
    - 动态行操作 + 审计结论textarea + AI辅助 + 导入导出dropdown + 编制提示
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 5.3 Write unit tests for G6-6 利息测算
    - 分组新增/删除逻辑、期间链式计算（上期末=下期初）、交叉验证
    - _Requirements: 3.2, 3.3, 3.4, 3.5_

- [ ] 6. Checkpoint - 公允价值+利息测算验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. G6-7 业务模式分析（三section问卷）
  - [ ] 7.1 实现 useG6SppiBusinessModel.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiBusinessModel.ts`
    - BusinessModelData/BusinessModelSection/BusinessModelItem数据模型
    - 三section数据管理，综合判断逻辑（持有收取/兼有/其他）
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 7.2 实现 G6TabBusinessModel.vue 组件
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-sppi/classification/G6TabBusinessModel.vue`
    - 顶部方法论上下文（琥珀色: CAS22业务模式三类定义）
    - 三section结构：(一)业务模式确定 / (二)出售情况分析 / (三)综合判断
    - 每section: 8列表格(序号/检查项目/审计要求/管理层说明textarea/是否满足下拉/审计结论textarea/风险评级/索引)
    - 综合判断section: 最终分类下拉(持有收取/兼有/其他) + 综合分析textarea autosize
    - 每section标题行右侧AI辅助按钮 + 复核按钮 + 编制提示details
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]* 7.3 Write unit tests for G6-7 业务模式
    - 三section数据结构、综合判断推导逻辑
    - _Requirements: 4.2_

- [ ] 8. G6-8 SPPI测试（80行六section+虚拟滚动）
  - [ ] 8.1 实现 useG6SppiTest.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiTest.ts`
    - SppiTestData/SppiSection/SppiItem数据模型
    - 六section管理 + SPPI_METHODOLOGY方法论映射
    - 综合结论推导：任一section="否"→overallConclusion='fail'
    - hasFailedSection计算属性
    - _Requirements: 5.1, 5.2, 5.4, 5.5_

  - [ ] 8.2 实现 G6TabSppiTest.vue 组件
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-sppi/classification/G6TabSppiTest.vue`
    - 顶部方法论上下文（琥珀色: SPPI定义）
    - 六section: (一)本金定义/(二)利息定义/(三)修改时间价值/(四)提前还款条款/(五)合同关联工具/(六)综合判断
    - el-table-v2虚拟滚动80行，列: 序号/检查区域/检查项目/CAS要求/合同条款摘要textarea/是否满足SPPI(是/否/不适用)/判断依据textarea/风险等级/索引/备注
    - 任一section FAIL → 红色高亮section标题 + 底部"不满足SPPI，需重分类"提示
    - 每section标题行AI辅助按钮 + 复核按钮 + 综合结论区 + 编制提示
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 8.3 Write unit tests for G6-8 SPPI测试
    - SPPI决策逻辑（任一FAIL→红色）、hasFailedSection计算、section结论推导
    - _Requirements: 5.4, 5.5_

- [ ] 9. Checkpoint - 分类测试验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. G6-9/G6-10 盘点表
  - [ ] 10.1 实现 useG6SppiInventory.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiInventory.ts`
    - SecuritiesInventoryData/InventoryItem数据模型
    - 差异公式(盘点-账面)、动态行管理
    - _Requirements: 6.1, 6.4_

  - [ ] 10.2 实现 G6TabSecuritiesInventory.vue 组件
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-sppi/inspection/G6TabSecuritiesInventory.vue`
    - 29行×7列表格: 序号/证券名称/证券代码/面值/数量(盘点)/数量(账面)/差异(公式)
    - 动态行增删(ElMessageBox.prompt) + 审计结论 + 编制提示 + 复核按钮
    - _Requirements: 6.1, 6.4_

  - [ ] 10.3 实现 useG6SppiReconciliation.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiReconciliation.ts`
    - ReconciliationData/ReconciliationItem/ChangeDetailItem数据模型
    - activeTab/selectedRowIndex状态，calcInventoryRollForward/calcInventoryVariance调用
    - 差异必填校验(|差异|>0时差异原因必填)，动态行管理
    - _Requirements: 6.2, 6.3, 6.4_

  - [ ] 10.4 实现 G6TabInventoryRollForward.vue 组件
    - 创建 `frontend/src/components/workpaper/g6-other-bond-investment-sppi/inspection/G6TabInventoryRollForward.vue`
    - 2区段Tab: Tab1倒轧计算(10列) / Tab2增减明细(8列)，行同步selectedRowIndex
    - Tab1: 证券名称/盘点日数量/增减/基准日数量(公式)/账面数量/差异(公式,红色)/差异原因/差异结论/索引/备注
    - Tab2: 证券名称/日期/交易类型(下拉buy/sell/mature/transfer)/数量/金额/凭证号/经办人/备注
    - 差异红色高亮+差异原因必填，动态行 + 导入导出 + AI辅助 + 审计结论 + 编制提示
    - _Requirements: 6.2, 6.3, 6.4_

  - [ ]* 10.5 Write unit tests for G6-9/G6-10 盘点
    - 差异计算、倒轧公式、差异必填校验逻辑
    - _Requirements: 6.3, 6.4_

- [ ] 11. 导入导出与AI辅助
  - [ ] 11.1 实现 useG6SppiImportExport.ts composable
    - 创建 `frontend/src/components/workpaper/composables/useG6SppiImportExport.ts`
    - 4张表(G6-5/G6-6/G6-9/G6-10)导入导出逻辑
    - el-dropdown"导入导出▾"(导出模板/导出数据/导入数据)
    - 宽表分sheet导出（G6-5按2区段/G6-10按2区段）
    - 使用http(axios)调用后端端点
    - _Requirements: 7.3_

  - [ ] 11.2 实现后端导入导出 _g6_other_bond_investment_sppi_import_export.py
    - 创建 `backend/app/routers/wp_render_strategies/_g6_other_bond_investment_sppi_import_export.py`
    - 12端点: 4表×3(export-template/export-data/import-data)
    - multipart/form-data上传，格式校验422+具体列错误
    - StreamingResponse中文文件名RFC5987编码
    - _Requirements: 7.3_

  - [ ] 11.3 实现后端AI辅助 _g6_other_bond_investment_sppi_ai.py
    - 创建 `backend/app/routers/wp_render_strategies/_g6_other_bond_investment_sppi_ai.py`
    - 4端点: fair-value-conclusion / interest-conclusion / business-model-conclusion / sppi-conclusion
    - POST /api/workpapers/{wp_id}/g6-sppi/ai/{section}
    - _Requirements: 7.4_

  - [ ]* 11.4 Write integration tests for 导入导出+AI端点
    - 4表导出模板/导出数据/导入数据端点测试 + AI 4 section端点测试
    - _Requirements: 7.3, 7.4_

- [ ] 12. Final checkpoint - 全组件集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (6 PBT in useG6SppiFormulaEngine)
- Unit tests validate specific examples and edge cases
- 公式引擎6纯函数为PBT核心验证对象，composable/组件逻辑用单元测试
- 宽表(G6-5/G6-10)采用2区段Tab拆分，行同步通过selectedRowIndex
- G6-8 SPPI测试80行启用el-table-v2虚拟滚动
- 导入导出仅4张表(G6-5/G6-6/G6-9/G6-10)，G6-7/G6-8为问卷式无需导入导出
- 集成仅版本链+复核对话，无抽凭/截止/附注EventBus/OCR

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 3, "tasks": ["4.1", "5.1", "7.1", "8.1", "10.1", "10.3"] },
    { "id": 4, "tasks": ["4.2", "5.2", "7.2", "8.2", "10.2", "10.4"] },
    { "id": 5, "tasks": ["4.3", "5.3", "7.3", "8.3", "10.5"] },
    { "id": 6, "tasks": ["11.1", "11.2", "11.3"] },
    { "id": 7, "tasks": ["11.4"] }
  ]
}
```
