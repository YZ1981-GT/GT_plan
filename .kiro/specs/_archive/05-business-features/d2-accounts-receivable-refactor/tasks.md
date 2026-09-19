# Implementation Plan: D2 应收账款底稿精细化组件拆分

## Overview

将 `useD2AccountsReceivable.ts`（1123行）拆分为18个独立子composable + 对应Vue子组件。按依赖顺序实现：共享公式引擎 → 各composable → Vue组件 → 后端导入导出 → 双模式切换 → 集成测试。主composable降至~300行。

## Tasks

- [x] 1. 实现共享公式引擎 useD2FormulaEngine.ts
  - [x] 1.1 创建 `composables/useD2FormulaEngine.ts`，实现全部纯函数
    - 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN → 0）
    - 实现 `getAuditedAmount`（审定数 = 未审 + AJE + RJE）
    - 实现 `getChangeRate`（变动率，含期初=0特殊处理：期初=0且期末=0→''，期初=0且期末≠0→1）
    - 实现 `calculateProvision`（应计提 = 余额 × 损失率）
    - 实现 `calculateDifference`（差异 = 实际 - 应计提）
    - 实现 `calculatePledgeRatio`（质押比例 = 质押总额 / 审定总额，除零返回0）
    - 实现 `determineCutoff`（截止判定：收入日期 > 资产负债表日 → true）
    - 实现 `sumif`（SUMIF聚合：按分类字段筛选行后对值字段求和）
    - 实现 `calculateExpectedLossRate`（ECL迁徙率连乘：rates.reduce((a,b)=>a*b, 1)）
    - 实现 `calculateTurnoverRate`（周转率 = 收入 / 平均应收，除零返回0）
    - 实现 `calculateTurnoverDays`（周转天数 = 365 / 周转率，周转率=0返回0）
    - _Requirements: 1.2, 1.4, 1.6, 2.7, 3.4, 5.2, 7.5, 9.2, 10.3, 10.5, 12.4, 12.5, 14.2, 22.1_

  - [ ]* 1.2 编写 Property 1 PBT：审定数公式正确性
    - **Property 1: 审定数公式正确性**
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 3（未审/AJE/RJE）
    - 断言：返回值 === 未审 + AJE + RJE
    - **Validates: Requirements 1.4, 3.3, 6.3, 9.2**

  - [ ]* 1.3 编写 Property 2 PBT：合计行恒等于明细行之和
    - **Property 2: 合计行恒等于明细行之和**
    - 生成器：`fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:30})`
    - 断言：sum(rows) === rows.reduce((a,b)=>a+b, 0)
    - **Validates: Requirements 1.5, 2.8, 3.5, 6.4, 9.4, 11.5**

  - [ ]* 1.4 编写 Property 4 PBT：变动额与变动率公式正确性
    - **Property 4: 变动额与变动率公式正确性**
    - 生成器：`fc.float` × 2（含0边界策略）
    - 断言：变动额 === 期末-期初；变动率期初=0时特殊处理
    - **Validates: Requirements 1.6**

  - [ ]* 1.5 编写 Property 5 PBT：变动率阈值高亮判定
    - **Property 5: 变动率阈值高亮判定**
    - 生成器：`fc.float({min:-10, max:10})`
    - 断言：|r| > 0.3 时返回true，否则false
    - **Validates: Requirements 1.7**

  - [ ]* 1.6 编写 Property 6 PBT：SUMIF聚合正确性
    - **Property 6: SUMIF聚合正确性**
    - 生成器：自定义 DetailRow[] 生成器（随机creditRiskClassification + 随机金额）
    - 断言：sumif结果 === 手动filter+reduce求和
    - **Validates: Requirements 1.2**

  - [ ]* 1.7 编写 Property 10 PBT：坏账准备期末未审数公式
    - **Property 10: 坏账准备期末未审数公式**
    - 生成器：`fc.float` × 6（期初审定/计提/转入/收回/转回/核销）
    - 断言：期末未审 === 期初审定 + 计提 + 转入 - 收回 - 转回 - 核销
    - **Validates: Requirements 3.4**

  - [ ]* 1.8 编写 Property 14 PBT：ECL迁徙率连乘与概率加权
    - **Property 14: ECL迁徙率连乘与概率加权**
    - 生成器：`fc.array(fc.float({min:0, max:1}), {minLength:1, maxLength:6})`
    - 断言：calculateExpectedLossRate === rates.reduce((a,b)=>a*b, 1)
    - **Validates: Requirements 10.3, 10.5**

  - [ ]* 1.9 编写 Property 18 PBT：截止日期跨期判定
    - **Property 18: 截止日期跨期判定**
    - 生成器：自定义日期对生成器（revenueDate/bsDate）
    - 断言：determineCutoff === (revenueDate > bsDate)
    - **Validates: Requirements 7.5, 14.2**

  - [ ]* 1.10 编写 Property 20 PBT：金额格式化正确性
    - **Property 20: 金额格式化正确性**
    - 生成器：`fc.float({min:-1e12, max:1e12})`
    - 断言：正数→含千分位+2位小数；负数→括号格式；零→"-"
    - **Validates: Requirements 22.1, 22.2, 22.3**

  - [ ]* 1.11 编写 Property 22 PBT：周转率与周转天数公式
    - **Property 22: 周转率与周转天数公式**
    - 生成器：`fc.float({min:1, max:1e9})` × 2
    - 断言：turnoverRate === revenue/avgReceivable; turnoverDays === 365/turnoverRate
    - **Validates: Requirements 5.2**

- [x] 2. Checkpoint - 公式引擎验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 实现 useD2Adjudication.ts composable
  - [x] 3.1 创建 `composables/useD2Adjudication.ts`，实现审定表D2-1核心逻辑
    - 定义 `AdjudicationRow` 类型（含 rowKey/label/各期数值/变动/SUMIF标记）
    - 定义固定行结构配置：单项计提 | 账龄组合 | 客户类型组合 | 合计行
    - 实现 `adjudicationRows` computed（从 allResponses 读取 D2-adj-* 前缀数据）
    - 实现 SUMIF取数逻辑（直接从同一 allResponses Map 读取 D2-detail-rows 的 remark JSON，computed 响应式链）
    - 实现 `sumif` 调用对三分类各聚合 S列/Z列/AA列
    - 实现 `totalRow` computed（= SUM三分类行各列）
    - 实现 `trialBalanceDiff` computed（= 审定数 - 试算表数）
    - 实现 `getChangeRate` 调用 + 变动率计算
    - 实现 `updateCell`（编辑 → 公式重算 → debounce保存）
    - 实现 EventBus `publishAdjudicated`（发布 'substantive:adjudicated' 事件，payload含 wpCode='D2'/accountCode='1122'/auditedAmount/priorAmount/changeRate）
    - 实现 EventBus 监听 `adjustment:created`（AJE/RJE → 累加对应列）
    - 实现 `writebackTrialBalance`（回写 trial_balance.audited_amount 科目1122）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 21.1, 21.2, 21.5, 21.6_

  - [ ]* 3.2 编写 Property 7 PBT：D2-2行公式链正确性（含SUMIF验证）
    - **Property 7: D2-2行公式链正确性**
    - 生成器：自定义 DetailRow[] 生成器（完整字段）
    - 断言：SUMIF聚合后D2-1各分类行值 === 手动filter+sum
    - **Validates: Requirements 2.7**

- [x] 4. 实现 useD2Detail.ts composable
  - [x] 4.1 创建 `composables/useD2Detail.ts`，实现明细表D2-2核心逻辑
    - 定义 `DetailRow` 类型（39列完整字段定义）
    - 实现 `rows` reactive（从 D2-detail-rows remark JSON加载）
    - 实现 `totalRow` computed（SUM全部行各金额列，不可编辑）
    - 实现 `searchQuery` + `filteredRows` computed（按客户名称模糊搜索，大小写不敏感）
    - 实现 `addRow()`（在合计行上方新增空行，所有金额=0）
    - 实现 `removeRow(rowId)`
    - 实现 `matchRelatedParty(name)`（从 relatedParties 列表模糊匹配，设置relationType）
    - 实现行公式链自动计算（priorAudited/endBalance/currentUnadj/currentAudited）
    - 实现 `updateCell`（编辑 → 公式重算 → 触发关联方匹配(如编辑customerName) → debounce保存）
    - 实现 `useVirtualScroll` computed（rows.length > 30 启用）
    - 实现序列化/反序列化（JSON.stringify rows → D2-detail-rows remark字段）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 18.4_

  - [ ]* 4.2 编写 Property 3 PBT：动态行添加保持结构不变量
    - **Property 3: 动态行添加保持结构不变量**
    - 生成器：`fc.array(DetailRow生成器, {minLength:0, maxLength:10})`
    - 断言：addRow后长度=N+1；新行金额全为0；位于合计行前
    - **Validates: Requirements 2.4, 3.7, 4.2, 6.2, 7.3, 9.6, 11.4, 12.6, 14.4**

  - [ ]* 4.3 编写 Property 8 PBT：客户名称关联方自动匹配
    - **Property 8: 客户名称关联方自动匹配**
    - 生成器：`fc.string({minLength:1})` + `fc.array(fc.string({minLength:1}))`
    - 断言：名称在列表中 → 关联方关系；不在 → '非关联方'
    - **Validates: Requirements 2.5**

  - [ ]* 4.4 编写 Property 9 PBT：客户搜索过滤正确性
    - **Property 9: 客户搜索过滤正确性**
    - 生成器：`fc.string` + `fc.array(DetailRow生成器)`
    - 断言：filteredRows 每行 customerName 包含 q（不敏感）；无遗漏无多余
    - **Validates: Requirements 2.9**

  - [ ]* 4.5 编写 Property 19 PBT：动态行序列化Round-Trip
    - **Property 19: 动态行序列化Round-Trip**
    - 生成器：自定义 DetailRow[] JSON生成器
    - 断言：JSON.stringify → JSON.parse 后深度相等
    - **Validates: Requirements 18.4, 18.5, 19.3**

  - [ ]* 4.6 编写 Property 21 PBT：从D2-2按条件导入过滤
    - **Property 21: 从D2-2按条件导入过滤**
    - 生成器：`fc.array(DetailRow生成器)` + `fc.oneof('单项计提','账龄组合','客户类型组合')`
    - 断言：导入结果 === rows.filter(r => r.creditRiskClassification === value)
    - **Validates: Requirements 6.5, 9.7**

- [x] 5. 实现 useD2BadDebt.ts composable
  - [x] 5.1 创建 `composables/useD2BadDebt.ts`，实现坏账准备D2-3核心逻辑
    - 定义 `BadDebtRow` 类型（含 category/14列数值字段）
    - 实现 `individualRows`/`agingRows`/`customerTypeRows` reactive（三分类，从 D2-bd-*-rows 加载）
    - 实现 `totalRow` computed（SUM全部行）
    - 实现期末未审数自动计算（= 期初审定 + 计提 + 转入 - 收回 - 转回 - 核销）
    - 实现 `eclDifference` computed（= 坏账合计 - ECL测试总额）
    - 实现 `eclWarning` computed（差异≠0 → 黄色警告字符串"与D2-9 ECL测算差异: ±xxx元"）
    - 实现 `addSubRow(category)`/`removeSubRow(rowId)`
    - 实现 `updateCell` + debounce保存
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 18.5_

  - [ ]* 5.2 编写 Property 11 PBT：跨sheet一致性差异警告
    - **Property 11: 跨sheet一致性差异警告**
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 2
    - 断言：不相等时返回含差异金额的警告字符串；相等时返回 null
    - **Validates: Requirements 3.6, 11.6, 15.7**

- [x] 6. 实现 useD2Adjustment.ts composable
  - [x] 6.1 创建 `composables/useD2Adjustment.ts`，实现调整分录D2-4核心逻辑
    - 定义 `AdjustmentEntry` 类型（10列）
    - 实现 `entries` reactive（从 D2-entry-rows 加载）
    - 实现 `debitTotal`/`creditTotal` computed
    - 实现 `isBalanced` computed（debit === credit）
    - 实现 `balanceDiff` computed
    - 实现 `addEntry()`/`removeEntry(rowId)`
    - 实现 `updateEntry` + debounce保存
    - 实现 `publishAdjustment()`（EventBus 'adjustment:created' 事件）
    - 实现 `pushToA13(rowIds)`（EventBus推送至A13错报汇总）
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 6.2 编写 Property 12 PBT：调整分录借贷平衡校验
    - **Property 12: 调整分录借贷平衡校验**
    - 生成器：`fc.array(fc.record({debit: fc.float({min:0}), credit: fc.float({min:0})}), {minLength:1, maxLength:10})`
    - 断言：isBalanced === (sum(debit) === sum(credit))
    - **Validates: Requirements 4.3**

- [x] 7. Checkpoint - 核心composable验证（审定表+明细表+坏账+调整分录）
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. 实现 useD2Analysis.ts composable
  - [x] 8.1 创建 `composables/useD2Analysis.ts`，实现分析程序D2-5逻辑
    - 定义 `AnalysisIndicators` 类型
    - 实现 `indicators` computed（周转率/周转天数/坏账率/前五大集中度/账龄分布）
    - 实现 `turnoverDaysWarning` computed（变动>30%）
    - 实现从试算平衡表自动获取营业收入和应收账款余额（auto_data_source resolver）
    - 实现 `dataSource`/`remark` 手动输入字段 + debounce保存
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 9. 实现 useD2Ecl.ts composable
  - [x] 9.1 创建 `composables/useD2Ecl.ts`，实现ECL合并逻辑（D2-9 + D2-10）
    - 定义 `EclSingleRow`/`MigrationRateRow`/`EclDiscountRow` 类型
    - 实现 D2-9 单项ECL：`singleRows` reactive + `singleTotal` computed
    - 实现 D2-9 应计提自动计算（= 余额×损失率）+ 差异计算（= 实际-应计提）
    - 实现 D2-9 从D2-3自动获取"期末坏账准备账面余额"（跨sheet computed引用 D2-bd-individual-rows）
    - 实现 D2-9 从D2-2筛选"单项计提"客户导入（`importFromDetail`）
    - 实现 D2-10 单项折现区：`discountRows` + 概率加权计算（weighted=折现值×概率）+ 损失率计算（1-ΣPV/余额）
    - 实现 D2-10 组合迁徙率：`migrationMatrix` + 三年平均（AVG）+ 预期损失率连乘（calculateExpectedLossRate）
    - 实现 D2-10→D2-9 损失率输出（`outputLossRates` ComputedRef<Map>）
    - 实现迁徙率变动提示（与上期比变动>20%→黄色警告）
    - 实现 `addSingleRow`/`removeSingleRow`/`updateCell` + debounce保存
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [ ]* 9.2 编写 Property 13 PBT：ECL应计提与差异计算
    - **Property 13: ECL应计提与差异计算**
    - 生成器：`fc.float({min:0, max:1e9})` × 3（余额/损失率/实际余额）
    - 断言：provision === balance×lossRate; difference === actual - provision
    - **Validates: Requirements 9.2**

- [x] 10. 实现 useD2RelatedParty.ts composable
  - [x] 10.1 创建 `composables/useD2RelatedParty.ts`，实现关联方D2-6逻辑
    - 定义 `RelatedPartyRow` 类型（12列）
    - 实现 `rows` reactive（从 D2-rp-rows 加载）
    - 实现 `totalRow` computed（各金额列SUM）
    - 实现行公式计算（期末余额=期初+借方-贷方；账面价值=期末-坏账）
    - 实现 `addRow()`（新增时从项目关联方清单下拉匹配）
    - 实现 `importFromDetail()`（从D2-2按关联方类型≠非关联方自动导入）
    - 实现 `updateCell` + debounce保存
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 11. 实现 useD2VoucherCheck.ts composable
  - [x] 11.1 创建 `composables/useD2VoucherCheck.ts`，实现凭证抽查D2-7逻辑
    - 定义 `SamplingParams`/`VoucherSampleRow` 类型
    - 实现 `params` reactive（抽样参数区）
    - 实现 `samples` reactive（从 D2-check7-rows 加载）
    - 实现 `progress` computed（已抽取/目标 + 比率）
    - 实现 `abnormalCount`/`abnormalRate` computed
    - 实现 `autoMarkCutoff`（凭证日期与收入日期跨期时自动标记"跨期"）
    - 实现 `addSample`/`removeSample`/`updateCell` + debounce保存
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 12. 实现 useD2PolicyCheck.ts composable
  - [x] 12.1 创建 `composables/useD2PolicyCheck.ts`，实现政策检查D2-8逻辑
    - 定义 `PolicyParagraph` 类型
    - 实现 `paragraphs` reactive（6个政策段落：ECL模型/信用风险增加/减值迹象/会计估计变更/同行比较/损失率方法）
    - 实现 `completedCount`/`totalCount` computed（进度追踪）
    - 实现 `hasNonCompliant` computed（是否有结论=N的段落）
    - 实现 `updateParagraph`（编辑实际情况/评价/结论 → 立即保存结论 / debounce保存文本）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 13. 实现 useD2WriteoffCheck.ts composable
  - [x] 13.1 创建 `composables/useD2WriteoffCheck.ts`，实现转回核销D2-11逻辑
    - 定义 `WriteoffRow` 类型（含section区分转回/核销）
    - 实现 `reversalRows`/`writeoffRows` reactive（双段分别加载）
    - 实现 `reversalTotal`/`writeoffTotal` computed
    - 实现 `reversalConsistencyWarning` computed（与D2-3"本期减少-转回"列对比，不一致时黄色警告）
    - 实现 `addRow(section)`/`removeRow`/`updateCell` + debounce保存
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [x] 14. 实现 useD2PledgeCheck.ts composable
  - [x] 14.1 创建 `composables/useD2PledgeCheck.ts`，实现质押保理D2-12逻辑
    - 定义 `PledgeRow`/`FactoringRow` 类型
    - 实现 `pledgeRows`/`factoringRows` reactive（双区块分别加载）
    - 实现 `pledgeTotal` computed
    - 实现 `pledgeRatio` computed（= 质押总额/审定总额）
    - 实现 `pledgeRatioWarning` computed（> 0.5 触发）
    - 实现 CAS 23 自动终止确认判定（riskTransferred=Y→终止；riskTransferred=N且controlRetained=N→终止；其余→不终止）
    - 实现 `addPledgeRow`/`addFactoringRow`/`removeRow`/`updateCell` + debounce保存
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [ ]* 14.2 编写 Property 15 PBT：CAS 23终止确认自动判定
    - **Property 15: CAS 23终止确认自动判定**
    - 生成器：`fc.boolean` × 2（riskTransferred/controlRetained）
    - 断言：(true,*)→终止; (false,false)→终止; (false,true)→不终止
    - **Validates: Requirements 12.4**

  - [ ]* 14.3 编写 Property 16 PBT：质押比例计算与阈值警告
    - **Property 16: 质押比例计算与阈值警告**
    - 生成器：`fc.float({min:0, max:1e9})` × 2（pledged/total, total>0）
    - 断言：ratio === pledged/total; warning === (ratio > 0.5)
    - **Validates: Requirements 12.5**

- [x] 15. 实现 useD2BizModel.ts composable
  - [x] 15.1 创建 `composables/useD2BizModel.ts`，实现业务模式D2-13逻辑
    - 定义 `BizModelJudgment`/`BizModelGroup` 类型
    - 实现 `judgments` reactive（4个Y/N判断题）
    - 实现 `groups` reactive（业务模式判定区）
    - 实现 `allAnswered` computed（4题全部回答）
    - 实现 `recommendedModel` computed（基于判断题回答的决策逻辑：仅收取→以摊余成本计量; 仅出售→以公允价值计量; 兼有→FVOCI; SPPI不满足→FVTPL）
    - 实现 `addGroup`/`removeGroup`/`updateJudgment`/`updateGroup` + debounce保存
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

  - [ ]* 15.2 编写 Property 17 PBT：业务模式自动推荐
    - **Property 17: 业务模式自动推荐**
    - 生成器：`fc.tuple(fc.oneof(fc.constant('Y'),fc.constant('N')), ×4)`
    - 断言：决策逻辑确定性输出正确的业务模式分类
    - **Validates: Requirements 13.4**

- [x] 16. 实现 useD2Cutoff.ts composable
  - [x] 16.1 创建 `composables/useD2Cutoff.ts`，实现截止测试逻辑
    - 定义 `CutoffSample` 类型
    - 实现 `samples` reactive（从 D2-cutoff-rows 加载）
    - 实现自动跨期判定（调用 determineCutoff(revenueDate, bsDate)）
    - 实现 `cutoffCount`/`cutoffTotalAmount` computed
    - 实现 `hasCutoffIssue` computed（cutoffCount > 0）
    - 实现 `addSample`/`removeSample`/`updateCell` + debounce保存
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [x] 17. 实现 useD2Disclosure.ts composable
  - [x] 17.1 创建 `composables/useD2Disclosure.ts`，实现附注披露4版本逻辑
    - 定义 `DisclosureVersion`/`DisclosureSection`/`DisclosureRow` 类型
    - 实现 `activeVersion` ref（'listed-d2-1'|'soe-d2-1'|'listed-aging'|'soe-aging'）
    - 实现 `switchVersion`（切换后从对应 D2-disc-{version}-* 加载数据）
    - 实现 `sections` computed（按版本渲染不同表格结构）
    - 实现比例列自动计算（= 单项/合计×100%）
    - 实现净额列自动计算（= 金额-坏账准备）
    - 实现跨sheet引用（从D2-1审定表+D2-3坏账表自动获取审定数填入对应行）
    - 实现 `inconsistencyWarnings` computed（披露金额与审定表不一致时产生警告）
    - 实现 `updateCell` + debounce保存
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7_

- [x] 18. 实现 useD2Procedure.ts composable
  - [x] 18.1 创建 `composables/useD2Procedure.ts`，实现程序表D2A逻辑
    - 定义 `ProcedureStep` 类型
    - 实现 `steps` reactive（7个审计步骤，从 D2-proc-* 加载）
    - 实现 `completedCount`/`totalCount` computed
    - 实现 `allNecessaryDone` computed（全部为completed/not_applicable）
    - 实现 `overallConclusion` ref（仅allNecessaryDone时可编辑）
    - 实现 EventBus监听 'risk:assessed'(B50)→更新步骤riskLevel
    - 实现 EventBus监听 'control:test-concluded'(C3)→更新controlConclusion
    - 实现 EventBus监听 'confirmation:completed'(D0)→更新函证面板
    - 实现 `updateStep` + debounce保存
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 21.3, 21.4, 21.5_

- [x] 19. Checkpoint - 全部composable验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 20. 实现 D2TabAdjudication.vue 组件
  - [x] 20.1 创建 `d2/D2TabAdjudication.vue`（~350行），审定表D2-1 HTML渲染
    - 使用 `useD2Adjudication` composable
    - 渲染固定行 el-table：单项计提 | 账龄组合 | 客户类型组合 | 合计行
    - 列配置：项目|期初未审|期初AJE|期初RJE|期初审定|期末未审|期末AJE|期末RJE|期末审定|变动额|变动率|原因分析
    - SUMIF自动取数单元格浅蓝色背景 + tooltip"取自D2-2按信用风险组合方式聚合"
    - 变动率 >30% 红色高亮（:class="{ 'rate-warning': isExceeding }"）
    - 合计行不可编辑
    - 试算平衡表差异行（差异≠0红色高亮）
    - 金额格式化（displayPrefs.fmtAmount）+ 零值"-" + 负数红色括号
    - 比例列百分比格式
    - el-skeleton 加载占位
    - 表头工具栏：导出模板|导出数据|导入数据 + 双模式el-segmented
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 22.1, 22.2, 22.3, 22.4, 22.6, 22.7_

- [x] 21. 实现 D2TabDetail.vue 组件
  - [x] 21.1 创建 `d2/D2TabDetail.vue`（~400行），明细表D2-2 HTML渲染（39列）
    - 使用 `useD2Detail` composable
    - el-table 横向滚动渲染39列，固定前2列（序号/客户名称）
    - 金额列右对齐+格式化，日期列日期选择器
    - "关联方类型"下拉选择（非关联方/控股股东/实际控制人/其他关联方）
    - "信用风险组合方式"下拉选择（单项计提/账龄组合/客户类型组合）
    - 关联方行橙色背景高亮（:row-class-name）
    - "添加客户"按钮 + 动态行删除
    - 搜索框（表头上方）→ filteredRows
    - 超30行启用虚拟滚动（el-table-v2）
    - 合计行底部固定不可编辑
    - 表头工具栏 + 双模式
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 22.1, 22.5, 22.7_

- [x] 22. 实现 D2TabBadDebt.vue 组件
  - [x] 22.1 创建 `d2/D2TabBadDebt.vue`（~300行），坏账准备D2-3 HTML渲染
    - 使用 `useD2BadDebt` composable
    - el-table 渲染14列：项目|期初×4|本期增加×2|本期减少×3|期末×4
    - 固定行结构：按单项计提（可展开）+ 按账龄组合（可展开）+ 按客户类型组合（可展开）+ 合计行
    - 子行增删按钮
    - ECL差异警告（合计行旁黄色 el-alert）
    - 合计行不可编辑 + 金额格式化
    - 表头工具栏 + 双模式
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 22.1, 22.7_

- [x] 23. 实现 D2TabAdjustment.vue 组件
  - [x] 23.1 创建 `d2/D2TabAdjustment.vue`（~250行），调整分录D2-4 HTML渲染
    - 使用 `useD2Adjustment` composable
    - el-table 渲染10列
    - "新增调整分录"按钮 + 动态行删除
    - 底部借贷合计行：平衡时绿色"✓平衡"，否则红色"✗不平衡：差额xxx"
    - "推送至A13"按钮（选中行 → EventBus发布）
    - 金额格式化 + 表头工具栏 + 双模式
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 22.1, 22.7_

- [x] 24. 实现 D2TabAnalysis.vue 组件
  - [x] 24.1 创建 `d2/D2TabAnalysis.vue`（~250行），分析程序D2-5 HTML渲染
    - 使用 `useD2Analysis` composable
    - 卡片式布局：周转率卡 | 周转天数卡 | 坏账率卡 | 账龄分布卡 | 前五大集中度卡
    - 周转天数变动>30%时黄色警告标签
    - 手动输入区（数据来源 + 备注textarea）
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 22.7_

- [x] 25. 实现 D2TabRelatedParty.vue 组件
  - [x] 25.1 创建 `d2/D2TabRelatedParty.vue`（~250行），关联方D2-6 HTML渲染
    - 使用 `useD2RelatedParty` composable
    - el-table 渲染12列
    - "添加关联方"按钮（自动下拉匹配关联方清单）
    - "从D2-2导入"按钮
    - 合计行 + 金额格式化
    - 表头工具栏 + 双模式
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 22.1, 22.7_

- [x] 26. 实现 D2TabVoucherCheck.vue 组件
  - [x] 26.1 创建 `d2/D2TabVoucherCheck.vue`（~300行），凭证抽查D2-7 HTML渲染
    - 使用 `useD2VoucherCheck` composable
    - 两区块：抽样参数区（el-form）+ 凭证抽样明细表（el-table 17列）
    - 进度条（已抽取/目标样本量）
    - "添加样本"按钮 + 动态行删除
    - 跨期自动标记（凭证日期与收入日期比对）
    - 底部汇总：已检查笔数/异常笔数/异常率
    - 表头工具栏 + 双模式
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 22.1, 22.7_

- [x] 27. 实现 D2TabPolicyCheck.vue 组件
  - [x] 27.1 创建 `d2/D2TabPolicyCheck.vue`（~300行），政策检查D2-8 HTML渲染
    - 使用 `useD2PolicyCheck` composable
    - 段落型卡片布局（非el-table），6个政策段落
    - 每段落：左栏政策条款（只读）| 右栏实际情况（textarea）| 下方评价（textarea）| 结论（Y/N/NA radio）
    - 结论=N时红色边框 + "需关注"标签
    - 顶部进度：已完成段数/总段数
    - 编制提示折叠区（`<details>` 蓝色左边线+浅蓝背景）
    - 表头双模式切换
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 22.7_

- [x] 28. 实现 D2TabEcl.vue 组件
  - [x] 28.1 创建 `d2/D2TabEcl.vue`（~400行），ECL测算D2-9+D2-10合并HTML渲染
    - 使用 `useD2Ecl` composable
    - el-tabs 内嵌两个tab-pane：单项ECL(D2-9) | 计量测试(D2-10)
    - D2-9: el-table 8列 + 合计行 + 差异红色高亮 + "添加债务人"按钮 + "从D2-2导入单项计提"按钮
    - D2-10单项折现区: 债务人×场景折叠展示（概率加权自动计算）
    - D2-10组合区: 迁徙率矩阵表（账龄段×年度×平均×损失率）+ 变动提示
    - 金额格式化 + 表头工具栏 + 双模式
    - _Requirements: 9.1-9.7, 10.1-10.7, 22.1, 22.7_

- [x] 29. 实现 D2TabWriteoffCheck.vue 组件
  - [x] 29.1 创建 `d2/D2TabWriteoffCheck.vue`（~250行），转回核销D2-11 HTML渲染
    - 使用 `useD2WriteoffCheck` composable
    - 双段结构：转回区（el-table 8列）+ 核销区（el-table 8列）
    - 各区域"添加"按钮 + 动态行删除
    - 各区域底部合计行
    - 转回合计与D2-3不一致时黄色警告
    - 金额格式化 + 表头工具栏 + 双模式
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 22.1, 22.7_

- [x] 30. 实现 D2TabPledgeCheck.vue 组件
  - [x] 30.1 创建 `d2/D2TabPledgeCheck.vue`（~300行），质押保理D2-12 HTML渲染
    - 使用 `useD2PledgeCheck` composable
    - 双区块：质押情况（el-table 9列）+ 保理终止确认（el-table 8列）
    - 质押比例显示 + >50%红色警告
    - CAS 23终止确认结论自动填充
    - 各区域"添加"按钮 + 动态行删除
    - 金额格式化 + 表头工具栏 + 双模式
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 22.1, 22.7_

- [x] 31. 实现 D2TabBizModel.vue 组件
  - [x] 31.1 创建 `d2/D2TabBizModel.vue`（~250行），业务模式D2-13 HTML渲染
    - 使用 `useD2BizModel` composable
    - QA问答式卡片：4个判断题（Y/N radio + 依据textarea）
    - 业务模式判定区：el-table 5列 + "添加组合"按钮
    - 自动推荐业务模式显示（全部回答后高亮推荐结果）
    - 报表项目分类区
    - 表头双模式切换
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 22.7_

- [x] 32. 实现 D2TabCutoff.vue 组件
  - [x] 32.1 创建 `d2/D2TabCutoff.vue`（~200行），截止测试 HTML渲染
    - 使用 `useD2Cutoff` composable
    - el-table 8列：序号|发票号|收入日期|入账日期|金额|跨期判定|结论|备注
    - 跨期判定自动填充（determineCutoff）
    - 存在跨期时表头红色警告"发现N笔跨期，合计金额xxx"
    - "添加样本"按钮 + 动态行删除
    - 底部汇总：已检查/跨期笔数/跨期金额
    - 金额格式化 + 表头工具栏 + 双模式
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 22.1, 22.7_

- [x] 33. 实现 D2TabDisclosure.vue 组件
  - [x] 33.1 创建 `d2/D2TabDisclosure.vue`（~350行），附注披露4版本 HTML渲染
    - 使用 `useD2Disclosure` composable
    - 顶部 el-segmented 切换（"上市公司" | "国企"）+ 二级切换（"D2-1版" | "账龄版"）
    - 按版本动态渲染：上市公司(金额/比例/坏账/计提比例/净额) | 国企(余额/比例/坏账/比例)
    - 跨sheet自动取数单元格浅蓝背景 + tooltip
    - 不一致时黄色警告tooltip
    - 金额格式化 + 比例百分比 + 表头工具栏 + 双模式
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 22.1, 22.4, 22.7_

- [x] 34. 实现 D2TabProcedure.vue 组件
  - [x] 34.1 创建 `d2/D2TabProcedure.vue`（~250行），程序表D2A HTML渲染
    - 使用 `useD2Procedure` composable
    - 卡片式布局：7个审计步骤卡片
    - 每步含：序号|描述|分类|目标|状态(4态下拉)|执行人|日期|发现|结论|索引号(GtIndexChip)
    - 顶部进度条
    - 风险等级标签（H红/M黄/L绿，从EventBus获取）
    - 控制测试结论提示（从EventBus获取）
    - 全部必要步骤完成后启用"审计结论"textarea
    - 表头双模式切换
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 22.7_

- [x] 35. Checkpoint - 全部Vue组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 36. 修改主入口组件 GtD2AccountsReceivable.vue
  - [x] 36.1 在 `GtD2AccountsReceivable.vue` 中集成15个新子组件
    - 在 el-tabs 中替换旧tab-pane为新子组件引用（D2TabAdjudication/D2TabDetail/D2TabBadDebt/D2TabAdjustment/D2TabAnalysis/D2TabRelatedParty/D2TabVoucherCheck/D2TabPolicyCheck/D2TabEcl/D2TabWriteoffCheck/D2TabPledgeCheck/D2TabBizModel/D2TabCutoff/D2TabDisclosure/D2TabProcedure）
    - 传递 allResponses/wpId/projectId/isReadonly/relatedParties/bsDate 等 props
    - 暂时保留旧代码（注释掉旧 tab-pane），确认新组件正常工作
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8, 20.9, 20.10_

  - [x] 36.2 从 `useD2AccountsReceivable.ts` 中删除已拆出逻辑
    - 删除 SUMIF/审定表/明细表/坏账/调整分录/分析/关联方/凭证/政策/ECL/转回核销/质押/业务模式/截止/附注/程序表 相关代码（~800行）
    - 保留：Tab管理 + activeTab路由同步 + 联动协调 + EventBus监听转发
    - 确保拆分后 useD2AccountsReceivable.ts 约 ~300 行
    - 删除旧注释掉的 tab-pane
    - 运行现有 D2 测试套件确认不回归
    - _Requirements: 20.10, 20.11, 20.12_

- [x] 37. 实现 useD2ImportExport.ts 通用composable
  - [x] 37.1 创建 `composables/useD2ImportExport.ts`，导入导出通用逻辑
    - 定义 `ImportableSheet` 类型联合（8个sheet）
    - 实现 `exportTemplate(sheet)`（调用 POST /api/workpapers/{wp_id}/d2/export-template?sheet=xxx → 下载xlsx）
    - 实现 `exportData(sheet)`（调用 POST /api/workpapers/{wp_id}/d2/export-data?sheet=xxx → 下载xlsx）
    - 实现 `importData(sheet, file)`（调用 POST /api/workpapers/{wp_id}/d2/import-data?sheet=xxx → 返回摘要）
    - 实现 `importing` ref + `lastError` ref
    - 导入成功：ElMessage.success("成功导入N行数据，M个字段已更新")
    - 导入失败：ElMessage.error(错误列名列表)
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7_

- [x] 38. 实现 useD2DualMode.ts 通用composable
  - [x] 38.1 创建 `composables/useD2DualMode.ts`，双模式切换逻辑
    - 实现 `mode` ref（'html' | 'onlyoffice'）
    - 实现 OO 健康检查（GET /api/workpapers/onlyoffice/health）
    - 实现 `ooAvailable` ref（健康检查通过=true）
    - 实现 `switchMode`：切OO→获取config+渲染GtOnlyOfficeSheet+隐藏非当前sheet；切HTML→重新加载allResponses
    - OO不可用时禁用切换 + tooltip
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5_

- [x] 39. 实现后端导入导出端点
  - [x] 39.1 创建 `backend/app/routers/wp_render_strategies/_d2_import_export.py`（~250行）
    - 实现 `POST /api/workpapers/{wp_id}/d2/export-template?sheet=D2-2`（空白xlsx模板，含表头+格式+公式）
    - 实现 `POST /api/workpapers/{wp_id}/d2/export-data?sheet=D2-2`（含当前数据的xlsx）
    - 实现 `POST /api/workpapers/{wp_id}/d2/import-data?sheet=D2-2`（解析xlsx → 回写checklist_responses）
    - 使用 openpyxl 生成/解析 xlsx
    - 格式校验：列名不匹配时返回 400 + 错误列名列表
    - 行数限制：超500行截断 + 返回警告摘要
    - 支持 D2-2/D2-3/D2-4/D2-6/D2-7/D2-9/D2-11/D2-12 八个sheet
    - 注册路由到 router_registry
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7_

  - [ ]* 39.2 编写后端导入导出集成测试（hypothesis）
    - Round-trip 测试：生成随机行数据 → export-data → import-data → 验证等价
    - 模板格式校验：随机列名排列 → 验证错误检测
    - 8个sheet各自round-trip
    - **Validates: Requirements 19.3, 19.4**

- [x] 40. Checkpoint - 导入导出和双模式验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 41. 持久化与自动保存集成
  - [x] 41.1 确保全部composable的持久化逻辑完整
    - 验证 item_id 命名规范（D2-adj-/D2-detail-/D2-bd-/D2-entry-/D2-cutoff-/D2-analysis-/D2-rp-/D2-check7-/D2-policy-/D2-ecl9-/D2-ecl10-/D2-writeoff-/D2-pledge-/D2-bizmodel-/D2-disc-/D2-proc- 前缀）
    - 验证 debounce 2秒自动保存（编辑金额/文本后）
    - 验证选择类字段立即保存（结论Y/N/NA、下拉选择）
    - 验证动态行 JSON 序列化存储于 remark 字段
    - 验证跨sheet数据变更后 computed 自动刷新（无 API 调用延迟）
    - 验证 localStorage 持久化 activeTab（key含wpId）
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_

- [x] 42. 回归测试 - 运行现有 D2 全量测试
  - [x] 42.1 运行现有 D2 测试套件确保无回归
    - `rtk python -m pytest backend/tests/ -k d2 -v --tb=short`
    - `rtk npx vitest run --reporter=verbose` (D2相关测试文件)
    - 确认 76 tests (13 PBT + 89 vitest + 1 hypothesis) 全绿
    - 如有失败，修复后重跑直至全绿

- [x] 43. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 44. D0函证→D2-2联动（自动标记"是否函证"）
  - [x] 44.1 在 `useD2Detail.ts` 中注册 EventBus 监听 'confirmation:completed'
    - 事件 payload 含 customerName/confirmationResult
    - 模糊匹配 D2-2 中客户行（customerName contains 匹配），匹配到的行 isConfirmation=true
    - 自动标记的行浅绿色背景高亮（_confirmationAutoMarked=true 标志位）
    - 触发 debounce 自动保存
    - _Requirements: 23.1, 23.2, 23.3, 23.4_

- [x] 45. D2-2从辅助余额表直接导入
  - [x] 45.1 在 `useD2Detail.ts` 中实现 `importFromAuxBalance()` 方法
    - 调用 `GET /api/projects/{pid}/ledger/aux-balance-detail` 传参 account_code=1122, aux_type=customer
    - merge模式：按客户名去重，仅更新 priorUnadjusted/endBalance 字段，不覆盖 AJE/RJE/账龄等手工字段
    - 返回 { imported, updated, added } 摘要
    - 前端工具栏增加"从余额表导入"按钮
    - 无数据时 ElMessage.info 提示
    - _Requirements: 24.1, 24.2, 24.3, 24.4, 24.5_

- [x] 46. D2-5分析异常→A1-13联动推送
  - [x] 46.1 在 `useD2Analysis.ts` 中实现 analytical:significant-change 事件发布
    - watch indicators 变化，周转天数变动率>30%时发布 EventBus 事件
    - payload 含 wpCode='D2'/indicator/changeRate/currentValue/priorValue
    - 从 analytical_review_service 复用 resolver 获取上期对比数据（调用 /api/projects/{pid}/auto-data/analytical_review?year=）
    - _Requirements: 25.1, 25.2, 25.3_

- [x] 47. 复核对话通用集成
  - [x] 47.1 在所有D2子组件中集成 useReviewDialogProvider
    - 每个子组件 inject('openReviewDialog')
    - D2TabAdjudication：审计说明+结论区各1个💬固定入口
    - D2TabPolicyCheck：结论=N的段落旁💬入口
    - D2TabEcl：差异超重要性行旁💬入口
    - D2TabVoucherCheck：异常行右键"发起复核"
    - 所有el-table子组件：@cell-contextmenu → openReviewDialog（sectionId=`D2-{tab}-{rowKey}-{field}`）
    - onMounted 加载 /api/review-threads/active?wp_id= 显示活跃线程蓝/红圆点
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7_

- [x] 48. 交叉索引GtIndexChip增强
  - [x] 48.1 在各子组件关键位置添加 GtIndexChip
    - D2TabAdjudication：变动率>30%的"原因分析"列旁 → 跳转D2-5分析Tab
    - D2TabBadDebt："计提"列旁 → 跳转D2-9 ECL对应债务人
    - D2TabRelatedParty："索引号"列 → 跳转A17-1重大事项
    - D2TabVoucherCheck："对方科目"列 → 跳转对方科目底稿（如6001→D4）
    - D2TabProcedure：每步索引号 → 跳转关联子Tab
    - D2TabEcl：差异行 → 跳转D2-3坏账准备
    - D2TabDisclosure：审定数引用 → 跳转D2-1审定表
    - _Requirements: 27.1, 27.2, 27.3, 27.4, 27.5, 27.6_

- [x] 49. Final checkpoint - 联动加强验证
  - Ensure all new integrations work, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 每个 Property 对应 design.md 中的一个 correctness property
- 从 `useD2AccountsReceivable.ts` 拆出的内容参照 design.md "拆分边界" 表
- 后端导入导出（Task 39）和前端导入导出 composable（Task 37）已分开
- 双模式切换（Task 38）依赖组件基础完成（Task 20-34）
- 所有 PBT 使用 fast-check，numRuns: 100
- D2特有的SUMIF引擎是核心差异点，需优先验证（Property 6）
- 跨sheet数据流通过同一allResponses Map的computed链实现，不走API
- D2-10的198个公式拆分为：单项折现公式（概率加权）+ 组合迁徙率矩阵（连乘）
- CAS 23终止确认逻辑在D2-12保理区实现
- 附注4版本通过el-segmented动态切换，数据各自独立存储

## Risks & Execution Reminders（执行时风险提醒）

- **D2-2 remark超大风险**：100+客户×39字段=单条JSON可能>10KB。执行Task 4时验证性能，若行数>200考虑分片存储
- **SUMIF computed性能**：执行Task 3时确认100行filter+reduce在2s debounce内完成，Vue3 computed天然lazy无需额外优化
- **EventBus内存泄漏**：执行Task 36(主入口重构)时统一在onUnmounted清理5个EventBus listener
- **39列宽表体验**：执行Task 21时实测1366×768屏幕，确认固定列+横向滚动可用；考虑列可见性配置
- **D2-10除零**：执行Task 9(useD2Ecl)时确认calcExpectedLossRate内rates含0→返回0而非NaN/Infinity
- **OO双模式数据同步**：执行Task 38(useD2DualMode)时确认切回HTML后强制reload allResponses，不依赖OO callback
- **AI列必须是下拉**：执行Task 21(D2TabDetail)时D2-2"信用风险组合方式"列必须是el-select（3固定值），禁止el-input自由输入
- **附注lazy加载**：执行Task 33(D2TabDisclosure)时4版本用v-if按需渲染，不要v-show同时挂载4套表格
