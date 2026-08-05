# Design Document: G0 投资循环函证源模板对齐与联动补齐

## Overview

本设计以「泛化既有共享件 + G0 专属声明式清单」为主轴，避免第三份矩阵实现与第二份下区实现。

三条设计主线：

1. **矩阵与下区泛化** —— `f0SummaryAggregation.ts` 的 8 指标矩阵与 G0-1 逐条同构（`SUMIF(E,品种,F/U/Y)` + 3 个派生比例 + `(替代+回函)/账面`），把品种集合与账面取数口径抽成**按循环的声明式 spec**，F0/G0 共用同一引擎；E0 是 6 指标子集（无替代两行），以同一引擎的指标裁剪表达。下区四块同理抽为 `confirmationLowerZone` 按循环声明。
2. **索引号双真源分离** —— 沿用 H10 的「定位常量 vs 展示常量分离」范式：`sheetName`（真实 tab 名，含笔误）用于定位/请求，`indexLabel`（底稿目录索引号）用于展示，二者在同一条声明里成对出现并由守卫双向锁死。
3. **守卫以源 xlsx 为唯一裁决者** —— 所有结构断言经 openpyxl 直读 `backend/wp_templates/G/G0 投资循环函证.xlsx`，不连库故可进 CI；每类断言配反向自检。

### 关键实证（改造前基线，本 spec 的判据）

| # | 实证 | 手段 |
|---|---|---|
| 1 | G0 源模板 10 sheet 全 visible | openpyxl `sheet_state` |
| 2 | G0-1 上区 28 列 5 段 + `AB 审计结论` | openpyxl R5/R6 + merged_cells |
| 3 | G0-1 下区 8 指标公式与 F0-1 逐条同构 | 逐格读公式对比 D0-1/F0-1 |
| 4 | G0-3（跟函）与 F0-8（舞弊）与 D0 版逐字相同 | 逐行 diff |
| 5 | `CYCLE_VARIANT_COLUMNS.G0 = []`、`CYCLE_EXCLUDED_COLUMNS.G0 = []` | 读 `confirmationColumnSpec.ts` |
| 6 | `CrossWorkpaperNav.vue` 写死 `D0-*` 8 项；`buildCrossWorkpaperNavDefs` 零消费方 | grep 全仓 |
| 7 | `E0SummaryLowerZone.vue` 零消费方 | grep 全仓 |
| 8 | `wp_index` 只有 `G0 / G0-1..G0-5`（无 G0-3S/G0-6/G0-7/G0-8），且 G0-4=投资函证差异调节、G0-5=投资函证替代程序（遗留命名族，与目录相反） | postgres 只读 |
| 9 | `workpaper_sheet_classification` 有 G0 的 10 条，sheet 名与 tab 名逐字一致 | postgres 只读 |
| 10 | `report_config` 实测 BS-003=1101 / BS-021=1504 / BS-022=1506 / BS-023=1531 / BS-024=1511 / BS-025=1507 / BS-026=1519 / BS-042=2101（四准则一致） | postgres 只读 |
| 11 | G0 预设 `sheet='审定表G0-1'`（源 xlsx 无）+ `TB_SUM('1101~1511')` | 读 `prefill_formula_mapping.json` |
| 12 | `procedure_table_templates.json` 双 G0A：`/tables/G0A` 12 条正确（`get_template` 只读 `tables` → 运行时生效）、根级 `/G0A` 8 条自造 | 读 json + 读 `procedure_table_auto_service.get_template` |
| 13 | G0A 12 条 item 全 `applicable_default:"yes"`；item 键集无程序分类字段 | 读 json |
| 14 | `ConfirmationSampling.vue` 只有 4 项（抽样方式/样本量/选样标准/抽样结论），与源模板 6 项不符；替代程序组件的 `SamplingInfo` 才是正确的 6 项 | 读源码 |
| 15 | G0-6 block1 含源模板没有的记账凭证 5 列、缺投资条款；block2 把支持性文件 1/2 六列压成一个 `support_doc`；block3 用自造列替换源三组证据 | 对比 `blockColumnConfigsG06.ts` 与源 xlsx |

## Architecture

```
源 xlsx（唯一裁决者）
  backend/wp_templates/G/G0 投资循环函证.xlsx
        │
        │ openpyxl 直读（守卫）
        ▼
┌──────────────────────────────────────────────────────────────┐
│ 后端                                                          │
│  tests/test_g0_source_template_facts.py     ← R1 事实固化      │
│  scripts/fix/fix_g0_prefill_presets.py      ← R9 预设纠偏      │
│  data/procedure_table_templates.json        ← R8 程序分类      │
│  tests/test_g0a_procedure_template.py       ← R8 守卫          │
│  routers/review_dialog._SECTION_PROMPTS     ← R3.7 AI prompt   │
└──────────────────────────────────────────────────────────────┘
        │ render-config（project_context.tb_amount 来自 G1/G4/G5/G6/G7/G8/G9/G10）
        ▼
┌──────────────────────────────────────────────────────────────┐
│ 前端 —— G0 专属（D-2：自建副本，不动 E0/F0 两份）               │
│  g0-confirmation/g0SummaryMatrix.ts     新建·8 指标 × 8 品种    │
│  g0-confirmation/g0SummaryLowerZone.ts  新建·下区四块文字真源   │
│  g0-confirmation/G0SummaryLowerZone.vue 新建·下区渲染           │
│  g0-confirmation/g0SheetRegistry.ts     新建·tab名↔目录索引号   │
│  g0-confirmation/g0SourceDefects.ts     新建·7 条源缺陷登记      │
│  alternativeG06/blockColumnConfigsG06.ts 改·三区块对齐 + 增强区 │
│  alternativeG06/GtConfirmationAlternativeG06.vue 改·表头+文案   │
└──────────────────────────────────────────────────────────────┘
        │  最小挂载 hunk（并发 spec 正改这两个文件）
        ▼
┌──────────────────────────────────────────────────────────────┐
│ 前端 —— 共享件（只做加法式最小改动，禁整文件覆写）              │
│  confirmation/confirmationColumnSpec.ts 加·标签覆盖表 + G0 键   │
│  coordination/cycleConfirmationMeta.ts  加·sheets(定位/展示分离)│
│  coordination/CrossWorkpaperNav.vue     修·改用 buildNavDefs    │
│  ConfirmationSampling.vue               改·6 项对齐 SamplingConfig│
│  GtConfirmationSummary.vue              加·isG0 + 挂载下区/矩阵 │
└──────────────────────────────────────────────────────────────┘
```

### 处置判据（裁决门 D = **D-2 各自实现后收敛**，2026-08-04 用户裁决）

| 能力 | 既有实现 | 处置 |
|---|---|---|
| 品种×指标矩阵 | `composables/f0SummaryAggregation.ts`（8 指标）· `e0SummaryMatrix.ts`（6 指标） | **G0 自建 `g0SummaryMatrix.ts`**（第 3 份）。**不动** F0/E0 两份（并发 spec 在用）。以「同源性守卫」代替泛化：断言 G0 与 F0 对同一输入产出逐字节相同的指标序列与派生值 → 收敛前不会先分叉 |
| 下区四块 | `E0SummaryLowerZone.vue` + `e0SummaryLowerZone.ts`（**零消费方**，E0 侧遗留） | **G0 自建 `g0SummaryLowerZone.ts` + `G0SummaryLowerZone.vue`**（第 2 份，且是第一个真有消费方的）。**不动** E0 那份 |
| 列集与列标签 | `confirmationColumnSpec.ts`（**唯一共享注册表，无「各自一份」选项**） | **加法式改动**：新增 `CYCLE_COLUMN_LABEL_OVERRIDES` + 两个既有 record 的 `G0` 键。与 H0 spec 的兼容判据 = 双方 record 各自键互不重叠 |
| 样本选择 6 项 | 替代程序族 `SamplingConfig`（`alternativeD05Types.ts`，5 项同义 + `test_scope` 语义不同） | `ConfirmationSampling.vue` **改用同一字段族** + additive `test_population`；旧 4 字段保留读回兼容 |
| 跨表导航 | `buildCrossWorkpaperNavDefs`（已备好，**零消费方**） | **接线**，删 `CrossWorkpaperNav.vue` 写死的 `D0-*` 定义 |
| 跟函备忘录 / 舞弊 19 条 / 回函可靠性 14 列 | 已覆盖 G0（与 D0 逐字相同 / 已含渠道列） | **不动**，只加守卫钉死"无需 G0 分叉" |
| 两张差异核对表 | `g0DiffSourceManifest.ts` 已逐列锁死 | **不重做**，只补 M 列方向缺陷登记与守卫 |

**D-2 的代价与对冲**：代价 = 矩阵 4 份 / 下区 3 份 + 一次收敛返工。对冲手段两条 ——
①**同源性守卫**（Property 7 重写）把「两份实现算法一致」变成机器可验，使副本不会各自漂移；
②每份副本在模块头声明 `CONVERGENCE_TARGET` 常量指向收敛 spec 名，使收敛时能 grep 定位全部副本与删除条件。

**收敛 spec（后续，本 spec 只登记）**：待收敛副本 = `e0SummaryMatrix` / `f0SummaryAggregation` /
`g0SummaryMatrix` / `h0SummaryMatrix`（矩阵 4 份）+ `E0SummaryLowerZone` / `G0SummaryLowerZone` /
`H0SummaryLowerZone`（下区 3 份）；判据 = 收敛不得改变任一循环既有输出（以各自基线快照为准），
每份副本的删除条件 = 其全部消费方已改指泛化件且该循环基线快照逐字节不变。

## Components and Interfaces

### 1. `g0-confirmation/g0SummaryMatrix.ts`（新建，G0 自有副本）

D-2 下不再抽泛化层，但**声明式结构照样保留**（品种/指标各带 `source_ref`），使收敛时只需把
声明搬到泛化件、算法整段替换：

```ts
/** 矩阵指标 —— 源模板 8 行，E0 只用前 6 行 */
export type MatrixMetricKey =
  | 'book_amount' | 'send_amount' | 'send_ratio'
  | 'reply_confirmed' | 'reply_over_send' | 'reply_over_book'
  | 'alt_confirmed' | 'reply_alt_over_book'

export interface MatrixMetricDef {
  key: MatrixMetricKey
  /** 源模板逐字标签 */
  label: string
  kind: 'amount' | 'ratio'
  editable: boolean
  /** 聚合字段（amount 类）或分子/分母（ratio 类） */
  sum?: 'amount' | 'confirmed_amount' | 'alt_confirmed'
  ratio?: { num: MatrixMetricKey | MatrixMetricKey[]; den: MatrixMetricKey }
  /** 源锚点，如 'G0-1!C22' */
  source_ref: string
}

export interface MatrixCategoryDef {
  /** 与 grid `account_type` 取值逐字相同 */
  name: string
  /** 账面金额取数：报表行 + 相邻循环 wp_code；null = 无固定科目不预填 */
  book: { rowCode: string; wpCode: string; hint: string } | null
  source_ref: string
}

export interface SummaryMatrixSpec {
  cycle: ConfirmCycle
  metrics: MatrixMetricDef[]      // 顺序即渲染顺序
  categories: MatrixCategoryDef[]
  /** 矩阵块源锚点，如 'G0-1!C19' */
  anchor: string
}
```

### 2. `g0SummaryMatrix.ts` 的算法部分（与 `f0SummaryAggregation` 同源）

```ts
export interface MatrixCell {
  category: string
  metric: MatrixMetricKey
  label: string
  value: number | null      // null = 分母缺失/为 0 → 渲染「-」
  kind: 'amount' | 'ratio'
  editable: boolean
  sourceHint?: string
  isManual?: boolean
}

export function buildG0SummaryMatrix(input: {
  rows: readonly ConfirmationRow[]
  bookAmounts?: Record<string, number>       // 缺该品种 = undefined ≠ 0
  manualOverrides?: Record<string, number>   // key = `${category}::${metricKey}`
}): MatrixCell[][]

export function safeRatio(num?: number | null, den?: number | null): number | null
export function sumByCategory(rows, category: string, field: keyof ConfirmationRow): number

/** 收敛锚点（裁决门 D = D-2）：收敛 spec 靠 grep 这个常量定位全部副本 */
export const CONVERGENCE_TARGET = 'confirmation-summary-matrix-convergence'
```

**F0/E0 两份一行不改**（并发 spec 在用）。同源性由 Property 7 的守卫保证：对同一
`rows`/`bookAmounts` 输入，G0 与 F0 的 8 个指标 `label`/`kind`/`editable`/`value` 序列逐字节相同。

### 3. `g0SummaryMatrix.ts` 的品种声明

```ts
export const G0_MATRIX_SPEC: SummaryMatrixSpec = {
  cycle: 'G0',
  anchor: 'G0-1!C19',
  metrics: [ /* 8 条，label 逐字取 C21~C28，source_ref 逐格 */ ],
  categories: [
    { name: '交易性金融资产',     book: { rowCode: 'BS-003', wpCode: 'G1',  hint: "TB('1101','期末余额')" }, source_ref: 'G0-1!E20' },
    { name: '长期股权投资',       book: { rowCode: 'BS-024', wpCode: 'G7',  hint: "TB('1511','期末余额')" }, source_ref: 'G0-1!F20' },
    { name: '债权投资',           book: { rowCode: 'BS-021', wpCode: 'G4',  hint: "TB('1504','期末余额')" }, source_ref: 'G0-1!G20' },
    // 源 H20 为 `……` 可扩位；以下品种取自 G0A 程序 1（B7）明列的品种
    { name: '长期应收款',         book: { rowCode: 'BS-023', wpCode: 'G5',  hint: "TB('1531','期末余额')" }, source_ref: 'G0A!B7' },
    { name: '其他债权投资',       book: { rowCode: 'BS-022', wpCode: 'G6',  hint: "TB('1506','期末余额')" }, source_ref: 'G0A!B7' },
    { name: '其他权益工具投资',   book: { rowCode: 'BS-025', wpCode: 'G8',  hint: "TB('1507','期末余额')" }, source_ref: 'G0A!B7' },
    { name: '其他非流动金融资产', book: { rowCode: 'BS-026', wpCode: 'G9',  hint: "TB('1519','期末余额')" }, source_ref: 'G0A!B7' },
    { name: '交易性金融负债',     book: { rowCode: 'BS-042', wpCode: 'G10', hint: "TB('2101','期末余额')" }, source_ref: 'G0A!B7' },
  ],
}
```

科目码只作**兜底与展示**（R4.4）：`rowCode` 是权威，`hint` 供溯源 tooltip；运行态账面金额取相邻循环 render-config 的 `project_context.tb_amount`，由 `four_table/g_cycle_specs.py` 的语义定位产生。

### 4. `g0-confirmation/g0SummaryLowerZone.ts` + `G0SummaryLowerZone.vue`（G0 自有副本）

```ts
export interface LowerZoneTextDef {
  block: 'matrix' | 'sample_selection' | 'audit_note' | 'conclusion' | 'tips'
  key: string
  /** 逐字源模板文字；跨格已合并 */
  text: string
  /** 源锚点，多格合并用 '+' 连接，如 'G0-1!X21+X22' */
  anchor: string
  /** true = 只读方法论上下文；false = 下方有录入位置 */
  readonly: boolean
  /** placeholder（源模板示例文字） */
  placeholder?: string
}

export interface LowerZoneSpec {
  cycle: ConfirmCycle
  blocks: { key: string; anchor: string; title: string }[]
  texts: LowerZoneTextDef[]
  /** 录入键前缀，如 'G0-1-lower-' */
  keyPrefix: string
  /** 参考结论选项（源 A55~A57） */
  refConclusions?: { code: 'A' | 'B' | 'C'; text: string; anchor: string }[]
  /** 编制说明（只读折叠） */
  preparationNotes?: { text: string; anchor: string }[]
}
```

G0 的 `sample_selection` 块与 E0 语义不同：E0 是 3 段只读准则文字（银行账户全部函证），G0 是 **6 项可录入**（测试总体/特定样本/抽样总体/样本量/抽样方法/抽样过程）→ 由 `LowerZoneTextDef.readonly` 区分，组件按 `readonly` 决定渲染只读段落还是 textarea + AI 入口。**这正是 D-2 下不强行泛化的实证理由**：两个循环的同名块语义不同，泛化件必须先有 `readonly` 维度才能容纳，收敛时以此为设计输入。

`G0SummaryLowerZone.vue` props：`{ projectId, wpId, readonly, matrix, responses }`，emits `{ update, ai-generate }`。渲染顺序按 `G0_LOWER_ZONE_BLOCKS`。同样声明 `CONVERGENCE_TARGET = 'confirmation-summary-lower-zone-convergence'`。

**`E0SummaryLowerZone.vue` 一行不改**（零消费方，接线属 E0 侧遗留）。

### 5. `confirmationColumnSpec.ts` 扩展（标签覆盖 + G0 列集）

```ts
/** 枢纽 → 列标签覆盖（源模板用词不同不强行统一，Requirement 8.3） */
export const CYCLE_COLUMN_LABEL_OVERRIDES: Record<ConfirmCycle, Record<string, string>> = {
  D0: {}, E0: {}, F0: {},
  G0: {
    confirm_index: '询证函索引号',   // 源 G0-1!B5
    account_type:  '账户/交易',      // 源 G0-1!E6
    amount:        '账面期末余额',   // 源 G0-1!F6
    entity_address:'收件地址',       // 源 G0-1!J6
    is_replied:    '是否收到回函',   // 源 G0-1!L6
    match_status:  '是否相符',       // 源 G0-1!N6
    reply_date:    '回函日期',       // 源 G0-1!O6
    reply_from_addr:'回函地址',      // 源 G0-1!Q6
    difference:    '差异',           // 源 G0-1!T6
    remark:        '其他说明/备注',  // 源 G0-1!W6
  },
  H0: {}, K0: {}, L0: {},
}

CYCLE_VARIANT_COLUMNS.G0  = ['row_conclusion']                              // 源 AB5 审计结论
CYCLE_EXCLUDED_COLUMNS.G0 = ['contact_person', 'contact_phone', 'currency'] // 源模板无此三列
```

`resolveConfirmationColumns(cycle)` 在返回前套用 `CYCLE_COLUMN_LABEL_OVERRIDES[cycle]`（浅拷贝列对象，不改 `BASE_CONFIRMATION_COLUMNS` 本体）。六个非 G0 循环覆盖表为空 → 返回值逐字节不变。

`row_conclusion` 的 `group` 当前是 `send_memo`（K0/L0 语义）。G0 的 AB 列是独立第 5 段 → 复用既有 `row_summary` group（E0 在用，`COLUMN_GROUP_LABELS.row_summary = '行级审计结论'`），通过 variant 定义覆盖 group：新增 `g0_row_conclusion` variant def（`key: 'row_conclusion'` 保持字段名，`group: 'row_summary'`）。

### 6. `cycleConfirmationMeta.ts` 扩展（sheetName / indexLabel 分离）

```ts
export interface ConfirmationSheetRef {
  /** 定位真源：源模板真实 tab 名（逐字，含全/半角括号与索引号笔误） */
  sheetName: string | null
  /** 展示真源：底稿目录索引号 */
  indexLabel: string
  /** 源模板 tab 名索引号与目录不一致时的说明（tooltip） */
  indexTypoNote?: string
}
```

`CycleConfirmationMeta` 新增 `sheets: Record<'summary'|'entityVerify'|'followup'|'diff'|'diffSecurities'|'diffChecklist'|'altPrimary'|'altSecondary'|'reliability'|'fraud'|'program', ConfirmationSheetRef | null>`，既有的 `summaryCode`/`diffCode`/… **保留不动**（零回归；由 `sheets` 派生或并列声明），G0 的 `diffSecuritiesCode` 由 `'G0-3S'` 改为 `'G0-4'`（目录索引号），定位交给 `sheets.diffSecurities.sheetName`。

G0 声明（`g0SheetRegistry.ts` 提供，meta 引用）：

| 槽 | sheetName（定位） | indexLabel（展示） | 笔误说明 |
|---|---|---|---|
| program | `函证程序表G0A` | G0A | — |
| summary | `函证结果汇总表G0-1` | G0-1 | — |
| entityVerify | `核实被函证单位信息G0-2` | G0-2 | — |
| followup | `跟函函证过程控制G0-3` | G0-3 | — |
| diffSecurities | `函证差异核对表G0-3（证券投资）` | **G0-4** | 源 tab 名索引号笔误，目录为 G0-4 |
| diff | `函证差异核对表G0-4(非证券投资)` | **G0-5** | 源 tab 名索引号笔误，目录为 G0-5 |
| altPrimary | `替代程序检查表G0-6` | G0-6 | — |
| reliability | `邮件传真回函可靠性验证G0-7` | G0-7 | — |
| fraud | `函证程序舞弊风险评价表F0-8` | **G0-8** | 源 tab 名写 F0-8，目录为 G0-8 |
| diffChecklist / altSecondary | null | — | G0 无此表 |

### 7. `CrossWorkpaperNav.vue` 修复

删 `NAV_DEFINITIONS` 写死块，改 `props.wpCode` → `buildCrossWorkpaperNavDefs(props.wpCode)`；导航项携带 `sheetName`；点击时若目标在同一工作簿则 emit `navigate-sheet`（宿主走 `?sheet=` 切页），否则 emit 既有 `navigate`。

### 8. `ConfirmationSampling.vue` 对齐 6 项（**`isG0` 门控**，裁决门 E）

**实测前提**：该组件唯一消费方是 `GtConfirmationSummary.vue`（`grep` 全仓确认），而后者服务全部七枢纽 →
无门控地改成 6 项会同时改变 D0/E0/F0/H0/K0/L0 的样本选择区，与 R11.1 冲突。

故新增 `cycle?: ConfirmCycle` prop（`GtConfirmationSummary.vue` 传入既有的 `props.wpCode` 派生值），
组件内 `const isG0 = computed(() => cycle === 'G0')`：

- `isG0` → 渲染源模板 6 项（下表字段族）
- 其余 → 渲染既有 4 项，**渲染路径逐字节不变**（守卫以基线快照比对）

**门控是渲染层概念**：`SamplingConfig` 的 6 个字段对全部枢纽都可读写，`emit('change', field, value)`
不按枢纽分叉 → 其余枢纽若已存 6 项数据不会因门控丢失（R3.6.3）。平台级统一为 6 项登记为待收敛项
（见 tasks.md §Notes「收敛 spec 登记」）。

字段改用替代程序族的 `SamplingConfig`（`confirmation/alternativeD05/alternativeD05Types.ts`）：

| 源模板项 | 源锚点 | 字段 | 来源 |
|---|---|---|---|
| 测试总体 | `G0-1!J20` | `test_population` | **additive 新增**（`test_scope` 是「测试范围」5 点选项，语义不同，不可复用） |
| 特定样本 | `G0-1!J21` | `specific_samples` | `SamplingConfig` 既有 |
| 抽样总体 | `G0-1!J22` | `sampling_population` | `SamplingConfig` 既有 |
| 确定的抽样样本量 | `G0-1!J23` | `sample_size` | `SamplingConfig` 既有 |
| 抽样方法 | `G0-1!J25` | `sampling_method` | `SamplingConfig` 既有 |
| 抽样过程 | `G0-1!J26` | `sampling_process` | `SamplingConfig` 既有 |

placeholder 逐字取源模板示例（`K20`/`K21`/`K22`/`K23`/`K25`/`K26`；`K24`/`K27` 是补充说明段落，作只读提示）。旧 4 字段读回映射：`sampling_size → sample_size`、`sampling_criteria → specific_samples`、`sampling_method` 同名沿用、`sampling_conclusion` 独立保留（源模板无对应项，作源外增强登记）。自动统计卡片保留。

### 9. `blockColumnConfigsG06.ts` 重构

```
block1 ①检查初始投资协议、公司章程等（源 A9）
  被投资单位 | 投资比例 | 投资金额 | 投资条款 | 索引号
  （删源模板没有的记账凭证 5 列；补 investment_term）

block2 ②本期发生额检查（源 A15，借贷双区 A16/A24）
  记账凭证{日期|凭证编号|业务内容|对方科目|金额}
  + 支持性文件1{识别特征|信息1|信息2}
  + 支持性文件2{识别特征|信息1|信息2}
  + 索引号 | 是否异常
  （`support_doc` 单列拆成 6 列；旧值迁移进 `support1_feature`）

block3 ③检查期后是否被出售或赎回（源 A32）
  记账凭证 5 列
  + 投资协议/交易确认单/交割单{日期或编号|被投资单位名称|金额}
  + 银行回单{日期或编号|付款方|金额}
  + 索引号 | 是否异常

block4 ④源外增强（持仓证明 / 股利收入 / 公允价值佐证）
  保留全部既有字段名，逐列登记理由（数据零丢失红线）
```

新增 `G06_SOURCE_EXTRA: { field; label; block; reason }[]` 登记全部源外字段（含 block3 现有的 `disposal_amount`/`net_proceeds`/`sell_qty`/`trade_price`/`original_cost`/`fee`/`disposal_gain`/`bank_received` —— 迁入 block4 或标注为 block3 增强列，由守卫要求全部在册）。

### 10. 后端改动

- `tests/test_g0_source_template_facts.py` —— R1 全部断言（openpyxl 直读，不连库）
- `tests/test_g0a_procedure_template.py` —— R8 守卫（12 条逐字 + 程序分类 + 单一定义）
- `data/procedure_table_templates.json` —— `/tables/G0A` 12 条补 `program_category`；按分类修正 `applicable_default`；删根级 `/G0A`
- `scripts/fix/fix_g0_prefill_presets.py` —— R9 幂等脚本（`--dry-run`/`--check`/round-trip 自检）
- `tests/test_g0_prefill_presets.py` —— R9 守卫（只扫语义字段）
- `routers/review_dialog._SECTION_PROMPTS` —— 补 G0-1 下区 5 条审计说明 + 1 条审计结论 prompt（每条 ≥20 字，写明源模板口径 + 「不得虚构」）

## Data Models

### G0-1 下区录入键

| 键 | 内容 | 源锚点 |
|---|---|---|
| **`G0-1-matrix-{品种}-{指标key}`** | 矩阵手工覆盖（含品种账面金额 `book_amount`） | `E21:H21` + 派生格 |
| `G0-1-sampling` | 样本选择 6 项（`SamplingConfig` JSON） | `J19` 块 |
| `G0-1-lower-audit-note-{1..5}` | 审计说明 5 段 | `S20`/`X20`/`S24`/`S25`/`S28` |
| `G0-1-lower-conclusion` | 审计结论 | `C30` |
| `G0-1-lower-conclusion-ref` | 采用的参考结论代码（A/B/C） | `A55~A57` |

**🔴 矩阵键名真源 = `g0MatrixDataSources.g0MatrixOverrideItemId(category, metric)` → `G0-1-matrix-{品种}-{指标key}`**
（Task 7 已交付并由 `g0SummaryMatrix.spec.ts` 56 例钉死）。本表原先写的
`G0-1-lower-book-amount-{category}` 与 `G0-1-lower-matrix-override-{category}::{metricKey}`
**是立项时的陈旧设想，已作废** —— 账面金额手工值就是 `book_amount` 这个可编辑指标的覆盖值，不另立键。
Task 18 的 `cell_ref` 必须对齐该真源，否则预设指向没人读的键 = 死配置。

内存态 `manualOverrides` 的形态仍是 `key = ${category}::${metricKey}`（由 `parseG0ManualOverrides`
从上述持久化键解析而来），只对 `editable` 指标生效 —— **持久化键与内存键是两层，勿混用**。

### G0-1 grid 行字段映射（源 28 列 → `ConfirmationRow`）

| 源列 | 源标签 | 字段 | 归属段 |
|---|---|---|---|
| A | 序号 | `seq` | send_info |
| B | 询证函索引号 | `confirm_index` | send_info |
| C | 选取样本目的 | `sample_purpose` | send_info |
| D | 被询证单位名称 | `entity_name` | send_info |
| E | 账户/交易 | `account_type` | send_info（矩阵品种维度） |
| F | 账面期末余额 | `amount` | send_info（矩阵发函金额来源） |
| G | 函证方式 | `confirmation_method` | send_info |
| H | 发函日期 | `send_date` | send_info |
| I | 发函单号 | `send_doc_no` | send_info |
| J | 收件地址 | `entity_address` | send_info |
| K | 地址核查是否一致 | `send_addr_match` | send_info |
| L | 是否收到回函（√） | `is_replied` | reply_info |
| M | 回函方式 | `reply_method` | reply_info |
| N | 是否相符 | `match_status` | reply_amount |
| O | 回函日期 | `reply_date` | reply_info |
| P | 回函快递单号 | `reply_courier_no` | reply_info |
| Q | 回函地址 | `reply_from_addr` | reply_info |
| R | 发函地址与回函地址是否一致 | `send_reply_addr_match` | reply_info |
| S | 回函金额 | `reply_amount` | reply_amount |
| T | 差异 | `difference` | reply_amount（派生） |
| U | 可确认金额 | `confirmed_amount` | reply_amount（矩阵回函确认来源） |
| V | 调节索引 | `diff_ref_index` | alternative |
| W | 其他说明/备注 | `remark` | alternative |
| X | 是否采取替代程序（√） | `use_alternative` | alternative |
| Y | 替代后可确认金额 | `alt_confirmed` | alternative（矩阵替代确认来源） |
| Z | 替代后不可确认金额 | `alt_unconfirmed` | alternative |
| AA | 替代程序索引号 | `alt_ref_index` | alternative |
| AB | 审计结论 | `row_conclusion` | row_summary（**新增**） |

VLOOKUP 联动（源 D/G/J/K/M/Q/R 列自 G0-2 带入，列序 2/3/4/10/16/19/22）由既有 `importFromSummary` 族承担，本 spec 不改，只在守卫中钉死映射列序。

### `g0SourceDefects.ts` 源缺陷登记表

```ts
export interface G0SourceDefect {
  id: string
  anchor: string        // 'G0-1!E24'
  defect: string        // 源模板事实描述
  intent: string        // 正确意图
  handling: 'implement-intent' | 'display-as-is' | 'index-label-correction'
  note?: string
}
```

6 条：`directory-serial`（`底稿目录!D7`）/ `matrix-sumif-range`（`G0-1!E24`）/ `xref-reliability`（`G0-1!S24`）/ `xref-followup-self`（`G0-2!AA6`）/ `securities-mv-diff-direction`（`函证差异核对表G0-3（证券投资）!M7:M17`）/ `tab-index-typos`（三处 tab 名）。

## Error Handling

| 情形 | 处置 | 依据 |
|---|---|---|
| 矩阵分母缺失或为 0 | 返回 `null` → UI 渲染「-」 | R3.4；绝不产出 NaN/Infinity，也不用 0 冒充 |
| 某品种账面金额取不到（相邻循环无 render-config / 本项目无该科目） | `bookAmounts[category]` 为 `undefined`（非 0），该品种比例行显「-」并在 tooltip 写「本项目无此科目或未编制 Gx 审定表」 | R4.3；「无此科目」与「余额为 0」必须可区分 |
| 品种在 grid 中无任何行 | 金额指标为 0（求和为空集）、比例为 `null` | 与源模板 `SUMIF` 空集返 0 一致 |
| 手工覆盖写在不可编辑指标上 | 忽略且不报错（守卫断言其不生效） | R3.5 / Property 6 |
| 下区文字锚点在源模板读不到 | 守卫打红（fail closed），不静默跳过 | R1.8 |
| 跨表导航目标槽 `sheetName` 为 null | 不生成导航入口（不产生「未找到」的死链） | R5.3 |
| 深链 `?sheet=` 未命中 | 走既有 `resolveSheetNameByDeepLink` 三级兜底（原样 → 归一相等 → 归一后缀/包含），仍不中则回退底稿目录并提示 | 平台既有语义 |
| G0-6 旧载荷含 `support_doc` | 迁移到 `support1_feature`，原字段保留读回 | R7.5 数据零丢失 |
| 预设纠偏脚本 round-trip 自检失败 | exit 2 并不写盘 | R9.4；防全文件重排与并发冲突 |
| `--check` 发现欠账 | 非 0 退出并逐条列出 | R9.4 |
| AI 生成失败（下区审计说明） | 提示失败并保留原文，不写入空串 | 平台既有语义 |

## Testing Strategy

**分层**

| 层 | 内容 | 文件 |
|---|---|---|
| 源模板事实（后端，不连库，可进 CI） | R1 全部 + G0-6 两级表头 + G0A 12 条 + 下区锚点 + D0 对比 | `backend/tests/test_g0_source_template_facts.py` |
| 程序表模板（后端） | Property 19/20 | `backend/tests/test_g0a_procedure_template.py` |
| 公式预设（后端） | Property 21/22/23 | `backend/tests/test_g0_prefill_presets.py` |
| 源缺陷双向（后端） | Property 24/27 | 并入 `test_g0_source_template_facts.py` |
| 矩阵引擎（前端，含 PBT） | Property 4/5/6/7 | `confirmation/__tests__/summaryMatrix.spec.ts` |
| 列集与标签（前端） | Property 2/3 | `confirmation/__tests__/confirmationColumnSpec.g0.spec.ts` |
| 下区（前端，交叉读源码 + 后端 JSON） | Property 8/9 | `confirmation/__tests__/summaryLowerZone.spec.ts` |
| 跨前后端锁死（前端读后端 py 源码） | Property 10/11 | `g0-confirmation/__tests__/g0SummarySpec.spec.ts` |
| 导航与注册（前端） | Property 12/14/15 | `g0-confirmation/__tests__/g0SheetRegistry.spec.ts` |
| 消费方存在性（前端，扫全仓） | Property 13 | 并入 `g0SheetRegistry.spec.ts` |
| G0-6 区块（前端 + 后端交叉） | Property 16/17/18 | `alternativeG06/__tests__/blockColumnConfigsG06.spec.ts` + 后端事实守卫 |
| 共享组件无分叉（后端 + 前端） | Property 25/26 | 事实守卫 + `confirmation/__tests__/g0SharedComponentCoverage.spec.ts` |

**守卫编写铁律（本 spec 直接适用）**

- 读源码型断言必须先 `stripComments()`，且 `stripComments()` 自身要有反向自检（用内联 fixture，不依赖真实文件恰好含反例）。
- 截函数体用花括号配对，不用固定字符窗口（会溢出到下一个函数）。
- 前端读后端 py 源码时注意 `REPO_ROOT` 回退层数：`confirmation/__tests__/` 下与 `g0-confirmation/__tests__/` 下层数不同，逐个实测不照抄。
- 每条结构断言配反向自检；断言前先确认抽取结果非空（防正则失效导致断言空转）。
- 基线快照类断言（Property 3/7/20）必须在改造**之前**采集并入库，改造后比对。

**实测（浏览器 + 真实 DB 只读）**

1. G0-1 下区四块渲染 → 录入 ≥2 行 grid（不同品种）→ 矩阵值随之变化（发函/回函/替代三列）→ 手工覆盖账面金额 → 比例更新。
2. 样本选择 6 项录入 → `checklist_responses` 落库验证键名。
3. 审计说明 5 段 + 审计结论录入 → 落库验证；AI 按钮返回 200 且不虚构。
4. 跨表导航条在 G0 上显示 G0 自己的槽位（含修正后的 G0-4/G0-5/G0-8 展示值）→ 点击切页成功。
5. G0-6 三区块列渲染与源模板一致 → 录入含 `1234567.5` 的金额显示 `1,234,567.50`（`WpAmountInput`）。
6. G0A 程序表：备选与 IPO 专项 4 条默认未勾选。
7. 测完按实测前快照**逐字节复原**测试数据（`checklist_responses` / `working_paper.parsed_data`），并清理 `tmp_*` 诊断产物。

**验收门**：后端 G0 相关全绿 + 前端 confirmation 全量无新增失败（预存在基线单独列出）+ CI job `g0-confirmation-alignment` / `-frontend` 绿 + 上述 7 项实测通过。

## Correctness Properties

### Property 1: 源模板 10 sheet 全可见且名称逐字固化

守卫以 openpyxl 直读源 xlsx，断言 sheet 数为 10、`sheet_state` 全为 `visible`、名称集合与 R1.1 清单逐字相等。反向自检：改写任一名称常量必打红。

**Validates: Requirements 1.1, 6.4**

### Property 2: G0-1 上区列集与源模板 28 列一一映射

`resolveConfirmationColumns('G0')` 的列标签集合（套用标签覆盖后）与源 xlsx `函证结果汇总表G0-1` 的 28 个叶子列（A/B/AB 在 R5，其余在 R6）**一一映射且双侧无剩余**；分段归属按 R5 合并区，其中 `S 回函金额`/`T 差异` 按 D0/F0 意图归入 `reply_amount` 段（源模板段头右移，见 Property 24 缺陷 #7）。反向自检：删去 `CYCLE_EXCLUDED_COLUMNS.G0` 任一项则出现"平台多列"必打红。

**Validates: Requirements 1.2, 2.1, 2.2, 2.5**

### Property 3: 标签覆盖对其余六循环逐字节无影响

对 D0/E0/F0/H0/K0/L0 分别断言 `resolveConfirmationColumns(cycle)` 的序列化结果与改造前基线快照逐字节相等。

**Validates: Requirements 2.4, 11.1**

### Property 4: 矩阵取值等于源模板 SUMIF 口径

对随机生成的 grid（随机品种 × 随机金额），断言 `buildSummaryMatrix` 的 `send_amount` / `reply_confirmed` / `alt_confirmed` 分别等于按品种过滤后 `amount` / `confirmed_amount` / `alt_confirmed` 之和（PBT）。反向自检：去掉品种过滤后各品种值之和必不等于逐品种值。

**Validates: Requirements 3.3, 1.3**

### Property 5: 分母缺失或为 0 时返回 null 而非 0/NaN

对 `book_amount` 为 `undefined` 与 `0` 两种情形，断言三个比例指标与末行比例均为 `null`；断言矩阵中不存在 `NaN`/`Infinity`。

**Validates: Requirements 3.4**

### Property 29: 品种可见性「有就显示没有隐藏」且无录入死锁

（逻辑上属 Property 5 一族，编号续排以符合 spec schema）


断言 `visibleG0Categories(input)` 的四条行为：①grid 有该品种行 / 取到账面金额 / 有手工值 三者任一成立即可见 ②三者皆无即隐藏 ③8 个品种全无内容时**返回全部候选**（不返空数组）④`showAll=true` 时返回全部候选。断言隐藏不改变 `buildG0SummaryMatrix` 的计算结果（隐藏是渲染层概念，`manualOverrides` 与 `bookAmounts` 里被隐藏品种的值不被清除）。反向自检：去掉「全无内容 → 返全部」分支则空底稿必返空数组（死锁复现）。

**Validates: Requirements 3.2.1, 3.2.2, 3.2.3, 3.2.4, 3.2.6**

### Property 30: 自定义品种可扩展且参与聚合的前提被明示

断言候选全集之外的自定义品种一旦其名称与 grid `account_type` 取值一致即参与 `sumByCategory` 聚合；断言名称不一致时该品种三个金额指标为 0（而非报错），且实现侧提供该要求的提示文案（源码级断言提示文字存在）。

**Validates: Requirements 3.2.5**

### Property 6: 手工值优先于自动取数

对同一格同时提供 `bookAmounts` 与 `manualOverrides`，断言输出取手工值且 `isManual === true`；对 `editable === false` 的指标，断言 `manualOverrides` 不生效。

**Validates: Requirements 3.5**

### Property 7: G0 矩阵与 F0 矩阵同源（D-2 的分叉对冲）

对同一 `rows`/`bookAmounts` 输入，断言 `buildG0SummaryMatrix` 与 `buildF0SummaryMatrix` 的 8 个指标在 `label`/`kind`/`editable`/`value` 四项上**逐字节相同**（品种名不同故按指标序号对齐比较）。断言 `f0SummaryAggregation.ts` 与 `e0SummaryMatrix.ts` 与 `E0SummaryLowerZone.vue` **未被本 spec 改动**（git 层面由 review 保证，测试层面断言其导出符号集合与基线一致）。断言 `g0SummaryMatrix.ts` 与 `G0SummaryLowerZone.vue` 声明了 `CONVERGENCE_TARGET`。反向自检：把 G0 的某个比例改成分母 0 返 0（F0 返 null）则必打红。

**Validates: Requirements 11.1, 11.2, 11.2.1, 11.2.2, 11.3, 11.8**

### Property 8: 下区四块文字与源模板逐字一致且跨格已合并

守卫用 openpyxl 读 `G0-1` 下区各锚点，断言 `LowerZoneSpec.texts` 的 `text` 与源单元格逐字相等；对 `anchor` 含 `+` 的条目，断言其 `text` 等于两格文字拼接且不以标点开头（防半句话）。

**🔴 实证修正（2026-08-04）**：审计说明 5 项的结构是**小标题 + 可选只读提示语**，不是「一句话拆两格」——
故 `LowerZoneTextDef` 区分 `title`/`hint` 两个角色，**只有 `hint` 可能由多格拼接**，且全下区仅第 2 项
（`X21`+`X22`）需要拼接。守卫因此分两组断言：①每项 `title` 与单一源格逐字相等（`S20`/`X20`/`S24`/`S25`/`S28`）
②唯一的拼接 `hint` 等于 `X21`+`X22` 且不以标点开头。**禁止**把 `X20`+`X21`+`X22` 或 `S25`+`S26` 当成一句话拼接
（会产出「4、针对不符事项的程序如果回函中存在未函证的其他信息…」的错句）。另断言参考结论内容取自 **B 列**
（`B55`/`B56`/`B57`，A 列只是 `A、`/`B、`/`C、` 标签）、函证注意事项 8 条取自 **`B44:B51`**
（`A43` 只是标题；**只扫 A 列的探针会整段漏掉**）。

**Validates: Requirements 3.1, 3.2, 3.7, 3.8, 3.9, 3.10**

### Property 9: 样本选择 6 项字段与替代程序族同源

断言 `ConfirmationSampling.vue` 使用的字段名集合 ⊇ `SamplingConfig` 的 5 个同义字段 ∪ `{test_population}`；断言旧 4 字段的读回映射对每个旧字段都有落点（无数据丢失）；断言源模板 6 项 placeholder 与源单元格 `K20/K21/K22/K23/K25/K26` 逐字相等。反向自检：断言 `test_population` 与 `test_scope` 是两个不同字段且 `ConfirmationSampling.vue` 不使用 `test_scope`（语义为 G0-6 的「测试范围」）。

**Validates: Requirements 3.6, 3.6.1, 3.11**

### Property 31: 样本选择 6 项由 isG0 门控且六枢纽渲染不变

（逻辑上属 Property 9 一族，编号续排以符合 spec schema）

源码级断言 `ConfirmationSampling.vue` 存在 `cycle` prop 与 `isG0` 判定，且 6 项字段的渲染块处于 `isG0` 条件内；断言 `GtConfirmationSummary.vue` 向该组件传入了 `cycle`（**传不存在的 prop = 静默失效**，故同时从 `defineProps` 动态抽合法名比对调用点）。挂载渲染断言：`cycle='D0'` 时可见字段集合 == 改造前 4 项基线、`cycle='G0'` 时 == 6 项。反向自检：去掉门控则 `cycle='D0'` 必出现 6 项（六枢纽回归复现）。另断言门控只影响渲染 —— `cycle='D0'` 下写入 `sampling_population` 仍能读回（R3.6.3）。

**Validates: Requirements 3.6.2, 3.6.3, 11.1**

### Property 10: 矩阵品种与后端报表行双向锁死

断言 `G0_MATRIX_SPEC.categories` 的每个 `rowCode` 都在 `four_table/g_cycle_specs.py` 的声明中出现（读后端源码交叉比对），且后端 G 循环声明的报表行若属矩阵覆盖科目则必须在前端清单内。反向自检：前端多一个品种或后端改一个 row_code 都打红。

**Validates: Requirements 4.1, 4.2, 4.5**

### Property 11: 科目码不参与运行态取数

源码级断言：`g0SummarySpec.ts` 的科目码字面量只出现在 `hint` 字符串内，不出现在任何请求参数、事件载荷或查询条件中。守卫先 `stripComments()` 并含反向自检。

**Validates: Requirements 4.3, 4.4**

### Property 12: 跨表导航项按循环解析且无失效入口

断言 `CrossWorkpaperNav.vue` 源码不含 `D0-` 字面量数组定义；断言 `buildCrossWorkpaperNavDefs('G0-1')` 不产生 `G0-3S`；断言其返回的每个槽位在 `g0SheetRegistry` 中有非 null `sheetName`。

**Validates: Requirements 5.1, 5.3, 5.4, 5.5**

### Property 13: 泛化件与新建件均有真实消费方

源码级扫描：`summaryMatrix.ts` / `SummaryLowerZone.vue` / `g0SummarySpec.ts` / `g0SheetRegistry.ts` / `g0SourceDefects.ts` / `buildCrossWorkpaperNavDefs` 每一项至少有一个非测试消费方（排除 `components.d.ts` 与 `__tests__`）。

**Validates: Requirements 5.6, 11.3, 11.5, 11.6**

### Property 14: 定位值与展示值分离且不混用

断言 `g0SheetRegistry` 每条同时有 `sheetName` 与 `indexLabel`；断言三处笔误条目的 `indexLabel !== sheetName` 中的索引号片段且 `indexTypoNote` 非空；源码级断言 sheet 请求/深链参数只使用 `sheetName`。

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

### Property 15: sheet 注册与 override / 分类表三向一致

断言 `g0SheetRegistry` 的 10 个 `sheetName` 与 `workpaper_sheet_classification` 的 G0 记录（离线快照或 fixture）逐字相等；断言 `wp_code_overrides.json` 含三条含索引号笔误的**全名键**。

**Validates: Requirements 6.5**

### Property 16: G0-6 四区块列与源模板交叉锁死

守卫 openpyxl 直读 `替代程序检查表G0-6`，断言 block1/block2/block3 的列 label 序列与源模板两级表头逐字一致；断言 block1 不含记账凭证列且含「投资条款」；断言 block2 含支持性文件 1/2 各 3 列；断言所有源外字段都在 `G06_SOURCE_EXTRA` 登记表内。

**Validates: Requirements 1.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.8**

### Property 17: G0-6 数据零丢失

断言重构前的字段名集合 ⊆ 重构后的字段名集合 ∪ 迁移映射的源侧；对含旧 `support_doc` 的载荷，断言迁移后值落在 `support1_feature`。

**Validates: Requirements 7.5**

### Property 18: 编制指导文案与现行区块一致

源码级断言 `GtConfirmationAlternativeG06.vue` 的 `details` 文案不含已废弃的四区块表述（「持仓证明」「投资收益/股利」「处置收益」「公允价值佐证」作为**区块编号 ①②③④** 的搭配），且提到的区块名与 `BLOCK_COLUMN_CONFIGS_G06` 的 `title` 一致。

**Validates: Requirements 7.6**

### Property 19: G0A 12 条与源模板逐字一致且程序分类落地

断言 `/tables/G0A` 恰 12 条、`content`/`ref_index` 与源 `B7:B18`/`E7:E18` 逐字相等（第 8、12 条 `ref_index` 为空）、`program_category` 与源 `D7:D18` 逐字相等（12 条全部非空）；断言分类集合为 `{常规★(8), 备选(2), IPO/上市/新三板/重组/舞弊应对(1), 舞弊应对/IPO/上市/新三板/重组(1)}`；断言 `applicable_default` **保持 `"yes"` 不变**并配反向断言说明「写 `"no"` 是死配置」（`_a_program.py` 只认 `"na"`）。

**Validates: Requirements 1.6, 8.1, 8.2, 8.3, 8.5**

### Property 20: G0A 的运行时权威唯一且平台级议题可见

断言 `get_template('G0A')` 返回 12 条版本（`name == '函证程序表'`）；WHERE 根级 `/G0A` 仍存在 THE 断言其 `items` 数与 `tables` 版本不同，且断言消息指向平台级议题「根级 66 条同族条目 / 57 条重复分叉 / 9 条根级独有在运行时不可用」；断言其余 120 个 `tables` 模板与 66 条根级条目的 `applicable_default` 分布与 Task 3 基线快照一致（零回归）。

**Validates: Requirements 8.4, 8.5, 8.6, 8.7**

### Property 21: G0 预设 sheet 名与科目均可验证

断言 G0 预设块 `sheet` 在源 xlsx 的 `wb.sheetnames` 中存在；断言预设不含 `TB_SUM('....~....')` 跨科目族区间；断言每个引用科目码在标准科目表内且属 G 循环报表行引用集合。

**Validates: Requirements 9.1, 9.2, 9.6**

### Property 22: 预设纠偏脚本幂等且 round-trip 安全

断言 `--check` 在已修正状态下 exit 0；断言连续两次 `--apply` 第二次为 0 项变更；断言脚本对未改动条目的 `json.dumps` 逐字复现原文（否则 exit 2）。

**Validates: Requirements 9.3, 9.4**

### Property 23: 预设守卫只扫语义字段

源码级断言守卫不对整块序列化结果做"不得出现"断言，只对 `formula`/`account_codes`/`cell_ref`/`sheet` 取值判定；含反向自检（在 `description` 内写入被禁字样时守卫仍应通过）。

**Validates: Requirements 9.5**

### Property 24: 源模板缺陷双向断言

对 `g0SourceDefects.ts` 的每条登记（**7 条**），断言（a）源 xlsx 确实存在该缺陷（openpyxl 读该锚点验证，已由 `backend/tests/test_g0_source_template_facts.py::TestSourceDefectsExist` 实现）与（b）平台实现已按 `handling` 处置；两者缺一即打红。对 `handling === 'display-as-is'` 的条目，断言展示文字与源原文逐字相等。缺陷 #7（段头右移）以 D0-1 的 `S5:W5` 作「正确意图」旁证，并断言两表合并区确实不同（否则说明源模板已被改动，spec 前提失效）。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

### Property 25: G0-3 / F0-8 无需 G0 专属分叉

断言源 xlsx 的 `跟函函证过程控制G0-3` 与 `函证程序舞弊风险评价表F0-8` 正文与 D0 对应 sheet 逐行相等；断言 `memoTemplates.scenariosFor('G0')` 返回通用场景集、`PRESET_FRAUD_ITEMS` 无 G0 分支。

**Validates: Requirements 1.5**

### Property 26: 回函可靠性 14 列已覆盖 G0-7

断言 `ReliabilityRow` 的字段族覆盖源 `邮件传真回函可靠性验证G0-7` 的 14 个叶子列（含 `G:M` 七子列验证组），逐列给出映射；无缺列即通过，缺列打红。

**Validates: Requirements 1.5, 11.1**

### Property 27: 差异表证券侧 M 列方向按意图统一

断言源 xlsx `M7 == '=J7-G7'`（缺陷存在）且 `SECURITIES_DIFF_COLUMNS` 的 `market_value_diff` 语义注释/派生实现为 `账面 − 回函`（与 `qty_diff`/`fv_diff` 同向）。

**Validates: Requirements 10.1, 10.2**

### Property 28: 并发边界不变式（**已收窄**，2026-08-04）

**原表述作废**：「F0 spec 仍含 `- [-]`/`- [~]` 时不得标记完成」——实测 F0 剩余 1 个 `[-]` + 2 个 `[~]` 全是浏览器实测项且用户已明确中止该轮，标记不会消失 → 原表述会**永久阻塞** G0 Wave 3，是个死条件。

**收窄后的判据（两条同时成立才可动共享文件）**：

1. **按文件而非按 spec 标记**：目标共享文件在 `git status` 中的 mtime 距当前 **> 30 分钟**（判「不在飞」；实证手段 = `os.path.getmtime`，30 分钟阈值来自本轮观测到的并发编辑节奏 —— Wave 6 三个文件在 8 分钟内被连续改动）。
2. **F0 侧触及该文件的任务已收口**：对 `GtConfirmationSummary.vue`，判据是 F0 tasks.md 的 Task 16（`ConfirmationSampling`/矩阵相关）为 `[x]`；`[-]`/`[~]` 项若不触及该文件则不构成阻塞。

**配套**：动共享文件前后各跑一次目标文件的既有守卫全量，diff 为空才算「最小 hunk 未伤及既有代码」。本 Property 以 spec 文档交叉检查表达，非代码守卫。

**Validates: Requirements 11.4, 11.5**
