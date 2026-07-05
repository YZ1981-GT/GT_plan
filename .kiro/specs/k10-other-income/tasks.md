# Implementation Plan: K10 其他收益底稿专属HTML精美组件

## Overview

K10其他收益底稿专属组件`k10-other-income`。K循环损益类底稿（10有效sheet/1 xlsx/~90+公式）。

主入口 GtK10OtherIncome.vue（sheetName v-if分发，defineAsyncComponent lazy）+ 9个子组件 + composable分层（含补助核对引擎）+ 后端3个py文件。

科目：6117其他收益（**损益类！取发生额**，从tb_ledger取数，贷方=收益）
公式特征：审定=未审+AJE+RJE；收益类发生额=贷方发生-借方发生；补助核对联动K7

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册+契约]
    P1 --> P2[Phase 2: 公式引擎(损益类)+补助核对引擎+PBT]
    P2 --> P3[Phase 3: Composable层]
    P3 --> P4[Phase 4: Vue子组件]
    P1 --> P5[Phase 5: 后端(损益取数)]
    P4 --> P6[Phase 6: 集成联动]
    P5 --> P6
    P6 --> P7[Phase 7: 测试验收]
```

## Tasks

### Phase 0: 双源输入验证

- [ ] 0.1 openpyxl脚本读取K10其他收益.xlsx全部10 sheet
  - 产出：k10_structure_summary.json（确认K10-1 69公式/K10-2 11公式）
  - _Requirements: 双源输入流程_

- [ ] 0.2 K其他收益循环底稿模板库md交叉验证
  - 核对：损益类取数/政府补助分类/K7递延收益核对
  - 产出：k10_conflict_resolution.md
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - wp_code_overrides: K10/K10-1~K10-6/K10A → 'k10-other-income'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry + GtK10OtherIncome.vue骨架（sheetName v-if + selfLoad）
  - _Requirements: 1.1-1.10_

- [ ] 1.2 编写注册契约测试
  - _Requirements: 1.6-1.8_

### Phase 2: 公式引擎（损益类）+补助核对引擎+PBT

- [ ] 2.1 创建 useK10FormulaEngine.ts（损益类！）
  - calcAuditedAmount / calcIncomeStatementOccurrence(cr,dr)=cr-dr / calcYoYChange / calcSubtotal
  - _Requirements: 2.3-2.4, 6.1-6.3, 7.3-7.4, 7.6-7.7_

- [ ] 2.2 创建 useK10GrantReconcileEngine.ts
  - calcTotalRecognized / isConsistentWithK7
  - _Requirements: 4.2-4.3, 7.5_

- [ ]* 2.3 编写 Property CP-K10-01 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: k10-other-income, Property CP-K10-01: 审定数公式链**

- [ ]* 2.4 编写 Property CP-K10-02 PBT：损益类发生额（贷-借）
  - 生成器：creditOcc≥0, debitOcc≥0
  - 断言：calcIncomeStatementOccurrence(cr, dr) === cr - dr
  - **Feature: k10-other-income, Property CP-K10-02: 收益类发生额=贷方发生-借方发生**

- [ ]* 2.5 编写 Property CP-K10-03 PBT：合计计入
  - 断言：calcTotalRecognized(direct, deferred) === direct + deferred
  - **Feature: k10-other-income, Property CP-K10-03: 合计计入=直接+递延分摊**

- [ ]* 2.6 编写 Property CP-K10-04 PBT：与K7一致性判断
  - 断言：isConsistentWithK7(a, b) === (Math.abs(a - b) < 0.01)
  - **Feature: k10-other-income, Property CP-K10-04: 与K7一致性判断**

- [ ]* 2.7 编写 Property CP-K10-05 PBT：同比变动率
  - 生成器：current∈R, prior≠0
  - 断言：calcYoYChange(cur, prior) === (cur - prior)/prior
  - **Feature: k10-other-income, Property CP-K10-05: 同比变动率=(本期-上期)/上期**

- [ ]* 2.8 编写 Property CP-K10-06 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: k10-other-income, Property CP-K10-06: 合计行恒等**

### Phase 3: Composable层

- [ ] 3.1 创建 useK10FormData.ts
  - selfLoad + checklist_responses + writebackTB(**发生额**，科目6117，从tb_ledger取数)
  - _Requirements: 1.9, 1.10, 2.6, 6.1-6.2_

- [ ] 3.2 创建 useK10CrossSheet.ts（adjudicationVsDetail / reconcileVsK7）
  - _Requirements: 2.5, 4.3-4.5_

- [ ] 3.3 创建 useK10DualMode.ts + useK10ImportExport.ts
  - _Requirements: 3.3, 7.2_

- [ ] 3.4 创建 sheet-specific composables
  - useK10Adjudication / useK10Detail / useK10GrantReconcile / useK10Checks
  - _Requirements: 2~7 全部_

### Phase 4: Vue子组件

- [ ] 4.1 创建 K10TabIndex.vue 底稿目录
  - _Requirements: 1.2_

- [ ] 4.2 创建 K10TabAdjudication.vue 审定表K10-1（损益类69公式+发生额取数+按来源分行+TB回写）
  - _Requirements: 2.1-2.7_

- [ ] 4.3 创建 K10TabDetail.vue 明细表K10-2（12列+动态行+43行+导入导出）
  - _Requirements: 3.1-3.4_

- [ ] 4.4 创建 K10TabGrantReconcile.vue K10-4（补助核对引擎+与K7一致性+GtIndexChip跳转）
  - _Requirements: 4.1-4.5_

- [ ] 4.5 创建 K10TabReceivableGrant.vue K10-5 + K10TabOtherIncomeCheck.vue K10-6
  - 应收补助检查+综合检查(分类正确性)+抽凭+OCR+不合规摘要
  - _Requirements: 5.1-5.4_

- [ ] 4.6 创建 K10TabAdjustment.vue + 附注（K10TabDisclosureListed/Soe.vue）
  - 调整分录借贷平衡+EventBus / 附注双版本+自动取数
  - _Requirements: 7.1-7.2_

### Phase 5: 后端

- [ ] 5.1 创建 _k10_other_income.py render策略 + RENDERER_DISPATCH注册（**损益类取数**，tb_ledger发生额）
  - _Requirements: 1.6, 6.1_

- [ ] 5.2 创建 _k10_import_export.py 导入导出3端点
  - _Requirements: 3.3, 7.2_

- [ ] 5.3 创建 _k10_ai_generate.py AI生成 + 更新 k10-other-income.yaml
  - section: grant-reconcile-conclusion / receivable-grant-eval / overall-opinion
  - _Requirements: 4.1, 7.1_

### Phase 6: 集成联动

- [ ] 6.1 EventBus: TB回写(6117发生额) + substantive:adjudicated → 附注
  - _Requirements: 2.6, 7.1_

- [ ] 6.2 EventBus: adjustment:created → A13 + 附注subscribe刷新 + K7递延收益分摊核对联动
  - _Requirements: 7.2, 4.3_

- [ ] 6.3 GtIndexChip跳转K7 + 抽凭引擎 + 行级OCR + 双模式OO
  - _Requirements: 4.5, 5.3_

### Phase 7: 测试验收

- [ ] 7.1 单元测试：useK10FormulaEngine + useK10GrantReconcileEngine
  - 损益方向(贷-借) + 合计计入 + K7一致性 + 同比 + 边界
  - _Requirements: CP-K10-01~06_

- [ ] 7.2 集成测试：损益取数(发生额) + 补助核对联动K7 + 审定回写
  - _Requirements: 2.5, 4.3, 6.1_

- [ ] 7.3 Playwright E2E：打开K10→审定(验证发生额)→明细→补助核对→检查→保存
  - _Requirements: 全部_
