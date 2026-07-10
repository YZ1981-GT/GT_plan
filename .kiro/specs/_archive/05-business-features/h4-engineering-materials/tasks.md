# Implementation Plan: H4 工程物资底稿专属HTML精美组件

## Overview

H4工程物资底稿专属组件`h4-engineering-materials`。H循环精简底稿（13个sheet/1 xlsx/~120+公式）。

主入口 GtH4EngineeringMaterials.vue（sheetName v-if分发，defineAsyncComponent lazy）+ 12个子组件 + 12个composable + 后端3个py文件。

科目：1605工程物资（借方/资产类）
公式特征：期末=期初+借方-贷方（资产类）；审定=未审+AJE+RJE；联动H2在建工程

## Tasks

### Phase 0: 双源输入验证

- [x] 0.1 openpyxl脚本读取H4工程物资.xlsx全部13 sheet
  - 提取：sheet名/列头/行数/公式单元格/合并区域/数据类型
  - 产出：h4_structure_summary.json（权威列头+公式清单）
  - 验证：13 sheet结构与本spec描述一致
  - _Requirements: 双源输入流程_

- [x] 0.2 H固定资产循环底稿模板库md交叉验证
  - 核对：审计目标/程序清单/联动关系/认定对应/交叉引用
  - 冲突解决：列名以xlsx为准，联动方向以md为准
  - 产出：h4_conflict_resolution.md（如有冲突）
  - _Requirements: 双源输入流程_

### Phase 1: 注册+契约测试

- [x] 1.1 注册componentType和映射
  - 在 `wp_code_overrides.json` 中将H4/H4-1~H4-9/H4A映射为'h4-engineering-materials'
  - 在 `VALID_COMPONENT_TYPES` 中注册'h4-engineering-materials'
  - 在 `htmlRendererRegistry.ts` 中注册 'h4-engineering-materials' → GtH4EngineeringMaterials 映射
  - 创建 `GtH4EngineeringMaterials.vue` 主入口骨架（sheetName prop v-if分发 + defineAsyncComponent lazy + selfLoad）
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9_

- [x] 1.2 编写注册契约测试
  - htmlRendererRegistry.spec.ts 验证'h4-engineering-materials'已注册
  - VALID_COMPONENT_TYPES契约验证
  - wp_code_overrides契约验证H4/H4-1~H4-9映射
  - RENDERER_DISPATCH注册验证
  - _Requirements: 1.6, 1.7, 1.8_

### Phase 2: 公式引擎+PBT

- [x] 2.1 创建 `composables/useH4FormulaEngine.ts`，实现全部纯函数
  - `calcAuditedAmount(unadj, aje, rje)` → 审定=未审+AJE+RJE
  - `calcAssetEndBalance(begin, debit, credit)` → 资产类期末=期初+借方-贷方
  - `calcTriangleReconciliation(begin, increase, decrease, end)` → 三角勾稽差额
  - `calcSubtotal(arr)` → 合计=SUM
  - `calcDiffRate(actual, expected)` → 差异率
  - `calcPriceDiffRate(transPrice, marketPrice)` → 关联价差率
  - _Requirements: 2.3-2.5, 5.2, 8.2_

- [x]* 2.2 编写 Property P1 PBT：审定数公式链
  - 生成器：fc.float({min:-1e9, max:1e9}) × 3 (unadj/aje/rje)
  - 断言：calcAuditedAmount(u, a, r) === u + a + r
  - **Feature: h4-engineering-materials, Property P1: 审定数公式链正确性**

- [x]* 2.3 编写 Property P2 PBT：资产类期末余额
  - 生成器：fc.float({min:0, max:1e9}) × 3
  - 断言：calcAssetEndBalance(b, d, c) === b + d - c
  - **Feature: h4-engineering-materials, Property P2: 资产类期末余额公式**

- [x]* 2.4 编写 Property P3 PBT：三角勾稽恒等
  - 生成器：fc.float({min:0, max:1e9}) × 3, end=begin+increase-decrease
  - 断言：calcTriangleReconciliation(b, i, d, b+i-d) === 0
  - **Feature: h4-engineering-materials, Property P3: 三角勾稽恒等**

- [x]* 2.5 编写 Property P4 PBT：合计行恒等
  - 生成器：fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:50})
  - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
  - **Feature: h4-engineering-materials, Property P4: 合计行恒等**

- [x]* 2.6 编写 Property P5 PBT：关联价差率
  - 生成器：fc.float({min:1, max:1e9}) × 2 (transPrice, marketPrice)
  - 断言：calcPriceDiffRate(t, m) === (t-m)/m * 100
  - **Feature: h4-engineering-materials, Property P5: 关联价差率公式**

- [x]* 2.7 编写 Property P6 PBT：差异率
  - 生成器：fc.float({min:1, max:1e9}) × 2 (actual, expected)
  - 断言：calcDiffRate(a, e) === (a-e)/e * 100
  - **Feature: h4-engineering-materials, Property P6: 差异率公式**

### Phase 3: Composable层

- [x] 3.1 创建 useH4FormData.ts
  - selfLoad逻辑（render-config?force_component_type=h4-engineering-materials）
  - checklist_responses CRUD（item_id前缀"H4-{sheet}-{field}"）
  - writebackTrialBalance（科目1605）
  - _Requirements: 1.9, 1.10, 2.8_

- [x] 3.2 创建 useH4CrossSheet.ts
  - adjudicationVsDetail computed（H4-1审定合计 vs H4-2明细合计）
  - additionVsAdjudication computed（H4-4增加 vs H4-1借方发生）
  - disposalVsAdjudication computed（H4-5减少 vs H4-1贷方发生）
  - _Requirements: 2.7, 3.5_

- [x] 3.3 创建 useH4DualMode.ts + useH4ImportExport.ts
  - 双模式切换逻辑（HTML ↔ OO）+ OO健康检查
  - 导入导出三级（导出模板/导出数据/导入数据）
  - _Requirements: 3.8, 7.6_

- [x] 3.4 创建 sheet-specific composables
  - useH4Adjudication.ts / useH4Detail.ts / useH4Adjustment.ts
  - useH4AdditionCheck.ts / useH4DisposalCheck.ts / useH4Stocktake.ts / useH4RelatedParty.ts
  - _Requirements: 2~8 全部_

### Phase 4: Vue子组件

- [x] 4.1 创建 H4TabIndex.vue 底稿目录
  - 13行sheet列表+进度条+GtIndexChip跳转
  - _Requirements: 1.2_

- [x] 4.2 创建 H4TabAdjudication.vue 审定表H4-1
  - 51公式自动计算+TB取数+回写+三角勾稽+跨sheet校验
  - _Requirements: 2.1-2.10_

- [x] 4.3 创建 H4TabDetail.vue 明细表H4-2
  - 67列→3区段Tab + 动态行 + 合计行 + 导入导出
  - _Requirements: 3.1-3.9_

- [x] 4.4 创建 H4TabAdjustment.vue 调整分录H4-3
  - 10列 + 借贷平衡 + EventBus + 导入导出
  - _Requirements: 4.1-4.6_

- [x] 4.5 创建 H4TabAdditionCheck.vue 增加检查H4-4
  - 19列 + 抽凭 + OCR + 差异计算 + 统计摘要
  - _Requirements: 5.1-5.7_

- [x] 4.6 创建 H4TabDisposalCheck.vue 减少检查H4-5
  - 29列2区块 + 联动H2 + GtIndexChip + 抽凭
  - _Requirements: 6.1-6.6_

- [x] 4.7 创建 H4TabStocktakeCheck.vue 盘点检查H4-6
  - 12列 + 差异自动计算 + 高亮
  - _Requirements: 7.1-7.3_

- [x] 4.8 创建 H4TabImpairment.vue + H4TabRecoverable.vue
  - OnlyOffice为主渲染 + HTML摘要视图
  - _Requirements: 7.4-7.6_

- [x] 4.9 创建 H4TabRelatedParty.vue 关联交易H4-9
  - 16列 + 价差率自动计算 + 异常高亮 + 统计摘要
  - _Requirements: 8.1-8.5_

- [x] 4.10 创建 H4TabDisclosureListed.vue + H4TabDisclosureSoe.vue
  - 附注嵌套表 + EventBus subscribe
  - _Requirements: 1.2_

### Phase 5: 后端

- [x] 5.1 创建 h4_engineering_materials_renderer.py
  - RENDERER_DISPATCH注册'h4-engineering-materials'
  - render逻辑：读取checklist_responses + TB数据 + 跨sheet合计
  - _Requirements: 1.6_

- [x] 5.2 创建 h4_engineering_materials.py 路由（3端点）
  - POST /h4/export-template：导出空白模板
  - POST /h4/export-data：导出当前数据
  - POST /h4/import-data：导入数据+校验
  - _Requirements: 3.8, 4.6_

### Phase 6: 集成

- [x] 6.1 EventBus集成
  - publish 'substantive:adjudicated'（H4-1审定完成→附注+报表）
  - publish 'adjustment:created'（H4-3调整分录→A13）
  - subscribe TB更新刷新H4-1取数
  - _Requirements: 2.8, 4.4_

- [x] 6.2 跨底稿联动
  - H4-5减少→H2在建工程GtIndexChip跳转
  - H4-1审定→TB回写
  - _Requirements: 6.3, 2.8_

### Phase 7: 测试

- [x] 7.1 单元测试：useH4FormulaEngine全部纯函数
  - 覆盖所有边界：零值/负值/大数/NaN防护
  - _Requirements: P1-P6_

- [x] 7.2 集成测试：跨sheet数据流
  - H4-1↔H4-2合计一致性
  - H4-3 AJE/RJE→H4-1同步
  - _Requirements: 2.7, 3.5, 4.5_

- [x] 7.3 Playwright E2E
  - 完整流程：打开H4→编辑审定表→验证公式→切换sheet→盘点→保存
  - _Requirements: 全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave-0", "tasks": ["0.1", "0.2"] },
    { "id": "wave-1", "tasks": ["1.1", "1.2"] },
    { "id": "wave-2", "tasks": ["2.1"] },
    { "id": "wave-3", "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7"] },
    { "id": "wave-4", "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "id": "wave-5", "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "4.10"] },
    { "id": "wave-6", "tasks": ["5.1", "5.2"] },
    { "id": "wave-7", "tasks": ["6.1", "6.2"] },
    { "id": "wave-8", "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```
