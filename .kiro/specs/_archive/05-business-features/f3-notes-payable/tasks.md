# Implementation Plan: F3 应付票据专属HTML精美组件

## Overview

实现F3应付票据专属组件`f3-notes-payable`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtF3NotesPayable.vue + 9个子组件 + 10个composable + 后端3个py文件。核心公式：贷方余额=期初+贷方-借方；应付利息=面值×利率×天数/360；审定=未审+AJE+RJE。10个有效sheet，1个xlsx源模板(77KB)。科目2201应付票据。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2"] },
    { "id": "wave5", "tasks": ["5.1", "5.2", "5.3", "5.4"] },
    { "id": "wave6", "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5"] },
    { "id": "wave7", "tasks": ["7.1"] },
    { "id": "wave8", "tasks": ["8.1", "8.2"] },
    { "id": "wave9", "tasks": ["9.1", "9.2", "9.3"] },
    { "id": "wave10", "tasks": ["10.1"] }
  ]
}
```

## Notes

- F3是贷方科目（负债类），公式方向与F1（借方/资产类）相反：期末未审=期初审定+贷方-借方
- F3-2明细表(25列)拆为3区段Tab（基础信息9列/票据详情8列/审定调整8列）
- F3-7检查表(97行18列)采用借方/贷方独立区块设计（类似F1-7），非区段Tab
- F3-4带息票据利息测算是本循环特色sheet：面值×利率×天数/360
- F3-5逾期票据检查含风险等级自动建议逻辑（逾期>90天→高风险）
- 抽凭引擎集成在F3-7（检查表），OCR集成在F3-4（利息测算表识别票据信息）
- 截止自动提取(useCutoffAutoSampling)不适用于F3（无截止测试需求）
- F3A程序表直接复用a-program-console组件，不需独立开发

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将F3A/F3-1~F3-7/附注披露(上市)/附注披露(国企)映射为'f3-notes-payable'（10个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'f3-notes-payable'
    - 在 `htmlRendererRegistry.ts` 中注册 'f3-notes-payable' → GtF3NotesPayable 映射
    - 创建 `GtF3NotesPayable.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy + selfLoad逻辑 + el-tabs 10 tabs + OnlyOffice fallback）
    - _Requirements: 1.1~1.8_

  - [x]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'f3-notes-payable'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证10个映射条目
    - _Requirements: 1.3, 1.4, 1.5_

- [x] 2. 实现公式引擎 useF3FormulaEngine.ts
  - [x] 2.1 创建 `composables/useF3FormulaEngine.ts`，实现全部6个纯函数
    - 实现 `calcInterest`（应付利息 = 面值 × 利率/100 × 天数/360，面值<0或天数<0→0）
    - 实现 `calcOverdueDays`（逾期天数 = MAX(0, 当前日期timestamp - 到期日timestamp) / 86400000，取整）
    - 实现 `calcCreditBalance`（贷方余额 = 期初 + 贷方 - 借方）
    - 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
    - 实现 `calcConcentration`（集中度 = 单一方金额 / 总额 × 100，总额=0→0）
    - 实现 `isDebitCreditBalanced`（借贷平衡 = |SUM(debits) - SUM(credits)| < 0.01）
    - _Requirements: 11.1~11.6_

  - [x]* 2.2 编写 Property 1 PBT：带息票据利息公式
    - 生成器：`fc.float({min:0, max:1e8})` principal + `fc.float({min:0, max:100})` rate + `fc.nat({max:3650})` days
    - 断言：calcInterest(principal, rate, days) === principal × rate/100 × days/360
    - **Property 1: 应付利息=面值×利率/100×天数/360**
    - **Validates: Requirements 11.1, 7.3**

  - [x]* 2.3 编写 Property 2 PBT：贷方余额公式
    - 生成器：`fc.float({min:0, max:1e9})` × opening/credit/debit
    - 断言：calcCreditBalance(opening, credit, debit) === opening + credit - debit
    - **Property 2: 贷方余额=期初+贷方-借方**
    - **Validates: Requirements 11.3, 3.3, 5.2**

  - [x]* 2.4 编写 Property 3 PBT：审定数公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` × unadjusted/aje/rje
    - 断言：calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
    - **Property 3: 审定=未审+AJE+RJE**
    - **Validates: Requirements 11.4, 3.4**

  - [x]* 2.5 编写 Property 4 PBT：借贷平衡恒等
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:1, maxLength:20})` × debits/credits
    - 断言：isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
    - **Property 4: 借贷平衡=SUM借方===SUM贷方**
    - **Validates: Requirements 11.6, 6.2**

  - [x]* 2.6 编写 Property 5 PBT：集中度公式
    - 生成器：`fc.float({min:0, max:1e8})` amount + `fc.float({min:0.01, max:1e9})` total
    - 断言：calcConcentration(amount, total) === amount/total × 100
    - **Property 5: 集中度=amount/total×100**
    - **Validates: Requirements 11.5, 9.2**

  - [x]* 2.7 编写 Property 6 PBT：逾期天数非负
    - 生成器：fc.date() × currentDate/dueDate
    - 断言：calcOverdueDays(currentDate, dueDate) ≥ 0
    - **Property 6: 逾期天数恒≥0**
    - **Validates: Requirements 11.2, 8.2**

  - [x]* 2.8 编写 Property 7 PBT：利息与面值正比
    - 生成器：`fc.float({min:0.01, max:1e8})` × p1/p2 + 固定rate/days
    - 断言：calcInterest(p1, rate, days) / calcInterest(p2, rate, days) ≈ p1/p2（浮点误差<1e-10）
    - **Property 7: 利息与面值成正比**
    - **Validates: Requirements 11.1, 7.3**

  - [x]* 2.9 编写 Property 8 PBT：贷方余额方向性
    - 生成器：`fc.float({min:0, max:1e8})` × opening + credit>debit的一组
    - 断言：credit > debit → calcCreditBalance(opening, credit, debit) > opening
    - **Property 8: 贷方>借方→余额增加**
    - **Validates: Requirements 11.3, 3.3**

- [x] 3. 实现 useF3FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useF3FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate / debouncedSave / saveBatch
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=f3-notes-payable）
    - _Requirements: 1.6_

- [x] 4. 实现审定表 + 附注披露 composable
  - [x] 4.1 创建 `composables/useF3Adjudication.ts`
    - 定义 `AdjudicationRow` 类型（项目/期初4列/期末4列/索引）
    - 实现行结构：银行承兑汇票/商业承兑汇票/合计/试算表数/差异
    - 实现贷方公式链：期末未审=期初审定+贷方-借方 → 审定=未审+AJE+RJE → 合计=银行+商业
    - 实现试算表自动取数（科目2201 from trial_balance）
    - 实现差异计算+差异≠0红色标记
    - 实现EventBus发布 `substantive:adjudicated`(accountCode='2201')
    - 实现序列化/反序列化
    - _Requirements: 3.1~3.9_

  - [x]* 4.2 编写审定表单元测试
    - 验证贷方余额公式方向正确（期初+贷方-借方）
    - 验证合计行=银行承兑+商业承兑
    - 验证差异=审定-试算表数
    - _Requirements: 3.3~3.7_

- [x] 5. 实现明细表/调整分录/利息测算/逾期检查 composable
  - [x] 5.1 创建 `composables/useF3Detail.ts`（F3-2明细表3区段逻辑）
    - 定义 `NoteDetailRow` 类型（25列分3区段）
    - 实现3区段列配置导出
    - 实现公式链：期末余额=期初+增加-减少 / 审定=期末+AJE+RJE / 逾期天数=MAX(0,today-到期日)
    - 实现区段间行同步
    - 实现动态行增删 + 合计行 + 序列化/反序列化
    - _Requirements: 5.1~5.8_

  - [x] 5.2 创建 `composables/useF3InterestCalc.ts`（F3-4利息测算逻辑）
    - 定义 `InterestCalcRow` 类型（13列）
    - 实现公式链：应计天数=截止日-起始日 / 应付利息=面值×利率/100×天数/360 / 差异=应付-企业计提
    - 实现|差异|>100元橙色标记
    - 实现合计行 + 动态行增删 + 序列化/反序列化
    - _Requirements: 7.1~7.8_

  - [x] 5.3 创建 `composables/useF3OverdueCheck.ts`（F3-5逾期检查逻辑）
    - 定义 `OverdueNoteRow` 类型（15列）
    - 实现逾期天数公式 + 风险等级自动建议（>90→高，>30→中）
    - 实现高亮标记（>90红色，>30橙色）
    - 实现合计行（逾期笔数/总金额/高风险笔数） + 动态行增删 + 序列化/反序列化
    - _Requirements: 8.1~8.7_

  - [x] 5.4 创建 `composables/useF3RelatedParty.ts`（F3-6关联方检查逻辑）
    - 定义 `RelatedPartyNoteRow` 类型（16列）
    - 实现占比公式 + 集中度>30%橙色高亮
    - 实现合计行 + 动态行增删 + 序列化/反序列化
    - _Requirements: 9.1~9.6_

- [x] 6. 实现 Vue子组件
  - [x] 6.1 创建 `f3-notes-payable/F3TabAdjudication.vue`（F3-1审定表）
    - 调用useF3Adjudication
    - el-table渲染（项目|期初4列|期末4列|索引）
    - 合计行加粗 + 差异行红色 + 试算表数只读
    - EventBus发布 + GtIndexChip索引列
    - _Requirements: 3.1~3.9_

  - [x] 6.2 创建 `f3-notes-payable/F3TabDetail.vue`（F3-2明细表 25列→3区段Tab）
    - 调用useF3Detail
    - 3区段Tab切换（基础信息/票据详情/审定调整）
    - 区段间行同步 + 逾期行橙色高亮
    - 动态行增删 + 底部合计 + 导入导出
    - UI铁律：13px/公式列虚线/min-width
    - _Requirements: 5.1~5.8_

  - [x] 6.3 创建 `f3-notes-payable/F3TabInterestCalc.vue`（F3-4利息测算）
    - 调用useF3InterestCalc
    - el-table 13列 + 差异>100橙色高亮
    - 📎OCR列（POST contract-ocr识别票据面值/利率/期限→确认merge）
    - 动态行增删 + 底部合计 + 审计结论textarea(AI) + 编制提示details
    - 导入导出 + 虚拟滚动(>50行)
    - _Requirements: 7.1~7.8, 12.4_

  - [x] 6.4 创建 `f3-notes-payable/F3TabOverdueCheck.vue` + `F3TabRelatedParty.vue`
    - F3-5逾期检查：15列 + 风险高亮 + 底部汇总 + 动态行增删 + 导入导出 + AI
    - F3-6关联方检查：16列 + 集中度>30%橙色 + 底部汇总 + 动态行增删 + 导入导出 + AI
    - _Requirements: 8.1~8.7, 9.1~9.6_

  - [x] 6.5 创建 `f3-notes-payable/F3TabVoucherCheck.vue`（F3-7检查表 借方/贷方区块）
    - 创建 `composables/useF3VoucherCheck.ts`
    - 借方检查区(减少) + 贷方检查区(增加) 独立el-table
    - GtVoucherSamplingEngine集成（dialog模式，预填科目2201，样本按借贷方向分配）
    - 各区独立动态行增删 + 底部小计 + 审计结论textarea(AI)
    - 导入导出 + 虚拟滚动(97行)
    - 已抽凭行tooltip来源标记
    - _Requirements: 10.1~10.9_

- [x] 7. Checkpoint - 公式引擎+组件验证
  - Ensure all PBT tests pass (P1~P8), ask the user if questions arise.

- [x] 8. 实现后端 + 导入导出 + AI
  - [x] 8.1 创建后端3个py文件
    - `_f3_notes_payable.py`：render策略函数 + 注册RENDERER_DISPATCH['f3-notes-payable']
    - `_f3_notes_payable_import_export.py`：3端点（export-template/export-data/import-data）+ 6张动态行表格支持
    - `_f3_notes_payable_ai.py`：5个AI section端点 + 30秒超时
    - _Requirements: 1.3, 13.1~13.4_

  - [x] 8.2 创建 `composables/useF3ImportExport.ts` + `composables/useF3DualMode.ts`
    - useF3ImportExport：el-dropdown"导入导出▾" + axios三端点 + 6张表参数
    - useF3DualMode：模式状态(html/onlyoffice) + 切换逻辑 + localStorage持久化
    - _Requirements: 13.1~13.4_

- [x] 9. 跨模块联动集成
  - [x] 9.1 版本链集成
    - 主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 12.1, 12.5_

  - [x] 9.2 附注EventBus集成
    - 附注披露组件（F3TabDisclosureListed.vue / F3TabDisclosureSOE.vue）
    - subscribe `substantive:adjudicated`(accountCode='2201')自动刷新
    - publish `disclosure:note-text-updated` 联动附注模块
    - _Requirements: 4.1~4.5, 12.3_

  - [x] 9.3 抽凭引擎 + OCR集成
    - F3-7: GtVoucherSamplingEngine dialog集成（科目2201，样本按借贷分配）
    - F3-4: 📎OCR列（POST contract-ocr→票据面值/利率/期限识别→确认弹窗→merge）
    - _Requirements: 10.6~10.8, 12.2, 12.4_

- [x] 10. 集成测试与验收
  - [x] 10.1 编写集成测试
    - sheetName分发正确性（10个sheet→对应组件）
    - 贷方余额公式链（期初+贷方-借方=期末→+AJE+RJE=审定）
    - 利息测算公式（面值×利率×天数/360）
    - F3-7抽凭引擎样本分配（借贷方向）
    - F3-2三区段Tab行同步
    - EventBus(substantive:adjudicated)跨组件传递
    - 导入导出round-trip
    - 逾期天数计算+风险等级自动建议
    - _Requirements: 全部_
