# Implementation Plan: K4 其他流动负债底稿专属HTML精美组件

## Overview

K4其他流动负债底稿专属组件`k4-other-current-liabilities`。K循环负债类最简底稿（8有效sheet/1 xlsx/~90+公式）。

主入口 GtK4OtherCurrentLiabilities.vue（sheetName v-if分发）+ 7个子组件 + composable分层 + 后端3个py文件。

科目：2245其他流动负债（**贷方/负债类**）
公式特征：负债类期末=期初+贷方-借方；审定=未审+AJE+RJE

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

- [ ] 0.1 openpyxl脚本读取K4其他流动负债.xlsx全部8 sheet
  - 产出：k4_structure_summary.json（确认K4-1 72公式/K4-2 17公式）
  - _Requirements: 双源输入流程_

- [ ] 0.2 K其他流动负债循环底稿模板库md交叉验证
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - wp_code_overrides: K4/K4-1~K4-4/K4A → 'k4-other-current-liabilities'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry + GtK4OtherCurrentLiabilities.vue骨架
  - _Requirements: 1.1-1.10_

- [ ] 1.2 编写注册契约测试
  - _Requirements: 1.6-1.8_

### Phase 2: 公式引擎（负债类）+PBT

- [ ] 2.1 创建 useK4FormulaEngine.ts
  - calcAuditedAmount / calcLiabilityEndBalance / calcTriangleReconciliation / calcSubtotal / calcChangeRate
  - _Requirements: 2.2-2.3, 6.1-6.5_

- [ ]* 2.2 编写 Property CP-K4-01 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: k4-other-current-liabilities, Property CP-K4-01: 审定数公式链**

- [ ]* 2.3 编写 Property CP-K4-02 PBT：负债类期末余额
  - 断言：calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
  - **Feature: k4-other-current-liabilities, Property CP-K4-02: 负债类期末=期初+贷-借**

- [ ]* 2.4 编写 Property CP-K4-03 PBT：三角勾稽恒等式
  - 断言：calcTriangleReconciliation(b, inc, dec, b+inc-dec) === 0
  - **Feature: k4-other-current-liabilities, Property CP-K4-03: 三角勾稽恒等式**

- [ ]* 2.5 编写 Property CP-K4-04 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: k4-other-current-liabilities, Property CP-K4-04: 合计行恒等**

- [ ]* 2.6 编写 Property CP-K4-05 PBT：借贷平衡
  - 断言：Σdebit === Σcredit
  - **Feature: k4-other-current-liabilities, Property CP-K4-05: 借贷平衡**

### Phase 3: Composable层

- [ ] 3.1 创建 useK4FormData.ts（selfLoad + writebackTB 2245 负债口径）
- [ ] 3.2 创建 useK4CrossSheet.ts（明细聚合）
- [ ] 3.3 创建 useK4DualMode.ts + useK4ImportExport.ts
- [ ] 3.4 创建 useK4Adjudication.ts + useK4Detail.ts + useK4Check.ts

### Phase 4: Vue子组件

- [ ] 4.1 创建 K4TabIndex.vue 底稿目录
- [ ] 4.2 创建 K4TabAdjudication.vue 审定表K4-1（负债类72公式+三角勾稽+TB回写）
- [ ] 4.3 创建 K4TabDetail.vue 明细表K4-2（18列2区段+动态行+导入导出）
- [ ] 4.4 创建 K4TabCheck.vue 检查表K4-4（含反向截止+抽凭+OCR）
- [ ] 4.5 创建 K4TabAdjustment.vue 调整分录（借贷平衡+EventBus）
- [ ] 4.6 创建 K4TabDisclosureListed.vue + K4TabDisclosureSoe.vue 附注双版本

### Phase 5: 后端

- [ ] 5.1 创建 _k4_other_current_liabilities.py render策略 + RENDERER_DISPATCH（负债口径）
- [ ] 5.2 创建 _k4_import_export.py 导入导出3端点
- [ ] 5.3 创建 _k4_ai_generate.py AI生成 + 更新 k4-other-current-liabilities.yaml

### Phase 6: 集成联动

- [ ] 6.1 EventBus: TB回写(2245) + substantive:adjudicated → 附注
- [ ] 6.2 EventBus: adjustment:created → A13 + 附注subscribe刷新
- [ ] 6.3 抽凭引擎 + GtIndexChip跳转 + 双模式OO

### Phase 7: 测试验收

- [ ] 7.1 单元测试：useK4FormulaEngine（负债类方向 + 边界）
  - _Requirements: CP-K4-01~05_
- [ ] 7.2 集成测试：负债类回写 + 明细聚合 + sheetName分发
- [ ] 7.3 Playwright E2E：打开K4→审定→明细→检查→保存
