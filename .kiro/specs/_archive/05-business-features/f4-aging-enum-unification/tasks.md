# Implementation Plan

## Overview

6 波 strangler 迁移：先建零回归安全网与迁移纯函数（Wave 0-1），再落明细层（Wave 2）、审定层（Wave 3）、下游消费方（Wave 4）、后端导入导出（Wave 5），最后属性化测试与零回归门（Wave 6）。每波独立可发布可回退。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "description": "F4 默认预设显式登记 + 3 年段零回归基线快照" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "description": "migrateF4FlatToNested + 段/rowKey/OverOneYear 纯函数" },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "description": "F4-2 明细层 Nested_Aging 段驱动" },
    { "wave": 3, "tasks": ["4.1", "4.2"], "description": "F4-1 审定表按账龄段驱动 + 残差行" },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3"], "description": "F4-5 / 披露表 / 关联方下游收敛" },
    { "wave": 5, "tasks": ["6.1", "6.2"], "description": "后端 F4 期间注册 + 动态账龄导入导出" },
    { "wave": 6, "tasks": ["7.1", "7.2", "7.3"], "description": "PBT + 零回归门 + Playwright（可选）" }
  ]
}
```

## Tasks

- [x] 1. Wave 0：默认预设登记与零回归基线
- [x] 1.1 前后端显式登记 F4 默认账龄预设为 THREE_YEAR
  - 前端 `composables/useAgingConfig.ts::_applyDefault` 把 F4 纳入 THREE_YEAR 分支
  - 后端 `app/services/aging_config_service.py::DEFAULT_SUBJECT_PRESETS` 增 `"F4": THREE_YEAR`
  - 补前后端一致性契约测试
  - _Requirements: 6.1, 6.2, 6.3_
  - _Properties: Property 12_

- [x] 1.2 建立 3 年段零回归基线（characterization）
  - 对现有实现录制期望值：F4-1 按账龄各行、按性质↔按账龄交叉核对结论、F4-5 `syncFromDetail` 结果集、国企披露按账龄金额与 1 年以上合计
  - 断言以「迁移前后必须相等」形式固定（后续各波不得修改这些期望值）
  - _Requirements: 5.1, 5.3, 5.4_
  - _Properties: Property 6_

- [x] 2. Wave 1：迁移与派生纯函数
- [x] 2.1 新增 `migrateF4FlatToNested`（additive，不改共享迁移既有行为）
  - `composables/useAgingMigration.ts` 增 F4 专属扁平→nested 薄封装（镜像 `migrateD7FlatToNested`）
  - `unadjustedAging*`→`agingCurrent`、`auditedAging*`→`agingAudited`，含更早别名 `aging1Year/agingLt1/aging1to2Year/aging2to3Year/aging3YearPlus/adjustedAging1..4`
  - nested 已存在则原样返回（nested 优先）
  - 单测覆盖：仅扁平 / 仅 nested / 两者并存 / 别名 / 异常值
  - _Requirements: 1.4, 1.5, 5.5_
  - _Properties: Property 2_

- [x] 2.2 段/rowKey/1 年以上 派生纯函数
  - `LEGACY_AGING_ROWKEY` 映射表 + `f4AgingRowKey(segKey)`
  - `overOneYearKeys(segments)`（`dayFrom >= 366`）
  - `sumAgingBySegments(rows, period, segKeys)`
  - 单测 + PBT（任意段集合）
  - _Requirements: 2.2, 2.3, 3.1_
  - _Properties: Property 4, Property 8_

- [x] 3. Wave 2：F4-2 明细层段驱动
- [x] 3.1 `useF4Detail` 接入 Aging_Config 与 Nested_Aging
  - `useAgingConfig(projectId,'F4')`（或 inject 主入口 provide 的段），未加载回退 THREE_YEAR
  - `normalizeRow` 走 `migrateF4FlatToNested → remapRowAgingData(segments)`
  - 序列化只写 nested；扁平字段降级为 3 年段只读派生
  - `allocateAging(rowId, stage, segKey)` 候选改段
  - 双账龄勾稽（未审账龄合计=期末未审余额、审定账龄合计=审定数）按段求和
  - _Requirements: 1.1, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_
  - _Properties: Property 1, Property 2, Property 3, Property 7, Property 13_

- [x] 3.2 `F4TabDetail.vue` 账龄列段驱动
  - 账龄列 `v-for` 生效段（期末未审 / 期末审定两组）
  - `F4_DETAIL_AGING_COLUMNS` 改为按段生成（保留同名导出，兼容 integration 测试）
  - 「账龄分配」下拉按段；列设置与勾稽提示文案跟随段
  - _Requirements: 1.1, 1.2, 1.3, 1.8_
  - _Properties: Property 1, Property 7_

- [x] 3.3 主入口一处装配账龄段并 provide
  - `GtF4AccountsPayable.vue` 调 `useAgingConfig(projectId,'F4')`，`provide('f4AgingSegments'/'f4AgingPreset')`
  - 各 tab 改 inject（避免每 tab 各自请求、首帧段数不一致）
  - _Requirements: 1.1, 1.7_
  - _Properties: Property 13_

- [x] 4. Wave 3：F4-1 审定表段驱动
- [x] 4.1 `useF4Adjudication` 按账龄区块改段驱动 + 保留残差行
  - 行 = `segments.map(seg → rowKey = LEGACY_AGING_ROWKEY[seg.key] ?? seg.key)` + `aging-other`
  - `detailAggregation.aging` 改按段聚合（读 nested）；残差与未拆分 RJE 仍归 `aging-other`
  - 段变化时同 key 保金额 / 新段补 0 / 废弃段丢弃并持久化一次
  - 既有 `F4-1-adj-aging-rows`（rowKey 为 `within1year` 等）零迁移可读
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 5.3_
  - _Properties: Property 1, Property 3, Property 8_

- [x] 4.2 审定表组件按账龄区块去硬编码
  - `F4AdjudicationTable.vue` / `F4TabAdjudication.vue` 行数据源改段驱动结果
  - 按性质↔按账龄交叉核对语义与容差保持不变（含残差行）
  - _Requirements: 2.1, 2.5_
  - _Properties: Property 6_

- [x] 5. Wave 4：下游消费方收敛
- [x] 5.1 `useF4LongOutstanding` 用 Over_One_Year_Keys
  - `syncFromDetail` 判定改 `dayFrom >= 366` 段汇总；账龄 label 取占比最大的超 1 年段 label
  - _Requirements: 3.1, 3.2_
  - _Properties: Property 4_

- [x] 5.2 两张披露表段驱动 + 修正 1 年以上口径
  - `useF4DisclosureSOE`：按账龄行跟随段；`overOneYearAgingTotal` 改 Over_One_Year_Keys（**排除** `aging-other`，修正现有"除 within1year 外全部行"写法）；残差行仅有余额时展示
  - `useF4DisclosureListed`：1 年以上明细仍来自 F4-5，仅文案/label 跟随段
  - _Requirements: 3.3, 3.4_
  - _Properties: Property 4, Property 5_

- [x] 5.3 关联方检查表账龄枚举化
  - `useF4RelatedParty` / `F4TabRelatedParty.vue` 账龄输入改 `el-select` 段枚举 + allow-create
  - _Requirements: 3.5_

- [x] 6. Wave 5：后端导入导出动态账龄
- [x] 6.1 `subject_aging_periods` 注册 F4 = `['current','audited']`
  - `_cycle_import_export_common.py` 新增 F4 分支（additive，不改三期科目与 D3 行为）
  - 单测断言列头后缀为「期末未审」「期末审定」且不含「期初」
  - _Requirements: 4.4_
  - _Properties: Property 11_

- [x] 6.2 F4-2 导入导出账龄列动态化
  - 导出模板/数据：`resolve_aging_segments(db, wp_id, 'F4')` + `build_aging_headers` + `aging_export_values`
  - 导入：`match_import_aging` 按列头匹配段，未匹配列跳过 + `skipped_columns` 提示
  - 编制说明列出生效段；无配置时回退 F4 默认预设
  - Round_Trip 测试（3 年段 + 5 年段）
  - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 5.2_
  - _Properties: Property 9, Property 10_

- [x] 7. Wave 6：属性化测试与零回归门
- [x] 7.1 PBT 覆盖 Property 1/3/4/9
  - fast-check：任意段集合 × 任意行集合下聚合正确、段切换语义、1 年以上派生、Round_Trip 保值
  - _Requirements: 7.1, 7.2_
  - _Properties: Property 1, Property 3, Property 4, Property 9_

- [x] 7.2 零回归门
  - Wave 0 基线断言全绿（3 年段逐项相等）
  - 既有 F4 测试全绿：useF4Detail / useF4Adjudication / useF4LongOutstanding / useF4RelatedParty / useF4DisclosureListed / useF4DisclosureSOE / GtF4AccountsPayable.integration / useF4FormulaEngine.pbt — **191/191 passed**
  - 其它循环账龄相关测试全绿（D3/D6/D7/G2/G3 + useAgingConfig）— **107/107 passed + 47/47 passed**
  - 全部改动文件 `get_diagnostics` 全清 + Vite transform 200（16 文件全 200）+ 后端 AST OK（py_compile exit=0）
  - 后端 F4 测试：52 passed / 2 failed（pre-existing TestF4AiGenerate，git stash 对照确认非本 spec 引入）
  - _Requirements: 5.1, 5.2, 5.4, 5.5_
  - _Properties: Property 6_

- [ ] 7.3* Playwright 端到端（需实例化 F4 底稿的项目）
  - 项目账龄由 3 年段切 5 年段后：F4-2 账龄列数、F4-1 按账龄行数、F4-5 同步结果、国企披露按账龄行与 1 年以上合计 全部联动正确
  - 切回 3 年段后金额与切换前一致（无数据丢失）
  - _Requirements: 1.3, 2.6, 3.1, 3.4_
  - _Properties: Property 3_

## Notes

- **零回归红线**：3 年段（= 现有固定 4 档）下所有金额、勾稽结论、披露数字、导入导出往返必须与迁移前逐项一致；任何被迫调整的既有断言都要保留"3 年段结果与迁移前相同"的显式对照（Req 5.4）。
- **共享模块只允许 additive**：`useAgingMigration` / `_cycle_import_export_common` / `aging_config_service` 的改动不得改变其它循环行为（Req 5.5）。
- **Residual_Row 不是段**：`aging-other` 不参与段映射、不计入"1 年以上"，但仍进小计与交叉核对。
- **不改 F4 其它内容**：本 spec 只做账龄口径统一，不动 F4 的 27 列源表结构、抽凭/OCR、供应链融资、未入账检查、双模式等。
- 迁移无 DB schema 变更（账龄存 `checklist_responses` JSON），无需 migration 版本号。
