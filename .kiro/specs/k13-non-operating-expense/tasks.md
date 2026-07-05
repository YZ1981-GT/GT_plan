# Implementation Plan: K13 营业外支出底稿专属HTML精美组件

## Overview

K13营业外支出底稿专属组件`k13-non-operating-expense`。K循环损益类最简底稿（9有效sheet/1 xlsx/~90+公式）。

主入口 GtK13NonOperatingExpense.vue（sheetName v-if分发）+ 7个子组件 + composable分层 + 后端3个py文件。

科目：6711营业外支出（**损益类！取发生额**，从tb_ledger取数，借方=支出）
公式特征：审定=未审+AJE+RJE；支出类发生额=借方发生-贷方发生

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册+契约]
    P1 --> P2[Phase 2: 公式引擎(损益类)+PBT]
    P2 --> P3[Phase 3: Composable层]
    P3 --> P4[Phase 4: Vue子组件]
    P1 --> P5[Phase 5: 后端(损益取数)]
    P4 --> P6[Phase 6: 集成联动]
    P5 --> P6
    P6 --> P7[Phase 7: 测试验收]
```

## Tasks

### Phase 0: 双源输入验证

- [ ] 0.1 openpyxl脚本读取K13营业外支出.xlsx全部9 sheet
  - 产出：k13_structure_summary.json（确认K13-1 69公式/K13-2 31公式）
  - _Requirements: 双源输入流程_

- [ ] 0.2 K营业外支出循环底稿模板库md交叉验证
  - 核对：损益类取数/营业外支出分类/税前扣除性
  - 产出：k13_conflict_resolution.md
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - wp_code_overrides: K13/K13-1~K13-4/K13A → 'k13-non-operating-expense'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry + GtK13NonOperatingExpense.vue骨架（sheetName v-if + selfLoad）
  - _Requirements: 1.1-1.10_

- [ ] 1.2 编写注册契约测试
  - _Requirements: 1.6-1.8_

### Phase 2: 公式引擎（损益类）+PBT

- [ ] 2.1 创建 useK13FormulaEngine.ts（损益类！）
  - calcAuditedAmount / calcIncomeStatementOccurrence(dr,cr)=dr-cr / calcYoYChange / calcProportion / calcSubtotal
  - _Requirements: 2.3-2.4, 5.1-5.3, 6.3-6.7_

- [ ]* 2.2 编写 Property CP-K13-01 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: k13-non-operating-expense, Property CP-K13-01: 审定数公式链**

- [ ]* 2.3 编写 Property CP-K13-02 PBT：损益类发生额（借-贷）
  - 生成器：debitOcc≥0, creditOcc≥0
  - 断言：calcIncomeStatementOccurrence(dr, cr) === dr - cr
  - **Feature: k13-non-operating-expense, Property CP-K13-02: 支出类发生额=借方发生-贷方发生**

- [ ]* 2.4 编写 Property CP-K13-03 PBT：同比变动率
  - 生成器：current∈R, prior≠0
  - 断言：calcYoYChange(cur, prior) === (cur - prior)/prior
  - **Feature: k13-non-operating-expense, Property CP-K13-03: 同比变动率=(本期-上期)/上期**

- [ ]* 2.5 编写 Property CP-K13-04 PBT：占比公式
  - 生成器：item∈R, total>0
  - 断言：calcProportion(item, total) === item/total
  - **Feature: k13-non-operating-expense, Property CP-K13-04: 占比=单项/合计**

- [ ]* 2.6 编写 Property CP-K13-05 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: k13-non-operating-expense, Property CP-K13-05: 合计行恒等**

### Phase 3: Composable层

- [ ] 3.1 创建 useK13FormData.ts
  - selfLoad + checklist_responses + writebackTB(**发生额**，科目6711，从tb_ledger取数)
  - _Requirements: 1.9, 1.10, 2.6, 5.1-5.2_

- [ ] 3.2 创建 useK13CrossSheet.ts（adjudicationVsDetail）
  - _Requirements: 2.5, 3.2_

- [ ] 3.3 创建 useK13DualMode.ts + useK13ImportExport.ts
  - _Requirements: 3.3, 6.2_

- [ ] 3.4 创建 useK13Adjudication.ts + useK13Detail.ts + useK13Check.ts
  - _Requirements: 2~6 全部_

### Phase 4: Vue子组件

- [ ] 4.1 创建 K13TabIndex.vue 底稿目录
  - _Requirements: 1.2_

- [ ] 4.2 创建 K13TabAdjudication.vue 审定表K13-1（损益类69公式+发生额取数+按去向分行+TB回写）
  - _Requirements: 2.1-2.7_

- [ ] 4.3 创建 K13TabDetail.vue 明细表K13-2（26列3区段+动态行+27行+导入导出）
  - _Requirements: 3.1-3.4_

- [ ] 4.4 创建 K13TabNonOperatingCheck.vue K13-4（分类正确性+税前扣除性检查+抽凭+OCR+不合规摘要）
  - _Requirements: 4.1-4.3_

- [ ] 4.5 创建 K13TabAdjustment.vue 调整分录（借贷平衡+EventBus）
  - _Requirements: 6.2_

- [ ] 4.6 创建 K13TabDisclosureListed.vue + K13TabDisclosureSoe.vue 附注双版本
  - 按去向披露+自动取数
  - _Requirements: 6.1_

### Phase 5: 后端

- [ ] 5.1 创建 _k13_non_operating_expense.py render策略 + RENDERER_DISPATCH注册（**损益类取数**，tb_ledger发生额）
  - _Requirements: 1.6, 5.1_

- [ ] 5.2 创建 _k13_import_export.py 导入导出3端点
  - _Requirements: 3.3, 6.2_

- [ ] 5.3 创建 _k13_ai_generate.py AI生成 + 更新 k13-non-operating-expense.yaml
  - section: non-operating-eval / overall-opinion
  - _Requirements: 6.1_

### Phase 6: 集成联动

- [ ] 6.1 EventBus: TB回写(6711发生额) + substantive:adjudicated → 附注
  - _Requirements: 2.6, 6.1_

- [ ] 6.2 EventBus: adjustment:created → A13 + 附注subscribe刷新
  - _Requirements: 6.2_

- [ ] 6.3 抽凭引擎 + 行级OCR + GtIndexChip跳转 + 双模式OO
  - _Requirements: 4.2_

### Phase 7: 测试验收

- [ ] 7.1 单元测试：useK13FormulaEngine（损益方向(借-贷) + 同比/占比 + 边界）
  - _Requirements: CP-K13-01~05_

- [ ] 7.2 集成测试：损益取数(发生额) + 明细聚合 + 审定回写
  - _Requirements: 2.5, 5.1_

- [ ] 7.3 Playwright E2E：打开K13→审定(验证发生额)→明细→检查→保存
  - _Requirements: 全部_
