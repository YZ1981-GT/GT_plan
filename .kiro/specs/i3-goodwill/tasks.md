# Implementation Plan: I3 商誉底稿专属HTML精美组件

## Overview

I3商誉底稿专属组件`i3-goodwill`。I循环DCF核心底稿（15有效sheet/1 xlsx/~120+公式）。

主入口 GtI3Goodwill.vue（sheetName v-if分发）+ 11个子组件 + 11个composable + 后端4个py文件。

科目：1711商誉（借方/资产类，**不摊销！**仅年度减值测试）
公式特征：期末=期初+新并购-减值（不摊销）；DCF现值；减值先冲商誉再分摊；审定=未审+AJE+RJE

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-0",
      "name": "Phase0 双源输入",
      "tasks": [
        "0.1",
        "0.2"
      ],
      "parallel": true
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
      "tasks": [
        "2.1",
        "2.2"
      ],
      "parallel": true
    },
    {
      "id": "wave-3",
      "name": "Phase2 PBT",
      "tasks": [
        "2.3",
        "2.4",
        "2.5",
        "2.6",
        "2.7",
        "2.8",
        "2.9",
        "2.10"
      ],
      "parallel": true
    },
    {
      "id": "wave-4",
      "name": "Phase3 基础 composable",
      "tasks": [
        "3.1",
        "3.2",
        "3.3"
      ],
      "parallel": true
    },
    {
      "id": "wave-5",
      "name": "Phase3 sheet/domain composables",
      "tasks": [
        "3.4",
        "3.5",
        "3.6"
      ],
      "parallel": true
    },
    {
      "id": "wave-6",
      "name": "Phase4 Vue 子组件",
      "tasks": [
        "4.1",
        "4.2",
        "4.3",
        "4.4",
        "4.5",
        "4.6",
        "4.7",
        "4.8",
        "4.9",
        "4.10"
      ],
      "parallel": true
    },
    {
      "id": "wave-7",
      "name": "Phase5 后端",
      "tasks": [
        "5.1",
        "5.2",
        "5.3",
        "5.4",
        "5.5"
      ],
      "parallel": true
    },
    {
      "id": "wave-8",
      "name": "Phase6 集成联动",
      "tasks": [
        "6.1",
        "6.2",
        "6.3",
        "6.4",
        "6.5"
      ],
      "parallel": true
    },
    {
      "id": "wave-9",
      "name": "Phase7 测试验收",
      "tasks": [
        "7.1",
        "7.2",
        "7.3",
        "7.4"
      ],
      "parallel": true
    }
  ]
}
```

## Tasks

### Phase 0: 双源输入验证

- [x] 0.1 openpyxl脚本读取I3商誉.xlsx全部15 sheet
  - 确认1个历史遗留sheet已被regex skip
  - 产出：i3_structure_summary.json
  - _Requirements: 双源输入流程_

- [x] 0.2 底稿模板库md交叉验证
  - 核对DCF模型/CGU分摊/减值分摊规则
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: I3/I3-1~I3-8/I3A → 'i3-goodwill'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry + GtI3Goodwill.vue骨架
  - _Requirements: 1.1-1.10_

- [x] 1.2 编写注册契约测试
  - _Requirements: 1.6-1.8_

### Phase 2: 公式引擎+PBT

- [x] 2.1 创建 useI3FormulaEngine.ts（商誉不摊销！）
  - calcAuditedAmount / calcGoodwillEndBalance / calcGoodwillNetValue
  - calcInitialGoodwill / calcSubtotal / calcImpairmentAllocation
  - _Requirements: 2.2-2.7, 4.2, 5.2-5.4_

- [x] 2.2 创建 useI3DcfEngine.ts
  - calcDcfPresentValue / calcTerminalValue / calcWacc
  - calcRecoverableAmount / calcSensitivity
  - _Requirements: 6.2-6.5_

- [x]* 2.3 编写 Property P1 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: i3-goodwill, Property P1: 审定数公式链**

- [x]* 2.4 编写 Property P2 PBT：商誉期末余额（不摊销！）
  - 生成器：begin≥0, newAcq≥0, impairment∈[0, begin+newAcq]
  - 断言：calcGoodwillEndBalance(b, n, i) === b + n - i
  - **Feature: i3-goodwill, Property P2: 商誉期末=期初+新并购-减值（不摊销）**

- [x] 2.5 编写 Property P3 PBT：初始商誉=合并成本-净资产公允
  - 生成器：mergerCost > netAssetFV
  - 断言：calcInitialGoodwill(mc, nafv) === mc - nafv
  - **Feature: i3-goodwill, Property P3: 初始商誉=合并成本-可辨认净资产公允**

- [x]* 2.6 编写 Property P4 PBT：减值先冲商誉
  - 生成器：totalImpairment>0, goodwillAmount>0, otherAssets[]
  - 断言：goodwillImpairment === MIN(total, goodwill)；剩余按比例分摊
  - **Feature: i3-goodwill, Property P4: 减值先冲商誉再分摊**

- [x]* 2.7 编写 Property P5 PBT：DCF现值计算
  - 断言：calcDcfPresentValue(cfs, r) === Σ(cf/(1+r)^(i+1))
  - **Feature: i3-goodwill, Property P5: DCF现值计算正确性**

- [x]* 2.8 编写 Property P6 PBT：可收回金额MAX
  - 断言：calcRecoverableAmount(fv, dcf) === Math.max(fv, dcf)
  - **Feature: i3-goodwill, Property P6: 可收回金额=MAX(公允-处置费, DCF)**

- [x]* 2.9 编写 Property P7 PBT：减值金额非负且≤资产组账面
  - 断言：impairment ∈ [0, cguBookValue]
  - **Feature: i3-goodwill, Property P7: 减值金额∈[0, 资产组账面]**

- [x]* 2.10 编写 Property P8 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: i3-goodwill, Property P8: 合计行恒等**

### Phase 3: Composable层

- [x] 3.1 创建 useI3FormData.ts（selfLoad + writebackTB 1711）
- [x] 3.2 创建 useI3CrossSheet.ts（明细聚合 + 减值联动）
- [x] 3.3 创建 useI3Adjudication.ts（商誉不摊销审定逻辑）
- [x] 3.4 创建 useI3Detail.ts（30列3区段）
- [x] 3.5 创建 useI3Impairment.ts（CGU分摊+先冲商誉逻辑）
- [x] 3.6 创建 useI3Disclosure.ts + useI3ImportExport.ts + useI3DualMode.ts

### Phase 4: Vue子组件

- [x] 4.1 创建 I3TabIndex.vue
- [x] 4.2 创建 I3TabAdjudication.vue（66公式，不摊销！）
- [x] 4.3 创建 I3TabDetail.vue（30列3区段）
- [x] 4.4 创建 I3TabAdjustment.vue
- [x] 4.5 创建 I3TabInitialValue.vue（入账测算12公式）
- [x] 4.6 创建 I3TabTargetedCheck.vue
- [x] 4.7 创建 I3TabImpairmentTest.vue（CGU分摊）
- [x] 4.8 创建 I3TabRecoverableTest.vue（DCF核心100×16+虚拟滚动）
- [x] 4.9 创建 I3TabReviewProcess.vue（153行大表+虚拟滚动）
- [x] 4.10 创建 I3TabDisclosureListed.vue + I3TabDisclosureSoe.vue

### Phase 5: 后端

- [x] 5.1 创建 _i3_goodwill.py render策略 + RENDERER_DISPATCH
- [x] 5.2 创建 _i3_import_export.py 导入导出3端点
- [x] 5.3 创建 _i3_ai_generate.py AI生成（DCF参数建议）
- [x] 5.4 创建 _i3_dcf_engine.py DCF引擎验证端点
- [x] 5.5 更新 wp_render_schema: i3-goodwill.yaml

### Phase 6: 集成联动

- [x] 6.1 EventBus: TB回写(1711) + substantive:adjudicated
- [x] 6.2 EventBus: adjustment:created → A13
- [x] 6.3 GtIndexChip: I3-6→I3-7 DCF跳转
- [x] 6.4 附注EventBus + 双模式OO
- [x] 6.5 _should_skip_historical_sheet回归验证（I3历史遗留1sheet）

### Phase 7: 测试验收

- [x] 7.1 Vitest: useI3FormulaEngine + useI3DcfEngine
- [x] 7.2 Vitest组件: sheetName分发
- [x] 7.3 后端pytest: render+DCF验证+导入导出
- [x] 7.4 Playwright E2E: DCF测算→减值分摊→审定表全链路
