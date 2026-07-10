# Implementation Plan: H6 固定资产清理底稿专属HTML精美组件

## Overview

H6固定资产清理底稿专属组件`h6-asset-disposal-clearing`。H循环精简底稿（8 sheet/1 xlsx/~100+公式）。

主入口 GtH6AssetDisposalClearing.vue（sheetName v-if分发 + 过渡科目状态栏，defineAsyncComponent lazy）+ 7个子组件 + 9个composable + 后端3个py文件。

科目：1606固定资产清理（借方/资产类，过渡科目）
公式特征：过渡科目期末=0；净损益=收入-净值-费用-税费；联动H1处置+H10损益

## Tasks

### Phase 0: 双源输入验证

- [x] 0.1 openpyxl脚本读取H6固定资产清理.xlsx全部8 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 产出：h6_structure_summary.json
  - 验证：8 sheet结构与本spec描述一致
  - _Requirements: 双源输入流程_

- [x] 0.2 H固定资产循环底稿模板库md交叉验证
  - 核对：联动关系（H1处置/H10损益）/过渡科目规则
  - 产出：h6_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - wp_code_overrides: H6/H6-1~H6-4/H6A → 'h6-asset-disposal-clearing'
  - VALID_COMPONENT_TYPES注册 + htmlRendererRegistry注册
  - 创建 GtH6AssetDisposalClearing.vue 主入口骨架（sheetName v-if + 状态栏 + selfLoad）
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9_

- [x] 1.2 编写注册契约测试
  - htmlRendererRegistry / VALID_COMPONENT_TYPES / wp_code_overrides / RENDERER_DISPATCH
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+PBT

- [x] 2.1 创建 `composables/useH6FormulaEngine.ts`
  - calcAuditedAmount / calcAssetEndBalance / calcNetBookValue
  - calcDisposalGainLoss / calcSubtotal / isTransitBalanceZero
  - _Requirements: 2.3-2.6, 3.2_

- [x]* 2.2 编写 Property P1 PBT：审定数公式链
  - 生成器：fc.float({min:-1e9, max:1e9}) × 3
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: h6-asset-disposal-clearing, Property P1: 审定数公式链**

- [x]* 2.3 编写 Property P2 PBT：资产类期末余额
  - 生成器：fc.float({min:0, max:1e9}) × 3
  - 断言：calcAssetEndBalance(b, d, c) === b + d - c
  - **Feature: h6-asset-disposal-clearing, Property P2: 资产类期末余额**

- [x]* 2.4 编写 Property P3 PBT：清理净损益
  - 生成器：fc.float({min:0, max:1e9}) × 4 (income, netValue, expenses, tax)
  - 断言：calcDisposalGainLoss(i, nv, e, t) === i - nv - e - t
  - **Feature: h6-asset-disposal-clearing, Property P3: 清理净损益公式**

- [x]* 2.5 编写 Property P4 PBT：过渡科目零余额判定
  - 生成器：fc.float({min:-1e9, max:1e9})
  - 断言：isTransitBalanceZero(0)===true; isTransitBalanceZero(≠0)===false
  - **Feature: h6-asset-disposal-clearing, Property P4: 过渡科目零余额判定**

- [x]* 2.6 编写 Property P5 PBT：净账面价值
  - 生成器：fc.float({min:0, max:1e9}) × 2
  - 断言：calcNetBookValue(cost, dep) === cost - dep
  - **Feature: h6-asset-disposal-clearing, Property P5: 净账面价值公式**

### Phase 3: Composable层

- [x] 3.1 创建 useH6FormData.ts
  - selfLoad + checklist_responses CRUD + writebackTB(1606)
  - _Requirements: 1.9, 1.10, 2.8_

- [x] 3.2 创建 useH6CrossSheet.ts
  - adjudicationVsDetail / transitAccountStatus / disposalGainLossVsH10
  - _Requirements: 2.5, 2.7, 3.7_

- [x] 3.3 创建 useH6DualMode.ts + useH6ImportExport.ts
  - 双模式切换 + 导入导出三级
  - _Requirements: 3.6_

- [x] 3.4 创建 sheet-specific composables
  - useH6Adjudication / useH6Detail / useH6Adjustment / useH6Check
  - _Requirements: 2~4 全部_

### Phase 4: Vue子组件

- [x] 4.1 创建 H6TabIndex.vue 底稿目录
  - 8行sheet列表+进度条+过渡科目状态指示
  - _Requirements: 1.2, 6.1_

- [x] 4.2 创建 H6TabAdjudication.vue 审定表H6-1
  - 59公式+过渡科目期末=0校验+H10交叉验证+TB回写
  - _Requirements: 2.1-2.9_

- [x] 4.3 创建 H6TabDetail.vue 明细表H6-2
  - 25列2区块+净损益计算+GtIndexChip(H1/H10)+动态行+导入导出
  - _Requirements: 3.1-3.7_

- [x] 4.4 创建 H6TabAdjustment.vue 调整分录H6-3
  - 10列+借贷平衡+EventBus
  - _Requirements: 4.1-4.2_

- [x] 4.5 创建 H6TabCheck.vue 检查表H6-4
  - 18列+合规/不合规选择+统计摘要+与H6-2联动
  - _Requirements: 4.3-4.6_

- [x] 4.6 创建 H6TabDisclosureListed.vue + H6TabDisclosureSoe.vue
  - 附注嵌套表
  - _Requirements: 1.2_

### Phase 5: 后端

- [x] 5.1 创建 h6_asset_disposal_clearing_renderer.py
  - RENDERER_DISPATCH注册 + 过渡科目校验逻辑
  - _Requirements: 1.6, 6.3_

- [x] 5.2 创建 h6_asset_disposal_clearing.py 路由
  - POST /h6/export-template | /h6/export-data | /h6/import-data
  - _Requirements: 3.6_

### Phase 6: 集成

- [x] 6.1 EventBus集成
  - subscribe H1 'disposal:initiated'（H1-8→H6自动创建行）
  - publish 'disposal:completed'（H6结转→H10）
  - publish 'substantive:adjudicated'（H6-1→附注）
  - publish 'adjustment:created'（H6-3→A13）
  - _Requirements: 5.1-5.4_

- [x] 6.2 跨底稿GtIndexChip
  - H6-2 → H1-8(联动H1编号) + H10(联动H10编号)
  - _Requirements: 5.1, 5.2_

### Phase 7: 测试

- [x] 7.1 单元测试：useH6FormulaEngine全部纯函数
  - _Requirements: P1-P5_

- [x] 7.2 集成测试：过渡科目+跨底稿联动
  - 期末=0校验 / H1→H6→H10事件链 / 审定↔明细一致性
  - _Requirements: 2.5, 5.1-5.4, 6.1-6.3_

- [x] 7.3 Playwright E2E
  - 完整流程：打开H6→过渡科目状态→编辑→检查→保存→验证H10联动
  - _Requirements: 全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave-0", "tasks": ["0.1", "0.2"] },
    { "id": "wave-1", "tasks": ["1.1", "1.2"] },
    { "id": "wave-2", "tasks": ["2.1"] },
    { "id": "wave-3", "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6"] },
    { "id": "wave-4", "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "id": "wave-5", "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6"] },
    { "id": "wave-6", "tasks": ["5.1", "5.2"] },
    { "id": "wave-7", "tasks": ["6.1", "6.2"] },
    { "id": "wave-8", "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```
