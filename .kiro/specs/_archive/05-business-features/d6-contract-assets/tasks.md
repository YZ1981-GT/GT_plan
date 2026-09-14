# Implementation Plan: D6 合同资产底稿专属HTML精美组件

## Overview

实现D6合同资产底稿专属组件`d6-contract-assets`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtD6ContractAssets.vue + 11个子组件 + 11个composable + 后端4个py文件。科目1402借方/资产类，核心公式：期末=期初+借方-贷方；净值=原值-坏账准备；应计提=余额×损失率。三区块审定表（177公式）+ 30列最宽明细表（69公式）+ ECL双组合测算（58公式）+ 163公式最复杂附注（5子节）+ 段落式政策检查。D循环中第二复杂底稿（仅次于D4营业收入）。

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将D6/D6-1/D6-2/D6-3/D6-4/D6-5/D6-6/D6-7/D6-8/D6-9映射为'd6-contract-assets'
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'd6-contract-assets'
    - 在 `htmlRendererRegistry.ts` 中注册 'd6-contract-assets' → GtD6ContractAssets 映射
    - 创建 `GtD6ContractAssets.vue` 主入口骨架（el-tabs 11个tab-pane + selfLoad逻辑）
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 1.8_

  - [x] 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'd6-contract-assets'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证D6/D6-1~D6-9共10个映射
    - _Requirements: 1.5, 1.6, 1.7_

- [x] 2. 实现共享公式引擎 useD6FormulaEngine.ts
  - [x] 2.1 创建 `composables/useD6FormulaEngine.ts`，实现全部纯函数
    - 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN/Infinity → 0）
    - 实现 `calcEndUnadjustedDebit`（借方科目期末未审 = 期初审定 + 借方发生 - 贷方发生）
    - 实现 `calcAuditedAmount`（审定数 = 未审 + AJE + RJE）
    - 实现 `calcEndAudited`（期末审定 = 期末未审 + 账项调整 + 重分类调整）
    - 实现 `calcNetValue`（净值 = 原值 - 坏账准备，跨区块公式）
    - 实现 `calcExpectedProvision`（ECL应计提 = 审定余额 × 预期信用损失率）
    - 实现 `calcEclDifference`（ECL差异 = 应计提 - 账面余额）
    - 实现 `calcChangeAmount`（变动额 = 期末审定 - 期初审定）
    - 实现 `calcChangeRate`（变动率：期初=0且期末=0→''/期初=0→'N/A'/其他→(期末-期初)/期初）
    - 实现 `isChangeRateExceeding`（变动率绝对值超阈值判定）
    - 实现 `calcSubtotal`（合计 = SUM数组）
    - 实现 `calcBlockTotal`（XX小计 = 小计 - "减：列示于其他非流动资产"扣减值）
    - 实现 `calcImpairmentEndUnadjusted`（减值期末未审 = 期初审定+计提+其他增加-转回-核销-其他减少）
    - 实现 `calcRelatedPartyEndBalance`（关联方期末余额 = 期初+借方-贷方，借方科目）
    - 实现 `calcBookValue`（账面价值 = 期末余额 - 坏账准备）
    - 实现 `calcPercentage`（比例% = 该类别金额/合计金额×100）
    - _Requirements: 1.4, 2.3, 2.4, 2.5, 5.4, 8.3, 10.3, 13.3_

  - [x]* 2.2 编写 Property 1 PBT：借方科目期末余额公式
    - 生成器：`fc.float({min:0, max:1e9})` × priorAudited/debit/credit
    - 断言：calcEndUnadjustedDebit(priorAudited, debit, credit) === priorAudited + debit - credit
    - **Property 1: 借方科目期末余额公式**
    - **Validates: Requirements 1.4, 5.4**

  - [x]* 2.3 编写 Property 2 PBT：审定数 = 未审 + AJE + RJE
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 3
    - 断言：calcAuditedAmount(u, a, r) === u + a + r
    - **Property 2: 审定数 = 未审 + AJE + RJE**
    - **Validates: Requirements 1.4, 2.3**

  - [x]* 2.4 编写 Property 3 PBT：净值 = 原值 - 坏账准备
    - 生成器：`fc.float({min:0, max:1e9})` × originalValue, `fc.float({min:0, max:originalValue})` × impairment
    - 断言：calcNetValue(originalValue, impairment) === originalValue - impairment
    - **Property 3: 净值 = 原值 - 坏账准备（跨区块联动）**
    - **Validates: Requirements 2.5, 3.3, 26.1, 26.2, 26.3**

  - [x]* 2.5 编写 Property 4 PBT：XX小计 = 小计 - 非流动扣减
    - 生成器：`fc.float({min:0, max:1e9})` × subtotal, `fc.float({min:0, max:subtotal})` × deduction
    - 断言：calcBlockTotal(subtotal, deduction) === subtotal - deduction
    - **Property 4: XX小计 = 小计 - 非流动扣减**
    - **Validates: Requirements 2.4, 26.4**

  - [x]* 2.6 编写 Property 6 PBT：合计行 = SUM(明细行)
    - 生成器：`fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:50})`
    - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
    - **Property 6: 合计行 = SUM(明细行)**
    - **Validates: Requirements 2.4, 5.5, 8.4, 13.7**

  - [x]* 2.7 编写 Property 9 PBT：变动率阈值高亮判定
    - 生成器：`fc.float({min:-10, max:10})`
    - 断言：isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)；空串/'N/A'→false
    - **Property 9: 变动率阈值高亮判定**
    - **Validates: Requirements 2.7**

- [x] 3. 实现 useD6FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useD6FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate（PUT单条response）
    - 实现 debouncedSave（2秒debounce版本）
    - 实现 saveBatch（批量保存）
    - 实现 writebackTrialBalance（回写科目1402）
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=d6-contract-assets）
    - _Requirements: 1.8, 21.5, 21.7, 21.8_

- [x] 4. 实现 useD6CrossSheet.ts 跨Sheet联动
  - [x] 4.1 创建 `composables/useD6CrossSheet.ts`
    - 实现 originalValueAggregation computed（D6-2按合同类型聚合endAudited到审定表区块一各动态行）
    - 实现 impairmentAggregation computed（D6-3按分类聚合endAudited到审定表区块二各动态行）
    - 实现 blockTotals computed（三区块小计/扣减/合计）
    - 实现 netValueRows computed（净值=原值-坏账，逐行+小计+非流动+合计）
    - 实现 eclReferenceValues computed（D6-8→D6-3应计提参考值）
    - 实现 adjustmentTotals computed（D6-4→D6-1 AJE/RJE合计）
    - 实现 netValueValidation computed（三区块交叉验证：|原值合计-坏账合计-净值合计|≤0.01）
    - 实现 adjudicationForDisclosure computed（D6-1审定数→附注引用）
    - 实现 eclForDisclosure computed（D6-8单项/组合→附注(2)(3)(4)子节）
    - 实现 impairmentChangesForDisclosure computed（D6-3计提/转回/核销→附注(5)子节）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 15.2, 15.3, 15.4, 16.2, 16.3, 27.1, 27.2, 27.3_

  - [x]* 4.2 编写 Property 5 PBT：按分类聚合正确性
    - 生成器：自定义 DetailRow[] 生成器（contractType随机从'工程施工'/'质量保证金'/'其他'取）
    - 断言：各类别sum === 手动filter+reduce结果
    - **Property 5: 按分类聚合正确性**
    - **Validates: Requirements 3.1, 3.2, 5.5, 5.6**

  - [x]* 4.3 编写 Property 12 PBT：三区块交叉验证
    - 生成器：`fc.float({min:0, max:1e9})` × 3 (block1Total, block2Total, block3Total)
    - 断言：netValueValidation.isValid === (|block1Total - block2Total - block3Total| ≤ 0.01)
    - **Property 12: 三区块交叉验证（净值小计=原值小计-坏账小计）**
    - **Validates: Requirements 2.9, 26.6**

- [x] 5. Checkpoint - 公式引擎与基础设施验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 实现 useD6Adjudication.ts 审定表D6-1（三区块177公式）
  - [x] 6.1 创建 `composables/useD6Adjudication.ts`
    - 定义三区块固定配置 ADJUDICATION_BLOCKS（block1=原值/block2=坏账准备/block3=净值）
    - 每区块含：动态行 + subtotalRow + deductionRow("减：列示于其他非流动资产") + blockTotalRow(XX小计)
    - 实现 blocks computed（从allResponses加载 + crossSheet聚合填入 + 公式计算）
    - 实现 rows 公式：小计=SUM(动态行)；XX小计=小计-非流动扣减；审定数=未审+AJE+RJE
    - 实现 区块三净值逐行=区块一对应行-区块二对应行（跨区块联动，rowKey对齐）
    - 实现 trialBalanceAmount（从TB auto_data取数科目1402）+ trialBalanceDiff(=净值合计-TB数)
    - 实现 netValueValidation（净值小计=原值小计-坏账小计，|diff|>0.01时红色警告）
    - 实现 changeAmount/changeRate/isExceeding 变动额与变动率（>30%红色高亮）
    - 实现 auditNotes 双向绑定（explanation/impairmentEval/longTermReason/conclusion）
    - 实现 updateCell（编辑 → 公式重算 → debouncedSave）
    - 实现 addDynamicRow/removeDynamicRow（区块一/区块二联动增删→区块三自动同步）
    - 实现 publishAdjudicated（EventBus: substantive:adjudicated，payload含wpCode='D6'/accountCode='1402'/auditedAmount）
    - 实现 onAdjustmentCreated监听（adjustment:created事件→AJE/RJE累加）
    - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率|原因分析
    - _Requirements: 2.1-2.10, 3.1-3.8, 4.1-4.7, 26.1-26.6_

- [x] 7. 实现 useD6Detail.ts 明细表D6-2（30列69公式）
  - [x] 7.1 创建 `composables/useD6Detail.ts`
    - 定义 DetailRow 类型（30列完整字段：序号~期后结转金额）
    - 实现 rows reactive（从D6-2-rows加载JSON数组）
    - 实现行内公式自动计算：期初审定(10)=7+8+9; 期末未审(17)=10+15-16(借方!); 期末审定(20)=17+18+19
    - 实现 subtotalByType computed（按合同类型小计：工程施工/质量保证金/其他）
    - 实现 classificationRows computed（附加分类行：合并范围内关联方/合并范围外关联方/非关联方 + 单项计提/业务类型组合/客户类型组合）
    - 实现 totalRow computed（总合计=SUM所有明细行）
    - 实现 addRow/removeRow/updateCell
    - 实现 importFromAuxBalance（调后端API从tb_aux_balance科目1402按客户/合同维度导入）
    - 实现 searchFilter + filteredRows computed（按合同名称/客户名称模糊搜索）
    - 对"类型"列下拉（工程施工/质量保证金/其他）
    - 对"关联关系"列下拉（非关联方/实际控制人/控股股东/…/其他关联方 8种）
    - 对"信用风险组合方式"列下拉（单项计提/业务类型组合/客户类型组合/…动态）
    - 对"是否在建设期或质保期内"列下拉（是/否）
    - _Requirements: 5.1-5.14, 6.1-6.8, 7.1-7.5_

  - [x]* 7.2 编写 Property 10 PBT：D6-2行公式链（借方科目完整链）
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 7 (priorUnadjusted, priorAje, priorRje, debit, credit, endAje, endRje)
    - 断言：priorAudited=7+8+9; endUnadjusted=priorAudited+15-16; endAudited=endUnadjusted+18+19
    - **Property 10: D6-2行公式链（借方科目完整链）**
    - **Validates: Requirements 5.4**

  - [x]* 7.3 编写 Property 7 PBT：动态行添加保持结构不变量
    - 生成器：`fc.array(DetailRow生成器, {minLength:0, maxLength:30})`
    - 断言：addRow后length=N+1；新行数值全0；新行位于合计行前
    - **Property 7: 动态行添加保持结构不变量**
    - **Validates: Requirements 5.7, 8.5, 9.2, 13.9, 14.4**

- [x] 8. 实现 useD6ImpairmentDetail.ts 减值准备明细D6-3（14列63公式）
  - [x] 8.1 创建 `composables/useD6ImpairmentDetail.ts`
    - 定义 ImpairmentDetailRow 类型（14列：项目/期初(未审/AJE/RJE/审定)/本期增加(计提/其他)/本期减少(转回/核销/其他)/期末(未审/AJE/RJE/审定)）
    - 实现 singleRows reactive（按单项评估计提，从D6-3-rows加载JSON筛选category='single'）
    - 实现 groupRows reactive（按信用风险组合计提，从D6-3-rows加载JSON筛选category='group'）
    - 实现行内公式：期初审定=未审+AJE+RJE；期末未审=期初审定+计提+其他增加-转回-核销-其他减少；期末审定=期末未审+AJE+RJE
    - 实现 singleSubtotal/groupSubtotal computed（各分类小计=SUM对应动态行）
    - 实现 totalRow computed（合计=按单项小计+按组合小计）
    - 实现 reconciliation computed（核对行：D6-3合计 vs D6-1坏账区块合计，差异≠0红色高亮）
    - 实现 addRow(category)/removeRow/updateCell
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - _Requirements: 8.1-8.8, 27.2, 27.5_

  - [x]* 8.2 编写 Property 15 PBT：减值准备明细公式链（D6-3）
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 10 (priorUnadjusted, priorAje, priorRje, provision, otherIncrease, reversal, writeOff, otherDecrease, endAje, endRje)
    - 断言：priorAudited=未审+AJE+RJE; endUnadjusted=期初审定+计提+其他增加-转回-核销-其他减少; endAudited=期末未审+AJE+RJE
    - **Property 15: 减值准备明细公式链（D6-3）**
    - **Validates: Requirements 8.3**

- [x] 9. 实现 useD6Adjustment.ts 调整分录D6-4
  - [x] 9.1 创建 `composables/useD6Adjustment.ts`
    - 定义 AdjustmentRow 类型（10列：调整事项说明/类别/报表项目/科目名称/附注项目/…/借方金额/贷方金额/索引/备注）
    - 实现 rows reactive（从D6-4-rows加载JSON）
    - 实现 debitTotal/creditTotal/isBalanced/balanceDiff computed
    - 实现 addRow/removeRow/updateCell
    - 实现 publishAdjustment（EventBus adjustment:created，payload含wpCode='D6'/entryType/amount/accountCode='1402'）
    - 实现 pushToA13（EventBus推送选中分录至A13错报汇总）
    - _Requirements: 9.1-9.7_

  - [x]* 9.2 编写 Property 8 PBT：调整分录借贷平衡检查
    - 生成器：`fc.array(fc.record({debit:fc.float({min:0,max:1e9}), credit:fc.float({min:0,max:1e9})}))`
    - 断言：isBalanced === (debitTotal === creditTotal)；balanceDiff === debitTotal - creditTotal
    - **Property 8: 调整分录借贷平衡检查**
    - **Validates: Requirements 9.3**

- [x] 10. 实现 useD6RelatedParty.ts 关联方检查D6-5（14列）
  - [x] 10.1 创建 `composables/useD6RelatedParty.ts`
    - 定义 RelatedPartyRow 类型（14列：关联方名称/关联关系/期初余额/借方/贷方/期末余额/坏账准备/账面价值/发生时间及账龄/未结转原因/至审计日结转金额/处理计划/索引号/备注）
    - 实现 rows reactive（从D6-5-rows加载JSON）
    - 实现行内公式：期末余额=期初+借方-贷方（借方科目）；账面价值=期末余额-坏账准备
    - 实现 totalRow computed（期初/借方/贷方/期末/坏账/账面价值各列SUM）
    - 实现 addRow/removeRow/updateCell
    - 实现 importFromDetail（从D6-2筛选"关联关系≠非关联方"的行导入：客户名称/关联关系/期初/借方/贷方/期末）
    - 对"关联关系"列下拉（实际控制人/控股股东/控股股东附属企业/持有5%以上/联营/合营/董高监/其他关联方）
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - _Requirements: 10.1-10.9_

  - [x]* 10.2 编写 Property 18 PBT：关联方期末余额（借方科目）+ 账面价值
    - 生成器：`fc.float({min:0, max:1e9})` × priorBalance/debit/credit, `fc.float({min:0, max:endBalance})` × impairment
    - 断言：calcRelatedPartyEndBalance === priorBalance+debit-credit；calcBookValue === endBalance-impairment
    - **Property 18: 关联方期末余额（借方科目）+ 账面价值**
    - **Validates: Requirements 10.3**

  - [x]* 10.3 编写 Property 19 PBT：账面价值 = 期末余额 - 坏账准备
    - 生成器：`fc.float({min:0, max:1e9})` × endBalance, `fc.float({min:0, max:endBalance})` × impairment
    - 断言：calcBookValue(endBalance, impairment) === endBalance - impairment
    - **Property 19: 账面价值 = 期末余额 - 坏账准备**
    - **Validates: Requirements 10.3, 15.1**

- [x] 11. 实现 useD6EclCalculation.ts 减值测算D6-8（ECL双组合58公式）
  - [x] 11.1 创建 `composables/useD6EclCalculation.ts`
    - 定义 EclSingleRow 类型（8列：债务人名称/审定余额①/损失率②/应计提③=①×②/账面余额④/差异⑤=③-④/依据/索引）
    - 定义 EclAgingGroup 类型（groupId/groupName/rows:EclAgingRow[]，固定6账龄段+小计）
    - 定义 EclAgingRow 类型（6列：账龄段/审定余额①/损失率②/应计提③=①×②/账面余额④/差异⑤=③-④）
    - 实现 singleRows reactive（从D6-8-single-rows加载JSON）
    - 实现 agingGroups reactive（从D6-8-groups加载JSON，每组合含6账龄段行+小计行）
    - 实现行内公式：应计提③=余额①×损失率②；差异⑤=应计提③-账面余额④
    - 实现 singleTotal computed（单项合计：余额/应计提/账面/差异各SUM）
    - 实现 agingGroupTotals computed（每组合小计行=SUM 6账龄段）
    - 实现 grandTotal computed（合计应计提=单项合计+各组合合计；总差异=合计应计提-合计账面）
    - 实现 diffAlert computed（总差异≠0时生成黄色el-alert文案）
    - 实现 addSingleRow/removeSingleRow/addAgingGroup/removeAgingGroup
    - 实现 updateSingleCell/updateAgingCell
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - _Requirements: 13.1-13.12, 27.1, 27.4_

  - [x]* 11.2 编写 Property 13 PBT：ECL应计提 = 余额 × 损失率
    - 生成器：`fc.float({min:0, max:1e9})` × balance, `fc.float({min:0, max:1})` × rate
    - 断言：calcExpectedProvision(balance, rate) === balance × rate
    - **Property 13: ECL应计提 = 余额 × 损失率**
    - **Validates: Requirements 13.3, 13.4**

  - [x]* 11.3 编写 Property 14 PBT：ECL差异 = 应计提 - 账面余额
    - 生成器：`fc.float({min:0, max:1e9})` × 2 (expectedProvision, bookBalance)
    - 断言：calcEclDifference(expectedProvision, bookBalance) === expectedProvision - bookBalance
    - **Property 14: ECL差异 = 应计提 - 账面余额**
    - **Validates: Requirements 13.3**

- [x] 12. 实现 useD6Inspection.ts 检查表D6-6（双区块+抽样参数19公式）
  - [x] 12.1 创建 `composables/useD6Inspection.ts`
    - 定义 InspectionSampleRow 类型（(1)区块含borrowAmount/creditAmount；(2)区块无borrowAmount仅creditAmount）
    - 定义 SamplingParams 类型（测试总体/特定样本/抽样总体/目标样本量/抽样方法/抽样过程）
    - 实现 samplingParams reactive（从D6-6-sampling-params加载）
    - 实现 block1Rows reactive（(1)本期增减变动检查，从D6-6-block1-rows加载）
    - 实现 block2Rows reactive（(2)期后贴现/背书/调整检查，从D6-6-block2-rows加载）
    - 实现 addSample(block)/removeSample(block, rowId)
    - 实现 checkRatioSummary computed（检查比例=检查金额/账面金额，从D6-2取账面金额合计）
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - _Requirements: 11.1-11.9, 25.1-25.3_

  - [x]* 12.2 编写 Property 16 PBT：期后结转联动一致性
    - 生成器：自定义 DetailRow[] + InspectionBlock2Row[] 生成器，共享customerName
    - 断言：detail.postPeriodSettlement === SUM(inspection.block2.filter(s => s.customerName === detail.customerName).map(s => s.creditAmount))
    - **Property 16: 期后结转联动一致性**
    - **Validates: Requirements 25.1, 25.3**

- [x] 13. 实现 useD6Disclosure.ts 附注披露（上市5子节163公式 / 国企3子节）
  - [x] 13.1 创建 `composables/useD6Disclosure.ts`
    - 上市公司版5子节：(1)分类(项目/期末(账面余额/减值准备/账面价值)/上年(同结构)) → (2)减值计提情况(类别/期末(余额/比例%/金额/损失率%)/上年(同)) → (3)按单项明细(名称/余额/准备/损失率%/理由) → (4)按组合明细(分组:组合名→账龄/余额/准备/损失率%) → (5)本期计提/转回/核销(项目/计提/转回/核销/原因)
    - 国企版3子节：(1)合同资产情况 → (2)减值准备(期初/计提/转回/核销/期末) → (3)本期账面价值重大变动
    - 实现 listedSections computed（从crossSheet取数：adjudicationForDisclosure/eclForDisclosure/impairmentChangesForDisclosure）
    - 实现 soeSections computed（从crossSheet取数简化版）
    - 实现 groupedDetails（上市版第4子节按组合分组，支持addGroup/addGroupedDetailRow）
    - 实现 showListed/showSoe computed（按applicable_standards判断适用性）
    - 实现 activeVariant ref（el-segmented切换'listed'|'soe'）
    - 实现 noteTexts 双向绑定 + EventBus disclosure:note-text-updated / note:section-updated监听
    - 实现比例列自动计算（比例%=该类别金额/合计金额×100%）
    - _Requirements: 15.1-15.9, 16.1-16.7, 17.1-17.7_

  - [x]* 13.2 编写 Property 17 PBT：附注按金额排序
    - 生成器：`fc.array(fc.record({name:fc.string(), amount:fc.float({min:0,max:1e9})}), {minLength:2, maxLength:20})`
    - 断言：排序后items[i].amount >= items[i+1].amount 恒成立（降序）
    - **Property 17: 附注按金额排序**
    - **Validates: Requirements 15.1**

- [x] 14. Checkpoint - 全部composable验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. 实现 D6TabProcedure.vue 程序表D6A
  - [x] 15.1 创建 `d6/D6TabProcedure.vue`（~200行）
    - 复用 GtAProgramConsole componentType（selfLoad：force_component_type=a-program-console）
    - GtIndexChip跳转：D6-1/D6-2/D6-3/D6-5/D6-6/D6-7/D6-8/D6-9/D0/D4/A1-1/A1-15/A1-16
    - EventBus监听risk:updated更新程序步骤状态
    - 特别标注ECL减值测算步骤（GtIndexChip跳D6-7+D6-8）
    - 特别标注函证程序步骤（GtIndexChip跳D0）
    - _Requirements: 18.1-18.6_

- [x] 16. 实现 D6TabAdjudication.vue 审定表D6-1
  - [x] 16.1 创建 `d6/D6TabAdjudication.vue`（~400行）
    - el-table三区块固定结构，区块间2px深灰分割线，区块标题带序号
    - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率|原因分析
    - "减：列示于其他非流动资产"行浅蓝色背景 + tooltip
    - 跨sheet自动取数单元格浅蓝色标记 + tooltip数据来源
    - 变动率>30%红色高亮 + 差异≠0红色高亮
    - 区块三底部：试算平衡表数行 + 差异行（差异≠0红色高亮）
    - 交叉验证：净值小计≠原值小计-坏账小计时黄色警告"净值≠原值-坏账准备，差额：±xxx元"
    - "审计说明"区域3个textarea（变动分析/计提充分性评价+GtIndexChip→D6-8/长期挂账+GtIndexChip→D6-6）
    - "审计结论"区域textarea
    - 每textarea旁🤖AI生成按钮 + 💬复核入口
    - 右键@cell-contextmenu → openReviewDialog
    - 编制提示`<details>`折叠（蓝色左边线+浅蓝背景，默认收起）
    - 金额fmtAmount + 比例fmtPercent
    - _Requirements: 2.1-2.10, 4.1-4.7, 26.1-26.6_

- [x] 17. 实现 D6TabDetail.vue 明细表D6-2
  - [x] 17.1 创建 `d6/D6TabDetail.vue`（~400行）
    - el-table横向滚动30+列，固定前4列（序号/合同名称/类型/客户名称）
    - 各下拉列：类型/关联关系/信用风险组合/是否在建设期
    - 自动计算列灰底不可编辑（期初审定/期末未审/期末审定）
    - 关联关系≠"非关联方"时整行橙色背景高亮
    - "添加明细行"按钮 + 行删除 + 按类型小计行 + 附加分类行 + 总合计行（不可编辑）
    - "从余额表导入"按钮 + "导出空模板"/"导入数据"按钮
    - 搜索框（合同名称/客户名称模糊搜索）
    - 超30行虚拟滚动
    - 金额右对齐 + fmtAmount + 零值"-" + 负数红色括号
    - "审计说明"3条textarea + 🤖AI + 💬复核
    - GtIndexChip跳转D6-6（期后结转）
    - _Requirements: 5.1-5.14, 6.1-6.8, 7.1-7.5_

- [x] 18. 实现 D6TabImpairmentDetail.vue 减值准备明细D6-3
  - [x] 18.1 创建 `d6/D6TabImpairmentDetail.vue`（~350行）
    - el-table 14列，双分类行结构（按单项评估计提 + 按信用风险组合计提）
    - 各分类区域内动态行 + 小计行 + 合计行（=单项小计+组合小计）
    - "添加单项计提行"/"添加组合计提行"按钮
    - 底部核对行（D6-3合计 vs D6-1坏账区块合计），差异≠0红色高亮
    - 自动计算列灰底
    - 金额fmtAmount
    - "审计说明"textarea + 🤖AI（基于计提/转回/核销变动分析） + "审计结论"textarea
    - _Requirements: 8.1-8.8_

- [x] 19. 实现 D6TabAdjustment.vue 调整分录D6-4
  - [x] 19.1 创建 `d6/D6TabAdjustment.vue`（~250行）
    - el-table 10列 + "新增调整分录"按钮
    - 底部借贷合计行 + 平衡指示（绿色✓平衡/红色✗不平衡：差额xxx）
    - "推送至A13"按钮（多选行）
    - 编制提示`<details>`折叠（蓝色左边线+浅蓝背景，默认收起）
    - _Requirements: 9.1-9.7_

- [x] 20. 实现 D6TabRelatedParty.vue 关联方检查D6-5
  - [x] 20.1 创建 `d6/D6TabRelatedParty.vue`（~300行）
    - el-table 14列
    - "关联关系"下拉（8种）
    - 自动计算列灰底（期末余额/账面价值）
    - "从D6-2导入"按钮（筛选关联关系≠非关联方） + "添加关联方"按钮
    - 底部合计行（期初/借方/贷方/期末/坏账/账面价值各列SUM）
    - 每行GtIndexChip跳转D6-2对应客户明细行
    - "审计说明"textarea + 🤖AI + "审计结论"textarea + 💬复核
    - _Requirements: 10.1-10.9_

- [x] 21. 实现 D6TabInspection.vue 检查表D6-6
  - [x] 21.1 创建 `d6/D6TabInspection.vue`（~350行）
    - 3区域布局：抽样参数区 + (1)本期增减变动检查 + (2)期后贴现/背书/调整检查
    - 抽样参数区6字段 + 进度条（已抽取/目标样本量）
    - (1)区块含借方+贷方列；(2)区块仅贷方列（无借方）
    - 各区块"添加样本"按钮 + 行删除
    - 底部检查比例汇总（方向/账面金额/检查金额/检查比例）
    - 集成抽凭引擎（voucher-sampling-engine）
    - (2)区块对方科目=主营业务收入时 GtIndexChip跳D4
    - 💬复核入口
    - _Requirements: 11.1-11.9_

- [x] 22. 实现 D6TabPolicyCheck.vue 减值政策D6-7（段落式）
  - [x] 22.1 创建 `d6/D6TabPolicyCheck.vue`（~300行）
    - 段落式卡片布局4节：(一)计提政策（左右分栏60%/40%） → (二)历史坏账损失 → (三)前瞻性信息 → (四)同行业对比（el-table动态行）
    - 第(一)节左=被审计单位政策textarea / 右=准则要求只读灰底
    - 第(四)节el-table 5列：公司名称/ECL描述/账龄组合比例/单项标准/差异分析 + 动态添加行
    - 每节底部"审计评价"textarea + 🤖AI
    - 底部"三、审计说明"textarea + "四、审计结论"textarea + 💬复核
    - GtIndexChip跳D6-8（验证政策执行一致性）
    - 所有textarea自动高度调整（min-height:120px, auto-grow）
    - 注：段落式组件无单独composable公式逻辑，直接读写useD6FormData
    - _Requirements: 12.1-12.8_

- [x] 23. 实现 D6TabEclCalculation.vue 减值测算D6-8
  - [x] 23.1 创建 `d6/D6TabEclCalculation.vue`（~400行）
    - 双区块布局：(一)单项计提 + (二)账龄组合（多组合子表）+ 合计
    - (一)单项 el-table 8列 + "添加债务人"按钮
    - (二)每组合独立子表（6账龄段+小计） + "添加组合"按钮
    - 自动计算列灰底（应计提③/差异⑤）
    - 底部合计行 + 总差异≠0时黄色el-alert
    - GtIndexChip跳D6-7（政策一致性）/ D6-3（核对账面余额）
    - ECL差异列不为零时提供GtIndexChip跳D6-3对应行
    - "审计说明"textarea + 🤖AI（评价损失率合理性+前瞻性调整）+ "审计结论"textarea + 💬复核
    - _Requirements: 13.1-13.12_

- [x] 24. 实现 D6TabWriteoffCheck.vue 转回核销D6-9
  - [x] 24.1 创建 `d6/D6TabWriteoffCheck.vue`（~300行）
    - 双段结构：(一)转回检查8列 + (二)核销检查8列
    - 各区块"添加转回记录"/"添加核销记录"按钮 + 行删除
    - 各区块底部合计行（转回金额合计/核销金额合计）
    - (二)核销"是否由关联交易产生"下拉（是/否），选"是"整行橙色高亮
    - 转回记录每行GtIndexChip跳D6-3对应项目
    - "审计说明"textarea + 🤖AI + "审计结论"textarea + 💬复核
    - _Requirements: 14.1-14.9_

- [x] 25. 实现 D6TabDisclosure.vue 附注披露
  - [x] 25.1 创建 `d6/D6TabDisclosure.vue`（~400行）
    - el-segmented切换（"上市公司版" | "国企版"），按applicable_standards自动显示/隐藏
    - 上市公司版：5子节卡片（分类/减值计提/单项明细/组合明细(分组)/计提转回核销）
    - 国企版：3子节卡片（合同资产情况/减值准备/重大变动）
    - 跨sheet浅蓝色取数 + tooltip来源（审定表/ECL测算/减值明细）
    - 第(4)子节按组合分组显示（每组合独立子表+分组标题）+ "添加组合"按钮
    - 第(3)(4)(5)子节动态行添加/删除
    - 比例列自动计算 + 合计行
    - 每子节底部"说明"textarea（双向回写附注模块 EventBus）+ 编制提示`<details>`折叠
    - GtIndexChip跳D6-1/D6-8/D6-3（数据来源溯源）
    - _Requirements: 15.1-15.9, 16.1-16.7, 17.1-17.7_

- [x] 26. Checkpoint - 全部Vue组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 27. 实现后端导入导出端点
  - [x] 27.1 创建 `backend/app/routers/wp_render_strategies/_d6_import_export.py`
    - POST /api/workpapers/{wp_id}/d6/export-template?sheet=D6-2|D6-3|D6-5|D6-8（空白xlsx模板）
    - POST /api/workpapers/{wp_id}/d6/export-data?sheet=D6-2|D6-3|D6-5|D6-8（含数据xlsx）
    - POST /api/workpapers/{wp_id}/d6/import-data?sheet=D6-2|D6-3|D6-5|D6-8（解析xlsx回写）
    - POST /api/workpapers/{wp_id}/d6/import-aux-balance（从tb_aux_balance科目1402按客户/合同维度导入）
    - 格式校验：列名不匹配→400+错误列表
    - 注册路由到router_registry
    - _Requirements: 6.1-6.7, 24.3_

  - [x]* 27.2 编写 Property 11 PBT（后端hypothesis）：导入导出Round-Trip
    - 生成随机DetailRow[]/ImpairmentRow[]/RelatedPartyRow[]/EclRow[]→export→import→验证等价
    - 模板格式校验：随机列名→验证错误检测
    - **Property 11: 导入导出Round-Trip**
    - **Validates: Requirements 6.5, 6.6**

- [x] 28. 实现后端Resolver和AI生成端点
  - [x] 28.1 创建 `backend/app/routers/wp_render_strategies/_d6_resolvers.py`
    - 注册`d6_tb_unadjusted` resolver到_REGISTRY（从trial_balance科目1402取期初/期末未审数）
    - 注册`d6_impairment_tb` resolver到_REGISTRY（从trial_balance坏账准备相关科目取期初/期末未审数）
    - _Requirements: 28.3, 28.4, 24.1, 24.6_

  - [x] 28.2 创建 `backend/app/routers/wp_render_strategies/_d6_ai_generate.py`
    - POST /api/workpapers/{wp_id}/d6/ai-generate 端点
    - 支持16个section（adj-explanation/adj-impairment-eval/adj-long-term/adj-conclusion/detail-change/detail-aging/detail-post-settlement/impairment-explanation/ecl-explanation/ecl-conclusion/policy-eval-1~4/related-party/inspection/writeoff/disclosure-note）
    - 自动加载D6各sheet数据 + project_context作为LLM context
    - 注册到router_registry "AI与辅助"组
    - _Requirements: 4.2, 4.3, 7.2, 7.3, 8.8, 10.7, 12.4, 12.5, 13.10, 14.7_

- [x] 29. 实现后端render策略与account_package_registry
  - [x] 29.1 创建 `backend/app/routers/wp_render_strategies/_d6_contract_assets.py`
    - 在RENDERER_DISPATCH注册'd6-contract-assets'→`_render_d6_contract_assets`策略函数
    - 实现`_render_d6_contract_assets`返回审定表三区块结构+明细表行数据+减值明细+ECL组合数据+各sheet配置
    - 读取D6.yaml render schema中的fixed_cells和dynamic_table配置生成初始结构化数据
    - _Requirements: 28.1, 28.2, 28.6_

  - [x] 29.2 更新 account_package_registry.json
    - 添加D6_contract_assets工作包定义（含12个有效sheet：D6A/D6-1/D6-2/D6-3/D6-4/D6-5/D6-6/D6-7/D6-8/D6-9/附注上市/附注国企）
    - sheets数组顺序严格对齐源模板xlsx的sheet顺序
    - _Requirements: 28.5_

- [x] 30. 集成主入口与双模式切换
  - [x] 30.1 完善 GtD6ContractAssets.vue 主入口
    - el-tabs 11个tab-pane引用11个子组件
    - Tab顺序对齐源模板sheet顺序：D6A→D6-1→D6-2→D6-3→D6-4→D6-5→D6-6→D6-7→D6-8→D6-9→附注
    - 传递allResponses/wpId/projectId/isReadonly/crossSheet等props
    - provide openReviewDialog（inject模式零成本集成复核）
    - _Requirements: 1.1, 1.2, 22.5_

  - [x] 30.2 在所有子组件中实现HTML ↔ OnlyOffice双模式切换
    - 每个Tab页头部el-segmented（"结构化视图"|"在线编辑"）
    - 切OO：获取onlyoffice-config → GtOnlyOfficeSheet → 隐藏非当前sheet(SetVisible(false))
    - 切回HTML：重新加载checklist_responses刷新
    - OO不可用时禁用+tooltip
    - _Requirements: 21.1-21.4_

- [x] 31. Checkpoint - 后端与双模式验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 32. 回归测试与全量验证
  - [x] 32.1 运行全量测试确保无回归
    - vitest run 所有D6相关spec文件
    - python -m pytest backend/tests/ -k d6
    - 验证htmlRendererRegistry注册数量更新
    - 验证VALID_COMPONENT_TYPES含'd6-contract-assets'
    - 验证wp_code_overrides D6/D6-1~D6-9共10个映射正确
    - 验证RENDERER_DISPATCH含'd6-contract-assets'策略
    - 验证auto_data_resolvers._REGISTRY含d6_tb_unadjusted和d6_impairment_tb
    - 验证account_package_registry含D6工作包12个sheet
    - _Requirements: all_

  - [x]* 32.2 编写 Property 20 PBT：ECL→D6-3→D6-1联动链完整性
    - 生成器：自定义 EclData + ImpairmentData + AdjudicationData 生成器
    - 断言：D6-8 grandTotal = SUM(单项) + SUM(各组合)；D6-3 total = SUM(单项rows) + SUM(组合rows)；D6-1区块二合计 = D6-3 total；D6-1区块三净值合计 = 区块一合计 - 区块二合计
    - **Property 20: ECL→D6-3→D6-1联动链完整性**
    - **Validates: Requirements 27.1, 27.2, 27.3**

- [x] 33. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional PBT tests
- 每个Property对应design.md中的一个correctness property（共20个PBT）
- 所有PBT使用fast-check（前端）或hypothesis（后端），numRuns: 100
- 借方科目核心公式：期末未审 = 期初审定 + 借方发生 - 贷方发生
- 三区块核心：净值=原值-坏账准备（逐行跨区块联动）
- ECL核心：应计提=余额×损失率；差异=应计提-账面余额
- 跨sheet全部通过allResponses computed链，不走API调用
- selfLoad必须支持（bundle内嵌场景htmlData为null）
- 程序表D6A复用a-program-console componentType，不需单独实现公式
- D6-7段落式会计政策检查（非表格），Vue组件直接读写useD6FormData，无单独composable公式逻辑
- D6特色：三区块审定表净值=原值-坏账跨区块联动、ECL双组合测算（单项+账龄组合×多组合）、30列平台最宽明细表、段落式政策检查、163公式最复杂附注（5子节含按组合分组）
- ECL→D6-3→D6-1联动链：D6-8应计提参考值→D6-3核对→D6-1坏账区块→净值区块
- D6-2↔D6-6期后结转双向联动：D6-6(2)区块贷方→D6-2期后结转金额列累加
- AI生成端点复用B14/A17-1模式：project_context + 底稿数据snapshot + CPA system prompt
- 附注上市(163公式)比附注国企(~30公式)复杂得多：含5子节+按组合分组明细+比例列
- 科目1402合同资产，借方科目/资产类，D循环中第二复杂底稿（仅次于D4营业收入）
