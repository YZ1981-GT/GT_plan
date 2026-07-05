# Implementation Plan: K11 资产减值损失底稿专属HTML精美组件

## Overview

K11资产减值损失底稿专属组件`k11-asset-impairment-loss`。K循环损益类减值汇总底稿（7有效sheet/1 xlsx/~80+公式）。

主入口 GtK11AssetImpairmentLoss.vue（sheetName v-if分发）+ 6个子组件 + composable分层（含减值汇总引擎）+ 后端3个py文件。

科目：6701资产减值损失（**损益类！取发生额**，从tb_ledger取数，借方=减值）
公式特征：审定=未审+AJE+RJE；减值损失发生额=借方发生-贷方发生；减值汇总=Σ各来源

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册+契约]
    P1 --> P2[Phase 2: 公式引擎(损益类)+减值汇总引擎+PBT]
    P2 --> P3[Phase 3: Composable层]
    P3 --> P4[Phase 4: Vue子组件]
    P1 --> P5[Phase 5: 后端(损益取数)]
    P4 --> P6[Phase 6: 集成联动]
    P5 --> P6
    P6 --> P7[Phase 7: 测试验收]
```

## Tasks

### Phase 0: 双源输入验证

- [ ] 0.1 openpyxl脚本读取K11资产减值损失.xlsx全部7 sheet
  - 产出：k11_structure_summary.json（确认K11-1 61公式/K11-2 17公式）
  - _Requirements: 双源输入流程_

- [ ] 0.2 K资产减值损失循环底稿模板库md交叉验证
  - 核对：损益类取数/减值汇总/源底稿联动F2/H1/I1/I3/商誉不可转回
  - 产出：k11_conflict_resolution.md
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [ ] 1.1 注册componentType和映射
  - wp_code_overrides: K11/K11-1~K11-3/K11A → 'k11-asset-impairment-loss'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry + GtK11AssetImpairmentLoss.vue骨架（sheetName v-if + selfLoad）
  - _Requirements: 1.1-1.10_

- [ ] 1.2 编写注册契约测试
  - _Requirements: 1.6-1.8_

### Phase 2: 公式引擎（损益类）+减值汇总引擎+PBT

- [ ] 2.1 创建 useK11FormulaEngine.ts（损益类！）
  - calcAuditedAmount / calcIncomeStatementOccurrence(dr,cr)=dr-cr / calcSourceVariance / calcSubtotal
  - _Requirements: 2.3-2.4, 3.2, 5.1-5.3, 6.3-6.4, 6.6-6.7_

- [ ] 2.2 创建 useK11ImpairmentSummaryEngine.ts
  - calcImpairmentSummary
  - _Requirements: 4.1, 4.3, 6.5_

- [ ]* 2.3 编写 Property CP-K11-01 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: k11-asset-impairment-loss, Property CP-K11-01: 审定数公式链**

- [ ]* 2.4 编写 Property CP-K11-02 PBT：损益类发生额（借-贷）
  - 生成器：debitOcc≥0, creditOcc≥0
  - 断言：calcIncomeStatementOccurrence(dr, cr) === dr - cr
  - **Feature: k11-asset-impairment-loss, Property CP-K11-02: 减值损失发生额=借方发生-贷方发生**

- [ ]* 2.5 编写 Property CP-K11-03 PBT：减值汇总
  - 断言：calcImpairmentSummary(sources) === Σsources
  - **Feature: k11-asset-impairment-loss, Property CP-K11-03: 减值汇总=Σ各来源**

- [ ]* 2.6 编写 Property CP-K11-04 PBT：源底稿核对差异
  - 断言：calcSourceVariance(k11, src) === k11 - src
  - **Feature: k11-asset-impairment-loss, Property CP-K11-04: 源底稿核对差异**

- [ ]* 2.7 编写 Property CP-K11-05 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: k11-asset-impairment-loss, Property CP-K11-05: 合计行恒等**

### Phase 3: Composable层

- [ ] 3.1 创建 useK11FormData.ts
  - selfLoad + checklist_responses + writebackTB(**发生额**，科目6701，从tb_ledger取数)
  - _Requirements: 1.9, 1.10, 2.6, 5.1-5.2_

- [ ] 3.2 创建 useK11CrossSheet.ts（adjudicationVsDetail / sourceReconcile vs F2/H1/I1/I3）
  - _Requirements: 2.5, 3.3, 4.2-4.4_

- [ ] 3.3 创建 useK11DualMode.ts + useK11ImportExport.ts
  - _Requirements: 6.2_

- [ ] 3.4 创建 useK11Adjudication.ts + useK11Detail.ts
  - _Requirements: 2~6 全部_

### Phase 4: Vue子组件

- [ ] 4.1 创建 K11TabIndex.vue 底稿目录（含减值来源汇总状态）
  - _Requirements: 1.2_

- [ ] 4.2 创建 K11TabAdjudication.vue 审定表K11-1（损益类61公式+发生额取数+按类别分行+源底稿GtIndexChip+TB回写+37行）
  - _Requirements: 2.1-2.8_

- [ ] 4.3 创建 K11TabDetail.vue 明细表K11-2（18列2区段+源核对+差异红标+商誉无转回+动态行+50行+导入导出）
  - _Requirements: 3.1-3.5, 4.5_

- [ ] 4.4 创建 K11TabAdjustment.vue 调整分录（借贷平衡+EventBus）
  - _Requirements: 6.2_

- [ ] 4.5 创建 K11TabDisclosureListed.vue + K11TabDisclosureSoe.vue 附注双版本
  - 按资产类别披露+自动取数
  - _Requirements: 6.1_

### Phase 5: 后端

- [ ] 5.1 创建 _k11_asset_impairment_loss.py render策略 + RENDERER_DISPATCH注册（**损益类取数**，tb_ledger发生额）
  - _Requirements: 1.6, 5.1_

- [ ] 5.2 创建 _k11_import_export.py 导入导出3端点
  - _Requirements: 6.2_

- [ ] 5.3 创建 _k11_ai_generate.py AI生成 + 更新 k11-asset-impairment-loss.yaml
  - section: impairment-summary-conclusion / overall-opinion
  - _Requirements: 6.1_

### Phase 6: 集成联动

- [ ] 6.1 EventBus: TB回写(6701发生额) + substantive:adjudicated → 附注
  - _Requirements: 2.6, 6.1_

- [ ] 6.2 EventBus: adjustment:created → A13 + subscribe各减值源底稿(F2/H1/I1/I3)减值计提
  - _Requirements: 6.2, 4.2_

- [ ] 6.3 各来源GtIndexChip跳转减值底稿 + 双模式OO
  - _Requirements: 2.7_

### Phase 7: 测试验收

- [ ] 7.1 单元测试：useK11FormulaEngine + useK11ImpairmentSummaryEngine
  - 损益方向(借-贷) + 减值汇总 + 源核对差异 + 边界
  - _Requirements: CP-K11-01~05_

- [ ] 7.2 集成测试：损益取数(发生额) + 源底稿核对联动 + 审定回写
  - _Requirements: 2.5, 4.2, 5.1_

- [ ] 7.3 Playwright E2E：打开K11→审定(验证发生额)→明细源核对→跳转源底稿→保存
  - _Requirements: 全部_
