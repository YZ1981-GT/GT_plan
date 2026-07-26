# Design Document

## Overview

把 F4 应付账款的账龄从"自带固定 5 行 + 扁平 4+4 字段"迁移到平台账龄枚举单一真源（`useAgingConfig` + Nested_Aging），并在 3 年段下逐字节零回归。

策略是 **strangler 分层替换**：先在明细层（F4-2）落地 Nested_Aging + 迁移链，再让审定层（F4-1）改为段驱动并沿用既有 rowKey，最后收敛下游（F4-5 / 关联方 / 两张披露表）与后端导入导出。每一波独立可回退。

## Architecture

```
项目账龄配置（唯一真源）
  前端 useAgingConfig(projectId,'F4')          后端 aging_config_service.get_effective_segments
        │                                              │
        ├── useF4Detail（F4-2）                        └── _f4 导入导出
        │     · agingCurrent / agingAudited（Nested）        · build_aging_headers(segments, ['current','audited'])
        │     · migrateF4FlatToNested + remapRowAgingData     · aging_export_values / match_import_aging
        │     · allocateAging 候选 = segments
        │     · 双账龄勾稽按段求和
        │
        ├── useF4Adjudication（F4-1 按账龄区块）
        │     · 行 = segments.map(seg → rowKey = LEGACY_AGING_ROWKEY[seg.key] ?? seg.key) + Residual_Row
        │     · detailAggregation 按段聚合，残差/未拆分 RJE → aging-other
        │
        └── 下游（只读派生）
              · useF4LongOutstanding：Over_One_Year_Keys（dayFrom>=366）
              · useF4DisclosureSOE：按账龄行跟随段；1年以上合计按 Over_One_Year_Keys（排除 Residual_Row）
              · useF4DisclosureListed：1年以上明细来自 F4-5（无需改段逻辑，仅文案）
              · useF4RelatedParty：账龄输入 = 段枚举（allow-create）
```

### 关键设计决策

**决策 1：期间命名映射 = `current`(期末未审) + `audited`(期末审定)，F4 无期初账龄。**
平台 `_AGING_PERIOD_FIELD` 已有 `prior→agingPrior / current→agingCurrent / audited→agingAudited`，标签 `期初/期末未审/期末审定` 正好对应 F4 的两组账龄。故 F4 复用 `agingCurrent`/`agingAudited` 字段名，不新造字段。后端 `subject_aging_periods` 当前只有"三期科目集合"与"其余返回 `['prior','audited']`"两个分支，**必须新增 F4 分支返回 `['current','audited']`**（Req 4.4）；否则 F4 会拿到错误的期初列头。

**决策 2：F4-1 rowKey 用 Legacy 映射表沿用既有存储键（对齐 D3/D7 已 proven 范式）。**
`LEGACY_AGING_ROWKEY = { within1:'within1year', y1to2:'1to2year', y2to3:'2to3year', over3:'3yearplus' }`；映射表未覆盖的段（y3to4/y4to5/over5/自定义）直接用段 key。这样 3 年段项目的既有 `F4-1-adj-aging-rows` 无需数据迁移即可读（Req 2.2 / 5.3）。

**决策 3：Residual_Row 保留且不属于段。**
`aging-other` 是 F4 特有的残差桶（承接明细四档合计与期末余额的差额、以及明细未按账龄拆分的 RJE）。它**不参与**段映射、**不计入** Over_One_Year_Keys 汇总（修正现有国企披露"除 within1year 外全部"的写法，Req 3.3），但仍进按账龄小计与交叉核对（保持迁移前语义，Req 2.5）。

**决策 4：迁移链复用平台 `useAgingMigration`，只新增 F4 专属扁平→nested 薄封装。**
新增 `migrateF4FlatToNested(raw)`（镜像 `migrateD7FlatToNested`）：把 `unadjustedAging*` → `agingCurrent`、`auditedAging*` → `agingAudited`（含更早别名 `aging1Year/agingLt1/adjustedAging1..4`），**nested 已存在则原样返回**（Req 1.5）；随后统一交给既有 `remapRowAgingData(row, segments)` 对齐当前段（Req 1.6）。不改共享迁移函数的既有行为（Req 5.5）。

**决策 5：扁平字段保留为只读兼容层，不双写。**
`DetailRow` 仍保留 Legacy_Flat_Fields 的类型字段以兼容既有导入导出/测试读取路径，但**权威值一律来自 Nested_Aging**；序列化只写 nested（避免"两处真源"）。若某消费方仍读扁平字段，则由 F4-2 的 computed 从 nested 派生 3 年段对应值（仅 3 年段有对应字段，其它段不派生）。

**决策 6：默认预设 F4 = THREE_YEAR（前后端同时显式登记）。**
F4 源模板是 4 档，与 3 年段一一对应，默认 THREE_YEAR 可使既有项目"不配置账龄"时段数与现状一致（零回归的前提，Req 6.2）。

## Components and Interfaces

### 前端

| 组件/模块 | 改动 |
|---|---|
| `composables/useAgingMigration.ts` | **新增** `migrateF4FlatToNested(raw)`（additive，不改既有导出） |
| `composables/useF4Detail.ts` | 接 `useAgingConfig(projectId,'F4')`；`normalizeRow` 走 `migrateF4FlatToNested → remapRowAgingData`；`agingCurrent/agingAudited` 为权威；`allocateAging(rowId, stage, segKey)` 候选改段；双账龄勾稽按段求和；导出 `segments`/`agingColumns` 供组件渲染 |
| `composables/useF4Adjudication.ts` | 按账龄区块行段驱动（`LEGACY_AGING_ROWKEY`）+ Residual_Row；`detailAggregation.aging` 改为 `Record<segKeyOrLegacy, ...>` 按段聚合；`F4_AGING_DEFAULTS` 保留为 3 年段回退常量 |
| `composables/useF4LongOutstanding.ts` | `syncFromDetail` 用 Over_One_Year_Keys + 段 label |
| `composables/useF4DisclosureSOE.ts` | 按账龄行跟随段；`overOneYearAgingTotal` 改 Over_One_Year_Keys（排除 Residual_Row） |
| `composables/useF4DisclosureListed.ts` | 仅文案/label 跟随段（金额来自 F4-1 与 F4-5） |
| `composables/useF4RelatedParty.ts` | 账龄字段候选 = 段枚举（allow-create 保留） |
| `f4-accounts-payable/F4TabDetail.vue` | 账龄列 `v-for` 段；`F4_DETAIL_AGING_COLUMNS` 改为按段生成的 computed（保留同名导出以兼容 integration 测试）；账龄分配下拉按段 |
| `f4-accounts-payable/F4AdjudicationTable.vue`、`F4TabAdjudication.vue` | 按账龄区块行数据源改段驱动结果（无硬编码 4 行） |
| `f4-accounts-payable/F4TabDisclosureSOE.vue` / `F4TabLongOutstanding.vue` / `F4TabRelatedParty.vue` | 文案与列/选项跟随段 |
| `GtF4AccountsPayable.vue` | 一处 `useAgingConfig(projectId,'F4')` 装配，`provide('f4AgingSegments'/'f4AgingPreset')`，各 tab inject（对齐 D2 范式，避免每 tab 各自请求） |

### 后端

| 模块 | 改动 |
|---|---|
| `app/services/aging_config_service.py` | `DEFAULT_SUBJECT_PRESETS['F4'] = THREE_YEAR` |
| `app/routers/wp_render_strategies/_cycle_import_export_common.py` | `subject_aging_periods`：新增 F4 → `['current','audited']`（additive 分支） |
| F4 导入导出模块（`_f4*`） | F4-2 列头/取值/导入匹配改动态：`resolve_aging_segments(db, wp_id, 'F4')` + `build_aging_headers` + `aging_export_values` + `match_import_aging`；编制说明列出生效段；返回 `skipped_columns` |

## Data Models

### F4 明细行（F4-2）账龄部分

```ts
interface F4DetailAging {
  // 权威（Nested_Aging）
  agingCurrent: Record<string, number>   // 期末未审账龄，key = 段 key
  agingAudited: Record<string, number>   // 期末审定账龄，key = 段 key
  // 兼容层（只读派生，仅 3 年段有对应字段；序列化不写）
  unadjustedAgingLt1?: number; unadjustedAging1to2?: number
  unadjustedAging2to3?: number; unadjustedAgingGt3?: number
  auditedAgingLt1?: number; auditedAging1to2?: number
  auditedAging2to3?: number; auditedAgingGt3?: number
}
```

### F4-1 按账龄区块行

```ts
// 存储键不变：F4-1-adj-aging-rows
interface StoredF4AdjRow {
  rowKey: string   // 3年段 → within1year/1to2year/2to3year/3yearplus；其它段 → 段 key；残差 → 'aging-other'
  label: string    // 段 label（残差行固定「其他/未分类」）
  openingUnadjusted: number; openingAje: number; openingRje: number
  closingUnadjusted: number; closingAje: number; closingRje: number
}
```

### 段 ↔ 既有 rowKey 映射

| 段 key | F4-1 rowKey（3 年段沿用） |
|---|---|
| within1 | within1year |
| y1to2 | 1to2year |
| y2to3 | 2to3year |
| over3 | 3yearplus |
| y3to4 / y4to5 / over5 / 自定义 | 同段 key |
| —（残差） | aging-other |

## Correctness Properties

### Property 1: 段驱动聚合等于逐行逐段求和
对任意明细行集合与任意生效段集合，F4-1 按账龄各段金额等于该段在所有行 `agingCurrent/agingAudited` 上的求和。
**Validates: Requirements 2.4, 1.9**

### Property 2: Nested 优先于 Legacy
行同时含 Nested_Aging 与 Legacy_Flat_Fields 时，取值恒等于 Nested_Aging；仅含 Legacy 时等于迁移后的 nested 值。
**Validates: Requirements 1.4, 1.5**

### Property 3: 段切换保同 key、补新段、丢废段
从段集 A 切到 B 后，A∩B 段金额不变，B−A 段为 0，A−B 段不出现在结果中。
**Validates: Requirements 1.6, 2.6**

### Property 4: Over_One_Year_Keys 由 dayFrom 派生
对任意段集合，"1 年以上"段集合恒等于 `segments.filter(s => s.dayFrom >= 366).map(s => s.key)`，与段数量/命名无关。
**Validates: Requirements 3.1, 3.3**

### Property 5: Residual_Row 不计入 1 年以上
`aging-other` 金额任意时，"1 年以上账龄合计"不随其变化。
**Validates: Requirements 3.3**

### Property 6: 3 年段 = 迁移前口径
生效段为 3 年段且行仅含 Legacy_Flat_Fields 时，F4-1 按账龄各行、按性质/按账龄交叉核对结论、F4-5 同步集合、国企披露按账龄金额，与迁移前实现逐项相等。
**Validates: Requirements 5.1, 5.3**

### Property 7: 双账龄勾稽按段求和
"期末未审账龄合计 = 期末未审余额"与"期末审定账龄合计 = 审定数"的判定，在任意段集合下都以生效段求和为基准。
**Validates: Requirements 1.9**

### Property 8: rowKey 映射稳定且可逆
段 key → rowKey 映射对 3 年段恒为既有 4 键；对未覆盖段恒为段 key；同一段 key 多次映射结果一致。
**Validates: Requirements 2.2, 2.3**

### Property 9: 导入导出 Round_Trip 保值
任意段集合下，F4-2 导出后再导入，各段 `agingCurrent/agingAudited` 金额不变。
**Validates: Requirements 4.1, 4.2, 4.3, 5.2**

### Property 10: 未匹配账龄列跳过并提示
导入文件含不属于生效段的账龄列时，该列被跳过、其余列正常导入，且返回 `skipped_columns` 含该列名。
**Validates: Requirements 4.3**

### Property 11: F4 期间集合固定为 current+audited
`subject_aging_periods('F4')` 恒返回 `['current','audited']`，导出列头后缀恒为「期末未审」「期末审定」，不含「期初」。
**Validates: Requirements 4.1, 4.4**

### Property 12: 前后端默认预设一致
前端 `useAgingConfig` 对 F4 的默认预设与后端 `DEFAULT_SUBJECT_PRESETS['F4']` 相同（THREE_YEAR）；有 subject_overrides 时两端都以覆盖为准。
**Validates: Requirements 6.1, 6.2, 6.3**

### Property 13: 配置未加载时段数稳定
账龄配置加载中/失败时，段集合等于 F4 默认预设，不出现"先 4 档后跳变"的中间态。
**Validates: Requirements 1.7**

## Error Handling

- **账龄配置接口失败**：前端回退 F4 默认预设（THREE_YEAR）+ `console.warn`，不阻断编辑；后端 `resolve_aging_segments` 已有同款回退。
- **行数据账龄结构异常**（非对象/含 NaN）：迁移函数按 0 处理该段，不抛错、不丢整行。
- **导入列头缺失核心列**：沿用 F4 既有列名校验（400 + 不匹配列名列表），不改现有契约。
- **导入账龄列未匹配**：跳过 + `skipped_columns` 警告（不静默丢数）。
- **F4-1 既有存储含未知 rowKey**（历史脏数据）：保留该行但不参与段映射（避免删数），在交叉核对提示中如实体现。

## Testing Strategy

- **纯函数单测**：`migrateF4FlatToNested`、段聚合、Over_One_Year_Keys 派生、rowKey 映射、双账龄勾稽（Property 1/2/4/5/7/8）。
- **PBT（fast-check）**：Property 1/3/4/9（任意段集合 × 任意行集合）。
- **零回归对照测试**：3 年段下与迁移前期望值逐项断言（Property 6）；既有 5 个 F4 spec 全绿（Req 5.4）。
- **后端**：`subject_aging_periods('F4')`、动态列头/取值/导入匹配、Round_Trip、`skipped_columns`（Property 9/10/11）。
- **契约测试**：前后端默认预设一致（Property 12）。
- **Playwright（可选）**：切换项目账龄配置（3年段→5年段）后 F4-2/F4-1/F4-5/披露表段数与金额联动正确；需实例化 F4 底稿的项目。
