# Implementation Plan: K8 销售费用底稿专属HTML精美组件

## Overview

K8销售费用底稿专属组件`k8-selling-expenses`。K循环损益类底稿（12有效sheet/1 xlsx/~120+公式）。

主入口 GtK8SellingExpenses.vue（sheetName v-if分发，defineAsyncComponent lazy）+ 11个子组件 + composable分层（含实质性分析引擎+截止引擎）+ 后端3个py文件。

科目：6601销售费用（**损益类！取发生额**，从tb_ledger取数）
公式特征：审定=未审+AJE+RJE；费用类发生额=借方发生-贷方发生；同比/占比分析；截止双向

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
      "parallel": true,
      "tasks": [
        "2.1",
        "2.2"
      ]
    },
    {
      "id": "wave-3",
      "name": "Phase2 PBT",
      "parallel": true,
      "tasks": [
        "2.3",
        "2.4",
        "2.5",
        "2.6",
        "2.7",
        "2.8",
        "2.9"
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

- [x] 0.1 openpyxl脚本读取K8销售费用.xlsx全部12 sheet
  - 产出：k8_structure_summary.json（确认K8-1 73公式/K8-4 25公式/K8-6/K8-7各44行）
  - _Requirements: 双源输入流程_

- [x] 0.2 K销售费用循环底稿模板库md交叉验证
  - 核对：损益类取数/tb_ledger明细科目/实质性分析/截止双向
  - 产出：k8_conflict_resolution.md
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: K8/K8-1~K8-8/K8A → 'k8-selling-expenses'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry + GtK8SellingExpenses.vue骨架（sheetName v-if + selfLoad）
  - _Requirements: 1.1-1.10_

- [x] 1.2 编写注册契约测试
  - _Requirements: 1.6-1.8_

### Phase 2: 公式引擎（损益类）+分析引擎+截止引擎+PBT

- [x] 2.1 创建 useK8FormulaEngine.ts（损益类！）
  - calcAuditedAmount / calcIncomeStatementOccurrence(dr,cr)=dr-cr / calcSubtotal
  - _Requirements: 2.3-2.4, 7.1-7.4, 9.1-9.2, 9.6_

- [x] 2.2 创建 useK8AnalysisEngine.ts + useK8CutoffEngine.ts
  - calcYoYChange / calcRatioToRevenue / isAbnormalFluctuation / isCrossPeriod / autoSampleCutoff
  - _Requirements: 4.2-4.4, 5.3-5.4, 9.3-9.5, 9.7_

- [x]* 2.3 编写 Property CP-K8-01 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: k8-selling-expenses, Property CP-K8-01: 审定数公式链**

- [x]* 2.4 编写 Property CP-K8-02 PBT：损益类发生额（借-贷）
  - 生成器：debitOcc≥0, creditOcc≥0
  - 断言：calcIncomeStatementOccurrence(dr, cr) === dr - cr
  - **Feature: k8-selling-expenses, Property CP-K8-02: 费用类发生额=借方发生-贷方发生**

- [x]* 2.5 编写 Property CP-K8-03 PBT：同比变动率
  - 生成器：current∈R, prior≠0
  - 断言：calcYoYChange(cur, prior) === (cur - prior)/prior
  - **Feature: k8-selling-expenses, Property CP-K8-03: 同比变动率=(本期-上期)/上期**

- [x]* 2.6 编写 Property CP-K8-04 PBT：占收入比
  - 生成器：expense∈R, revenue>0
  - 断言：calcRatioToRevenue(exp, rev) === exp/rev
  - **Feature: k8-selling-expenses, Property CP-K8-04: 占收入比=费用/营业收入**

- [x]* 2.7 编写 Property CP-K8-05 PBT：异常波动判断
  - 断言：isAbnormalFluctuation(rate, th) === (Math.abs(rate) > th)
  - **Feature: k8-selling-expenses, Property CP-K8-05: 异常判断=|变动率|>阈值**

- [x]* 2.8 编写 Property CP-K8-06 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: k8-selling-expenses, Property CP-K8-06: 合计行恒等**

- [x]* 2.9 编写 Property CP-K8-07 PBT：跨期判断确定性
  - 断言：sourceDate/bookDate分属不同会计期间 → isCrossPeriod=true
  - **Feature: k8-selling-expenses, Property CP-K8-07: 跨期判断确定性**

### Phase 3: Composable层

- [x] 3.1 创建 useK8FormData.ts
  - selfLoad + checklist_responses + writebackTB(**发生额**，科目6601，从tb_ledger取数)
  - _Requirements: 1.9, 1.10, 2.6, 7.1-7.3_

- [x] 3.2 创建 useK8CrossSheet.ts（adjudicationVsDetail / analysisVsDetail）
  - _Requirements: 2.5, 3.2, 4.6_

- [x] 3.3 创建 useK8DualMode.ts + useK8ImportExport.ts
  - _Requirements: 3.3, 8.2_

- [x] 3.4 创建 sheet-specific composables
  - useK8Adjudication / useK8Detail / useK8Analysis / useK8Cutoff / useK8Checks
  - _Requirements: 2~8 全部_

### Phase 4: Vue子组件

- [x] 4.1 创建 K8TabIndex.vue 底稿目录
  - _Requirements: 1.2_

- [x] 4.2 创建 K8TabAdjudication.vue 审定表K8-1（损益类73公式+发生额取数+按明细分行+TB回写）
  - _Requirements: 2.1-2.7_

- [x] 4.3 创建 K8TabDetail.vue 明细表K8-2（27列3区段+tb_ledger取数+动态行+48行+导入导出）
  - _Requirements: 3.1-3.4_

- [x] 4.4 创建 K8TabSubstantiveAnalysis.vue K8-4（25公式+同比环比占比+异常标记+39行+AI辅助）
  - _Requirements: 4.1-4.6_

- [x] 4.5 创建 K8TabCutoffV2S.vue K8-6 + K8TabCutoffS2V.vue K8-7
  - 截止双向+自动抽样+跨期判断+跨期红标+44行+行级抽凭
  - _Requirements: 5.1-5.6_

- [x] 4.6 创建 K8TabContractCheck.vue K8-5 + K8TabSellingCheck.vue K8-8 + K8TabAdjustment.vue + 附注（K8TabDisclosureListed/Soe.vue）
  - 合同检查+综合检查+抽凭+OCR / 调整分录 / 附注双版本
  - _Requirements: 6.1-6.4, 8.1-8.2_

### Phase 5: 后端

- [x] 5.1 创建 _k8_selling_expenses.py render策略 + RENDERER_DISPATCH注册（**损益类取数**，tb_ledger发生额）
  - _Requirements: 1.6, 7.1-7.2_

- [x] 5.2 创建 _k8_import_export.py 导入导出3端点
  - _Requirements: 3.3, 8.2_

- [x] 5.3 创建 _k8_ai_generate.py AI生成 + 更新 k8-selling-expenses.yaml
  - section: fluctuation-analysis / cutoff-conclusion / contract-check-eval / overall-opinion
  - _Requirements: 4.6, 8.1_

### Phase 6: 集成联动

- [x] 6.1 EventBus: TB回写(6601发生额) + substantive:adjudicated → 附注
  - _Requirements: 2.6, 8.1_

- [x] 6.2 EventBus: adjustment:created → A13 + 附注subscribe刷新
  - _Requirements: 8.2_

- [x] 6.3 useCutoffAutoSampling集成(序时账±5天) + 抽凭引擎 + 行级OCR + GtIndexChip + 双模式OO
  - _Requirements: 5.3, 6.3_

### Phase 7: 测试验收

- [x] 7.1 单元测试：useK8FormulaEngine + useK8AnalysisEngine + useK8CutoffEngine
  - 损益方向(借-贷) + 同比/占比 + 异常判断 + 跨期 + 边界
  - _Requirements: CP-K8-01~07_

- [ ] 7.2 集成测试：损益取数(发生额) + 实质性分析 + 截止双向 + 审定回写
  - _Requirements: 2.5, 4.4, 5.4, 7.1_

- [x] 7.3 Playwright E2E：打开K8→审定(验证发生额)→明细→实质性分析→截止双向→保存
  - _Requirements: 全部_
