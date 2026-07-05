# Implementation Plan: N3 递延所得税负债底稿专属HTML精美组件

## Overview

N3递延所得税负债底稿专属组件`n3-deferred-tax-liabilities`。N税费循环负债类底稿（6 sheet/1 xlsx/~92+公式）。N3是N循环最简底稿。

主入口 GtN3DeferredTaxLiabilities.vue（sheetName v-if，defineAsyncComponent lazy）+ 5个子组件 + 8个composable + 后端3个py文件。

科目：2901递延所得税负债（**贷方/负债类**！取期末余额）
公式特征：审定=未审+AJE+RJE；负债类期末=期初+贷方-借方；递延所得税负债=应纳税暂时性差异×税率；与N1同源对应。

## Tasks

### Phase 0: 双源输入验证

- [ ] 0.1 openpyxl脚本读取N3递延所得税负债.xlsx全部6 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 确认：审定表N3-1(24×14,78公式)/明细表N3-2(31×14,14公式)/审计程序表N3A/调整分录N3-3/附注
  - 产出：n3_structure_summary.json（权威列头+公式清单）
  - _Requirements: 双源输入流程_

- [ ] 0.2 N税费循环底稿模板库md交叉验证
  - 核对：负债类取数规则/应纳税暂时性差异测算/N1对应/N5递延税费用核对/不确认特殊项
  - 冲突解决：列名以xlsx为准，联动方向以md为准
  - 产出：n3_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - wp_code_overrides: N3/N3-1~N3-3/N3A → 'n3-deferred-tax-liabilities'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry注册
  - 创建 GtN3DeferredTaxLiabilities.vue 骨架（sheetName prop v-if分发 + defineAsyncComponent lazy + selfLoad）
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8, 1.9, 1.11_

- [ ] 1.2 编写注册契约测试
  - htmlRendererRegistry.spec.ts / VALID_COMPONENT_TYPES / wp_code_overrides / RENDERER_DISPATCH
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+税务引擎+PBT

- [ ] 2.1 创建 `composables/useN3FormulaEngine.ts`（负债类！）
  - calcAuditedAmount(u,a,r)=u+a+r
  - calcLiabilityEndBalance(begin,credit,debit)=begin+credit-debit（负债类期末，2901贷方）
  - calcSubtotal / calcProportion
  - _Requirements: 1.5, 2.3, 2.4, 6.6_

- [ ] 2.2 创建 `composables/useN3DeferredTaxEngine.ts`（核心税务引擎，与N1同源）
  - calcTaxableTemporaryDifference(bookValue,taxBase)=账面-计税基础
  - calcDeferredTaxLiability(taxableDiff,taxRate)=应纳税暂时性差异×税率
  - calcWeightedAvgRate
  - _Requirements: 3.2, 4.1-4.3_

- [ ]* 2.3 编写 Property P1 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: n3-deferred-tax-liabilities, Property P1: 审定数公式链**

- [ ]* 2.4 编写 Property P2 PBT：负债类期末余额（期初+贷-借）
  - 生成器：fc.float({min:0,max:1e9}) × 3 (begin, credit, debit)
  - 断言：calcLiabilityEndBalance(b, c, d) === b + c - d
  - **Feature: n3-deferred-tax-liabilities, Property P2: 负债类期末余额（期初+贷-借）**

- [ ]* 2.5 编写 Property P3 PBT：应纳税暂时性差异
  - 断言：calcTaxableTemporaryDifference(bv, tb) === bv - tb
  - **Feature: n3-deferred-tax-liabilities, Property P3: 应纳税暂时性差异（账面-计税基础）**

- [ ]* 2.6 编写 Property P4 PBT：递延税负债=差异×税率
  - 生成器：diff∈R, rate∈[0,0.25]
  - 断言：calcDeferredTaxLiability(diff, rate) === diff × rate
  - **Feature: n3-deferred-tax-liabilities, Property P4: 递延税负债=应纳税差异×税率**

- [ ]* 2.7 编写 Property P5 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: n3-deferred-tax-liabilities, Property P5: 合计行恒等**

### Phase 3: Composable层

- [ ] 3.1 创建 useN3FormData.ts
  - selfLoad + checklist_responses + writebackTB(**期末余额**，科目2901贷方)
  - _Requirements: 1.9, 1.10, 2.6, 6.6_

- [ ] 3.2 创建 useN3CrossSheet.ts
  - adjudicationVsDetail / n3ToN1Correspondence / deferredTaxChange(供N5)
  - _Requirements: 2.5, 6.1-6.5_

- [ ] 3.3 创建 useN3DualMode.ts + useN3ImportExport.ts + sheet-specific composables
  - 双模式 + 导入导出三级 + useN3Adjudication / useN3Detail
  - _Requirements: 3.4, 2~5 全部_

### Phase 4: Vue子组件

- [ ] 4.1 创建 N3TabIndex.vue 底稿目录
  - 6行+进度条+联动状态
  - _Requirements: 1.2_

- [ ] 4.2 创建 N3TabAdjudication.vue 审定表N3-1
  - 78公式+负债类期末取数+应纳税差异项目分行+N3-2交叉验证+N1对应提示+TB回写
  - _Requirements: 2.1-2.8_

- [ ] 4.3 创建 N3TabDetail.vue 明细表N3-2
  - 14列14公式+应纳税差异×税率+动态行+统计摘要+导入导出
  - _Requirements: 3.1-3.6_

- [ ] 4.4 创建 N3TabAdjustment.vue 调整分录N3-3
  - 借贷平衡+EventBus+双向同步N3-1
  - _Requirements: 5.1_

- [ ] 4.5 创建 N3TabDisclosure.vue 附注披露
  - 上市/国企模板+应纳税差异明细+期初期末余额+subscribe刷新
  - _Requirements: 5.2-5.4_

### Phase 5: 后端

- [ ] 5.1 创建 n3_deferred_tax_liabilities_renderer.py
  - RENDERER_DISPATCH注册 + **负债类取数逻辑**（期末余额！2901贷方）
  - _Requirements: 1.6, 6.6_

- [ ] 5.2 创建 n3_deferred_tax_liabilities.py 路由
  - 导出模板/导出数据/导入数据（axios+Authorization）
  - _Requirements: 3.4_

- [ ] 5.3 创建 n3_deferred_tax_liabilities_service.py
  - 负债类取数（tb_balance期末余额，direction=贷）+ 递延税负债测算 + 跨底稿合计
  - _Requirements: 4.1-4.4, 6.6_

### Phase 6: 集成

- [ ] 6.1 EventBus集成
  - publish 'substantive:adjudicated'（N3-1→附注）
  - publish 'adjustment:created'（N3-3→A13）
  - publish 'deferred-tax:liability-updated'（→N5-8递延税费用核对）
  - subscribe 'disclosure:refresh'
  - _Requirements: 5.1, 5.3, 6.2, 6.4_

- [ ] 6.2 跨底稿GtIndexChip
  - N3-2 ↔ N1-4测算表（同源差异分列）
  - N3-1本期变动额 → N5-8递延税费用核对
  - _Requirements: 6.1, 6.3, 6.5_

- [ ] 6.3 六大集成标准
  - 版本链useVersionTrail + 附注EventBus + 复核对话provide/inject + 导入导出
  - _Requirements: 1.5, 5.1-5.4_

### Phase 7: 测试

- [ ] 7.1 单元测试：useN3FormulaEngine + useN3DeferredTaxEngine
  - 负债类方向(期初+贷-借) + 应纳税差异×税率 + 边界(零值/大数/税率边界)
  - _Requirements: P1-P5_

- [ ] 7.2 集成测试：负债类取数+跨底稿联动
  - 期末余额取数正确性(贷方) / N1-4负债部分→N3-2 / 本期变动→N5核对 / N1对应分列
  - _Requirements: 2.5, 6.1-6.6_

- [ ] 7.3 Playwright E2E
  - 完整流程：打开N3→审定(验证负债类取数)→明细(应纳税差异×税率)→调整→附注→保存
  - _Requirements: 全部_

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册]
    P1 --> P2[Phase 2: 公式引擎+递延税引擎+PBT]
    P2 --> P3[Phase 3: Composable]
    P3 --> P4[Phase 4: Vue组件]
    P1 --> P5[Phase 5: 后端(负债类取数)]
    P4 --> P6[Phase 6: 集成+N1/N5联动]
    P5 --> P6
    P6 --> P7[Phase 7: 测试]
```
