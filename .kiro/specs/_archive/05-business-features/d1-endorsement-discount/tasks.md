# Implementation Plan: D1 背书贴现组专属组件

## Overview

将 `useD1NotesReceivable.ts`（1237行）中背书贴现相关的D1-6/D1-7/D1-8/D1-9四个sheet的逻辑拆分为独立子组件+子composable。按依赖顺序实现：公式引擎扩展 → 各composable → Vue组件 → 主入口集成 → 后端导入导出 → 双模式切换 → 集成测试。

## Tasks

- [x] 1. 扩展共享公式引擎 useD1FormulaEngine.ts
  - [x] 1.1 在 `composables/useD1FormulaEngine.ts` 中新增贴息+业务模式纯函数
    - 实现 `calcDiscountDays(maturityDate, discountDate)`: 到期日-贴现日天数差
    - 实现 `calcDiscountInterest(faceValue, discountRate, days)`: P×R×D/360
    - 实现 `calcInterestDifference(calculated, booked)`: 应计-账面
    - 实现 `determineBusinessMode(q1, q2, q3, q4)`: QA矩阵IF公式判定业务模式
    - 实现 `determineReportItem(businessMode)`: 业务模式→列报项目映射
    - _Requirements: 2.4, 2.5, 2.6, 2.7, 10.4, 10.5, 10.6_

  - [x]* 1.2 编写 Property 1 PBT：QA矩阵业务模式判定正确性
    - **Property 1: QA矩阵业务模式判定正确性**
    - 生成器：`fc.oneof(fc.constant('Y'), fc.constant('N'), fc.constant(''))` × 4
    - 断言：Q1=Y∧Q2=N→收取现金流；Q1=Y∧Q2=Y∧Q4=Y→两者兼有；Q1=N∨(Q2=Y∧Q4=N)→其他；余→''
    - **Validates: Requirements 2.4, 2.5, 2.6**

  - [x]* 1.3 编写 Property 2 PBT：列报项目判定与业务模式映射一致性
    - **Property 2: 列报项目判定与业务模式映射一致性**
    - 生成器：先生成4个QA值→determineBusinessMode→determineReportItem
    - 断言：非空模式必有非空列报项目；三种模式分别映射正确科目
    - **Validates: Requirements 2.7**

  - [x]* 1.4 编写 Property 3 PBT：贴息天数计算正确性
    - **Property 3: 贴息天数计算正确性**
    - 生成器：自定义日期对（discountDate ≤ maturityDate，范围2020-2030）
    - 断言：calcDiscountDays === (Date(maturity) - Date(discount)) / 86400000
    - **Validates: Requirements 10.4**

  - [x]* 1.5 编写 Property 4 PBT：应计贴现利息公式正确性
    - **Property 4: 应计贴现利息公式P×R×D/360**
    - 生成器：`fc.float({min:0,max:1e9})` P + `fc.float({min:0,max:0.5})` R + `fc.integer({min:0,max:365})` D
    - 断言：calcDiscountInterest(P,R,D) === P*R*D/360（浮点精度容差1e-6）
    - **Validates: Requirements 10.5**

  - [x]* 1.6 编写 Property 5 PBT：贴息差异计算正确性
    - **Property 5: 贴息差异计算正确性**
    - 生成器：`fc.float({min:-1e9,max:1e9})` × 2
    - 断言：calcInterestDifference(a,b) === a-b
    - **Validates: Requirements 10.6**

  - [x]* 1.7 编写 Property 7 PBT：合计行恒等于明细行之和
    - **Property 7: 合计行恒等于明细行之和**
    - 生成器：`fc.array(fc.float({min:-1e9,max:1e9}), {minLength:1, maxLength:30})`
    - 断言：calcSubtotal(rows) === rows.reduce((a,b)=>a+b, 0)
    - **Validates: Requirements 4.7, 7.3, 8.3, 10.8**

  - [x]* 1.8 编写 Property 12 PBT：贴息差异高亮判定
    - **Property 12: 贴息差异高亮判定**
    - 生成器：`fc.float({min:-1e6,max:1e6})`
    - 断言：d !== 0 时标记高亮；d === 0 时不标记
    - **Validates: Requirements 10.7**

- [x] 2. Checkpoint - 公式引擎验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 实现 useD1BusinessMode.ts composable
  - [x] 3.1 创建 `composables/useD1BusinessMode.ts`，实现业务模式分析D1-6核心逻辑
    - 定义 `BusinessModeRow`/`QACell`/`QAMatrix` 类型
    - 实现 `basisRows` reactive（从 D1-bm-basis-rows 加载3个固定行JSON）
    - 实现 `qaMatrix` reactive（从 D1-bm-qa-matrix 加载4×3矩阵JSON）
    - 实现 `businessModeResults` computed（对每列调用 determineBusinessMode）
    - 实现 `reportItemResults` computed（对每列调用 determineReportItem）
    - 实现 `updateBasisRow`（编辑业务模式依据表→debounce保存）
    - 实现 `updateQACell`（切换Y/N→立即保存→触发computed重算判定结果）
    - 实现 `auditNote`/`auditConclusion` 双向绑定+保存
    - _Requirements: 1.1-1.6, 2.1-2.8, 3.1-3.5, 13.1, 13.5, 13.6_

- [x] 4. 实现 useD1MemoReconciliation.ts composable
  - [x] 4.1 创建 `composables/useD1MemoReconciliation.ts`，实现备查簿核对D1-7核心逻辑
    - 定义 `MemoRow`/`ReconciliationRow` 类型（31列完整字段）
    - 实现 `bankRows`/`commercialRows` reactive（从 D1-memo-rows 加载JSON）
    - 实现 `bankSubtotal`/`commercialSubtotal`/`grandTotal` computed（SUM各分类行各数值列）
    - 实现 `reconciliationRows` computed（核对区3行：备查簿合计/明细账D1-2/差异）
    - 实现跨sheet取数逻辑（从 allResponses 的 D1-cat-rows 读取D1-2数据，纯computed）
    - 实现 `endorsedStats` computed（SUMIFS按状态统计贴现/背书总额）
    - 实现 `hasDifference` computed（核对区差异行任一列≠0）
    - 实现 `addRow(category)`/`removeRow(rowId)`（动态行CRUD）
    - 实现 `updateCell`（编辑→公式重算→debounce保存）
    - 实现 `cutoffDate` 双向绑定
    - _Requirements: 4.1-4.8, 5.1-5.6, 6.1-6.5, 13.2, 13.5-13.7_

  - [x]* 4.2 编写 Property 6 PBT：备查簿核对区差异
    - **Property 6: 备查簿核对区差异等于备查簿减明细账**
    - 生成器：自定义备查簿SUM值 + D1-2值生成器
    - 断言：差异行每列 === 备查簿合计 - 明细账值
    - **Validates: Requirements 5.1, 5.2**

  - [x]* 4.3 编写 Property 8 PBT：动态行添加保持结构不变量
    - **Property 8: 动态行添加保持结构不变量**
    - 生成器：`fc.array(MemoRow简化生成器, {minLength:0, maxLength:10})`
    - 断言：addRow后长度=N+1；新行数值全为0；位于合计行之前
    - **Validates: Requirements 4.8, 7.2, 8.2, 10.3**

  - [x]* 4.4 编写 Property 9 PBT：动态行序列化Round-Trip
    - **Property 9: 动态行序列化Round-Trip**
    - 生成器：自定义 MemoRow[] JSON 生成器
    - 断言：JSON.stringify → JSON.parse 后深度相等
    - **Validates: Requirements 13.7, 13.8, 13.9**

  - [x]* 4.5 编写 Property 11 PBT：SUMIFS统计正确性
    - **Property 11: D1-7 SUMIFS统计正确性**
    - 生成器：`fc.array(MemoRow)` 含随机 status ('持有'|'已贴现'|'已背书'|'到期')
    - 断言：贴现统计 === filter(已贴现).sum(amount)；背书统计 === filter(已背书).sum(amount)
    - **Validates: Requirements 5.6**

- [x] 5. 实现 useD1EndorsementDetail.ts composable
  - [x] 5.1 创建 `composables/useD1EndorsementDetail.ts`，实现贴现背书明细D1-8逻辑
    - 定义 `EndorsementRow` 类型（16列字段）
    - 实现 `discountRows`/`endorseRows` reactive（从 D1-endorse-discount-rows/transfer-rows 加载JSON）
    - 实现 `discountTotal`/`endorseTotal` computed（SUM各表的金额列）
    - 实现 `addDiscountRow()`/`removeDiscountRow()`/`addEndorseRow()`/`removeEndorseRow()`
    - 实现 `updateCell(table, rowId, field, value)`
    - 实现 `importFromMemo(table, memoRows)`（从D1-7备查簿按状态筛选导入数据）
    - 实现 `auditNote`/`auditConclusion` 双向绑定+保存
    - _Requirements: 7.1-7.5, 8.1-8.5, 9.1-9.4, 13.3, 13.5, 13.6, 13.8, 17.1-17.5_

  - [x]* 5.2 编写 Property 10 PBT：从备查簿导入状态筛选正确性
    - **Property 10: 从备查簿导入状态筛选正确性**
    - 生成器：`fc.array(MemoRow简化)` + `fc.oneof('已贴现','已背书')`
    - 断言：导入后结果行仅包含对应状态；数量等于源中该状态行数
    - **Validates: Requirements 17.1, 17.2**

- [x] 6. 实现 useD1InterestCheck.ts composable
  - [x] 6.1 创建 `composables/useD1InterestCheck.ts`，实现贴息检查D1-9逻辑
    - 定义 `InterestCheckRow` 类型（13列字段）
    - 实现 `rows` reactive（从 D1-interest-rows 加载JSON）
    - 实现各行的自动计算字段：
      - discountDays = calcDiscountDays(maturityDate, discountDate)
      - calculatedInterest = calcDiscountInterest(faceValue, discountRate, discountDays)
      - difference = calcInterestDifference(calculatedInterest, bookedInterest)
    - 实现 `totalRow` computed（SUM: 票面金额/应计利息/账面利息/差异）
    - 实现 `totalDifference`/`differenceCount`/`maxDifference` computed（差异统计）
    - 实现 `addRow()`/`removeRow(rowId)`/`updateCell(rowId, field, value)`
    - 实现 `auditNote`/`auditConclusion` 双向绑定+保存
    - _Requirements: 10.1-10.9, 11.1-11.4, 13.4, 13.5, 13.6, 13.9_

- [x] 7. Checkpoint - 全部 composable 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. 实现 D1TabBusinessMode.vue 组件
  - [x] 8.1 创建 `d1/D1TabBusinessMode.vue`（~250行），业务模式分析D1-6 HTML渲染
    - 使用 `useD1BusinessMode` composable
    - 审计目标区域（只读文本 el-alert type=info）
    - "(一)业务模式及依据"el-table：组合名称|业务模式(el-select)|具体依据(textarea)|索引号(GtIndexChip)|备注
    - 3固定行（高信用银行/低信用银行/商业）不可删除
    - "(二)分类判断"QA矩阵：4行×3列格子，每格el-select(是/否)
    - 判定结果行：业务模式（自动填充，蓝色背景）
    - 列报项目行：科目名称（自动填充，蓝色背景）
    - "审计说明"区域：textarea + 🤖AI + 💬复核
    - "审计结论"区域：textarea + 🤖AI + 💬复核
    - "编制提示"折叠区：`<details>` 蓝色左边线+浅蓝背景，5段提示文本
    - el-segmented 双模式切换头部
    - _Requirements: 1.1-1.6, 2.1-2.8, 3.1-3.5, 12.1, 16.1-16.6_

- [x] 9. 实现 D1TabMemoReconciliation.vue 组件
  - [x] 9.1 创建 `d1/D1TabMemoReconciliation.vue`（~400行），备查簿核对D1-7 HTML渲染
    - 使用 `useD1MemoReconciliation` composable
    - 审计目标+审计过程+截止日期（el-date-picker）
    - 31列宽表 el-table：
      - 横向滚动（overflow-x: auto）
      - 左侧固定列（票据类型+票据号）
      - 表头二级分组（基本信息|流转|金额|审定 四组嵌套el-table-column）
      - 列语义化控件（日期picker/金额输入/下拉/文本）
    - 银行承兑区 + 银行承兑小计行 + 商业承兑区 + 商业承兑小计行 + 合计行
    - "添加票据"按钮（分bank/commercial两个）
    - 核对区表格（3行：备查簿合计/明细账D1-2/差异，差异≠0红色高亮）
    - 跨sheet取数单元格浅蓝背景+tooltip
    - 贴现背书统计区
    - "审计说明"+"审计结论"+"编制提示"折叠区
    - el-segmented 双模式切换头部
    - el-skeleton 加载占位
    - _Requirements: 4.1-4.8, 5.1-5.6, 6.1-6.5, 12.1, 16.1-16.6_

- [x] 10. 实现 D1TabEndorsementDetail.vue 组件
  - [x] 10.1 创建 `d1/D1TabEndorsementDetail.vue`（~350行），贴现背书明细D1-8 HTML渲染
    - 使用 `useD1EndorsementDetail` composable
    - "(一)已贴现尚未到期票据检查表"el-table：16列（语义化控件）
      - 动态行增删 + 合计行
      - "会计处理是否正确"=否的行红色背景
      - "信用等级"el-select（AAA/AA+/AA/AA-/A+/A/其他）
      - "索引号"GtIndexChip
    - "(二)已背书尚未到期票据检查表"el-table：同结构
      - 动态行增删 + 合计行
    - 两表各带"从备查簿导入"按钮
    - "审计说明"+"审计结论"区域
    - el-segmented 双模式切换头部
    - _Requirements: 7.1-7.5, 8.1-8.5, 9.1-9.4, 12.1, 16.1-16.6, 17.1-17.5_

- [x] 11. 实现 D1TabInterestCheck.vue 组件
  - [x] 11.1 创建 `d1/D1TabInterestCheck.vue`（~300行），贴息检查D1-9 HTML渲染
    - 使用 `useD1InterestCheck` composable
    - 审计目标+审计过程（只读文本）
    - 贴息计算表 el-table：13列
      - 日期列：el-date-picker
      - 金额列：数字输入 + fmtAmount
      - 利率列：百分比输入（4位小数）
      - 贴息天数列：只读自动计算（灰色背景）
      - 应计利息列：只读自动计算（灰色背景）
      - 差异列：只读自动计算（差异≠0红色高亮）
      - 票据类型列：el-select
    - 动态行增删 + 合计行
    - "审计说明"+"审计结论"区域
    - el-segmented 双模式切换头部
    - _Requirements: 10.1-10.9, 11.1-11.4, 12.1, 16.1-16.6_

- [x] 12. Checkpoint - 四个 Vue 组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. 修改主入口组件集成
  - [x] 13.1 在 `GtD1NotesReceivable.vue` 中集成四个新子组件
    - 在 el-tabs 中新增四个 tab-pane 引用 D1TabBusinessMode/D1TabMemoReconciliation/D1TabEndorsementDetail/D1TabInterestCheck
    - 传递 allResponses/wpId/projectId/isReadonly 等 props
    - 替换原有占位Tab内容
    - 运行现有 D1 测试套件确认不回归
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

  - [x] 13.2 从 `useD1NotesReceivable.ts` 中删除已拆出的背书贴现逻辑
    - 删除业务模式/备查簿/贴现背书/贴息相关代码
    - 确保拆分后 useD1NotesReceivable.ts 进一步缩减
    - 运行全部测试确认不回归
    - _Requirements: 15.5, 15.6, 15.7, 15.8_

- [x] 14. 实现后端导入导出端点
  - [x] 14.1 创建后端导入导出路由（扩展已有 `_d1_import_export.py`）
    - 新增 D1-6/D1-7/D1-8/D1-9 四个sheet的导出模板/导出数据/导入数据端点
    - D1-7导出模板含31列表头+格式（最复杂）
    - D1-9导出模板含贴息公式（不含数据行）
    - 使用 openpyxl 生成/解析 xlsx
    - 格式校验：列名不匹配时返回 400 + 错误列名列表
    - 行数限制：超500行截断 + 返回警告摘要
    - 注册路由到 router_registry
    - _Requirements: 14.1-14.6_

  - [x]* 14.2 编写后端导入导出集成测试（hypothesis）
    - Round-trip 测试：生成随机行数据 → export → import → 验证等价
    - D1-7 31列模板格式校验
    - D1-9 贴息公式列识别
    - _Requirements: 14.3, 14.4_

- [x] 15. 实现前端导入导出 UI
  - [x] 15.1 在四个子组件中添加导入导出工具栏
    - 每个 D1TabXxx.vue 顶部添加工具栏（el-button-group）
    - "导出模板"按钮 → 调用 export-template → 下载 xlsx
    - "导出数据"按钮 → 调用 export-data → 下载 xlsx
    - "导入数据"按钮 → el-upload → 调用 import-data → 显示摘要
    - 导入错误时 ElMessage.error 展示不匹配列名
    - _Requirements: 14.1-14.6_

- [x] 16. 实现双模式切换
  - [x] 16.1 在四个子组件中实现 HTML ↔ OnlyOffice 双模式切换
    - 每个 Tab 页头部 el-segmented（"结构化视图" | "在线编辑"）
    - 切换到 OO 模式：获取 onlyoffice-config → GtOnlyOfficeSheet → onDocumentReady SetVisible(false) 隐藏非当前sheet
    - 切回 HTML 模式：重新加载 checklist_responses
    - OO 服务不可用时禁用 + tooltip
    - _Requirements: 12.1-12.5_

- [x] 17. Checkpoint - 导入导出和双模式验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 18. 持久化与自动保存集成
  - [x] 18.1 确保四个 composable 的持久化逻辑完整
    - 验证 item_id 命名规范（D1-bm-/D1-memo-/D1-endorse-/D1-interest- 前缀）
    - 验证 debounce 2秒自动保存（编辑金额/文本/日期后）
    - 验证选择类字段（QA矩阵Y/N、下拉）立即保存
    - 验证动态行 JSON 序列化存储于 remark 字段
    - 验证跨sheet数据变更后 computed 自动刷新核对区
    - _Requirements: 13.1-13.9_

- [x] 19. 复核对话集成
  - [x] 19.1 在四个子组件中集成 GtReviewDialog
    - inject openReviewDialog
    - 审计说明/结论区域固定💬入口按钮
    - 表格单元格右键菜单"发起复核对话"（@cell-contextmenu）
    - 活跃线程蓝/红圆点标记（onMounted加载 /review-threads/active）
    - _Requirements: 18.3-18.7_

- [x] 20. 回归测试
  - [x] 20.1 运行现有 D1 测试套件确保无回归
    - `rtk python -m pytest backend/tests/ -k d1 -v --tb=short`
    - `rtk npx vitest run --reporter=verbose` (D1相关测试文件)
    - 确认原有测试全绿
    - 如有失败，修复后重跑直至全绿

- [x] 21. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 每个 Property 对应 design.md 中的一个 correctness property
- D1-7 是本spec最复杂的组件（31列宽表+核对区+统计区），composable可能接近400行上限
- D1-6 的QA矩阵IF公式在前端composable中实现，不依赖后端计算
- D1-8 的"从备查簿导入"功能依赖 D1-7 数据，需在 D1-7 composable 完成后实现
- D1-9 贴息公式 P×R×D/360 使用已有 useD1FormulaEngine 扩展
- 所有 PBT 使用 fast-check，numRuns: 100
- 后端导入导出扩展已有 `_d1_import_export.py`，不新建文件
