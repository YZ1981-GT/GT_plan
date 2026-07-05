# Implementation Plan: N4 税金及附加底稿专属HTML精美组件

## Overview

N4税金及附加底稿专属组件`n4-taxes-and-surcharges`。N税费循环损益类底稿（9 sheet/1 xlsx/~110+公式，其中O2A原底稿标记skip）。

主入口 GtN4TaxesAndSurcharges.vue（sheetName v-if，defineAsyncComponent lazy）+ 6个子组件 + 8个composable + 后端3个py文件。

科目：6403税金及附加（**损益类**！取本期发生额，从tb_ledger）
公式特征：审定=未审+AJE+RJE；损益类发生额=借方发生-贷方发生；各税种=计税依据×税率（与N2同源）；费用确认=N2计提额。

## Tasks

### Phase 0: 双源输入验证

- [ ] 0.1 openpyxl脚本读取N4税金及附加.xlsx全部9 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 确认：审定表N4-1(24×14,83公式)/明细表N4-2(34×11,18公式)/附注上市(18×12)/附注国企(17×11)/审计程序表N4A/调整分录N4-3
  - 标记skip：O2A原底稿
  - 产出：n4_structure_summary.json（权威列头+公式清单）
  - _Requirements: 双源输入流程_

- [ ] 0.2 N税费循环底稿模板库md交叉验证
  - 核对：损益类取数规则(tb_ledger发生额)/多税种测算(与N2同源)/N2计提对应/A利润表勾稽
  - 冲突解决：列名以xlsx为准，联动方向以md为准
  - 产出：n4_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - wp_code_overrides: N4/N4-1~N4-3/N4A → 'n4-taxes-and-surcharges'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry注册
  - 创建 GtN4TaxesAndSurcharges.vue 骨架（sheetName prop v-if分发 + defineAsyncComponent lazy + selfLoad）
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8, 1.9, 1.11_

- [ ] 1.2 编写注册契约测试
  - htmlRendererRegistry.spec.ts / VALID_COMPONENT_TYPES / wp_code_overrides / RENDERER_DISPATCH
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+税务引擎+PBT

- [ ] 2.1 创建 `composables/useN4FormulaEngine.ts`（损益类！）
  - calcAuditedAmount(u,a,r)=u+a+r
  - calcPeriodAmount(debitOccur,creditOccur)=借方发生-贷方发生（损益类本期发生额，从tb_ledger）
  - calcSubtotal / calcYoyChange(current,prior)=(本期-上期)/上期
  - _Requirements: 1.5, 2.3, 2.4, 7.1-7.4_

- [ ] 2.2 创建 `composables/useN4MultiTaxEngine.ts`（多税种测算引擎，与N2同源纯函数）
  - calcSurtax(vat,consumptionTax,rate)=(增值税+消费税)×税率
  - calcPropertyTaxByValue(originalValue,deductRate)=原值×(1-扣除比例)×1.2%
  - calcStampTax(taxableAmount,rate)=计税金额×税率
  - calcLandUseTax(area,unitTax)=占地面积×单位税额
  - _Requirements: 4.1-4.5_

- [ ]* 2.3 编写 Property P1 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: n4-taxes-and-surcharges, Property P1: 审定数公式链**

- [ ]* 2.4 编写 Property P2 PBT：损益类本期发生额（借方发生-贷方发生）
  - 生成器：fc.float({min:0,max:1e9}) × 2 (debitOccur, creditOccur)
  - 断言：calcPeriodAmount(d, c) === d - c
  - **Feature: n4-taxes-and-surcharges, Property P2: 损益类本期发生额（发生额！）**

- [ ]* 2.5 编写 Property P3 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: n4-taxes-and-surcharges, Property P3: 合计行恒等**

- [ ]* 2.6 编写 Property P4 PBT：城建税及附加
  - 生成器：vat,ct∈R≥0, rate∈{0.07,0.05,0.01,0.03,0.02}
  - 断言：calcSurtax(vat, ct, rate) === (vat + ct) × rate
  - **Feature: n4-taxes-and-surcharges, Property P4: 城建税及附加=(增值税+消费税)×税率**

- [ ]* 2.7 编写 Property P5 PBT：房产税从价
  - 生成器：ov∈R≥0, dr∈[0,0.3]
  - 断言：calcPropertyTaxByValue(ov, dr) === ov × (1-dr) × 0.012
  - **Feature: n4-taxes-and-surcharges, Property P5: 房产税从价=原值×(1-扣除比例)×1.2%**

- [ ]* 2.8 编写 Property P6 PBT：印花税
  - 生成器：amt∈R≥0, rate∈[0,0.001]
  - 断言：calcStampTax(amt, rate) === amt × rate
  - **Feature: n4-taxes-and-surcharges, Property P6: 印花税=计税金额×税率**

### Phase 3: Composable层

- [ ] 3.1 创建 useN4FormData.ts
  - selfLoad + checklist_responses + writebackTB(**本期发生额**，科目6403损益类，从tb_ledger)
  - _Requirements: 1.9, 1.10, 2.7, 7.1-7.4_

- [ ] 3.2 创建 useN4CrossSheet.ts
  - adjudicationVsDetail / n4VsN2Accrual(费用确认vs计提) / toIncomeStatement(供A利润表)
  - _Requirements: 2.5, 2.6, 6.1-6.5_

- [ ] 3.3 创建 useN4DualMode.ts + useN4ImportExport.ts + sheet-specific composables
  - 双模式 + 导入导出三级 + useN4Adjudication / useN4Detail
  - _Requirements: 3.4, 2~5 全部_

### Phase 4: Vue子组件

- [ ] 4.1 创建 N4TabIndex.vue 底稿目录
  - 9行（skip标记O2A）+进度条+各税种统计仪表板+联动状态
  - _Requirements: 1.2, 1.11_

- [ ] 4.2 创建 N4TabAdjudication.vue 审定表N4-1
  - 83公式+损益类发生额取数+税种分行+N4-2交叉验证+N2计提对应+TB回写+A利润表勾稽
  - _Requirements: 2.1-2.8_

- [ ] 4.3 创建 N4TabDetail.vue 明细表N4-2
  - 11列18公式+计税依据×税率+同比变动+N2计提差异标红+动态行+统计摘要+导入导出
  - _Requirements: 3.1-3.6_

- [ ] 4.4 创建 N4TabAdjustment.vue 调整分录N4-3
  - 借贷平衡+EventBus+双向同步N4-1
  - _Requirements: 5.1_

- [ ] 4.5 创建 N4TabDisclosureListed/Soe.vue
  - 附注上市(18×12)/国企(17×11)+各税种本期上期发生额+同比变动说明+subscribe刷新
  - _Requirements: 5.2-5.4_

### Phase 5: 后端

- [ ] 5.1 创建 n4_taxes_and_surcharges_renderer.py
  - RENDERER_DISPATCH注册 + **损益类取数逻辑**（本期发生额！6403，从tb_ledger）
  - _Requirements: 1.6, 7.2_

- [ ] 5.2 创建 n4_taxes_and_surcharges.py 路由
  - 导出模板/导出数据/导入数据（axios+Authorization）
  - _Requirements: 3.4_

- [ ] 5.3 创建 n4_taxes_and_surcharges_service.py
  - 损益类取数（tb_ledger本期发生额，与H10/I6同款）+ 多税种测算 + N2计提对应 + 跨底稿合计
  - _Requirements: 4.1-4.5, 6.1-6.5, 7.1-7.4_

### Phase 6: 集成

- [ ] 6.1 EventBus集成
  - publish 'substantive:adjudicated'（N4-1→附注）
  - publish 'adjustment:created'（N4-3→A13）
  - publish 'expense:taxes-surcharges-updated'（→A类利润表）
  - subscribe 'tax-accrual:updated'（N2计提额）+ 'disclosure:refresh'
  - _Requirements: 5.1, 5.3, 6.1, 6.4_

- [ ] 6.2 跨底稿GtIndexChip
  - N4-1税金及附加项 ↔ N2-1应交税费对应税种行
  - N4-1审定发生额 → A类利润表税金及附加行
  - _Requirements: 6.2, 6.3_

- [ ] 6.3 六大集成标准
  - 版本链useVersionTrail + 附注EventBus + 复核对话provide/inject + 导入导出
  - _Requirements: 1.5, 5.1-5.4_

### Phase 7: 测试

- [ ] 7.1 单元测试：useN4FormulaEngine + useN4MultiTaxEngine
  - 损益类方向(本期发生额) + 各税种计税依据×税率 + 同比变动 + 边界(零值/大数/上期为0除零)
  - _Requirements: P1-P6_

- [ ] 7.2 集成测试：损益类取数+N2对应+跨底稿联动
  - 本期发生额取数正确性(tb_ledger) / 费用确认=N2计提额 / N4-1→N4-2 / N4→A利润表勾稽
  - _Requirements: 2.5-2.6, 6.1-6.5, 7.1-7.4_

- [ ] 7.3 Playwright E2E
  - 完整流程：打开N4→审定(验证损益类发生额取数)→明细(计税依据×税率+N2对应)→调整→附注→保存
  - _Requirements: 全部_

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册]
    P1 --> P2[Phase 2: 公式引擎+多税种引擎+PBT]
    P2 --> P3[Phase 3: Composable]
    P3 --> P4[Phase 4: Vue组件]
    P1 --> P5[Phase 5: 后端(损益类发生额取数)]
    P4 --> P6[Phase 6: 集成+N2对应+A利润表]
    P5 --> P6
    P6 --> P7[Phase 7: 测试]
```
