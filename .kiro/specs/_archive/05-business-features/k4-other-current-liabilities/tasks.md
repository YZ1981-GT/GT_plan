# Implementation Plan: K4 其他流动负债底稿专属HTML精美组件

## Overview

K4其他流动负债底稿专属组件`k4-other-current-liabilities`。K循环负债类最简底稿（8有效sheet/1 xlsx/~90+公式）。

主入口 GtK4OtherCurrentLiabilities.vue（sheetName v-if分发）+ 7个子组件 + composable分层 + 后端3个py文件。

科目：2245其他流动负债（**贷方/负债类**）
公式特征：负债类期末=期初+贷方-借方；审定=未审+AJE+RJE

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

- [x] 0.1 openpyxl脚本读取K4其他流动负债.xlsx全部8 sheet
  - 产出：k4_structure_summary.json（确认K4-1 80公式/K4-2 46公式，含引用/汇总公式）
  - 实际sheet names有空格："审定表 K4-1"/"明细表 K4-2"等
  - _Requirements: 双源输入流程_

- [x] 0.2 K其他流动负债循环底稿模板库md交叉验证
  - 产出：k4_cross_validation_report.md（8 sheet全匹配/负债类方向验证/EventBus联动/完整性认定）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: K4/K4-1~K4-4/K4A → 'k4-other-current-liabilities'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry + GtK4OtherCurrentLiabilities.vue骨架
  - _Requirements: 1.1-1.10_

- [x] 1.2 编写注册契约测试
  - _Requirements: 1.6-1.8_

### Phase 2: 公式引擎（负债类）+PBT

- [x] 2.1 创建 useK4FormulaEngine.ts
  - calcAuditedAmount / calcLiabilityEndBalance / calcTriangleReconciliation / calcSubtotal / calcChangeRate
  - _Requirements: 2.2-2.3, 6.1-6.5_

- [x]* 2.2 编写 Property CP-K4-01 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: k4-other-current-liabilities, Property CP-K4-01: 审定数公式链**

- [x]* 2.3 编写 Property CP-K4-02 PBT：负债类期末余额
  - 断言：calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
  - **Feature: k4-other-current-liabilities, Property CP-K4-02: 负债类期末=期初+贷-借**

- [x]* 2.4 编写 Property CP-K4-03 PBT：三角勾稽恒等式
  - 断言：calcTriangleReconciliation(b, inc, dec, b+inc-dec) === 0
  - **Feature: k4-other-current-liabilities, Property CP-K4-03: 三角勾稽恒等式**

- [x]* 2.5 编写 Property CP-K4-04 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: k4-other-current-liabilities, Property CP-K4-04: 合计行恒等**

- [x]* 2.6 编写 Property CP-K4-05 PBT：借贷平衡
  - 断言：Σdebit === Σcredit
  - **Feature: k4-other-current-liabilities, Property CP-K4-05: 借贷平衡**

### Phase 3: Composable层

- [x] 3.1 创建 useK4FormData.ts（selfLoad + writebackTB 2245 负债口径）
- [x] 3.2 创建 useK4CrossSheet.ts（明细聚合）
- [x] 3.3 创建 useK4DualMode.ts + useK4ImportExport.ts
- [x] 3.4 创建 useK4Adjudication.ts + useK4Detail.ts + useK4Check.ts

### Phase 4: Vue子组件

- [x] 4.1 创建 K4TabIndex.vue 底稿目录
- [x] 4.2 创建 K4TabAdjudication.vue 审定表K4-1（负债类72公式+三角勾稽+TB回写）
- [x] 4.3 创建 K4TabDetail.vue 明细表K4-2（18列2区段+动态行+导入导出）
- [x] 4.4 创建 K4TabCheck.vue 检查表K4-4（含反向截止+抽凭+OCR）
- [x] 4.5 创建 K4TabAdjustment.vue 调整分录（借贷平衡+EventBus）
- [x] 4.6 创建 K4TabDisclosureListed.vue + K4TabDisclosureSoe.vue 附注双版本

### Phase 5: 后端

- [x] 5.1 创建 _k4_other_current_liabilities.py render策略 + RENDERER_DISPATCH（负债口径）
- [x] 5.2 创建 _k4_import_export.py 导入导出3端点
- [x] 5.3 创建 _k4_ai_generate.py AI生成 + 更新 k4-other-current-liabilities.yaml

### Phase 6: 集成联动

- [x] 6.1 EventBus: TB回写(2245) + substantive:adjudicated → 附注
- [x] 6.2 EventBus: adjustment:created → A13 + 附注subscribe刷新
- [x] 6.3 抽凭引擎 + GtIndexChip跳转 + 双模式OO

### Phase 7: 测试验收

- [x] 7.1 单元测试：useK4FormulaEngine（负债类方向 + 边界）
  - _Requirements: CP-K4-01~05_
- [x] 7.2 集成测试：负债类回写 + 明细聚合 + sheetName分发
- [x] 7.3 Playwright E2E：打开K4→审定→明细→检查→保存
