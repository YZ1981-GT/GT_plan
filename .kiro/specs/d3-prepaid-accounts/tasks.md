# Implementation Plan: D3 预收账款底稿专属HTML精美组件

## Overview

实现D3预收账款底稿专属组件`d3-prepaid-accounts`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端(导入导出+resolver+AI+render策略)→双模式→期后结转联动→集成测试。主入口GtD3PrepaidAccounts.vue + 9个子组件 + 12个composable + 后端4个py文件。

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将D3/D3-1/D3-2映射为'd3-prepaid-accounts'
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'd3-prepaid-accounts'
    - 在 `htmlRendererRegistry.ts` 中注册 'd3-prepaid-accounts' → GtD3PrepaidAccounts 映射
    - 创建 `GtD3PrepaidAccounts.vue` 主入口骨架（el-tabs 9个tab-pane + selfLoad逻辑）
    - _Requirements: 20.1, 20.5, 20.6, 20.7, 20.8_

  - [x] 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'd3-prepaid-accounts'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证D3/D3-1/D3-2映射
    - _Requirements: 20.5, 20.6, 20.7_

- [x] 2. 实现共享公式引擎 useD3FormulaEngine.ts
  - [x] 2.1 创建 `composables/useD3FormulaEngine.ts`，实现全部纯函数
    - 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN/Infinity → 0）
    - 实现 `calcAuditedAmount`（审定数 = 未审 + AJE + RJE）
    - 实现 `calcChangeAmount`（变动额 = 期末 - 期初）
    - 实现 `calcChangeRate`（变动率，含期初=0特殊处理：0/0→'', 0/非0→'N/A'）
    - 实现 `calcSubtotal`（合计 = SUM数组）
    - 实现 `calcPriorAudited`（期初审定 = 未审 + 调整 + 重分类）
    - 实现 `calcEndBalance`（贷方科目期末 = 期初审定 + 贷方 - 借方）
    - 实现 `calcEndUnadjusted`（期末未审 = 期末余额 + 被审单位重分类）
    - 实现 `calcEndAudited`（期末审定 = 期末未审 + AJE + RJE）
    - 实现 `calcRelatedPartyEndBalance`（关联方期末 = 期初 + 贷方 - 借方）
    - 实现 `isChangeRateExceeding`（阈值判定）
    - 实现 `calcAnomalyRate`（异常率 = 异常/总数 × 100%）
    - 实现 `aggregateByNature`（按款项性质分组SUM）
    - 实现 `aggregateByAging`（按审定账龄聚合）
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 4.4, 10.3, 11.5_

  - [x]* 2.2 编写 Property 1 PBT：审定数公式正确性
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 3
    - 断言：calcAuditedAmount(u, a, r) === u + a + r
    - **Feature: d3-prepaid-accounts, Property 1: 审定数公式正确性**

  - [x]* 2.3 编写 Property 2 PBT：变动额与变动率
    - 生成器：`fc.float` × 2 (含0边界策略)
    - 断言：changeAmount === current - prior; changeRate特殊处理验证
    - **Feature: d3-prepaid-accounts, Property 2: 变动额与变动率公式正确性**

  - [x]* 2.4 编写 Property 3 PBT：合计行
    - 生成器：`fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:30})`
    - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
    - **Feature: d3-prepaid-accounts, Property 3: 合计行恒等于明细行之和**

  - [x]* 2.5 编写 Property 4 PBT：阈值判定
    - 生成器：`fc.float({min:-10, max:10})`
    - 断言：isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)
    - **Feature: d3-prepaid-accounts, Property 4: 变动率阈值高亮判定**

  - [x]* 2.6 编写 Property 16 PBT：差异行
    - 生成器：`fc.float` × 2
    - 断言：diff === total - tbAmount
    - **Feature: d3-prepaid-accounts, Property 16: 差异行计算正确性**

- [x] 3. 实现 useD3FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useD3FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate（PUT单条response）
    - 实现 debouncedSave（2秒debounce版本）
    - 实现 saveBatch（批量保存）
    - 实现 writebackTrialBalance（回写科目2203）
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=d3-prepaid-accounts）
    - _Requirements: 17.1-17.11, 22.1_

- [ ] 4. Checkpoint - 公式引擎与基础设施验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 实现 useD3CrossSheet.ts 跨Sheet联动
  - [x] 5.1 创建 `composables/useD3CrossSheet.ts`
    - 实现 natureAggregation computed（按款项性质聚合D3-2 endAudited/priorAudited）
    - 实现 agingAggregation computed（按审定账龄U~X列聚合）
    - 实现 longTermRows computed（筛选账龄>1年行）
    - 实现 relatedPartyRows computed（筛选关联方类型≠非关联方）
    - 实现 adjustmentTotals computed（从D3-3行汇总AJE/RJE）
    - 实现 adjudicationForDisclosure computed（审定表数据供附注引用）
    - _Requirements: 2.1, 2.2, 9.2, 10.4, 12.2, 12.3, 13.2, 13.3_

  - [x]* 5.2 编写 Property 6 PBT：按性质聚合
    - 生成器：自定义 DetailRow[] 生成器（nature随机从4种取）
    - 断言：各性质组sum === 手动filter+reduce结果
    - **Feature: d3-prepaid-accounts, Property 6: 按款项性质聚合正确性**

  - [x]* 5.3 编写 Property 7 PBT：按账龄聚合
    - 生成器：自定义 DetailRow[] 生成器（agingAudited随机）
    - 断言：within1/y1to2/y2to3/over3各项sum正确
    - **Feature: d3-prepaid-accounts, Property 7: 按审定账龄聚合正确性**

  - [x]* 5.4 编写 Property 8 PBT：交叉验证
    - 生成器：自定义 DetailRow[] 生成器
    - 断言：natureAggregation各项之和 === agingAggregation各项之和 === SUM(endAudited)
    - **Feature: d3-prepaid-accounts, Property 8: 性质分类合计与账龄分类合计交叉验证**

  - [x]* 5.5 编写 Property 18 PBT：筛选导入
    - 生成器：自定义 DetailRow[] + relationType/aging随机
    - 断言：longTermRows恰好包含y1to2+y2to3+over3>0的行；relatedPartyRows恰好包含type≠非关联方的行
    - **Feature: d3-prepaid-accounts, Property 18: D3-2筛选导入正确性**

- [x] 6. 实现 useD3Adjudication.ts 审定表D3-1
  - [x] 6.1 创建 `composables/useD3Adjudication.ts`
    - 定义双区块固定行配置（NATURE_ROWS + AGING_ROWS）
    - 实现 sections computed（从allResponses加载 + crossSheet聚合填入）
    - 实现 trialBalanceAmount（从TB auto_data取数）+ trialBalanceDiff computed
    - 实现 crossValidationDiff + crossValidationWarning computed
    - 实现 auditNotes 双向绑定（agingReason/changeAnalysis/conclusion）
    - 实现 updateCell（编辑 → 公式重算 → debouncedSave）
    - 实现 publishAdjudicated（EventBus发布，payload含2203/auditedAmount）
    - 实现 onAdjustmentCreated监听（AJE/RJE累加）
    - _Requirements: 1.1-1.8, 2.1-2.8, 3.1-3.7, 18.1

  - [x]* 6.2 编写 Property 9 PBT：AJE/RJE同步
    - 生成器：`fc.constantFrom('AJE','RJE')` + `fc.float({min:-1e9, max:1e9})`
    - 断言：事件触发后对应列值正确累加
    - **Feature: d3-prepaid-accounts, Property 9: 调整分录EventBus同步正确性**

- [x] 7. 实现 useD3Detail.ts 明细表D3-2
  - [x] 7.1 创建 `composables/useD3Detail.ts`
    - 定义 DetailRow 类型（27列完整字段）
    - 实现 rows reactive（从D3-det-rows加载JSON数组）
    - 实现行内公式自动计算（H=E+F+G, O=H+N-M, Q=O+P, T=Q+R+S）
    - 实现 subtotalRow computed + verificationRow computed（合计-TB数）
    - 实现 searchQuery + filteredRows computed（模糊搜索）
    - 实现 addRow/removeRow/updateCell
    - 实现 matchRelatedParty（从relatedParties列表包含匹配）
    - 实现 importFromAuxBalance（调后端API批量导入）
    - 实现 onConfirmationCompleted监听（标记isConfirmed='Y'）
    - _Requirements: 4.1-4.12, 5.1-5.7, 6.1-6.5, 18.4_

  - [x]* 7.2 编写 Property 5 PBT：D3-2行公式链
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 8 (E,F,G,M,N,P,R,S)
    - 断言：H=E+F+G; O=H+N-M; Q=O+P; T=Q+R+S
    - **Feature: d3-prepaid-accounts, Property 5: 明细表D3-2行内公式链正确性**

  - [x]* 7.3 编写 Property 10 PBT：动态行添加
    - 生成器：`fc.array(DetailRow生成器, {minLength:0, maxLength:20})`
    - 断言：addRow后length=N+1；新行数值全0
    - **Feature: d3-prepaid-accounts, Property 10: 动态行添加保持结构不变量**

  - [x]* 7.4 编写 Property 11 PBT：关联方匹配
    - 生成器：`fc.string({minLength:1})` + `fc.array(fc.string({minLength:1}))`
    - 断言：名称包含列表项→返回关联关系；否则→'非关联方'
    - **Feature: d3-prepaid-accounts, Property 11: 关联方自动匹配正确性**

  - [x]* 7.5 编写 Property 12 PBT：搜索过滤
    - 生成器：`fc.string` + `fc.array(DetailRow生成器)`
    - 断言：filteredRows每行customerName包含q(不敏感)；无遗漏无多余
    - **Feature: d3-prepaid-accounts, Property 12: 搜索过滤正确性**

  - [x]* 7.6 编写 Property 13 PBT：函证标记
    - 生成器：`fc.string({minLength:1})` + DetailRow[]
    - 断言：匹配行isConfirmed='Y'；不匹配行不变
    - **Feature: d3-prepaid-accounts, Property 13: 函证完成事件标记正确性**

- [x] 8. 实现 useD3Adjustment.ts 调整分录D3-3
  - [x] 8.1 创建 `composables/useD3Adjustment.ts`
    - 定义 AdjustmentRow 类型（10列）
    - 实现 rows reactive（从D3-aje-rows加载JSON）
    - 实现 debitTotal/creditTotal/isBalanced/balanceDiff computed
    - 实现 addRow/removeRow/updateCell
    - 实现 publishAdjustment（EventBus adjustment:created）
    - 实现 pushToA13（EventBus推送选中分录至A13错报汇总）
    - _Requirements: 7.1-7.7, 18.2_

  - [x]* 8.2 编写 Property 15 PBT：借贷平衡
    - 生成器：`fc.array(fc.record({debit:fc.float({min:0,max:1e9}), credit:fc.float({min:0,max:1e9})}))`
    - 断言：isBalanced === (debitTotal === creditTotal)
    - **Feature: d3-prepaid-accounts, Property 15: 调整分录借贷平衡检查**

- [ ] 9. Checkpoint - 核心composable验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. 实现 useD3Analysis.ts 分析表D3-4
  - [x] 10.1 创建 `composables/useD3Analysis.ts`
    - 定义 AnalysisSection/AnalysisRow/Top5DebtorRow 类型
    - 实现 4区块数据（借方分析/贷方分析/Top5/审计说明）
    - 实现从TB auto_data获取借方/贷方发生额总计
    - 实现差异行 = TB总计 - 分拆合计
    - 实现 top5Debtors computed（从crossSheet取D3-2按余额降序前5）
    - 实现 top5ConcentrationWarning computed（>50%时警告）
    - 实现 publishSignificantChange（变动>30%时EventBus）
    - _Requirements: 8.1-8.8, 18.3, 22.2_

  - [x]* 10.2 编写 Property 17 PBT：Top5分析
    - 生成器：自定义DetailRow[]生成器（{minLength:1, maxLength:50}）
    - 断言：top5为前5大余额降序；>50%时有警告
    - **Feature: d3-prepaid-accounts, Property 17: Top5债务人分析正确性**

- [x] 11. 实现 useD3LongTerm.ts 长期检查D3-5
  - [x] 11.1 创建 `composables/useD3LongTerm.ts`
    - 定义 LongTermRow 类型（8列）
    - 实现 rows reactive（从D3-lt-rows加载JSON）
    - 实现从crossSheet.longTermRows导入功能
    - 实现 subtotalRow computed（期末余额/结转金额SUM）
    - 实现 addRow/removeRow/updateCell
    - 实现 auditNote/conclusion 双向绑定
    - _Requirements: 9.1-9.8_

- [x] 12. 实现 useD3RelatedParty.ts 关联方D3-6
  - [x] 12.1 创建 `composables/useD3RelatedParty.ts`
    - 定义 RelatedPartyRow 类型（10列）
    - 实现 rows reactive（从D3-rp-rows加载JSON）
    - 实现从crossSheet.relatedPartyRows导入功能
    - 实现行内公式（期末=期初+贷方-借方）
    - 实现 subtotalRow computed
    - 实现 addRow/removeRow/updateCell
    - 实现 auditNote/conclusion 双向绑定
    - _Requirements: 10.1-10.9_

- [x] 13. 实现 useD3VoucherCheck.ts 凭证检查D3-7
  - [x] 13.1 创建 `composables/useD3VoucherCheck.ts`
    - 定义 VoucherCheckRow/SamplingParams 类型
    - 实现 samplingParams reactive
    - 实现 currentChangeRows（本期增减17列）+ postPeriodRows（期后结转16列）
    - 实现 totalChecked/anomalyCount/anomalyRate computed
    - 实现 addSample/removeSample/updateCell
    - 实现 autoMarkCrossPeriod（日期<收入确认日→标"跨期疑点"）
    - _Requirements: 11.1-11.9_

  - [x]* 13.2 编写 Property 19 PBT：异常率
    - 生成器：自定义VoucherRow[]生成器（isAbnormal随机赋值）
    - 断言：anomalyRate === 非空异常行数/总行数×100
    - **Feature: d3-prepaid-accounts, Property 19: 凭证检查异常率计算正确性**

  - [x]* 13.3 编写 Property 20 PBT：跨期标记
    - 生成器：`fc.date()` × 2 (voucherDate + revenueDate)
    - 断言：voucherDate < revenueDate → isAbnormal='跨期疑点'
    - **Feature: d3-prepaid-accounts, Property 20: 期后结转跨期自动标记**

- [x] 14. 实现 useD3DisclosureListed.ts + useD3DisclosureSoe.ts
  - [x] 14.1 创建附注composable
    - useD3DisclosureListed.ts：3子节（按性质/超1年/重大变动）+ 从crossSheet取数 + 动态行 + 合计 + 说明textarea + EventBus双向回写
    - useD3DisclosureSoe.ts：2子节（按账龄/超1年）+ 从crossSheet取数 + 动态行 + 合计
    - 实现 applicable_standards 适用性判断（listed/soe显示控制）
    - _Requirements: 12.1-12.8, 13.1-13.7, 14.1-14.6_

- [ ] 15. Checkpoint - 全部composable验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. 实现 D3TabAdjudication.vue 审定表
  - [x] 16.1 创建 `d3/D3TabAdjudication.vue`（~400行）
    - 双区块el-table（按性质 + 按账龄）
    - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率|原因分析
    - 合计行不可编辑 + 跨sheet浅蓝色背景 + tooltip来源
    - 变动率>30%红色高亮 + 试算表差异≠0红色
    - 交叉验证警告el-alert
    - "审计说明"区域：(1)超1年原因+GtIndexChip→D3-5 (2)变动分析textarea+🤖AI (3)CAS14提示details折叠
    - "审计结论"区域 + 💬复核入口 + 右键@cell-contextmenu
    - 金额fmtAmount + 百分比 + el-skeleton
    - _Requirements: 1.1-1.8, 2.4, 3.1-3.7, 19.1, 21.1-21.7_

- [x] 17. 实现 D3TabDetail.vue 明细表
  - [x] 17.1 创建 `d3/D3TabDetail.vue`（~400行）
    - el-table横向滚动27列，固定前2列（对方单位名称/公司代码）
    - "款项性质"下拉 + "关联方类型"下拉 + 关联方行橙色高亮
    - 自动计算列灰底不可编辑（H/O/Q/T）
    - 搜索框（表头上方）+ filteredRows
    - 超30行虚拟滚动
    - "添加客户"按钮 + 行删除 + 合计行 + 核对行
    - "从余额表导入"按钮 + 导入摘要
    - 金额右对齐 + fmtAmount + 零值"-" + 负数红色括号
    - 审计说明3条textarea + AI按钮 + 复核入口
    - _Requirements: 4.1-4.12, 5.1-5.7, 6.1-6.5, 19.2, 21.1-21.5_

- [x] 18. 实现 D3TabAdjustment.vue 调整分录
  - [x] 18.1 创建 `d3/D3TabAdjustment.vue`（~250行）
    - el-table 10列 + "新增调整分录"按钮
    - 底部借贷合计行 + 平衡指示（绿色✓/红色✗差额）
    - "推送至A13"按钮（多选行）
    - 编制提示details折叠（蓝色左边线+浅蓝背景）
    - _Requirements: 7.1-7.7_

- [x] 19. 实现 D3TabAnalysis.vue 分析表
  - [x] 19.1 创建 `d3/D3TabAnalysis.vue`（~350行）
    - 4区块卡片式布局（借方/贷方/Top5/审计说明）
    - 借方贷方：项目/金额/来源/备注 + 差异行红色高亮
    - Top5：债务人名称/期末/期初/变动金额/变动比例/账龄/原因/期后结账 + GtIndexChip→D3-2
    - >50%集中度el-alert警告
    - 审计说明textarea + 🤖AI按钮
    - _Requirements: 8.1-8.8, 19.2, 22.2_

- [x] 20. 实现 D3TabLongTerm.vue 长期检查
  - [x] 20.1 创建 `d3/D3TabLongTerm.vue`（~250行）
    - el-table 8列 + "从D3-2导入"按钮 + "添加行"按钮
    - 合计行（期末余额/结转金额SUM）
    - "未结转原因"列🤖AI建议按钮
    - GtIndexChip每行→D3-2对应客户
    - 审计说明+结论textarea + AI + 金额格式化
    - _Requirements: 9.1-9.8, 19.3_

- [x] 21. 实现 D3TabRelatedParty.vue 关联方
  - [x] 21.1 创建 `d3/D3TabRelatedParty.vue`（~250行）
    - el-table 10列 + "从D3-2导入"按钮 + "添加关联方"按钮
    - "关联关系"下拉 + 行内公式（期末=期初+贷方-借方）
    - 合计行 + GtIndexChip→D3-2 + 审计说明+结论 + 💬复核
    - _Requirements: 10.1-10.9, 19.3_

- [x] 22. 实现 D3TabVoucherCheck.vue 凭证检查
  - [x] 22.1 创建 `d3/D3TabVoucherCheck.vue`（~350行）
    - 3区域：抽样参数区 + (1)本期增减17列 + (2)期后结转16列
    - 抽样参数：测试总体/特定样本/抽样总体/方法/进度条
    - "添加样本"按钮（每区块独立）
    - 汇总：已检查/异常/异常率
    - 跨期自动标记"跨期疑点"逻辑
    - 抽凭引擎集成（GtIndexChip→voucher-sampling-engine）
    - 💬复核入口
    - _Requirements: 11.1-11.9, 19.4_

- [x] 23. 实现 D3TabDisclosureListed.vue + D3TabDisclosureSoe.vue
  - [x] 23.1 创建附注Vue组件
    - D3TabDisclosureListed.vue（~250行）：3子节卡片 + 跨sheet浅蓝取数 + 动态行 + 合计 + 说明textarea + 编制提示折叠 + GtIndexChip→D3-1
    - D3TabDisclosureSoe.vue（~200行）：2子节卡片 + 跨sheet取数 + 动态行 + 合计 + applicable_standards判断 + el-segmented切换（上市/国企）
    - _Requirements: 12.1-12.8, 13.1-13.7, 14.1-14.6, 19.5_

- [ ] 24. Checkpoint - 全部Vue组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 25. 实现后端导入导出端点
  - [x] 25.1 创建 `backend/app/routers/wp_render_strategies/_d3_import_export.py`
    - POST /api/workpapers/{wp_id}/d3/export-template?sheet=D3-2（空白xlsx模板）
    - POST /api/workpapers/{wp_id}/d3/export-data?sheet=D3-2（含数据xlsx）
    - POST /api/workpapers/{wp_id}/d3/import-data?sheet=D3-2（解析xlsx回写）
    - POST /api/workpapers/{wp_id}/d3/import-aux-balance（从tb_aux_balance科目2203按客户导入）
    - 格式校验：列名不匹配→400+错误列表
    - 行数限制：>500行截断+警告
    - 支持D3-2/D3-5/D3-6/D3-7导入导出
    - 注册路由到router_registry
    - _Requirements: 5.1-5.7, 22.3_

  - [x]* 25.2 编写 Property 14 PBT（后端hypothesis）：导入导出Round-Trip
    - 生成随机DetailRow[]→export→import→验证等价
    - 模板格式校验：随机列名→验证错误检测
    - **Feature: d3-prepaid-accounts, Property 14: 导入导出Round-Trip**

- [x] 26. 实现后端Auto Data Resolver和AI生成端点
  - [x] 26.1 创建 `backend/app/routers/wp_render_strategies/_d3_resolvers.py`
    - 注册`d3_tb_unadjusted` resolver到_REGISTRY（从trial_balance科目2203取期初/期末未审数）
    - 注册`d3_ledger_analysis` resolver到_REGISTRY（从tb_ledger科目2203取借方/贷方发生额+按对方科目分拆）
    - _Requirements: 22.1, 22.2, 25.3, 25.4_

  - [x] 26.2 创建 `backend/app/routers/wp_render_strategies/_d3_ai_generate.py`
    - POST /api/workpapers/{wp_id}/d3/ai-generate 端点
    - 支持9个section（adj-aging-reason/adj-change-analysis/adj-conclusion/detail-change/detail-contract/detail-longterm/analysis-note/longterm-reason/related-party-note）
    - 自动加载D3-1变动数据 + D3-4 Top5 + D3-5长期挂账行 + project_context作为LLM context
    - 注册到router_registry "AI与辅助"组
    - _Requirements: 3.2, 6.2, 8.7, 9.6, 10.7_

  - [x] 26.3 创建后端render策略函数和account_package_registry更新
    - 在RENDERER_DISPATCH注册'd3-prepaid-accounts'→`_render_d3_prepaid_accounts`策略函数
    - 实现`_render_d3_prepaid_accounts`返回审定表双区块配置+明细表列定义+各sheet元数据
    - 更新account_package_registry.json添加D3_prepaid_accounts工作包（含10个有效sheet定义）
    - _Requirements: 25.1, 25.2, 25.5_

- [x] 27. 实现前端导入导出UI
  - [x] 27.1 在子组件中添加导入导出工具栏
    - D3TabDetail/D3TabLongTerm/D3TabRelatedParty/D3TabVoucherCheck顶部工具栏
    - "导出模板"/"导出数据"/"导入数据" el-button-group
    - el-upload组件 + 导入摘要ElMessage.success + 错误ElMessage.error
    - _Requirements: 5.5-5.7_

- [x] 28. 实现双模式切换
  - [x] 28.1 在所有子组件中实现HTML ↔ OnlyOffice切换
    - 每个Tab页头部el-segmented（"结构化视图"|"在线编辑"）
    - 切OO：获取onlyoffice-config → GtOnlyOfficeSheet → onDocumentReady SetVisible(false)隐藏非当前sheet
    - 切回HTML：重新加载checklist_responses刷新
    - OO不可用时禁用+tooltip
    - 复用GtOnlyOfficeSheet组件和健康检查
    - _Requirements: 16.1-16.5_

- [x] 29. 集成主入口GtD3PrepaidAccounts.vue
  - [x] 29.1 完善主入口组件
    - el-tabs 9个tab-pane引用9个子组件
    - 传递allResponses/wpId/projectId/isReadonly/crossSheet等props
    - Tab顺序对齐源模板sheet顺序：D3A→D3-1→D3-2→D3-3→D3-4→D3-5→D3-6→D3-7→附注
    - 附注Tab内el-segmented切换上市/国企（根据applicable_standards）
    - provide openReviewDialog（inject模式零成本集成复核）
    - _Requirements: 20.1-20.8, 14.1-14.3_

- [x] 30. 实现D3-2期后结转与D3-7联动
  - [x] 30.1 在useD3CrossSheet中添加postPeriodSettlementSync computed
    - 从D3-7 (2)期后结转区块按客户聚合贷方金额
    - D3TabDetail中显示联动提示（当D3-7有金额但D3-2 Z列为空时黄色提示）
    - D3TabVoucherCheck中显示D3-2 Z列合计的交叉验证
    - _Requirements: 23.1-23.3_

- [ ] 31. Checkpoint - 导入导出和双模式验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 32. 回归测试与全量验证
  - [x] 32.1 运行全量测试确保无回归
    - vitest run 所有D3相关spec文件
    - python -m pytest backend/tests/ -k d3
    - 验证htmlRendererRegistry注册数量更新
    - 验证VALID_COMPONENT_TYPES含'd3-prepaid-accounts'
    - 验证wp_code_overrides D3/D3-1/D3-2映射正确
    - 验证RENDERER_DISPATCH含'd3-prepaid-accounts'策略
    - 验证auto_data_resolvers._REGISTRY含d3_tb_unadjusted和d3_ledger_analysis
    - _Requirements: all_

- [ ] 33. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional PBT tests, can be skipped for faster MVP
- 每个Property对应design.md中的一个correctness property
- 所有PBT使用fast-check（前端）或hypothesis（后端），numRuns: 100
- 贷方科目核心公式：期末余额 = 期初审定 + 贷方发生 - 借方发生（与D1/D2借方科目相反）
- 跨sheet全部通过allResponses computed链，不走API调用
- selfLoad必须支持（bundle内嵌场景htmlData为null）
- 程序表D3A复用a-program-console componentType，不需单独实现
- D3-2 Z列(期后结转)与D3-7 (2)期后结转检查区块通过crossSheet computed链双向验证（不自动覆盖用户手填值，仅提示不一致）
- AI生成端点复用B14/A17-1模式：project_context + 底稿数据snapshot + CPA system prompt
- auto_data resolver注册后，程序表D3A步骤可通过auto_data_source标识自动取数显示完成状态
