# Implementation Plan: D4 营业收入底稿专属HTML精美组件

## Overview

实现D4营业收入底稿专属组件`d4-operating-revenue`。这是平台最大的单科目底稿（42有效sheet/8 xlsx/~280+公式）。按依赖顺序：注册→公式引擎→基础设施→跨sheet→核心组(D4-1~4+附注+目录)→政策→分析程序→检查程序→关联方→IPO/舞弊(含访谈模板)→其他收入→后端→双模式→行同步+适用性→集成。

主入口 GtD4OperatingRevenue.vue（嵌套Tab 7组）+ 38个子组件 + 16个composable + 后端3个py文件。

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将D4/D4-1~D4-36/D4A映射为'd4-operating-revenue'
    - 在 `VALID_COMPONENT_TYPES` 中注册'd4-operating-revenue'
    - 在 `htmlRendererRegistry.ts` 中注册 'd4-operating-revenue' → GtD4OperatingRevenue 映射
    - 创建 `GtD4OperatingRevenue.vue` 主入口骨架（嵌套el-tabs 7一级+N二级 + selfLoad）
    - _Requirements: 1.1, 1.6, 1.7, 1.8, 1.9_

  - [x] 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 验证'd4-operating-revenue'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证D4/D4-1~D4-36映射
    - _Requirements: 1.6, 1.7, 1.8_

- [x] 2. 实现共享公式引擎 useD4FormulaEngine.ts
  - [x] 2.1 创建 `composables/useD4FormulaEngine.ts`，实现全部纯函数
    - `parseNum` / `calcAuditedAmount` / `calcMonthlyTotal` / `calcAuditedWithAdj`
    - `calcChangeRate` / `calcChangeAmount` / `calcSubtotal`
    - `calcGrossMarginRate` / `calcProportion` / `calcPriceDiffRate`
    - `isChangeRateExceeding` / `calcAnomalyRate` / `calcCoverageRate`
    - `isCrossPeriod` / `calcCrossPeriodDays` / `isSuspiciousFundFlow` / `isIpoGroupVisible`
    - _Requirements: 1.5, 2.3, 3.2, 4.2, 8.2, 11.3, 13.2, 14.1, 14.11, 25.1-25.4_

  - [x]* 2.2 编写 Property 1 PBT：损益类审定数公式链
    - 生成器：12个月fc.float + adj/prior各字段
    - 断言：N=SUM(months); P=N+O; S=Q+R; T=(N-Q)/Q; U=(P-S)/S
    - **Feature: d4-operating-revenue, Property 1: 损益类审定数公式链正确性**

  - [x]* 2.3 编写 Property 2 PBT：合计行
    - 生成器：`fc.array(fc.float({min:-1e9,max:1e9}), {minLength:1, maxLength:30})`
    - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
    - **Feature: d4-operating-revenue, Property 2: 合计行恒等于明细行之和**

  - [x]* 2.4 编写 Property 4 PBT：阈值判定
    - 生成器：`fc.float({min:-10,max:10})` + `fc.float({min:0.01,max:1})`
    - 断言：isChangeRateExceeding(r, t) === (Math.abs(r) > t)
    - **Feature: d4-operating-revenue, Property 4: 变动率阈值高亮判定**

  - [x]* 2.5 编写 Property 10 PBT：毛利率
    - 生成器：`fc.float({min:0,max:1e9})` × 2
    - 断言：calcGrossMarginRate(rev,cost) === (rev-cost)/rev (rev>0)
    - **Feature: d4-operating-revenue, Property 10: 毛利率公式正确性**

  - [x]* 2.6 编写 Property 11 PBT：关联价格差异率
    - 生成器：`fc.float({min:0.01,max:1e6})` × 2
    - 断言：calcPriceDiffRate(rp,nrp) === (rp-nrp)/nrp*100
    - **Feature: d4-operating-revenue, Property 11: 关联方价格差异率**

  - [x]* 2.7 编写 Property 13 PBT：IPO可见性
    - 生成器：`fc.string` + fc.constantFrom('ipo','listed','neeq','restructuring','fraud_risk','normal')
    - 断言：isIpoGroupVisible returns true iff contains keyword
    - **Feature: d4-operating-revenue, Property 13: IPO/舞弊组可见性控制**

  - [x]* 2.8 编写 Property 14 PBT：资金回流可疑
    - 生成器：`fc.float({min:0})` × 2 + `fc.nat({max:60})`
    - 断言：isSuspiciousFundFlow logic correct
    - **Feature: d4-operating-revenue, Property 14: 资金回流可疑判定**

  - [x]* 2.9 编写 Property 16 PBT：金额格式化
    - 生成器：`fc.float({min:-1e12,max:1e12})`
    - 断言：正数千分位/负数括号红色/零"-"
    - **Feature: d4-operating-revenue, Property 16: 金额格式化规则**

  - [x]* 2.10 编写 Property 20 PBT：占比计算
    - 生成器：`fc.float({min:0})` × 2
    - 断言：calcProportion(item,total) === item/total*100 (total>0)
    - **Feature: d4-operating-revenue, Property 20: 占比计算正确性**

- [x] 3. 实现 useD4FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useD4FormData.ts`
    - allResponses Map加载 + saveImmediate + debouncedSave(2s) + saveBatch
    - writebackTrialBalance（科目6001+6051）
    - selfLoad逻辑（render-config?force_component_type=d4-operating-revenue）
    - projectContext加载（含business_category/applicable_standards）
    - _Requirements: 1.9, 1.10, 24.1-24.6_

- [x] 4. 实现 useD4CrossSheet.ts 跨Sheet联动
  - [x] 4.1 创建 `composables/useD4CrossSheet.ts`
    - mainRevenueByProduct computed（D4-2按产品聚合）
    - otherRevenueByItem computed（D4-3按项目聚合）
    - adjustmentTotals computed（D4-4 AJE/RJE按科目分拆）
    - productRevenueForMargin computed（D4-2→D4-8）
    - customerStructureData computed（D4-2→D4-9 Top排名）
    - adjudicationForDisclosure computed（D4-1→附注）
    - ipoGroupVisible computed（从projectContext.business_category判断）
    - _Requirements: 17.1-17.9, 14.1_

  - [x]* 4.2 编写 Property 5 PBT：跨Sheet聚合
    - 生成器：自定义RevenueDetailRow[] + product枚举
    - 断言：按产品分组sum === D4-1对应行
    - **Feature: d4-operating-revenue, Property 5: 跨Sheet聚合正确性**

- [x] 5. Checkpoint - 公式引擎与基础设施验证

- [x] 6. 实现核心组 composable（D4-1/D4-2/D4-3/D4-4）
  - [x] 6.1 创建 `composables/useD4Adjudication.ts`
    - 双区块固定行（主营产品行+小计 / 其他项目行+小计 / 营业收入合计）
    - sections computed（从crossSheet聚合值填入）
    - trialBalanceRow + differenceRow（TB科目6001+6051）
    - mainCrossValidation / otherCrossValidation 警告
    - updateCell + addProductRow/removeProductRow
    - publishAdjudicated（EventBus → TB回写）
    - onAdjustmentCreated监听
    - _Requirements: 2.1-2.10, 18.1_

  - [x] 6.2 创建 `composables/useD4RevenueDetail.ts`
    - RevenueDetailRow 22列完整定义
    - rows reactive + 行内公式（N=SUM months; P=N+O; S=Q+R; T/U变动率）
    - subtotalRow + verificationRow（合计-TB 6001）
    - searchQuery + filteredRows + addRow/removeRow/updateCell
    - importFromLedger（从序时账导入）
    - _Requirements: 3.1-3.10_

  - [x] 6.3 创建 `composables/useD4OtherRevenue.ts`
    - OtherRevenueRow完整定义（含审定/占比/变动自动计算）
    - rows + subtotalRow + verificationRow（合计-TB 6051）
    - addRow/removeRow/updateCell
    - _Requirements: 4.1-4.7_

  - [x] 6.4 创建 `composables/useD4Adjustment.ts`
    - D4AdjustmentRow 10列 + rows + debitTotal/creditTotal/isBalanced
    - addRow/removeRow/updateCell + publishAdjustment + pushToA13
    - _Requirements: 5.1-5.7_

  - [x]* 6.5 编写 Property 6 PBT：借贷平衡
    - **Feature: d4-operating-revenue, Property 6: 调整分录借贷平衡检查**

  - [x]* 6.6 编写 Property 7 PBT：AJE同步
    - **Feature: d4-operating-revenue, Property 7: 调整分录EventBus同步正确性**

  - [x]* 6.7 编写 Property 8 PBT：差异/交叉验证
    - **Feature: d4-operating-revenue, Property 8: 差异行与交叉验证**

  - [x]* 6.8 编写 Property 3 PBT：动态行添加
    - **Feature: d4-operating-revenue, Property 3: 动态行添加保持结构不变量**

  - [x]* 6.9 编写 Property 17 PBT：EventBus回写
    - **Feature: d4-operating-revenue, Property 17: EventBus审定数回写正确性**

  - [x]* 6.10 编写 Property 19 PBT：搜索过滤
    - **Feature: d4-operating-revenue, Property 19: 搜索过滤正确性**

- [x] 7. 实现核心组 Vue组件
  - [x] 7.1 创建 `d4/core/D4TabAdjudication.vue`（~400行）
    - 双区块el-table + 合计行不可编辑 + 跨sheet浅蓝背景
    - 变动率>30%红色 + 差异≠0红色 + 交叉验证el-alert
    - 审计说明/结论textarea + AI按钮 + 💬复核 + GtIndexChip→D4-6/D4-7/D4-2
    - _Requirements: 2.1-2.10, 19.1, 21.1_

  - [x] 7.2 创建 `d4/core/D4TabRevenueDetail.vue`（~400行）
    - el-table横向滚动22列 + 固定col A + 搜索框 + 虚拟滚动(>30行)
    - 自动计算列灰底 + 变动>30%红色 + 金额fmtAmount右对齐
    - "添加产品行"/"从序时账导入" + 合计行 + 核对行
    - 审计说明/结论 + AI + GtIndexChip→D4-8
    - _Requirements: 3.1-3.10, 19.3, 21.2_

  - [x] 7.3 创建 `d4/core/D4TabOtherRevenue.vue`（~300行）
    - el-table + 审定/占比/变动自动计算 + 变动>30%红色
    - "添加项目行" + 合计行 + 核对行
    - 审计说明/结论 + 💬复核
    - _Requirements: 4.1-4.7, 21.2_

  - [x] 7.4 创建 `d4/core/D4TabAdjustment.vue`（~250行）
    - el-table 10列 + "新增调整分录" + 借贷合计+平衡指示
    - "推送至A13"按钮 + 编制提示details折叠
    - _Requirements: 5.1-5.7_

  - [x] 7.5 创建 `d4/core/D4TabDisclosureListed.vue` + `D4TabDisclosureSoe.vue`
    - 3子节/2子节卡片 + 跨sheet取数浅蓝色 + 动态行 + 合计
    - applicable_standards判断显隐 + 说明textarea + EventBus note-text-updated
    - _Requirements: 6.1-6.10_

- [x] 8. Checkpoint - 核心组验证

- [x] 9. 实现政策组 D4-5
  - [x] 9.1 创建 `composables/useD4PolicyCheck.ts` + `d4/policy/D4TabPolicyCheck.vue`
    - CAS14五步法卡片结构（5步）
    - 每步：政策条款只读details + 实际情况textarea + 审计师评价textarea+AI
    - Y/N/NA结论 + N时强制说明 + 进度条(5步中已完成N步)
    - 💬复核入口
    - _Requirements: 7.1-7.7, 21.3_

- [x] 10. 实现分析程序组 D4-6~11
  - [x] 10.1 创建 `composables/useD4Analysis.ts`
    - D4-6指标卡片网格(2列×N行) + TB自动取数
    - D4-7月度毛利率趋势表(12月×产品) + 波动>5%黄色
    - D4-8产品毛利对比 + 变动>10%红色
    - D4-9客户集中度(Top5/Top10/HHI) + >50%警告
    - D4-10客户价格变动 + >20%红色
    - D4-11产品价格趋势
    - publishSignificantChange EventBus
    - _Requirements: 8.1-8.10, 17.5-17.7, 18.3_

  - [x] 10.2 创建6个Vue子组件（d4/analysis/D4TabIndicator~D4TabProductPrice.vue）
    - 各sheet独立渲染 + crossSheet取数 + 审计说明AI + 💬复核
    - _Requirements: 8.1-8.10, 19.3, 21.7_

  - [x]* 10.3 编写 Property 12 PBT：Top5集中度
    - **Feature: d4-operating-revenue, Property 12: 客户集中度Top5计算**

  - [x]* 10.4 编写 Property 18 PBT：异常率/覆盖率
    - **Feature: d4-operating-revenue, Property 18: 异常率与覆盖率计算**

- [x] 11. 实现检查程序组 D4-12~20
  - [x] 11.1 创建 `composables/useD4Inspection.ts`
    - D4-12合同检查（动态行+覆盖率+下拉）
    - D4-13 ERP核对（差异=账面-ERP）
    - D4-14/15发生/完整性（抽样参数+凭证明细+汇总+抽凭引擎集成）
    - D4-16出口核对（月度对比+汇率+差异）
    - D4-17/18截止双向（跨期自动判断+天数+红色高亮+汇总+auto-sampling集成）
    - D4-19折扣（政策+明细+符合性）
    - D4-20退货（本期+期后+退货模式AI）
    - _Requirements: 9.1-9.7, 10.1-10.8, 11.1-11.8, 12.1-12.8_

  - [x] 11.2 创建9个Vue子组件（d4/inspection/D4TabContract~D4TabReturn.vue）
    - 各sheet独立渲染 + 采样参数进度条 + GtIndexChip交叉引用 + 💬复核
    - _Requirements: 9.1-9.7, 10.1-10.8, 11.1-11.8, 12.1-12.8, 19.5-19.8_

  - [x]* 11.3 编写 Property 9 PBT：截止跨期判断
    - 生成器：`fc.date` × 3
    - **Feature: d4-operating-revenue, Property 9: 截止跨期自动判断**

- [x] 12. Checkpoint - 政策+分析+检查组验证

- [x] 13. 实现关联方组 D4-21
  - [x] 13.1 创建 `composables/useD4RelatedPrice.ts` + `d4/related/D4TabRelatedPrice.vue`
    - 对比分析表（关联vs非关联单价+差异率+结论）
    - >10%黄色/>20%红色 + 合计 + 占比
    - AI评价按钮 + GtIndexChip→A17 + 💬复核
    - _Requirements: 13.1-13.8_

- [x] 14. 实现IPO/舞弊组 D4-22A~32（条件可见）
  - [x] 14.1 创建 `composables/useD4Ipo.ts`
    - visibility守卫（business_category判断）
    - D4-22A IPO程序表（复用a-program-console + GtIndexChip）
    - D4-22 IPO指标（同D4-6结构+增强指标）
    - D4-23发票对比（月度差异+>10%黄色）
    - D4-24第三方回款（代付协议+资金流向+资金回流模式识别）
    - D4-25经销商（背景+销售匹配）
    - D4-26境外（贸易条款+海关）
    - D4-27未披露关联方（穿透+红色高亮）
    - D4-28/29客户核查（固定Y/N清单+逐客户详细）
    - D4-30/31访谈（多客户汇总+单客户详细+AI建议问题）
    - D4-32资金流水（入出+净额+时间匹配+可疑自动标记）
    - _Requirements: 14.1-14.12_

  - [x] 14.2 创建12个Vue子组件（d4/ipo/D4TabIpoProcedure~D4TabFundFlow.vue）
    - 各sheet独立渲染 + 条件可见v-if + 💬复核（重点D4-24/D4-32）
    - _Requirements: 14.1-14.12, 22.4_

- [x] 15. 实现其他收入组 D4-33~36
  - [x] 15.1 创建 `composables/useD4OtherGroup.ts`
    - D4-33毛利率（同D4-8结构，数据源D4-3）
    - D4-34合同测算（差异=实际-应确认）
    - D4-35凭证检查（同D4-14结构）
    - D4-36截止测试（同D4-17/18结构）
    - _Requirements: 15.1-15.8_

  - [x] 15.2 创建4个Vue子组件（d4/other/D4TabOtherMargin~D4TabOtherCutoff.vue）
    - 各sheet渲染 + 从D4-3取数 + 汇总公式 + 💬复核
    - _Requirements: 15.1-15.8_

- [x] 16. Checkpoint - 全部功能组验证

- [x] 17. 实现后端导入导出端点
  - [x] 17.1 创建 `_d4_import_export.py`
    - POST export-template/export-data/import-data（支持D4-2/D4-3/D4-12/D4-14~20/D4-21~36）
    - 格式校验 + 行数限制>500截断 + 错误列表
    - 注册路由到router_registry
    - _Requirements: 20.6, 20.7_

  - [x]* 17.2 编写 Property 15 PBT（后端hypothesis）：Round-Trip
    - 生成随机RevenueDetailRow[]→export→import→验证等价
    - **Feature: d4-operating-revenue, Property 15: 导入导出Round-Trip**

- [x] 18. 实现后端Resolver和AI端点
  - [x] 18.1 创建 `_d4_resolvers.py`
    - `d4_tb_unadjusted` resolver（trial_balance 6001+6051期初/期末未审数）
    - `d4_ledger_monthly` resolver（tb_ledger 6001按月汇总）
    - `d4_analysis_indicators` resolver（多科目余额计算毛利率/周转率/应收占比）
    - _Requirements: 20.1-20.4, 26.3-26.5_

  - [x] 18.2 创建 `_d4_ai_generate.py`
    - POST /api/workpapers/{wp_id}/d4/ai-generate
    - 支持8+section（adj-note/revenue-change/policy-evaluation/analysis-note/return-analysis/related-price/interview-questions等）
    - 注册到router_registry "AI与辅助"组
    - _Requirements: 21.1-21.8_

  - [x] 18.3 实现render策略和account_package_registry
    - RENDERER_DISPATCH注册'd4-operating-revenue'→`_render_d4_operating_revenue`
    - 策略函数返回完整html_data（双区块+明细+分组+visibility）
    - account_package_registry.json更新（36 sheet + 8 xlsx源映射）
    - _Requirements: 26.1-26.7_

- [x] 19. 实现前端导入导出UI + 双模式切换
  - [x] 19.1 在D4-2/D4-3/D4-12/D4-14~20等子组件添加导入导出工具栏
    - "导出模板"/"导出数据"/"导入数据" + el-upload + 错误提示
    - D4-2增加"从序时账导入"按钮
    - _Requirements: 20.2, 20.6, 20.7_

  - [x] 19.2 在所有子组件实现双模式切换
    - el-segmented（"结构化视图"|"在线编辑"）
    - 8个源xlsx分别管理OO配置 + SetVisible隐藏非当前sheet
    - OO不可用时禁用 + 切回HTML重新加载responses
    - _Requirements: 23.1-23.6_

- [x] 20. 集成主入口 GtD4OperatingRevenue.vue
  - [x] 20.1 完善主入口组件
    - 嵌套el-tabs：一级7组 + 二级各组内sheet
    - IPO/舞弊组v-if条件可见
    - 附注Tab内根据applicable_standards判断上市/国企显隐
    - provide openReviewDialog（inject模式）
    - 传递allResponses/wpId/projectId/crossSheet等
    - Tab顺序对齐源模板
    - _Requirements: 1.1-1.10, 14.1, 6.8-6.9_

- [x] 21. 实现程序表D4A集成 + GtIndexChip全量配置
  - [x] 21.1 D4A程序表集成
    - 复用a-program-console + selfLoad + GtIndexChip→各子sheet
    - EventBus接收risk:updated更新步骤状态
    - D4A↔D4-22A IPO程序表交叉引用
    - _Requirements: 16.1-16.5_

  - [x] 21.2 配置全部GtIndexChip交叉索引（10+处）
    - D4-1→D4-6/D4-7/D4-2; D4-2→D4-8; D4-9→D4-21
    - D4-12→D4-14/15; D4-17/18→D2; D4-19→D4-12; D4-20→D4-17/18
    - D4-21→A17; D4A→D4-1~36; D4-22A→D4-22~32
    - 点击GtIndexChip切换一级+二级Tab定位
    - _Requirements: 19.1-19.12_

- [x] 22. 实现D4-2↔D4-1行结构同步 + 附注成本跨循环取数 + 适用性控制
  - [x] 22.1 D4-2产品行↔D4-1主营行同步
    - useD4CrossSheet中实现syncProductRowToAdjudication(action, product)
    - D4-2 addRow时→D4-1主营区块新增对应行（isFromCrossSheet=true）
    - D4-2 removeRow时→D4-1同步删除（AJE/RJE为零时直接删，否则弹确认）
    - D4-3同理→D4-1其他区块
    - D4-1中isFromCrossSheet=true的行"项目"列不可编辑
    - _Requirements: 27.1-27.4_

  - [x] 22.2 附注成本数据跨循环取数
    - useD4CrossSheet中实现costFromTb computed（从TB科目6401+6402取审定发生额）
    - D4TabDisclosureListed/Soe的"营业成本"列自动填充（浅蓝背景+tooltip）
    - TB无成本数据时显示"待M循环审定"灰色占位
    - 毛利自动计算=收入-成本
    - _Requirements: 28.1-28.4_

  - [x] 22.3 修订前程序表skip + 出口/境外适用性
    - wp_code_overrides中D4A修订前sheet映射skip
    - useD4CrossSheet中实现hasExportBusiness computed
    - D4-16/D4-26的二级Tab用v-if守卫（hasExportBusiness）
    - 隐藏Tab被外部GtIndexChip访问时显示"不适用"提示
    - _Requirements: 29.1-29.4_

  - [x] 22.4 实现"访谈记录与核对示例"sheet渲染
    - 在d4/ipo/D4TabInterviewTemplate.vue中实现QA卡片结构（基本信息+交易核实+现场观察+结论）
    - "新建走访记录"按钮（基于模板创建实例，支持多客户）
    - AI预填基本情况+建议问题
    - _Requirements: 30.1-30.4_

  - [x] 22.5 实现统一底稿目录Tab
    - 在d4/core/D4TabIndex.vue中合并8个源文件底稿目录为统一清单（42行）
    - 每行GtIndexChip跳转对应二级Tab + 不适用行灰色 + 进度条
    - 作为"核心"组第一个二级Tab
    - _Requirements: 31.1-31.5_

- [x] 23. Checkpoint - 集成与双模式验证

- [x] 24. 回归测试与全量验证
  - [x] 24.1 运行全量测试
    - vitest run 所有D4相关spec文件
    - python -m pytest backend/tests/ -k d4
    - 验证htmlRendererRegistry注册数量更新
    - 验证VALID_COMPONENT_TYPES含'd4-operating-revenue'
    - 验证RENDERER_DISPATCH含'd4-operating-revenue'策略
    - 验证auto_data_resolvers含d4_tb_unadjusted/d4_ledger_monthly/d4_analysis_indicators
    - 验证wp_code_overrides D4/D4-1~D4-36映射（含修订前skip）
    - 验证D4-2行增减时D4-1同步
    - _Requirements: all_

- [x] 25. Final checkpoint - 全部功能集成验证

## Notes

- Tasks marked with `*` are optional PBT tests
- 每个Property对应design.md中的一个correctness property
- 所有PBT使用fast-check（前端）或hypothesis（后端），numRuns: 100
- 损益类核心特征：取发生额（非余额），审定=未审+AJE+RJE，无期初期末余额概念
- 跨sheet全部通过allResponses computed链，不走API调用
- selfLoad必须支持（bundle内嵌/独立打开均可）
- 程序表D4A复用a-program-console componentType
- IPO/舞弊组通过business_category字段控制一级Tab可见性（v-if）
- 附注按applicable_standards控制上市/国企Tab显隐
- 8个源xlsx对应8个OO配置，双模式切换时按当前二级Tab确定打开哪个xlsx的哪个sheet
- AI生成端点复用B14/A17-1模式：project_context + 底稿数据snapshot + CPA system prompt
- auto_data resolver注册后，程序表D4A可通过auto_data_source自动取数
- 由于36 sheet规模大，composable按功能域分组而非每sheet一个（useD4Analysis覆盖D4-6~11，useD4Inspection覆盖D4-12~20，useD4Ipo覆盖D4-22A~32）
- **D4-2产品行↔D4-1行同步**：D4-2 addRow/removeRow时需同步D4-1对应区块行结构（isFromCrossSheet标记），D4-3同理。删除时需检查AJE/RJE非零则弹确认
- **修订前程序表D4A（229行旧版）skip**：仅保留新版D4A（43行），旧版在wp_code_overrides映射skip不渲染
- **附注成本跨循环取数**：营业成本(6401/6402)由M循环审定，D4附注的成本列通过TB resolver取数（浅蓝标记），非手工填写
- **出口/境外适用性**：D4-16/D4-26仅对has_export_business=true项目显示，其他项目隐藏该二级Tab
