# Implementation Plan: G4 债权投资底稿(SPPI组)专属HTML精美组件

## Overview

G4债权投资(SPPI组)专属组件 `g4-bond-investment-sppi`，覆盖4个sheet（G4-5业务模式分析/G4-6合同现金流量特征分析/G4-7有价证券盘点表/G4-8盘点倒轧表）。采用sheetName v-if dispatch模式 + defineAsyncComponent懒加载 + 公式引擎composable（2个决策函数+9个纯函数） + 13个PBT验证 + 六大集成联动（版本链✅+复核✅）。按D~N底稿开发标准8步组织为8波次。

## Tasks

- [x] 1. 注册四件套
  - [x] 1.1 后端注册：VALID_COMPONENT_TYPES添加'g4-bond-investment-sppi' + RENDERER_DISPATCH注册render_g4_bond_investment_sppi策略函数
    - 创建 `backend/app/routers/wp_render_strategies/_g4_bond_investment_sppi.py`
    - 在 `VALID_COMPONENT_TYPES` 列表中添加 `'g4-bond-investment-sppi'`
    - 在 `RENDERER_DISPATCH` 中注册 `'g4-bond-investment-sppi': render_g4_bond_investment_sppi`
    - render函数返回4个sheet的配置（componentType/sheetName/columns/rows）
    - _Requirements: 1.1, 1.5_

  - [x] 1.2 前端注册：htmlRendererRegistry添加'g4-bond-investment-sppi'映射
    - 在 `htmlRendererRegistry` 中添加 `'g4-bond-investment-sppi': () => import('./workpaper/GtG4BondInvestmentSppi.vue')`
    - _Requirements: 1.1, 1.3_

  - [x] 1.3 wp_code_overrides.json添加4条映射（G4-5/G4-6/G4-7/G4-8→g4-bond-investment-sppi）
    - G4-5-业务模式分析 → g4-bond-investment-sppi
    - G4-6-合同现金流量特征分析 → g4-bond-investment-sppi
    - G4-7-有价证券盘点表 → g4-bond-investment-sppi
    - G4-8-盘点倒轧表 → g4-bond-investment-sppi
    - _Requirements: 1.4_

  - [x] 1.4 创建数据加载composable useG4SppiFormData.ts + 双模式composable useG4SppiDualMode.ts
    - 创建 `audit-platform/frontend/src/composables/useG4SppiFormData.ts`（数据加载/保存/selfLoad）
    - 创建 `audit-platform/frontend/src/composables/useG4SppiDualMode.ts`（HTML↔OO切换+localStorage）
    - selfLoad: htmlData为null时调用render-config?force_component_type=g4-bond-investment-sppi
    - _Requirements: 1.6, 8.6_

- [x] 2. 公式引擎 useG4SppiFormulaEngine.ts + 13个PBT
  - [x] 2.1 实现useG4SppiFormulaEngine.ts（parseNum + 2个决策函数 + 9个纯函数 + 组合判定函数）
    - 创建 `audit-platform/frontend/src/composables/useG4SppiFormulaEngine.ts`
    - 实现 `parseNum`（null/undefined/NaN/空串→0）
    - 实现 `determineBusinessModel(answers)` → AC/FVOCI/FVTPL/INCOMPLETE
    - 实现 `determineSPPIConclusion(4 booleans)` → PASS/FAIL/FURTHER_ANALYSIS
    - 实现 `calcInventoryTotal(faceValue, quantity)` → 面值×数量(2dp)
    - 实现 `calcReportDateQuantity(countDateQty, change)` → 盘点日+增减
    - 实现 `calcReportDateTotal(reportFaceValue, reportQuantity)` → 报表日面值×数量(2dp)
    - 实现 `calcReconciliationVariance(reportDateTotal, bookTotal)` → 差异(2dp)
    - 实现 `isReconciliationBalanced(reportDateTotal, bookTotal)` → |差异|<0.01
    - 实现 `calcSumColumn(values[])` → 数组求和
    - 实现 `determineFinalClassification(businessModel, sppiResult)` → 最终分类
    - 所有函数无副作用、无Vue响应式依赖、输入通过parseNum清洗
    - _Requirements: 6.1~6.10_

  - [x]* 2.2 PBT: Property 1 — 业务模式决策确定性
    - **Property 1: 业务模式决策确定性**
    - **Validates: Requirements 6.1**
    - ∀ answers ∈ {q1~q5: boolean}: determineBusinessModel(answers) 两次调用结果完全相等
    - 使用 `fc.boolean()` 生成q1~q5，numRuns ≥ 100

  - [x]* 2.3 PBT: Property 2 — 业务模式决策完备性
    - **Property 2: 业务模式决策完备性**
    - **Validates: Requirements 6.1, 2.3**
    - ∀ answers ∈ {q1~q5: boolean}: determineBusinessModel(answers) ∈ {'AC', 'FVOCI', 'FVTPL'}（32种组合无未定义输出）
    - 使用 `fc.boolean()` 生成q1~q5，numRuns ≥ 100

  - [x]* 2.4 PBT: Property 3 — 业务模式决策互斥性
    - **Property 3: 业务模式决策互斥性**
    - **Validates: Requirements 6.1, 2.3**
    - ∀ answers: determineBusinessModel(answers) 恰好属于AC/FVOCI/FVTPL之一（三类互斥）
    - numRuns ≥ 100

  - [x]* 2.5 PBT: Property 4 — SPPI结论推导确定性
    - **Property 4: SPPI结论推导确定性**
    - **Validates: Requirements 6.2, 3.8**
    - ∀ (earlyRedemption, extension, equityConversion, leverage) ∈ boolean⁴: 相同输入产出相同结论
    - 使用 `fc.boolean()` 生成4个布尔，numRuns ≥ 100

  - [x]* 2.6 PBT: Property 5 — SPPI失败条件充分性
    - **Property 5: SPPI失败条件充分性**
    - **Validates: Requirements 6.2, 3.8**
    - ∀ inputs where hasEquityConversion=true OR hasLeverage=true: determineSPPIConclusion === 'FAIL'
    - numRuns ≥ 100

  - [x]* 2.7 PBT: Property 6 — SPPI通过条件必要性
    - **Property 6: SPPI通过条件必要性**
    - **Validates: Requirements 6.2, 3.8**
    - ∀ inputs: determineSPPIConclusion === 'PASS' → 4项均为false
    - numRuns ≥ 100

  - [x]* 2.8 PBT: Property 7 — 盘点总计公式
    - **Property 7: 盘点总计公式**
    - **Validates: Requirements 6.3, 4.4, 5.2**
    - ∀ faceValue ∈ ℝ≥0, quantity ∈ ℤ≥0: calcInventoryTotal === round(faceValue×quantity, 2)
    - 使用 `fc.float({min:0, max:1e8, noNaN:true})` + `fc.integer({min:0, max:1e6})`

  - [x]* 2.9 PBT: Property 8 — 报表日数量加法恒等
    - **Property 8: 报表日数量加法恒等**
    - **Validates: Requirements 6.4, 5.3**
    - ∀ countDateQty ∈ ℤ≥0, change ∈ ℤ: calcReportDateQuantity === countDateQty + change
    - 使用 `fc.integer({min:0, max:1e6})` + `fc.integer({min:-1e4, max:1e4})`

  - [x]* 2.10 PBT: Property 9 — 倒轧差异公式
    - **Property 9: 倒轧差异公式**
    - **Validates: Requirements 6.6, 5.5**
    - ∀ reportTotal, bookTotal ∈ ℝ≥0: calcReconciliationVariance === round(reportTotal-bookTotal, 2)
    - 使用 `fc.float({min:0, max:1e8, noNaN:true})`

  - [x]* 2.11 PBT: Property 10 — 倒轧平衡判定一致性
    - **Property 10: 倒轧平衡判定一致性**
    - **Validates: Requirements 6.7, 5.6**
    - ∀ reportTotal, bookTotal: isReconciliationBalanced ↔ |reportTotal-bookTotal| < 0.01
    - numRuns ≥ 100

  - [x]* 2.12 PBT: Property 11 — 合计行加法交换律
    - **Property 11: 合计行加法交换律**
    - **Validates: Requirements 6.8, 4.5, 5.8**
    - ∀ values ∈ ℝ[]: calcSumColumn(values) === calcSumColumn(shuffle(values))
    - 使用 `fc.array(fc.float({min:-1e8, max:1e8, noNaN:true}))`

  - [x]* 2.13 PBT: Property 12 — parseNum健壮性
    - **Property 12: parseNum健壮性**
    - **Validates: Requirements 6.9**
    - ∀ input ∈ {null, undefined, '', NaN, '  ', 'abc'}: parseNum(input) === 0
    - ∀ n ∈ ℝ (finite): parseNum(n) === n
    - 使用 `fc.oneof(fc.constant(null), fc.constant(undefined), fc.constant(''), fc.constant(NaN), fc.constant('abc'), fc.float())`

  - [x]* 2.14 PBT: Property 13 — SPPI与业务模式组合分类
    - **Property 13: SPPI与业务模式组合分类**
    - **Validates: Requirements 6.1, 6.2 (组合逻辑)**
    - 当sppiResult='FAIL'时: determineFinalClassification必返回'FVTPL'
    - 当businessModel='AC'且sppiResult='PASS'时: 最终分类为'AC'
    - numRuns ≥ 100

- [x] 3. 主入口 GtG4BondInvestmentSppi.vue
  - [x] 3.1 实现主入口GtG4BondInvestmentSppi.vue（sheetName v-if分发 + defineAsyncComponent懒加载 + 版本链 + 复核provide）
    - 创建 `audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentSppi.vue`
    - 接收props: htmlData/sheetName/wpId/projectId/readonly
    - 正则提取sheetName编码: `/G4-([5-8])/` → G4-5/G4-6/G4-7/G4-8
    - v-if分发到4个子组件（defineAsyncComponent懒加载）
    - 未匹配编码 → OnlyOffice fallback（GtOnlyOfficeSheet）
    - 集成useVersionTrail（autoSnapshot on save + "版本历史"按钮）
    - provide openReviewDialog → 子组件inject使用
    - selfLoad逻辑（htmlData为null时调useG4SppiFormData.ts加载）
    - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9, 7.1, 7.2, 9.9_

  - [x] 3.2 创建子组件目录结构骨架（4个子组件占位）
    - 创建 `audit-platform/frontend/src/components/workpaper/g4-bond-investment-sppi/classification/G4TabBusinessModel.vue`（骨架）
    - 创建 `audit-platform/frontend/src/components/workpaper/g4-bond-investment-sppi/classification/G4TabSppiTest.vue`（骨架）
    - 创建 `audit-platform/frontend/src/components/workpaper/g4-bond-investment-sppi/inspection/G4TabSecuritiesInventory.vue`（骨架）
    - 创建 `audit-platform/frontend/src/components/workpaper/g4-bond-investment-sppi/inspection/G4TabInventoryReconciliation.vue`（骨架）
    - _Requirements: 1.9_

- [x] 4. Checkpoint — 注册四件套+公式引擎+主入口骨架
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. G4-5 业务模式分析（问卷式+决策chip）
  - [x] 5.1 实现useG4SppiBusinessModel.ts composable（问卷逻辑+答案→决策→chip映射）
    - 创建 `audit-platform/frontend/src/composables/useG4SppiBusinessModel.ts`
    - 管理QuestionnaireItem[]响应式数据（5道问题）
    - watch答案变化 → 调用determineBusinessModel → 更新conclusion
    - chip映射: AC→绿色/FVOCI→蓝色/FVTPL→橙色/INCOMPLETE→灰色
    - 次级组合逻辑（hasSubPortfolios + SubPortfolio[] + ElMessageBox.prompt新增）
    - _Requirements: 2.1~2.9, 6.1_

  - [x] 5.2 实现G4TabBusinessModel.vue完整UI（方法论上下文+问卷radio+说明textarea+结论chip+次级组合+审计结论）
    - 顶部方法论上下文（琥珀色左边线+浅黄背景）
    - (一)部分：5道问题（是/否radio + 说明textarea autosize）+ 审计评价textarea
    - 底部结论chip区域（动态变色：AC绿/FVOCI蓝/FVTPL橙/INCOMPLETE灰）
    - (二)部分：适用性radio（默认"否"）→ 选"是"展开次级组合编辑区
    - 次级组合：ElMessageBox.prompt输入组合名→重复5道问题→各自独立结论chip
    - 底部审计结论textarea（带AI辅助按钮）+ 编制提示details折叠
    - inject openReviewDialog → section标题栏右侧复核按钮
    - _Requirements: 2.1~2.9, 9.1~9.6, 9.11_

- [x] 6. G4-6 SPPI测试（两部分+方法论上下文+虚拟滚动）
  - [x] 6.1 实现useG4SppiTest.ts composable（两部分逻辑+动态行+SPPI决策自动设结论）
    - 创建 `audit-platform/frontend/src/composables/useG4SppiTest.ts`
    - 管理bondItems[]响应式数据（部分一）
    - 管理financialProducts三步数据（部分二）
    - watch 4布尔标志变化 → 调用determineSPPIConclusion → 自动设结论（用户可覆盖）
    - 动态行增删逻辑（ElMessageBox.prompt输入投资项目名称）
    - 分析项目选择 → METHODOLOGY_MAP动态映射判断逻辑文本
    - _Requirements: 3.1~3.12, 6.2_

  - [x] 6.2 实现G4TabSppiTest.vue完整UI（部分一虚拟滚动表格+方法论上下文列+部分二三步表格）
    - 部分(一): el-table-v2虚拟滚动表格（80行）
    - 列: 投资项目|票面价值|票面利率|提前回售(是/否)|展期(是/否)|权益转换(是/否)|杠杆(是/否)|结论(下拉)|分析项目(下拉)|判断逻辑(方法论上下文)
    - 判断逻辑列: 琥珀色左边线+浅黄背景，根据分析项目动态切换7种方法论文本
    - 分析项目下拉: 简单条款|浮动利率|利率调整|提前偿付|展期选择权|无追索权|合同挂钩工具
    - 部分(一)底部: 审计结论textarea + AI辅助按钮
    - 部分(二)第一步: 保本保收益表格（step1Items）
    - 部分(二)第二步: 浮动收益不现实表格（step2Items）
    - 部分(二)第三步: 穿透底层资产表格（step3Items）
    - 部分(二)底部: 审计结论textarea + AI辅助按钮
    - 编制提示details折叠（底部）
    - 动态行新增按钮 + 导入导出下拉
    - inject openReviewDialog → section标题栏右侧复核按钮
    - _Requirements: 3.1~3.12, 9.1~9.8_

- [x] 7. G4-7 盘点表 + G4-8 倒轧表（3区段Tab）
  - [x] 7.1 实现useG4SppiInventory.ts composable（盘点信息头+明细+公式+合计行）
    - 创建 `audit-platform/frontend/src/composables/useG4SppiInventory.ts`
    - 管理InventoryHeader响应式数据（6字段）
    - 管理InventoryItem[]（seq/securitiesName/faceValue/quantity/total/couponRate/maturityDate）
    - computed: 每行total = calcInventoryTotal(faceValue, quantity)
    - computed: 合计行（面值合计/数量合计/总计合计 via calcSumColumn）
    - 动态行增删（ElMessageBox.prompt输入证券名称）
    - _Requirements: 4.1~4.8, 6.3, 6.8_

  - [x] 7.2 实现G4TabSecuritiesInventory.vue完整UI（信息头form+明细表格+合计行+审计结论）
    - 盘点信息头el-form（盘点单位/日期date-picker/会计主管/出纳/监盘人/盘点人）
    - 明细el-table（序号|证券名称|面值|数量|总计(公式列虚线下划线tooltip)|票面利率|到期日）
    - 合计行（面值合计/数量合计/总计合计）
    - 底部审计说明textarea + 审计结论textarea（各带AI按钮），el-card包裹
    - 编制提示details折叠
    - 动态行新增按钮 + 导入导出下拉
    - inject openReviewDialog → section标题栏右侧复核按钮
    - _Requirements: 4.1~4.8, 9.1~9.5_

  - [x] 7.3 实现useG4SppiReconciliation.ts composable（3区段+行同步+差异高亮逻辑）
    - 创建 `audit-platform/frontend/src/composables/useG4SppiReconciliation.ts`
    - 管理ReconciliationItem[]响应式数据（18个字段）
    - activeTab ref（'countDate'/'changes'/'reportDate'）
    - selectedRowIndex ref（跨Tab行同步）
    - computed: 每行countTotal = calcInventoryTotal(countFaceValue, countQuantity)
    - computed: 每行reportQuantity = calcReportDateQuantity(countQuantity, changeQuantity)
    - computed: 每行reportTotal = calcReportDateTotal(reportFaceValue, reportQuantity)
    - computed: 每行variance = calcReconciliationVariance(reportTotal, bookTotal)
    - computed: 差异高亮标志（|variance|>0 → 红色+备注必填）
    - computed: 合计行（各列calcSumColumn）
    - Tab切换时保持selectedRowIndex（超范围重置为0）
    - 动态行增删（ElMessageBox.prompt输入证券名称）
    - _Requirements: 5.1~5.10, 6.3~6.8_

  - [x] 7.4 实现G4TabInventoryReconciliation.vue完整UI（3区段Tab+el-table+行同步+差异红色高亮+合计行）
    - 3个Tab按钮区（盘点日实存/增减变动/报表日实存+差异）
    - Tab切换仅切换列定义（columns computed），不销毁el-table实例
    - 盘点日实存(6列): 证券名称|数量|面值|总计(公式)|票面利率|到期日
    - 增减变动(2列): 增减数量|增减面值总额
    - 报表日实存+差异(10列): 报表日数量(公式)|报表日面值|报表日总计(公式)|票面利率|到期日|账面结存数量|账面结存面值|账面结存总计|差异(公式,红色高亮)|备注
    - 行选中状态: 点击行→selectedRowIndex更新→跨Tab保持
    - 差异列: |差异|>0时单元格红色高亮 + 备注列必填校验
    - 公式列: 虚线下划线+cursor:help+tooltip显示公式来源
    - 底部合计行 + 审计结论textarea（AI按钮） + 编制提示details折叠
    - 动态行新增按钮 + 导入导出下拉
    - inject openReviewDialog → section标题栏右侧复核按钮
    - _Requirements: 5.1~5.10, 9.1~9.5, 9.10_

- [x] 8. Checkpoint — G4-5~G4-8四个子组件完整实现
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 导入导出 + AI（5 section）
  - [x] 9.1 实现后端导入导出端点 _g4_bond_investment_sppi_import_export.py（3张表×3端点=9端点）
    - 创建 `backend/app/routers/wp_render_strategies/_g4_bond_investment_sppi_import_export.py`
    - POST /api/workpapers/{wp_id}/g4-sppi/export-template?sheet={code}（G4-6/G4-7/G4-8）
    - POST /api/workpapers/{wp_id}/g4-sppi/export-data?sheet={code}
    - POST /api/workpapers/{wp_id}/g4-sppi/import-data?sheet={code}（multipart/form-data）
    - G4-8按3区段分sheet导出（盘点日实存/增减变动/报表日实存+差异 各一个sheet）
    - StreamingResponse中文文件名RFC5987编码
    - 导入格式校验（错误返回行号/字段/原因详细列表）
    - _Requirements: 8.1~8.3_

  - [x] 9.2 实现前端useG4SppiImportExport.ts composable（el-dropdown导入导出▾ + 3张表）
    - 创建 `audit-platform/frontend/src/composables/useG4SppiImportExport.ts`
    - el-dropdown"导入导出▾"（导出模板/导出数据/导入数据）
    - 复用http(axios)调用后端三端点
    - G4-6: 部分一bondItems + 部分二三步数据
    - G4-7: 盘点明细items
    - G4-8: 倒轧明细items（按3区段分sheet导出）
    - 导入成功后刷新对应表格数据
    - 导入格式错误→ElMessage展示详细错误
    - _Requirements: 8.1~8.3_

  - [x] 9.3 实现后端AI端点 _g4_bond_investment_sppi_ai.py（5 section）
    - 创建 `backend/app/routers/wp_render_strategies/_g4_bond_investment_sppi_ai.py`
    - POST /api/workpapers/{wp_id}/g4-sppi/ai/{section}
    - 5个section: business-model-conclusion / sppi-bond-conclusion / sppi-financial-conclusion / inventory-conclusion / reconciliation-conclusion
    - 每个section根据当前数据上下文生成审计结论建议
    - _Requirements: 8.4, 8.5_

  - [x] 9.4 前端AI辅助按钮集成（5个section标题行右侧AI按钮）
    - G4-5: business-model-conclusion（审计结论区）
    - G4-6部分一: sppi-bond-conclusion（债券审计结论区）
    - G4-6部分二: sppi-financial-conclusion（理财审计结论区）
    - G4-7: inventory-conclusion（盘点审计结论区）
    - G4-8: reconciliation-conclusion（倒轧审计结论区）
    - 每个AI按钮调用对应endpoint → 流式返回填入textarea
    - _Requirements: 8.4, 8.5_

- [x] 10. UI精调 + 集成测试
  - [x] 10.1 UI规范统一精调
    - 表格字体13px
    - AI+复核按钮右对齐在section标题同行
    - 公式列虚线下划线+cursor:help+tooltip显示公式来源
    - 列宽min-width自适应
    - 审计说明/结论el-card包裹
    - 编制提示details折叠底部
    - G4-5问卷式交互优化（非传统表格）
    - G4-6方法论上下文琥珀色左边线+浅黄背景
    - G4-8区段Tab切换无闪烁/行同步无延迟
    - G4-5结论chip动态变色（AC绿/FVOCI蓝/FVTPL橙/未完成灰）
    - _Requirements: 9.1~9.11_

  - [x]* 10.2 集成测试（sheetName分发+公式链+UI交互）
    - sheetName分发正确性（4个sheet名→对应组件 + 未知名→OnlyOffice fallback）
    - G4-5问卷→决策→chip完整流程
    - G4-6 SPPI自动结论（4布尔→结论下拉）
    - G4-6方法论上下文动态切换（7种分析项目→方法论文本）
    - G4-7盘点明细公式链（面值×数量=总计→合计行）
    - G4-8三区段Tab行同步+倒轧公式链
    - G4-8差异>0→红色高亮+备注必填
    - 导入导出round-trip(3张表)
    - 版本链autoSnapshot触发
    - 复核对话provide/inject传递
    - selfLoad模式验证
    - _Requirements: 1.1~9.11 (全覆盖)_

- [x] 11. Final Checkpoint — 全部完成
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (13 properties via fast-check)
- Unit tests validate specific examples and edge cases
- 公式引擎所有函数为纯函数，支持独立PBT验证无需启动Vue实例
- G4-8宽表18列→3区段Tab是核心UX创新点，行同步是关键技术难点
- G4-6虚拟滚动(el-table-v2)仅部分(一)80行需要，部分(二)行数少不需要
- 导入导出仅动态行表格需要（G4-6/G4-7/G4-8），G4-5问卷式不需要
- 六大集成中仅版本链+复核对话激活，其余4项明确不集成

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13", "2.14", "3.1", "3.2"] },
    { "id": 3, "tasks": ["5.1", "6.1", "7.1", "7.3"] },
    { "id": 4, "tasks": ["5.2", "6.2", "7.2", "7.4"] },
    { "id": 5, "tasks": ["9.1", "9.3"] },
    { "id": 6, "tasks": ["9.2", "9.4"] },
    { "id": 7, "tasks": ["10.1", "10.2"] }
  ]
}
```
