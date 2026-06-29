# Implementation Plan: D1 附注披露组专属组件

## Overview

将 `useD1NotesReceivable.ts` 中附注披露（上市公司）和附注披露（国企）两个sheet的逻辑拆分为独立子组件+子composable。共用 `useD1Disclosure.ts`（~300行）+ `D1TabDisclosure.vue`（~350行），通过 variant='listed'|'soe' 区分版本。按依赖顺序实现：公式扩展 → composable → Vue组件 → 后端导入导出 → 双模式 → 集成。

## Tasks

- [ ] 1. 扩展 useD1FormulaEngine.ts 公式函数
  - [ ] 1.1 在 `useD1FormulaEngine.ts` 中新增 `safeDivide` 纯函数
    - 实现 `safeDivide(numerator, divisor)`：divisor=0 返回 0，否则返回 numerator/divisor
    - 对应源模板 IFERROR(x/y, 0) 语义
    - _Requirements: 5.4, 5.5, 6.2, 7.3_

  - [ ]* 1.2 编写 Property 10 PBT：safeDivide 安全除法
    - **Property 10: safeDivide 安全除法**
    - 生成器：`fc.float({min:-1e9, max:1e9, noNaN:true})` × 2（含分母=0策略）
    - 断言：分母=0时返回0；否则返回分子/分母
    - **Validates: Requirements 5.4, 5.5, 6.2, 7.3**

  - [ ]* 1.3 编写 Property 1 PBT：比例计算正确性
    - **Property 1: 比例计算正确性（IFERROR语义）**
    - 生成器：`fc.float({min:-1e9, max:1e9, noNaN:true})` × 2（余额, 合计）
    - 断言：合计=0时比例=0；否则比例=余额/合计
    - **Validates: Requirements 5.4**

  - [ ]* 1.4 编写 Property 2 PBT：预期信用损失率计算正确性
    - **Property 2: 预期信用损失率计算正确性**
    - 生成器：`fc.float` × 2（坏账准备, 账面余额）
    - 断言：余额=0时损失率=0；否则损失率=坏账/余额
    - **Validates: Requirements 5.5, 6.2, 7.3**

- [ ] 2. 实现 useD1Disclosure.ts composable 核心逻辑
  - [ ] 2.1 创建 `composables/useD1Disclosure.ts`，实现框架与跨sheet取数
    - 定义所有数据模型类型（PledgedRow/EndorsedRow/TransferRow/BadDebtClassRow/IndividualDetailRow/PortfolioDetailRow/BadDebtMovementRow/ReversalDetailRow/WriteOffDetailRow/CategorySummaryRow）
    - 实现 `sectionOrder` computed（上市6子节/国企7子节顺序）
    - 实现 `crossSheetData` computed（从 allResponses Map 读取 D1-adj-* 前缀数据）
    - 实现 item_id 前缀逻辑（D1-disc-listed-/D1-disc-soe- 根据 variant 动态确定）
    - 实现数据加载逻辑（从 checklist_responses 各 item_id 加载 JSON 数组 → reactive rows）
    - _Requirements: 1.1, 1.2, 1.3, 10.2, 11.1, 11.2, 11.3, 13.1, 15.2, 15.3_

  - [ ] 2.2 实现质押票据子节逻辑
    - 实现 `pledgedRows` reactive（预设银行承兑+商业承兑固定行）
    - 实现 `pledgedTotal` computed（SUM 所有行的 pledgedAmount）
    - 实现 `addPledgedRow()`/`removePledgedRow(rowId)`（动态行 CRUD）
    - 实现 `updateCell` 质押部分（编辑 → 重算合计 → debounce 保存）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 2.3 实现背书贴现子节逻辑
    - 实现 `endorsedRows` reactive（预设固定行）
    - 实现 `endorsedTotal` computed（SUM 各列）
    - 实现 `addEndorsedRow()`/`removeEndorsedRow(rowId)`
    - 实现 CAS23 提示文字常量
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 2.4 实现转应收账款子节逻辑
    - 实现 `transferRows` reactive（预设固定行）
    - 实现 `transferTotal` computed
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ] 2.5 实现坏账分类子节逻辑（最复杂）
    - 实现期末/上年分类表 rows + total computed
    - 实现比例列公式（safeDivide(balance, totalBalance)）
    - 实现损失率列公式（safeDivide(provision, balance)）
    - 实现账面价值列公式（calcNetValue(balance, provision)）
    - 实现按单项明细表 rows（期末+上年各一组）+ addRow/removeRow
    - 实现银行承兑组合明细 rows（期末+上年）+ addRow/removeRow
    - 实现商业承兑组合明细 rows（期末+上年）+ addRow/removeRow
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ] 2.6 实现坏账变动子节逻辑
    - 实现 `movementRows` reactive（上市版1行/国企版3行：单项+组合+合计）
    - 实现期末余额公式（calcBadDebtEndBalance）
    - 实现重要转回明细 rows + addRow/removeRow + total computed
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ] 2.7 实现核销子节逻辑
    - 实现 `writeOffAmount` ref + 重要核销明细 rows + addRow/removeRow + total
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ] 2.8 实现国企专有票据分类子节逻辑
    - 实现 `categorySummaryRows` computed（从 crossSheetData 映射）
    - 实现 `categorySummaryTotal` computed（SUM）
    - 实现账面价值计算（余额 - 坏账准备）
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [ ] 3. Checkpoint - composable 核心逻辑验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 编写 composable PBT 测试
  - [ ]* 4.1 编写 Property 3 PBT：账面价值等于余额减坏账
    - **Property 3: 账面价值等于余额减坏账**
    - 生成器：`fc.float({min:-1e9, max:1e9, noNaN:true})` × 2
    - 断言：calcNetValue(balance, provision) === balance - provision
    - **Validates: Requirements 5.6, 10.3**

  - [ ]* 4.2 编写 Property 4 PBT：合计行恒等于明细行之和
    - **Property 4: 合计行恒等于明细行之和**
    - 生成器：`fc.array(fc.float({noNaN:true}), {minLength:1, maxLength:20})`
    - 断言：calcSubtotal(rows) === rows.reduce((a,b) => a+b, 0)
    - **Validates: Requirements 2.5, 3.4, 4.3, 5.7, 8.7, 9.4**

  - [ ]* 4.3 编写 Property 5 PBT：坏账变动期末余额公式
    - **Property 5: 坏账变动期末余额公式**
    - 生成器：`fc.float({min:-1e9, max:1e9, noNaN:true})` × 6
    - 断言：期末 === 上年末 + 计提 - 转回 - 核销 - 转销 + 其他
    - **Validates: Requirements 8.2**

  - [ ]* 4.4 编写 Property 6 PBT：动态行添加保持结构不变量
    - **Property 6: 动态行添加保持结构不变量**
    - 生成器：`fc.array(PledgedRow生成器, {minLength:0, maxLength:10})`
    - 断言：addRow后长度=N+1；新行数值全为0
    - **Validates: Requirements 2.3, 3.3, 6.3, 8.6, 9.3**

  - [ ]* 4.5 编写 Property 7 PBT：跨Sheet取数响应式一致性
    - **Property 7: 跨Sheet取数响应式一致性**
    - 生成器：自定义 Map<string, {value: string}> 生成器（含 D1-adj-* key）
    - 断言：crossSheetData 各字段 === parseNum(map.get(key).value)
    - **Validates: Requirements 10.2, 11.2, 11.3**

  - [ ]* 4.6 编写 Property 8 PBT：动态行序列化 Round-Trip
    - **Property 8: 动态行序列化 Round-Trip**
    - 生成器：自定义 PledgedRow[]/EndorsedRow[]/... 生成器
    - 断言：JSON.stringify → JSON.parse 深度相等
    - **Validates: Requirements 13.4, 13.5**

  - [ ]* 4.7 编写 Property 9 PBT：变体子节顺序正确性
    - **Property 9: 变体子节顺序正确性**
    - 生成器：`fc.constantFrom('listed', 'soe')`
    - 断言：listed → ['pledged','endorsed','transfer','badDebtClass','badDebtMovement','writeOff']；soe → ['categorySummary','badDebtClass','badDebtMovement','pledged','endorsed','transfer','writeOff']
    - **Validates: Requirements 1.2, 1.3**

- [ ] 5. Checkpoint - PBT 验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. 实现 D1TabDisclosure.vue 组件
  - [ ] 6.1 创建 `d1/D1TabDisclosure.vue`（~350行），附注披露 HTML 渲染
    - 接收 props: variant/allResponses/wpId/projectId/isReadonly
    - 使用 `useD1Disclosure` composable
    - 顶部：变体标识(el-tag) + el-segmented双模式切换 + 导入导出工具栏(el-button-group)
    - 跨sheet取数区（上市版顶部浅蓝色摘要卡片）
    - 按 sectionOrder 动态渲染 el-card 折叠卡片
    - 每个子节内部用 el-table 渲染对应数据
    - 金额格式化（displayPrefs.fmtAmount）+ 零值"-" + 负数红色括号 + 百分比格式
    - 标题列左对齐 / 金额列右对齐
    - el-skeleton 加载占位
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

  - [ ] 6.2 实现质押票据子节 el-table 渲染
    - 列：票据种类 | 期末质押金额
    - 固定行不可删除 + 动态行删除按钮
    - "添加行"按钮
    - 合计行（底部固定，不可编辑）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 6.3 实现背书贴现子节 el-table 渲染
    - 列：票据种类 | 终止确认金额 | 未终止确认金额
    - 固定行 + 动态行 + 合计行
    - CAS23 提示文字（el-alert type="info"，表格下方）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 6.4 实现转应收账款子节 el-table 渲染
    - 列：票据种类 | 转应收账款金额
    - 固定行 + 合计行
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ] 6.5 实现坏账分类子节渲染（最复杂子节）
    - 期末分类表 el-table：类别|余额|比例(%)|坏账准备|损失率(%)|账面价值
    - 上年分类表 el-table（同结构）
    - 按单项明细表（期末+上年各一个 el-table）：名称|余额|坏账|损失率|依据
    - 银行承兑组合明细表（期末+上年）：出票人类型/账龄|余额|坏账|损失率
    - 商业承兑组合明细表（期末+上年）：同银行结构
    - 各表动态行增删按钮
    - 提示文字区域
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ] 6.6 实现坏账变动子节渲染
    - 变动表 el-table：项目|上年末|计提|转回|核销|转销|其他|期末
    - 上市版单行 / 国企版三行(单项+组合+合计)
    - 重要转回明细表 el-table：单位名称|转回原因|原确认方式|转回依据|转回金额
    - 动态行增删 + 合计行
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ] 6.7 实现核销子节渲染
    - 核销汇总（单值显示）
    - 重要核销明细表 el-table：单位名称|票据性质|核销金额|核销原因|履行程序
    - 动态行增删 + 合计行
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ] 6.8 实现国企票据分类子节渲染（v-if="variant==='soe'"）
    - 列：票据种类|期末余额|期末坏账|期末账面价值|期初余额|期初坏账|期初账面价值
    - 浅蓝色背景标记自动取数单元格 + tooltip
    - 合计行
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [ ] 7. Checkpoint - Vue 组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. 集成到主入口 GtD1NotesReceivable.vue
  - [ ] 8.1 在 `GtD1NotesReceivable.vue` 中新增两个 tab-pane 引用 D1TabDisclosure
    - tab-pane "附注披露(上市)" → `<D1TabDisclosure variant="listed" />`
    - tab-pane "附注披露(国企)" → `<D1TabDisclosure variant="soe" />`
    - 传递 allResponses/wpId/projectId/isReadonly props
    - 保持现有 tab 顺序不变，新增在原有附注占位 tab 位置
    - _Requirements: 15.1, 15.2_

  - [ ] 8.2 从 `useD1NotesReceivable.ts` 中删除附注披露相关旧代码
    - 删除附注披露上市/国企相关的 reactive 数据和 computed
    - 删除旧 tab-pane 占位
    - 确保拆分后 useD1NotesReceivable.ts 行数进一步减少
    - _Requirements: 15.2, 15.3_

- [ ] 9. 实现双模式切换
  - [ ] 9.1 在 D1TabDisclosure.vue 中实现 HTML ↔ OnlyOffice 双模式
    - el-segmented 切换控件（"结构化视图" | "在线编辑"）
    - 切换到 OO：获取 onlyoffice-config → 渲染 GtOnlyOfficeSheet → SetVisible(false) 隐藏非当前sheet
    - sheetName 根据 variant 确定（"附注披露信息（上市公司）" / "附注披露信息（国企）"）
    - 切回 HTML：重新加载 checklist_responses 刷新数据
    - OO 不可用时禁用选项 + tooltip
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [ ] 9.5 实现提示文字展示
  - [ ] 9.5.1 在 useD1Disclosure.ts 中定义 DISCLOSURE_GUIDANCE 常量
    - 顶部说明提示（云信/融信数字化债权）
    - 背书贴现 CAS23 终止确认判断提示（4段）
    - 坏账分类提示（逾期转应收账款）
    - 核销提示（逐项披露要求）
    - _Requirements: 17.1, 17.2, 17.3_

  - [ ] 9.5.2 在 D1TabDisclosure.vue 中实现提示折叠区域
    - 各子节对应位置插入 `<details>` 折叠区域（只读提示）
    - 蓝色左边线 + 浅蓝背景 + 默认收起
    - "可无限量添加行"位置显示浅灰色占位提示行
    - _Requirements: 17.4, 17.5_

- [ ] 9.5.3 实现"说明"文本区域与附注模块双向回写
  - [ ] 9.5.3.1 在各子节"说明："标签处渲染可编辑 textarea（区别于不可编辑的提示折叠区）
    - 每个 textarea 旁增加🤖AI生成按钮 + 💬复核对话入口（inject openReviewDialog）
    - 保存时发布 EventBus `disclosure:note-text-updated` 事件（payload含 variant/sectionKey/content/updatedBy/updatedAt）
    - 监听 EventBus `note:section-updated` 事件，附注模块变更时自动更新本地 textarea
    - item_id 格式 `D1-disc-{variant}-note-{sectionKey}`
    - 冲突解决：last-write-wins + tooltip 显示最近更新者和时间
    - _Requirements: 17b.1, 17b.2, 17b.3, 17b.4, 17b.5, 17b.6, 17b.7_

- [ ] 9.6 实现联动跳转
  - [ ] 9.6.1 在 D1TabDisclosure.vue 中添加 GtIndexChip 跳转
    - 跨sheet取数区：GtIndexChip 跳转审定表D1-1 Tab
    - 坏账分类子节：GtIndexChip 跳转坏账准备D1-4 Tab
    - 坏账变动子节：GtIndexChip 跳转坏账准备D1-4 Tab
    - 组件顶部："查看附注全文"按钮跳转附注模块
    - EventBus 发布 'disclosure:updated' 事件
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_

- [ ] 9.7 实现行类型标识与导入规则
  - [ ] 9.7.1 确保所有子节 row 数据包含 rowType 字段
    - fixed 行左侧显示锁定图标
    - dynamic 行左侧显示删除按钮
    - summary 行不可编辑（底部固定）
    - 导入时按规则识别行类型（银行/商业→fixed，合计→summary，其余→dynamic）
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5_

- [ ] 10. 实现后端导入导出
  - [ ] 10.1 创建 `backend/app/routers/wp_render_strategies/_d1_disclosure_export.py`（~150行）
    - 实现 `POST /api/workpapers/{wp_id}/d1/disclosure/export-template?variant=listed`
    - 实现 `POST /api/workpapers/{wp_id}/d1/disclosure/export-data?variant=listed`
    - 实现 `POST /api/workpapers/{wp_id}/d1/disclosure/import-data?variant=listed`
    - 使用 openpyxl 生成/解析 xlsx
    - 格式校验：列名不匹配时返回 400 + 错误列名列表
    - 注册路由到 router_registry
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [ ] 10.2 在 D1TabDisclosure.vue 中实现导入导出 UI
    - "导出模板"按钮 → 调用 export-template → 下载 xlsx
    - "导出数据"按钮 → 调用 export-data → 下载 xlsx
    - "导入数据" el-upload → 调用 import-data → ElMessage.success 摘要
    - 导入错误时 ElMessage.error 展示不匹配列名
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [ ] 11. 实现持久化与自动保存
  - [ ] 11.1 确保 useD1Disclosure 的持久化逻辑完整
    - 验证 item_id 命名规范（D1-disc-listed-/D1-disc-soe- 前缀）
    - 验证 debounce 2秒自动保存（编辑金额/文本后）
    - 验证选择类字段立即保存
    - 验证动态行 JSON 序列化存储于 remark 字段
    - 验证跨sheet数据 computed 自动刷新（无 API 调用延迟）
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 11.3_

- [ ] 12. Checkpoint - 全功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. 回归测试
  - [ ] 13.1 运行现有 D1 测试套件确保无回归
    - `rtk python -m pytest backend/tests/ -k d1 -v --tb=short`
    - `rtk npx vitest run --reporter=verbose`（D1 相关测试文件）
    - 确认现有 D1 测试全绿
    - 如有失败，修复后重跑直至全绿

- [ ] 14. Final checkpoint - 全部功能验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 每个 Property 对应 design.md 中的一个 correctness property
- 复用 Spec 1（d1-adjudication-table）的 useD1FormulaEngine.ts 公式函数
- 坏账分类子节最复杂（6.5），包含8个 el-table（期末/上年 × 分类总表/单项/银行组合/商业组合）
- 上市版和国企版通过 variant 控制显示逻辑，不拆分为两个独立组件
- 所有 PBT 使用 fast-check，numRuns: 100
- 后端导入导出复用 Spec 1 的 openpyxl 模式
