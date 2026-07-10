# Implementation Plan: N5 所得税费用底稿专属HTML精美组件

## Overview

N5所得税费用底稿专属组件`n5-income-tax-expense`。N税费循环最复杂底稿（15 sheet/1 xlsx/~95+公式，含82行当期计算表+107行纳税调整大表，其中N3A原底稿标记skip）。

主入口 GtN5IncomeTaxExpense.vue（sheetName v-if，defineAsyncComponent lazy）+ 13个子组件（core/calc/benefit三分组）+ 11个composable + 后端3个py文件。

科目：6801所得税费用（**损益类**！取本期发生额，从tb_ledger）
公式特征：审定=未审+AJE+RJE；损益类发生额；应纳税所得额=会计利润±纳税调整；当期所得税=应纳税所得额×税率；所得税费用=当期+递延；递延=递延税负债增-递延税资产增；研发加计=研发费用×加计比例。

## Tasks

### Phase 0: 双源输入验证

- [x] 0.1 openpyxl脚本读取N5所得税费用.xlsx全部15 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 确认：审定表N5-1(28×14,36公式)/明细表N5-2(38×10,8公式)/当期计算表N5-4(82×7)/纳税调整N5-5(107×8)/税收优惠N5-6(54×6,10公式)/研发加计N5-6-1(43×7,17公式)/高新认定N5-6-2(18×13)/财产损失N5-7(15×7,12公式)/递延核对N5-8(44×10,12公式)/附注上市(29×12)/附注国企(32×255)
  - 标记skip：N3A原底稿
  - 产出：n5_structure_summary.json（权威列头+公式清单）
  - _Requirements: 双源输入流程_

- [x] 0.2 N税费循环底稿模板库md交叉验证
  - 核对：损益类取数(tb_ledger)/当期所得税计算链/纳税调整分类/递延核对(N1/N3)/研发加计(I6/I2)/高新认定/会计利润(A利润表)
  - 冲突解决：列名以xlsx为准，联动方向以md为准
  - 产出：n5_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: N5/N5-1~N5-8/N5-6-1/N5-6-2/N5A → 'n5-income-tax-expense'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry注册
  - 创建 GtN5IncomeTaxExpense.vue 骨架（sheetName prop v-if分发 + defineAsyncComponent lazy + selfLoad）
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8, 1.9, 1.11_

- [x] 1.2 编写注册契约测试
  - htmlRendererRegistry.spec.ts / VALID_COMPONENT_TYPES / wp_code_overrides / RENDERER_DISPATCH
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+所得税引擎+纳税调整引擎+PBT

- [x] 2.1 创建 `composables/useN5FormulaEngine.ts`（损益类！）
  - calcAuditedAmount(u,a,r)=u+a+r
  - calcPeriodAmount(debitOccur,creditOccur)=借方发生-贷方发生（损益类本期发生额，从tb_ledger）
  - calcSubtotal / calcEffectiveTaxRate(incomeTax,accountingProfit)=所得税费用/会计利润
  - _Requirements: 1.5, 2.3, 2.4, 12.1-12.4_

- [x] 2.2 创建 `composables/useN5IncomeTaxEngine.ts`（核心所得税引擎，纯函数）
  - calcTaxableIncome(accountingProfit,addBack,deduct)=会计利润+调增-调减
  - calcCurrentTax(taxableIncome,taxRate)=应纳税所得额×税率
  - calcIncomeTaxExpense(currentTax,deferredTax)=当期+递延
  - calcDeferredTaxExpense(liabilityIncrease,assetIncrease)=递延税负债增-递延税资产增
  - calcRdSuperDeduction(rdExpense,superRate)=研发费用×加计比例
  - _Requirements: 3.2, 3.3, 5.2, 8.2, 13.1-13.4, 13.6_

- [x] 2.3 创建 `composables/useN5TaxAdjustmentEngine.ts`（纳税调整引擎，纯函数）
  - calcNetAdjustment(addBacks[],deducts[])=Σ调增-Σ调减
  - calcPropertyLossAdjustment(bookLoss,deductibleLoss)=账面损失-税前扣除额
  - _Requirements: 4.3, 7.2, 13.5_

- [x]* 2.4 编写 Property P1 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: n5-income-tax-expense, Property P1: 审定数公式链**

- [x]* 2.5 编写 Property P2 PBT：损益类本期发生额（发生额！）
  - 生成器：fc.float({min:0,max:1e9}) × 2 (debitOccur, creditOccur)
  - 断言：calcPeriodAmount(d, c) === d - c
  - **Feature: n5-income-tax-expense, Property P2: 损益类本期发生额（发生额！）**

- [x]* 2.6 编写 Property P3 PBT：应纳税所得额（会计利润±纳税调整）
  - 生成器：ap∈R, addBack∈R≥0, deduct∈R≥0
  - 断言：calcTaxableIncome(ap, addBack, deduct) === ap + addBack - deduct
  - **Feature: n5-income-tax-expense, Property P3: 应纳税所得额=会计利润+调增-调减**

- [x]* 2.7 编写 Property P4 PBT：当期所得税（应纳税所得额×税率）
  - 生成器：ti∈R≥0, rate∈{0.15,0.25}
  - 断言：calcCurrentTax(ti, rate) === ti × rate
  - **Feature: n5-income-tax-expense, Property P4: 当期所得税=应纳税所得额×税率**

- [x]* 2.8 编写 Property P5 PBT：所得税费用（当期+递延）
  - 断言：calcIncomeTaxExpense(cur, def) === cur + def
  - **Feature: n5-income-tax-expense, Property P5: 所得税费用=当期+递延**

- [x]* 2.9 编写 Property P6 PBT：递延所得税费用（负债增-资产增）
  - 断言：calcDeferredTaxExpense(li, ai) === li - ai
  - **Feature: n5-income-tax-expense, Property P6: 递延所得税费用=递延税负债增-递延税资产增**

- [x]* 2.10 编写 Property P7 PBT：研发费用加计扣除
  - 生成器：rd∈R≥0, rate∈{1.0,0.75,0.5}
  - 断言：calcRdSuperDeduction(rd, rate) === rd × rate
  - **Feature: n5-income-tax-expense, Property P7: 研发费用加计扣除=研发费用×加计比例**

- [x]* 2.11 编写 Property P8 PBT：纳税调整净额
  - 生成器：addBacks/deducts为fc.array(fc.float)
  - 断言：calcNetAdjustment(adds, deds) === Σadds - Σdeds
  - **Feature: n5-income-tax-expense, Property P8: 纳税调整净额=Σ调增-Σ调减**

- [x]* 2.12 编写 Property P9 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: n5-income-tax-expense, Property P9: 合计行恒等**

- [x]* 2.13 编写 Property P10 PBT：财产损失纳税调整额
  - 断言：calcPropertyLossAdjustment(bl, dl) === bl - dl
  - **Feature: n5-income-tax-expense, Property P10: 财产损失纳税调整额=账面损失-税前扣除额**

### Phase 3: Composable层

- [x] 3.1 创建 useN5FormData.ts
  - selfLoad + checklist_responses + writebackTB(**本期发生额**，科目6801损益类，从tb_ledger)
  - _Requirements: 1.9, 1.10, 2.7, 12.1-12.4_

- [x] 3.2 创建 useN5CrossSheet.ts
  - adjudicationVsCalc / deferredReconcile(N1/N3) / rdFromI6I2 / profitFromIncomeStatement(A) / effectiveTaxRate
  - _Requirements: 2.6, 3.4-3.6, 5.3, 8.3-8.4, 11.1-11.4_

- [x] 3.3 创建 useN5DualMode.ts + useN5ImportExport.ts
  - 双模式 + 导入导出三级（纳税调整明细分sheet导出）
  - _Requirements: 4.6_

- [x] 3.4 创建 sheet-specific composables
  - useN5CurrentTaxCalc / useN5TaxAdjustment / useN5RdSuperDeduction / useN5DeferredReconcile
  - _Requirements: 3~8 全部_

### Phase 4: Vue子组件（core）

- [x] 4.1 创建 N5TabIndex.vue 底稿目录
  - 15行（skip标记N3A）+进度条+纳税调整仪表板+有效税率+联动状态
  - _Requirements: 1.2, 1.11_

- [x] 4.2 创建 N5TabAdjudication.vue 审定表N5-1
  - 36公式+损益类发生额取数+当期/递延/合计分行+N5-4/N5-8取数+TB回写+有效税率
  - _Requirements: 2.1-2.8_

- [x] 4.3 创建 N5TabDetail.vue 明细表N5-2
  - 10列8公式+当期/递延分项+合计与N5-1交叉验证+动态行+导入导出
  - _Requirements: 9.1-9.2_

- [x] 4.4 创建 N5TabAdjustment.vue 调整分录N5-3
  - 借贷平衡+EventBus+双向同步N5-1
  - _Requirements: 9.3_

- [x] 4.5 创建 N5TabDisclosureListed/Soe.vue
  - 附注上市(29×12)/国企(32×255)+所得税费用与会计利润调节表+有效税率分析+subscribe刷新
  - _Requirements: 10.1-10.3_

### Phase 4b: Vue子组件（calc，核心计算）

- [x] 4.6 创建 N5TabCurrentTaxCalc.vue 当期所得税计算表N5-4（核心）
  - 82×7+计算链(会计利润→±调整→应纳税所得额→×税率→减免→当期所得税)+A利润表联动+N5-5/N5-6/N5-6-1取数+回填N5-1
  - _Requirements: 3.1-3.7_

- [x] 4.7 创建 N5TabTaxAdjustment.vue 纳税调整明细表N5-5（107行大表）
  - 107×8+**虚拟滚动**+调增/调减分类小计+净额回填N5-4+研发加计联动N5-6-1+动态行+分sheet导入导出
  - _Requirements: 4.1-4.7_

- [x] 4.8 创建 N5TabDeferredReconcile.vue 递延所得税费用核对表N5-8
  - 44×10+12公式+递延税资产/负债期初期末本期变动+subscribe N1/N3+递延所得税费用=负债增-资产增+回填N5-1
  - _Requirements: 8.1-8.5_

### Phase 4c: Vue子组件（benefit，优惠）

- [x] 4.9 创建 N5TabTaxBenefit.vue 税收优惠明细表N5-6
  - 54×6+10公式+各项优惠汇总+优惠税率减免+减免税额回填N5-4+高新认定联动
  - _Requirements: 6.1-6.3_

- [x] 4.10 创建 N5TabRdSuperDeduction.vue 研发加计扣除表N5-6-1
  - 43×7+17公式+研发费用六要素+加计比例+I6/I2联动(费用化+资本化)+加计扣除额回填N5-5调减
  - _Requirements: 5.1-5.5_

- [x] 4.11 创建 N5TabHighTechCheck.vue 高新认定检查表N5-6-2
  - 18×13+逐条认定条件检查+不满足红色警告+认定结论联动N5-6优惠税率
  - _Requirements: 6.4-6.6_

- [x] 4.12 创建 N5TabPropertyLoss.vue 财产损失明细表N5-7
  - 15×7+12公式+账面损失/核准扣除/待核准+纳税调整额=账面-税前扣除+未核准调增+回填N5-5
  - _Requirements: 7.1-7.4_

### Phase 5: 后端

- [x] 5.1 创建 n5_income_tax_expense_renderer.py
  - RENDERER_DISPATCH注册 + **损益类取数逻辑**（本期发生额！6801，从tb_ledger）
  - _Requirements: 1.6, 12.2_

- [x] 5.2 创建 n5_income_tax_expense.py 路由
  - 导出模板/导出数据/导入数据（axios+Authorization，纳税调整分sheet）
  - _Requirements: 4.6_

- [x] 5.3 创建 n5_income_tax_expense_service.py
  - 损益类取数（tb_ledger本期发生额）+ 当期所得税计算 + 纳税调整汇总 + 递延核对(N1/N3) + 研发加计(I6/I2) + 跨底稿合计
  - _Requirements: 3~8, 11.1-11.4, 12.1-12.4, 13.1-13.6_

### Phase 6: 集成

- [x] 6.1 EventBus集成
  - publish 'substantive:adjudicated'（N5-1→附注）
  - publish 'adjustment:created'（N5-3→A13）
  - publish 'income-tax:updated'（→A类利润表）
  - subscribe 'deferred-tax:asset-updated'(N1) + 'deferred-tax:liability-updated'(N3) + 'disclosure:refresh'
  - _Requirements: 8.3, 9.3, 10.2, 11.1, 11.3_

- [x] 6.2 跨底稿GtIndexChip
  - N5-8 ↔ N1-1/N3-1（递延核对）
  - N5-4 ↔ A利润表（会计利润）
  - N5-6-1 ↔ I6研发费用/I2开发支出
  - _Requirements: 11.2_

- [x] 6.3 六大集成标准
  - ✓ 版本链useVersionTrail（useWorkpaperVersionToolbar + scheduleAutoSnapshot provide）
  - ✓ 附注EventBus（subscribe 'substantive:adjudicated' in disclosure components）
  - ✓ 复核对话provide/inject（provide('openReviewDialog') in main entry, inject in all sub-components）
  - ○ 抽凭引擎——N/A（N5是计算/核对类底稿，非凭证检查类，无需抽凭）
  - ✓ 导入导出（useN5ImportExport in N5TabDetail/N5TabTaxAdjustment）
  - ○ 行级OCR——N/A（N5是计算密集型底稿，数据来源为公式计算和跨底稿联动，无纸质凭证需OCR）
  - _Requirements: 1.5, 9.3, 10.2_

### Phase 7: 测试

- [x] 7.1 单元测试：useN5FormulaEngine + useN5IncomeTaxEngine + useN5TaxAdjustmentEngine
  - 损益类方向(发生额) + 应纳税所得额 + 当期所得税 + 所得税费用=当期+递延 + 递延=负债增-资产增 + 研发加计 + 纳税调整净额 + 边界(亏损/零利润除零/大数)
  - _Requirements: P1-P10_

- [x] 7.2 集成测试：损益类取数+计算链+跨底稿联动
  - 本期发生额取数(tb_ledger) / 会计利润(A)→N5-4→应纳税所得额→当期所得税 / N5-5调整净额回填 / N5-8递延核对(N1/N3一致) / N5-6-1研发加计(I6/I2) / 所得税费用=当期+递延
  - _Requirements: 3.1-3.7, 8.1-8.5, 11.1-11.4, 12.1-12.4_

- [x] 7.3 Playwright E2E
  - 完整流程：打开N5→纳税调整107行(虚拟滚动)→研发加计→高新认定→财产损失→当期所得税计算→递延核对→审定(当期+递延)→附注→保存
  - _Requirements: 全部_

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册]
    P1 --> P2[Phase 2: 公式引擎+所得税引擎+纳税调整引擎+PBT]
    P2 --> P3[Phase 3: Composable]
    P3 --> P4[Phase 4: Vue组件 core]
    P3 --> P4b[Phase 4b: Vue组件 calc计算]
    P3 --> P4c[Phase 4c: Vue组件 benefit优惠]
    P1 --> P5[Phase 5: 后端(损益类发生额取数)]
    P4 --> P6[Phase 6: 集成+N1/N3/I6/I2/A联动]
    P4b --> P6
    P4c --> P6
    P5 --> P6
    P6 --> P7[Phase 7: 测试]
```
