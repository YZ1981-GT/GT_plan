# Implementation Plan: D7 合同负债底稿专属HTML精美组件

## Overview

实现D7合同负债底稿专属组件`d7-contract-liabilities`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtD7ContractLiabilities.vue + 9个子组件 + 11个composable + 后端3个py文件。科目2205贷方/负债类，9有效sheet，核心贷方科目公式：期末=期初+贷方-借方。双区块审定表（按性质+按账龄，含"减：计入其他非流动负债"扣减行）、27列明细表、4区块分析表（含Top10）、CAS14合同负债vs预收账款区分联动。

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将D7/D7-1/D7-2/D7-3/D7-4/D7-5/D7-6/D7-7映射为'd7-contract-liabilities'
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'd7-contract-liabilities'
    - 在 `htmlRendererRegistry.ts` 中注册 'd7-contract-liabilities' → GtD7ContractLiabilities 映射
    - 创建 `GtD7ContractLiabilities.vue` 主入口骨架（el-tabs 8个tab-pane + selfLoad逻辑）
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 1.8_

  - [x] 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'd7-contract-liabilities'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证D7/D7-1/D7-2/D7-3/D7-4/D7-5/D7-6/D7-7映射
    - _Requirements: 1.5, 1.6, 1.7_

- [x] 2. 实现共享公式引擎 useD7FormulaEngine.ts
  - [x] 2.1 创建 `composables/useD7FormulaEngine.ts`，实现全部纯函数
    - 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN/Infinity → 0）
    - 实现 `calcCreditEndBalance`（贷方科目期末余额 = 期初 + 贷方发生 - 借方发生）
    - 实现 `calcAuditedAmount`（审定数 = 未审 + AJE + RJE）
    - 实现 `calcChangeAmount`（变动额 = 期末审定 - 期初审定）
    - 实现 `calcChangeRate`（变动率，含期初=0特殊处理：两期均0→'' / 期初=0→'N/A'）
    - 实现 `isChangeRateExceeding`（阈值判定，非数值类型返回false）
    - 实现 `calcSubtotal`（合计 = SUM数组）
    - 实现 `calcContractLiabilityTotal`（合同负债合计 = 小计 - 非流动负债扣减）
    - 实现 `aggregateByNature`（按款项性质分组SUM）
    - 实现 `aggregateByAging`（按审定账龄4段列SUM）
    - 实现 `topNByField`（按指定字段降序取前N）
    - _Requirements: 1.4, 2.3, 2.4, 2.5, 2.6, 5.4, 9.4, 11.3_

  - [x]* 2.2 编写 Property 1 PBT：贷方科目期末余额公式
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 3 (opening, credit, debit)
    - 断言：calcCreditEndBalance(opening, credit, debit) === opening + credit - debit
    - **Feature: d7-contract-liabilities, Property 1: 贷方科目期末余额公式**
    - **Validates: Requirements 1.4, 5.4, 11.3**

  - [x]* 2.3 编写 Property 2 PBT：审定数 = 未审 + AJE + RJE
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 3
    - 断言：calcAuditedAmount(u, a, r) === u + a + r
    - **Feature: d7-contract-liabilities, Property 2: 审定数 = 未审 + AJE + RJE**
    - **Validates: Requirements 1.4, 2.3**

  - [x]* 2.4 编写 Property 3 PBT：合同负债合计 = 小计 - 非流动负债扣减
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 2 (subtotal, deduction)
    - 断言：calcContractLiabilityTotal(subtotal, deduction) === subtotal - deduction
    - **Feature: d7-contract-liabilities, Property 3: 合同负债合计 = 小计 - 非流动负债扣减**
    - **Validates: Requirements 2.6**

  - [x]* 2.5 编写 Property 6 PBT：合计行 = SUM(明细行)
    - 生成器：`fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:30})`
    - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
    - **Feature: d7-contract-liabilities, Property 6: 合计行 = SUM(明细行)**
    - **Validates: Requirements 2.5, 5.5, 10.4, 11.6**

  - [x]* 2.6 编写 Property 9 PBT：变动率阈值高亮判定
    - 生成器：`fc.float({min:-10, max:10})`
    - 断言：isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)；空串/'N/A'→false
    - **Feature: d7-contract-liabilities, Property 9: 变动率阈值高亮判定**
    - **Validates: Requirements 2.7**

  - [x]* 2.7 编写 Property 16 PBT：变动额与变动率计算
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 2 (prior, current)
    - 断言：calcChangeAmount === current - prior；calcChangeRate符合期初=0规则
    - **Feature: d7-contract-liabilities, Property 16: 变动额与变动率计算**
    - **Validates: Requirements 2.4**

  - [x]* 2.8 编写 Property 17 PBT：变动率特殊情况边界
    - 生成器：`fc.float({min:0, max:0})` + `fc.float({min:-1e9, max:1e9})` 组合
    - 断言：期初=0且期末=0→''；期初=0且期末≠0→'N/A'；isChangeRateExceeding对非数值返回false
    - **Feature: d7-contract-liabilities, Property 17: 变动率特殊情况边界**
    - **Validates: Requirements 2.4, 2.7**

- [x] 3. 实现 useD7FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useD7FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate（PUT单条response）
    - 实现 debouncedSave（2秒debounce版本）
    - 实现 saveBatch（批量保存）
    - 实现 writebackTrialBalance（回写科目2205，贷方科目/负债类）
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=d7-contract-liabilities）
    - _Requirements: 1.8, 3.6, 20.5, 20.7, 20.8_

- [x] 4. 实现 useD7CrossSheet.ts 跨Sheet联动
  - [x] 4.1 创建 `composables/useD7CrossSheet.ts`
    - 实现 natureAggregation computed（D7-2按"款项性质"聚合endAudited到预收货款/开发项目预收款/预收工程款/其他）
    - 实现 agingAggregation computed（D7-2按审定账龄4段列SUM：1年以内/1~2年/2~3年/3年以上）
    - 实现 adjustmentTotals computed（从D7-3行汇总AJE/RJE）
    - 实现 adjudicationForDisclosure computed（审定表数据供附注引用）
    - 实现 voucherPostTransferTotal computed（D7-7期后结转贷方合计）
    - 实现 crossValidation computed（性质分类合计 vs 账龄分类合计交叉验证）
    - 实现 crossSheetStatus状态管理（loaded/loading/error + 失败时"-"占位+黄色三角）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 2.9, 24.3_

  - [x]* 4.2 编写 Property 4 PBT：按性质聚合正确性
    - 生成器：自定义 DetailRow[] 生成器（natureType随机从'预收货款'/'开发项目预收款'/'预收工程款'/'其他'取）
    - 断言：各类别sum === 手动filter+reduce结果
    - **Feature: d7-contract-liabilities, Property 4: 按性质聚合正确性（D7-2→D7-1）**
    - **Validates: Requirements 3.1**

  - [x]* 4.3 编写 Property 5 PBT：按账龄聚合正确性
    - 生成器：自定义 DetailRow[] 生成器（4段aging字段随机）
    - 断言：各账龄段sum === 手动map+reduce结果
    - **Feature: d7-contract-liabilities, Property 5: 按账龄聚合正确性（D7-2→D7-1）**
    - **Validates: Requirements 3.2**

  - [x]* 4.4 编写 Property 12 PBT：双区块交叉验证
    - 生成器：自定义 DetailRow[] 生成器（endAudited=SUM(endAging1~4)约束）
    - 断言：按性质聚合合计 === 按账龄聚合合计（当每行账龄之和=endAudited时恒成立）
    - **Feature: d7-contract-liabilities, Property 12: 性质分类合计 = 账龄分类合计（双区块交叉验证）**
    - **Validates: Requirements 2.9**

- [x] 5. Checkpoint - 公式引擎与基础设施验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 实现 useD7Adjudication.ts 审定表D7-1（双区块）
  - [x] 6.1 创建 `composables/useD7Adjudication.ts`
    - 定义双区块固定行配置（NATURE_BLOCK: 预收货款/开发项目预收款/预收工程款/其他/小计/减：计入其他非流动负债的合同负债/合同负债合计）
    - 定义AGING_BLOCK（1年以内/1~2年/2~3年/3年以上/合计/试算平衡表数/差异数）
    - 实现 natureRows computed（从allResponses加载 + crossSheet.natureAggregation填入 + 公式计算）
    - 实现 agingRows computed（从allResponses加载 + crossSheet.agingAggregation填入 + 公式计算）
    - 实现 小计行公式（=SUM对应明细行）+ 合同负债合计（=小计-非流动负债扣减）
    - 实现 账龄合计行（=SUM 4段）+ 差异行（=合计-试算平衡表数）
    - 实现 crossValidationWarning computed（性质合计≠账龄合计时黄色警告）
    - 实现 trialBalanceAmount（从TB auto_data取数科目2205）+ trialBalanceDiff computed
    - 实现 auditNotes 双向绑定（explanation/conclusion/agingExplanation）
    - 实现 updateCell（编辑 → 公式重算 → debouncedSave）
    - 实现 publishAdjudicated（EventBus: substantive:adjudicated，payload含2205/auditedAmount）
    - 实现 onAdjustmentCreated监听（AJE/RJE累加）
    - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率|原因分析
    - _Requirements: 2.1-2.9, 3.1-3.7, 4.1-4.7, 17.1, 18.1, 23.1_

- [x] 7. 实现 useD7Detail.ts 明细表D7-2（27列）
  - [x] 7.1 创建 `composables/useD7Detail.ts`
    - 定义 DetailRow 类型（27列完整字段：合同名称~期后结转）
    - 实现 rows reactive（从D7-2-rows加载JSON数组）
    - 实现行内贷方科目公式链：期初审定=未审+AJE+RJE；期末余额=期初审定+贷方-借方；期末未审=期末余额+重分类；期末审定=期末未审+AJE+RJE
    - 实现 totalRow computed（合计行=SUM所有客户行各金额列）+ verificationRow computed（核对行=合计-试算表数）
    - 实现 addRow/removeRow/updateCell
    - 实现 importFromAuxBalance（调后端API从tb_aux_balance科目2205按客户导入）
    - 实现 searchFilter + filteredRows computed（按单位名称/合同名称模糊搜索）
    - 实现 关联方自动匹配（输入单位名称→模糊匹配related_parties→填充关联关系列）
    - 实现 onConfirmationCompleted监听（EventBus 'confirmation:completed'→标Y）
    - 实现 期后结转联动（D7-7 postTransferRows按客户名匹配累加creditAmount）
    - 对"类型(款项性质)"列应用下拉选择（预收货款/开发项目预收款/预收工程款/其他）
    - 对"关联关系"列应用下拉选择（非关联方/实际控制人/控股股东/...）
    - _Requirements: 5.1-5.12, 6.1-6.7, 7.1-7.5, 18.4, 24.1-24.3_

  - [x]* 7.2 编写 Property 10 PBT：D7-2行公式链正确性
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 8 (priorUnadjusted,priorAje,priorRje,creditAmount,debitAmount,entityReclass,endAje,endRje)
    - 断言：priorAudited=u+a+r; endBalance=priorAudited+credit-debit; endUnadjusted=endBalance+reclass; endAudited=endUnadjusted+endAje+endRje
    - **Feature: d7-contract-liabilities, Property 10: D7-2行内公式链正确性**
    - **Validates: Requirements 5.4**

  - [x]* 7.3 编写 Property 7 PBT：动态行添加保持结构不变量
    - 生成器：`fc.array(DetailRow生成器, {minLength:0, maxLength:20})`
    - 断言：addRow后length=N+1；新行数值全0；新行位于合计行之前
    - **Feature: d7-contract-liabilities, Property 7: 动态行添加保持结构不变量**
    - **Validates: Requirements 5.6, 8.2, 10.3, 11.5, 12.4**

- [x] 8. 实现 useD7Adjustment.ts 调整分录D7-3
  - [x] 8.1 创建 `composables/useD7Adjustment.ts`
    - 定义 AdjustmentRow 类型（10列）
    - 实现 rows reactive（从D7-3-rows加载JSON）
    - 实现 debitTotal/creditTotal/isBalanced/balanceDiff computed
    - 实现 addRow/removeRow/updateCell
    - 实现 publishAdjustment（EventBus adjustment:created，payload含wpCode='D7'/entryType/amount/accountCode='2205'）
    - 实现 pushToA13（EventBus推送选中分录至A13错报汇总）
    - _Requirements: 8.1-8.7, 18.2_

  - [x]* 8.2 编写 Property 8 PBT：借贷平衡
    - 生成器：`fc.array(fc.record({debit:fc.float({min:0,max:1e9}), credit:fc.float({min:0,max:1e9})}))`
    - 断言：isBalanced === (debitTotal === creditTotal)
    - **Feature: d7-contract-liabilities, Property 8: 调整分录借贷平衡检查**
    - **Validates: Requirements 8.3**

- [x] 9. 实现 useD7Analysis.ts 分析表D7-4（4区块）
  - [x] 9.1 创建 `composables/useD7Analysis.ts`
    - 实现 (一)借方发生额分析：debitRows computed（TB取数科目2205 + 按对方科目分拆）+ debitTotal + debitDiff（=TB总计-分拆合计）
    - 实现 (三)贷方发生额分析：creditRows computed + creditTotal + creditDiff
    - 实现 (四)期末Top10债务人：top10Rows computed（从D7-2按endAudited降序前10）+ 变动金额/变动比例/账龄/期后结转
    - 实现 top10Concentration computed（占合计百分比）+ isHighConcentration（>50%黄色提示）
    - 实现 差异行红色高亮（差异≠0时）
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - 实现 publishSignificantChange（EventBus 'analytical:significant-change'，变动>30%时）
    - _Requirements: 9.1-9.10, 18.3, 23.2_

  - [x]* 9.2 编写 Property 13 PBT：Top10排序正确性
    - 生成器：`fc.array(fc.record({endAudited:fc.float({min:0,max:1e9})}), {minLength:10, maxLength:50})`
    - 断言：(1)长度=min(10,N)；(2)降序排列；(3)结果集最小值≥未入选最大值
    - **Feature: d7-contract-liabilities, Property 13: Top10排序正确性**
    - **Validates: Requirements 9.4**

- [x] 10. 实现 useD7LongTerm.ts 账龄1年以上D7-5
  - [x] 10.1 创建 `composables/useD7LongTerm.ts`
    - 定义 LongTermRow 类型（8列：客户名称/期末余额/账龄/经济业务说明/未结转原因/至审计日结转金额/处理计划/备注）
    - 实现 rows reactive（从D7-5-rows加载JSON数组）
    - 实现 totalRow computed（期末余额/至审计日结转金额各列SUM）
    - 实现 addRow/removeRow/updateCell
    - 实现 importFromD72（从D7-2筛选审定账龄>1年的客户行导入）
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - _Requirements: 10.1-10.8_

- [x] 11. 实现 useD7RelatedParty.ts 关联方D7-6
  - [x] 11.1 创建 `composables/useD7RelatedParty.ts`
    - 定义 RelatedPartyRow 类型（11列：关联方名称/关联关系/期初余额/借方发生/贷方发生/期末余额/发生时间及账龄/未结转原因/至审计日结转金额/处理计划/备注）
    - 实现 rows reactive（从D7-6-rows加载JSON数组）
    - 实现行内公式：期末余额=期初余额+贷方发生-借方发生（贷方科目）
    - 实现 totalRow computed（期初/借方/贷方/期末/至审计日结转各列SUM）
    - 实现 addRow/removeRow/updateCell
    - 实现 importFromD72（从D7-2筛选"关联关系≠非关联方"的客户行导入）
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - _Requirements: 11.1-11.9_

  - [x]* 11.2 编写 Property 14 PBT：关联方期末余额公式
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 3 (opening, credit, debit)
    - 断言：endBalance === opening + credit - debit（贷方科目公式）
    - **Feature: d7-contract-liabilities, Property 14: 关联方期末余额公式**
    - **Validates: Requirements 11.3**

- [x] 12. 实现 useD7VoucherCheck.ts 凭证检查D7-7
  - [x] 12.1 创建 `composables/useD7VoucherCheck.ts`
    - 定义 VoucherCheckRow 类型 + SamplingParams 类型
    - 实现 samplingParams reactive（从D7-7-sampling-params加载JSON）
    - 实现 periodChangeRows reactive（从D7-7-period-rows加载，本期增减变动区块）
    - 实现 postTransferRows reactive（从D7-7-post-rows加载，期后结转区块，无借方金额列）
    - 实现 checkedCount/abnormalCount/abnormalRate computed（汇总公式）
    - 实现 postTransferCreditTotal computed（期后结转贷方合计 → 供crossSheet联动D7-2）
    - 实现 addSample/removeSample/updateCell（按block区分）
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - _Requirements: 12.1-12.9, 18.5, 24.1-24.3_

  - [x]* 12.2 编写 Property 15 PBT：期后结转联动一致性
    - 生成器：自定义 VoucherRow[] + DetailRow[] 生成器（客户名匹配）
    - 断言：D7-7期后结转贷方合计 === D7-2中对应客户行"期后结转"列合计
    - **Feature: d7-contract-liabilities, Property 15: 期后结转联动一致性（D7-7→D7-2）**
    - **Validates: Requirements 24.3**

- [x] 13. 实现 useD7Disclosure.ts 附注披露
  - [x] 13.1 创建 `composables/useD7Disclosure.ts`
    - 上市公司版3子节：(1)按性质分类（固定行+减：非流动负债+合计，从crossSheet.adjudicationForDisclosure取数）(2)账龄超过1年的重要合同负债（动态行+合计，从D7-5取数）(3)本期重大变动（动态行+合计）
    - 国企版2子节：(1)按性质分类（固定行+合计）(2)本期重大变动（动态行+合计）
    - 实现 showListed/showSoe computed（根据applicable_standards判断）
    - 实现 activeVariant（el-segmented切换'listed'/'soe'）
    - 实现 addDynamicRow/removeDynamicRow（对第(2)(3)子节）
    - 实现 各子节合计行自动计算
    - 实现 noteTexts 双向绑定 + EventBus disclosure:note-text-updated
    - 实现 onNoteSectionUpdated监听（EventBus 'note:section-updated'，last-write-wins）
    - _Requirements: 13.1-13.8, 14.1-14.6, 15.1-15.6_

- [x] 14. Checkpoint - 全部composable验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. 实现 D7TabProcedure.vue 程序表
  - [x] 15.1 创建 `d7/D7TabProcedure.vue`（~200行）
    - 复用 GtAProgramConsole componentType（selfLoad：force_component_type=a-program-console）
    - GtIndexChip跳转：D7-1/D7-2/D7-4/D7-5/D7-6/D7-7/D0/D3/D4/A1-1/A1-15/A1-16
    - CAS14准则相关程序步骤提供GtIndexChip跳转D3预收账款底稿
    - EventBus监听risk:updated更新程序步骤状态
    - _Requirements: 16.1-16.5, 17.4, 18.6, 19.6_

- [x] 16. 实现 D7TabAdjudication.vue 审定表
  - [x] 16.1 创建 `d7/D7TabAdjudication.vue`（~400行）
    - 双区块el-table固定行结构（一、按性质分类7行 + 二、按账龄分类7行）
    - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率|原因分析
    - "减：计入其他非流动负债的合同负债"行浅蓝背景 + 可编辑
    - 合同负债合计=小计-非流动负债扣减（自动计算灰底）
    - 跨sheet自动取数单元格浅蓝色标记 + tooltip数据来源
    - 变动率>30%红色高亮 + 差异≠0红色高亮
    - 交叉验证：性质合计≠账龄合计时黄色el-alert显示差额
    - 试算平衡表数行（科目2205）+ 差异行
    - CAS14准则提示折叠区（`<details>`蓝色左边线+浅蓝背景，默认收起，合同负债vs预收账款区分决策树）
    - "审计说明"区域3条textarea（超1年原因+变动分析+账龄说明）+ 🤖AI按钮 + GtIndexChip(→D7-5, →D7-2, →D3)
    - "审计结论"区域：textarea + 🤖AI按钮
    - 💬复核入口 + 右键@cell-contextmenu
    - 金额fmtAmount + el-segmented双模式
    - _Requirements: 2.1-2.9, 3.4, 3.6, 4.1-4.7, 17.1-17.3, 19.1, 20.1, 21.1-21.5, 22.1-22.4_

- [x] 17. 实现 D7TabDetail.vue 明细表
  - [x] 17.1 创建 `d7/D7TabDetail.vue`（~400行）
    - el-table横向滚动27列，固定前2列（合同名称/项目名称、单位名称）
    - "类型(款项性质)"下拉（预收货款/开发项目预收款/预收工程款/其他）+ 蓝色info提示CAS14
    - "关联关系"下拉（非关联方/实际控制人/控股股东/...）+ 非关联方时橙色行高亮
    - 自动计算列灰底不可编辑（期初审定/期末余额/期末未审/期末审定）
    - "添加客户"按钮 + 行删除 + 合计行 + 核对行（不可编辑）
    - "从余额表导入"按钮 + "导出空模板"/"导入数据"按钮
    - 搜索框（按单位名称/合同名称模糊筛选）
    - GtIndexChip：关联方行→D7-6
    - 超30行虚拟滚动
    - 3条审计说明textarea（期末变动/合同履行/超1年原因）+ 🤖AI + GtIndexChip(→D7-5)
    - "审计结论"textarea + 💬复核
    - 金额右对齐 + fmtAmount + 零值"-" + 负数红色括号
    - el-segmented双模式
    - _Requirements: 5.1-5.12, 6.1-6.7, 7.1-7.5, 17.2, 19.3, 20.1, 22.1-22.5_

- [x] 18. 实现 D7TabAdjustment.vue 调整分录
  - [x] 18.1 创建 `d7/D7TabAdjustment.vue`（~250行）
    - el-table 10列 + "新增调整分录"按钮
    - 底部借贷合计行 + 平衡指示（绿色✓平衡/红色✗不平衡：差额xxx）
    - "推送至A13"按钮（多选行）
    - 编制提示details折叠（蓝色左边线+浅蓝背景，默认收起）
    - el-segmented双模式
    - _Requirements: 8.1-8.7, 20.1_

- [x] 19. 实现 D7TabAnalysis.vue 分析表
  - [x] 19.1 创建 `d7/D7TabAnalysis.vue`（~350行）
    - 4区块卡片式布局：(一)借方发生额分析 + (三)贷方发生额分析 + (四)Top10债务人 + 审计说明/结论
    - 借方/贷方区块底部差异行（差异≠0红色高亮）
    - Top10表：债权人名称/期末/期初/变动金额/变动比例/账龄/期后结转
    - Top10集中度>50%黄色高亮提示
    - Top10每行GtIndexChip跳转D7-2对应客户行
    - "审计说明"textarea + 🤖AI + "审计结论"textarea + 🤖AI
    - el-segmented双模式
    - _Requirements: 9.1-9.10, 19.2, 20.1_

- [x] 20. 实现 D7TabLongTerm.vue 账龄1年以上
  - [x] 20.1 创建 `d7/D7TabLongTerm.vue`（~250行）
    - el-table 8列 + "从D7-2导入"按钮 + "添加行"按钮
    - 底部合计行（期末余额/至审计日结转金额列SUM）
    - 每行GtIndexChip跳转D7-2对应客户行
    - "未结转原因"列🤖AI建议按钮
    - "审计说明"textarea + 🤖AI + "审计结论"textarea
    - 金额格式化（千分位/负数红色括号/零值"-"）
    - el-segmented双模式
    - _Requirements: 10.1-10.8, 19.3, 20.1_

- [x] 21. 实现 D7TabRelatedParty.vue 关联方
  - [x] 21.1 创建 `d7/D7TabRelatedParty.vue`（~300行）
    - el-table 11列 + "从D7-2导入"按钮 + "添加关联方"按钮
    - "关联关系"下拉（实际控制人/控股股东/...）
    - 期末余额=期初+贷方-借方 自动计算列灰底
    - 底部合计行（期初/借方/贷方/期末/至审计日结转各列SUM）
    - 每行GtIndexChip跳转D7-2对应客户行
    - "审计说明"textarea + 🤖AI + "审计结论"textarea + 💬复核
    - el-segmented双模式
    - _Requirements: 11.1-11.9, 19.3, 20.1, 21.1-21.3_

- [x] 22. 实现 D7TabVoucherCheck.vue 凭证检查
  - [x] 22.1 创建 `d7/D7TabVoucherCheck.vue`（~350行）
    - 3区域布局：抽样参数区 + (1)本期增减变动检查表 + (2)期后结转检查表
    - 抽样参数区6字段 + 进度条（已抽取/目标样本量）
    - (1)本期变动：含借方+贷方金额列 + 核对内容(1-5)checkbox + 是否异常
    - (2)期后结转：无借方金额列 + 对方科目为主营业务收入时GtIndexChip跳转D4
    - 各区块"添加样本"按钮
    - 底部汇总：已检查笔数/异常笔数/异常率
    - 集成抽凭引擎（voucher-sampling-engine）
    - "审计说明"textarea + "审计结论"textarea + 💬复核
    - el-segmented双模式
    - _Requirements: 12.1-12.9, 18.5, 19.4, 20.1, 21.1-21.3_

- [x] 23. 实现 D7TabDisclosure.vue 附注披露
  - [x] 23.1 创建 `d7/D7TabDisclosure.vue`（~350行）
    - el-segmented切换（"上市公司版" | "国企版"）
    - 上市公司版3子节卡片：(1)按性质分类（固定行+减：非流动+合计）(2)超1年重要合同负债（动态行+合计）(3)重大变动（动态行+合计）
    - 国企版2子节卡片：(1)按性质分类（固定行+合计）(2)重大变动（动态行+合计）
    - 跨sheet浅蓝色取数 + tooltip来源
    - 各子节动态添加/删除行
    - 各子节合计行自动计算
    - 每子节"说明"textarea（双向回写附注模块 EventBus）+ 编制提示折叠
    - 按applicable_standards自动显示/隐藏版本
    - 各子节GtIndexChip跳转D7-1审定数来源行
    - el-segmented双模式（结构化视图/在线编辑）
    - _Requirements: 13.1-13.8, 14.1-14.6, 15.1-15.6, 19.5, 20.1_

- [x] 24. Checkpoint - 全部Vue组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 25. 实现后端导入导出端点
  - [x] 25.1 创建 `backend/app/routers/wp_render_strategies/_d7_import_export.py`
    - POST /api/workpapers/{wp_id}/d7/export-template?sheet=D7-2|D7-5|D7-6（空白xlsx模板）
    - POST /api/workpapers/{wp_id}/d7/export-data?sheet=D7-2|D7-5|D7-6（含数据xlsx）
    - POST /api/workpapers/{wp_id}/d7/import-data?sheet=D7-2|D7-5|D7-6（解析xlsx回写）
    - POST /api/workpapers/{wp_id}/d7/import-aux-balance（从tb_aux_balance科目2205按客户导入）
    - 格式校验：列名不匹配→400+错误列表
    - 注册路由到router_registry
    - _Requirements: 6.5, 6.6, 6.7, 25.1_

  - [x]* 25.2 编写 Property 11 PBT（后端hypothesis）：导入导出Round-Trip
    - 生成随机DetailRow[]/LongTermRow[]/RelatedPartyRow[]→export→import→验证等价
    - 模板格式校验：随机列名→验证错误检测
    - **Feature: d7-contract-liabilities, Property 11: 导入导出Round-Trip**
    - **Validates: Requirements 6.5, 6.6**

- [x] 26. 实现后端Resolver和AI生成端点
  - [x] 26.1 创建 `backend/app/routers/wp_render_strategies/_d7_resolvers.py`
    - 注册`d7_tb_unadjusted` resolver到_REGISTRY（从trial_balance科目2205取期初/期末未审数）
    - 注册`d7_ledger_analysis` resolver到_REGISTRY（从tb_ledger科目2205取借方/贷方发生额+按对方科目分拆）
    - _Requirements: 25.3, 25.4, 23.1, 23.2_

  - [x] 26.2 创建 `backend/app/routers/wp_render_strategies/_d7_ai_generate.py`
    - POST /api/workpapers/{wp_id}/d7/ai-generate 端点
    - 支持9个section（adj-explanation/adj-conclusion/adj-aging-explanation/detail-change/detail-contract/detail-over1year/analysis-explanation/analysis-conclusion/longterm-reason）
    - 自动加载D7-1变动数据 + D7-4分析结果 + D7-5长期挂账 + project_context作为LLM context
    - 注册到router_registry "AI与辅助"组
    - _Requirements: 4.2, 4.3, 7.2, 9.8, 9.9, 10.5, 10.6_

- [x] 27. 实现后端render策略函数和account_package_registry
  - [x] 27.1 在RENDERER_DISPATCH注册'd7-contract-liabilities'→`_render_d7_contract_liabilities`策略函数
    - 实现`_render_d7_contract_liabilities`返回审定表双区块结构+明细表行数据+各sheet配置
    - 更新account_package_registry.json添加D7_contract_liabilities工作包（含9个有效sheet：D7A/D7-1/D7-2/D7-3/D7-4/D7-5/D7-6/D7-7/附注）
    - 读取D7.yaml render schema生成初始结构化数据
    - _Requirements: 25.1, 25.2, 25.5_

- [x] 28. 集成主入口与双模式切换
  - [x] 28.1 完善 GtD7ContractLiabilities.vue 主入口
    - el-tabs 8个tab-pane引用9个子组件（附注内含el-segmented切换上市/国企）
    - Tab顺序对齐源模板sheet顺序：D7A→D7-1→D7-2→D7-3→D7-4→D7-5→D7-6→D7-7→附注
    - 传递allResponses/wpId/projectId/isReadonly/crossSheet等props
    - provide openReviewDialog（inject模式零成本集成复核）
    - _Requirements: 1.1, 1.2, 21.5_

  - [x] 28.2 在所有子组件中实现HTML ↔ OnlyOffice双模式切换
    - 每个Tab页头部el-segmented（"结构化视图"|"在线编辑"）
    - 切OO：获取onlyoffice-config → GtOnlyOfficeSheet → 隐藏非当前sheet(SetVisible(false))
    - 切回HTML：重新加载checklist_responses刷新
    - OO不可用时禁用+tooltip
    - _Requirements: 20.1-20.8_

- [x] 29. Checkpoint - 后端与双模式验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 30. 回归测试与全量验证
  - [x] 30.1 运行全量测试确保无回归
    - vitest run 所有D7相关spec文件
    - python -m pytest backend/tests/ -k d7
    - 验证htmlRendererRegistry注册数量更新
    - 验证VALID_COMPONENT_TYPES含'd7-contract-liabilities'
    - 验证wp_code_overrides D7/D7-1/D7-2/D7-3/D7-4/D7-5/D7-6/D7-7映射正确
    - 验证RENDERER_DISPATCH含'd7-contract-liabilities'策略
    - 验证auto_data_resolvers._REGISTRY含d7_tb_unadjusted + d7_ledger_analysis
    - 验证account_package_registry含D7工作包9个sheet
    - _Requirements: all_

- [x] 31. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional PBT tests
- 每个Property对应design.md中的一个correctness property
- 所有PBT使用fast-check（前端）或hypothesis（后端），numRuns: 100
- 贷方科目核心公式：期末余额 = 期初审定 + 贷方发生 - 借方发生（贷增借减）
- 审定表双区块特色：一、按性质分类（含"减：非流动负债"扣减行）+ 二、按账龄分类
- 合同负债合计 = 小计 - 计入其他非流动负债的合同负债
- 交叉验证：性质分类合计 必须等于 账龄分类合计
- 跨sheet全部通过allResponses computed链，不走API调用
- selfLoad必须支持（bundle内嵌场景htmlData为null）
- 程序表D7A复用a-program-console componentType，不需单独实现公式
- D7特色：CAS14合同负债vs预收账款区分联动（D3↔D7）
- D7来源交叉：D7-7期后结转→D7-2期后结转列（按客户名匹配累加）
- D7-2明细表27列（贷方科目公式链4步）：期初审定→期末余额→期末未审→期末审定
- 分析表4区块：借方分析+贷方分析+Top10债务人+审计说明
- AI生成端点复用B14/A17-1模式：project_context + 底稿数据snapshot + CPA system prompt
- 附注上市3子节（分类+超1年+重大变动）比国企2子节（分类+重大变动）多1个子节
- 5方EventBus联动：substantive:adjudicated + adjustment:created + analytical:significant-change + confirmation:completed + risk:updated
