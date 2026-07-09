# Implementation Plan: L7 其他非流动负债底稿专属HTML精美组件

## Overview

L7其他非流动负债底稿专属组件`l7-other-noncurrent-liabilities`（8 sheet/1 xlsx/~90+公式）。L筹资循环最简标准负债底稿。

主入口 GtL7OtherNoncurrentLiabilities.vue（sheetName v-if，lazy）+ 7个子组件 + 9个composable + 后端3个py文件。

科目：2801其他非流动负债（贷方/负债类）
公式特征：**负债类贷方**期末=期初+贷方-借方

## Tasks

### Phase 0: 双源输入验证

- [x] 0.1 openpyxl脚本读取L7其他非流动负债.xlsx全部8 sheet
  - 提取结构 + 确认审定表L7-1(74公式,实际比预估多2个差额公式)+明细表L7-2结构(46公式,25×27)
  - 产出：l7_structure_summary.json
  - _Requirements: 双源输入流程_

- [x] 0.2 L筹资循环底稿模板库md交叉验证
  - 核对：负债类方向/标准审定流程
  - 产出：l7_conflict_resolution.md
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: L7/L7-1~L7-4/L7A → 'l7-other-noncurrent-liabilities'
  - VALID_COMPONENT_TYPES + htmlRendererRegistry注册
  - 创建 GtL7OtherNoncurrentLiabilities.vue 骨架（sheetName v-if + selfLoad）
  - _Requirements: 1.1-1.11_

- [x] 1.2 编写注册契约测试
  - htmlRendererRegistry / VALID_COMPONENT_TYPES / wp_code_overrides / RENDERER_DISPATCH
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+PBT

- [x] 2.1 创建 `useL7FormulaEngine.ts`（负债类！）
  - calcAuditedAmount / calcLiabilityEndBalance(b,cr,dr)=b+cr-dr / calcSubtotal
  - _Requirements: 2.3-2.4, 5.1-5.3_

- [x] 2.2 编写 Property P1 PBT：审定数公式链
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: l7-other-noncurrent-liabilities, Property P1: 审定数公式链**

- [x] 2.3 编写 Property P2 PBT：负债类期末（贷方！）
  - 生成器：fc.float({min:0, max:1e9}) × 3
  - 断言：calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
  - **Feature: l7-other-noncurrent-liabilities, Property P2: 负债类贷方期末余额**

- [x] 2.4 编写 Property P3 PBT：小计求和
  - 断言：calcSubtotal(arr) === Σarr
  - **Feature: l7-other-noncurrent-liabilities, Property P3: 分类小计**

- [x] 2.5 编写 Property P4 PBT：明细合计=审定合计
  - 断言：Σ明细.期末 === 审定表合计.期末
  - **Feature: l7-other-noncurrent-liabilities, Property P4: 明细审定勾稽**

- [x] 2.6 编写 Property P5 PBT：期末非负
  - 生成器：begin≥0, credit≥0, debit≤begin+credit
  - 断言：calcLiabilityEndBalance(b, cr, dr) >= 0
  - **Feature: l7-other-noncurrent-liabilities, Property P5: 期末非负**

### Phase 3: Composable层

- [x] 3.1 创建 useL7FormData.ts
  - selfLoad + checklist_responses + writebackTB(2801)
  - _Requirements: 1.9, 1.10, 2.6_

- [x] 3.2 创建 useL7CrossSheet.ts
  - adjudicationVsDetail
  - _Requirements: 2.5, 3.5_

- [x] 3.3 创建 useL7DualMode.ts + useL7ImportExport.ts
  - _Requirements: 5.4, 5.5_

- [x] 3.4 创建 sheet-specific composables
  - useL7Adjudication / useL7Detail / useL7OtherCheck / useL7Adjustment
  - _Requirements: 2~4 全部_

### Phase 4: Vue子组件

- [x] 4.1 创建 L7TabIndex.vue 底稿目录
  - 8行+进度条
  - _Requirements: 1.2_

- [x] 4.2 创建 L7TabAdjudication.vue 审定表L7-1
  - 负债类单区块+项目小计+TB回写
  - _Requirements: 2.1-2.7_

- [x] 4.3 创建 L7TabDetail.vue 明细表L7-2
  - 27列区段Tab切换+动态行+导入导出
  - _Requirements: 3.1-3.5_

- [x] 4.4 创建 L7TabOtherCheck.vue 检查表L7-4
  - 核对清单+结论区+AI辅助
  - _Requirements: 4.1-4.2_

- [x] 4.5 创建 L7TabAdjustment.vue + L7TabDisclosureListed/Soe.vue
  - 调整借贷平衡 + 附注上市/国企切换
  - _Requirements: 4.3-4.5_

### Phase 5: 后端

- [x] 5.1 创建 l7_other_noncurrent_liabilities_renderer.py
  - RENDERER_DISPATCH注册 + 负债类公式验证
  - _Requirements: 1.6_

- [x] 5.2 创建 l7_other_noncurrent_liabilities.py 路由
  - 导出模板/导出数据/导入数据
  - _Requirements: 5.5_

- [x] 5.3 创建 l7_other_noncurrent_liabilities_service.py
  - 负债类公式验证
  - _Requirements: 2.4_

### Phase 6: 集成

- [x] 6.1 EventBus集成
  - publish 'substantive:adjudicated' / 'adjustment:created'
  - subscribe 附注刷新
  - _Requirements: 2.6, 2.7_

- [x] 6.2 跨底稿联动
  - L7审定 → TB回写(2801)
  - _Requirements: 2.6_

- [x] 6.3 版本链+复核对话集成
  - useVersionTrail(autoSnapshot) + provide openReviewDialog
  - _Requirements: 5.6_

### Phase 7: 测试

- [x] 7.1 单元测试：useL7FormulaEngine
  - 负债类方向 + 小计 + 明细勾稽
  - _Requirements: P1-P5_

- [x] 7.2 集成测试：审定→明细勾稽 + TB回写
  - _Requirements: 2.5, 2.6_

- [x] 7.3 Playwright E2E
  - 完整流程：打开L7→审定→明细→检查表→保存
  - _Requirements: 全部_

## Task Dependency Graph

```mermaid
graph TD
    P0[Phase 0: 双源输入] --> P1[Phase 1: 注册]
    P1 --> P2[Phase 2: 公式引擎+PBT]
    P2 --> P3[Phase 3: Composable]
    P3 --> P4[Phase 4: Vue组件]
    P1 --> P5[Phase 5: 后端]
    P4 --> P6[Phase 6: 集成]
    P5 --> P6
    P6 --> P7[Phase 7: 测试]
```
