# Implementation Plan: G3 应收股利专属HTML精美组件

## Overview

实现G3应收股利专属组件`g3-dividend-receivable`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtG3DividendReceivable.vue + 6个子组件 + 8个composable + 后端3个py文件。核心公式：借方余额=期初+借方-贷方；应收股利=持股数×每股股利；分红率=分红总额/净利润×100%。7个有效sheet，1个xlsx源模板(469KB)。科目1131应收股利。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2"] },
    { "id": "wave5", "tasks": ["5.1", "5.2", "5.3"] },
    { "id": "wave6", "tasks": ["6.1", "6.2", "6.3", "6.4"] },
    { "id": "wave7", "tasks": ["7.1"] },
    { "id": "wave8", "tasks": ["8.1", "8.2"] },
    { "id": "wave9", "tasks": ["9.1", "9.2", "9.3"] },
    { "id": "wave10", "tasks": ["10.1"] }
  ]
}
```

## Notes

- G3是借方科目（资产类）：期末未审=期初审定+借方(本期宣告)-贷方(本期收回)
- G3-2明细表(33列)拆为4区段Tab（被投资方信息8列/持股明细9列/分红方案8列/应收核算8列）
- G3-4测算及检查表(18列)拆为2区段Tab（股利测算9列/凭证检查9列）
- G3-1审定表较特殊：22列按被投资方分行（含持股比例列+本期宣告/收回列）
- G3核心公式简单：应收股利=持股数×每股股利
- 分红率计算需注意：净利润≤0时返回0或N/A
- 动态行新增时需弹ElMessageBox.prompt输入被投资方名称
- 抽凭引擎集成在G3-4（测算及检查表的凭证检查区段）
- 截止自动提取不适用G3
- G3A程序表直接复用a-program-console
- G3相对简单（7 sheets），el-tabs模式

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将G3A/G3-1~G3-5/附注披露(上市)/附注披露(国企)映射为'g3-dividend-receivable'（8个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES` 中注册'g3-dividend-receivable'
    - 在 `htmlRendererRegistry.ts` 中注册 'g3-dividend-receivable' → GtG3DividendReceivable 映射
    - 创建 `GtG3DividendReceivable.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy + selfLoad逻辑 + el-tabs 7 tabs + OnlyOffice fallback）
    - _Requirements: 1.1~1.8_

  - [x]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'g3-dividend-receivable'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证8个映射条目
    - _Requirements: 1.3, 1.4, 1.5_

- [x] 2. 实现公式引擎 useG3FormulaEngine.ts
  - [x] 2.1 创建 `composables/useG3FormulaEngine.ts`，实现全部8个纯函数
    - 实现 `calcDividend`（应收股利 = 持股数 × 每股股利，持股数<0→0）
    - 实现 `calcPayoutRatio`（实际分红率 = 分红总额 / 净利润 × 100%，净利润≤0→0）
    - 实现 `calcDebitBalance`（借方余额 = 期初 + 借方 - 贷方）
    - 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
    - 实现 `calcOverdueDays`（逾期天数 = MAX(0, 当前日期 - 约定日)）
    - 实现 `calcNetReceivable`（期末应收 = 应收股利 - 已收金额）
    - 实现 `calcEquityShare`（权益份额 = 净资产 × 持股比例/100）
    - 实现 `isDebitCreditBalanced`（|SUM(debits) - SUM(credits)| < 0.01）
    - _Requirements: 9.1~9.8_

  - [x]* 2.2 编写 Property 1 PBT：股利测算公式
    - 生成器：`fc.nat({max:1e8})` shares + `fc.float({min:0, max:100})` dps
    - 断言：calcDividend(shares, dps) === shares × dps
    - **Property 1: 应收股利=持股数×每股股利**
    - **Validates: Requirements 9.1, 5.3, 5.5, 7.2**

  - [x]* 2.3 编写 Property 2 PBT：借方余额公式
    - 生成器：`fc.float({min:0, max:1e9})` × opening/debit/credit
    - 断言：calcDebitBalance(opening, debit, credit) === opening + debit - credit
    - **Property 2: 借方余额=期初+借方-贷方**
    - **Validates: Requirements 9.3, 3.3**

  - [x]* 2.4 编写 Property 3 PBT：审定数公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` × unadjusted/aje/rje
    - 断言：calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
    - **Property 3: 审定=未审+AJE+RJE**
    - **Validates: Requirements 9.4, 3.4**

  - [x]* 2.5 编写 Property 4 PBT：逾期天数非负
    - 生成器：fc.date() × currentDate/dueDate
    - 断言：calcOverdueDays(currentDate, dueDate) ≥ 0
    - **Property 4: 逾期天数恒≥0**
    - **Validates: Requirements 9.5, 8.2**

  - [x]* 2.6 编写 Property 5 PBT：借贷平衡恒等
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:1, maxLength:20})` × debits/credits
    - 断言：isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
    - **Property 5: 借贷平衡**
    - **Validates: Requirements 9.8, 6.2**

  - [x]* 2.7 编写 Property 6 PBT：分红率与分红总额正比
    - 生成器：`fc.float({min:0.01, max:1e8})` × d1/d2 + `fc.float({min:0.01, max:1e8})` netProfit
    - 断言：calcPayoutRatio(d1, netProfit) / calcPayoutRatio(d2, netProfit) ≈ d1/d2
    - **Property 6: 分红率与分红额成正比**
    - **Validates: Requirements 9.2, 5.4**

  - [x]* 2.8 编写 Property 7 PBT：股利与持股数正比
    - 生成器：`fc.nat({min:1, max:1e8})` × s1/s2 + `fc.float({min:0.01, max:100})` dps
    - 断言：calcDividend(s1, dps) / calcDividend(s2, dps) ≈ s1/s2
    - **Property 7: 股利与持股成正比**
    - **Validates: Requirements 9.1, 5.3**

  - [x]* 2.9 编写 Property 8 PBT：净应收=应收-已收
    - 生成器：`fc.float({min:0, max:1e8})` × receivable/received
    - 断言：calcNetReceivable(receivable, received) === receivable - received
    - **Property 8: 净应收=应收股利-已收金额**
    - **Validates: Requirements 9.6, 5.6**

  - [x]* 2.10 编写 Property 9 PBT：权益份额公式
    - 生成器：`fc.float({min:-1e9, max:1e9})` netAssets + `fc.float({min:0, max:100})` ratio
    - 断言：calcEquityShare(netAssets, ratio) === netAssets × ratio/100
    - **Property 9: 权益份额=净资产×持股比例/100**
    - **Validates: Requirements 9.7, 5.2**

  - [x]* 2.11 编写 Property 10 PBT：分红率非负
    - 生成器：`fc.float({min:0, max:1e8})` dividendTotal + `fc.float({min:0.01, max:1e8})` netProfit
    - 断言：calcPayoutRatio(dividendTotal, netProfit) ≥ 0
    - **Property 10: 净利润>0时分红率≥0**
    - **Validates: Requirements 9.2**

- [x] 3. 实现 useG3FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useG3FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate / debouncedSave / saveBatch
    - 实现 selfLoad逻辑
    - _Requirements: 1.6_

- [x] 4. 实现审定表 + 附注披露 composable
  - [x] 4.1 创建 `composables/useG3Adjudication.ts`
    - 定义 G3AdjudicationRow 类型（22列，含被投资方/持股比例/本期宣告/本期收回）
    - 行结构：按被投资方逐行（动态增删，新增弹ElMessageBox.prompt）+ 合计 + 试算表数 + 差异
    - 实现借方公式：期末未审 = 期初审定 + 本期宣告(借方) - 本期收回(贷方)
    - 审定=未审+AJE+RJE → 合计汇总 → 试算表取数(1131) → 差异+红色
    - EventBus发布 `substantive:adjudicated`(accountCode='1131')
    - _Requirements: 3.1~3.10_

  - [x]* 4.2 编写审定表单元测试
    - 验证借方余额公式方向（期初+宣告-收回）
    - 验证合计行汇总
    - 验证差异=审定-试算表数
    - _Requirements: 3.3~3.7_

- [x] 5. 实现明细表/测算检查/逾期 composable
  - [x] 5.1 创建 `composables/useG3Detail.ts`（G3-2明细表4区段逻辑）
    - 定义 DividendDetailRow 类型（33列分4区段）
    - 4区段列配置导出（被投资方8/持股9/分红8/应收8）
    - 公式链：权益份额=净资产×比例/100 / 分红总额=持股×DPS / 分红率=总额/净利润×100% / 应收=持股×DPS / 期末应收=应收-已收 / 逾期天数
    - 区段间行同步 + 动态行增删(弹名称输入) + 合计 + 逾期行橙色
    - _Requirements: 5.1~5.11_

  - [x] 5.2 创建 `composables/useG3CalcCheck.ts`（G3-4测算及检查2区段）
    - 定义 CalcCheckRow 类型（18列分2区段）
    - 2区段：股利测算(应收=持股×DPS, 差异=测算-入账) / 凭证检查(9列)
    - 区段间行同步 + 差异>100橙色 + 抽凭引擎集成(样本填入凭证检查区段)
    - 动态行增删 + 合计 + 来源tooltip
    - _Requirements: 7.1~7.10_

  - [x] 5.3 创建 `composables/useG3OverdueCheck.ts`（G3-5长期未收回）
    - 定义 OverdueDividendRow 类型（13列）
    - 逾期天数公式 + 风险高亮(>180红/>90橙) + 风险/可收回性下拉
    - 底部汇总 + 动态行增删
    - _Requirements: 8.1~8.8_

- [x] 6. 实现 Vue子组件
  - [x] 6.1 创建 `g3-dividend-receivable/G3TabAdjudication.vue`（G3-1审定表22列）
    - 调用useG3Adjudication
    - el-table（被投资方|持股比例|期初4列|期末4列|宣告|收回|备注|索引）
    - 合计加粗 + 差异红色 + EventBus + GtIndexChip + 动态行增删(弹名称)
    - _Requirements: 3.1~3.10_

  - [x] 6.2 创建 `g3-dividend-receivable/G3TabDetail.vue`（G3-2明细表 33列→4区段Tab）
    - 调用useG3Detail
    - 4区段Tab切换（被投资方/持股/分红/应收）
    - 区段间行同步 + 逾期行橙色 + 分红率N/A处理
    - 动态行增删(弹名称) + 底部合计 + 导入导出
    - UI铁律：13px/公式列虚线/min-width
    - _Requirements: 5.1~5.11_

  - [x] 6.3 创建 `G3TabCalcCheck.vue`（G3-4测算及检查 2区段Tab）
    - 调用useG3CalcCheck
    - 2区段Tab（股利测算/凭证检查）+ 行同步
    - 股利测算公式列(持股×DPS)虚线+tooltip + 差异>100橙色
    - GtVoucherSamplingEngine集成（dialog，科目1131，样本填入凭证检查区段）
    - 底部合计 + 审计结论textarea(AI) + 编制提示details + 导入导出
    - 已抽凭行来源tooltip
    - _Requirements: 7.1~7.10_

  - [x] 6.4 创建 `G3TabAdjustment.vue` + `G3TabOverdueCheck.vue` + 附注披露
    - G3-3调整分录（借贷平衡 + 动态行增删 + 导入导出）
    - G3-5长期未收回（逾期高亮 + 风险下拉 + 底部汇总 + AI结论 + 导入导出）
    - G3TabDisclosureListed.vue + G3TabDisclosureSOE.vue（EventBus subscribe/publish）
    - _Requirements: 6.1~6.4, 8.1~8.8, 4.1~4.4_

- [x] 7. Checkpoint - 公式引擎+组件验证
  - Ensure all PBT tests pass (P1~P10), ask the user if questions arise.

- [x] 8. 实现后端 + 导入导出 + AI
  - [x] 8.1 创建后端3个py文件
    - `_g3_dividend_receivable.py`：render策略函数 + 注册RENDERER_DISPATCH['g3-dividend-receivable']
    - `_g3_dividend_receivable_import_export.py`：3端点（export-template/export-data/import-data）+ 5张动态行表格支持
    - `_g3_dividend_receivable_ai.py`：3个AI section端点 + 30秒超时
    - _Requirements: 1.3, 14.1~14.4_

  - [x] 8.2 创建 `composables/useG3ImportExport.ts` + `composables/useG3DualMode.ts`
    - useG3ImportExport：el-dropdown"导入导出▾" + axios三端点 + 5张表参数
    - useG3DualMode：模式状态(html/onlyoffice) + 切换逻辑 + localStorage持久化
    - _Requirements: 14.1~14.4_

- [x] 9. 跨模块联动集成
  - [x] 9.1 版本链集成
    - 主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 13.1, 13.5_

  - [x] 9.2 附注EventBus集成
    - G3TabDisclosureListed.vue / G3TabDisclosureSOE.vue
    - subscribe `substantive:adjudicated`(accountCode='1131')自动刷新
    - publish `disclosure:note-text-updated` 联动附注模块
    - _Requirements: 4.1~4.4, 13.3_

  - [x] 9.3 抽凭引擎集成
    - G3-4: GtVoucherSamplingEngine dialog集成（科目1131，样本填入凭证检查区段+来源tooltip）
    - _Requirements: 7.8~7.10, 13.2_

- [x] 10. 集成测试与验收
  - [x] 10.1 编写集成测试
    - sheetName分发正确性（7个sheet→对应组件）
    - 借方余额公式链（期初+宣告-收回=期末→+AJE+RJE=审定）
    - 股利测算公式（持股数×每股股利）
    - 分红率计算（分红总额/净利润×100%，净利润≤0→0/N/A）
    - G3-2四区段Tab行同步
    - G3-4两区段Tab行同步+抽凭样本填入
    - EventBus(substantive:adjudicated)跨组件传递
    - 导入导出round-trip(5张表)
    - 逾期天数计算+风险评估
    - 动态行新增弹名称输入
    - _Requirements: 全部_
