# Implementation Plan: K6 持有待售资产和负债底稿专属HTML精美组件

## Overview

K6持有待售底稿专属组件`k6-held-for-sale`。K循环含CAS42分类+减值孰低的资产/负债混合底稿（11有效sheet/1 xlsx/~90+公式）。

主入口 GtK6HeldForSale.vue（sheetName v-if分发，defineAsyncComponent lazy）+ 10个子组件 + composable分层（含分类引擎+减值孰低引擎）+ 后端3个py文件。

科目：持有待售资产（借方/资产类）+ 持有待售负债（贷方/负债类）
公式特征：账面=原值-折旧摊销-减值；CAS42五条件分类；减值=MAX(0,账面-公允净额)

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

- [x] 0.1 openpyxl脚本读取K6持有待售资产和负债.xlsx全部11 sheet
  - 产出：k6_structure_summary.json（确认K6-1 45公式/K6-5 16公式/K6-6 13公式）
  - _Requirements: 双源输入流程_

- [x] 0.2 K持有待售循环底稿模板库md交叉验证
  - 核对：CAS42五条件/减值孰低/处置组分摊/不再满足重分类
  - 产出：k6_conflict_resolution.md
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: K6/K6-1~K6-7/K6A → 'k6-held-for-sale'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry + GtK6HeldForSale.vue骨架（sheetName v-if + selfLoad）
  - _Requirements: 1.1-1.10_

- [x] 1.2 编写注册契约测试
  - _Requirements: 1.6-1.8_

### Phase 2: 公式引擎+CAS42分类引擎+减值孰低引擎+PBT

- [x] 2.1 创建 useK6FormulaEngine.ts
  - calcAuditedAmount / calcBookValue / calcSubtotal
  - _Requirements: 2.3-2.4, 3.2, 9.1-9.2, 9.7_

- [x] 2.2 创建 useK6ClassificationEngine.ts + useK6ImpairmentEngine.ts
  - classifyHeldForSale / calcFairValueNet / calcImpairment / calcAllocationRatio
  - _Requirements: 4.2, 5.2-5.4, 6.2-6.3, 9.3-9.6_

- [x]* 2.3 编写 Property CP-K6-01 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: k6-held-for-sale, Property CP-K6-01: 审定数公式链**

- [x]* 2.4 编写 Property CP-K6-02 PBT：账面价值
  - 断言：calcBookValue(cost, dep, imp) === cost - dep - imp
  - **Feature: k6-held-for-sale, Property CP-K6-02: 账面价值=原值-折旧摊销-减值**

- [x]* 2.5 编写 Property CP-K6-03 PBT：分类判断确定性
  - 断言：全True→'classified'；含任一False→'not_classified'
  - **Feature: k6-held-for-sale, Property CP-K6-03: CAS42五条件分类判断**

- [x]* 2.6 编写 Property CP-K6-04 PBT：公允价值净额
  - 断言：calcFairValueNet(fv, sc) === fv - sc
  - **Feature: k6-held-for-sale, Property CP-K6-04: 公允价值净额=公允-出售费用**

- [x]* 2.7 编写 Property CP-K6-05 PBT：减值孰低且非负
  - 断言：calcImpairment(bv, fvn) === Math.max(0, bv - fvn) 且 结果≥0
  - **Feature: k6-held-for-sale, Property CP-K6-05: 减值=MAX(0,账面-公允净额)非负**

- [x]* 2.8 编写 Property CP-K6-06 PBT：分摊比例
  - 生成器：itemBook∈R, groupBook>0
  - 断言：calcAllocationRatio(item, group) === item/group
  - **Feature: k6-held-for-sale, Property CP-K6-06: 分摊比例=组内/组合计**

- [x]* 2.9 编写 Property CP-K6-07 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: k6-held-for-sale, Property CP-K6-07: 合计行恒等**

### Phase 3: Composable层

- [x] 3.1 创建 useK6FormData.ts（selfLoad + writebackTB 持有待售资产+负债双科目）
  - _Requirements: 1.9, 1.10, 2.6_

- [x] 3.2 创建 useK6CrossSheet.ts
  - adjudicationVsDetail / impairmentVsAdjudication / groupVsImpairment
  - _Requirements: 2.7, 3.3, 5.5, 6.4_

- [x] 3.3 创建 useK6DualMode.ts + useK6ImportExport.ts
  - _Requirements: 3.4, 8.2_

- [x] 3.4 创建 sheet-specific composables
  - useK6Adjudication / useK6Detail / useK6InitialRecognition / useK6Impairment / useK6GroupImpairment / useK6NoLongerCheck
  - _Requirements: 2~8 全部_

### Phase 4: Vue子组件

- [x] 4.1 创建 K6TabIndex.vue 底稿目录
  - _Requirements: 1.2_

- [x] 4.2 创建 K6TabAdjudication.vue 审定表K6-1（资产+负债双区块+45公式+三角勾稽+TB回写）
  - _Requirements: 2.1-2.8_

- [x] 4.3 创建 K6TabDetail.vue 明细表K6-2（15列12公式+账面价值+动态行+40行+导入导出）
  - _Requirements: 3.1-3.5_

- [x] 4.4 创建 K6TabInitialRecognition.vue K6-4（CAS42五条件核对清单+分类判断+AI辅助）
  - _Requirements: 4.1-4.5_

- [x] 4.5 创建 K6TabImpairmentTest.vue K6-5 + K6TabGroupImpairment.vue K6-6
  - 减值孰低测试+处置组分摊+回连审定+虚拟滚动+AI辅助
  - _Requirements: 5.1-5.6, 6.1-6.4_

- [x] 4.6 创建 K6TabNoLongerCheck.vue K6-7 + K6TabAdjustment.vue + 附注（K6TabDisclosureListed/Soe.vue）
  - 不再满足检查+重分类+抽凭 / 调整分录 / 附注双版本
  - _Requirements: 7.1-7.4, 8.1-8.2_

### Phase 5: 后端

- [x] 5.1 创建 _k6_held_for_sale.py render策略 + RENDERER_DISPATCH注册（资产+负债口径）
  - _Requirements: 1.6_

- [x] 5.2 创建 _k6_import_export.py 导入导出3端点
  - _Requirements: 3.4, 8.2_

- [x] 5.3 创建 _k6_ai_generate.py AI生成 + 更新 k6-held-for-sale.yaml
  - section: classification-conclusion / impairment-conclusion / no-longer-eval / overall-opinion
  - _Requirements: 4.5, 5.6, 8.1_

### Phase 6: 集成联动

- [x] 6.1 EventBus: TB回写(持有待售资产+负债) + substantive:adjudicated → 附注
  - _Requirements: 2.6, 8.1_

- [x] 6.2 EventBus: adjustment:created → A13 + 附注subscribe刷新
  - _Requirements: 8.2_

- [x] 6.3 抽凭引擎 + 行级OCR + GtIndexChip跳转 + 双模式OO
  - _Requirements: 7.3_

### Phase 7: 测试验收

- [x] 7.1 单元测试：useK6FormulaEngine + useK6ClassificationEngine + useK6ImpairmentEngine
  - 账面价值 + 五条件分类 + 减值孰低非负 + 分摊 + 边界
  - _Requirements: CP-K6-01~07_

- [x] 7.2 集成测试：分类→减值→处置组分摊回连审定 + 审定回写
  - _Requirements: 2.7, 4.2, 5.5, 6.4_

- [x] 7.3 Playwright E2E：打开K6→审定→明细→初始确认→减值测试→处置组→保存
  - _Requirements: 全部_
