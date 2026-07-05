# Implementation Plan: K3 其他应付款底稿专属HTML精美组件

## Overview

K3其他应付款底稿专属组件`k3-other-payables`。K循环负债类底稿（11有效sheet/1 xlsx/~80+公式）。

主入口 GtK3OtherPayables.vue（sheetName v-if分发，defineAsyncComponent lazy）+ 10个子组件 + composable分层 + 后端3个py文件。

科目：2241其他应付款（**贷方/负债类**）
公式特征：负债类期末=期初+贷方-借方（与资产类相反）；审定=未审+AJE+RJE；完整性认定+反向截止

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册+契约]
    P1 --> P2[Phase 2: 公式引擎(负债类)+PBT]
    P2 --> P3[Phase 3: Composable层]
    P3 --> P4[Phase 4: Vue子组件]
    P1 --> P5[Phase 5: 后端]
    P4 --> P6[Phase 6: 集成联动]
    P5 --> P6
    P6 --> P7[Phase 7: 测试验收]
```

## Tasks

### Phase 0: 双源输入验证

- [ ] 0.1 openpyxl脚本读取K3其他应付款.xlsx全部11 sheet
  - 产出：k3_structure_summary.json（确认K3-1 50公式/K3-2 19公式/K3-4 8公式）
  - _Requirements: 双源输入流程_

- [ ] 0.2 K其他应付款循环底稿模板库md交叉验证
  - 核对：负债类方向/完整性认定/长期挂账/关联方
  - 产出：k3_conflict_resolution.md
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - wp_code_overrides: K3/K3-1~K3-7/K3A → 'k3-other-payables'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry注册
  - 创建 GtK3OtherPayables.vue 骨架（sheetName v-if + selfLoad）
  - _Requirements: 1.1-1.10_

- [ ] 1.2 编写注册契约测试
  - htmlRendererRegistry / VALID_COMPONENT_TYPES / wp_code_overrides / RENDERER_DISPATCH
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎（负债类）+PBT

- [ ] 2.1 创建 useK3FormulaEngine.ts
  - calcAuditedAmount / calcLiabilityEndBalance / calcTriangleReconciliation / calcProportion / calcSubtotal / calcChangeRate
  - _Requirements: 2.2-2.3, 7.1, 9.1-9.6_

- [ ]* 2.2 编写 Property CP-K3-01 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: k3-other-payables, Property CP-K3-01: 审定数公式链**

- [ ]* 2.3 编写 Property CP-K3-02 PBT：负债类期末余额
  - 断言：calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
  - **Feature: k3-other-payables, Property CP-K3-02: 负债类期末=期初+贷-借**

- [ ]* 2.4 编写 Property CP-K3-03 PBT：三角勾稽恒等式
  - 断言：calcTriangleReconciliation(b, inc, dec, b+inc-dec) === 0
  - **Feature: k3-other-payables, Property CP-K3-03: 三角勾稽恒等式**

- [ ]* 2.5 编写 Property CP-K3-04 PBT：账龄合计恒等
  - 断言：calcSubtotal(agingBuckets) === ΣagingBuckets
  - **Feature: k3-other-payables, Property CP-K3-04: 账龄合计恒等**

- [ ]* 2.6 编写 Property CP-K3-05 PBT：占比公式
  - 生成器：item∈R, total>0
  - 断言：calcProportion(item, total) === item/total
  - **Feature: k3-other-payables, Property CP-K3-05: 占比=单项/合计**

- [ ]* 2.7 编写 Property CP-K3-06 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: k3-other-payables, Property CP-K3-06: 合计行恒等**

### Phase 3: Composable层

- [ ] 3.1 创建 useK3FormData.ts（selfLoad + writebackTB 2241 负债口径）
  - _Requirements: 1.9, 1.10, 2.6_

- [ ] 3.2 创建 useK3CrossSheet.ts（adjudicationVsDetail / longOutstandingVsDetail）
  - _Requirements: 2.5, 3.3, 4.4, 5.4_

- [ ] 3.3 创建 useK3DualMode.ts + useK3ImportExport.ts
  - _Requirements: 3.4, 8.2_

- [ ] 3.4 创建 sheet-specific composables
  - useK3Adjudication / useK3Detail / useK3LargeAmount / useK3Checks
  - _Requirements: 2~8 全部_

### Phase 4: Vue子组件

- [ ] 4.1 创建 K3TabIndex.vue 底稿目录
  - _Requirements: 1.2_

- [ ] 4.2 创建 K3TabAdjudication.vue 审定表K3-1（负债类50公式+三角勾稽+TB回写+完整性说明）
  - _Requirements: 2.1-2.7, 7.3_

- [ ] 4.3 创建 K3TabDetail.vue 明细表K3-2（27列3区段+账龄+疑似未入账标记+动态行+3年以上高亮+导入导出）
  - _Requirements: 3.1-3.6, 7.4_

- [ ] 4.4 创建 K3TabLargeAmount.vue K3-4 + K3TabLongOutstanding.vue K3-5
  - 大额分析+长期挂账检查+转营业外提示+抽凭
  - _Requirements: 4.1-4.4, 5.1-5.4_

- [ ] 4.5 创建 K3TabRelatedParty.vue K3-6 + K3TabPayableCheck.vue K3-7（含反向截止）
  - 关联方+综合检查+反向截止测试+抽凭+OCR+不合规摘要
  - _Requirements: 6.1-6.5, 7.2_

- [ ] 4.6 创建 K3TabAdjustment.vue + 附注（K3TabDisclosureListed/Soe.vue）
  - 调整分录借贷平衡+EventBus / 附注双版本+自动取数
  - _Requirements: 8.1-8.2_

### Phase 5: 后端

- [ ] 5.1 创建 _k3_other_payables.py render策略 + RENDERER_DISPATCH注册（负债口径）
  - _Requirements: 1.6, 7.1_

- [ ] 5.2 创建 _k3_import_export.py 导入导出3端点
  - _Requirements: 3.4, 8.2_

- [ ] 5.3 创建 _k3_ai_generate.py AI生成 + 更新 k3-other-payables.yaml
  - section: large-amount-eval / long-outstanding-eval / related-party-eval / overall-opinion
  - _Requirements: 6.1, 8.1_

### Phase 6: 集成联动

- [ ] 6.1 EventBus: TB回写(2241) + substantive:adjudicated → 附注
  - _Requirements: 2.6, 8.1_

- [ ] 6.2 EventBus: adjustment:created → A13 + 附注subscribe刷新 + 长期挂账转销联动K12
  - _Requirements: 8.2, 5.2_

- [ ] 6.3 抽凭引擎 + 行级OCR + GtIndexChip跳转 + 双模式OO
  - _Requirements: 4.4, 6.3_

### Phase 7: 测试验收

- [ ] 7.1 单元测试：useK3FormulaEngine（负债类方向 + 边界零值/大数）
  - _Requirements: CP-K3-01~06_

- [ ] 7.2 集成测试：负债类回写 + 长期挂账联动 + 账龄勾稽
  - _Requirements: 2.5, 2.6, 5.4_

- [ ] 7.3 Playwright E2E：打开K3→审定→明细账龄→大额→长期挂账→反向截止→保存
  - _Requirements: 全部_
