# Implementation Plan: F1 预付账款底稿专属HTML精美组件

## Overview

实现F1预付账款底稿专属组件`f1-prepayment`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtF1Prepayment.vue + 10个子组件 + 10个composable + 后端4个py文件。科目1123借方/资产类，核心公式：期末=期初+借方-贷方；审定数=未审+AJE+RJE；变动额=期末审定-期初审定。标准审定表（93公式）+ 11列明细表（69公式）+ 实质性分析 + 长期挂款检查 + 关联方检查 + 综合检查 + 附注披露 + 函证程序。F循环中等复杂度底稿。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2"] },
    { "id": "wave5", "tasks": ["6.1", "6.2"] },
    { "id": "wave6", "tasks": ["7.1", "7.2", "7.3"] },
    { "id": "wave7", "tasks": ["8.1", "8.2"] },
    { "id": "wave8", "tasks": ["10.1", "11.1", "12.1", "13.1"] },
    { "id": "wave9", "tasks": ["15.1"] },
    { "id": "wave10", "tasks": ["16.1", "16.2", "16.3", "16.4", "16.5", "16.6", "16.7", "16.8", "16.9", "16.10"] },
    { "id": "wave11", "tasks": ["17.1", "18.1", "19.1", "20.1"] },
    { "id": "wave12", "tasks": ["22.1"] },
    { "id": "wave13", "tasks": ["23.1"] },
    { "id": "wave14", "tasks": ["24.1", "24.2"] },
    { "id": "wave15", "tasks": ["25.1"] },
    { "id": "wave16", "tasks": ["26.1", "27.1", "28.1", "28.2", "29.1"] }
  ]
}
```

## Notes

- F1是借方科目（资产类），公式方向：期末=期初+借方-贷方
- F1-1审定表有两级结构（按性质+按账龄），两个小计必须交叉校验相等
- F1-2明细表(32列)拆为3区段Tab（基础+期初/本期发生+期末/账龄+结果）
- F1-7检查表(93行×19列)采用借方/贷方独立区块设计
- F1与F0存货循环函证联动（函证结果回填到明细表）
- 抽凭引擎集成在F1-7（检查表），OCR集成在F1-7（📎列）
- 截止自动提取(useCutoffAutoSampling)不适用于F1
- F1A程序表直接复用a-program-console组件

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将F1/F1-1/F1-2/F1-3/F1-4/F1-5/F1-6/F1-7映射为'f1-prepayment'
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'f1-prepayment'
    - 在 `htmlRendererRegistry.ts` 中注册 'f1-prepayment' → GtF1Prepayment 映射
    - 创建 `GtF1Prepayment.vue` 主入口骨架（el-tabs 10个tab-pane + selfLoad逻辑）
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 1.8_

  - [x]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'f1-prepayment'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证F1/F1-1~F1-7共8个映射
    - _Requirements: 1.5, 1.6, 1.7_

- [x] 2. 实现共享公式引擎 useF1FormulaEngine.ts
  - [x] 2.1 创建 `composables/useF1FormulaEngine.ts`，实现全部纯函数
    - 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN/Infinity → 0）
    - 实现 `calcEndUnadjustedDebit`（借方科目期末未审 = 期初审定 + 借方发生 - 贷方发生）
    - 实现 `calcAuditedAmount`（审定数 = 未审 + AJE + RJE）
    - 实现 `calcChangeAmount`（变动额 = 期末审定 - 期初审定）
    - 实现 `calcChangeRate`（变动率：期初=0且期末=0→''/期初=0→'N/A'/其他→(期末-期初)/期初）
    - 实现 `isChangeRateExceeding`（变动率绝对值超阈值判定）
    - 实现 `calcSubtotal`（合计 = SUM数组）
    - 实现 `calcBookValue`（账面价值 = 期末余额 - 坏账准备）
    - 实现 `calcTurnoverRate`（周转率 = 营业成本/平均预付账款余额）
    - 实现 `calcTurnoverDays`（周转天数 = 365/周转率）
    - 实现 `calcPercentage`（比例% = 该类别金额/合计金额×100）
    - _Requirements: 1.4, 2.3, 2.4, 2.5, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8_

  - [x]* 2.2 编写 Property 1 PBT：借方科目期末余额公式
    - 生成器：`fc.float({min:0, max:1e9})` × priorAudited/debit/credit
    - 断言：calcEndUnadjustedDebit(priorAudited, debit, credit) === priorAudited + debit - credit
    - **Property 1: 借方科目期末余额公式**
    - **Validates: Requirements 1.4, 13.3**

  - [x]* 2.3 编写 Property 2 PBT：审定数 = 未审 + AJE + RJE
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 3
    - 断言：calcAuditedAmount(u, a, r) === u + a + r
    - **Property 2: 审定数 = 未审 + AJE + RJE**
    - **Validates: Requirements 1.4, 2.3**

  - [x]* 2.4 编写 Property 3 PBT：变动额与变动率公式
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 2（含0边界策略）
    - 断言：变动额 === 期末-期初；变动率期初=0时特殊处理
    - **Property 3: 变动额与变动率公式**
    - **Validates: Requirements 2.4, 2.5, 13.4, 13.5**

  - [x]* 2.5 编写 Property 4 PBT：合计行 = SUM(明细行)
    - 生成器：`fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:50})`
    - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
    - **Property 4: 合计行 = SUM(明细行)**
    - **Validates: Requirements 2.4, 13.6**

  - [x]* 2.6 编写 Property 5 PBT：变动率阈值高亮判定
    - 生成器：`fc.float({min:-10, max:10})`
    - 断言：isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)；空串/'N/A'→false
    - **Property 5: 变动率阈值高亮判定**
    - **Validates: Requirements 2.7, 13.7**

- [x] 3. 实现 useF1FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useF1FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate（PUT单条response）
    - 实现 debouncedSave（2秒debounce版本）
    - 实现 saveBatch（批量保存）
    - 实现 writebackTrialBalance（回写科目1123）
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=f1-prepayment）
    - _Requirements: 1.8, 10.10, 15.1, 15.4_

- [x] 4. 实现 useF1CrossSheet.ts 跨Sheet联动
  - [x] 4.1 创建 `composables/useF1CrossSheet.ts`
    - 实现 originalValueAggregation computed（F1-2按预付类型聚合openingAudited/closingAudited到审定表）
    - 实现 adjustmentAggregation computed（F1-3 AJE/RJE合计到审定表）
    - 实现 adjudicationWithAggregation computed（审定表+聚合数据+公式计算）
    - 实现 confirmationResults computed（F0→F1-2函证结果）
    - 实现 longTermFlags computed（F1-5→F1-2长期挂款标记）
    - 实现 relatedPartyFlags computed（F1-6→F1-2关联方标记）
    - 实现 analysisForAdjudication computed（F1-4→F1-1原因分析）
    - 实现 adjudicationForDisclosure computed（F1-1审定数→附注引用）
    - 实现 detailForDisclosure computed（F1-2账龄分布→附注引用）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.6, 5.7, 11.8, 11.9_

  - [x]* 4.2 编写 Property 6 PBT：按预付类型聚合正确性
    - 生成器：自定义 DetailRow[] 生成器（nature随机从'goods'/'service'/'rent'/'other'取）
    - 断言：各类别sum === 手动filter+reduce结果
    - **Property 6: 按预付类型聚合正确性**
    - **Validates: Requirements 3.1, 3.2, 4.1, 4.2_

- [x] 5. Checkpoint - 公式引擎与基础设施验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 实现 useF1Adjudication.ts 审定表F1-1（两级结构：按性质+按账龄）
  - [x] 6.1 创建 `composables/useF1Adjudication.ts`
    - 定义 `AdjudicationRow` 类型（rowKey/label/期初未审/期初账项调整/期初重分类调整/期初审定/期末未审/期末账项调整/期末重分类调整/期末审定/变动额/变动率/原因分析/isDynamic/isTotal/section）
    - 定义两级固定行配置：
      - section='nature'：货款/工程款/设备款/服务费/其他 + 合计行（动态行可增删）
      - section='aging'：1年以内含1年/1至2年含2年/2至3年含3年/3年以上 + 合计行（固定4行不可增删）
      - 底部：试算平衡表数行 + 差异数行
    - 实现 `natureRows` computed + `agingRows` computed（分级渲染）
    - 实现 `natureTotalRow` computed + `agingTotalRow` computed（各级合计）
    - 实现 公式：审定数=未审+账项调整+重分类调整；变动额=期末审定-期初审定；变动率=(期末-期初)/期初
    - 实现 trialBalanceAmount（从TB auto_data取数科目1123）+ trialBalanceDiff(=合计审定数-TB数)
    - 实现 crossValidation computed（按性质合计 vs 按账龄合计 金额一致性校验，不一致红色警告）
    - 实现 changeAmount/changeRate/isExceeding 变动额与变动率（>30%红色高亮）
    - 实现 auditNote + auditConclusion 双向绑定（审计说明+审计结论textarea，支持AI生成）
    - 实现 updateCell（编辑 → 公式重算 → debouncedSave）
    - 实现 addDynamicRow/removeDynamicRow（仅"按性质"部分允许增删）
    - 实现 publishAdjudicated（EventBus: substantive:adjudicated，payload含wpCode='F1'/accountCode='1123'/auditedAmount/priorAmount/changeRate）
    - 实现 EventBus 监听 `adjustment:created`（AJE/RJE → 累加对应列）
    - 实现 `writebackTrialBalance`（回写 trial_balance.audited_amount 科目1123）
    - 实现序列化/反序列化（JSON.stringify rows → F1-adjudication-rows remark字段）
    - _Requirements: 2.1~2.12, 3.1~3.10_

  - [x]* 6.2 编写 Property 7 PBT：审定表公式链正确性
    - 生成器：自定义 AdjudicationRow[] 生成器（含两级结构完整字段）
    - 断言：审定数===未审+账项调整+重分类调整；变动额===期末审定-期初审定；按性质合计===各性质行之和；按账龄合计===各账龄行之和
    - **Property 7: 审定表公式链正确性**
    - **Validates: Requirements 2.3, 2.4, 2.10**

- [x] 7. 实现 useF1Detail.ts 明细表F1-2（32列宽表→3区段）
  - [x] 7.1 创建 `composables/useF1Detail.ts`，实现明细表F1-2核心逻辑
    - 定义 `DetailRow` 类型（32列完整字段按xlsx：债权人名称/公司代码/关联方类型/款项性质/期初未审余额/期初账项调整/期初重分类调整/期初审定余额/期初审定账龄4段/借方发生/贷方发生/期末余额/被审计单位重分类/期末未审余额/期末未审账龄4段/账项调整/重分类调整/审定数/期末审定账龄4段/是否函证/期后到货/备注）
    - 实现 `rows` reactive（从 F1-detail-rows remark JSON加载）
    - 实现 `totalRow` computed（SUM全部行各金额列，不可编辑）
    - 实现 `filterBySupplierName` + `filteredRows` computed（按债权人名称搜索筛选）
    - 实现 `filterByNature` + `filteredRows` computed（按款项性质筛选）
    - 实现 `filterByAging` computed（仅显示3年以上有值的行）
    - 实现行公式链：期初审定余额 = 期初未审 + 期初账项调整 + 期初重分类调整
    - 实现行公式链：期末余额 = 期初审定余额 + 借方发生 - 贷方发生
    - 实现行公式链：审定数 = 期末未审余额 + 账项调整 + 重分类调整
    - 实现 `updateCell`（编辑 → 公式重算 → debounce保存）
    - 实现 `addRow()`（在合计行上方新增空行，所有金额=0）
    - 实现 `removeRow(rowId)`
    - 实现序列化/反序列化（JSON.stringify rows → F1-detail-rows remark字段）
    - 实现长期挂款标记（"3年以上"账龄列有值时isLongTerm=true）
    - 实现关联方标记（关联方类型非空时isRelatedParty=true）
    - 实现函证结果同步（来自F0数据）
    - 实现区段配置导出（segmentA列定义/segmentB列定义/segmentC列定义，供Vue组件el-tabs渲染）
    - _Requirements: 4.1~4.16, 5.1~5.10_

  - [x]* 7.2 编写 Property 8 PBT：明细表余额计算公式链正确性
    - 生成器：自定义 DetailRow[] 生成器（完整32列字段）
    - 断言：期末余额 === 期初审定余额 + 借方发生 - 贷方发生；审定数 === 期末未审 + 账项调整 + 重分类调整
    - **Property 8: 明细表余额计算公式链正确性**
    - **Validates: Requirements 4.5, 4.6, 4.7, 13.3**

  - [x]* 7.3 编写 Property 9 PBT：明细表合计行恒等于明细行之和
    - 生成器：`fc.array(DetailRow生成器, {minLength:0, maxLength:10})`
    - 断言：合计行各列 === SUM明细行对应列
    - **Property 9: 明细表合计行恒等于明细行之和**
    - **Validates: Requirements 4.8, 13.6**

- [x] 8. 实现 useF1Adjustment.ts 调整分录F1-3
  - [x] 8.1 创建 `composables/useF1Adjustment.ts`，实现调整分录F1-3核心逻辑
    - 定义 `AdjustmentRow` 类型（调整事项说明/科目名称/借方金额/贷方金额/索引/备注）
    - 实现 `rows` reactive（从 F1-adjustment-rows remark JSON加载）
    - 实现 `totalRow` computed（SUM借方/贷方合计，不可编辑）
    - 实现 `balanceCheck` computed（借方合计===贷方合计，否则红色警告）
    - 实现 `filterByAccountName` + `filteredRows` computed（按科目名称筛选）
    - 实现 `updateCell`（编辑 → 公式重算 → debounce保存）
    - 实现 `addRow()`（在合计行上方新增空行）
    - 实现 `removeRow(rowId)`
    - 实现序列化/反序列化（JSON.stringify rows → F1-adjustment-rows remark字段）
    - 实现 EventBus 发布 `adjustment:created`（新增/修改调整分录时）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

  - [x]* 8.2 编写 Property 10 PBT：调整分录借贷平衡检查
    - 生成器：`fc.array(AdjustmentRow生成器, {minLength:1, maxLength:10})`
    - 断言：借方合计===贷方合计
    - **Property 10: 调整分录借贷平衡检查**
    - **Validates: Requirements 6.5_

- [x] 9. Checkpoint - 核心审定表与明细表验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. 实现 useF1SubstantiveAnalysis.ts 实质性分析F1-4
  - [x] 10.1 创建 `composables/useF1SubstantiveAnalysis.ts`，实现实质性分析F1-4核心逻辑
    - 定义三个区块数据结构：余额变动分析、周转率分析、账龄分布分析
    - 实现 `balanceChangeAnalysis` computed（从F1-1获取余额变动数据）
    - 实现 `turnoverRateAnalysis` computed（计算周转率=营业成本/平均预付账款余额）
    - 实现 `turnoverDaysAnalysis` computed（计算周转天数=365/周转率）
    - 实现 `agingDistributionAnalysis` computed（从F1-2获取账龄分布数据）
    - 实现 `anomalyDetection` computed（识别异常：周转率下降/账龄集中/余额异常增长）
    - 实现 `conclusion` reactive（分析结论textarea，支持AI生成）
    - 实现 `generateConclusion`（AI生成分析结论）
    - 实现序列化/反序列化（JSON.stringify analysis → F1-analysis remark字段）
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

- [x] 11. 实现 useF1LongTermCheck.ts 长期挂款检查F1-5
  - [x] 11.1 创建 `composables/useF1LongTermCheck.ts`，实现长期挂款检查F1-5核心逻辑
    - 定义 `LongTermCheckRow` 类型（供应商名称/预付金额/账龄/款项性质/预付日期/长期挂款原因/可收回性评估/减值准备/处理措施/备注）
    - 实现 `rows` computed（从F1-2筛选账龄='over_3_years'的行）
    - 实现 `totalRow` computed（SUM预付金额/SUM减值准备）
    - 实现 `autoAssessRecoverability` computed（基于规则自动评估可收回性）
    - 实现 `autoSuggestImpairment` computed（可收回性='无法收回'时建议全额减值）
    - 实现 `updateCell`（编辑 → debounce保存）
    - 实现序列化/反序列化（JSON.stringify rows → F1-long-term-check remark字段）
    - 实现与审定表F1-1的数据联动（减值准备→坏账准备考虑）
    - 实现与明细表F1-2的数据联动（点击行跳转到对应明细行）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10_

- [x] 12. 实现 useF1RelatedParty.ts 关联方检查F1-6
  - [x] 12.1 创建 `composables/useF1RelatedParty.ts`，实现关联方检查F1-6核心逻辑
    - 定义 `RelatedPartyRow` 类型（供应商名称/关联关系/预付金额/账龄/款项性质/关联交易类型/交易定价公允性/披露状态/坏账准备/账面价值/备注）
    - 实现 `rows` computed（从F1-2筛选关联方供应商，通过关联方名录匹配）
    - 实现 `totalRow` computed（SUM预付金额/SUM账面价值）
    - 实现 `autoIdentifyRelation` computed（基于供应商名称自动识别关联关系）
    - 实现 `calcBookValue` computed（账面价值 = 预付金额 - 坏账准备）
    - 实现 `disclosureRiskCheck` computed（披露状态='未披露'时标记风险）
    - 实现 `updateCell`（编辑 → debounce保存）
    - 实现序列化/反序列化（JSON.stringify rows → F1-related-party-check remark字段）
    - 实现与关联方名录的数据联动（自动匹配关联关系）
    - 实现披露完整性评估（披露比例/风险等级）
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

- [x] 13. 实现 useF1ComprehensiveCheck.ts 综合检查F1-7（借方+贷方两区块）
  - [x] 13.1 创建 `composables/useF1ComprehensiveCheck.ts`，实现综合检查F1-7核心逻辑
    - 定义抽样参数区数据结构（测试总体笔数金额/特定样本描述/抽样总体笔数金额/确定样本量/抽样方法/抽样过程）
    - 定义借方检查区数据结构（16列：供应商名称/日期/凭证编号/业务内容/对方科目/对方明细科目/借方金额 + 付款审批单日期编号/是否恰当审批 + 银行回单日期/收款方/金额 + 合同供应商/合同金额/预付比例 + 索引号/是否异常）
    - 定义贷方检查区数据结构（14列：供应商名称/日期/凭证编号/业务内容/对方科目/对方明细科目/贷方金额 + 入库单日期编号/品名/单位/数量 + 采购发票日期编号/对手方/金额 + 索引号/是否异常）
    - 定义检查比例汇总结构（方向/账面金额/检查金额/检查比例/说明）
    - 实现 `samplingParams` reactive（抽样参数6字段）
    - 实现 `debitCheckRows` reactive（借方检查行）+ `creditCheckRows` reactive（贷方检查行）
    - 实现 `debitTotalRow` computed + `creditTotalRow` computed（各区块合计行）
    - 实现 `coverageStats` computed（检查比例 = 检查金额/账面金额）
    - 实现 `isCoverageLow` computed（<50%时预警）
    - 实现 `updateCell`（编辑 → debounce保存）
    - 实现 `addDebitRow()`/`removeDebitRow(id)`/`addCreditRow()`/`removeCreditRow(id)`（借方贷方独立增删行）
    - 实现序列化/反序列化（JSON.stringify → F1-comprehensive-check remark字段）
    - 实现行级OCR上传（复用OCR端点，识别凭证信息自动填入行）
    - 实现段列配置导出（debitColumnGroups/creditColumnGroups，供Vue组件固定列+滚动列分组渲染）
    - _Requirements: 10.1~10.12_

- [x] 14. Checkpoint - 分析与检查表验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. 实现 useF1Disclosure.ts 附注披露F1
  - [x] 15.1 创建 `composables/useF1Disclosure.ts`，实现附注披露核心逻辑
    - 定义上市公司版账龄表数据结构（账龄/期末数/占比/上年年末数/占比）
    - 定义国企版账龄表数据结构（账龄/期末数/上年年末数）
    - 实现 `listedVersion` computed（上市公司版，从F1-1+F1-2获取数据）
    - 实现 `soeVersion` computed（国企版，简化版）
    - 实现 `agingBreakdown` computed（从F1-2按账龄分组统计）
    - 实现 `calcPercentage` computed（计算占比）
    - 实现 `impairmentInfo` computed（坏账准备情况，如适用）
    - 实现 `switchVersion`（上市公司版/国企版切换）
    - 实现 `updateCell`（编辑 → debounce保存）
    - 实现序列化/反序列化（JSON.stringify → F1-disclosure remark字段）
    - 实现导出审计报告附注格式
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10_

- [x] 16. 实现 Vue子组件（10个）
  - [x] 16.1 创建 `components/workpaper/f1/F1TabProcedure.vue`（程序表F1A）
    - 复用 GtAProgramConsole 组件
    - 传递 F1 程序配置
    - 实现 selfLoad 逻辑
    - _Requirements: 1.2, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 16.2 创建 `components/workpaper/f1/F1TabAdjudication.vue`（审定表F1-1，两级结构）
    - 调用 useF1Adjudication.ts
    - 渲染两级结构：el-card"一、按照性质分类"（动态行el-table+增删行按钮）+ el-card"二、按照账龄分类"（固定4行el-table）
    - 每级el-table列：项目 | 期初(未审/账项调整/重分类调整/审定) | 期末(未审/账项调整/重分类调整/审定) | 变动额 | 变动率 | 原因分析
    - 底部：试算平衡表数行 + 差异行（≠0红色）
    - 实现crossValidation显示（按性质合计 vs 按账龄合计 不一致时红色警告条）
    - 实现变动率高亮（>30%红色）
    - 实现"三、审计说明"textarea + "四、审计结论"textarea（均AI按钮右对齐）
    - 实现GtIndexChip（索引跳转）
    - 实现只读模式控制
    - UI铁律：13px字体/公式列虚线下划线+tooltip/min-width自适应/审计说明el-card包裹
    - _Requirements: 2.1~2.12_

  - [x] 16.3 创建 `components/workpaper/f1/F1TabDetail.vue`（明细表F1-2，32列→3区段）
    - 调用 useF1Detail.ts
    - 渲染 el-tabs 3区段切换（"基础+期初"/"本期发生+期末"/"账龄+结果"）
    - 每区段内使用 el-table（固定列+横滚列分组）
    - 区段间行位置同步（切换区段保持当前行选中状态）
    - 实现筛选器（债权人名称搜索/款项性质下拉/仅3年以上切换）
    - 实现下拉选择（关联方类型/款项性质/是否函证）
    - 实现长期挂款高亮（橙色，3年以上有值）
    - 实现函证差异高亮（红色，回函不符）
    - 实现虚拟滚动（行数>100）
    - 实现导入导出（完整32列Excel模板）
    - _Requirements: 4.1~4.16_

  - [x] 16.4 创建 `components/workpaper/f1/F1TabAdjustment.vue`（调整分录F1-3）
    - 调用 useF1Adjustment.ts
    - 渲染 el-table（6列）
    - 实现下拉选择（科目名称）
    - 实现GtIndexChip（索引跳转）
    - 实现借贷不平衡警告（红色）
    - 实现筛选器（科目/分录编号）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

  - [x] 16.5 创建 `components/workpaper/f1/F1TabSubstantiveAnalysis.vue`（实质性分析F1-4）
    - 调用 useF1SubstantiveAnalysis.ts
    - 渲染三个区块（余额变动/周转率/账龄分布）
    - 实现图表可视化（余额变动趋势图、账龄分布饼图）
    - 实现年份切换功能
    - 实现AI生成结论按钮
    - 实现异常波动说明textarea
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

  - [x] 16.6 创建 `components/workpaper/f1/F1TabLongTermCheck.vue`（长期挂款F1-5）
    - 调用 useF1LongTermCheck.ts
    - 渲染 el-table（10列）
    - 实现下拉选择（可收回性评估/处理措施）
    - 实现自动减值建议（可收回性='无法收回'时）
    - 实现跳转到明细表功能
    - 实现风险汇总报告
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10_

  - [x] 16.7 创建 `components/workpaper/f1/F1TabRelatedParty.vue`（关联方检查F1-6）
    - 调用 useF1RelatedParty.ts
    - 渲染 el-table（11列）
    - 实现下拉选择（关联关系/关联交易类型/交易定价公允性/披露状态）
    - 实现披露风险高亮（黄色）
    - 实现关联方名录联动
    - 实现披露完整性评估
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

  - [x] 16.8 创建 `components/workpaper/f1/F1TabComprehensiveCheck.vue`（综合检查F1-7，借方+贷方两区块）
    - 调用 useF1ComprehensiveCheck.ts
    - 渲染抽样参数区（6字段表单卡片）
    - 渲染借方检查区（el-table 16列，固定凭证7列+滚动证据9列）
    - 渲染贷方检查区（el-table 14列，固定凭证7列+滚动证据7列）
    - 渲染检查比例汇总（3行×5列小表格，低比例橙色高亮）
    - 实现下拉选择（是否恰当审批/是否异常）
    - 实现借方/贷方独立增删行
    - 实现行级OCR上传（📎列）
    - 底部审计说明+审计结论textarea（AI辅助）
    - 实现导入导出（借方+贷方两sheet）
    - _Requirements: 10.1~10.12_

  - [x] 16.9 创建 `components/workpaper/f1/F1TabDisclosure.vue`（附注披露）
    - 调用 useF1Disclosure.ts
    - 实现 el-tabs 切换（上市公司版/国企版）
    - 渲染账龄分析表（el-table）
    - 实现占比自动计算
    - 实现坏账准备情况展示
    - 实现导出审计报告附注格式
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10_

  - [x] 16.10 创建 `components/workpaper/f1/F1TabConfirmationProcedure.vue`（函证程序G1A）
    - 复用 F0 函证程序表结构
    - 与 F0 函证结果汇总表联动
    - 与预付账款明细表联动（函证结果回填）
    - 实现程序完成度汇总
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [x] 17. 实现后端导入导出端点
  - [x] 17.1 创建 `backend/app/routers/wp_render_strategies/_f1_import_export.py`
    - 实现 `export_f1_template` 端点（POST /api/workpapers/{wp_id}/f1/export-template?sheet=F1-2）
    - 实现 `import_f1_data` 端点（POST /api/workpapers/{wp_id}/f1/import-data?sheet=F1-2，multipart/form-data）
    - 实现 `export_f1_data` 端点（POST /api/workpapers/{wp_id}/f1/export-data?sheet=F1-2）
    - 支持sheet参数：F1-2(明细表32列)/F1-5(长期挂款)/F1-6(关联方)/F1-7-debit(借方检查)/F1-7-credit(贷方检查)
    - 实现 xlsx生成与解析（使用openpyxl）
    - 实现数据校验与错误处理（列头匹配校验+类型校验）
    - 导出模板含填写说明sheet
    - StreamingResponse中文文件名RFC5987编码
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

- [x] 18. 实现后端AI生成端点
  - [x] 18.1 创建 `backend/app/routers/wp_render_strategies/_f1_ai_generate.py`
    - 实现 `generate_explanation` 端点（POST /api/workpapers/F1/ai/explanation）
    - 实现 `generate_long_term_analysis` 端点（POST /api/workpapers/F1/ai/long-term-analysis）
    - 实现 `generate_analysis_conclusion` 端点（POST /api/workpapers/F1/ai/analysis-conclusion）
    - 实现 `identify_related_party` 端点（POST /api/workpapers/F1/ai/identify-related-party）
    - 集成AI服务（基于上下文生成文本）
    - 实现超时控制（30秒）
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8_

- [x] 19. 实现后端Render策略函数
  - [x] 19.1 创建 `backend/app/routers/wp_render_strategies/_f1_prepayment.py`
    - 实现 `render_f1_prepayment` 函数（Render策略）
    - 返回 componentType='f1-prepayment'
    - 支持 force_component_type 参数
    - 支持自定义渲染配置
    - _Requirements: 1.5, 1.8_

- [x] 20. 实现后端Auto Data Resolver
  - [x] 20.1 创建 `backend/app/services/auto_data_resolvers/_f1_prepaid.py`
    - 实现 `resolve_f1_auto_data` 函数（Auto Data Resolver）
    - 从试算平衡表自动获取科目1123数据
    - 从序时账自动获取预付账款明细数据
    - 从关联方名录自动获取关联方信息
    - 返回 auto_data JSON
    - _Requirements: 2.8, 9.3, 14.1_

- [x] 21. Checkpoint - 后端验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 22. 实现双模式切换
  - [x] 22.1 实现前端双模式切换逻辑
    - 在每个子组件右上角显示"切换到OnlyOffice"按钮
    - 实现模式切换状态管理（reactive mode: 'html' | 'onlyoffice'）
    - 实现OnlyOffice sheet隐藏逻辑（只显示当前sheet）
    - 实现模式切换时数据同步（HTML→OO / OO→HTML）
    - 实现localStorage持久化（记住用户选择）
    - 实现OnlyOffice加载失败降级（自动回HTML模式）
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7_

- [x] 23. 集成测试
  - [x] 23.1 编写集成测试
    - 测试完整用户流程（新建底稿→填写明细表→生成审定表→生成附注）
    - 测试跨sheet联动（明细表变更→审定表自动更新）
    - 测试调整分录联动（新增调整→审定表AJE/RJE自动更新）
    - 测试函证联动（F0函证结果→明细表函证结果自动更新）
    - 测试导入导出（导出模板→离线填写→导入解析）
    - 测试双模式切换（HTML↔OO数据同步）
    - 测试AI生成（AI生成原因说明/分析结论）
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8_

- [x] 24. 性能优化
  - [x] 24.1 实现性能优化
    - 明细表启用虚拟滚动（行数>100）
    - 跨sheet计算启用debounce（2秒）
    - 公式计算启用缓存
    - 图表渲染启用懒加载
    - 导入导出启用进度条
    - AI生成启用超时控制
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7_

- [x] 25. 最终验收
  - [x] 25.1 最终验收检查
    - 所有单元测试通过
    - 所有集成测试通过
    - 性能测试通过（大数据量响应<2秒）
    - 代码审查通过
    - 文档更新完成
    - 部署到测试环境
    - 用户验收测试


- [x] 26. 抽凭引擎集成
  - [x] 26.1 F1-7综合检查表集成GtVoucherSamplingEngine
    - 在F1TabComprehensiveCheck.vue抽样参数区添加"使用抽凭引擎"按钮
    - import GtVoucherSamplingEngine组件（dialog模式）
    - 点击按钮打开dialog，预填总体金额和科目代码1123
    - 用户确认后将选中样本映射到借方/贷方检查区动态行：供应商名称→供应商名称列/日期→日期列/凭证编号→凭证编号列/金额→借方金额或贷方金额列
    - 自动更新抽样参数区字段（样本量/抽样方法/置信水平）
    - 已填入行添加tooltip来源标记"来自抽凭引擎 {algorithm}"
    - _Requirements: 22_

- [x] 27. 版本链集成
  - [x] 27.1 集成useVersionTrail到GtF1Prepayment主入口
    - import useVersionTrail composable并调用useVersionTrail(wpId)
    - 在每次save成功后调用versionTrail.autoSnapshot()
    - 工具栏右侧添加"版本历史"按钮（el-button icon="Clock"）
    - 点击按钮打开GtWpVersionTrail drawer（direction="rtl" size="400px"）
    - GtWpVersionTrail显示版本列表+VersionDiffPanel差异对比
    - 支持手动创建命名快照（ElMessageBox.prompt输入备注）
    - _Requirements: 23_

- [x] 28. 附注模块EventBus联动
  - [x] 28.1 附注Tab订阅substantive:adjudicated事件
    - 在F1TabDisclosure.vue onMounted中subscribe EventBus `substantive:adjudicated`
    - 回调中检查payload.wpCode==='F1' && payload.accountCode==='1123'
    - 匹配则重新计算附注数据（从更新后的auditedAmount刷新账龄分布/坏账准备等）
    - 显示蓝色info bar "数据已更新"（3秒auto-dismiss）
    - onUnmounted中unsubscribe
    - _Requirements: 24_

  - [x] 28.2 审定表发布disclosure:note-text-updated事件
    - 在useF1Adjudication.ts中watch auditNote/auditConclusion变更
    - 变更时debounce 2秒后publish EventBus `disclosure:note-text-updated`（payload: {wpCode:'F1', section:'adjudication', text: auditConclusion}）
    - 事件供外部附注模块消费
    - _Requirements: 24_

- [x] 29. 复核对话provide/inject架构
  - [x] 29.1 GtF1Prepayment主入口provide openReviewDialog
    - import GtReviewDialog + useReviewDialog composable
    - 在setup中provide('openReviewDialog', openReviewDialog)
    - 每个子组件inject('openReviewDialog')
    - 每个section标题栏右侧添加"复核"按钮（仅当inject成功时显示）
    - section标题布局：flex justify-between；左侧h3标题；右侧el-button-group含AI+复核按钮
    - _Requirements: 20 补充_
