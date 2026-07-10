# Implementation Plan: H2 在建工程底稿专属HTML精美组件

## Overview

H2在建工程底稿专属组件`h2-construction-in-progress`。H循环第二大底稿（21有效sheet/1 xlsx/~130+公式）。

主入口 GtH2ConstructionInProgress.vue（sheetName v-if分发，defineAsyncComponent lazy）+ 17个子组件 + 18个composable + 后端4个py文件。

科目：1604在建工程（借方/资产类）
公式特征：期末=期初+借方-贷方（资产类）；审定=未审+AJE+RJE；三角勾稽（期末=期初+增加-减少-转固）

## Tasks

### Phase 0: 双源输入验证

- [x] 0.1 openpyxl脚本读取H2在建工程.xlsx全部21 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 产出：h2_structure_summary.json（权威列头+公式清单）
  - 验证：21 sheet结构与本spec描述一致
  - _Requirements: 双源输入流程_

- [x] 0.2 H固定资产循环底稿模板库md交叉验证
  - 核对：审计目标/程序清单/联动关系/认定对应/交叉引用
  - 冲突解决：列名以xlsx为准，联动方向以md为准
  - 产出：h2_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - 在 `wp_code_overrides.json` 中将H2/H2-1~H2-17/H2A映射为'h2-construction-in-progress'
  - 在 `VALID_COMPONENT_TYPES` 中注册'h2-construction-in-progress'
  - 在 `htmlRendererRegistry.ts` 中注册 'h2-construction-in-progress' → GtH2ConstructionInProgress 映射
  - 创建 `GtH2ConstructionInProgress.vue` 主入口骨架（sheetName prop v-if分发 + defineAsyncComponent lazy + selfLoad）
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9_

- [x] 1.2 编写注册契约测试
  - htmlRendererRegistry.spec.ts 验证'h2-construction-in-progress'已注册
  - VALID_COMPONENT_TYPES契约验证
  - wp_code_overrides契约验证H2/H2-1~H2-17映射
  - RENDERER_DISPATCH注册验证
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+PBT

- [x] 2.1 创建 `composables/useH2FormulaEngine.ts`，实现全部纯函数
  - `calcAuditedAmount(unadj, aje, rje)` → 审定=未审+AJE+RJE
  - `calcAssetEndBalance(begin, debit, credit)` → 资产类期末=期初+借方-贷方
  - `calcCipEndBalance(begin, increase, decrease, transfer)` → 在建期末=期初+增加-减少-转固
  - `calcTriangleWithTransfer(begin, increase, decrease, transfer, end)` → 三角勾稽差额(含转固)
  - `calcSubtotal(arr)` → 合计=SUM
  - `calcCompletionRate(accumulated, budget)` → 完工率
  - `calcOverBudgetRate(actual, budget)` → 超预算率
  - `calcCostDiffRate(actual, budget)` → 造价差异率
  - `calcOverdueDays(actualDate, plannedDate)` → 工期超期天数
  - `calcTransferCondition(conditions)` → CAS4五条件全满足判定
  - `isBalanced(entries)` → 借贷平衡检查
  - _Requirements: 1.5, 2.3-2.6, 5.2, 6.2, 8.2_

- [x] 2.2 创建 `composables/useH2InterestCapEngine.ts`，实现利息资本化纯函数
  - `calcWeightedCapRate(loans)` → 加权资本化率
  - `calcWeightedExpenditure(expenditures, totalDays)` → 累计支出加权平均数
  - `calcCapAmountNoBorrow(weightedExp, capRate)` → 无专门借款资本化金额
  - `calcSpecialLoanCap(interest, idleIncome)` → 专门借款资本化=利息-闲置收益
  - `calcGeneralLoanSupp(excessWeightedExp, generalCapRate)` → 一般借款补充资本化
  - `calcTotalCapWithBorrow(specialCap, generalSupp)` → 有专门借款合计
  - `calcDcfPresentValue(cashFlows, discountRate)` → DCF现值
  - `calcTerminalValue(perpetuityCF, discountRate, growthRate)` → 终值
  - _Requirements: 10.4, 10.5, 12.4_

- [x]* 2.3 编写 Property P1 PBT：审定数公式链
  - 生成器：fc.float({min:-1e9, max:1e9}) × 3 (unadj/aje/rje)
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: h2-construction-in-progress, Property P1: 审定数公式链正确性**

- [x]* 2.4 编写 Property P2 PBT：资产类期末余额
  - 生成器：fc.float({min:0, max:1e9}) × 3
  - 断言：calcAssetEndBalance(b, d, c) === b + d - c
  - **Feature: h2-construction-in-progress, Property P2: 资产类期末余额公式**

- [x]* 2.5 编写 Property P3 PBT：在建工程三角勾稽（含转固扣减）
  - 生成器：fc.float({min:0, max:1e9}) × 4, end=begin+increase-decrease-transfer
  - 断言：calcTriangleWithTransfer(b, i, d, t, b+i-d-t) === 0
  - **Feature: h2-construction-in-progress, Property P3: 在建工程三角勾稽含转固扣减**

- [x]* 2.6 编写 Property P4 PBT：合计行恒等
  - 生成器：fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:50})
  - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
  - **Feature: h2-construction-in-progress, Property P4: 合计行恒等于明细行之和**

- [x]* 2.7 编写 Property P5 PBT：完工率公式正确性
  - 生成器：fc.float({min:1, max:1e9}), fc.float({min:1, max:1e9})
  - 断言：calcCompletionRate(acc, bud) === acc/bud×100
  - **Feature: h2-construction-in-progress, Property P5: 完工率公式正确性**

- [x]* 2.8 编写 Property P6 PBT：加权资本化率计算（无专门借款）
  - 生成器：fc.array(fc.record({principal,rate,days}), {minLength:1, maxLength:10})
  - 断言：calcWeightedCapRate(loans) === Σ(p×r×d/365)/Σ(p×d/365)
  - **Feature: h2-construction-in-progress, Property P6: 加权资本化率计算正确性**

- [x]* 2.9 编写 Property P7 PBT：专门借款利息资本化公式
  - 生成器：fc.float({min:1, max:1e8}), fc.float({min:0, max:1e6})
  - 断言：calcSpecialLoanCap(interest, idle) === interest - idle
  - **Feature: h2-construction-in-progress, Property P7: 专门借款利息资本化公式**

- [x]* 2.10 编写 Property P8 PBT：工程造价差异率
  - 生成器：fc.float({min:1, max:1e9}), fc.float({min:1, max:1e9})
  - 断言：calcCostDiffRate(actual, budget) === (actual-budget)/budget×100
  - **Feature: h2-construction-in-progress, Property P8: 工程造价差异率公式**

- [x]* 2.11 编写 Property P9 PBT：转固条件判定（CAS4五条件全满足）
  - 生成器：fc.array(fc.boolean(), {minLength:5, maxLength:5})
  - 断言：calcTransferCondition(conds) === conds.every(c=>c)
  - **Feature: h2-construction-in-progress, Property P9: CAS4转固五条件全满足判定**

- [x]* 2.12 编写 Property P10 PBT：借贷平衡检查
  - 生成器：fc.array(fc.record({debit: fc.float({min:0}), credit: fc.float({min:0})}), {minLength:1, maxLength:20})
  - 断言：isBalanced === (SUM(debit) === SUM(credit))
  - **Feature: h2-construction-in-progress, Property P10: 借贷平衡检查**

- [x]* 2.13 编写 Property P11 PBT：DCF现值
  - 生成器：fc.array(fc.float({min:1, max:1e6}), {minLength:1, maxLength:10}), fc.float({min:0.01, max:0.3})
  - 断言：calcDcfPresentValue(cfs, r) === Σ(cf_i/(1+r)^(i+1))
  - **Feature: h2-construction-in-progress, Property P11: DCF现值计算正确性**

- [x]* 2.14 编写 Property P12 PBT：工期超期判定
  - 生成器：fc.date() × 2（确保actual≥planned）
  - 断言：calcOverdueDays(actual, planned) === daysDiff(actual, planned) 且结果≥0
  - **Feature: h2-construction-in-progress, Property P12: 工期超期判定正确性**

### Phase 3: FormData/CrossSheet composables

- [x] 3.1 创建 `composables/useH2FormData.ts`
  - allResponses Map加载 + saveImmediate + debouncedSave(2s) + saveBatch
  - writebackTrialBalance（科目1604借方）
  - selfLoad逻辑（render-config?force_component_type=h2-construction-in-progress）
  - projectContext加载（含business_category/applicable_standards）
  - TB自动取数unadjusted_amount→审定表未审数
  - _Requirements: 14.8-14.9_

- [x] 3.2 创建 `composables/useH2CrossSheet.ts`
  - detailTotals computed（H2-2按工程聚合期末/增加/减少/转固）
  - adjudicationFromDetail computed（H2-2合计→H2-1）
  - transferSummary computed（H2-5转固合计→H2-1转固列）
  - interestCapForDetail computed（H2-10/11资本化金额→H2-2利息列）
  - analysisFromDetail computed（H2-2→H2-4取数）
  - disclosureAutoFill computed（H2-1→附注各子节）
  - _Requirements: 14.6-14.7_

- [x] 3.3 创建 `composables/useH2Adjudication.ts`
  - 固定行（各工程项目+小计+合计） + 12列含转固列
  - 三角勾稽实时校验（期末=期初+增加-减少-转固）
  - TB取数行 + 差异行 + 交叉验证H2-2 + 转固验证H2-5
  - updateCell + publishAdjudicated（EventBus → TB回写）
  - _Requirements: 2.1-2.12_

- [x] 3.4 创建 `composables/useH2Detail.ts`
  - DetailRow 50列完整定义 + 3区段分组配置（基本/增减/竣工结转）
  - 行内公式（期末=期初+增加-减少-转固；增加合计；完工进度）
  - subtotalRow + crossValidation（vs H2-1）
  - addRow(弹窗命名)/removeRow/updateCell
  - _Requirements: 3.1-3.12_

- [x] 3.5 创建 `composables/useH2Adjustment.ts`
  - H2AdjustmentRow 10列 + rows + debitTotal/creditTotal/isBalanced
  - addRow/removeRow/updateCell + publishAdjustment + pushToA13
  - _Requirements: 4.1-4.8_

- [x] 3.6 创建 `composables/useH2Analysis.ts`
  - 三区域（工程进度+资本化率+工期分析）+ 10公式自动计算
  - 从H2-2 crossSheet取数 + 超期/超预算异常判定
  - _Requirements: 5.1-5.8_

- [x] 3.7 创建 `composables/useH2TransferCheck.ts`
  - TransferRow 15列 + CAS4五条件自动判定
  - 转固合计 + 与H2-1交叉验证 + H1联动EventBus
  - 延迟天数计算 + 异常高亮规则
  - _Requirements: 6.1-6.10_

- [x] 3.8 创建 `composables/useH2ReviewRecord.ts`
  - 签章式结构（基本信息+审核事项逐条+结论签名）
  - 工程项目筛选 + 从H2-2取数工程列表
  - _Requirements: 7.1-7.5_

- [x] 3.9 创建 `composables/useH2CostComparison.ts`
  - CostComparisonRow 16列 + 14公式自动计算
  - 从H2-2取数 + 超支/超预算高亮规则
  - _Requirements: 8.1-8.7_

- [x] 3.10 创建 `composables/useH2AdditionCheck.ts`
  - AdditionRow 24列 + 抽样参数 + 汇总统计
  - 集成voucher-sampling-engine + OCR端点
  - _Requirements: 9.1-9.2, 9.5-9.8_

- [x] 3.11 创建 `composables/useH2DecreaseCheck.ts`
  - DecreaseRow 27列 + 抽样参数 + 汇总统计
  - 集成voucher-sampling-engine
  - _Requirements: 9.3-9.5, 9.7-9.8_

- [x] 3.12 创建 `composables/useH2InterestCap.ts`
  - interestCapBranch状态(noBorrow/withBorrow) + 2分支共用数据
  - 调用InterestCapEngine计算 + 差异对比 + EventBus联动L
  - 从H2-2取数(各工程利息列) + 交叉验证
  - _Requirements: 10.1-10.10_

- [x] 3.13 创建 `composables/useH2Stocktake.ts`
  - 计划/检查/小结三阶段共用状态
  - FixedAssetStocktakeDialog集成
  - 停工迹象自动标记 + 与H2-15减值联动
  - _Requirements: 11.1-11.6_

- [x] 3.14 创建 `composables/useH2Impairment.ts`
  - 减值迹象6项判断 + 测算表 + DCF模型
  - 敏感性分析矩阵 + 可收回金额MAX选取
  - 从H2-13取数停工工程列表
  - _Requirements: 12.1-12.7_

- [x] 3.15 创建 `composables/useH2RelatedParty.ts`
  - RelatedPartyRow 15列 + 差异率计算 + 合计行
  - 高亮规则(差异率>10%红色)
  - _Requirements: 13.1-13.6_

- [x] 3.16 创建 `composables/useH2Disclosure.ts`
  - variant参数（listed/soe）双版本共用
  - 多子节结构 + 跨sheet自动取数 + 动态行
  - EventBus 'disclosure:note-text-updated'
  - _Requirements: 14.6_

### Phase 4: 各sheet Vue组件

- [x] 4.1 创建 `h2/core/H2TabIndex.vue`（~150行）
  - 底稿目录（21行进度条+完成状态）
  - _Requirements: 1.2_

- [x] 4.2 创建 `h2/core/H2TabAdjudication.vue`（~450行）
  - el-table 12列 + 三角勾稽校验红色高亮(含转固)
  - 审计说明/结论 + AI + 💬复核 + GtIndexChip→H2-4
  - _Requirements: 2.1-2.12, 14.6_

- [x] 4.3 创建 `h2/core/H2TabDetail.vue`（~500行）
  - 3区段Tab切换(基本/增减/竣工结转) + 行同步 + 固定列
  - 合计行 + 交叉验证H2-1 + 导入导出
  - _Requirements: 3.1-3.12_

- [x] 4.4 创建 `h2/core/H2TabAdjustment.vue`（~250行）
  - el-table 10列 + 借贷平衡 + 推送A13
  - _Requirements: 4.1-4.8_

- [x] 4.5 创建 `h2/core/H2TabAnalysis.vue`（~350行）
  - 三区域(进度+资本化率+工期) + 阈值高亮 + GtIndexChip
  - _Requirements: 5.1-5.8_

- [x] 4.6 创建 `h2/core/H2TabDisclosureListed.vue` + `H2TabDisclosureSoe.vue`（各~300行）
  - 多子节卡片 + 跨sheet浅蓝色 + 动态行 + 合计
  - _Requirements: 14.6_

- [x] 4.7 创建 `h2/inspection/H2TabTransferCheck.vue`（~400行）
  - el-table 15列 + CAS4五条件判定 + 延迟高亮 + GtIndexChip→H1
  - 方法论上下文区域 + 转固合计 + EventBus联动H1
  - _Requirements: 6.1-6.10_

- [x] 4.8 创建 `h2/inspection/H2TabReviewRecord.vue`（~350行）
  - 签章式卡片(基本信息+审核事项+结论签名)
  - 工程筛选el-select + 审计结论AI + 💬复核
  - _Requirements: 7.1-7.5_

- [x] 4.9 创建 `h2/inspection/H2TabCostComparison.vue`（~350行）
  - el-table 16列(14公式) + 超支红色高亮 + GtIndexChip→H2-2
  - 合计行 + 审计说明 + AI + 💬复核
  - _Requirements: 8.1-8.7_

- [x] 4.10 创建 `h2/inspection/H2TabAdditionCheck.vue`（~400行）
  - 双区域(抽样参数+明细) + 固定列+滚动列 + OCR📎 + 抽凭
  - _Requirements: 9.1-9.2, 9.5-9.8_

- [x] 4.11 创建 `h2/inspection/H2TabDecreaseCheck.vue`（~350行）
  - 双区域(抽样参数+明细) + 损失分类 + 抽凭
  - _Requirements: 9.3-9.5, 9.7-9.8_

- [x] 4.12 创建 `h2/inspection/H2TabRelatedParty.vue`（~300行）
  - el-table 15列 + 价格差异率>10%红色 + 合计行
  - _Requirements: 13.1-13.6_

- [x] 4.13 创建 `h2/interest/H2TabInterestCapNoBorrow.vue`（~450行）
  - 28列78行(12公式) + 分支选择器 + 借款明细 + 加权计算
  - _Requirements: 10.1-10.4, 10.6-10.10_

- [x] 4.14 创建 `h2/interest/H2TabInterestCapWithBorrow.vue`（~400行）
  - 28列48行(15公式) + 专门借款+一般借款补充 + 合计
  - _Requirements: 10.1, 10.3, 10.5-10.10_

- [x] 4.15 创建 `h2/stocktake/H2TabStocktakePlan.vue`（~250行）
  - 3区域(基本信息+工程选取+时间安排)
  - _Requirements: 11.1_

- [x] 4.16 创建 `h2/stocktake/H2TabStocktakeCheck.vue`（~350行）
  - 盘点检查表 + 停工红色高亮 + 导入导出
  - _Requirements: 11.2, 11.5_

- [x] 4.17 创建 `h2/stocktake/H2TabStocktakeSummary.vue`（~300行）
  - 段落型+表格(踏勘总体+异常清单+结论)
  - _Requirements: 11.3, 11.6_

- [x] 4.18 创建 `h2/impairment/H2TabImpairment.vue`（~350行）
  - 双区域(迹象判断6项+测算表) + GtIndexChip→H2-16/H2-13
  - _Requirements: 12.1-12.2, 12.5-12.7_

- [x] 4.19 创建 `h2/impairment/H2TabRecoverable.vue`（~400行）
  - DCF模型(假设+现金流预测+折现) + 敏感性矩阵
  - _Requirements: 12.3-12.4_

### Phase 5: 后端（render策略+import_export+ai_generate+利息资本化引擎endpoint）

- [x] 5.1 创建 `_h2_construction_in_progress.py` render策略
  - 注册RENDERER_DISPATCH['h2-construction-in-progress']
  - render函数：加载allResponses + projectContext + TB数据(1604)
  - 返回html_data结构（sections/rows/formulas/crossSheetRefs）
  - _Requirements: 1.1, 14.8_

- [x] 5.2 创建 `_h2_import_export.py` 导入导出3端点
  - POST /h2/export-template → 空白结构xlsx（H2-2按3区段分sheet）
  - POST /h2/export-data → 当前数据xlsx（含公式结果）
  - POST /h2/import-data → 解析xlsx→验证→写入checklist_responses
  - StreamingResponse中文文件名RFC5987编码
  - _Requirements: 14.3-14.4_

- [x] 5.3 创建 `_h2_ai_generate.py` AI生成6 section
  - adj-note / adj-conclusion / analysis-progress
  - cost-comparison-note / interest-cap-summary / impairment-conclusion
  - 各section使用对应sheet数据+项目上下文生成
  - _Requirements: 14.5_

- [x] 5.4 创建 `_h2_interest_cap_engine.py` 利息资本化引擎端点
  - POST /h2/interest-cap/calculate → 2分支计算（无/有专门借款）
  - POST /h2/interest-cap/validate → 验证账面vs测算差异
  - 纯函数实现（与前端对等逻辑）
  - _Requirements: 10.4, 10.5_

- [x] 5.5 创建 `_h2_construction_in_progress.py` auto_data_resolver
  - h2_tb_unadjusted: 从trial_balance取科目1604未审数
  - h2_transfer_summary: 从H2-5取数转固合计
  - 注册到_REGISTRY
  - _Requirements: 14.8_

### Phase 6: 集成（主入口+双模式+导入导出+跨底稿联动）

- [x] 6.1 完成 GtH2ConstructionInProgress.vue 主入口集成
  - sheetName regex分发全部17个子组件
  - defineAsyncComponent lazy（除H2TabIndex外）
  - provide openReviewDialog给子组件inject
  - useVersionTrail集成（autoSnapshot on save）
  - _Requirements: 1.2-1.3, 14.8, 14.10_

- [x] 6.2 创建 `composables/useH2DualMode.ts`
  - HTML↔OnlyOffice el-segmented切换
  - OO健康检查(`health.data?.data?.healthy`双层兼容)
  - 切换前autoSave
  - _Requirements: 14.1-14.2_

- [x] 6.3 创建 `composables/useH2ImportExport.ts`
  - el-dropdown三级UI + axios请求（非fetch）
  - H2-2宽表按3区段分sheet导出
  - 导入xlsx解析+验证+确认对话+写入
  - _Requirements: 14.3-14.4_

- [x] 6.4 H2-8 抽凭引擎集成
  - GtVoucherSamplingEngine dialog→样本填入AdditionCheck
  - _Requirements: 9.5_

- [x] 6.5 H2-8 行级OCR集成
  - 📎列POST contract-ocr端点 → ElMessageBox确认 → merge字段
  - _Requirements: 9.6_

- [x] 6.6 H2-5转固联动H1
  - publish 'h2:transfer-to-h1'事件
  - GtIndexChip跳转H1固定资产审定表
  - _Requirements: 6.7-6.8, 14.7_

- [x] 6.7 H2-10/11利息资本化联动L
  - publish 'h2:interest-capitalized'事件（payload含资本化金额/利息总额/资本化率）
  - _Requirements: 10.9, 14.7_

- [x] 6.8 附注EventBus集成
  - subscribe 'substantive:adjudicated' 刷新附注取数
  - publish 'disclosure:note-text-updated' 通知外部
  - _Requirements: 14.6_

- [x] 6.9 C7前置驱动集成
  - subscribe 'control:c7-completed' → 更新H2A前置状态
  - _Requirements: 14.7_

### Phase 7: 测试（契约+PBT+Playwright E2E）

- [x] 7.1 契约测试完善
  - schema_contract: h2相关表结构验证
  - column_contract: checklist_responses item_id前缀"H2-"
  - componentType契约: 'h2-construction-in-progress' ∈ VALID_COMPONENT_TYPES
  - render策略契约: RENDERER_DISPATCH['h2-construction-in-progress']存在
  - _Requirements: 1.6-1.8_

- [x] 7.2 后端PBT (hypothesis)
  - test_h2_interest_cap_engine_pbt.py: 2分支利息资本化计算
  - test_h2_import_export_pbt.py: 导入→导出→导入round-trip一致性
  - test_h2_triangle_with_transfer_pbt.py: 三角勾稽含转固校验
  - _Requirements: 10.4, 14.3, 2.6_

- [x] 7.3 前端PBT (fast-check) — P1~P12全部验证
  - useH2FormulaEngine.pbt.spec.ts: P1/P2/P3/P4/P5/P8/P9/P10/P12
  - useH2InterestCapEngine.pbt.spec.ts: P6/P7/P11
  - _Requirements: design.md Correctness Properties_

- [x] 7.4 集成测试
  - H2-1审定表：编辑→公式计算→三角勾稽(含转固)→TB回写→EventBus
  - H2-2明细表：3区段Tab切换→行同步→合计→交叉验证H2-1
  - H2-5转固：五条件判定→延迟计算→联动H1→EventBus
  - H2-10/11利息资本化：分支切换→引擎计算→差异→联动L
  - 导入导出：导出模板→填写→导入→数据一致
  - _Requirements: 全部_

- [x] 7.5 Playwright E2E测试
  - 场景1: 打开H2底稿→切换到H2-1→编辑未审数→验证审定数自动计算→三角勾稽含转固显示
  - 场景2: 切换到H2-10→选择分支→验证利息资本化计算→切换到H2-11→数据独立
  - 场景3: 切换到H2-5→勾选五条件→验证自动判定→GtIndexChip跳转H1
  - 场景4: 双模式切换→HTML→OO→HTML→数据不丢失
  - 场景5: H2-2宽表→3区段Tab切换→行选中同步→添加工程→各区段可见
  - _Requirements: 全部_

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册+契约]
    P1 --> P2[Phase 2: 公式引擎+PBT]
    P2 --> P3[Phase 3: Composables]
    P3 --> P4[Phase 4: Vue组件]
    P1 --> P5[Phase 5: 后端]
    P4 --> P6[Phase 6: 集成]
    P5 --> P6
    P6 --> P7[Phase 7: 测试]

    subgraph Phase2内部
        2.1[FormulaEngine] --> 2.3~2.5[PBT P1~P5]
        2.2[InterestCapEngine] --> 2.8~2.9[PBT P6~P7]
    end

    subgraph Phase3内部
        3.1[FormData] --> 3.2[CrossSheet]
        3.1 --> 3.3[Adjudication]
        3.1 --> 3.4[Detail]
        3.2 --> 3.7[TransferCheck]
        3.2 --> 3.12[InterestCap]
        3.2 --> 3.14[Impairment]
        3.2 --> 3.16[Disclosure]
        3.7 --> 3.3
        3.12 --> 3.4
    end

    subgraph Phase4内部
        4.2[Adjudication.vue] --> 4.3[Detail.vue]
        4.7[TransferCheck.vue] --> 4.2
        4.13[InterestNoBorrow.vue] --> 4.3
    end

    subgraph Phase6内部
        6.1[主入口] --> 6.2[DualMode]
        6.1 --> 6.3[ImportExport]
        6.1 --> 6.4[抽凭集成]
        6.1 --> 6.5[OCR集成]
        6.1 --> 6.6[转固联动H1]
        6.1 --> 6.7[利息联动L]
        6.1 --> 6.8[附注EventBus]
        6.1 --> 6.9[C7前置]
    end
```
