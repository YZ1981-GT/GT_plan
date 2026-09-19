# Implementation Plan: D1 ECL坏账准备专属组件

## Overview

从 `useD1NotesReceivable.ts`（1237行）拆出D1-14/D1-15坏账准备相关逻辑为2个独立子组件+2个独立composable。D1-14为段落式左右分栏政策检查（5 section），D1-15为8列测算表×2 section（组合+单项）。公式简单：D=B×C / F=E-D / SUM合计。实现语言：TypeScript + Vue 3。

## Tasks

- [x] 1. 实现纯函数与类型定义
  - [x] 1.1 创建 `composables/useD1EclCalc.ts` 导出纯函数和类型
    - 定义 `EclRow` 接口（id/debtor/balance/lossRate/shouldProvision/actualProvision/difference/basis/indexRef）
    - 定义 `SumRow` 接口（balance/shouldProvision/actualProvision/difference）
    - 实现 `calculateShouldProvision(balance, lossRate)`: balance × lossRate
    - 实现 `calculateDifference(actualProvision, shouldProvision)`: actualProvision - shouldProvision
    - 实现 `calculateSumRow(rows: EclRow[])`: 各字段 reduce 求和
    - 实现 `calculateGrandTotal(portfolioSum, individualSum)`: 两SumRow逐字段相加
    - 实现 `checkExceedsMateriality(totalDifference, materiality)`: materiality>0 AND |diff|>materiality
    - 实现 `clampLossRate(value)`: Math.max(0, Math.min(1, value))
    - 实现 `formatAmountDisplay(amount, fmtAmount)`: 负数→括号/零→"-"/正数→fmtAmount
    - 实现 `serializeRows(rows)`/`deserializeRows(json)`: JSON持久化（computed字段hydrate时重算）
    - _Requirements: 6.4, 6.5, 6.6, 7.4, 7.5, 7.7, 8.3, 14.6, 15.2, 16.1, 16.2, 12.5, 12.6_

  - [x]* 1.2 编写 Property 1 PBT：D=B×C 应计提公式
    - **Property 1: D=B×C 应计提公式正确性**
    - 生成器：`fc.float({min:-1e8, max:1e8, noNaN:true})` × balance + `fc.float({min:0, max:1, noNaN:true})` × lossRate
    - 断言：calculateShouldProvision(balance, lossRate) === balance × lossRate（容差1e-10）
    - **Validates: Requirements 6.4, 7.4**

  - [x]* 1.3 编写 Property 2 PBT：F=E-D 差异公式
    - **Property 2: F=E-D 差异公式正确性**
    - 生成器：`fc.float({min:-1e8, max:1e8, noNaN:true})` × actualProvision + shouldProvision
    - 断言：calculateDifference(actual, should) === actual - should
    - **Validates: Requirements 6.5, 7.4**

  - [x]* 1.4 编写 Property 3 PBT：SUM合计行+grandTotal不变量
    - **Property 3: SUM合计行不变量**
    - 生成器：`fc.array(eclRowArbitrary(), {minLength:0, maxLength:10})` × 2（portfolio + individual）
    - 断言：portfolioSumRow各字段 === Σ(row.field)；grandTotal === portfolioSum + individualSum 逐字段
    - **Validates: Requirements 6.6, 7.5, 7.7**

  - [x]* 1.5 编写 Property 4 PBT：exceedsMateriality判断
    - **Property 4: 重要性判断公式正确性**
    - 生成器：`fc.float({min:-1e9, max:1e9, noNaN:true})` totalDiff + `fc.float({min:-100, max:1e9, noNaN:true})` materiality
    - 断言：checkExceedsMateriality(diff, mat) === (mat>0 AND |diff|>mat)
    - **Validates: Requirements 8.3**

  - [x]* 1.6 编写 Property 5 PBT：动态行增删计数
    - **Property 5: 动态行增删计数不变量**
    - 生成器：`fc.integer({min:0, max:20})` initialLength + operations序列
    - 断言：addRow→N+1；removeRow(valid i)→N-1；removeRow(invalid)→不变
    - **Validates: Requirements 6.3, 7.3**

  - [x]* 1.7 编写 Property 6 PBT：clampLossRate [0,1]
    - **Property 6: 损失率clamp [0,1]不变量**
    - 生成器：`fc.float({min:-10, max:10, noNaN:true})`
    - 断言：result∈[0,1]；v∈[0,1]→result===v；v<0→0；v>1→1
    - **Validates: Requirements 16.1, 16.2**

  - [x]* 1.8 编写 Property 7 PBT：JSON Round-Trip
    - **Property 7: JSON Round-Trip行数据持久化**
    - 生成器：自定义EclRow[]生成器（debtor:fc.string / balance:fc.float / lossRate:fc.float({0,1}) / actualProvision:fc.float）
    - 断言：deserializeRows(serializeRows(rows))各行debtor/balance/lossRate/actualProvision/basis/indexRef等价，shouldProvision/difference重算一致
    - **Validates: Requirements 12.5, 12.6**

  - [x]* 1.9 编写 Property 8 PBT：负数金额括号格式
    - **Property 8: 负数金额括号格式**
    - 生成器：`fc.float({min:-1e9, max:-0.01, noNaN:true})`
    - 断言：formatAmountDisplay(amount, fmtAmount) 包含'('和')'，不包含'-'
    - **Validates: Requirements 15.2**

- [x] 2. Checkpoint - 纯函数与PBT验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 实现 useD1PolicyCheck.ts composable (~200行)
  - [x] 3.1 创建 `composables/useD1PolicyCheck.ts`
    - 定义 `UseD1PolicyCheckOptions` 接口（allResponses/wpId/projectId/saveImmediate/debouncedSave/isReadonly）
    - 定义 `PolicyConclusion`/`PolicyChangeFlag` 类型
    - 实现 Section 2 政策概述：policyOverviewLeft(Ref) / policyOverviewRight(Ref) / savePolicyOverview(debounce)
    - 实现 Section 3 ECL模型：eclModelPortfolio/eclModelIndividual/eclModelMigration(3个textarea Ref) + eclModelRight(Ref) + saveEclModel(debounce)
    - 实现 Section 4 政策变更：policyChangeFlag(Ref) / policyChangeContent/policyChangeReason(Ref) / showPolicyChangeDetails(computed: flag==='是') / setPolicyChangeFlag(立即保存)
    - 实现 Section 5 审计结论：policyConclusion(Ref) / conclusionText(Ref) / setPolicyConclusion(立即保存) / saveConclusionText(debounce)
    - 实现 hydrate()：从allResponses读取各item_id初始化状态
    - 实现 isLoading ref
    - item_id命名：D1-policy-overview-* / D1-policy-ecl-* / D1-policy-change-* / D1-policy-conclusion
    - 写出跨Spec数据：D1-policy-conclusion(conclusion字段=合理性评价)
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 10.3, 12.1, 12.3, 12.4, 14.3, 14.4_

- [x] 4. 实现 useD1EclCalc.ts composable (~300行)
  - [x] 4.1 创建 `composables/useD1EclCalc.ts` composable主体
    - 定义 `UseD1EclCalcOptions` 接口（allResponses/wpId/projectId/saveImmediate/debouncedSave/isReadonly）
    - 实现 portfolioRows: Ref<EclRow[]>（预设5行空行）
    - 实现 individualRows: Ref<EclRow[]>（预设3行空行）
    - 实现 addPortfolioRow() / removePortfolioRow(index) / addIndividualRow() / removeIndividualRow(index)
    - 实现行编辑时自动重算：shouldProvision=balance×lossRate / difference=actualProvision-shouldProvision
    - 实现 lossRate输入clamp[0,1] + 输入超范围黄色边框1.5s
    - 实现 portfolioSumRow: ComputedRef<SumRow>（调用calculateSumRow）
    - 实现 individualSumRow: ComputedRef<SumRow>（调用calculateSumRow）
    - 实现 grandTotalRow: ComputedRef<SumRow>（调用calculateGrandTotal）
    - 实现 materialityThreshold: ComputedRef<number>（从allResponses读取含materiality前缀的item）
    - 实现 exceedsMateriality: ComputedRef<boolean>（调用checkExceedsMateriality）
    - 实现 auditNote/auditConclusion: Ref<string> + saveAuditNote/saveAuditConclusion(debounce)
    - 实现 hydrate()：从allResponses读取D1-ecl-portfolio-rows/D1-ecl-individual-rows JSON反序列化
    - 实现 isLoading ref
    - 实现跨Spec写出：grandTotalRow变更时debounce写D1-ecl-total-should-provision / D1-ecl-total-actual-provision / D1-ecl-total-difference
    - 实现 exportTemplate/exportData/importData 存根（调用后端端点）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.1, 9.2, 9.3, 9.4, 9.5, 10.1, 10.2, 10.4, 10.5, 12.2, 12.3, 12.4, 12.5, 12.6, 14.6, 15.1, 15.2, 15.3, 15.4, 15.5, 15.7, 16.1, 16.2, 16.3, 16.4_

- [x] 5. Checkpoint - 两个composable逻辑验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 实现 D1TabPolicyCheck.vue 组件 (~350行)
  - [x] 6.1 创建 `d1/D1TabPolicyCheck.vue`
    - Props: wpId/projectId/allResponses/isReadonly/displayPrefs
    - 使用 useD1PolicyCheck composable
    - 顶部 el-segmented 双模式切换（"结构化视图" | "在线编辑"）
    - el-skeleton v-if="isLoading" 加载占位
    - Section 1 底稿抬头：致同/应收票据坏账准备/entity_name/period_end/index_no/page_no + 审计目标el-alert(info, 全宽只读)
    - Section 2 政策概述 左右分栏：el-row :gutter=16 → el-col(:lg=14 :md=12)左侧浅灰底4个textarea + el-col(:lg=10 :md=12)右侧审计师核查意见textarea，已填写蓝色左边线
    - Section 3 ECL模型描述 左右分栏：左侧3个textarea(组合评估方法/单项评估标准/迁徙率法参数) + 右侧核查意见textarea
    - Section 4 政策变更：el-radio-group(是/否) + v-if展开textarea(变更内容B38 + 变更原因B39) / v-else灰色"本期无政策变更"
    - Section 5 审计结论：el-radio-group(合理/基本合理但需关注/不合理) + textarea + 🤖AI按钮 + 💬复核对话按钮 + `<details>`编制提示折叠区
    - inject openReviewDialog 集成💬复核对话入口
    - GtOnlyOfficeSheet v-if="isOOMode" 降级模式
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 11.1, 11.2, 11.3, 11.4, 11.5, 15.6_

- [x] 7. 实现 D1TabEclCalc.vue 组件 (~300行)
  - [x] 7.1 创建 `d1/D1TabEclCalc.vue`
    - Props: wpId/projectId/allResponses/isReadonly/displayPrefs
    - 使用 useD1EclCalc composable
    - 顶部 el-segmented 双模式切换 + 导入导出工具栏（导出模板/导出数据/导入数据）
    - el-skeleton v-if="isLoading" 加载占位
    - Section 1 按组合计提：el-divider标题 + el-table(:data=portfolioRows, border) 8列
      - A:债务人名称(el-input) B:审定余额(数字+fmtAmount,右对齐) C:预期信用损失率(百分比,居中) D:应计提(只读灰色,右对齐) E:账面余额(数字+fmtAmount,右对齐) F:差异(只读灰色,右对齐,≠0红色) G:计提依据(textarea) H:索引号(GtIndexChip)
      - 合计行(portfolioSumRow) + "添加组合"按钮
    - Section 2 按单项计提：el-divider标题 + 同结构el-table(:data=individualRows) 8列 + 合计行(individualSumRow) + "添加单项"按钮
    - 总合计行(grandTotalRow)：组合合计+单项合计
    - 差异分析卡片(el-card)：组合差异合计 | 单项差异合计 | 差异总额 | 重要性水平 | 是否超重要性
      - exceedsMateriality→红色背景⚠️"超重要性水平，建议调整" / else→绿色背景✓"未超重要性水平"
      - materialityThreshold未加载→"-"占位+黄色⚠️
    - 审计说明区域(textarea + 🤖AI + 💬复核) + 审计结论区域(textarea + 🤖AI + 💬复核)
    - `<details>` 编制提示折叠区（D=B×C含义/F=E-D差异追查/组合单项不重复/超重要性建议）
    - inject openReviewDialog
    - GtOnlyOfficeSheet v-if="isOOMode" 降级模式
    - 金额格式化：fmtAmount千分位2位小数 / 负数括号红色 / 零显示"-" / B/D/E/F右对齐 / A/G左对齐 / C居中
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.1, 9.2, 9.3, 9.4, 9.5, 11.1, 11.2, 11.3, 11.4, 11.5, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 16.1, 16.2, 16.3, 16.4_

- [x] 8. Checkpoint - 两个Vue组件渲染验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 主入口集成与代码拆分
  - [x] 9.1 修改 GtD1NotesReceivable.vue 集成两个新组件
    - 在 el-tabs 中为 D1-14/D1-15 新增 tab-pane，引用 D1TabPolicyCheck / D1TabEclCalc
    - 传递 allResponses/wpId/projectId/isReadonly/displayPrefs props
    - 替换原有 D1-14/D1-15 占位Tab内容
    - _Requirements: 14.1, 14.2, 14.5_

  - [x] 9.2 从 useD1NotesReceivable.ts 删除已拆出的ECL相关逻辑
    - 删除原 D1-14/D1-15 相关代码段
    - 确保 useD1NotesReceivable 行数缩减
    - 运行全部D1测试确认不回归
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [x] 10. 后端导入导出端点
  - [x] 10.1 扩展 `_d1_import_export.py` 添加D1-15导入导出
    - POST export-template：生成D1-15空白xlsx模板（8列表头+组合/单项两section header）
    - POST export-data：生成含当前组合+单项数据的xlsx文件
    - POST import-data：解析xlsx按section分隔符识别组合行与单项行，回写checklist_responses
    - 格式校验：列数≠8或缺少section header→400错误+不匹配列名列表
    - 导入行数>当前行数时自动扩展动态行
    - 导入完成返回摘要（"成功导入N行数据，M个字段已更新"）
    - D1-14不提供导入导出（纯段落文本无批量导入场景）
    - 注册路由到 router_registry
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

  - [x]* 10.2 编写后端导入导出集成测试（hypothesis）
    - 随机行数据→export生成xlsx buffer→import解析→验证数据等价
    - 模板格式校验：验证导出模板含8列表头+2 section header
    - 列名篡改→400响应验证
    - **Validates: Requirements 13.2, 13.3**

- [x] 11. Checkpoint - 导入导出与主入口集成验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. 回归测试与最终验证
  - [x] 12.1 运行全部D1相关测试确认无回归
    - vitest run D1相关测试文件
    - pytest backend/tests/ -k d1
    - 确认所有PBT(P1-P8)和单元测试全绿
    - _Requirements: 全部16条_

- [x] 13. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. P1 D1-15 E列从D1-4自动取数
  - [x] 14.1 在 useD1EclCalc.ts 中实现"从D1-4取数"逻辑
    - 从allResponses读取D1-adj-bad-debt-*前缀数据
    - 按组合section：按账龄段bandKey匹配→填入对应行E列
    - 按单项section：按债务人名称精确匹配→填入对应行E列
    - 填充后标记行的autoPulled=true（用于浅蓝背景显示）
    - 用户编辑E列后清除autoPulled标记
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6_

  - [x] 14.2 在 D1TabEclCalc.vue 工具栏添加"从D1-4取数"按钮
    - 按钮位于表格工具栏（导入导出按钮旁）
    - 点击→调用composable方法→E列填充+浅蓝背景
    - D1-4未填写时按钮旁黄色提示
    - _Requirements: 17.1, 17.6_

- [x] 15. P1 AI辅助生成审计说明/结论
  - [x] 15.1 启用 D1-14/D1-15 的🤖AI按钮
    - D1-14：点击→收集各section文本+核查意见+变更flag+合理性评价→调用/ai-generate
    - D1-15：点击→收集差异汇总+重要性+各行最大差异→调用/ai-generate
    - 复用a171/ai-generate模式（CPA system prompt + 编制提示注入）
    - AI不可用时disabled + tooltip
    - 生成结果→确认弹窗→填入textarea
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 8 Properties对应design.md中的correctness properties: P1(D=B×C) P2(F=E-D) P3(SUM+grandTotal) P4(exceedsMateriality) P5(addRemoveRows) P6(clampLossRate) P7(JSONRoundTrip) P8(negativeBrackets)
- 架构：2 Vue组件(D1TabPolicyCheck.vue ~350行 + D1TabEclCalc.vue ~300行) + 2 composables(useD1PolicyCheck.ts ~200行 + useD1EclCalc.ts ~300行)
- 纯函数从 useD1EclCalc.ts 导出，方便PBT测试
- D1-14段落式左右分栏（d-form-paragraph），无动态表格
- D1-15为8列测算表×2 section（按组合计提+按单项计提），公式D=B×C / F=E-D / SUM合计
- 跨Spec数据通过同一allResponses Map computed读取（重要性水平B15 / 审定表D1-adj-*），纯响应式无EventBus
- 跨Spec写出通过debounce saveImmediate回调
- 所有PBT使用fast-check，numRuns: 100
- 导入导出仅D1-15提供（D1-14纯段落无批量场景）
- JSON序列化只存用户输入字段（shouldProvision/difference为hydrate时重算）
