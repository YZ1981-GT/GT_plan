# Implementation Plan: D1 审定表组件拆分

## Overview

将 `useD1NotesReceivable.ts`（1237行）中审定表D1-1、原值明细D1-2/D1-3、坏账准备D1-4 四个sheet的逻辑拆分为独立子组件+子composable。按依赖顺序实现：共享公式引擎 → 各composable → Vue组件 → 后端导入导出 → 双模式切换 → 集成测试。

## Tasks

- [x] 1. 实现共享公式引擎 useD1FormulaEngine.ts
  - [x] 1.1 创建 `composables/useD1FormulaEngine.ts`，实现全部纯函数
    - 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN → 0）
    - 实现 `calcAuditedAmount`（审定数 = 未审 + AJE + RJE，3参数净额版本，对应源模板E=B+C+D）
    - 实现 `calcChangeRate`（变动率，含期初=0特殊处理）
    - 实现 `calcSubtotal`（小计 = SUM明细行）
    - 实现 `calcNetValue`（净值 = 原值 - 坏账准备）
    - 实现 `isChangeRateExceeding`（变动率阈值判定）
    - 实现 `calcExpectedLossRate`（ECL迁徙率连乘）
    - 实现 `calcProvision`（应计提 = 余额 × 损失率）
    - 实现 `calcDifference`（差异 = 实际 - 应计提）
    - 实现 `calcBadDebtEndBalance`（期末未审数 = 期初审定 + 计提 - 收回 - 转回 - 核销 + 其他）
    - 实现 `calcCurrentUnadjusted`（期末未审数 = 期初审定 + 本期增加 - 本期减少，D1-2/D1-3用）
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 6.4, 10.5_

  - [x]* 1.2 编写 Property 1 PBT：审定数公式正确性
    - **Property 1: 审定数公式正确性**
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 3（未审/AJE净额/RJE净额）
    - 断言：返回值 === 未审 + AJE + RJE
    - **Validates: Requirements 1.3, 4.5, 5.5, 6.3**

  - [x]* 1.3 编写 Property 2 PBT：变动额与变动率公式正确性
    - **Property 2: 变动额与变动率公式正确性**
    - 生成器：`fc.float` × 2（含0边界策略）
    - 断言：变动额 === 期末-期初；变动率期初=0时特殊处理
    - **Validates: Requirements 1.4**

  - [x]* 1.4 编写 Property 3 PBT：小计行恒等于明细行之和
    - **Property 3: 小计行恒等于明细行之和**
    - 生成器：`fc.array(fc.float, {minLength:1, maxLength:20})`
    - 断言：calcSubtotal(rows) === rows.reduce((a,b)=>a+b, 0)
    - **Validates: Requirements 1.5, 4.6, 5.6, 6.5**

  - [x]* 1.5 编写 Property 4 PBT：净值等于原值减坏账准备
    - **Property 4: 净值等于原值减坏账准备**
    - 生成器：`fc.float` × 2
    - 断言：calcNetValue(gross, bad) === gross - bad
    - **Validates: Requirements 1.6**

  - [x]* 1.6 编写 Property 5 PBT：变动率阈值高亮判定
    - **Property 5: 变动率阈值高亮判定**
    - 生成器：`fc.float({min:-10, max:10})`
    - 断言：isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)
    - **Validates: Requirements 1.7**

  - [x]* 1.7 编写 Property 11 PBT：坏账准备期末未审数公式
    - **Property 11: 坏账准备期末未审数公式**
    - 生成器：`fc.float` × 6
    - 断言：calcBadDebtEndBalance(...) === 期初审定 + 计提 - 收回 - 转回 - 核销 + 其他
    - **Validates: Requirements 6.4**

- [x] 2. Checkpoint - 公式引擎验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. 实现 useD1Adjudication.ts composable
  - [ ] 3.1 创建 `composables/useD1Adjudication.ts`，实现审定表D1-1核心逻辑
    - 定义 `AdjudicationSection`/`AdjudicationDetailRow` 类型
    - 定义 `ADJUDICATION_ROWS_CONFIG` 三区块固定结构配置
    - 实现 `adjudicationSections` computed（三区块：原值/坏账/净值，各含明细行+小计行）
    - 实现跨Sheet取数逻辑（直接从同一个 allResponses Map 读取 D1-cat-rows/D1-bd-*-rows 的 remark JSON，纯 computed 响应式链，不走 API）
    - 废弃原有 `refreshCrossSheetData()` API调用方式，改为 computed 自动响应
    - 实现 `trialBalanceDiff` computed（试算平衡表差异行）
    - 实现 `auditNote` 双向绑定 + saveAuditNote
    - 实现 `auditConclusion` 双向绑定 + saveAuditConclusion
    - 实现 `autoChangeDescription` computed（自动生成变动百分比句子："公司应收票据期末净值较期初净值增加/减少：xx%"）
    - 实现 `aiGenerateNote()` / `aiGenerateConclusion()`（调用 `/review-dialog/ai-generate` 端点，context=审定表三区块摘要）
    - 实现 `updateCell`（单元格编辑 → 触发公式重算 → debounce 保存）
    - 实现 EventBus `publishAdjudicated`（审定数变化后发布事件）
    - 实现 EventBus 监听 `adjustment:created`（AJE/RJE → 累加对应列）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 8.1, 8.5, 8.6_

  - [ ]* 3.2 编写 Property 6 PBT：跨Sheet数据流完整性
    - **Property 6: 跨Sheet数据流完整性**
    - 生成器：自定义 CategoryRow[] + BadDebtRow[] 生成器
    - 断言：D1-1原值区 = D1-2对应行数据；坏账区 = D1-4行之和
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 3.3 编写 Property 7 PBT：EventBus调整分录同步正确性
    - **Property 7: EventBus调整分录同步正确性**
    - 生成器：`fc.oneof('AJE','RJE')` + `fc.float` + 科目标识
    - 断言：对应行的 AJE/RJE 列正确累加事件金额
    - **Validates: Requirements 3.1**

- [ ] 4. 实现 useD1DetailCategory.ts composable
  - [ ] 4.1 创建 `composables/useD1DetailCategory.ts`，实现按类别明细D1-2逻辑
    - 定义 `CategoryRow` 类型（含 rowId/category/isFixed/各期数值字段）
    - 实现 `rows` reactive（从 checklist_responses D1-cat-rows 加载 JSON 数组）
    - 实现预设固定行（银行承兑汇票 + 商业承兑汇票，isFixed=true 不可删除）
    - 实现 `subtotalRow` computed（SUM 所有明细行各数值列）
    - 实现 `addRow()`（在小计行上方新增空行，所有数值字段=0）
    - 实现 `removeRow(rowId)`（仅允许删除 isFixed=false 的行）
    - 实现 `updateCell(rowId, field, value)`（编辑 → 公式重算 → debounce 保存）
    - 实现序列化/反序列化（JSON.stringify rows → checklist_responses remark 字段）
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 8.2, 8.5, 8.7_

  - [ ]* 4.2 编写 Property 8 PBT：动态行添加保持结构不变量
    - **Property 8: 动态行添加保持结构不变量**
    - 生成器：`fc.array(CategoryRow生成器, {minLength:0, maxLength:10})`
    - 断言：addRow后长度=N+1；新行数值全为0；位于末尾（小计行之前）
    - **Validates: Requirements 4.3, 5.2**

  - [ ]* 4.3 编写 Property 13 PBT：动态行序列化Round-Trip
    - **Property 13: 动态行序列化Round-Trip**
    - 生成器：自定义 CategoryRow[] JSON 生成器（完整字段）
    - 断言：JSON.stringify → JSON.parse 后深度相等
    - **Validates: Requirements 8.7, 9.3**

- [ ] 5. 实现 useD1DetailCustomer.ts composable
  - [ ] 5.1 创建 `composables/useD1DetailCustomer.ts`，实现按客户明细D1-3逻辑
    - 定义 `CustomerRow` 类型（含 customerName/companyCode/relationType 等字段）
    - 实现 `rows` reactive（从 D1-cust-rows 加载）
    - 实现 `subtotalRow` computed（SUM 所有明细行各金额列）
    - 实现 `searchQuery` + `filteredRows` computed（按客户名称模糊搜索，大小写不敏感）
    - 实现 `addRow()`/`removeRow(rowId)`（动态行CRUD）
    - 实现 `matchRelatedParty(name)`（从 relatedParties 列表中模糊匹配关联关系）
    - 实现 `updateCell`（编辑时自动触发关联方匹配）
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 8.3, 8.5, 8.7_

  - [ ]* 5.2 编写 Property 9 PBT：客户名称关联方自动匹配
    - **Property 9: 客户名称关联方自动匹配**
    - 生成器：`fc.string({minLength:1})` + `fc.array(fc.string({minLength:1}))`
    - 断言：名称在列表中 → '关联方'；不在 → '非关联方'
    - **Validates: Requirements 5.3**

  - [ ]* 5.3 编写 Property 10 PBT：客户搜索过滤正确性
    - **Property 10: 客户搜索过滤正确性**
    - 生成器：`fc.string` + `fc.array(CustomerRow生成器)`
    - 断言：filteredRows 每行 customerName 包含 q（不敏感）；无遗漏无多余
    - **Validates: Requirements 5.7**

- [ ] 6. 实现 useD1BadDebt.ts composable
  - [ ] 6.1 创建 `composables/useD1BadDebt.ts`，实现坏账准备D1-4逻辑
    - 定义 `BadDebtRow` 类型（含 category/label/isSubRow/各期变动字段）
    - 实现 `individualRows`/`portfolioRows` reactive（按单项/按组合分组）
    - 实现 `subtotalRow` computed（SUM 全部行）
    - 实现期末未审数自动计算（= 期初审定 + 计提 - 收回 - 转回 - 核销 + 其他）
    - 实现 `eclDifference` computed + `eclWarning` computed（与ECL测试差异警告）
    - 实现 `addSubRow(category)`/`removeSubRow(rowId)`（展开子行增删）
    - 实现 `updateCell` + debounce 保存
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.4, 8.5_

  - [ ]* 6.2 编写 Property 12 PBT：ECL差异警告判定
    - **Property 12: ECL差异警告判定**
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 2
    - 断言：不相等时返回含差异金额的警告字符串；相等时返回 null
    - **Validates: Requirements 6.6**

- [ ] 7. Checkpoint - 全部 composable 验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. 实现 D1TabAdjudication.vue 组件
  - [ ] 8.1 创建 `d1/D1TabAdjudication.vue`（~350行），审定表D1-1 HTML渲染
    - 使用 `useD1Adjudication` composable
    - 渲染三区块 el-table（原值/坏账/净值），每区块含明细行+小计行
    - 列配置：项目|期初未审|期初AJE|期初RJE|期初审定|期末未审|期末AJE|期末RJE|期末审定|增减变动额|增减比例|原因分析
    - 小计行/净值行不可编辑（:class="{ 'is-summary': !row.isEditable }"）
    - 跨sheet自动取数单元格浅蓝色背景 + tooltip 显示来源
    - 变动率 >30% 红色高亮（:class="{ 'rate-warning': isExceeding }"）
    - 试算平衡表数行 + 差异行（差异≠0红色高亮）
    - "1.审计说明"区域：自动变动百分比句子 + "主要原因"红色标签 + textarea + 🤖AI按钮 + 💬复核对话入口
    - "2.审计结论"区域：textarea + 🤖AI按钮 + 💬复核对话入口
    - 表格单元格 @cell-contextmenu → 右键"发起复核对话"（inject openReviewDialog）
    - 活跃线程蓝/红圆点标记（onMounted 加载 /review-threads/active）
    - 金额格式化（displayPrefs.fmtAmount）+ 零值显示"-" + 负数红色括号
    - 比例列百分比格式（保留2位小数）
    - el-skeleton 加载占位
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.4, 3.4, 3.5, 3.6, 3.7, 11.1, 11.2, 11.3, 11.4, 11.6_

- [ ] 9. 实现 D1TabDetailCategory.vue 组件
  - [ ] 9.1 创建 `d1/D1TabDetailCategory.vue`（~300行），原值明细按类别D1-2 HTML渲染
    - 使用 `useD1DetailCategory` composable
    - el-table 渲染：票据种类|期初未审|期初AJE|期初RJE|期初审定|本期增加|本期减少|期末未审|期末AJE|期末RJE|期末审定
    - 预设银行承兑/商业承兑固定行（不可删除）
    - "添加种类"按钮 + 动态行删除按钮
    - 小计行自动SUM（不可编辑，底部固定）
    - 金额格式化 + 负数红色括号 + 零值"-"
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 11.1, 11.2, 11.3_

- [ ] 10. 实现 D1TabDetailCustomer.vue 组件
  - [ ] 10.1 创建 `d1/D1TabDetailCustomer.vue`（~350行），原值明细按客户D1-3 HTML渲染
    - 使用 `useD1DetailCustomer` composable
    - el-table 渲染：客户名称|公司代码|关联关系|期初未审|...|期末审定（14列）
    - 客户名称左对齐，金额列右对齐
    - "添加客户"按钮 + 动态行删除
    - 关联方行橙色背景高亮（:row-class-name）
    - 搜索框（表头上方）→ filteredRows 过滤
    - 超20行启用虚拟滚动（el-table-v2 或 virtual-scroll）
    - 小计行 + 金额格式化
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 11.1, 11.2, 11.3, 11.5_

- [ ] 11. 实现 D1TabBadDebt.vue 组件
  - [ ] 11.1 创建 `d1/D1TabBadDebt.vue`（~300行），坏账准备D1-4 HTML渲染
    - 使用 `useD1BadDebt` composable
    - el-table 渲染：项目|期初未审|期初AJE|期初RJE|期初审定|本期计提|本期收回|本期转回|本期核销|本期其他|期末未审|期末AJE|期末RJE|期末审定
    - 固定行结构：按单项计提（可展开子行）+ 按组合计提（可展开子行）+ 小计
    - 子行增删按钮
    - ECL差异警告（小计行旁黄色 el-alert）
    - 小计行不可编辑 + 金额格式化
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 11.1, 11.2, 11.3_

- [ ] 12. Checkpoint - 四个 Vue 组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. 修改主入口组件 GtD1NotesReceivable.vue
  - [ ] 13.1 在 `GtD1NotesReceivable.vue` 中集成四个新子组件（新旧并存验证）
    - 在 el-tabs 中新增四个 tab-pane 引用 D1TabAdjudication/D1TabDetailCategory/D1TabDetailCustomer/D1TabBadDebt
    - 传递 allResponses/wpId/projectId/isReadonly 等 props
    - 暂时保留旧代码（注释掉旧 tab-pane），确认新组件正常工作
    - 运行现有 D1 测试套件（76 tests: 13 PBT + 88 vitest + 1 hypothesis）确认不回归
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ] 13.2 从 `useD1NotesReceivable.ts` 中删除已拆出逻辑
    - 删除 adjudicationRows/crossSheetData/d14Data/crossSheetValues 相关代码（~800行）
    - 删除 ECL agingBands/migrationRateMatrix（已移至 useD1BadDebt）
    - 删除旧注释掉的 tab-pane
    - 确保拆分后 useD1NotesReceivable.ts 约 ~500 行
    - 再次运行全部测试确认不回归
    - _Requirements: 10.5, 10.6, 10.7, 10.8_

- [ ] 14. 实现后端导入导出端点
  - [ ] 14.1 创建 `backend/app/routers/wp_render_strategies/_d1_import_export.py`（~200行）
    - 实现 `POST /api/workpapers/{wp_id}/d1/export-template?sheet=D1-2`（空白xlsx模板，含表头+格式+公式）
    - 实现 `POST /api/workpapers/{wp_id}/d1/export-data?sheet=D1-2`（含当前数据的xlsx）
    - 实现 `POST /api/workpapers/{wp_id}/d1/import-data?sheet=D1-2`（解析xlsx → 回写checklist_responses）
    - 使用 openpyxl 生成/解析 xlsx
    - 格式校验：列名不匹配时返回 400 + 错误列名列表
    - 行数限制：超500行截断 + 返回警告摘要
    - 支持 D1-2/D1-3/D1-4 三个sheet的导入导出
    - 注册路由到 router_registry
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 14.2 编写后端导入导出集成测试（hypothesis）
    - Round-trip 测试：生成随机行数据 → export → import → 验证等价
    - 模板格式校验：随机列名排列 → 验证错误检测
    - _Requirements: 9.3, 9.4_

- [ ] 15. 实现前端导入导出 UI
  - [ ] 15.1 在四个子组件中添加导入导出工具栏
    - 每个 D1TabXxx.vue 顶部添加工具栏（el-button-group）
    - "导出模板"按钮 → 调用 export-template 端点 → 下载 xlsx
    - "导出数据"按钮 → 调用 export-data 端点 → 下载 xlsx
    - "导入数据"按钮 → el-upload 组件 → 调用 import-data → 显示摘要 ElMessage.success
    - 导入错误时 ElMessage.error 展示不匹配列名
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [ ] 16. 实现双模式切换
  - [ ] 16.1 在四个子组件中实现 HTML ↔ OnlyOffice 双模式切换
    - 每个 Tab 页头部添加 el-segmented（"结构化视图" | "在线编辑"）
    - 切换到 OO 模式：获取 onlyoffice-config → 渲染 GtOnlyOfficeSheet → onDocumentReady 中 SetVisible(false) 隐藏非当前sheet
    - 切回 HTML 模式：重新加载 checklist_responses 刷新数据
    - OO 服务不可用时禁用"在线编辑"选项 + tooltip
    - 复用已有 GtOnlyOfficeSheet 组件和健康检查逻辑
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 17. Checkpoint - 导入导出和双模式验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 18. 持久化与自动保存集成
  - [ ] 18.1 确保四个 composable 的持久化逻辑完整
    - 验证 item_id 命名规范（D1-adj-/D1-cat-/D1-cust-/D1-bd- 前缀）
    - 验证 debounce 2秒自动保存（编辑金额/文本后）
    - 验证选择类字段立即保存
    - 验证动态行 JSON 序列化存储于 remark 字段
    - 验证跨sheet数据变更后 computed 自动刷新审定表引用值（无 API 调用延迟）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 2.3_

- [ ] 19. 回归测试 - 运行现有 D1 全量测试
  - [ ] 19.1 运行现有 D1 测试套件确保无回归
    - `rtk python -m pytest backend/tests/ -k d1 -v --tb=short`
    - `rtk npx vitest run --reporter=verbose` (D1相关测试文件)
    - 确认 76 tests (13 PBT + 88 vitest + 1 hypothesis) 全绿
    - 如有失败，修复后重跑直至全绿

- [ ] 20. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 每个 Property 对应 design.md 中的一个 correctness property
- 从 `useD1NotesReceivable.ts` 拆出的内容参照 design.md "拆分边界" 表
- 后端导入导出（Task 14）和前端导入导出 UI（Task 15）已分开
- 双模式切换（Task 16）依赖组件基础完成（Task 8-11）
- 所有 PBT 使用 fast-check，numRuns: 100
