# Implementation Plan: G2 应收利息专属HTML精美组件

## Overview

实现G2应收利息专属组件`g2-interest-receivable`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtG2InterestReceivable.vue + 9个子组件 + 11个composable + 后端3个py文件。核心公式：借方余额=期初+借方-贷方；应收利息=面值×利率×天数/365；ECL=EAD×PD×LGD。10个有效sheet，1个xlsx源模板(97KB)。科目1132应收利息。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11"] },
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

- G2是借方科目（资产类），公式方向：期末未审=期初审定+借方-贷方
- G2-7坏账准备测算(18列)拆为2区段Tab（阶段划分9列/ECL测算9列）
- G2-8凭证检查表(103行21列)采用借方/贷方独立区块设计
- G2-5利息测算是本循环特色sheet：面值×票面利率×计息天数/365（注意是365天基准，非360天）
- G2与F3的利息区别：F3用360天基准（票据惯例），G2用365天基准（债券惯例）
- ECL三阶段是G2核心减值逻辑：Stage1(12个月PD)/Stage2(整个存续期PD)/Stage3(整个存续期PD+已减值)
- G2-6长期未收回检查含阶段转移建议逻辑（逾期>180天→Stage3，>90天→Stage2）
- 抽凭引擎集成在G2-8（检查表），OCR也在G2-8
- 截止自动提取不适用G2（应收利息无截止测试需求）
- G2A程序表直接复用a-program-console

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将G2A/G2-1~G2-8/附注披露(上市)/附注披露(国企)映射为'g2-interest-receivable'（11个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES` 中注册'g2-interest-receivable'
    - 在 `htmlRendererRegistry.ts` 中注册 'g2-interest-receivable' → GtG2InterestReceivable 映射
    - 创建 `GtG2InterestReceivable.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy + selfLoad逻辑 + el-tabs 10 tabs + OnlyOffice fallback）
    - _Requirements: 1.1~1.8_

  - [x]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'g2-interest-receivable'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证11个映射条目
    - _Requirements: 1.3, 1.4, 1.5_

- [x] 2. 实现公式引擎 useG2FormulaEngine.ts
  - [x] 2.1 创建 `composables/useG2FormulaEngine.ts`，实现全部10个纯函数
    - 实现 `calcInterest365`（应收利息 = 面值 × 利率/100 × 天数/365，面值<0或天数<0→0）
    - 实现 `calcAccruedDays`（计息天数 = 截止日timestamp - 起始日timestamp / 86400000，取整）
    - 实现 `calcDebitBalance`（借方余额 = 期初 + 借方 - 贷方）
    - 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
    - 实现 `calcECL`（ECL = EAD × PD × LGD，任一<0→0）
    - 实现 `calcOverdueDays`（逾期天数 = MAX(0, 当前日期 - 约定日)）
    - 实现 `determineStage`（已减值→3, 显著增加→2, 否则→1）
    - 实现 `isDebitCreditBalanced`（|SUM(debits) - SUM(credits)| < 0.01）
    - 实现 `calcNetReceivable`（期末应收 = 应计利息 - 已收利息）
    - 实现 `calcECLVariance`（差异 = 测算ECL - 企业计提）
    - _Requirements: 12.1~12.10_

  - [x]* 2.2 编写 Property 1 PBT：利息测算公式(365天)
    - 生成器：`fc.float({min:0, max:1e8})` principal + `fc.float({min:0, max:100})` rate + `fc.nat({max:3650})` days
    - 断言：calcInterest365(principal, rate, days) === principal × rate/100 × days/365
    - **Property 1: 应收利息=面值×利率/100×天数/365**
    - **Validates: Requirements 12.1, 5.3, 8.3**

  - [x]* 2.3 编写 Property 2 PBT：借方余额公式
    - 生成器：`fc.float({min:0, max:1e9})` × opening/debit/credit
    - 断言：calcDebitBalance(opening, debit, credit) === opening + debit - credit
    - **Property 2: 借方余额=期初+借方-贷方**
    - **Validates: Requirements 12.3, 3.3**

  - [x]* 2.4 编写 Property 3 PBT：审定数公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` × unadjusted/aje/rje
    - 断言：calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
    - **Property 3: 审定=未审+AJE+RJE**
    - **Validates: Requirements 12.4, 3.4**

  - [x]* 2.5 编写 Property 4 PBT：ECL公式
    - 生成器：`fc.float({min:0, max:1e8})` EAD + `fc.float({min:0, max:1})` PD + `fc.float({min:0, max:1})` LGD
    - 断言：calcECL(EAD, PD, LGD) === EAD × PD × LGD
    - **Property 4: ECL=EAD×PD×LGD**
    - **Validates: Requirements 12.5, 6.2, 10.4**

  - [x]* 2.6 编写 Property 5 PBT：逾期天数非负
    - 生成器：fc.date() × currentDate/dueDate
    - 断言：calcOverdueDays(currentDate, dueDate) ≥ 0
    - **Property 5: 逾期天数恒≥0**
    - **Validates: Requirements 12.6, 9.2**

  - [x]* 2.7 编写 Property 6 PBT：借贷平衡恒等
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:1, maxLength:20})` × debits/credits
    - 断言：isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
    - **Property 6: 借贷平衡**
    - **Validates: Requirements 12.8, 7.2**

  - [x]* 2.8 编写 Property 7 PBT：利息与面值正比
    - 生成器：`fc.float({min:0.01, max:1e8})` × p1/p2 + 固定rate/days
    - 断言：calcInterest365(p1, rate, days) / calcInterest365(p2, rate, days) ≈ p1/p2（浮点误差<1e-10）
    - **Property 7: 利息与面值成正比**
    - **Validates: Requirements 12.1, 5.3**

  - [x]* 2.9 编写 Property 8 PBT：ECL与EAD正比
    - 生成器：`fc.float({min:0.01, max:1e8})` × e1/e2 + 固定PD/LGD
    - 断言：calcECL(e1, PD, LGD) / calcECL(e2, PD, LGD) ≈ e1/e2
    - **Property 8: ECL与EAD成正比**
    - **Validates: Requirements 12.5, 10.4**

  - [x]* 2.10 编写 Property 9 PBT：阶段判定确定性
    - 生成器：fc.boolean() × impaired/significantIncrease
    - 断言：determineStage结果∈{1,2,3} ∧ impaired=true→3 ∧ !impaired&&significantIncrease→2 ∧ else→1
    - **Property 9: 阶段判定优先级：减值>显著增加>正常**
    - **Validates: Requirements 12.7, 10.2**

  - [x]* 2.11 编写 Property 10 PBT：净应收=应计-已收
    - 生成器：`fc.float({min:0, max:1e8})` × accrued/received
    - 断言：calcNetReceivable(accrued, received) === accrued - received
    - **Property 10: 净应收=应计利息-已收利息**
    - **Validates: Requirements 12.9, 5.4**

- [x] 3. 实现 useG2FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useG2FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate / debouncedSave / saveBatch
    - 实现 selfLoad逻辑
    - _Requirements: 1.6_

- [x] 4. 实现审定表 + 附注披露 composable
  - [x] 4.1 创建 `composables/useG2Adjudication.ts`
    - 定义 G2AdjudicationRow 类型
    - 行结构：债权投资利息/其他债权投资利息/定期存款利息/其他 + 合计 + 试算表数 + 差异
    - 实现借方公式链：期末未审=期初审定+借方-贷方 → 审定=未审+AJE+RJE → 合计汇总
    - 试算表取数(1132) + 差异+红色标记 + EventBus发布
    - _Requirements: 3.1~3.9_

  - [x]* 4.2 编写审定表单元测试
    - 验证借方余额公式方向正确（期初+借方-贷方）
    - 验证合计行汇总
    - 验证差异=审定-试算表数
    - _Requirements: 3.3~3.7_

- [x] 5. 实现明细表/坏账/利息测算/逾期检查/ECL composable
  - [x] 5.1 创建 `composables/useG2Detail.ts`（G2-2明细表16列）
    - 定义 InterestDetailRow 类型
    - 实现公式链：计息天数=截止-起始 / 应计利息=面值×利率×天数/365 / 期末应收=应计-已收 / 差异=应收-账面
    - 差异>100橙色标记 + 动态行增删 + 合计 + 序列化
    - _Requirements: 5.1~5.8_

  - [x] 5.2 创建 `composables/useG2InterestCalc.ts`（G2-5利息测算）
    - 定义利息测算行类型（11列）
    - 实现公式：应收利息=面值×利率×天数/365 / 差异=应收-企业计提
    - 差异>100橙色 + 合计 + 动态行增删
    - _Requirements: 8.1~8.8_

  - [x] 5.3 创建 `composables/useG2OverdueCheck.ts`（G2-6长期未收回）+ `useG2BadDebtDetail.ts`（G2-3坏账明细）
    - G2-6：逾期天数公式 + 阶段转移建议(>180→Stage3, >90→Stage2) + 风险等级
    - G2-3：ECL公式 + 阶段下拉 + 转移方向
    - _Requirements: 9.1~9.8, 6.1~6.7_

  - [x] 5.4 创建 `composables/useG2ECLCalc.ts`（G2-7 ECL测算2区段）+ `useG2VoucherCheck.ts`（G2-8检查表）
    - G2-7：2区段(阶段划分/ECL测算) + 阶段判定公式 + ECL=EAD×PD×LGD + 行同步
    - G2-8：借方/贷方独立区块 + 借方区测算利息公式 + 各区独立增删
    - _Requirements: 10.1~10.10, 11.1~11.11_

- [x] 6. 实现 Vue子组件
  - [x] 6.1 创建 `g2-interest-receivable/G2TabAdjudication.vue`（G2-1审定表）
    - 调用useG2Adjudication
    - el-table（项目|期初4列|期末4列|索引）
    - 合计加粗 + 差异红色 + EventBus + GtIndexChip
    - _Requirements: 3.1~3.9_

  - [x] 6.2 创建 `g2-interest-receivable/G2TabDetail.vue` + `G2TabInterestCalc.vue`
    - G2-2明细表（16列 + 利息公式 + 差异高亮 + 动态行增删 + 导入导出）
    - G2-5利息测算（11列 + 核心公式 + 合计 + AI结论 + 编制提示）
    - _Requirements: 5.1~5.8, 8.1~8.8_

  - [x] 6.3 创建 `G2TabBadDebtDetail.vue` + `G2TabOverdueCheck.vue`
    - G2-3坏账明细（20列 + ECL + 阶段下拉 + 转移方向）
    - G2-6长期未收回（13列 + 逾期>180红/>90橙 + 阶段建议 + 风险下拉）
    - _Requirements: 6.1~6.7, 9.1~9.8_

  - [x] 6.4 创建 `G2TabECLCalc.vue`（G2-7 坏账准备测算 2区段Tab）
    - 调用useG2ECLCalc
    - 2区段Tab（阶段划分/ECL测算）+ 行同步
    - 阶段判定公式列 + ECL公式列（虚线+tooltip）
    - 差异>10%阈值橙色 + 底部合计 + AI结论 + 编制提示
    - 虚拟滚动(72行) + 动态行增删 + 导入导出
    - _Requirements: 10.1~10.10_

  - [x] 6.5 创建 `G2TabVoucherCheck.vue`（G2-8 凭证检查表 借方/贷方区块）
    - 调用useG2VoucherCheck
    - 借方检查区(利息确认14列) + 贷方检查区(利息收回12列) 独立el-table
    - 借方区测算利息公式列(面值×利率×天数/365)
    - GtVoucherSamplingEngine集成（dialog模式，科目1132，按借贷分配）
    - 📎OCR列（POST contract-ocr→确认→merge）
    - 各区独立动态行增删 + 底部小计 + AI结论
    - 虚拟滚动(103行) + 导入导出 + 来源tooltip
    - _Requirements: 11.1~11.11_

- [x] 7. Checkpoint - 公式引擎+组件验证
  - Ensure all PBT tests pass (P1~P10), ask the user if questions arise.

- [x] 8. 实现后端 + 导入导出 + AI
  - [x] 8.1 创建后端3个py文件
    - `_g2_interest_receivable.py`：render策略函数 + 注册RENDERER_DISPATCH['g2-interest-receivable']
    - `_g2_interest_receivable_import_export.py`：3端点（export-template/export-data/import-data）+ 7张动态行表格支持
    - `_g2_interest_receivable_ai.py`：5个AI section端点 + 30秒超时
    - _Requirements: 1.3, 14.1~14.4_

  - [x] 8.2 创建 `composables/useG2ImportExport.ts` + `composables/useG2DualMode.ts`
    - useG2ImportExport：el-dropdown"导入导出▾" + axios三端点 + 7张表参数
    - useG2DualMode：模式状态(html/onlyoffice) + 切换逻辑 + localStorage持久化
    - _Requirements: 14.1~14.4_

- [x] 9. 跨模块联动集成
  - [x] 9.1 版本链集成
    - 主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 13.1, 13.5_

  - [x] 9.2 附注EventBus集成
    - G2TabDisclosureListed.vue / G2TabDisclosureSOE.vue
    - subscribe `substantive:adjudicated`(accountCode='1132')自动刷新
    - publish `disclosure:note-text-updated` 联动附注模块
    - _Requirements: 4.1~4.4, 13.3_

  - [x] 9.3 抽凭引擎 + OCR集成
    - G2-8: GtVoucherSamplingEngine dialog集成（科目1132，样本按借贷分配）
    - G2-8: 📎OCR列POST contract-ocr→凭证信息识别→确认弹窗→merge
    - _Requirements: 11.7~11.9, 13.2, 13.4_

- [x] 10. 集成测试与验收
  - [x] 10.1 编写集成测试
    - sheetName分发正确性（10个sheet→对应组件）
    - 借方余额公式链（期初+借方-贷方=期末→+AJE+RJE=审定）
    - 利息测算全链路（面值×利率×天数/365）
    - ECL三阶段测算（阶段判定→适用PD→ECL=EAD×PD×LGD）
    - G2-7两区段Tab行同步
    - G2-8抽凭引擎样本分配（借贷方向）
    - EventBus(substantive:adjudicated)跨组件传递
    - 导入导出round-trip(7张表)
    - 逾期天数计算+阶段转移建议
    - 虚拟滚动（72行ECL/103行检查表）
    - _Requirements: 全部_
