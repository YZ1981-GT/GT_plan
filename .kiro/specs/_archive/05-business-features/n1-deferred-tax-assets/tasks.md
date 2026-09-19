`
# Implementation Plan: N1 递延所得税资产底稿专属HTML精美组件

## Overview

N1递延所得税资产底稿专属组件`n1-deferred-tax-assets`。N税费循环资产类底稿（9 sheet/1 xlsx/~120+公式）。

主入口 GtN1DeferredTaxAssets.vue（sheetName v-if，defineAsyncComponent lazy）+ 8个子组件 + 11个composable + 后端3个py文件。

科目：1811递延所得税资产（**借方/资产类**！取期末余额）
公式特征：审定=未审+AJE+RJE；资产类期末=期初+借方-贷方；递延所得税=暂时性差异×税率；可确认额=min(未弥补亏损,未来应纳税所得额)×税率

## Tasks

### Phase 0: 双源输入验证

- [x] 0.1 openpyxl脚本读取N1递延所得税资产.xlsx全部9 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 确认：审定表N1-1(35×15,78公式)/明细表N1-2(52×14,14公式)/测算表N1-4(63×15,21公式)/亏损检查N1-5(30×13)
  - 产出：n1_structure_summary.json（权威列头+公式清单）
  - _Requirements: 双源输入流程_

- [x] 0.2 N税费循环底稿模板库md交叉验证
  - 核对：资产类取数规则/递延税测算逻辑/可弥补亏损确认/N3对应/N5核对
  - 冲突解决：列名以xlsx为准，联动方向以md为准
  - 产出：n1_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: N1/N1-1~N1-5/N1A → 'n1-deferred-tax-assets'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry注册
  - 创建 GtN1DeferredTaxAssets.vue 骨架（sheetName prop v-if分发 + defineAsyncComponent lazy + selfLoad）
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9, 1.11_

- [x] 1.2 编写注册契约测试
  - htmlRendererRegistry.spec.ts / VALID_COMPONENT_TYPES / wp_code_overrides / RENDERER_DISPATCH
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+税务引擎+PBT

- [x] 2.1 创建 `composables/useN1FormulaEngine.ts`（资产类！）
  - calcAuditedAmount(u,a,r)=u+a+r
  - calcAssetEndBalance(begin,debit,credit)=begin+debit-credit（资产类期末）
  - calcSubtotal / calcProportion
  - _Requirements: 1.5, 2.3, 2.4, 8.1-8.4_

- [x] 2.2 创建 `composables/useN1DeferredTaxEngine.ts`（核心税务引擎）
  - calcTemporaryDifference(bookValue,taxBase)=bookValue-taxBase
  - calcDeferredTax(tempDiff,taxRate)=tempDiff×taxRate
  - calcWeightedAvgRate
  - _Requirements: 3.2, 4.2, 4.3_

- [x] 2.3 创建 `composables/useN1LossCompensationEngine.ts`
  - calcUnrecoveredLoss(lossAmount,recovered)=lossAmount-recovered
  - calcRecognizableAsset(unrecovered,futureTaxableIncome,taxRate)=min(unrecovered,futureTaxableIncome)×taxRate
  - isCompensationExpired(lossYear,currentYear,maxYears)
  - _Requirements: 5.2, 5.3_

- [x] 2.4 编写 Property P1 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Validates: Requirements 2.3**

- [x] 2.5 编写 Property P2 PBT：资产类期末余额（期初+借-贷）
  - 生成器：fc.float({min:0,max:1e9}) × 3 (begin, debit, credit)
  - 断言：calcAssetEndBalance(b, d, c) === b + d - c
  - **Validates: Requirements 2.4, 8.1**

- [x] 2.6 编写 Property P3 PBT：暂时性差异
  - 断言：calcTemporaryDifference(bv, tb) === bv - tb
  - **Validates: Requirements 3.2, 4.2**

- [x] 2.7 编写 Property P4 PBT：递延所得税=差异×税率
  - 生成器：diff∈R, rate∈[0,0.25]
  - 断言：calcDeferredTax(diff, rate) === diff × rate
  - **Validates: Requirements 4.3**

- [x] 2.8 编写 Property P5 PBT：合计行恒等
  - 断言：calcSubtotal(arr) === Σarr
  - **Validates: Requirements 2.5**

- [x] 2.9 编写 Property P6 PBT：未弥补亏损
  - 断言：calcUnrecoveredLoss(loss, rec) === max(0, loss - rec)
  - **Validates: Requirements 5.2**

- [x] 2.10 编写 Property P7 PBT：可确认递延税资产（min限额×税率）
  - 生成器：unrec>0, fti>0, rate∈(0,0.25]
  - 断言：calcRecognizableAsset(unrec, fti, rate) === min(unrec, fti) × rate
  - **Validates: Requirements 5.2**

### Phase 3: Composable层

- [x] 3.1 创建 useN1FormData.ts
  - selfLoad + checklist_responses + writebackTB(**期末余额**，科目1811借方)
  - _Requirements: 1.9, 1.10, 2.7, 8.1-8.3_

- [x] 3.2 创建 useN1CrossSheet.ts
  - adjudicationVsDetail / adjudicationVsCalcTable / lossCheckToCalcTable / n1ToN3Correspondence / deferredTaxChange(供N5)
  - _Requirements: 2.5, 2.6, 4.4, 4.6, 5.5, 7.1-7.5_

- [x] 3.3 创建 useN1DualMode.ts + useN1ImportExport.ts
  - 双模式 + 导入导出三级
  - _Requirements: 3.4_

- [x] 3.4 创建 sheet-specific composables
  - useN1Adjudication / useN1Detail / useN1CalcTable / useN1LossCheck
  - _Requirements: 2~5 全部_

### Phase 4: Vue子组件

- [x] 4.1 创建 N1TabIndex.vue 底稿目录
  - 9行+进度条+联动状态
  - _Requirements: 1.2_

- [x] 4.2 创建 N1TabAdjudication.vue 审定表N1-1
  - 78公式+资产类期末取数+N1-2/N1-4交叉验证+N3对应提示+TB回写
  - _Requirements: 2.1-2.9_

- [x] 4.3 创建 N1TabDetail.vue 明细表N1-2
  - 14列14公式+差异×税率+动态行+统计摘要+导入导出
  - _Requirements: 3.1-3.6_

- [x] 4.4 创建 N1TabCalcTable.vue 测算表N1-4（核心）
  - 63×15，21公式+资产/负债双部分测算+确认条件判断+回填N1-1/联动N3
  - _Requirements: 4.1-4.6_

- [x] 4.5 创建 N1TabLossCheck.vue 可弥补亏损检查N1-5
  - 30×13+未弥补/可确认测算+弥补期限判断+谨慎性警告+回填N1-4
  - _Requirements: 5.1-5.6_

- [x] 4.6 创建 N1TabAdjustment.vue 调整分录N1-3
  - 借贷平衡+EventBus+双向同步N1-1
  - _Requirements: 6.1_


- [x] 4.7 创建 N1TabDisclosureListed/Soe.vue
  - 附注上市(54×11)/国企(74×256)+未确认差异及亏损披露
  - _Requirements: 6.2-6.4_

### Phase 5: 后端

- [x] 5.1 创建 n1_deferred_tax_assets_renderer.py
  - RENDERER_DISPATCH注册 + **资产类取数逻辑**（期末余额！1811借方）
  - _Requirements: 1.6, 8.2_

- [x] 5.2 创建 n1_deferred_tax_assets.py 路由
  - 导出模板/导出数据/导入数据（axios+Authorization）
  - _Requirements: 3.4_

- [x] 5.3 创建 n1_deferred_tax_assets_service.py
  - 资产类取数（tb_balance期末余额）+ 递延税测算 + 亏损确认 + 跨底稿合计
  - _Requirements: 4.1-4.6, 5.1-5.6, 8.1-8.4_

### Phase 6: 集成

- [x] 6.1 EventBus集成
  - publish 'substantive:adjudicated'（N1-1→附注）
  - publish 'adjustment:created'（N1-3→A13）
  - publish 'deferred-tax:asset-updated'（→N5-8递延税费用核对）
  - subscribe 'disclosure:refresh'
  - _Requirements: 6.1, 6.3, 7.2, 7.4_

- [x] 6.2 跨底稿GtIndexChip
  - N1-4 ↔ N3-2明细（同源差异分列）
  - N1-1本期变动额 → N5-8递延税费用核对
  - _Requirements: 7.1, 7.3, 7.5_

- [x] 6.3 六大集成标准
  - 版本链useVersionTrail + 附注EventBus + 复核对话provide/inject + 导入导出
  - _Requirements: 1.5, 6.1-6.4_

### Phase 7: 测试

- [x] 7.1 单元测试：useN1FormulaEngine + useN1DeferredTaxEngine + useN1LossCompensationEngine
  - 资产类方向(期初+借-贷) + 差异×税率 + 谨慎性限额 + 边界(零值/大数/税率边界)
  - _Requirements: P1-P7_

- [x] 7.2 集成测试：资产类取数+跨底稿联动
  - 期末余额取数正确性 / N1-4→N1-1/N3回填 / N1-5→N1-4 / 本期变动→N5核对
  - _Requirements: 2.5-2.6, 4.4, 5.5, 7.1-7.5, 8.1-8.4_

- [x] 7.3 Playwright E2E
  - 完整流程：打开N1→审定(验证资产类取数)→明细→测算表(差异×税率)→亏损检查→保存
  - _Requirements: 全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave-1", "name": "Phase 0-1: 双源输入+注册", "tasks": ["0.1", "0.2", "1.1", "1.2"] },
    { "id": "wave-2", "name": "Phase 2: 公式引擎+PBT", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10"] },
    { "id": "wave-3", "name": "Phase 3: Composable", "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "id": "wave-4", "name": "Phase 4: Vue组件", "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7"] },
    { "id": "wave-5", "name": "Phase 5: 后端", "tasks": ["5.1", "5.2", "5.3"] },
    { "id": "wave-6", "name": "Phase 6: 集成", "tasks": ["6.1", "6.2", "6.3"] },
    { "id": "wave-7", "name": "Phase 7: 测试", "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```
