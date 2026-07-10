# Implementation Plan: K12 营业外收入底稿专属HTML精美组件

## Overview

K12营业外收入底稿专属组件`k12-non-operating-income`。K循环损益类最简底稿（9有效sheet/1 xlsx/~90+公式）。

主入口 GtK12NonOperatingIncome.vue（sheetName v-if分发）+ 7个子组件 + composable分层 + 后端3个py文件。

科目：6301营业外收入（**损益类！取发生额**，从tb_ledger取数，贷方=收入）
公式特征：审定=未审+AJE+RJE；收入类发生额=贷方发生-借方发生

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-0",
      "name": "Phase0 双源输入",
      "parallel": true,
      "tasks": [
        "0.1",
        "0.2"
      ]
    },
    {
      "id": "wave-1",
      "name": "Phase1 注册+契约",
      "tasks": [
        "1.1",
        "1.2"
      ]
    },
    {
      "id": "wave-2",
      "name": "Phase2 公式/领域引擎",
      "parallel": false,
      "tasks": [
        "2.1"
      ]
    },
    {
      "id": "wave-3",
      "name": "Phase2 PBT",
      "parallel": true,
      "tasks": [
        "2.2",
        "2.3",
        "2.4",
        "2.5",
        "2.6"
      ]
    },
    {
      "id": "wave-4",
      "name": "Phase3 基础 composable",
      "parallel": true,
      "tasks": [
        "3.1",
        "3.2",
        "3.3"
      ]
    },
    {
      "id": "wave-5",
      "name": "Phase3 sheet composables",
      "tasks": [
        "3.4"
      ]
    },
    {
      "id": "wave-6",
      "name": "Phase4 Vue 子组件",
      "parallel": true,
      "tasks": [
        "4.1",
        "4.2",
        "4.3",
        "4.4",
        "4.5",
        "4.6"
      ]
    },
    {
      "id": "wave-7",
      "name": "Phase5 后端三件套",
      "parallel": true,
      "tasks": [
        "5.1",
        "5.2",
        "5.3"
      ]
    },
    {
      "id": "wave-8",
      "name": "Phase6 集成联动",
      "parallel": true,
      "tasks": [
        "6.1",
        "6.2",
        "6.3"
      ]
    },
    {
      "id": "wave-9",
      "name": "Phase7 测试验收",
      "parallel": true,
      "tasks": [
        "7.1",
        "7.2",
        "7.3"
      ]
    }
  ]
}
```

## Tasks

### Phase 0: 双源输入验证

- [x] 0.1 openpyxl脚本读取K12营业外收入.xlsx全部9 sheet
  - 产出：k12_structure_summary.json（确认K12-1 70公式/K12-2 31公式）
  - _Requirements: 双源输入流程_

- [x] 0.2 K营业外收入循环底稿模板库md交叉验证
  - 核对：损益类取数/营业外收入分类(vs其他收益)
  - 产出：k12_conflict_resolution.md
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: K12/K12-1~K12-4/K12A → 'k12-non-operating-income'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry + GtK12NonOperatingIncome.vue骨架（sheetName v-if + selfLoad）
  - _Requirements: 1.1-1.10_

- [x] 1.2 编写注册契约测试
  - _Requirements: 1.6-1.8_

### Phase 2: 公式引擎（损益类）+PBT

- [x] 2.1 创建 useK12FormulaEngine.ts（损益类！）
  - calcAuditedAmount / calcIncomeStatementOccurrence(cr,dr)=cr-dr / calcYoYChange / calcProportion / calcSubtotal
  - _Requirements: 2.3-2.4, 5.1-5.3, 6.3-6.7_

- [x]* 2.2 编写 Property CP-K12-01 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: k12-non-operating-income, Property CP-K12-01: 审定数公式链**

- [x] 2.3 编写 Property CP-K12-02 PBT：损益类发生额（贷-借）
  - 生成器：creditOcc≥0, debitOcc≥0
  - 断言：calcIncomeStatementOccurrence(cr, dr) === cr - dr
  - **Feature: k12-non-operating-income, Property CP-K12-02: 收入类发生额=贷方发生-借方发生**

- [x]* 2.4 编写 Property CP-K12-03 PBT：同比变动率
  - 生成器：current∈R, prior≠0
  - 断言：calcYoYChange(cur, prior) === (cur - prior)/prior
  - **Feature: k12-non-operating-income, Property CP-K12-03: 同比变动率=(本期-上期)/上期**

- [x]* 2.5 编写 Property CP-K12-04 PBT：占比公式
  - 生成器：item∈R, total>0
  - 断言：calcProportion(item, total) === item/total
  - **Feature: k12-non-operating-income, Property CP-K12-04: 占比=单项/合计**

- [x]* 2.6 编写 Property CP-K12-05 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: k12-non-operating-income, Property CP-K12-05: 合计行恒等**

### Phase 3: Composable层

- [x] 3.1 创建 useK12FormData.ts
  - selfLoad + checklist_responses + writebackTB(**发生额**，科目6301，从tb_ledger取数)
  - _Requirements: 1.9, 1.10, 2.6, 5.1-5.2_

- [x] 3.2 创建 useK12CrossSheet.ts（adjudicationVsDetail）
  - _Requirements: 2.5, 3.2_

- [x] 3.3 创建 useK12DualMode.ts + useK12ImportExport.ts
  - _Requirements: 3.3, 6.2_

- [x] 3.4 创建 useK12Adjudication.ts + useK12Detail.ts + useK12Check.ts
  - _Requirements: 2~6 全部_

### Phase 4: Vue子组件

- [x] 4.1 创建 K12TabIndex.vue 底稿目录
  - _Requirements: 1.2_

- [x] 4.2 创建 K12TabAdjudication.vue 审定表K12-1（损益类70公式+发生额取数+按来源分行+TB回写）
  - _Requirements: 2.1-2.7_

- [x] 4.3 创建 K12TabDetail.vue 明细表K12-2（26列3区段+动态行+27行+导入导出）
  - _Requirements: 3.1-3.4_

- [x] 4.4 创建 K12TabNonOperatingCheck.vue K12-4（分类正确性检查+抽凭+OCR+不合规摘要）
  - _Requirements: 4.1-4.3_

- [x] 4.5 创建 K12TabAdjustment.vue 调整分录（借贷平衡+EventBus）
  - _Requirements: 6.2_

- [x] 4.6 创建 K12TabDisclosureListed.vue + K12TabDisclosureSoe.vue 附注双版本
  - 按来源披露+自动取数
  - _Requirements: 6.1_

### Phase 5: 后端

- [x] 5.1 创建 _k12_non_operating_income.py render策略 + RENDERER_DISPATCH注册（**损益类取数**，tb_ledger发生额）
  - _Requirements: 1.6, 5.1_

- [x] 5.2 创建 _k12_import_export.py 导入导出3端点
  - _Requirements: 3.3, 6.2_

- [x] 5.3 创建 _k12_ai_generate.py AI生成 + 更新 k12-non-operating-income.yaml
  - section: non-operating-eval / overall-opinion
  - _Requirements: 6.1_

### Phase 6: 集成联动

- [x] 6.1 EventBus: TB回写(6301发生额) + substantive:adjudicated → 附注
  - _Requirements: 2.6, 6.1_

- [x] 6.2 EventBus: adjustment:created → A13 + 附注subscribe刷新
  - _Requirements: 6.2_

- [x] 6.3 抽凭引擎 + 行级OCR + GtIndexChip跳转 + 双模式OO
  - _Requirements: 4.2_

### Phase 7: 测试验收

- [x] 7.1 单元测试：useK12FormulaEngine（损益方向(贷-借) + 同比/占比 + 边界）
  - _Requirements: CP-K12-01~05_

- [x] 7.2 集成测试：损益取数(发生额) + 明细聚合 + 审定回写
  - _Requirements: 2.5, 5.1_

- [x] 7.3 Playwright E2E：打开K12→审定(验证发生额)→明细→检查→保存
  - _Requirements: 全部_
