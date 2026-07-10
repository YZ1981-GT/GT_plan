# Implementation Plan: D1 监盘核查组专属组件

## Overview

将 `useD1NotesReceivable.ts`（1237行）中监盘核查相关的 D1-10/D1-11/D1-12/D1-13 四个sheet拆分为 **4个独立Vue组件 + 4个独立composable**。每个sheet一个组件+一个composable（每文件200-400行），全部做HTML精美组件（el-table + 金额格式化 + 动态行 + 公式自动计算），OnlyOffice仅作降级模式。TypeScript + Vue 3 Composition API + Element Plus。

## Tasks

- [x] 1. 纯函数与共享类型定义
  - [x] 1.1 创建共享类型与纯函数文件
    - 在 `composables/d1InspectionFormulas.ts` 中定义所有共享类型接口（InventoryCountRow 15列、RelatedPartyRow 13列、PledgeRow 16列、VouchingRow 13列、ExceptionSummaryRow、SamplePopulation、SpecificSampleRow）
    - 实现纯函数 `computeClosingBalance(c, d, e)` → c + d - e
    - 实现纯函数 `computeBookValue(f, g)` → f - g
    - 实现纯函数 `sumColumn<T>(rows, field)` → reduce sum
    - 实现纯函数 `computePledgeRatio(pledgeTotal, adjBookValue)` → null守卫
    - 实现纯函数 `computeExceptionRate(exceptionAmount, totalCheckedAmount)` → 0守卫
    - 实现纯函数 `formatNegativeAmount(value)` → 负数括号格式
    - 导出常量 NOTE_TYPE_OPTIONS / NOTE_STATUS_OPTIONS / RELATIONSHIP_OPTIONS / EXISTENCE_OPTIONS / ACCURACY_OPTIONS / APPROPRIATENESS_OPTIONS / TEST_CONCLUSION_OPTIONS / DIFFERENCE_OPTIONS
    - _Requirements: 4.4, 4.5, 8.1, 8.3, 12.4, 18.2_

  - [x]* 1.2 编写 Property 1 PBT：D1-11 期末余额公式 F=C+D-E
    - **Property 1: D1-11 期末余额公式 F=C+D-E**
    - 生成器：`fc.float({min:-1e8, max:1e8, noNaN:true})` × 3 (c, d, e)
    - 断言：`computeClosingBalance(c, d, e)` toBeCloseTo `c + d - e`
    - **Validates: Requirements 4.4**

  - [x]* 1.3 编写 Property 2 PBT：D1-11 账面价值公式 H=F-G
    - **Property 2: D1-11 账面价值公式 H=F-G**
    - 生成器：`fc.float({min:-1e8, max:1e8, noNaN:true})` × 2 (f, g)
    - 断言：`computeBookValue(f, g)` toBeCloseTo `f - g`
    - **Validates: Requirements 4.5**

  - [x]* 1.4 编写 Property 3 PBT：SUM合计行正确性
    - **Property 3: SUM合计行正确性**
    - 生成器：`fc.array(fc.record({amount: fc.float({min:-1e6, max:1e6, noNaN:true})}), {minLength:0, maxLength:30})`
    - 断言：`sumColumn(rows, 'amount')` === `rows.reduce((s,r) => s + (Number(r.amount)||0), 0)`
    - **Validates: Requirements 2.1, 5.1, 8.1, 12.1, 12.2**

  - [x]* 1.5 编写 Property 4 PBT：D1-12 质押比例计算与零值守卫
    - **Property 4: D1-12 质押比例计算与零值守卫**
    - 生成器：`fc.float({min:0, max:1e9})` pledgeTotal + `fc.option(fc.float({min:-1e6, max:1e9}))` adjBookValue
    - 断言：adjBookValue==null||===0 时返回 null；否则返回 pledgeTotal/adjBookValue；结果>0.5时isPledgeWarning=true
    - **Validates: Requirements 8.3, 8.4**

  - [x]* 1.6 编写 Property 5 PBT：D1-13 例外占比公式
    - **Property 5: D1-13 例外占比公式**
    - 生成器：`fc.float({min:0, max:1e8, noNaN:true})` × 2 (exceptionAmount, totalCheckedAmount)
    - 断言：totalCheckedAmount===0 时返回 0；否则返回 exceptionAmount/totalCheckedAmount
    - **Validates: Requirements 12.4**

  - [x]* 1.7 编写 Property 7 PBT：负数金额括号格式
    - **Property 7: 负数金额括号格式**
    - 生成器：负数 `fc.float({min:-1e9, max:-0.01, noNaN:true})`；非负 `fc.float({min:0, max:1e9, noNaN:true})`
    - 断言：负数输出包含'('和')'且不含'-'；非负数不产生括号格式
    - **Validates: Requirements 18.2**

- [x] 2. Checkpoint - 纯函数与PBT验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 实现 useD1InventoryCount.ts（D1-10 监盘表composable ~300行）
  - [x] 3.1 创建 `composables/useD1InventoryCount.ts` 核心逻辑
    - 定义 UseD1InventoryCountOptions 接口（allResponses/wpId/projectId/saveImmediate/saveDebouncedText/isReadonly）
    - 从 allResponses 读取 "D1-inventory-rows" JSON → 解析为 InventoryCountRow[]
    - 实现 `rows` computed + `addRow()`/`removeRow(id)`/`updateRow(id, field, value)` 动态行CRUD
    - 实现 `sumAmount` computed（H21 = SUM rows.amount）
    - 实现核对区：从 allResponses 读取 D1-adj-*-current-audited（跨Spec账面余额）→ `bookBalance` computed
    - 实现 `bookBalanceLoaded` computed（判断跨Spec数据是否存在）
    - 实现 `differenceAmount` computed（= sumAmount - bookBalance）
    - 实现 `hasDifference` computed（differenceAmount !== 0）
    - 实现 `reconArea` computed（聚合核对区全字段）
    - 实现审计说明/结论 Ref + debounce保存
    - 实现 exportTemplate/exportData/importData 导入导出接口
    - 金额字段 debounce 2s 保存；select类字段立即保存
    - _Requirements: 1.1-1.6, 2.1-2.5, 3.1-3.5, 15.1, 15.5, 15.7_

  - [x]* 3.2 编写 Property 6 PBT：动态行增删计数不变量（D1-10）
    - **Property 6: 动态行增删计数不变量**
    - 生成器：`fc.array(InventoryCountRowArbitrary, {minLength:0, maxLength:20})` + `fc.nat()`
    - 断言：addRow后长度=N+1；removeRow(validId)后长度=N-1
    - **Validates: Requirements 1.4**

- [x] 4. 实现 useD1RelatedPartyCheck.ts（D1-11 关联方检查composable ~250行）
  - [x] 4.1 创建 `composables/useD1RelatedPartyCheck.ts` 核心逻辑
    - 定义 UseD1RelatedPartyCheckOptions 接口
    - 从 allResponses 读取 "D1-rp-rows" JSON → 解析为 RelatedPartyRow[]
    - 实现 `rows` computed + `addRow()`/`removeRow(id)`/`updateRow(id, field, value)` 动态行CRUD
    - 实现逐行公式：F列 = computeClosingBalance(C, D, E)；H列 = computeBookValue(F, G)
    - 实现 `summaryRow` computed（Row14合计：SUM C/D/E/F/G/H/K 七列）
    - 实现跨Spec核对：从 allResponses 读取 D1-adj-*-current-audited → `adjClosingBalance` computed
    - 实现 `adjDataLoaded` computed + `reconDifference` computed（合计F - 审定表期末）
    - 实现审计说明/结论 Ref + debounce保存
    - 实现 exportTemplate/exportData/importData
    - _Requirements: 4.1-4.6, 5.1-5.5, 6.1-6.5, 15.2, 15.6, 15.8_

  - [x]* 4.2 编写 Property 6 PBT：动态行增删计数不变量（D1-11）
    - **Property 6: 动态行增删计数不变量**
    - 生成器：`fc.array(RelatedPartyRowArbitrary, {minLength:0, maxLength:20})`
    - 断言：addRow后长度=N+1；removeRow(validId)后长度=N-1
    - **Validates: Requirements 4.3**

- [x] 5. 实现 useD1PledgeCheck.ts（D1-12 质押检查composable ~250行）
  - [x] 5.1 创建 `composables/useD1PledgeCheck.ts` 核心逻辑
    - 定义 UseD1PledgeCheckOptions 接口
    - 从 allResponses 读取 "D1-pledge-rows" JSON → 解析为 PledgeRow[]
    - 实现 `rows` computed + `addRow()`/`removeRow(id)`/`updateRow(id, field, value)` 动态行CRUD
    - 实现 `sumNoteAmount` computed（H18 = SUM 票据金额列）
    - 实现 `sumPledgeAmount` computed（J18 = SUM 质押金额列）
    - 实现跨Spec取数：从 allResponses 读取 D1-adj-book-value-* → `adjBookValue` computed
    - 实现 `adjDataLoaded` computed
    - 实现 `pledgeRatio` computed（= computePledgeRatio(sumPledgeAmount, adjBookValue)）
    - 实现 `pledgeRatioDisplay` computed（百分比格式或"N/A"）
    - 实现 `isPledgeWarning` computed（pledgeRatio > 0.5）
    - 实现审计说明/结论 Ref + debounce保存
    - 实现 exportTemplate/exportData/importData
    - 票据类型/号码列 fixed 定位（横向滚动时可见）
    - _Requirements: 7.1-7.6, 8.1-8.6, 9.1-9.5, 15.3, 15.6, 15.9_

  - [x]* 5.2 编写 Property 6 PBT：动态行增删计数不变量（D1-12）
    - **Property 6: 动态行增删计数不变量**
    - 生成器：`fc.array(PledgeRowArbitrary, {minLength:0, maxLength:20})`
    - 断言：addRow后长度=N+1；removeRow(validId)后长度=N-1
    - **Validates: Requirements 7.4**

- [x] 6. Checkpoint - 三个composable验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 实现 useD1SamplingVouching.ts（D1-13 抽样凭证核对composable ~350行）
  - [x] 7.1 创建 `composables/useD1SamplingVouching.ts` 核心逻辑
    - 定义 UseD1SamplingVouchingOptions 接口
    - 实现 `population` Ref<SamplePopulation>（从 allResponses 读取 D1-sampling-population-* 字段）
    - 实现 `specificSamples` computed + `addSpecificSample()`/`removeSpecificSample(id)` 特定样本动态行
    - 实现 `vouchingRows` computed + `addVouchingRow()`/`removeVouchingRow(id)`/`updateVouchingRow(id, field, value)` 凭证核对明细CRUD
    - 实现 `checkedCount` computed（G32 = COUNT已填写行）
    - 实现 `checkedAmountTotal` computed（H32 = SUM金额列）
    - 实现 `vouchingAmountTotal` computed（G45 = SUM凭证核对金额列）
    - 实现 `exceptionSummary` computed（E48-G50：三类例外笔数/金额/占比，调用 computeExceptionRate）
    - 实现 `hasExceedingException` computed（任一占比 > tolerableErrorRate）
    - 实现 `tolerableErrorRate` Ref（默认5%）
    - 实现 `testConclusion` Ref（el-select值）
    - 实现审计说明/结论 Ref + debounce保存
    - 实现 exportTemplate/exportData/importData（仅解析凭证核对明细区域行，跳过抽样定义和例外汇总）
    - _Requirements: 10.1-10.4, 11.1-11.4, 12.1-12.6, 13.1-13.5, 15.4, 15.6, 15.10_

  - [x]* 7.2 编写 Property 6 PBT：动态行增删计数不变量（D1-13 凭证核对+特定样本）
    - **Property 6: 动态行增删计数不变量**
    - 生成器：`fc.array(VouchingRowArbitrary, {minLength:0, maxLength:20})`
    - 断言：addVouchingRow后长度=N+1；removeVouchingRow(validId)后长度=N-1；addSpecificSample/removeSpecificSample同理
    - **Validates: Requirements 10.3, 11.2**

- [x] 8. Checkpoint - 四个composable全部验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 实现 D1TabInventoryCount.vue（D1-10 监盘表组件 ~400行）
  - [x] 9.1 创建 `d1/D1TabInventoryCount.vue`
    - 使用 `useD1InventoryCount` composable
    - el-segmented 双模式切换（"结构化视图" | "在线编辑"）
    - 审计目标区域（只读静态文本，rows 5-9 审计目标和程序描述）
    - el-table 15列宽表（横向滚动 max-height），嵌套分组表头：
      - "监盘日结存"二级表头（A-L 12列）：票据类型(el-select) | 票据号(el-input) | 出票日(el-date-picker) | 出票人(el-input) | 承兑人(el-input) | 金额(数字+fmtAmount) | 到期日(el-date-picker) | 前手(el-input) | 收到日期(el-date-picker) | 背书贴现日(el-date-picker) | 被背书人(el-input) | 票据状态(el-select)
      - "核查结果"二级表头（M-O 3列）：是否存在差异(el-select是/否) | 差异原因(textarea仅差异=是时可编辑) | 索引号(GtIndexChip)
    - 差异="是"的行红色背景（row-class-name）
    - "添加票据"按钮 + 动态行增删
    - 合计行（H21 sumAmount 自动计算）
    - 核对区（A25-N25）：监盘日结存合计 | 账面余额(跨sheet/-占位+⚠️) | 差异金额(≠0红色) | 差异说明(textarea) | 审计结论(el-select) | 索引号(GtIndexChip)
    - 审计说明区域（textarea + 🤖AI + 💬复核）
    - 审计结论区域（textarea + 🤖AI + 💬复核）
    - 编制提示 `<details>` 折叠（蓝色左边线+浅蓝背景，默认收起：票据监盘程序/倒推说明/差异追查）
    - 列宽：日期120px / 金额110px / 文本auto最小80px
    - 负数红色括号；零值"-"；加载中 el-skeleton
    - GtOnlyOfficeSheet v-if isOOMode
    - _Requirements: 1.1-1.6, 2.1-2.5, 3.1-3.5, 14.1-14.5, 18.1-18.3, 18.6-18.7_

- [x] 10. 实现 D1TabRelatedPartyCheck.vue（D1-11 关联方检查组件 ~350行）
  - [x] 10.1 创建 `d1/D1TabRelatedPartyCheck.vue`
    - 使用 `useD1RelatedPartyCheck` composable
    - el-segmented 双模式切换
    - 审计目标区域（只读静态文本，rows 5-8）
    - el-table 13列：A关联方名称(el-input) | B关联关系(el-select 6选项) | C期初余额(数字+fmtAmount) | D借方发生(数字+fmtAmount) | E贷方发生(数字+fmtAmount) | F期末余额(只读公式C+D-E) | G减坏账准备(数字+fmtAmount) | H账面价值(只读公式F-G) | I账龄(el-input) | J款项性质(textarea) | K期后兑现(数字+fmtAmount) | L索引号(GtIndexChip) | M备注(el-input)
    - 金额列（C/D/E/F/G/H/K）右对齐，文本列左对齐
    - "添加关联方"按钮 + 动态行增删
    - 合计行 Row14（7列SUM：C/D/E/F/G/H/K）
    - 核对区：关联方期末余额合计 vs 审定表期末余额 → 差异（≠0红色高亮；未加载"-"+⚠️）
    - 审计说明 + 审计结论 + 编制提示（CAS 36披露/公允性/期后回收）
    - 负数红色括号；零值"-"；加载中 el-skeleton
    - GtOnlyOfficeSheet v-if isOOMode
    - _Requirements: 4.1-4.6, 5.1-5.5, 6.1-6.5, 14.1-14.5, 18.1-18.3, 18.5, 18.7_

- [x] 11. 实现 D1TabPledgeCheck.vue（D1-12 质押检查组件 ~350行）
  - [x] 11.1 创建 `d1/D1TabPledgeCheck.vue`
    - 使用 `useD1PledgeCheck` composable
    - el-segmented 双模式切换
    - 审计目标区域（只读静态文本，rows 5-8）
    - el-table 16列宽表（横向滚动），嵌套分组表头：
      - "票据基本信息"二级表头（A-I 9列）：票据类型(el-select) | 票据号码(el-input) | 收到日期(el-date-picker) | 前手(el-input) | 出票日(el-date-picker) | 出票人(el-input) | 承兑人(el-input) | 票据金额(数字+fmtAmount) | 到期日(el-date-picker)
      - "质押详情"二级表头（J-P 7列）：质押金额(数字+fmtAmount) | 质权人(el-input) | 质押原因(el-input) | 质押条件(el-input) | 质押期限(el-date-picker range) | 质押协议(el-input) | 索引号(GtIndexChip)
    - 票据类型+号码列 fixed 定位（横向滚动可见）
    - 金额列（票据金额/质押金额）右对齐，文本列左对齐
    - "添加质押票据"按钮 + 动态行增删
    - 合计行 Row18（H18票据金额合计 | J18质押金额合计）
    - 质押汇总区：H18 | J18 | 审定表净值(跨Spec/-+⚠️) | 质押比例(%格式或N/A)
    - 质押比例>50%：橙色预警标签（"⚠️ 质押比例超过50%，请关注受限资产披露"）
    - 审计说明 + 审计结论 + 编制提示（CAS 36第六十六条/合法性/持续经营/期限匹配）
    - 负数红色括号；零值"-"；加载中 el-skeleton
    - GtOnlyOfficeSheet v-if isOOMode
    - _Requirements: 7.1-7.6, 8.1-8.6, 9.1-9.5, 14.1-14.5, 18.1-18.5, 18.7_

- [x] 12. 实现 D1TabSamplingVouching.vue（D1-13 抽样凭证核对组件 ~400行）
  - [x] 12.1 创建 `d1/D1TabSamplingVouching.vue`
    - 使用 `useD1SamplingVouching` composable
    - el-segmented 双模式切换
    - 审计目标区域（只读静态文本，rows 5-7）
    - 抽样总体定义区：抽样总体描述(textarea) | 总体笔数(数字) + 总体金额(数字+fmtAmount) | 样本量(数字) | 抽取笔数 + 索引号(GtIndexChip跳转样本计算器)
    - 特定样本区域（动态行：项目描述 | 金额 | 抽出原因）
    - 分隔线 + "凭证核对明细"标题
    - 凭证核对明细 el-table：序号(只读自动编号) | 票据类型(el-select) | 票据号码(el-input) | 出票人(el-input) | 承兑人(el-input) | 金额(数字+fmtAmount) | 到期日(el-date-picker) | 存在性验证(el-select+tooltip) | 准确性验证(el-select+tooltip) | 记录恰当性(el-select+tooltip) | 备注(el-input) | 索引号(GtIndexChip)
    - 验证结果颜色编码：已核实/金额一致/恰当=绿色；未核实/金额不一致/不恰当=红色
    - 例外项行浅红色背景
    - "添加核查项"按钮（预设行数=样本量）
    - 核对结果区（G32核查笔数 | H32核查金额合计）
    - 例外汇总区 E48-G50：存在性例外(笔数/金额/占比) | 准确性例外 | 记录恰当性例外
    - 例外占比超标：红色高亮 + "例外率超标，请考虑扩大样本量"
    - 测试结论（el-select 4选项）
    - 审计说明 + 审计结论 + 编制提示（CAS 1314/抽样方法/例外追查/推断方法）
    - 负数红色括号；零值"-"；加载中 el-skeleton
    - GtOnlyOfficeSheet v-if isOOMode
    - _Requirements: 10.1-10.4, 11.1-11.4, 12.1-12.6, 13.1-13.5, 14.1-14.5, 18.1-18.4, 18.7_

- [x] 13. Checkpoint - 四个Vue组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. 主入口集成与代码拆分
  - [x] 14.1 在 GtD1NotesReceivable.vue 中集成四个独立Tab组件
    - 在 el-tabs 中新增4个 tab-pane 分别引用 D1TabInventoryCount / D1TabRelatedPartyCheck / D1TabPledgeCheck / D1TabSamplingVouching
    - 传递 allResponses/wpId/projectId/isReadonly/displayPrefs props
    - 替换原有 D1-10/D1-11/D1-12/D1-13 占位Tab内容
    - 确保 tab 顺序对齐 account_package_registry sheets 数组
    - _Requirements: 17.1-17.8_

  - [x] 14.2 从 useD1NotesReceivable.ts 中删除已拆出的监盘核查逻辑
    - 删除原有 D1-10/D1-11/D1-12/D1-13 相关代码段
    - 保留跨Spec数据写入契约（item_id前缀隔离：D1-inventory-/D1-rp-/D1-pledge-/D1-sampling-）
    - 运行全部 D1 测试确认不回归
    - _Requirements: 17.1-17.8_

- [x] 15. 实现双模式切换（四表通用）
  - [x] 15.1 在四个Vue组件中实现 HTML ↔ OnlyOffice 双模式
    - el-segmented 控制 isOOMode 状态
    - 切换到 OO 模式：获取 onlyoffice-config → GtOnlyOfficeSheet → onDocumentReady SetVisible(false) 隐藏非当前sheet
    - 切回 HTML 模式：重新加载 checklist_responses 数据
    - OO 健康检查失败：禁用"在线编辑"+ tooltip"OnlyOffice服务不可用"
    - 保留跨sheet公式完整性（不拆分文件）
    - _Requirements: 14.1-14.5_

- [x] 16. 实现导入导出三级（四表通用）
  - [x] 16.1 实现前端导入导出功能
    - 四个composable各自的 exportTemplate/exportData/importData 实现
    - exportTemplate：生成空白xlsx（含表头+格式，无数据行）
    - exportData：生成包含当前数据的xlsx
    - importData：解析xlsx → 校验列名 → 回写 checklist_responses
    - 格式不匹配：ElMessage.error + 列出不匹配列名
    - D1-10/D1-12 行数超出时自动扩展动态行
    - D1-13 仅解析凭证核对明细区域行，跳过抽样定义和例外汇总
    - 导入完成摘要（"成功导入N行数据，M个字段已更新"）
    - _Requirements: 16.1-16.7_

  - [x]* 16.2 编写 Property 8 PBT：导入导出 Round-Trip
    - **Property 8: 导入导出 Round-Trip**
    - 生成器：自定义 InventoryCountRow[]/RelatedPartyRow[]/PledgeRow[]/VouchingRow[] 生成器
    - 断言：exportData → importData 后行数据深度相等（数值字段允许 ±0.01）
    - **Validates: Requirements 15.7, 15.8, 15.9, 15.10, 16.2, 16.3**

- [x] 17. 复核对话集成与持久化验证
  - [x] 17.1 在四个Vue组件中集成 GtReviewDialog
    - inject openReviewDialog
    - 每个组件的审计说明/结论区域放置💬固定复核对话入口按钮
    - sectionId格式：`D1-inventory-note`/`D1-inventory-conclusion`/`D1-rp-note`/`D1-rp-conclusion`/`D1-pledge-note`/`D1-pledge-conclusion`/`D1-sampling-note`/`D1-sampling-conclusion`
    - _Requirements: 3.5, 6.5, 9.5, 13.5_

  - [x] 17.2 验证持久化与自动保存
    - 金额/文本/日期字段编辑后2s无操作触发debounce自动保存
    - 下拉选择类字段切换立即保存
    - 四表 item_id 前缀隔离正确（D1-inventory-/D1-rp-/D1-pledge-/D1-sampling-）
    - JSON数组格式存储于 remark 字段
    - _Requirements: 15.1-15.10_

- [x] 18. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 19. P0共享基础设施抽取
  - [x] 19.1 创建 `composables/d1SharedFormulas.ts`（~80行）
    - 导出共享纯函数：parseNum/sumColumn/computeClosingBalance/computeBookValue/computePledgeRatio/computeExceptionRate/formatNegativeAmount
    - 所有四个composable(useD1InventoryCount/useD1RelatedPartyCheck/useD1PledgeCheck/useD1SamplingVouching)改为从d1SharedFormulas导入，删除各自的重复实现
    - _Requirements: 20.1_

  - [x] 19.2 创建 `composables/useD1ImportExport.ts`（~150行）
    - 通用导入导出composable：接收(columnDefs/rowsRef/sheetName/wpId)参数
    - 提供 exportTemplate()/exportData()/importData(file) 方法
    - 四个composable改为调用 useD1ImportExport 而非各自实现
    - _Requirements: 20.2_

  - [x] 19.3 创建 `composables/useD1DualMode.ts`（~80行）
    - 通用双模式切换composable：接收(wpId/sheetName)参数
    - 提供 viewMode/isOOMode/ooHealthy/checkOOHealth/switchMode 方法
    - 四个Vue组件改为使用 useD1DualMode
    - _Requirements: 20.3_

  - [x] 19.4 创建 `d1/D1AuditNoteSection.vue`（~100行）
    - 通用审计说明/结论子组件：props(sectionId/noteText/conclusionText/guidanceHtml)
    - 内置 🤖AI按钮(disabled) + 💬复核对话入口(inject openReviewDialog) + 编制提示折叠
    - emit(update:note/update:conclusion)
    - 四个Vue组件的审计说明/结论区域改为使用此子组件
    - _Requirements: 20.4_

- [x] 20. P1 D1-12从备查簿D1-7自动导入已质押票据
  - [x] 20.1 在 useD1PledgeCheck.ts 中实现"从备查簿导入"逻辑
    - 从allResponses读取D1-memo-rows JSON → 筛选"是否质押=是"的行
    - 映射到PledgeRow的A-I列（9列票据基本信息），J-P留空
    - 返回映射结果供Vue组件调用
    - _Requirements: 19.1, 19.2, 19.3_

  - [x] 20.2 在 D1TabPledgeCheck.vue 中添加"从备查簿导入"按钮和交互
    - 在"添加质押票据"按钮旁增加"从备查簿导入已质押票据"按钮
    - 点击→确认弹窗→调用composable方法→新增行→ElMessage.success摘要
    - 备查簿无已质押票据时 ElMessage.info 提示
    - _Requirements: 19.4, 19.5, 19.6_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 架构：4个独立Vue组件 + 4个独立composable，每文件200-400行
- 文件清单：useD1InventoryCount.ts / D1TabInventoryCount.vue (D1-10) | useD1RelatedPartyCheck.ts / D1TabRelatedPartyCheck.vue (D1-11) | useD1PledgeCheck.ts / D1TabPledgeCheck.vue (D1-12) | useD1SamplingVouching.ts / D1TabSamplingVouching.vue (D1-13)
- 8个Properties：P1(F=C+D-E) P2(H=F-G) P3(SUM) P4(pledgeRatio) P5(exceptionRate) P6(addRemove) P7(negativeBrackets) P8(importExportRT)
- P6动态行增删在四个composable中分别测试（3.2/4.2/5.2/7.2），覆盖所有动态行场景
- 所有PBT使用 fast-check，numRuns: 100
- 跨Spec数据依赖：D1-adj-* (d1-adjudication-table) / D1-memo-rows (d1-endorsement-discount)
- 双模式：OO打开完整xlsx + SetVisible(false)隐藏非当前sheet，不拆分文件
- 导入导出：openpyxl 生成/解析xlsx，前端调后端端点
