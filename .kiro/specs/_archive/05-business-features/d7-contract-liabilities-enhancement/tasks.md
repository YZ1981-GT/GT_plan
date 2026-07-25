# Implementation Plan

## Overview

D7 合同负债两大增强的实现任务：**动态账龄全链路**（D7-2 明细/D7-1 审定/跨表聚合/D7-5 长期挂账/后端导入导出账龄列头，接入 `useAgingConfig` subject="D7" 2-period，复用 D3 已落地机制）与**调整分录按性质/账龄路由**（D7-3 增 natureType/agingBand，审定表纯 computed 从 `crossSheet.adjustmentTotals` 双分组派生，移除 `onAdjustmentCreated` 累加器）。

铁律：Windows 用 `python`（非 python3），命令分隔用 `;`；前端改动后 `get_diagnostics` 全清 + Vite transform 200；后端 `python -c "import ast; ast.parse(...)"` 校验；不 commit。属性测试前端 `fast-check` numRuns≥100 / 后端 `hypothesis` 显式 `@settings(max_examples=100)`。复用 D3 动态账龄机制，禁止新造平行实现。带 `*` 为 optional（仍需完成）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "name": "基础设施", "tasks": ["1", "2"], "dependsOn": [] },
    { "wave": 1, "name": "明细层", "tasks": ["3"], "dependsOn": [0] },
    { "wave": 2, "name": "跨表聚合", "tasks": ["4"], "dependsOn": [0, 1] },
    { "wave": 3, "name": "审定表与调整分录", "tasks": ["5", "6"], "dependsOn": [0, 1, 2] },
    { "wave": 4, "name": "长期挂账与列偏好", "tasks": ["7", "8"], "dependsOn": [1, 2] },
    { "wave": 5, "name": "后端导入导出", "tasks": ["9"], "dependsOn": [0] },
    { "wave": 6, "name": "刷新与只读接线", "tasks": ["10"], "dependsOn": [1, 3] },
    { "wave": 7, "name": "属性与单元测试", "tasks": ["11", "12"], "dependsOn": [3, 4, 5] },
    { "wave": 8, "name": "端到端验证", "tasks": ["13"], "dependsOn": [6, 7] }
  ]
}
```

## Tasks

- [x] 1. D7 纳入项目级账龄配置（2-period subject，前后端注册）
  - 前端 `useAgingConfig.ts`：`_applyDefault()` 分支扩展为 `subject === 'D3' || subject === 'F1' || subject === 'D7'` → THREE_YEAR；确认 `THREE_PERIOD_SUBJECTS` 不含 D7（`segmentsToBands('D7')` 产出 `currentField=''` 的 2-period bands）。
  - 后端 `aging_config_service.py`：`DEFAULT_SUBJECT_PRESETS` 新增 `"D7": AgingPreset.THREE_YEAR`。
  - 后端 `_cycle_import_export_common.py`：确认 `_THREE_PERIOD_SUBJECTS` 不含 D7，`subject_aging_periods('D7')` 返回 `["prior", "audited"]`。
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. 新增 D7 扁平→nested 账龄迁移薄封装 `migrateD7FlatToNested`
  - 在 `useAgingMigration.ts` 新增 `migrateD7FlatToNested(raw)`：仿 `migrateD2FlatToNested` 但仅映射 2-period 8 字段（`priorAging1~4`→`agingPrior.{within1/y1to2/y2to3/over3}`、`endAging1~4`→`agingAudited.{...}`，见 design §Data Models 迁移映射表）。
  - 规则：行已含 nested → 以 nested 为准忽略扁平；仅含扁平 → 先 `migrateD7FlatToNested` 再 `migrateD3F1Keys(_, segments)` 对齐当前段；输出不再含扁平 key。
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 3. `useD7Detail.ts` 改造为 nested keyed 动态账龄
  - `DetailRow` 用 `agingPrior: AgingData` / `agingAudited: AgingData` 替代 `priorAging1~4` / `endAging1~4`（见 design §2）。
  - 引入 `useAgingConfig(projectId, 'D7')` 取 `segments`/`bands`；`normalizeRow(raw, segments)` 走 Task 2 迁移链；`createEmptyRow(segments)` 按段零初始化。
  - `updateCell` 支持 `agingPrior.{segKey}` / `agingAudited.{segKey}` 嵌套路径写入；`rows` 加载 watch 依赖 `[D7-2-rows.remark, segments]`，`!segments.value.length` 时不解析。
  - `sumRows`/`totalRow`/`verificationRow` 账龄合计按 `segments` 动态 SUM；序列化仅输出 nested。
  - _Requirements: 2.1, 2.2, 2.3, 8.3_

- [x] 4. `useD7CrossSheet.ts` 账龄聚合动态化 + `adjustmentTotals` 双分组
  - `UseD7CrossSheetOptions` 新增 `segments?: Ref<AgingSegment[]>`；新增 `agingSegments`（项目段优先→数据兜底→THREE_YEAR）、`agingByKey`（用 `aggregateAgingByKeys` 从 nested 聚合）、`overOneYearKeys`（`dayFrom>=366`）。保留 `natureAggregation` 不变。
  - `adjustmentTotals` 重构为 `{ byNature, byAging, totalAje, totalRje }` 双分组（见 design §Data Models）：遍历 `D7-3-rows`，`entryType=debitAmount>0?AJE:RJE`，按 `natureType`(缺省 other)累加 byNature、按 `agingBand`(缺省不计入 byAging 明细但计入 total)累加 byAging。
  - `crossValidation` 账龄合计改从 `agingByKey.current` 求和；聚合忽略配置外旧段 key。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 10.1, 10.2_

- [x] 5. `useD7Adjustment.ts` 增加 `natureType` / `agingBand` 维度
  - `AdjustmentRow` 新增 `natureType: string`、`agingBand: string`；`normalizeRow`/`createEmptyRow` 默认 `natureType:''`/`agingBand:''`；`updateCell` 支持二字段更新并持久化。
  - `D7TabAdjustment.vue`：新增性质下拉（来自 `NATURE_TYPES`）与账龄段下拉（来自当前 `segments`）；只读模式只读展示。`publishAdjustment`/`pushToA13` 不变。
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 6. `useD7Adjudication.ts` 账龄区块动态化 + 纯 computed 派生 + 移除累加器
  - 账龄区块 `AGING_BLOCK_CONFIG` 硬编码 4 行 → 按 `crossSheet.agingSegments` 动态生成明细行；默认段沿用旧 rowKey（`LEGACY_AGING_ROWKEY`：within1→within-1-year 等），自定义段用 `seg.key`（保 item_id）。
  - 账龄合计行=各段之和；保留试算平衡表数行、差异数行（差异=账龄合计−TB）；旧账龄区块存储数据映射到当前段对应行保留可匹配值。
  - 性质区块保持固定 4 行；性质行调整数 = `adjustmentTotals.byNature[natureKey]`，账龄行调整数 = `adjustmentTotals.byAging[segKey]`（纯 computed，不落库）。
  - **移除 `onAdjustmentCreated`** 及其累加到 other 行的逻辑；交叉验证告警（性质调整合计===账龄调整合计），两区块合计不相加。
  - `tbSeedAmount` 逻辑不改。`D7TabAdjudication.vue` 账龄区块表格按动态行渲染。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 10.3, 10.4, 10.5, 10.6, 11.1, 11.2_

- [x] 7. `useD7LongTerm.ts` 超1年按 segment 动态判定
  - 依赖 `crossSheet.overOneYearKeys`/`agingSegments`（或自接 `useAgingConfig('D7')`）；`importFromD72` 改按段：超1年=`agingAudited` 中 `dayFrom>=366` 段之和>0（去掉硬编码 `endAging2+3+4`）；账龄 label 取占比最大的超1年段 label。
  - 保留 `disposalConclusion`/`disposalSummary` 不改。
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 8. `useD7DetailColumnPrefs.ts` 动态账龄列组
  - "账龄"组固定 `['endAging1..4']` → 按当前 `segments` 动态生成 `agingPrior.{segKey}`/`agingAudited.{segKey}` 显隐项；接收 `segments` 参数；`isColVisible`/`toggleCol` 逻辑不变。`D7TabDetail.vue` 账龄列 v-for 按 bands 渲染并接列偏好。
  - _Requirements: 2.4, 2.5_

- [x] 9. `_d7_import_export.py` 动态账龄列头 + D7-3 性质/账龄字段
  - 引入 `resolve_aging_segments`/`build_aging_headers`/`aging_export_values`/`match_import_aging`/`subject_aging_periods`（`_cycle_import_export_common`）。
  - D7-2：`_D7_2_BASE_HEADERS`(非账龄)+`_d7_2_dynamic_headers(segments)`（期初审定数后 + 期末审定数后各插 N 账龄列，periods=`['prior','audited']`）；导出用 `resolve_aging_segments`+`aging_export_values`（从 nested 取值），导入用 `match_import_aging`（label 匹配写 nested，未匹配 skipped+warning，缺列置0，基础列仍走 missing_cols 校验）；配置无效回退 THREE_YEAR 不崩。
  - `import-aux-balance`：构造行 `priorAging1~4`/`endAging1~4` → nested `agingPrior`/`agingAudited`，仅首段(within1)填余额其余0。
  - D7-3：`_SHEET_HEADERS["D7-3"]` 增"款项性质"、"账龄段"两列；`_export_row`/`_parse_row` 读写 `natureType`(默认"其他")、`agingBand`(默认空)。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 12.3, 12.4_

- [x] 10. `aging-config:changed` 刷新 + 只读守卫 + 主组件移除累加器绑定
  - `useD7Detail.ts`：`onMounted` 加 `window.addEventListener('aging-config:changed', ...)` → `remapRowAgingData(row, segments, false)` 逐行重映射后持久化；`onBeforeUnmount` 移除监听。`useD7Adjudication.ts` 账龄区块随 segments 刷新（computed 自动）。
  - 各 composable `updateCell` 前置 `if (isReadonly.value) return`（Detail/Adjustment）；`GtD7ContractLiabilities.vue` 移除对 `onAdjustmentCreated` 的 eventBus/事件绑定（Task 6 已删函数）。
  - _Requirements: 2.4, 7.1, 7.2, 7.3, 7.4, 9.5, 11.3, 11.4, 12.1_

- [x] 11. 前端属性测试 + 单元测试（P1-P7, P11-P16）
  - `fast-check` numRuns≥100，每个属性测试注释 `Feature: d7-contract-liabilities-enhancement, Property {n}: {text}`。
  - P1 2-period 无期末未审列 / P2 列数由段驱动 / P3 按段聚合忽略旧段 / P4 账龄合计与差异公式 / P5 超1年 dayFrom>=366 / P6 长期挂账筛选+label / P7 配置变更数据保留 / P11 扁平迁移保值仅输出 nested / P12 调整双分组派生缺省归其他 / P13 computed 幂等不放大+删除减少 / P14 段列 nested 写入 / P15 性质/账龄合计交叉验证恒等 / P16 D7-3 往返保留字段。
  - 单元测试：subject='D7' 接线、加载失败回退 THREE_YEAR、只读守卫、`aging-config:changed` 监听+卸载移除、`onAdjustmentCreated` 已移除、D7-3 字段持久化。
  - 生成器覆盖 THREE_YEAR/FIVE_YEAR/CUSTOM 段、含配置外旧段行、混合扁平+nested 历史行、空/负/大额、缺列/多列表头。
  - _Requirements: 1.2, 2.1, 2.2, 2.5, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 7.3, 8.1, 8.2, 8.3, 8.4, 9.3, 10.1, 10.2, 10.3, 10.4, 10.5, 11.3, 11.4, 12.3_

- [x] 12. 后端属性测试 + 导入导出往返回归（P8-P10）
  - `hypothesis` 显式 `@settings(max_examples=100)`；P8 动态列头 2N 含全段 label+导出取值顺序一致 / P9 导入按 label 匹配写段+缺列置零+未匹配报 warning / P10 D7-2 导入导出账龄往返一致。
  - 回归：仿 `test_d3_export_import_roundtrip` 新增 `test_d7_export_import_roundtrip`（含 THREE_YEAR/FIVE_YEAR 段 + D7-3 性质/账龄字段往返）；确认不破坏 `test_d7_import_export_pbt`。
  - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 6.7, 12.2_

- [x] 13. Playwright round-trip + 只读 + 导入导出回归实测
  - 用已实例化 D7 项目（如重药控股安徽 0ec33ac9 / wp 6f23dcce），实测：①FIVE_YEAR 配置下 D7-2 账龄列/ D7-1 账龄区块行数=6 段 ②明细录入某段→审定表账龄区块联动+交叉验证 ③D7-3 选性质/账龄段→审定表对应行调整数派生（编辑两次不放大、删除减少）④D7-2 导出→导入往返账龄一致 ⑤只读模式账龄列与性质/账龄字段只读渲染 ⑥`aging-config:changed`（切换项目账龄预设）后 D7 各区刷新且历史值保留 ⑦0 组件报错（排除 pre-existing SSE 401 / 无关 htmlRendererRegistry 阻断需先解除）。
  - 全改动文件 get_diagnostics 全清 + Vite transform 200 + 后端 AST OK；测试数据清理还原。不 commit。
  - _Requirements: 5.1, 6.7, 7.1, 7.3, 10.3, 11.3, 12.1, 12.2, 12.3_

## Notes

- **复用优先**：D3 是已上线的 2-period 动态账龄参考实现（`useD3Detail`/`useD3CrossSheet`/`useD3Adjudication`/`_d3_import_export`），D7 与 D3 同构（贷方往来款），本 spec 以最小改动平移，禁止新造平行机制。
- **唯一新增迁移工具** `migrateD7FlatToNested`（Task 2）——因 D7 历史是扁平字段而非 nested；其余迁移复用 `migrateD3F1Keys`/`remapRowAgingData`/`remapAgingData`。
- **双维度不相加铁律**：性质区块合计与账龄区块合计是同一总额的两个视图，靠交叉验证守卫恒等，绝不相加计入合同负债总额。
- **已完成前置**（本 spec 不重复）：eventBus 迁移、后端 project_context（bs_date/related_parties/tb_amount）、D7-7 抽凭引擎、D7-4 序时账导入、D7-5 处置结论 UI、D7↔D4 收入勾稽卡、D7-1 TB 预填种子、导入导出处置结论列。
- **Playwright 前置阻断**：当前工作区 `htmlRendererRegistry.ts` 引用缺失的 `GtB22CDesignEffectiveness.vue`（并发未提交 B22C 工作），会触发 Vite overlay 阻断全应用渲染；Task 13 实测前需该阻断已由 B22C 所有者解除。
