# Implementation Plan: F4 应付账款专属HTML精美组件

## Overview

实现F4应付账款专属组件`f4-accounts-payable`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtF4AccountsPayable.vue + 11个子组件 + 12个composable + 后端3个py文件。核心公式：贷方余额=期初+贷方-借方；审定=未审+AJE+RJE；变动率=(本期-上期)/上期×100。12个有效sheet，1个xlsx源模板(105KB)。科目2202应付账款。特色：F4-7反向截止测试(useCutoffAutoSampling) + F4-9供应商融资检查(保理/票据/供应链) + 两级审定(按性质+按账龄)。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2"] },
    { "id": "wave5", "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5"] },
    { "id": "wave6", "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"] },
    { "id": "wave7", "tasks": ["7.1"] },
    { "id": "wave8", "tasks": ["8.1", "8.2"] },
    { "id": "wave9", "tasks": ["9.1", "9.2", "9.3", "9.4"] },
    { "id": "wave10", "tasks": ["10.1"] }
  ]
}
```

## Notes

- F4是贷方科目（负债类），公式方向与F1（借方/资产类）相反：期末未审=期初审定+贷方-借方
- F4-1审定表有两级结构（按性质+按账龄），两个小计必须交叉校验相等
- F4-2明细表(27列)拆为3区段Tab（基础信息9列/账龄与核对10列/调整与审定8列）
- F4-7未入账检查是本循环特色：反向截止测试，集成useCutoffAutoSampling从序时账±5天自动提取
- F4-9供应商融资检查是另一特色：保理/票据融资/供应链融资3区域独立检查
- F4-8检查表(73行)采用借方/贷方独立区块设计
- 抽凭引擎集成在F4-8（检查表），截止自动提取集成在F4-7（未入账检查）
- OCR集成在F4-2明细表（识别发票金额/供应商）
- F4A程序表直接复用a-program-console组件

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将F4A/F4-1~F4-9/附注披露(上市)/附注披露(国企)映射为'f4-accounts-payable'（12个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'f4-accounts-payable'
    - 在 `htmlRendererRegistry.ts` 中注册 'f4-accounts-payable' → GtF4AccountsPayable 映射
    - 创建 `GtF4AccountsPayable.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy + selfLoad逻辑 + el-tabs 12 tabs + OnlyOffice fallback）
    - _Requirements: 1.1~1.8_

  - [x]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'f4-accounts-payable'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证12个映射条目
    - _Requirements: 1.3, 1.4, 1.5_

- [x] 2. 实现公式引擎 useF4FormulaEngine.ts
  - [x] 2.1 创建 `composables/useF4FormulaEngine.ts`，实现全部8个纯函数
    - 实现 `calcCreditBalance`（贷方余额 = 期初 + 贷方 - 借方）
    - 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
    - 实现 `calcAgingTotal`（账龄合计 = 各账龄段SUM）
    - 实现 `calcConcentration`（占比 = 金额/总额 × 100，总额=0→0）
    - 实现 `calcOutstandingDays`（挂账天数 = MAX(0, 当前日期 - 起始日) / 86400000取整）
    - 实现 `calcChangeRate`（变动率 = (本期-上期)/上期 × 100，上期=0→'N/A'）
    - 实现 `isDebitCreditBalanced`（借贷平衡 = |SUM(debits) - SUM(credits)| < 0.01）
    - 实现 `calcAgingCrossCheck`（账龄交叉校验 = |账龄合计 - 期末余额| < 0.01）
    - _Requirements: 13.1~13.8_

  - [x]* 2.2 编写 Property 1 PBT：贷方余额公式
    - 生成器：`fc.float({min:0, max:1e9})` × opening/credit/debit
    - 断言：calcCreditBalance(opening, credit, debit) === opening + credit - debit
    - **Property 1: 贷方余额=期初+贷方-借方**
    - **Validates: Requirements 13.1, 3.3, 5.2**

  - [x]* 2.3 编写 Property 2 PBT：审定数公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` × unadjusted/aje/rje
    - 断言：calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
    - **Property 2: 审定=未审+AJE+RJE**
    - **Validates: Requirements 13.2, 3.4**

  - [x]* 2.4 编写 Property 3 PBT：账龄交叉校验
    - 生成器：`fc.float({min:0, max:1e8})` × a1/a2/a3/a4，closingBalance = a1+a2+a3+a4
    - 断言：calcAgingCrossCheck(a1+a2+a3+a4, closingBalance) === true
    - **Property 3: 账龄合计===期末余额时校验通过**
    - **Validates: Requirements 13.8, 5.3, 5.5**

  - [x]* 2.5 编写 Property 4 PBT：集中度公式
    - 生成器：`fc.float({min:0, max:1e8})` amount + `fc.float({min:0.01, max:1e9})` total
    - 断言：calcConcentration(amount, total) === amount/total × 100
    - **Property 4: 集中度=amount/total×100**
    - **Validates: Requirements 13.4, 9.3**

  - [x]* 2.6 编写 Property 5 PBT：变动率公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` current + `fc.float({min:0.01, max:1e8})` prior（prior≠0）
    - 断言：calcChangeRate(current, prior) === (current-prior)/prior × 100
    - **Property 5: 变动率=(本期-上期)/上期×100**
    - **Validates: Requirements 13.6, 7.3**

  - [x]* 2.7 编写 Property 6 PBT：借贷平衡恒等
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:1, maxLength:20})` × debits/credits
    - 断言：isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
    - **Property 6: 借贷平衡=SUM借方===SUM贷方**
    - **Validates: Requirements 13.7, 6.2**

  - [x]* 2.8 编写 Property 7 PBT：挂账天数非负
    - 生成器：fc.date() × currentDate/startDate
    - 断言：calcOutstandingDays(currentDate, startDate) ≥ 0
    - **Property 7: 挂账天数恒≥0**
    - **Validates: Requirements 13.5, 8.2**

  - [x]* 2.9 编写 Property 8 PBT：两级审定交叉校验
    - 生成器：构造按性质行[]和按账龄行[]使得各自小计相等
    - 断言：SUM(natureRows.adjusted) === SUM(agingRows.adjusted)
    - **Property 8: 按性质小计===按账龄小计**
    - **Validates: Requirements 3.5, 3.8**

- [x] 3. 实现 useF4FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useF4FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate / debouncedSave / saveBatch
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=f4-accounts-payable）
    - _Requirements: 1.6_

- [x] 4. 实现审定表 + 附注披露 composable
  - [x] 4.1 创建 `composables/useF4Adjudication.ts`
    - 定义两级结构：byNature[] + byAging[] + total + trialBalance + variance
    - 实现按性质行：货款/工程款/服务费/其他/小计
    - 实现按账龄行：1年以内/1-2年/2-3年/3年以上/小计
    - 实现贷方公式链 + 审定公式 + 各级小计 + 交叉校验（按性质小计===按账龄小计）
    - 实现试算表自动取数（科目2202）+ 差异计算
    - 实现EventBus发布 `substantive:adjudicated`(accountCode='2202')
    - 实现序列化/反序列化
    - _Requirements: 3.1~3.10_

  - [x]* 4.2 编写审定表单元测试
    - 验证贷方余额公式方向正确
    - 验证两级交叉校验逻辑
    - 验证差异=审定-试算表数
    - _Requirements: 3.3~3.8_

- [x] 5. 实现各sheet composable
  - [x] 5.1 创建 `composables/useF4Detail.ts`（F4-2明细表3区段逻辑）
    - 定义 `APDetailRow` 类型（27列分3区段）
    - 实现3区段列配置导出
    - 实现公式链：期末=期初+贷方-借方 / 账龄合计=各段SUM / 审定=期末+AJE+RJE
    - 实现账龄交叉校验（合计≠期末红色标记）
    - 实现区段间行同步 + 动态行增删 + 合计行
    - _Requirements: 5.1~5.8_

  - [x] 5.2 创建 `composables/useF4SubstantiveAnalysis.ts`（F4-4实质性分析逻辑）
    - 定义行类型（8列）
    - 实现公式链：变动额=本期-上期 / 变动率 / 预期差异=本期-预期
    - 实现变动率>20%橙色标记
    - _Requirements: 7.1~7.6_

  - [x] 5.3 创建 `composables/useF4LongOutstanding.ts`（F4-5长期挂账逻辑）
    - 定义 `LongOutstandingRow` 类型（11列）
    - 实现挂账天数公式 + 高亮标记（>2年橙色，>3年红色）
    - 实现合计行（总额/2年以上/3年以上/建议转收入）+ 动态行增删
    - _Requirements: 8.1~8.6_

  - [x] 5.4 创建 `composables/useF4RelatedParty.ts`（F4-6关联方检查逻辑）
    - 定义 `RelatedPartyAPRow` 类型（15列）
    - 实现贷方余额公式 + 占比公式 + 集中度>30%橙色
    - 实现合计行 + 动态行增删
    - _Requirements: 9.1~9.6_

  - [x] 5.5 创建 `composables/useF4UnrecordedCheck.ts`（F4-7未入账检查逻辑）
    - 定义 `UnrecordedCheckRow` 通用类型（9列）
    - 实现3区域数据管理（期后采购/入库/收票各自rows[]）
    - 实现useCutoffAutoSampling集成（序时账±5天提取→按凭证类型分配到3区域）
    - 实现各区域独立动态行增删 + 底部小计
    - 实现"应入当期"="是"橙色高亮
    - 实现底部总结（未入账合计/建议调整金额）
    - _Requirements: 10.1~10.8_

- [x] 6. 实现 Vue子组件
  - [x] 6.1 创建 `f4-accounts-payable/F4TabAdjudication.vue`（F4-1审定表两级结构）
    - 调用useF4Adjudication
    - el-table渲染两级结构（按性质+按账龄+合计+TB数+差异）
    - 交叉校验失败红色高亮 + GtIndexChip索引列
    - EventBus发布
    - _Requirements: 3.1~3.10_

  - [x] 6.2 创建 `f4-accounts-payable/F4TabDetail.vue`（F4-2明细表 27列→3区段Tab）
    - 调用useF4Detail
    - 3区段Tab切换 + 区段间行同步 + 账龄交叉校验
    - 📎OCR列（识别发票金额/供应商→确认merge）
    - 动态行增删 + 底部合计 + 导入导出
    - _Requirements: 5.1~5.8, 14.4_

  - [x] 6.3 创建 `f4-accounts-payable/F4TabUnrecordedCheck.vue`（F4-7未入账检查 反向截止测试）
    - 调用useF4UnrecordedCheck
    - 顶部"截止自动提取"按钮（useCutoffAutoSampling）
    - 3区域独立el-table（期后采购/入库/收票）
    - "应入当期"="是"橙色高亮
    - 各区域独立增删 + 底部小计 + 底部总结textarea(AI)
    - 虚拟滚动(104行) + 导入导出
    - _Requirements: 10.1~10.8, 14.6_

  - [x] 6.4 创建 `f4-accounts-payable/F4TabVoucherCheck.vue`（F4-8检查表 借方/贷方区块）
    - 创建 `composables/useF4VoucherCheck.ts`
    - 借方区(付款减少) + 贷方区(采购增加) 独立el-table
    - GtVoucherSamplingEngine集成（dialog，科目2202，样本按借贷分配）
    - 贷方区特色：三单匹配（采购订单/入库单/发票）
    - 各区独立增删 + 底部小计 + 审计结论textarea(AI)
    - 导入导出 + 虚拟滚动(73行)
    - _Requirements: 11.1~11.9, 14.2_

  - [x] 6.5 创建 `f4-accounts-payable/F4TabSupplierFinancing.vue`（F4-9供应商融资）
    - 创建 `composables/useF4SupplierFinancing.ts`
    - 3区域独立el-table（保理/票据融资/供应链融资）
    - "应重分类"/"未终止确认"橙色高亮
    - 各区域独立增删 + 底部小计 + 底部总结textarea(AI)
    - 虚拟滚动(84行) + 导入导出
    - _Requirements: 12.1~12.6_

  - [x] 6.6 创建其余Vue子组件
    - F4TabAdjustment.vue（F4-3调整分录）：借贷平衡校验 + 动态行 + 导入导出
    - F4TabSubstantiveAnalysis.vue（F4-4实质性分析）：变动>20%橙色 + 审计结论(AI)
    - F4TabLongOutstanding.vue（F4-5长期挂账）：>2年橙/>3年红 + 汇总 + 导入导出
    - F4TabRelatedParty.vue（F4-6关联方）：>30%橙色 + 汇总 + 导入导出
    - F4TabDisclosureListed.vue / F4TabDisclosureSOE.vue（附注披露）
    - _Requirements: 4.1~4.5, 6.1~6.4, 7.1~7.6, 8.1~8.6, 9.1~9.6_

- [x] 7. Checkpoint - 公式引擎+组件验证
  - Ensure all PBT tests pass (P1~P8), ask the user if questions arise.

- [x] 8. 实现后端 + 导入导出 + AI
  - [x] 8.1 创建后端3个py文件
    - `_f4_accounts_payable.py`：render策略函数 + 注册RENDERER_DISPATCH['f4-accounts-payable']
    - `_f4_accounts_payable_import_export.py`：3端点 + 7张动态行表格支持
    - `_f4_accounts_payable_ai.py`：6个AI section端点 + 30秒超时
    - _Requirements: 1.3, 15.1~15.4_

  - [x] 8.2 创建 `composables/useF4ImportExport.ts` + `composables/useF4DualMode.ts`
    - useF4ImportExport：el-dropdown"导入导出▾" + axios三端点 + 7张表参数
    - useF4DualMode：模式状态(html/onlyoffice) + 切换逻辑 + localStorage持久化
    - _Requirements: 15.1~15.4_

- [x] 9. 跨模块联动集成
  - [x] 9.1 版本链集成
    - 主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 14.1, 14.5_

  - [x] 9.2 附注EventBus集成
    - 附注披露组件subscribe `substantive:adjudicated`(accountCode='2202')自动刷新
    - publish `disclosure:note-text-updated` 联动附注模块
    - _Requirements: 4.3~4.4, 14.3_

  - [x] 9.3 抽凭引擎 + 截止自动提取集成
    - F4-8: GtVoucherSamplingEngine dialog集成（科目2202，样本按借贷分配）
    - F4-7: useCutoffAutoSampling集成（序时账±5天，凭证按类型分配到3区域）
    - _Requirements: 10.2~10.3, 11.6~11.8, 14.2, 14.6_

  - [x] 9.4 OCR集成
    - F4-2: 📎OCR列（POST contract-ocr→发票金额/供应商识别→确认弹窗→merge）
    - _Requirements: 14.4_

- [x] 10. 集成测试与验收
  - [x] 10.1 编写集成测试
    - sheetName分发正确性（12个sheet→对应组件）
    - 贷方余额公式链
    - 两级审定交叉校验（按性质===按账龄）
    - F4-7截止自动提取→3区域分配（期后采购/入库/收票）
    - F4-8抽凭引擎样本借贷分配
    - F4-2三区段Tab行同步+账龄交叉校验
    - F4-9供应商融资3区域独立操作
    - EventBus(substantive:adjudicated)跨组件传递
    - 导入导出round-trip
    - _Requirements: 全部_
