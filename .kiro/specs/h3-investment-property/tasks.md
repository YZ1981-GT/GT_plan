# Implementation Plan: H3 投资性房地产底稿专属HTML精美组件

## Overview

H3投资性房地产底稿专属组件`h3-investment-property`。H循环第三大底稿（22有效sheet/1 xlsx/~230+公式）。

主入口 GtH3InvestmentProperty.vue（sheetName v-if分发 + measurementModel双计量模式，defineAsyncComponent lazy）+ 20个子组件 + 21个composable + 后端4个py文件。

科目：1503投资性房地产（借方/资产类）+ 成本模式下1504累计折旧（贷方/资产备抵类）
公式特征：双计量模式(成本/公允价值)控制显隐；互转三方向25公式；租金27公式

## Tasks

### Phase 0: 双源输入验证

- [ ] 0.1 openpyxl脚本读取H3投资性房地产.xlsx全部22 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 产出：h3_structure_summary.json（权威列头+公式清单）
  - 验证：22 sheet结构与本spec描述一致
  - _Requirements: 双源输入流程_

- [ ] 0.2 H固定资产循环底稿模板库md交叉验证
  - 核对：审计目标/程序清单/联动关系/认定对应/交叉引用
  - 冲突解决：列名以xlsx为准，联动方向以md为准
  - 产出：h3_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - 在 `wp_code_overrides.json` 中将H3/H3-1~H3-14/H3A映射为'h3-investment-property'
  - 在 `VALID_COMPONENT_TYPES` 中注册'h3-investment-property'
  - 在 `htmlRendererRegistry.ts` 中注册 'h3-investment-property' → GtH3InvestmentProperty 映射
  - 创建 `GtH3InvestmentProperty.vue` 主入口骨架（sheetName prop v-if分发 + measurementModel + defineAsyncComponent lazy + selfLoad）
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9, 1.11_

- [ ] 1.2 编写注册契约测试
  - htmlRendererRegistry.spec.ts 验证'h3-investment-property'已注册
  - VALID_COMPONENT_TYPES契约验证
  - wp_code_overrides契约验证H3/H3-1~H3-14映射
  - RENDERER_DISPATCH注册验证
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+PBT

- [ ] 2.1 创建 `composables/useH3FormulaEngine.ts`，实现全部纯函数
  - `calcAuditedAmount(unadj, aje, rje)` → 审定=未审+AJE+RJE
  - `calcAssetEndBalance(begin, debit, credit)` → 资产类期末=期初+借方-贷方
  - `calcContraEndBalance(begin, debit, credit)` → 备抵类期末=期初+贷方-借方
  - `calcCostTriangle(begin, increase, decrease, transfer, end)` → 成本模式三角勾稽差额
  - `calcFairEndBalance(begin, increase, decrease, transfer, fairChange)` → 公允模式期末
  - `calcFairValueChange(endFair, beginFair)` → 公允价值变动
  - `calcSubtotal(arr)` → 合计=SUM
  - `calcRentalIncome(monthlyRent, months, vacancyRate)` → 年租金
  - `calcRentalYield(annualRent, bookValue)` → 租金回报率
  - `calcVacancyLoss(monthlyRent, vacantMonths)` → 空置损失
  - `calcPerSqmRent(monthlyRent, area)` → 每平米租金
  - `calcStraightLineDepreciation(cost, salvageRate, usefulLife)` → 月折旧（成本模式）
  - `calcDepreciationWithImpairment(cost, salvageRate, usefulLife, impairment, elapsed)` → 含减值折旧
  - `calcDcfPresentValue(cashFlows, discountRate)` → DCF现值
  - `isBalanced(entries)` → 借贷平衡检查
  - _Requirements: 1.5, 2.4-2.6, 8.3-8.4, 14.2_

- [ ] 2.2 创建 `composables/useH3TransferEngine.ts`，实现互转纯函数
  - `calcSelfToInvestFair(bookValue, fairValue)` → 自用→投资(公允): {oci, pl}
  - `calcInvestToSelf(fairValue)` → 投资→自用: 公允=入账
  - `calcCipToInvestCost(cipBookValue)` → 在建→投资(成本): 账面=入账
  - `calcCipToInvestFair(cipBookValue, fairValue)` → 在建→投资(公允): {entryValue, diff}
  - `calcTransferDiff(transferOut, transferIn)` → 转出=转入差额
  - `calcTitleDiff(bookValue, certValue)` → 产权差异
  - _Requirements: 7.2-7.5, 12.2_

- [ ]* 2.3 编写 Property P1 PBT：审定数公式链
  - 生成器：fc.float({min:-1e9, max:1e9}) × 3 (unadj/aje/rje)
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: h3-investment-property, Property P1: 审定数公式链正确性**

- [ ]* 2.4 编写 Property P2 PBT：资产类期末余额（成本模式）
  - 生成器：fc.float({min:0, max:1e9}) × 3
  - 断言：calcAssetEndBalance(b, d, c) === b + d - c
  - **Feature: h3-investment-property, Property P2: 资产类期末余额（成本模式）**

- [ ]* 2.5 编写 Property P3 PBT：公允价值模式期末
  - 生成器：fc.float({min:-1e9, max:1e9}) × 5
  - 断言：calcFairEndBalance(b, i, d, t, fc) === b + i - d + t + fc
  - **Feature: h3-investment-property, Property P3: 公允价值模式期末公式**

- [ ]* 2.6 编写 Property P4 PBT：三角勾稽（成本模式）
  - 生成器：fc.float({min:0, max:1e9}) × 4, end=begin+increase-decrease+transfer
  - 断言：calcCostTriangle(b, i, d, t, b+i-d+t) === 0
  - **Feature: h3-investment-property, Property P4: 成本模式三角勾稽**

- [ ]* 2.7 编写 Property P5 PBT：合计行恒等
  - 生成器：fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:50})
  - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
  - **Feature: h3-investment-property, Property P5: 合计行恒等**

- [ ]* 2.8 编写 Property P6 PBT：互转公允值（自用→投资）
  - 生成器：fc.float({min:0, max:1e9}) × 2 (bookValue, fairValue)
  - 断言：result.oci === max(fair-book, 0) 且 result.pl === min(fair-book, 0)
  - **Feature: h3-investment-property, Property P6: 自用→投资互转公允值处理**

- [ ]* 2.9 编写 Property P7 PBT：互转账面值（投资→自用）
  - 生成器：fc.float({min:1, max:1e9})
  - 断言：calcInvestToSelf(fairValue) === fairValue
  - **Feature: h3-investment-property, Property P7: 投资→自用互转用公允作入账**

- [ ]* 2.10 编写 Property P8 PBT：折旧公式（成本模式直线法）
  - 生成器：fc.float({min:1, max:1e8}), fc.float({min:0, max:0.99}), fc.integer({min:1, max:50})
  - 断言：calcStraightLineDepreciation(cost, rate, life) === cost×(1-rate)/life/12
  - **Feature: h3-investment-property, Property P8: 成本模式直线法折旧**

- [ ]* 2.11 编写 Property P9 PBT：公允价值变动损益
  - 生成器：fc.float({min:0, max:1e9}) × 2
  - 断言：calcFairValueChange(end, begin) === end - begin
  - **Feature: h3-investment-property, Property P9: 公允价值变动损益公式**

- [ ]* 2.12 编写 Property P10 PBT：租金收入测算
  - 生成器：fc.float({min:1, max:1e6}), fc.integer({min:1, max:12}), fc.float({min:0, max:0.99})
  - 断言：calcRentalIncome(rent, months, vacancy) === rent × months × (1-vacancy)
  - **Feature: h3-investment-property, Property P10: 租金收入测算公式**

- [ ]* 2.13 编写 Property P11 PBT：DCF现值（仅成本模式）
  - 生成器：fc.array(fc.float({min:1, max:1e6}), {minLength:1, maxLength:10}), fc.float({min:0.01, max:0.3})
  - 断言：calcDcfPresentValue(cfs, r) === Σ(cf_i/(1+r)^(i+1))
  - **Feature: h3-investment-property, Property P11: DCF现值计算**

- [ ]* 2.14 编写 Property P12 PBT：产权差异
  - 生成器：fc.float({min:0, max:1e9}) × 2
  - 断言：calcTitleDiff(book, cert) === book - cert
  - **Feature: h3-investment-property, Property P12: 产权差异=账面-证载**

- [ ]* 2.15 编写 Property P13 PBT：measurement_model filter幂等性
  - 生成器：fc.constantFrom('cost','fair_value'), fc.array(fc.constantFrom('cost','fair_value'), {minLength:1, maxLength:10})
  - 断言：连续切换N次后最终状态=最后一次设定值（幂等）
  - **Feature: h3-investment-property, Property P13: 计量模式切换幂等性**

- [ ]* 2.16 编写 Property P14 PBT：借贷平衡
  - 生成器：fc.array(fc.record({debit: fc.float({min:0}), credit: fc.float({min:0})}), {minLength:1, maxLength:20})
  - 断言：isBalanced === (SUM(debit) === SUM(credit))
  - **Feature: h3-investment-property, Property P14: 借贷平衡检查**

### Phase 3: FormData/CrossSheet composables

- [ ] 3.1 创建 `composables/useH3FormData.ts`
  - allResponses Map加载 + saveImmediate + debouncedSave(2s) + saveBatch
  - writebackTrialBalance（成本模式科目1503+1504；公允模式科目1503）
  - selfLoad逻辑（render-config?force_component_type=h3-investment-property）
  - projectContext加载 + TB自动取数
  - _Requirements: 16.8-16.9_

- [ ] 3.2 创建 `composables/useH3MeasurementModel.ts`
  - measurementModel ref('cost'|'fair_value') + 持久化到checklist_responses
  - visibleSheets computed（根据模式返回可见sheet编码列表）
  - isSheetVisible(sheetCode) → boolean
  - switchModel(target) → 幂等切换 + 不丢数据
  - _Requirements: 1.11-1.12, 16.5, 16.11_

- [ ] 3.3 创建 `composables/useH3CrossSheet.ts`
  - detailTotals computed（H3-2按分类聚合）
  - adjudicationFromDetail computed（H3-2合计→H3-1）
  - transferSummary computed（H3-6互转金额→H3-1转换列）
  - rentalForDisclosure computed（H3-14→附注）
  - fairValueChangeTotal computed（H3-8→H3-1公允变动列）
  - disclosureAutoFill computed（多源→附注）
  - _Requirements: 16.6-16.7_

- [ ] 3.4 创建 `composables/useH3AdjudicationCost.ts`
  - 双区块(原值+折旧) + 10列50公式
  - 三角勾稽校验 + TB回写1503+1504 + 交叉验证H3-2
  - _Requirements: 2.1-2.9_

- [ ] 3.5 创建 `composables/useH3AdjudicationFair.ts`
  - 单区块(公允价值) + 10列50公式
  - 公允模式校验 + TB回写1503 + 交叉验证H3-2
  - _Requirements: 2.1-2.9_

- [ ] 3.6 创建 `composables/useH3DetailCost.ts`
  - DetailCostRow 49列 + 3区段分组（基本/折旧变动/增减转换）
  - 行内公式(净值=原值-折旧-减值) + subtotalRow + crossValidation
  - _Requirements: 3.1, 3.3-3.9_

- [ ] 3.7 创建 `composables/useH3DetailFair.ts`
  - DetailFairRow 31列 + 2区段分组（基本/公允变动）
  - 行内公式(期末公允=期初+增减±转换+变动) + subtotalRow
  - _Requirements: 3.2-3.9_

- [ ] 3.8 创建 `composables/useH3Adjustment.ts`
  - H3AdjustmentRow 10列 + debitTotal/creditTotal/isBalanced
  - addRow/removeRow/updateCell + publishAdjustment + pushToA13
  - _Requirements: 4.1-4.5_

- [ ] 3.9 创建 `composables/useH3PolicyCheck.ts`
  - CAS3五段落结构 + 计量模式突出显示 + 各段conclusion(Y/N/NA)
  - _Requirements: 5.1-5.5_

- [ ] 3.10 创建 `composables/useH3AdditionCheck.ts`
  - 双版本(成本21列/公允20列) + 抽凭+OCR + 汇总统计
  - _Requirements: 6.1-6.6_

- [ ] 3.11 创建 `composables/useH3TransferReview.ts`
  - 三方向分区(自用→投资/投资→自用/在建→投资)
  - 25公式 + 转出=转入验证 + EventBus联动H1/H2
  - GtIndexChip跳转 + 方法论上下文
  - _Requirements: 7.1-7.10_

- [ ] 3.12 创建 `composables/useH3Depreciation.ts`
  - depreciationBranch状态(noImpair/withImpair) + 2分支共用数据
  - 仅成本模式显示 + 折旧计算 + 差异验证
  - _Requirements: 8.1-8.8_

- [ ] 3.13 创建 `composables/useH3FairValueReview.ts`
  - 四区域(评估师信息/方法假设/复核计算/假设挑战)
  - 15公式 + 独立测算 + 范围判断 + 交叉验证H3-1
  - _Requirements: 9.1-9.8_

- [ ] 3.14 创建 `composables/useH3Stocktake.ts`
  - StocktakeRow 13列 + 空置高亮 + 汇总统计(出租/空置/空置率)
  - _Requirements: 10.1-10.5_

- [ ] 3.15 创建 `composables/useH3Impairment.ts`
  - 仅成本模式 + 减值迹象判断 + DCF模型 + 敏感性矩阵
  - _Requirements: 11.1-11.5_

- [ ] 3.16 创建 `composables/useH3TitleCheck.ts`
  - TitleRow 16列 + 面积差异 + 产权异常高亮
  - _Requirements: 12.1-12.5_

- [ ] 3.17 创建 `composables/useH3RelatedParty.ts`
  - RelatedPartyRow 11列 + 差异率 + 高亮规则
  - _Requirements: 13.1-13.5_

- [ ] 3.18 创建 `composables/useH3RentalIncome.ts`
  - 三区域(合同汇总/月度12列/到期管理)
  - 27公式 + 空置率 + 到期预警 + 交叉验证收入
  - _Requirements: 14.1-14.8_

- [ ] 3.19 创建 `composables/useH3Disclosure.ts`
  - variant参数（listed/soe）双版本
  - 含计量模式说明 + 跨sheet取数 + EventBus
  - _Requirements: 15.1-15.5_

### Phase 4: 各sheet Vue组件

- [ ] 4.1 创建 `h3/core/H3TabIndex.vue`（~150行）
  - 底稿目录（22行进度条+完成状态+计量模式标识）
  - _Requirements: 1.2_

- [ ] 4.2 创建 `h3/core/H3TabAdjudicationCost.vue`（~450行）
  - 双区块(原值+折旧) + 三角勾稽校验 + TB回写
  - 审计说明/结论 + AI + 💬复核 + GtIndexChip→H3-6
  - _Requirements: 2.1-2.9_

- [ ] 4.3 创建 `h3/core/H3TabAdjudicationFair.vue`（~400行）
  - 单区块(公允价值) + 公允变动列 + TB回写
  - 审计说明/结论 + AI + 💬复核
  - _Requirements: 2.1-2.9_

- [ ] 4.4 创建 `h3/core/H3TabDetailCost.vue`（~500行）
  - 3区段Tab切换(基本/折旧/增减) + 行同步 + 固定列
  - 合计行 + 交叉验证H3-1 + 导入导出
  - _Requirements: 3.1, 3.3-3.9_

- [ ] 4.5 创建 `h3/core/H3TabDetailFair.vue`（~400行）
  - 2区段Tab切换(基本/公允变动) + 行同步 + 固定列
  - 合计行 + 交叉验证H3-1 + 导入导出
  - _Requirements: 3.2-3.9_

- [ ] 4.6 创建 `h3/core/H3TabAdjustment.vue`（~250行）
  - el-table 10列 + 借贷平衡 + 推送A13
  - _Requirements: 4.1-4.5_

- [ ] 4.7 创建 `h3/core/H3TabDisclosureListed.vue` + `H3TabDisclosureSoe.vue`（各~350行）
  - 多子节卡片 + 计量模式说明 + 动态行 + 合计
  - _Requirements: 15.1-15.5_

- [ ] 4.8 创建 `h3/inspection/H3TabPolicyCheck.vue`（~350行）
  - CAS3五段落卡片 + 计量模式突出 + 进度条 + AI + 💬复核
  - _Requirements: 5.1-5.5_

- [ ] 4.9 创建 `h3/inspection/H3TabAdditionCost.vue`（~350行）
  - el-table 21列（成本模式）+ 抽凭+OCR + 汇总
  - _Requirements: 6.1, 6.3-6.6_

- [ ] 4.10 创建 `h3/inspection/H3TabAdditionFair.vue`（~300行）
  - el-table 20列（公允模式）+ 抽凭+OCR + 汇总
  - _Requirements: 6.2-6.6_

- [ ] 4.11 创建 `h3/inspection/H3TabTransferReview.vue`（~500行）
  - 三方向分区(36列25公式) + 转出=转入验证 + 方法论上下文
  - GtIndexChip→H1/H2 + EventBus + AI + 💬复核
  - _Requirements: 7.1-7.10_

- [ ] 4.12 创建 `h3/inspection/H3TabStocktakeCheck.vue`（~300行）
  - el-table 13列 + 空置黄色高亮 + 汇总 + 导入导出
  - _Requirements: 10.1-10.5_

- [ ] 4.13 创建 `h3/inspection/H3TabTitleCheck.vue`（~300行）
  - el-table 16列 + 产权异常红色 + 面积差异黄色
  - _Requirements: 12.1-12.5_

- [ ] 4.14 创建 `h3/inspection/H3TabRelatedParty.vue`（~250行）
  - el-table 11列 + 差异率>10%红色 + 合计行
  - _Requirements: 13.1-13.5_

- [ ] 4.15 创建 `h3/depreciation/H3TabDepreciationNoImpair.vue`（~400行）
  - 28列(42公式) + 分支选择器 + 差异高亮（仅成本模式）
  - _Requirements: 8.1-8.8_

- [ ] 4.16 创建 `h3/depreciation/H3TabDepreciationWithImpair.vue`（~400行）
  - 28列(62公式) + 减值影响 + 差异高亮（仅成本模式）
  - _Requirements: 8.1-8.8_

- [ ] 4.17 创建 `h3/impairment/H3TabImpairment.vue`（~350行）
  - 减值迹象+测算表（仅成本模式）+ GtIndexChip→H3-11
  - _Requirements: 11.1-11.5_

- [ ] 4.18 创建 `h3/impairment/H3TabRecoverable.vue`（~400行）
  - DCF模型+敏感性矩阵（仅成本模式）
  - _Requirements: 11.3-11.5_

- [ ] 4.19 创建 `h3/fairvalue/H3TabFairValueReview.vue`（~450行）
  - 四区域(评估师/方法/复核计算15公式/假设挑战)
  - 独立测算 + 范围判断 + AI + 💬复核
  - _Requirements: 9.1-9.8_

- [ ] 4.20 创建 `h3/rental/H3TabRentalIncome.vue`（~450行）
  - 三区域(合同汇总/月度12列/到期管理) + 27公式
  - 空置高亮 + 到期预警 + 导入导出 + AI + 💬复核
  - _Requirements: 14.1-14.8_

### Phase 5: 后端（render策略+import_export+ai_generate+互转引擎endpoint）

- [ ] 5.1 创建 `_h3_investment_property.py` render策略
  - 注册RENDERER_DISPATCH['h3-investment-property']
  - render函数：加载allResponses + projectContext + TB数据(1503+1504) + measurement_model
  - 返回html_data结构（含measurement_model字段控制前端显隐）
  - _Requirements: 1.1, 16.8_

- [ ] 5.2 创建 `_h3_import_export.py` 导入导出3端点
  - POST /h3/export-template → 空白结构xlsx（根据measurement_model导出对应版本）
  - POST /h3/export-data → 当前数据xlsx（含公式结果）
  - POST /h3/import-data → 解析xlsx→验证→写入checklist_responses
  - StreamingResponse中文文件名RFC5987编码
  - _Requirements: 16.3_

- [ ] 5.3 创建 `_h3_ai_generate.py` AI生成8 section
  - adj-note-cost / adj-note-fair / adj-conclusion / policy-evaluation
  - transfer-analysis / fair-value-summary / rental-analysis / impairment-conclusion
  - 各section使用对应sheet数据+项目上下文+measurement_model生成
  - _Requirements: 16.4_

- [ ] 5.4 创建 `_h3_transfer_engine.py` 互转引擎端点
  - POST /h3/transfer/calculate → 三方向计算（自用→投资/投资→自用/在建→投资）
  - POST /h3/transfer/validate → 验证转出=转入一致性
  - 纯函数实现（与前端对等逻辑）
  - _Requirements: 7.2-7.5_

- [ ] 5.5 创建 `_h3_investment_property.py` auto_data_resolver
  - h3_tb_unadjusted: 从trial_balance取科目1503(+1504成本模式)未审数
  - h3_rental_income: 从H3-14取数租金收入合计
  - 注册到_REGISTRY
  - _Requirements: 16.8_

### Phase 6: 集成（主入口+计量模式+双模式+导入导出+跨底稿联动）

- [ ] 6.1 完成 GtH3InvestmentProperty.vue 主入口集成
  - sheetName regex分发全部20个子组件
  - measurementModel el-segmented切换 + 显隐逻辑
  - defineAsyncComponent lazy（除H3TabIndex外）
  - provide openReviewDialog给子组件inject
  - useVersionTrail集成（autoSnapshot on save）
  - _Requirements: 1.2-1.3, 1.11-1.12, 16.8, 16.10_

- [ ] 6.2 创建 `composables/useH3DualMode.ts`
  - HTML↔OnlyOffice el-segmented切换
  - OO健康检查 + 切换前autoSave
  - _Requirements: 16.1-16.2_

- [ ] 6.3 创建 `composables/useH3ImportExport.ts`
  - el-dropdown三级UI + axios请求
  - 根据measurement_model导出对应版本
  - _Requirements: 16.3_

- [ ] 6.4 H3-5 抽凭引擎+OCR集成
  - GtVoucherSamplingEngine dialog→样本填入
  - 📎列POST contract-ocr端点 → ElMessageBox确认 → merge
  - _Requirements: 6.4_

- [ ] 6.5 H3-6互转联动H1/H2
  - publish 'h3:transfer-from-h1'/'h3:transfer-from-h2'事件
  - GtIndexChip跳转H1固定资产/H2在建工程
  - _Requirements: 7.6-7.8, 16.7_

- [ ] 6.6 附注EventBus集成
  - subscribe 'substantive:adjudicated' 刷新附注
  - publish 'disclosure:note-text-updated'
  - _Requirements: 15.5, 16.6_

- [ ] 6.7 公允价值变动联动
  - H3-8 publish 'h3:fair-value-changed'
  - H3-14 publish 'h3:rental-income-calculated'
  - _Requirements: 9.8, 14.6_

### Phase 7: 测试（契约+PBT+Playwright E2E）

- [ ] 7.1 契约测试完善
  - schema_contract: h3相关表结构验证
  - column_contract: checklist_responses item_id前缀"H3-"
  - componentType契约: 'h3-investment-property' ∈ VALID_COMPONENT_TYPES
  - render策略契约: RENDERER_DISPATCH['h3-investment-property']存在
  - _Requirements: 1.6-1.8_

- [ ] 7.2 后端PBT (hypothesis)
  - test_h3_transfer_engine_pbt.py: 三方向互转计算
  - test_h3_import_export_pbt.py: 导入→导出→导入round-trip
  - test_h3_measurement_model_pbt.py: 计量模式切换幂等性
  - _Requirements: 7.2-7.5, 16.3, 16.11_

- [ ] 7.3 前端PBT (fast-check) — P1~P14全部验证
  - useH3FormulaEngine.pbt.spec.ts: P1/P2/P3/P4/P5/P8/P9/P10/P11/P12/P14
  - useH3TransferEngine.pbt.spec.ts: P6/P7
  - useH3MeasurementModel.pbt.spec.ts: P13
  - _Requirements: design.md Correctness Properties_

- [ ] 7.4 集成测试
  - H3-1审定表：成本模式编辑→三角勾稽→TB回写→切换公允→公允变动→TB回写
  - H3-6互转：三方向转换→转出=转入验证→联动H1/H2→EventBus
  - H3-8公允复核：独立测算→范围判断→假设挑战→交叉验证H3-1
  - H3-14租金：月度计算→空置率→到期预警→收入验证
  - measurement_model切换：成本→公允→成本→数据不丢失→显隐正确
  - 导入导出：导出→导入→数据一致
  - _Requirements: 全部_

- [ ] 7.5 Playwright E2E测试
  - 场景1: 打开H3底稿→切换计量模式→验证sheet显隐→成本模式H3-1编辑→三角勾稽
  - 场景2: 切换到H3-6→录入互转→验证三方向公式→GtIndexChip跳转H1
  - 场景3: 切换到H3-8→录入评估数据→独立测算→范围判断高亮
  - 场景4: 切换到H3-14→录入月租→验证年租金计算→空置高亮→到期预警
  - 场景5: measurement_model切换3次→验证数据不丢失→两套数据独立
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
        2.2[TransferEngine] --> 2.8~2.9[PBT P6~P7]
        2.1 --> 2.10~2.12[PBT P8~P10]
    end

    subgraph Phase3内部
        3.1[FormData] --> 3.2[MeasurementModel]
        3.1 --> 3.3[CrossSheet]
        3.2 --> 3.4[AdjudicationCost]
        3.2 --> 3.5[AdjudicationFair]
        3.2 --> 3.6[DetailCost]
        3.2 --> 3.7[DetailFair]
        3.3 --> 3.11[TransferReview]
        3.3 --> 3.13[FairValueReview]
        3.3 --> 3.18[RentalIncome]
        3.3 --> 3.19[Disclosure]
        3.2 --> 3.12[Depreciation-仅cost]
        3.2 --> 3.15[Impairment-仅cost]
    end

    subgraph Phase4内部
        4.2[AdjCost.vue] --> 4.4[DetailCost.vue]
        4.3[AdjFair.vue] --> 4.5[DetailFair.vue]
        4.11[TransferReview.vue] --> 4.2
        4.11 --> 4.3
        4.19[FairValueReview.vue] --> 4.3
        4.15[DepNoImpair.vue] --> 4.2
    end

    subgraph Phase6内部
        6.1[主入口+计量模式] --> 6.2[DualMode]
        6.1 --> 6.3[ImportExport]
        6.1 --> 6.4[抽凭+OCR]
        6.1 --> 6.5[互转联动H1/H2]
        6.1 --> 6.6[附注EventBus]
        6.1 --> 6.7[公允变动+租金联动]
    end
```
