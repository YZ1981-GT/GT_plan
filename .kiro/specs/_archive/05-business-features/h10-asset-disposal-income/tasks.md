# Implementation Plan: H10 资产处置损益底稿专属HTML精美组件

## Overview

H10资产处置损益底稿专属组件`h10-asset-disposal-income`。H循环唯一损益类底稿（8 sheet/1 xlsx/~100+公式）。

主入口 GtH10AssetDisposalIncome.vue（sheetName v-if，defineAsyncComponent lazy）+ 7个子组件 + 10个composable + 后端3个py文件。

科目：6115资产处置损益（**损益类/贷方科目**！取发生额非余额）
公式特征：审定=未审+AJE+RJE；处置损益=收入-净值-费用-税费；损益净额=贷方发生-借方发生

## Tasks

### Phase 0: 双源输入验证

- [x] 0.1 openpyxl脚本读取H10资产处置损益.xlsx全部8 sheet
  - 提取结构+确认审定表69公式/明细表26公式
  - 产出：h10_structure_summary.json
  - _Requirements: 双源输入流程_

- [x] 0.2 H固定资产循环底稿模板库md交叉验证
  - 核对：损益类取数规则/H1~H8联动/H6清理结转
  - 产出：h10_conflict_resolution.md
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: H10/H10-1~H10-4/H10A → 'h10-asset-disposal-income'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry注册
  - 创建 GtH10AssetDisposalIncome.vue 骨架（sheetName v-if + selfLoad）
  - _Requirements: 1.1-1.10_

- [x] 1.2 编写注册契约测试
  - htmlRendererRegistry / VALID_COMPONENT_TYPES / wp_code_overrides / RENDERER_DISPATCH
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+PBT

- [x] 2.1 创建 `useH10FormulaEngine.ts`（损益类！）
  - calcAuditedAmount / calcIncomeStatementNet(cr,dr)=cr-dr / calcSubtotal
  - _Requirements: 2.3-2.4, 6.1-6.4_

- [x] 2.2 创建 `useH10DisposalCalcEngine.ts`
  - calcDisposalGainLoss / calcNetBookValue / calcGainLossRate
  - _Requirements: 7.1-7.6_

- [x]* 2.3 编写 Property P1 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: h10-asset-disposal-income, Property P1: 审定数公式链**

- [x]* 2.4 编写 Property P2 PBT：损益类净发生额（贷-借）
  - 生成器：fc.float({min:0, max:1e9}) × 2 (credit, debit)
  - 断言：calcIncomeStatementNet(cr, dr) === cr - dr
  - **Feature: h10-asset-disposal-income, Property P2: 损益净发生额（贷-借）**

- [x]* 2.5 编写 Property P3 PBT：处置净损益
  - 生成器：fc.float({min:0, max:1e9}) × 4 (income, netValue, expenses, tax)
  - 断言：calcDisposalGainLoss(i, nv, e, t) === i - nv - e - t
  - **Feature: h10-asset-disposal-income, Property P3: 处置净损益公式**

- [x]* 2.6 编写 Property P4 PBT：净账面值
  - 生成器：fc.float({min:0, max:1e9}) × 2
  - 断言：calcNetBookValue(cost, dep) === cost - dep
  - **Feature: h10-asset-disposal-income, Property P4: 净账面值**

- [x]* 2.7 编写 Property P5 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: h10-asset-disposal-income, Property P5: 合计行恒等**

- [x]* 2.8 编写 Property P6 PBT：处置损益率
  - 生成器：gainLoss∈R, cost>0
  - 断言：calcGainLossRate(gl, cost) === gl/cost × 100
  - **Feature: h10-asset-disposal-income, Property P6: 处置损益率**

### Phase 3: Composable层

- [x] 3.1 创建 useH10FormData.ts
  - selfLoad + checklist_responses + writebackTB(**发生额**，科目6115)
  - 注意：TB回写使用发生额而非期末余额！
  - _Requirements: 1.9, 1.10, 2.8, 6.2-6.3_

- [x] 3.2 创建 useH10CrossSheet.ts
  - adjudicationVsDetail / h10VsH6 / h10VsSourceWps(H1~H8)
  - _Requirements: 2.6, 2.7, 2.10, 5.5_

- [x] 3.3 创建 useH10DualMode.ts + useH10ImportExport.ts
  - 双模式 + 导入导出三级
  - _Requirements: 3.5_

- [x] 3.4 创建 sheet-specific composables
  - useH10Adjudication / useH10Detail / useH10Adjustment / useH10Check
  - _Requirements: 2~4 全部_

### Phase 4: Vue子组件

- [x] 4.1 创建 H10TabIndex.vue 底稿目录
  - 8行+进度条+来源追溯链状态（显示各源底稿编制状态）
  - _Requirements: 1.2_

- [x] 4.2 创建 H10TabAdjudication.vue 审定表H10-1
  - 69公式+损益取数+发生额+H6交叉验证+各源底稿合计验证+TB回写
  - _Requirements: 2.1-2.10_

- [x] 4.3 创建 H10TabDetail.vue 明细表H10-2
  - 36列3区段26公式+来源底稿GtIndexChip+动态行+统计摘要+导入导出
  - _Requirements: 3.1-3.7_

- [x] 4.4 创建 H10TabAdjustment.vue 调整分录H10-3
  - 10列+借贷平衡+EventBus+双向同步H10-1
  - _Requirements: 4.1_

- [x] 4.5 创建 H10TabCheck.vue 检查表H10-4
  - 80行20列+合规判断+与H10-2联动+抽凭+不合规摘要
  - _Requirements: 4.2-4.6_

- [x] 4.6 创建 H10TabDisclosureListed/Soe.vue
  - 附注
  - _Requirements: 1.2_

### Phase 5: 后端

- [x] 5.1 创建 h10_asset_disposal_income_renderer.py
  - RENDERER_DISPATCH注册 + **损益类取数逻辑**（发生额！）
  - _Requirements: 1.6, 6.2_

- [x] 5.2 创建 h10_asset_disposal_income.py 路由
  - 导出模板/导出数据/导入数据
  - _Requirements: 3.5_

- [x] 5.3 创建 h10_asset_disposal_income_service.py
  - 损益取数（tb_ledger发生额）+ 处置验证 + 跨底稿合计
  - _Requirements: 6.1-6.4, 7.1-7.6_

### Phase 6: 集成

- [x] 6.1 EventBus集成
  - subscribe H6 'disposal:completed'（自动创建H10明细行）
  - subscribe H1~H8 处置事件（更新来源数据）
  - publish 'substantive:adjudicated'（H10-1→附注）
  - publish 'adjustment:created'（H10-3→A13）
  - _Requirements: 5.1-5.5_

- [x] 6.2 跨底稿GtIndexChip
  - H10-2每行 ↔ 来源底稿减少检查对应行
  - H10-2 → H6清理明细
  - _Requirements: 5.1-5.2, 3.3_

### Phase 7: 测试

- [x] 7.1 单元测试：useH10FormulaEngine + useH10DisposalCalcEngine
  - 损益类方向(贷-借) + 处置损益 + 边界(零值/大数)
  - _Requirements: P1-P6_

- [x] 7.2 集成测试：损益取数+跨底稿联动
  - 发生额取数正确性 / H6→H10事件链 / 各源底稿合计一致
  - _Requirements: 2.7, 2.10, 5.2-5.5, 6.1-6.4_

- [x] 7.3 Playwright E2E
  - 完整流程：打开H10→审定(验证损益取数)→明细(跳转来源)→检查→保存
  - _Requirements: 全部_

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册]
    P1 --> P2[Phase 2: 公式引擎(损益类!)+处置引擎+PBT]
    P2 --> P3[Phase 3: Composable]
    P3 --> P4[Phase 4: Vue组件]
    P1 --> P5[Phase 5: 后端(损益取数)]
    P4 --> P6[Phase 6: 集成+H1~H8联动]
    P5 --> P6
    P6 --> P7[Phase 7: 测试]
```

## 验证记录（2026-07-05）

- 前端 vitest：24+ passed（PBT 9 + 集成 17+）
- 后端 pytest：12+ passed（注册契约 3 + API 9+）
- Playwright E2E：13+ passed（含底稿目录、附注、CHK-03/04）
- Phase 0：`h10_structure_summary.json` + `h10_conflict_resolution.md`
