# Implementation Plan: G1 交易性金融资产专属HTML精美组件

## Overview

实现G1交易性金融资产专属组件`g1-trading-financial-assets`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtG1TradingFinancialAssets.vue + 15个子组件(按子目录分组) + 15个composable + 后端3个py文件。核心公式：借方余额=期初+借方-贷方；公允价值=数量×单位公允值；未实现损益=公允-成本；Level1差异=持仓×报价-账面。16个有效sheet，1个xlsx源模板(153KB)。科目1501交易性金融资产。**最复杂的投资科目底稿**。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3"] },
    { "id": "wave5", "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6"] },
    { "id": "wave6", "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "6.8"] },
    { "id": "wave7", "tasks": ["7.1"] },
    { "id": "wave8", "tasks": ["8.1", "8.2"] },
    { "id": "wave9", "tasks": ["9.1", "9.2", "9.3"] },
    { "id": "wave10", "tasks": ["10.1"] }
  ]
}
```

## Notes

- G1是最复杂的投资科目底稿（16 sheets > 12 threshold → sheetName v-if dispatch模式）
- 子目录分组：core/(审定+明细+调整+附注) + valuation/(公允价值) + classification/(分类) + inspection/(检查盘点)
- G1-2明细表(35列)拆为5区段Tab（每区段7列，基础/持有/公允/损益/审定）
- G1-9分类适当性(21列)拆为2区段Tab（SPPI测试11列/业务模式判定10列）
- G1-5收益测算(18列)/G1-4结存(21列)/G1-12倒轧(18列)各拆为2区段Tab
- G1是借方科目（资产类）：期末未审=期初审定+借方-贷方
- G1-6公允价值测试表的特色：Level下拉→条件启用/禁用对应Level列（Level1/2/3互斥）
- G1-1审定表是多层结构（品种分组→子层：成本/公允变动/处置损益），需展开/折叠
- 附注披露(上市)198行需虚拟滚动
- G1-8/G1-10为叙述式表格（textarea每格，autosize）
- 抽凭引擎集成在G1-13（检查表），OCR也在G1-13
- 截止自动提取不适用G1（投资科目无截止测试）
- G1A程序表直接复用a-program-console

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将G1A/G1-1~G1-14/附注披露(上市)/附注披露(国企)映射为'g1-trading-financial-assets'（17个wp_code条目）
    - 在 `VALID_COMPONENT_TYPES` 中注册'g1-trading-financial-assets'
    - 在 `htmlRendererRegistry.ts` 中注册 'g1-trading-financial-assets' → GtG1TradingFinancialAssets 映射
    - 创建 `GtG1TradingFinancialAssets.vue` 主入口骨架（sheetName prop + regex提取编码 + v-if分发 + defineAsyncComponent lazy + selfLoad逻辑 + OnlyOffice fallback）
    - 创建子目录结构：g1-trading-financial-assets/{core,valuation,classification,inspection}/
    - _Requirements: 1.1~1.9_

  - [ ]* 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'g1-trading-financial-assets'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证17个映射条目
    - _Requirements: 1.3, 1.4, 1.5_

- [x] 2. 实现公式引擎 useG1FormulaEngine.ts
  - [x] 2.1 创建 `composables/useG1FormulaEngine.ts`，实现全部12个纯函数
    - 实现 `calcDebitBalance`（借方余额 = 期初 + 借方 - 贷方）
    - 实现 `calcAdjustedAmount`（审定 = 未审 + AJE + RJE）
    - 实现 `calcFairValue`（公允价值 = 数量 × 单位公允值，数量<0→0）
    - 实现 `calcUnrealizedGain`（未实现损益 = 公允价值 - 成本）
    - 实现 `calcRealizedGain`（已实现损益 = 处置收入 - 成本）
    - 实现 `calcNetGain`（净损益 = 已实现损益 - 手续费）
    - 实现 `calcLevel1Diff`（Level1差异 = 持仓×报价 - 账面值）
    - 实现 `calcCountDiff`（盘点差异 = 盘点数量 - 账面数量）
    - 实现 `calcReconciliation`（倒轧余额 = 监盘日余额 + 增加 - 减少）
    - 实现 `calcClosingQuantity`（期末数量 = 期初 + 买入 - 卖出，结果<0→0）
    - 实现 `isDebitCreditBalanced`（借贷平衡 = |SUM(debits) - SUM(credits)| < 0.01）
    - 实现 `calcFairValueChange`（公允变动 = 期末公允 - 期初公允）
    - _Requirements: 13.1~13.12_

  - [x]* 2.2 编写 Property 1 PBT：借方余额公式
    - 生成器：`fc.float({min:0, max:1e9})` × opening/debit/credit
    - 断言：calcDebitBalance(opening, debit, credit) === opening + debit - credit
    - **Property 1: 借方余额=期初+借方-贷方**
    - **Validates: Requirements 13.1, 3.4**

  - [x]* 2.3 编写 Property 2 PBT：公允价值计算
    - 生成器：`fc.nat({max:1e6})` quantity + `fc.float({min:0, max:1e4})` unitFV
    - 断言：calcFairValue(quantity, unitFV) === quantity × unitFV
    - **Property 2: 公允价值=数量×单位公允值**
    - **Validates: Requirements 13.3, 5.3, 9.3**

  - [x]* 2.4 编写 Property 3 PBT：未实现损益公式
    - 生成器：`fc.float({min:0, max:1e9})` × fairValue/cost
    - 断言：calcUnrealizedGain(fairValue, cost) === fairValue - cost
    - **Property 3: 未实现损益=公允-成本**
    - **Validates: Requirements 13.4, 7.4**

  - [x]* 2.5 编写 Property 4 PBT：已实现损益公式
    - 生成器：`fc.float({min:0, max:1e8})` × proceeds/cost
    - 断言：calcRealizedGain(proceeds, cost) === proceeds - cost
    - **Property 4: 已实现损益=处置收入-成本**
    - **Validates: Requirements 13.5, 5.5, 8.3**

  - [x]* 2.6 编写 Property 5 PBT：Level1差异公式
    - 生成器：`fc.nat({max:1e6})` qty + `fc.float({min:0, max:1e4})` quote + `fc.float({min:0, max:1e9})` bookValue
    - 断言：calcLevel1Diff(qty, quote, bookValue) === qty × quote - bookValue
    - **Property 5: Level1差异=持仓×报价-账面值**
    - **Validates: Requirements 13.7, 9.2**

  - [x]* 2.7 编写 Property 6 PBT：盘点差异公式
    - 生成器：`fc.integer({min:0, max:1e6})` × counted/booked
    - 断言：calcCountDiff(counted, booked) === counted - booked
    - **Property 6: 盘点差异=盘点-账面**
    - **Validates: Requirements 13.8, 12.2**

  - [x]* 2.8 编写 Property 7 PBT：倒轧余额公式
    - 生成器：`fc.float({min:0, max:1e9})` × countDay/increase/decrease
    - 断言：calcReconciliation(countDay, increase, decrease) === countDay + increase - decrease
    - **Property 7: 倒轧=监盘日+增加-减少**
    - **Validates: Requirements 13.9, 12.5**

  - [x]* 2.9 编写 Property 8 PBT：期末数量公式
    - 生成器：`fc.nat({max:1e6})` × opening/bought/sold（约束sold≤opening+bought）
    - 断言：calcClosingQuantity(opening, bought, sold) === opening + bought - sold
    - **Property 8: 期末数量=期初+买入-卖出**
    - **Validates: Requirements 13.10, 5.2, 7.2**

  - [x]* 2.10 编写 Property 9 PBT：借贷平衡恒等
    - 生成器：`fc.array(fc.float({min:0, max:1e6}), {minLength:1, maxLength:20})` × debits/credits
    - 断言：isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
    - **Property 9: 借贷平衡**
    - **Validates: Requirements 13.11, 6.2**

  - [x]* 2.11 编写 Property 10 PBT：净损益公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` realizedGain + `fc.float({min:0, max:1e6})` fee
    - 断言：calcNetGain(realizedGain, fee) === realizedGain - fee
    - **Property 10: 净损益=已实现-手续费**
    - **Validates: Requirements 13.6, 8.4**

  - [x]* 2.12 编写 Property 11 PBT：公允价值变动方向性
    - 生成器：fc.float × endFV > startFV（约束endFV > startFV）
    - 断言：calcFairValueChange(endFV, startFV) > 0
    - **Property 11: 期末>期初→变动>0**
    - **Validates: Requirements 13.12**

  - [x]* 2.13 编写 Property 12 PBT：审定数公式
    - 生成器：`fc.float({min:-1e8, max:1e8})` × unadjusted/aje/rje
    - 断言：calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
    - **Property 12: 审定=未审+AJE+RJE**
    - **Validates: Requirements 13.2, 3.5, 5.8**

- [x] 3. 实现 useG1FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useG1FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate / debouncedSave / saveBatch
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=g1-trading-financial-assets）
    - _Requirements: 1.6_

- [x] 4. 实现 core/ composable（审定表+明细表+调整）
  - [x] 4.1 创建 `composables/useG1Adjudication.ts`
    - 定义多层结构类型（AdjudicationCategory + SubRow）
    - 5品种分组（股票/基金/债券/衍生/其他）× 3子层（成本/公允变动/处置损益）
    - 实现借方公式链：期末未审=期初审定+借方-贷方 → 审定=未审+AJE+RJE
    - 实现品种小计+全部合计+试算表取数(1501)+差异+红色标记
    - 实现展开/折叠+EventBus发布`substantive:adjudicated`
    - _Requirements: 3.1~3.11_

  - [x] 4.2 创建 `composables/useG1Detail.ts`（G1-2明细表5区段逻辑）
    - 定义 `TradingDetailRow` 类型（35列分5区段）
    - 5区段列配置导出（基础/持有/公允/损益/审定各7列）
    - 公式链：期末数量/期末公允/变动/已实现损益/收益合计/期末成本/审定
    - 区段间行同步 + 动态行增删 + 分类小计+总计
    - _Requirements: 5.1~5.11_

  - [x] 4.3 创建附注披露逻辑
    - 附注(上市)198行虚拟滚动 + 附注(国企)32行
    - subscribe `substantive:adjudicated` + publish `disclosure:note-text-updated`
    - _Requirements: 4.1~4.5_

- [x] 5. 实现 valuation/ + classification/ + inspection/ composable
  - [x] 5.1 创建 `composables/useG1FairValueTest.ts`（G1-6公允价值测试）
    - 定义 FairValueTestRow 类型（19列）
    - Level条件启用逻辑（Level1/2/3互斥启用列）
    - Level1公式：计算市值=持仓×报价, 差异=市值-账面
    - Level2/3公式：差异=估值结果-账面
    - 差异>1%阈值橙色标记 + 底部统计
    - _Requirements: 9.1~9.10_

  - [x] 5.2 创建 `composables/useG1Level3.ts`（G1-7第三层次调节）
    - 定义调节行类型（13列）
    - 期末余额公式=期初+增加-减少+本期公允变动
    - _Requirements: 10.1~10.4_

  - [x] 5.3 创建 `composables/useG1Classification.ts`（G1-9分类适当性2区段）
    - 2区段Tab（SPPI测试11列 / 业务模式判定10列）
    - SPPI通过/不通过下拉 + 最终分类下拉(FVTPL/FVOCI/AC)
    - _Requirements: 11.1~11.6_

  - [x] 5.4 创建 `composables/useG1Inventory.ts`（G1-4结存表2区段）
    - 21列→2区段Tab（基础+期初增减 / 期末+损益）
    - 期末数量/成本/未实现损益公式
    - _Requirements: 7.1~7.7_

  - [x] 5.5 创建 `composables/useG1IncomeCalc.ts`（G1-5收益测算2区段）
    - 2区段Tab（投资收益测算9列 / 处置损益测算9列）
    - 应收金额=持有×每股股利 / 处置损益=成交-成本 / 净损益=处置-手续费
    - _Requirements: 8.1~8.6_

  - [x] 5.6 创建 inspection/ composable（G1-11~G1-14）
    - `useG1SecuritiesCount.ts`：盘点差异=盘点-账面, 差异>0橙色
    - `useG1CountReconciliation.ts`：倒轧=监盘日+增加-减少, 18列→2区段
    - `useG1VoucherCheck.ts`：48行检查表+抽凭引擎集成
    - `useG1DerivativeCheck.ts`：衍生工具类型下拉+合规结论
    - _Requirements: 12.1~12.12_

- [x] 6. 实现 Vue子组件
  - [x] 6.1 创建 `core/G1TabAdjudication.vue`（G1-1审定表多层结构）
    - 调用useG1Adjudication
    - 多层展开/折叠（品种→子层）+ el-table
    - 小计加粗 + 差异红色 + EventBus发布 + GtIndexChip
    - _Requirements: 3.1~3.11_

  - [x] 6.2 创建 `core/G1TabDetail.vue`（G1-2明细表 35列→5区段Tab）
    - 调用useG1Detail
    - 5区段Tab切换 + 行同步 + 分类小计+总计
    - 动态行增删 + 导入导出
    - _Requirements: 5.1~5.11_

  - [x] 6.3 创建 `core/G1TabAdjustment.vue` + 附注Vue组件
    - G1-3调整分录（借贷平衡校验）
    - G1TabDisclosureListed.vue（198行虚拟滚动 + EventBus subscribe/publish）
    - G1TabDisclosureSOE.vue
    - _Requirements: 6.1~6.4, 4.1~4.5_

  - [x] 6.4 创建 `valuation/G1TabFairValueTest.vue`（G1-6公允价值Level1-3）
    - 调用useG1FairValueTest
    - Level下拉→条件启用/禁用列（其他Level列灰色禁用）
    - Level1公式列(市值+差异)虚线+tooltip
    - 差异>1%阈值橙色 + 底部统计
    - 审计结论textarea(AI) + 编制提示details
    - _Requirements: 9.1~9.10_

  - [x] 6.5 创建 `valuation/G1TabLevel3Reconciliation.vue` + `classification/` 3个Vue组件
    - G1-7第三层次调节（期末=期初+增加-减少+变动）
    - G1-8业务模式分析（叙述式textarea）
    - G1-9分类适当性（21列→2区段Tab：SPPI/业务模式）
    - G1-10合同现金流(80行叙述式，虚拟滚动)
    - _Requirements: 10.1~10.4, 11.1~11.6_

  - [x] 6.6 创建 `inspection/G1TabInventory.vue` + `G1TabIncomeCalc.vue`
    - G1-4结存表（21列→2区段Tab + 品种分组小计）
    - G1-5收益测算（18列→2区段Tab + 合计+AI结论）
    - _Requirements: 7.1~7.7, 8.1~8.6_

  - [x] 6.7 创建 `inspection/G1TabSecuritiesCount.vue` + `G1TabCountReconciliation.vue`
    - G1-11有价证券监盘（盘点差异公式+橙色高亮）
    - G1-12盘点倒轧（18列→2区段 + 倒轧=监盘日+增加-减少）
    - _Requirements: 12.1~12.6_

  - [x] 6.8 创建 `inspection/G1TabVoucherCheck.vue` + `G1TabDerivativeCheck.vue`
    - G1-13检查表（48行 + GtVoucherSamplingEngine抽凭 + 📎OCR + 样本来源tooltip）
    - G1-14衍生金融工具核查（类型下拉/会计处理下拉/合规结论）
    - _Requirements: 12.7~12.12_

- [x] 7. Checkpoint - 公式引擎+组件验证
  - Ensure all PBT tests pass (P1~P12), ask the user if questions arise.

- [x] 8. 实现后端 + 导入导出 + AI
  - [x] 8.1 创建后端3个py文件
    - `_g1_trading_financial_assets.py`：render策略函数 + 注册RENDERER_DISPATCH['g1-trading-financial-assets']
    - `_g1_trading_financial_assets_import_export.py`：3端点（export-template/export-data/import-data）+ 10张动态行表格支持
    - `_g1_trading_financial_assets_ai.py`：8个AI section端点 + 30秒超时
    - _Requirements: 1.3, 15.1~15.4_

  - [x] 8.2 创建 `composables/useG1ImportExport.ts` + `composables/useG1DualMode.ts`
    - useG1ImportExport：el-dropdown"导入导出▾" + axios三端点 + 10张表参数
    - useG1DualMode：模式状态(html/onlyoffice) + 切换逻辑 + localStorage持久化
    - _Requirements: 15.1~15.4_

- [x] 9. 跨模块联动集成
  - [x] 9.1 版本链集成
    - [x] 主入口集成useVersionTrail（autoSnapshot on save + "版本历史"按钮 + GtWpVersionTrail drawer）
    - provide('openReviewDialog', openReviewDialog)供子组件inject
    - _Requirements: 14.1, 14.5_

  - [x] 9.2 附注EventBus集成
    - 附注披露组件subscribe `substantive:adjudicated`(accountCode='1501')自动刷新
    - publish `disclosure:note-text-updated` 联动附注模块
    - _Requirements: 4.3, 4.4, 14.3_

  - [x] 9.3 抽凭引擎 + OCR集成
    - G1-13: GtVoucherSamplingEngine dialog集成（科目1501，样本填入检查表行+来源tooltip）
    - G1-13: 📎OCR列POST contract-ocr→凭证信息识别→确认弹窗→merge
    - _Requirements: 12.7~12.9, 14.2, 14.4_

- [x] 10. 集成测试与验收
  - [x] 10.1 编写集成测试
    - sheetName分发正确性（16个sheet→对应组件，含子目录路由）
    - 借方余额公式链（期初+借方-贷方=期末→+AJE+RJE=审定）
    - G1-2五区段Tab行同步+公式链
    - G1-6 Level条件启用逻辑（Level切换→启用/禁用列）
    - G1-6 Level1差异公式（持仓×报价-账面）
    - G1-11→G1-12监盘→倒轧数据传递
    - G1-13抽凭引擎样本填入+来源tooltip
    - EventBus(substantive:adjudicated)跨组件传递
    - 导入导出round-trip(10张表)
    - 虚拟滚动（198行附注/80行合同现金流）
    - 多层审定表展开/折叠
    - _Requirements: 全部_
