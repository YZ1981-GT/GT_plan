# Implementation Plan: H1 固定资产底稿专属HTML精美组件

## Overview

H1固定资产底稿专属组件`h1-fixed-assets`。H循环最大单底稿（26有效sheet/1 xlsx/~280+公式）。

主入口 GtH1FixedAssets.vue（sheetName v-if分发，defineAsyncComponent lazy）+ 22个子组件 + 21个composable + 后端4个py文件。

科目：1601固定资产（借方/资产类）+ 1602累计折旧（贷方/资产备抵类）
公式特征：期末=期初+借方-贷方（资产类）；审定=未审+AJE+RJE；三角勾稽（期末=期初+增加-减少）

## Tasks

### Phase 0: 双源输入验证

- [ ] 0.1 openpyxl脚本读取H1固定资产.xlsx全部26 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 产出：h1_structure_summary.json（权威列头+公式清单）
  - 验证：26 sheet结构与本spec描述一致
  - _Requirements: 双源输入流程_

- [ ] 0.2 H固定资产循环底稿模板库md交叉验证
  - 核对：审计目标/程序清单/联动关系/认定对应/交叉引用
  - 冲突解决：列名以xlsx为准，联动方向以md为准
  - 产出：h1_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - 在 `wp_code_overrides.json` 中将H1/H1-1~H1-20/H1A映射为'h1-fixed-assets'
  - 在 `VALID_COMPONENT_TYPES` 中注册'h1-fixed-assets'
  - 在 `htmlRendererRegistry.ts` 中注册 'h1-fixed-assets' → GtH1FixedAssets 映射
  - 创建 `GtH1FixedAssets.vue` 主入口骨架（sheetName prop v-if分发 + defineAsyncComponent lazy + selfLoad）
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9_

- [ ] 1.2 编写注册契约测试
  - htmlRendererRegistry.spec.ts 验证'h1-fixed-assets'已注册
  - VALID_COMPONENT_TYPES契约验证
  - wp_code_overrides契约验证H1/H1-1~H1-20映射
  - RENDERER_DISPATCH注册验证
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+PBT

- [ ] 2.1 创建 `composables/useH1FormulaEngine.ts`，实现全部纯函数
  - `calcAuditedAmount(unadj, aje, rje)` → 审定=未审+AJE+RJE
  - `calcAssetEndBalance(begin, debit, credit)` → 资产类期末=期初+借方-贷方
  - `calcContraEndBalance(begin, debit, credit)` → 备抵类期末=期初+贷方-借方
  - `calcTriangleReconciliation(begin, increase, decrease, end)` → 三角勾稽差额
  - `calcNetValue(cost, accDep, impairment)` → 净值=原值-折旧-减值
  - `calcChangeRate(current, prior)` → 变动率
  - `calcSubtotal(arr)` → 合计=SUM
  - `calcProportion(item, total)` → 占比
  - `calcNewRate(netValue, cost)` → 成新率=净值/原值
  - `calcDisposalGainLoss(income, netValue, disposalCost)` → 处置损益
  - `calcPriceDiffRate(transPrice, fairValue)` → 关联价格差异率
  - `calcTitleDiff(bookValue, certValue)` → 权属差异
  - `calcLeaseReturnRate(netIncome, cost)` → 租赁收益率
  - _Requirements: 1.5, 2.3-2.7, 7.2, 9.3, 14.7, 15.2, 15.5_

- [ ] 2.2 创建 `composables/useH1DepreciationEngine.ts`，实现折旧纯函数
  - `calcStraightLine(cost, salvageRate, usefulLife)` → 直线法月折旧
  - `calcDoubleDeclining(netValue, usefulLife, elapsedMonths, totalMonths)` → 双倍余额递减
  - `calcSumOfYears(cost, salvageRate, usefulLife, remainingYears)` → 年数总和法
  - `calcUnitsOfProduction(cost, salvageRate, totalUnits, currentUnits)` → 工作量法
  - `calcDepreciationWithImpairment(cost, salvageRate, usefulLife, impairment, elapsedMonths)` → 含减值折旧
  - `calcDcfPresentValue(cashFlows, discountRate)` → DCF现值
  - `calcTerminalValue(perpetuityCF, discountRate, growthRate)` → 终值
  - `isMonotonicallyIncreasing(monthlyAccumulated, disposalMonths)` → 单调性校验
  - _Requirements: 11.5, 13.4_

- [ ]* 2.3 编写 Property P1 PBT：资产类审定数公式链
  - 生成器：fc.float({min:-1e9, max:1e9}) × 3 (unadj/aje/rje)
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: h1-fixed-assets, Property P1: 资产类审定数公式链正确性**

- [ ]* 2.4 编写 Property P2 PBT：资产类期末余额
  - 生成器：fc.float({min:0, max:1e9}) × 3
  - 断言：calcAssetEndBalance(b, d, c) === b + d - c
  - **Feature: h1-fixed-assets, Property P2: 资产类期末余额公式（借方科目）**

- [ ]* 2.5 编写 Property P3 PBT：备抵类期末余额
  - 生成器：fc.float({min:0, max:1e9}) × 3
  - 断言：calcContraEndBalance(b, d, c) === b + c - d
  - **Feature: h1-fixed-assets, Property P3: 备抵类期末余额公式（贷方科目）**

- [ ]* 2.6 编写 Property P4 PBT：三角勾稽恒等式
  - 生成器：fc.float({min:0, max:1e9}) × 3, end=begin+increase-decrease
  - 断言：calcTriangleReconciliation(b, i, d, b+i-d) === 0
  - **Feature: h1-fixed-assets, Property P4: 三角勾稽恒等式**

- [ ]* 2.7 编写 Property P5 PBT：合计行恒等
  - 生成器：fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:50})
  - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
  - **Feature: h1-fixed-assets, Property P5: 合计行恒等于明细行之和**

- [ ]* 2.8 编写 Property P6 PBT：直线法折旧正确性
  - 生成器：fc.float({min:1, max:1e8}), fc.float({min:0, max:0.99}), fc.integer({min:1, max:50})
  - 断言：calcStraightLine(cost, rate, life) === cost×(1-rate)/life/12
  - **Feature: h1-fixed-assets, Property P6: 直线法折旧公式正确性**

- [ ]* 2.9 编写 Property P7 PBT：双倍余额递减法（最后两年转直线）
  - 生成器：fc.float({min:1e4, max:1e8}), fc.float({min:0, max:0.1}), fc.integer({min:3, max:30})
  - 断言：最后24个月=(netValue-salvage)/24；前期=netValue×2/usefulLife/12
  - **Feature: h1-fixed-assets, Property P7: 双倍余额递减法折旧正确性**

- [ ]* 2.10 编写 Property P8 PBT：年数总和法折旧逐年递减
  - 生成器：fc.float({min:1e4, max:1e8}), fc.float({min:0, max:0.1}), fc.integer({min:2, max:30})
  - 断言：第n年折旧 > 第n+1年折旧（严格递减）
  - **Feature: h1-fixed-assets, Property P8: 年数总和法折旧逐年递减**

- [ ]* 2.11 编写 Property P9 PBT：折旧累计单调递增
  - 生成器：fc.array(fc.float({min:0.01, max:1e6}), {minLength:2, maxLength:12})
  - 断言：isMonotonicallyIncreasing(累计数组, []) === true
  - **Feature: h1-fixed-assets, Property P9: 折旧累计单调递增校验**

- [ ]* 2.12 编写 Property P10 PBT：DCF现值计算
  - 生成器：fc.array(fc.float({min:1, max:1e6}), {minLength:1, maxLength:10}), fc.float({min:0.01, max:0.3})
  - 断言：calcDcfPresentValue(cfs, r) === Σ(cf_i/(1+r)^(i+1))
  - **Feature: h1-fixed-assets, Property P10: DCF现值计算正确性**

- [ ]* 2.13 编写 Property P11 PBT：可收回金额MAX选取
  - 生成器：fc.float({min:0, max:1e8}) × 3
  - 断言：recoverable === Math.max(fairValue-disposalCost, dcfValue)
  - **Feature: h1-fixed-assets, Property P11: 可收回金额=MAX(公允-处置费,DCF现值)**

- [ ]* 2.14 编写 Property P12 PBT：减值金额非负且≤账面
  - 生成器：fc.float({min:0, max:1e8}) × 2
  - 断言：impairment=max(book-recoverable,0) ∈ [0, bookValue]
  - **Feature: h1-fixed-assets, Property P12: 减值金额非负且不超过账面价值**

- [ ]* 2.15 编写 Property P13 PBT：折旧分配合计=总额
  - 生成器：自定义归一化比例数组 + fc.float({min:1, max:1e8})
  - 断言：各部门分配额之和 === 折旧总额（精度0.01）
  - **Feature: h1-fixed-assets, Property P13: 折旧分配合计=折旧总额**

- [ ]* 2.16 编写 Property P14 PBT：借贷平衡检查
  - 生成器：fc.array(fc.record({debit: fc.float({min:0}), credit: fc.float({min:0})}), {minLength:1, maxLength:20})
  - 断言：isBalanced === (SUM(debit) === SUM(credit))
  - **Feature: h1-fixed-assets, Property P14: 借贷平衡检查**

- [ ]* 2.17 编写 Property P15 PBT：处置损益公式
  - 生成器：fc.float({min:0, max:1e8}) × 3
  - 断言：calcDisposalGainLoss(inc, nv, cost) === inc - nv - cost
  - **Feature: h1-fixed-assets, Property P15: 处置损益公式正确性**

- [ ]* 2.18 编写 Property P16 PBT：经营租出收益率
  - 生成器：fc.float({min:-1e6, max:1e6}), fc.float({min:1, max:1e8})
  - 断言：calcLeaseReturnRate(ni, c) === ni/c×100
  - **Feature: h1-fixed-assets, Property P16: 经营租出收益率公式**

- [ ]* 2.19 编写 Property P17 PBT：权属差异计算
  - 生成器：fc.float({min:0, max:1e9}) × 2
  - 断言：calcTitleDiff(b, c) === b - c
  - **Feature: h1-fixed-assets, Property P17: 权属差异=账面-证载**

### Phase 3: FormData/CrossSheet composables

- [ ] 3.1 创建 `composables/useH1FormData.ts`
  - allResponses Map加载 + saveImmediate + debouncedSave(2s) + saveBatch
  - writebackTrialBalance（科目1601借方+1602贷方）
  - selfLoad逻辑（render-config?force_component_type=h1-fixed-assets）
  - projectContext加载（含business_category/applicable_standards）
  - TB自动取数unadjusted_amount→审定表未审数
  - _Requirements: 19.1-19.9_

- [ ] 3.2 创建 `composables/useH1CrossSheet.ts`
  - detailTotals computed（H1-2按分类聚合原值/折旧/减值）
  - adjudicationFromDetail computed（H1-2合计→H1-1）
  - depreciationForAlloc computed（H1-12→H1-13按分类）
  - idleAssetsForImpairment computed（H1-4→H1-14）
  - disclosureAutoFill computed（H1-1/H1-4/H1-19→附注各子节）
  - adjustmentSync computed（H1-3 AJE/RJE→H1-1）
  - _Requirements: 17.1-17.9_

- [ ] 3.3 创建 `composables/useH1Adjudication.ts`
  - 双区块固定行（原值分类行+小计 / 折旧分类行+小计 / 净值合计）
  - 三角勾稽实时校验（原值层+折旧层）
  - TB取数行 + 差异行 + 交叉验证H1-2
  - updateCell + publishAdjudicated（EventBus → TB回写）
  - _Requirements: 2.1-2.12_

- [ ] 3.4 创建 `composables/useH1Detail.ts`
  - DetailRow 54列完整定义 + 4区段分组配置
  - 行内公式（原值期末/折旧期末/减值期末/净值）
  - subtotalRow + crossValidation（vs H1-1）
  - addRow(弹窗命名)/removeRow/updateCell
  - _Requirements: 3.1-3.12_

- [ ] 3.5 创建 `composables/useH1Adjustment.ts`
  - H1AdjustmentRow 13列 + rows + debitTotal/creditTotal/isBalanced
  - addRow/removeRow/updateCell + publishAdjustment + pushToA13
  - _Requirements: 4.1-4.8_

- [ ] 3.6 创建 `composables/useH1IdleCheck.ts`
  - IdleAssetRow 12列 + 闲置统计computed + 减值迹象判定
  - addRow(弹窗命名)/removeRow + 汇总统计
  - _Requirements: 5.1-5.8_

- [ ] 3.7 创建 `composables/useH1PolicyCheck.ts`
  - CAS4六段落结构定义 + 各段conclusion(Y/N/NA)
  - 折旧参数表（分类×方法×年限×残值率）
  - completionProgress computed
  - _Requirements: 6.1-6.7_

- [ ] 3.8 创建 `composables/useH1Analysis.ts`
  - 结构分析+变动分析双区域 + 8公式自动计算
  - 从H1-2 crossSheet取数 + 阈值异常判定
  - _Requirements: 7.1-7.8_

- [ ] 3.9 创建 `composables/useH1AdditionCheck.ts`
  - AdditionRow 24列 + 抽样参数 + 汇总统计
  - 集成voucher-sampling-engine + OCR端点
  - _Requirements: 8.1-8.10_

- [ ] 3.10 创建 `composables/useH1DisposalCheck.ts`
  - DisposalRow 27列 + 处置损益公式 + 汇总
  - 集成voucher-sampling-engine + EventBus联动H10
  - _Requirements: 9.1-9.11_

- [ ] 3.11 创建 `composables/useH1Stocktake.ts`
  - 计划/检查/小结三阶段共用状态
  - FixedAssetStocktakeDialog集成
  - 盘盈/盘亏自动汇总 + 账实相符率
  - _Requirements: 10.1-10.10_

- [ ] 3.12 创建 `composables/useH1Depreciation.ts`
  - depreciationBranch状态(A/B/C) + 3分支共用行数据
  - 调用DepreciationEngine计算 + 月度累计 + 差异
  - 从H1-2取数(资产参数) + EventBus发布结果
  - _Requirements: 11.1-11.13_

- [ ] 3.13 创建 `composables/useH1DepreciationAlloc.ts`
  - AllocRow 11列 + 分配比例计算 + 核对行
  - 从H1-12取数 + D5/K8/K9 GtIndexChip跳转
  - EventBus发布'h1:depreciation-allocated'
  - _Requirements: 12.1-12.8_

- [ ] 3.14 创建 `composables/useH1Impairment.ts`
  - 减值迹象6项判断 + 测算表 + DCF模型
  - 敏感性分析矩阵 + 可收回金额MAX选取
  - 从H1-4取数闲置资产列表
  - _Requirements: 13.1-13.10_

- [ ] 3.15 创建 `composables/useH1TitleCheck.ts`
  - BuildingRow 22列 + VehicleRow 18列
  - 权属异常判定 + 抵押统计 + 差异计算
  - _Requirements: 14.1-14.9_

- [ ] 3.16 创建 `composables/useH1LeaseCheck.ts`
  - RelatedPartyRow 15列 + OperatingLeaseRow 25列(23公式) + FinanceLeaseRow 22列
  - 价格差异率 + 租赁净收益 + 收益率
  - _Requirements: 15.1-15.10_

- [ ] 3.17 创建 `composables/useH1Disclosure.ts`
  - variant参数（listed/soe）双版本共用
  - 多子节结构 + 跨sheet自动取数 + 动态行
  - applicable_standards判断显隐
  - EventBus 'disclosure:note-text-updated'
  - _Requirements: 16.1-16.10_

### Phase 4: 各sheet Vue组件

- [ ] 4.1 创建 `h1/core/H1TabIndex.vue`（~150行）
  - 底稿目录（26行进度条+完成状态）
  - _Requirements: 1.2_

- [ ] 4.2 创建 `h1/core/H1TabAdjudication.vue`（~450行）
  - 双区块el-table + 三角勾稽校验红色高亮
  - 审计说明/结论 + AI + 💬复核 + GtIndexChip→H1-6
  - _Requirements: 2.1-2.12, 19.5-19.6_

- [ ] 4.3 创建 `h1/core/H1TabDetail.vue`（~500行）
  - 4区段Tab切换 + 行同步 + 固定列 + 虚拟滚动
  - 合计行 + 交叉验证H1-1 + 导入导出
  - _Requirements: 3.1-3.12_

- [ ] 4.4 创建 `h1/core/H1TabAdjustment.vue`（~250行）
  - el-table 13列 + 借贷平衡 + 推送A13
  - _Requirements: 4.1-4.8_

- [ ] 4.5 创建 `h1/core/H1TabAnalysis.vue`（~300行）
  - 双区域(结构+变动) + 阈值高亮 + GtIndexChip
  - _Requirements: 7.1-7.8_

- [ ] 4.6 创建 `h1/core/H1TabDisclosureListed.vue` + `H1TabDisclosureSoe.vue`（各~350行）
  - 多子节卡片 + 跨sheet浅蓝色 + 动态行 + 合计
  - _Requirements: 16.1-16.10_

- [ ] 4.7 创建 `h1/inspection/H1TabIdleCheck.vue`（~250行）
  - el-table 12列 + 减值迹象高亮 + GtIndexChip→H1-14
  - _Requirements: 5.1-5.8_

- [ ] 4.8 创建 `h1/inspection/H1TabPolicyCheck.vue`（~400行）
  - CAS4六段落卡片 + 进度条 + 引导区 + AI + 💬复核
  - _Requirements: 6.1-6.7_

- [ ] 4.9 创建 `h1/inspection/H1TabAdditionCheck.vue`（~400行）
  - 双区域(抽样参数+明细) + 固定列+滚动列 + OCR📎 + 抽凭
  - _Requirements: 8.1-8.10_

- [ ] 4.10 创建 `h1/inspection/H1TabDisposalCheck.vue`（~400行）
  - 双区域 + 借方/贷方视觉分组 + 处置损益公式 + GtIndexChip→H10
  - _Requirements: 9.1-9.11_

- [ ] 4.11 创建 `h1/inspection/H1TabTitleBuilding.vue`（~350行）
  - el-table 22列 + 权属异常红色 + 抵押黄色 + 汇总
  - _Requirements: 14.1-14.9_

- [ ] 4.12 创建 `h1/inspection/H1TabTitleVehicle.vue`（~300行）
  - el-table 18列 + 所有人异常高亮 + 年检状态
  - _Requirements: 14.1-14.9_

- [ ] 4.13 创建 `h1/inspection/H1TabRelatedParty.vue`（~300行）
  - el-table 15列 + 价格差异率>10%红色 + GtIndexChip
  - _Requirements: 15.1-15.3, 15.7-15.10_

- [ ] 4.14 创建 `h1/inspection/H1TabOperatingLease.vue`（~350行）
  - el-table 25列(23公式) + 收益率 + 市场租金对比
  - _Requirements: 15.4-15.5, 15.7-15.9_

- [ ] 4.15 创建 `h1/inspection/H1TabFinanceLease.vue`（~300行）
  - el-table 22列 + 5项分类判断 + 利息分摊
  - _Requirements: 15.6-15.8_

- [ ] 4.16 创建 `h1/stocktake/H1TabStocktakePlan.vue`（~300行）
  - 3区域(基本信息+样本选取+时间安排) + 引导区
  - _Requirements: 10.1, 10.8_

- [ ] 4.17 创建 `h1/stocktake/H1TabStocktakeCheck.vue`（~400行）
  - el-table 17列 + 盘亏红色 + 汇总 + 导入导出
  - _Requirements: 10.2, 10.4-10.5, 10.10_

- [ ] 4.18 创建 `h1/stocktake/H1TabStocktakeSummary.vue`（~350行）
  - 段落型+表格(仪表板+盘盈表+盘亏表+结论)
  - _Requirements: 10.3, 10.7, 10.9_

- [ ] 4.19 创建 `h1/depreciation/H1TabDepreciationStraight.vue`（~450行）
  - 28列(62公式) + 分支选择器 + 月度明细 + 差异高亮
  - _Requirements: 11.1-11.2, 11.6-11.13_

- [ ] 4.20 创建 `h1/depreciation/H1TabDepreciationImpair.vue`（~400行）
  - 含减值(86公式) + 减值影响列 + 差异
  - _Requirements: 11.1, 11.3, 11.6-11.13_

- [ ] 4.21 创建 `h1/depreciation/H1TabDepreciationMulti.vue`（~420行）
  - 多次减值(94公式) + 多时点 + 剩余年限
  - _Requirements: 11.1, 11.4, 11.6-11.13_

- [ ] 4.22 创建 `h1/depreciation/H1TabDepreciationAlloc.vue`（~300行）
  - 11列 + 分配比例 + 核对行 + GtIndexChip→D5/K8/K9
  - _Requirements: 12.1-12.8_

- [ ] 4.23 创建 `h1/impairment/H1TabImpairment.vue`（~400行）
  - 双区域(迹象判断+测算表) + 方法论上下文 + GtIndexChip→H1-15
  - _Requirements: 13.1-13.2, 13.6-13.10_

- [ ] 4.24 创建 `h1/impairment/H1TabRecoverable.vue`（~400行）
  - DCF模型(假设+现金流预测+折现) + 敏感性矩阵
  - _Requirements: 13.3-13.5_

### Phase 5: 后端（render策略+import_export+ai_generate+折旧引擎endpoint）

- [ ] 5.1 创建 `_h1_fixed_assets.py` render策略
  - 注册RENDERER_DISPATCH['h1-fixed-assets']
  - render函数：加载allResponses + projectContext + TB数据(1601+1602)
  - 返回html_data结构（sections/rows/formulas/crossSheetRefs）
  - _Requirements: 1.1, 19.3_

- [ ] 5.2 创建 `_h1_import_export.py` 导入导出3端点
  - POST /h1/export-template → 空白结构xlsx（H1-2按4区段分sheet）
  - POST /h1/export-data → 当前数据xlsx（含公式结果）
  - POST /h1/import-data → 解析xlsx→验证→写入checklist_responses
  - StreamingResponse中文文件名RFC5987编码
  - _Requirements: 18.3-18.4, 18.7-18.8_

- [ ] 5.3 创建 `_h1_ai_generate.py` AI生成8 section
  - adj-note / adj-conclusion / policy-evaluation / analysis-change
  - depreciation-summary / impairment-conclusion / stocktake-summary / disposal-note
  - 各section使用对应sheet数据+项目上下文生成
  - _Requirements: 18.5-18.6_

- [ ] 5.4 创建 `_h1_depreciation_engine.py` 折旧引擎端点
  - POST /h1/depreciation/calculate → 批量计算（4方法+含减值+多次减值）
  - POST /h1/depreciation/validate → 验证账面vs测算差异
  - 纯函数实现（与前端对等逻辑）
  - _Requirements: 11.5_

- [ ] 5.5 创建 `_h1_fixed_assets.py` auto_data_resolver
  - h1_tb_unadjusted: 从trial_balance取科目1601+1602未审数
  - h1_depreciation_monthly: 从tb_ledger取月度折旧发生额
  - 注册到_REGISTRY
  - _Requirements: 19.8_

### Phase 6: 集成（主入口+双模式+导入导出）

- [ ] 6.1 完成 GtH1FixedAssets.vue 主入口集成
  - sheetName regex分发全部22个子组件
  - defineAsyncComponent lazy（除H1TabIndex外）
  - provide openReviewDialog给子组件inject
  - useVersionTrail集成（autoSnapshot on save）
  - _Requirements: 1.2-1.3, 17.1_

- [ ] 6.2 创建 `composables/useH1DualMode.ts`
  - HTML↔OnlyOffice el-segmented切换
  - OO健康检查(`health.data?.data?.healthy`双层兼容)
  - 切换前autoSave
  - _Requirements: 18.1-18.2_

- [ ] 6.3 创建 `composables/useH1ImportExport.ts`
  - el-dropdown三级UI + axios请求（非fetch）
  - H1-2宽表按4区段分sheet导出
  - 导入xlsx解析+验证+确认对话+写入
  - _Requirements: 18.3-18.4, 18.7-18.8_

- [ ] 6.4 H1-7/H1-8 抽凭引擎集成
  - GtVoucherSamplingEngine dialog→样本填入AdditionCheck/DisposalCheck
  - _Requirements: 8.4, 9.6_

- [ ] 6.5 H1-7 行级OCR集成
  - 📎列POST contract-ocr端点 → ElMessageBox确认 → merge字段
  - _Requirements: 8.5_

- [ ] 6.6 附注EventBus集成
  - subscribe 'substantive:adjudicated' 刷新附注取数
  - publish 'disclosure:note-text-updated' 通知外部
  - _Requirements: 16.10, 17.9_

- [ ] 6.7 折旧分配跨底稿联动
  - H1-13 publish 'h1:depreciation-allocated'
  - GtIndexChip跳转D5/K8/K9
  - _Requirements: 12.6-12.7, 17.3_

- [ ] 6.8 H1-8处置联动H10
  - publish 'h1:disposal-completed'
  - GtIndexChip跳转H10
  - _Requirements: 9.7, 9.9, 17.4_

- [ ] 6.9 C6前置驱动集成
  - subscribe 'control:c6-completed' → 更新H1A前置状态
  - _Requirements: 17.5_

### Phase 7: 测试（契约+PBT+Playwright E2E）

- [ ] 7.1 契约测试完善
  - schema_contract: h1_fixed_assets相关表结构验证
  - column_contract: checklist_responses item_id前缀"H1-"
  - componentType契约: 'h1-fixed-assets' ∈ VALID_COMPONENT_TYPES
  - render策略契约: RENDERER_DISPATCH['h1-fixed-assets']存在
  - _Requirements: 1.6-1.8_

- [ ] 7.2 后端PBT (hypothesis)
  - test_h1_depreciation_engine_pbt.py: 4种折旧方法+含减值+多次减值
  - test_h1_import_export_pbt.py: 导入→导出→导入round-trip一致性
  - test_h1_triangle_reconciliation_pbt.py: 三角勾稽校验+备抵方向
  - _Requirements: 11.5, 18.3, 2.7_

- [ ] 7.3 前端PBT (fast-check) — P1~P17全部验证
  - useH1FormulaEngine.pbt.spec.ts: P1/P2/P3/P4/P5/P15/P16/P17
  - useH1DepreciationEngine.pbt.spec.ts: P6/P7/P8/P9/P10/P11/P12/P13
  - useH1CoreComposables.pbt.spec.ts: P14(借贷平衡)
  - _Requirements: design.md Correctness Properties_

- [ ] 7.4 集成测试
  - H1-1审定表：编辑→公式计算→三角勾稽→TB回写→EventBus
  - H1-2明细表：4区段Tab切换→行同步→合计→交叉验证H1-1
  - H1-12折旧：3分支切换→引擎计算→差异→分配→EventBus
  - H1-14减值：迹象判断→DCF计算→可收回金额→减值金额
  - 导入导出：导出模板→填写→导入→数据一致
  - _Requirements: 全部_

- [ ] 7.5 Playwright E2E测试
  - 场景1: 打开H1底稿→切换到H1-1→编辑未审数→验证审定数自动计算→三角勾稽显示
  - 场景2: 切换到H1-12→选择分支→验证折旧计算→切换分支→数据保持
  - 场景3: 切换到H1-7→添加样本→OCR上传→确认填入→汇总更新
  - 场景4: 双模式切换→HTML→OO→HTML→数据不丢失
  - 场景5: H1-2宽表→4区段Tab切换→行选中同步→添加行→各区段可见
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
        2.2[DepreciationEngine] --> 2.8~2.15[PBT P6~P13]
    end

    subgraph Phase3内部
        3.1[FormData] --> 3.2[CrossSheet]
        3.1 --> 3.3[Adjudication]
        3.1 --> 3.4[Detail]
        3.2 --> 3.12[Depreciation]
        3.2 --> 3.14[Impairment]
        3.2 --> 3.17[Disclosure]
        3.12 --> 3.13[DepreciationAlloc]
        3.6[IdleCheck] --> 3.14
    end

    subgraph Phase4内部
        4.2[Adjudication.vue] --> 4.3[Detail.vue]
        4.19[DepStraight.vue] --> 4.22[DepAlloc.vue]
        4.7[IdleCheck.vue] --> 4.23[Impairment.vue]
    end

    subgraph Phase6内部
        6.1[主入口] --> 6.2[DualMode]
        6.1 --> 6.3[ImportExport]
        6.1 --> 6.4[抽凭集成]
        6.1 --> 6.5[OCR集成]
        6.1 --> 6.6[附注EventBus]
        6.1 --> 6.7[折旧联动]
        6.1 --> 6.8[处置联动H10]
        6.1 --> 6.9[C6前置]
    end
```
