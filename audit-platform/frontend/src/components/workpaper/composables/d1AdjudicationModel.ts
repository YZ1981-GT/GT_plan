/**
 * d1AdjudicationModel — D1 审定表锚点与分类合计的**单一真源**（零依赖纯函数）
 *
 * Spec: .kiro/specs/d1-extraction-chain-completion/
 *       (Requirements 2.x / 3.x / Property 4, 5, 6, 7)
 *
 * ## 为什么必须收敛成一个模块
 *
 * 改造前 D1 有**四处**各自拼 `D1-adj-*` 锚点字符串，其中三处拼错、静默失效：
 *
 * | 消费方 | 读的锚点 | 实际写入方 | 结果 |
 * |--------|----------|------------|------|
 * | `useD1Adjudication`（写入方） | `D1-adj-gross-bank-current-unadj` | 自己 | ✅ |
 * | `useD1Disclosure`（披露①分类表） | `D1-adj-gross-bank-current-**audited**` / `D1-adj-**baddebt**-…` | **无** | ❌ 恒 0 |
 * | `useD1InventoryCount`（D1-10） | `D1-adj-**notes-receivable**-current-audited` | **无** | ❌ 恒 0 |
 * | `useD1RelatedPartyCheck`（D1-11） | 同上 | **无** | ❌ 恒 0 |
 *
 * 两类错因：① `-current-audited` 后缀**从不持久化**（审定数是 computed 列，
 * `serializeRows` 有意只存录入列）；② 前缀 `baddebt` / `notes-receivable` 与写入方的
 * `bd` / 分类 slug 不一致。三个消费方的单测都**镜像了同款错误锚点**播种 fixture，
 * 故测试恒绿而生产恒死 —— 只有把锚点构造收敛到本模块 + 源码守卫才能根治。
 *
 * ## 口径（源模板 `D1 应收票据.xlsx` 单元格公式为裁决者）
 *
 * - 审定数 `E8=B8+C8+D8` / `I8=F8+G8+H8` → `审定 = 未审 + 账项调整 + 重分类调整`
 * - 净值 `B16=B8-B12` / `F16=F8-F12` → `净值 = 原值 − 坏账准备`（逐列独立）
 * - D1-2 `H11=B11+F11-G11` → `期末未审 = 期初**未审** + 本期增加 − 本期减少`
 *   （🔴 注意是期初**未审**，不是期初审定）
 * - D1-1 原值行 ← D1-2（`B8='原值明细表（按类别）D1-2'!B14` 等）
 * - D1-1 坏账行 ← D1-4 **按票据种类小计**（`B12='坏账准备明细表D1-4'!B23`、`F12=!K23`）
 */

import {
  CELL_VALUE_TOLERANCE,
  deserializeRows,
  displayValueForCellState,
  readRaw,
  readRowFieldWithFallback,
  resolveCellState,
  rowsItemId,
  serializeRows,
  type DerivedCellState,
  type DynamicAdjRow,
  type DynamicRowsSpec,
} from './shared/dynamicAdjudicationRows'

/** `checklist_responses` 行的最小读取形状（与各 composable 的 ChecklistResponse 兼容）。 */
export interface D1AnchorResponse {
  item_id?: string
  conclusion?: string | null
  remark?: string | null
}

export type D1ResponseMap = ReadonlyMap<string, D1AnchorResponse>

// ─── 持久化键（明细底稿侧）───────────────────────────────────────────────────

/** D1-2 原值明细表（按类别）行集。 */
export const D1_CAT_ROWS_KEY = 'D1-cat-rows'
/** D1-4 坏账准备明细表 —— 按单项计提行集。 */
export const D1_BD_INDIVIDUAL_KEY = 'D1-bd-individual-rows'
/** D1-4 坏账准备明细表 —— 按组合计提行集。 */
export const D1_BD_PORTFOLIO_KEY = 'D1-bd-portfolio-rows'
/**
 * D1-4「按票据种类小计」行集（源模板 D1-4 R23/R24）。
 *
 * 源模板里这两行是**专门喂 D1-1 坏账区块**的额外小计块（`D1-1!B12=D1-4!B23`），
 * 与「按单项/按组合」是两个维度：D1-4 主体按**计提方法**拆，本块按**票据种类**拆。
 * 四表库 1231 只有总额、无票据种类拆分 → 本块只手工录入（宁缺勿造，不做比例分摊）。
 */
export const D1_BD_NOTETYPE_KEY = 'D1-bd-notetype-rows'

// ─── 锚点 ────────────────────────────────────────────────────────────────────

/** 审定表三区块。 */
export type D1AdjSection = 'gross' | 'bd' | 'net'

/** 审定表可持久化字段（**不含**审定数/变动额/变动率 —— 那些是派生列）。 */
export const D1_ADJ_FIELDS = [
  'prior-unadj',
  'prior-aje',
  'prior-rje',
  'current-unadj',
  'current-aje',
  'current-rje',
  'reason',
] as const
export type D1AdjField = (typeof D1_ADJ_FIELDS)[number]

/** 审定表锚点前缀。 */
export const D1_ADJ_PREFIX = 'D1-adj-'

/**
 * 唯一的审定表锚点构造器。
 *
 * 🔴 全平台禁止在本模块以外拼 `D1-adj-*` 字面量（守卫：`d1AnchorSingleSource.spec.ts`）。
 * 锚点形状必须与 `backend/data/d_cycle_extraction/d_cycle_anchor_registry.json` 的
 * D1 模式锚点一致，否则后端 `is_known_anchor` 会丢弃 seed。
 */
export function d1AdjAnchor(section: D1AdjSection, slug: string, field: D1AdjField): string {
  return `${D1_ADJ_PREFIX}${section}-${slug}-${field}`
}

/**
 * 按 `rowKey`（= `${section}-${slug}`，组件层的行标识）构造锚点。
 *
 * 供 `updateCell(rowKey, field, value)` 这类以行标识为入参的调用方使用，
 * 使它们也无需自己拼 `D1-adj-` 前缀（守卫要求）。
 */
export function d1AdjAnchorByRowKey(rowKey: string, field: D1AdjField | string): string {
  return `${D1_ADJ_PREFIX}${String(rowKey ?? '')}-${String(field ?? '')}`
}

/** 组合 rowKey。 */
export function d1AdjRowKey(section: D1AdjSection, slug: string): string {
  return `${section}-${slug}`
}

/** 审定表 TB↔审定净值核对行锚点（Tier A 公式 `TB('1121','期末余额')` 的落点）。 */
export const D1_ADJ_TB_AMOUNT_KEY = `${D1_ADJ_PREFIX}tb-amount`
/** 审定表审计说明 / 审计结论锚点。 */
export const D1_ADJ_NOTE_KEY = `${D1_ADJ_PREFIX}note`
export const D1_ADJ_CONCLUSION_KEY = `${D1_ADJ_PREFIX}conclusion`
/** 审定表锚点前缀判定（保存时按前缀批量收集 D1-adj-* 响应）。 */
export function isD1AdjAnchor(itemId: string): boolean {
  return String(itemId ?? '').startsWith(D1_ADJ_PREFIX)
}

/**
 * 审定表复核对话框 `section_id`（**与 checklist 锚点是不同命名空间**，但共用前缀，
 * 故一并在此收敛，防两处各写字面量后漂移）。
 *
 * 🔴 这两个值同时是后端 `_SECTION_PROMPTS` 的登记键，改字面量会让 AI 生成退回通用 prompt。
 */
export const D1_ADJ_REVIEW_SECTION = {
  auditNote: `${D1_ADJ_PREFIX}audit-note`,
  auditConclusion: `${D1_ADJ_PREFIX}audit-conclusion`,
} as const

/** 单元格级复核 `section_id`（形状与锚点一致，取同一构造器保证不漂移）。 */
export function d1AdjReviewSectionId(rowKey: string, field: string): string {
  return d1AdjAnchorByRowKey(rowKey, field)
}

// ─── 票据种类 ────────────────────────────────────────────────────────────────

export interface D1Category {
  /** 锚点 slug（ASCII、稳定）。固定行为 `bank` / `commercial`（与历史锚点兼容）。 */
  slug: string
  /** 展示名（源模板：银行承兑汇票 / 商业承兑汇票 / …）。 */
  label: string
  /** 是否源模板固定行（不可删除，恒排在前）。 */
  isFixed: boolean
  /** 对应 D1-2 行 id（动态行的 slug 由它派生）。 */
  rowId: string
}

/** 源模板 D1-1 固定的两个票据种类（与既有锚点 `gross-bank` / `gross-commercial` 兼容）。 */
export const D1_FIXED_CATEGORIES: readonly D1Category[] = [
  { slug: 'bank', label: '银行承兑汇票', isFixed: true, rowId: 'fixed-bank' },
  { slug: 'commercial', label: '商业承兑汇票', isFixed: true, rowId: 'fixed-commercial' },
] as const

/**
 * D1-2 行 → 锚点 slug。
 *
 * 用 **rowId** 而非票据种类名派生：rowId 是 ASCII 且稳定，改名不会让已录入的
 * AJE/RJE 变孤儿；票据种类名是中文且可编辑，用它做锚点必然产生孤儿数据。
 */
export function d1CategorySlug(rowId: string, category?: string): string {
  const id = String(rowId ?? '').trim()
  if (id === 'fixed-bank') return 'bank'
  if (id === 'fixed-commercial') return 'commercial'
  // 兜底：无 rowId 时按名称关键字归到固定行（历史数据兼容）
  if (!id) {
    const name = String(category ?? '')
    if (name.includes('银行')) return 'bank'
    if (name.includes('商业')) return 'commercial'
    return ''
  }
  const stripped = id.replace(/^dynamic-/, '').replace(/^fixed-/, '')
  const safe = stripped.replace(/[^A-Za-z0-9_-]/g, '')
  return safe ? `c-${safe}` : ''
}

// ─── 金额 ────────────────────────────────────────────────────────────────────

export interface D1PeriodAmounts {
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
}

export const D1_ZERO_AMOUNTS: D1PeriodAmounts = {
  priorUnadjusted: 0,
  priorAje: 0,
  priorRje: 0,
  priorAudited: 0,
  currentUnadjusted: 0,
  currentAje: 0,
  currentRje: 0,
  currentAudited: 0,
}

function n(v: unknown): number {
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const s = String(v ?? '').trim().replace(/,/g, '')
  if (!s) return 0
  const parsed = Number(s)
  return Number.isFinite(parsed) ? parsed : 0
}

/** 源模板 `E8=B8+C8+D8`：审定数 = 未审 + 账项调整 + 重分类调整。 */
export function d1Audited(unadj: number, aje: number, rje: number): number {
  return n(unadj) + n(aje) + n(rje)
}

/** 补齐派生列（审定数）。 */
export function d1WithAudited(a: Omit<D1PeriodAmounts, 'priorAudited' | 'currentAudited'>): D1PeriodAmounts {
  return {
    ...a,
    priorAudited: d1Audited(a.priorUnadjusted, a.priorAje, a.priorRje),
    currentAudited: d1Audited(a.currentUnadjusted, a.currentAje, a.currentRje),
  }
}

/** 逐列相加。 */
export function d1SumAmounts(list: readonly D1PeriodAmounts[]): D1PeriodAmounts {
  const s = (k: keyof D1PeriodAmounts) => list.reduce((acc, x) => acc + n(x[k]), 0)
  return {
    priorUnadjusted: s('priorUnadjusted'),
    priorAje: s('priorAje'),
    priorRje: s('priorRje'),
    priorAudited: s('priorAudited'),
    currentUnadjusted: s('currentUnadjusted'),
    currentAje: s('currentAje'),
    currentRje: s('currentRje'),
    currentAudited: s('currentAudited'),
  }
}

/** 源模板 `B16=B8-B12`：净值 = 原值 − 坏账准备（逐列独立）。 */
export function d1NetAmounts(gross: D1PeriodAmounts, provision: D1PeriodAmounts): D1PeriodAmounts {
  const d = (k: keyof D1PeriodAmounts) => n(gross[k]) - n(provision[k])
  return {
    priorUnadjusted: d('priorUnadjusted'),
    priorAje: d('priorAje'),
    priorRje: d('priorRje'),
    priorAudited: d('priorAudited'),
    currentUnadjusted: d('currentUnadjusted'),
    currentAje: d('currentAje'),
    currentRje: d('currentRje'),
    currentAudited: d('currentAudited'),
  }
}

// ─── 读取 ────────────────────────────────────────────────────────────────────

function readJsonArray(map: D1ResponseMap, key: string): any[] {
  const raw = map.get(key)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function readAnchor(map: D1ResponseMap, anchor: string): string {
  const resp = map.get(anchor)
  return resp?.remark ?? resp?.conclusion ?? ''
}

/** 读某区块某分类的手工录入金额（审定数现算）。 */
export function readD1AnchorAmounts(
  map: D1ResponseMap,
  section: D1AdjSection,
  slug: string,
): D1PeriodAmounts {
  return d1WithAudited({
    priorUnadjusted: n(readAnchor(map, d1AdjAnchor(section, slug, 'prior-unadj'))),
    priorAje: n(readAnchor(map, d1AdjAnchor(section, slug, 'prior-aje'))),
    priorRje: n(readAnchor(map, d1AdjAnchor(section, slug, 'prior-rje'))),
    currentUnadjusted: n(readAnchor(map, d1AdjAnchor(section, slug, 'current-unadj'))),
    currentAje: n(readAnchor(map, d1AdjAnchor(section, slug, 'current-aje'))),
    currentRje: n(readAnchor(map, d1AdjAnchor(section, slug, 'current-rje'))),
  })
}

/** 读某区块某分类的原因分析文本。 */
export function readD1AnchorReason(map: D1ResponseMap, section: D1AdjSection, slug: string): string {
  return String(readAnchor(map, d1AdjAnchor(section, slug, 'reason')) || '')
}

// ═══════════════════════════════════════════════════════════════════════════
// 行数组形态（Task 32：per-cell 锚点 → 行数组，**双读单写**）
//
// 🔴 关键实测（2026-09-28）：D1 现有 per-cell 键形态与共享模块
//    `shared/dynamicAdjudicationRows` 的 per-field 键形态**天然逐字一致** ——
//      `d1AdjAnchor(section, slug, field)`            → `D1-adj-{section}-{slug}-{field}`
//      `rowFieldItemId(SPEC, d1AdjRowKey(s, g), f)`   → `D1-adj-{section}-{slug}-{field}`
//    因为 `d1AdjRowKey(section, slug) === '{section}-{slug}'`、`prefix === 'D1-adj'`。
//    ⇒ 迁移是**接入共享模块**，不是另造一套键（需求 6.4 明令不得在 D1 侧另写一套）。
//    判据 `d1AdjRowsFallback.spec.ts` 把这条等价性钉死。
//
// 🔴 为什么必须双读（需求 6.1/6.2「迁移不归零」）：既有项目的金额只落在 per-cell item，
//    行对象里没有金额键。行对象值一旦存在即为权威（它也是 OO 回写的落点），
//    未补齐的行回落 per-cell；反过来 per-cell 优先会让 OO 改的值被旧值永久盖住。
//
// 🔴 `readRowFieldWithFallback` 要求**有带 rowId 的行对象**才会回落（`if (!rid) return 0`）
//    ⇒ 行数组为空时必须先按 `readD1Categories` 造占位行，否则回落路径走不到、金额归零。
//    这正是本模块 `d1AdjPlaceholderRow()` 的职责。
// ═══════════════════════════════════════════════════════════════════════════

/** 审定表金额字段（per-cell 键后缀 ↔ `D1PeriodAmounts` 的 camelCase 键）。 */
export const D1_ADJ_VALUE_FIELD_MAP = {
  'prior-unadj': 'priorUnadjusted',
  'prior-aje': 'priorAje',
  'prior-rje': 'priorRje',
  'current-unadj': 'currentUnadjusted',
  'current-aje': 'currentAje',
  'current-rje': 'currentRje',
} as const satisfies Record<string, keyof D1PeriodAmounts>

/** 迁移判定用的金额字段集（任一非零即认为该历史行「有数据」，必须保留）。 */
export const D1_ADJ_VALUE_FIELDS: readonly string[] = Object.keys(D1_ADJ_VALUE_FIELD_MAP)

/**
 * D1 审定表的动态行规格。
 *
 * `legacyRows: []` —— D1 的行不是写死的固定清单：分类由 `readD1Categories` 从 D1-2 动态推出
 * （银承/商承恒在前，其余按 D1-2 顺序追加）⇒ 迁移源是 categories 而不是静态 legacy 清单，
 * 故不走 `migrateLegacyFixedRows`，而由 `d1AdjPlaceholderRow` 逐分类造占位行驱动回落。
 */
export const D1_ADJ_ROWS_SPEC: DynamicRowsSpec = {
  prefix: 'D1-adj',
  legacyRows: [],
  valueFields: D1_ADJ_VALUE_FIELDS,
}

/** 行数组 store 键（`D1-adj-rows`，与 D4-1 的 `D4-1-rows` 同范式）。 */
export const D1_ADJ_ROWS_KEY: string = rowsItemId(D1_ADJ_ROWS_SPEC)

/** 读行数组（缺键/坏 JSON 均返回 `[]`，与共享模块口径一致）。 */
export function readD1AdjRows(map: D1ResponseMap): DynamicAdjRow[] {
  return deserializeRows(readRaw(map as Map<string, unknown>, D1_ADJ_ROWS_KEY))
}

/**
 * 某区块某分类的占位行 —— 只带 `rowId`/`label`，用于驱动 per-cell 回落。
 *
 * `source: 'legacy'` 如实反映「这行的值可能还只在旧 per-cell 键里」；
 * 一旦行对象补齐金额（写侧切换后），同一 rowId 的真实行会取代它。
 */
export function d1AdjPlaceholderRow(
  section: D1AdjSection,
  slug: string,
  label = '',
): DynamicAdjRow {
  return { rowId: d1AdjRowKey(section, slug), label, source: 'legacy' }
}

/**
 * 双读某区块某分类的金额：**行对象优先、缺则回落 per-cell 锚点**（Task 32）。
 *
 * 与 :func:`readD1AnchorAmounts` 的关系：后者是纯 per-cell 读取（迁移前的唯一路径），
 * 本函数在行数组不存在/该行无金额键时**逐字退化为它的结果**（判据钉住这条等价性）
 * ⇒ 接入本函数是零行为变化的升级，不是新语义。
 */
export function readD1AdjRowAmounts(
  map: D1ResponseMap,
  section: D1AdjSection,
  slug: string,
  rows?: readonly DynamicAdjRow[],
): D1PeriodAmounts {
  const rowId = d1AdjRowKey(section, slug)
  const list = rows ?? readD1AdjRows(map)
  const row = list.find((r) => r.rowId === rowId) ?? d1AdjPlaceholderRow(section, slug)
  const responses = map as Map<string, unknown>
  const read = (field: string): number =>
    readRowFieldWithFallback(row, responses, D1_ADJ_ROWS_SPEC, field)
  return d1WithAudited({
    priorUnadjusted: read('prior-unadj'),
    priorAje: read('prior-aje'),
    priorRje: read('prior-rje'),
    currentUnadjusted: read('current-unadj'),
    currentAje: read('current-aje'),
    currentRje: read('current-rje'),
  })
}

/** 可手工编辑的两个区块（净值恒为公式，不落库）。 */
export const D1_ADJ_EDITABLE_SECTIONS: readonly D1AdjSection[] = ['gross', 'bd']

// ═══════════════════════════════════════════════════════════════════════════
// 逐格四态覆盖状态机（Task 33）—— 修 cross-sheet 无条件盖掉手工值的静默丢数据
//
// 🔴 修前的行为：`const g = fromCat ?? 手工值` —— D1-2 一有行，手工录入的值就**既不显示
//    也改不了**（配合 `buildRow` 的 `isEditable = … && !isFromCrossSheet`）。审计师录进去的
//    数字凭空消失且无任何提示。与 D4-1 修前同型。
//
// 🔴 四态复用 `shared/dynamicAdjudicationRows` 的 `resolveCellState` /
//    `displayValueForCellState`（需求 6.4 明令不得在 D1 侧另写一套）。三个量：
//      stored  = 行对象/per-cell 里该格当前值（双读）
//      snap    = 行对象 derivedSnapshot[field]（最近一次由派生写入 store 的值）
//      derived = 当前现算 cross-sheet 值（D1-2 原值 / D1-4 按票据种类小计）
//    覆盖判定是 `stored ≠ snap`（**不是** `stored ≠ derived`）—— 后者会在上游一变时把所有
//    纯派生格误判成人工覆盖。
//
// 🔴 snap 只能挂在**行对象**上（per-cell 是纯文本 remark，装不下）⇒ 本节依赖 Task 32 的
//    写侧已切到行数组。这也是 tasks 依赖图「33 依赖 32」的确切理由。
// ═══════════════════════════════════════════════════════════════════════════

/** 某行某格的四态解析结果。 */
export interface D1AdjCellResolution {
  state: DerivedCellState
  /** 应当显示的值（S1/S3 跟随 derived；S2/S4 用 stored 覆盖值）。 */
  display: number
  stored: number
  snap: number | null
  derived: number
}

/** snap 读取：行对象 `derivedSnapshot[field]`（无则 `null` = 从未由派生写入过）。 */
export function readD1AdjSnap(
  map: D1ResponseMap,
  rowId: string,
  field: string,
  rows?: readonly DynamicAdjRow[],
): number | null {
  const list = rows ?? readD1AdjRows(map)
  const raw = list.find((r) => r.rowId === rowId)?.derivedSnapshot?.[field]
  if (raw == null) return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

/** 逐格解析四态（单格）。 */
export function resolveD1AdjCell(
  map: D1ResponseMap,
  rowId: string,
  field: string,
  derived: number,
  rows?: readonly DynamicAdjRow[],
): D1AdjCellResolution {
  const list = rows ?? readD1AdjRows(map)
  const row =
    list.find((r) => r.rowId === rowId)
    ?? ({ rowId, label: '', source: 'legacy' } as DynamicAdjRow)
  const stored = readRowFieldWithFallback(
    row,
    map as Map<string, unknown>,
    D1_ADJ_ROWS_SPEC,
    field,
  )
  const snap = readD1AdjSnap(map, rowId, field, list)

  // 🔴🔴 `snap === null`（从未由派生写入过 —— 迁移前的行，或同步器还没跑过一轮）必须**先降级**，
  //    不能直接丢给 `resolveCellState`：
  //      `resolveCellState(0, null, 100)` 会算出 `overridden = (0 ≠ null) = true` ⇒ S4
  //      ⇒ `displayValueForCellState('S4', 0, 100)` 取 stored ⇒ **上游值 100 被显示成 0**。
  //    这是实测踩到的回归（`useD1DisclosureDerived.spec.ts` 的 `endBalance` 期望 140 实得 0）。
  //
  //    降级依据：per-cell 形态下 `readNum` 对缺键返回 0 ⇒ **「没录入」与「录入了 0」不可区分**
  //    （形态的固有信息损失，不是判定逻辑的缺陷）。故按 stored 是否非零二分：
  //      * stored 非零 ⇒ 迁移前就存在手工值 ⇒ 判 **S2**（已覆盖、上游未变），显示 stored
  //        —— 这正是「cross-sheet 不再无条件盖掉手工值」要修的那一半；
  //      * stored 为零 ⇒ 无手工录入 ⇒ 判 **S1**（纯派生），显示 derived，与修前行为一致。
  //    同步器跑过一轮后 snap 不再为 null，四态即完整（含 S3/S4 的「上游已变」维度）。
  if (snap === null) {
    const overridden = Math.abs(stored) > CELL_VALUE_TOLERANCE
    return {
      state: overridden ? 'S2' : 'S1',
      display: overridden ? stored : derived,
      stored,
      snap,
      derived,
    }
  }

  const state = resolveCellState(stored, snap, derived)
  return {
    state,
    display: n(displayValueForCellState(state, stored, derived)),
    stored,
    snap,
    derived,
  }
}

/** 一行 6 个金额格的四态（field → 态）。 */
export type D1AdjRowCellStates = Partial<Record<string, DerivedCellState>>

/**
 * 把 cross-sheet 派生值与手工值按**逐格四态**合成该行应显示的金额。
 *
 * 🔴 这取代了修前的整行 `fromCat ?? 手工值`：覆盖是**逐格**的 —— 审计师可能只改了「账项调整」
 *    一列而其余列跟随上游，整行二选一必然丢掉其中一侧。
 */
export function mergeD1AdjRowByCellState(
  map: D1ResponseMap,
  section: D1AdjSection,
  slug: string,
  derived: D1PeriodAmounts,
  rows?: readonly DynamicAdjRow[],
): { amounts: D1PeriodAmounts; states: D1AdjRowCellStates } {
  const rowId = d1AdjRowKey(section, slug)
  const list = rows ?? readD1AdjRows(map)
  const states: D1AdjRowCellStates = {}
  const picked: Record<string, number> = {}
  for (const [field, camel] of Object.entries(D1_ADJ_VALUE_FIELD_MAP)) {
    const r = resolveD1AdjCell(map, rowId, field, n(derived[camel]), list)
    states[field] = r.state
    picked[camel] = r.display
  }
  return {
    amounts: d1WithAudited({
      priorUnadjusted: picked.priorUnadjusted,
      priorAje: picked.priorAje,
      priorRje: picked.priorRje,
      currentUnadjusted: picked.currentUnadjusted,
      currentAje: picked.currentAje,
      currentRje: picked.currentRje,
    }),
    states,
  }
}

/**
 * 同步器：把 cross-sheet 派生值物化进行对象（`stored` + `derivedSnapshot`）。
 *
 * 返回新的行数组序列化串；**无任何变化时返回 `null`**（幂等，调用方据此跳过写库）。
 *
 * 🔴 **只写未被覆盖的格**（`state === 'S1' || state === 'S3'`）—— 已被人工覆盖的格
 * （S2/S4）保持 stored 不动，只把 snap 推到当前 derived，这样「上游已变」这一维度能
 * 继续被认出来。若无条件写 stored，就等于用派生值冲掉审计师的覆盖值（即修前的缺陷）。
 *
 * 🔴🔴 **本函数写进 snap 的必须是 `derived`，绝不能是「显示值」**。tasks.md 明文记着
 * D4 的事故：同步器把显示值当派生值写回 snap ⇒ S2 下显示值就是 stored ⇒ 写完 snap==stored
 * ⇒ 下一次 `resolveCellState` 判成未覆盖 ⇒ **覆盖标记自我擦除**，而 13 条纯函数判据全绿。
 * 判据 `d1AdjCellStateMachine.spec.ts` 里有一条**真跑本函数**的断言钉住它。
 */
export function syncD1DerivedIntoRows(
  map: D1ResponseMap,
  categories: readonly D1Category[],
  derivedBySection: Partial<Record<D1AdjSection, Record<string, D1PeriodAmounts>>>,
): string | null {
  const existing = readD1AdjRows(map)
  const byId = new Map(existing.map((r) => [r.rowId, { ...r }]))
  let dirty = false

  for (const section of D1_ADJ_EDITABLE_SECTIONS) {
    const bySlug = derivedBySection[section]
    if (!bySlug) continue
    for (const c of categories) {
      const derived = bySlug[c.slug]
      if (!derived) continue
      const rowId = d1AdjRowKey(section, c.slug)
      const row =
        byId.get(rowId)
        ?? ({ rowId, label: c.label || c.slug, source: 'tb' } as DynamicAdjRow)
      const snapshot: Record<string, number | null> = { ...(row.derivedSnapshot ?? {}) }
      for (const [field, camel] of Object.entries(D1_ADJ_VALUE_FIELD_MAP)) {
        const d = n(derived[camel])
        const r = resolveD1AdjCell(map, rowId, field, d, existing)
        // snap 恒推到当前 derived（S2/S4 也推 —— 这才能让"上游已变"被认出来）。
        // 🔴 写的是 derived，不是 r.display。
        if (snapshot[field] !== d) {
          snapshot[field] = d
          dirty = true
        }
        // stored 只在未被覆盖时跟随（S1/S3）。
        if (r.state === 'S1' || r.state === 'S3') {
          if ((row as Record<string, unknown>)[field] !== d) {
            ;(row as Record<string, unknown>)[field] = d
            dirty = true
          }
        }
      }
      row.derivedSnapshot = snapshot
      if (!row.source) row.source = 'tb'
      byId.set(rowId, row)
    }
  }

  if (!dirty) return null
  const rows = [...byId.values()]
  return serializeRows(rows, {
    spec: D1_ADJ_ROWS_SPEC,
    reader: {
      readField: (rowId, field) => {
        const r = byId.get(rowId)
        const direct = r ? (r as Record<string, unknown>)[field] : undefined
        if (direct != null && Number.isFinite(Number(direct))) return Number(direct)
        return readRowFieldWithFallback(
          r ?? { rowId, label: '', source: 'legacy' },
          map as Map<string, unknown>,
          D1_ADJ_ROWS_SPEC,
          field,
        )
      },
      readDerivedSnapshot: (rowId) => byId.get(rowId)?.derivedSnapshot ?? null,
    },
  })
}

/**
 * 恢复取数（把某格从覆盖态退回 S1 纯派生）：`stored ← derived`、`snap ← derived`。
 *
 * 返回新的行数组序列化串。🔴 **当场写对**，不靠下一次同步自愈 —— 否则此刻若发生
 * flushSave / 切 OO，库里留的还是覆盖值（D4 判据 P15 的原文要求）。
 */
export function restoreD1AdjDerivedValue(
  map: D1ResponseMap,
  categories: readonly D1Category[],
  rowId: string,
  field: string,
  derived: number,
): string {
  const existing = readD1AdjRows(map)
  const byId = new Map(existing.map((r) => [r.rowId, { ...r }]))
  const row =
    byId.get(rowId) ?? ({ rowId, label: '', source: 'tb' } as DynamicAdjRow)
  ;(row as Record<string, unknown>)[field] = derived
  row.derivedSnapshot = { ...(row.derivedSnapshot ?? {}), [field]: derived }
  byId.set(rowId, row)
  const merged = new Map(byId)
  // 复用写侧的整清单口径（categories ∪ 已有行），避免两处行清单规则漂移。
  const base = serializeD1AdjRows(map, categories)
  for (const r of deserializeRows(base)) {
    if (!merged.has(r.rowId)) merged.set(r.rowId, r)
  }
  return serializeRows([...merged.values()], {
    spec: D1_ADJ_ROWS_SPEC,
    reader: {
      readField: (rid, f) => {
        const r = merged.get(rid)
        const direct = r ? (r as Record<string, unknown>)[f] : undefined
        if (direct != null && Number.isFinite(Number(direct))) return Number(direct)
        return readRowFieldWithFallback(
          r ?? { rowId: rid, label: '', source: 'legacy' },
          map as Map<string, unknown>,
          D1_ADJ_ROWS_SPEC,
          f,
        )
      },
      readDerivedSnapshot: (rid) => merged.get(rid)?.derivedSnapshot ?? null,
    },
  })
}

/**
 * 双读单格当前值（行对象优先、缺则回落 per-cell）。
 *
 * 给调用方（如「应用调整分录」的累加基数）用，使它们**无需直连**
 * `shared/dynamicAdjudicationRows` —— 键与回落规则一律收敛在本模块
 * （与 `d1AdjAnchor` 的单源纪律同理，守卫 `d1AnchorSingleSource.spec.ts`）。
 */
export function readD1AdjCellValue(
  map: D1ResponseMap,
  rowId: string,
  field: string,
): number {
  const row =
    readD1AdjRows(map).find((r) => r.rowId === rowId)
    ?? ({ rowId, label: '', source: 'legacy' } as DynamicAdjRow)
  return readRowFieldWithFallback(row, map as Map<string, unknown>, D1_ADJ_ROWS_SPEC, field)
}

/**
 * 写侧单写（Task 32）：把某格改动落成**行数组**的序列化串。
 *
 * 返回值直接写进 `D1-adj-rows` 这一个 item ⇒ 写侧只写新形态；旧 per-cell 键**只读不写**、
 * 原样留在库里（物理删除归后续 spec，回滚只需把读侧优先级调回 per-cell）。
 *
 * 🔴 **一次写入包含全部可编辑行，不是只写被改的那一行**：`serializeRows` 产出的是整个
 * 行数组，只塞一行会让其余行从行数组里消失、退回 per-cell 回落 ⇒ 每次编辑都在两种形态
 * 之间抖动。整清单幂等写入是唯一稳定形态（也与 D4-1 的写法一致）。
 *
 * 🔴 **未被改动的格用双读取当前值** ⇒ 第一次编辑该行时，它原本只在 per-cell 里的旧值会
 * 被一并固化进行对象（迁移在编辑时自然完成，不需要一次性批量迁移脚本，也不会归零）。
 *
 * 🔴 **`reason`（原因分析，文本）不随行落库**：共享模块 `serializeRows` 只序列化
 * `spec.valueFields`（数字）与结构键（`rowId`/`label`/`source`/`derivedSnapshot`），
 * 文本字段会被丢弃 ⇒ reason 仍走 per-cell 锚点。这是共享模块的形态边界，
 * 不是本次迁移的遗漏；把它塞进行对象需要先扩共享模块（归后续 spec）。
 */
export function serializeD1AdjRows(
  map: D1ResponseMap,
  categories: readonly D1Category[],
  edit?: { rowId: string; field: string; value: number },
): string {
  const existing = readD1AdjRows(map)
  const byId = new Map(existing.map((r) => [r.rowId, r]))
  const responses = map as Map<string, unknown>

  const rows: DynamicAdjRow[] = []
  const emitted = new Set<string>()
  for (const section of D1_ADJ_EDITABLE_SECTIONS) {
    for (const c of categories) {
      const rowId = d1AdjRowKey(section, c.slug)
      if (emitted.has(rowId)) continue
      emitted.add(rowId)
      const prev = byId.get(rowId)
      rows.push({
        rowId,
        label: prev?.label || c.label || c.slug,
        source: prev?.source ?? 'legacy',
        ...(prev?.derivedSnapshot ? { derivedSnapshot: prev.derivedSnapshot } : {}),
      })
    }
  }

  // 🔴 被编辑的行若不在 categories 派生出的清单里（分类刚被从 D1-2 删掉、或 rowKey 来自
  //    `resolveRowKeyFromAccount` 这类按科目映射的入口），**必须补进来**——否则 rows 里没有
  //    它，本次编辑连同该行既有金额会被静默丢弃。已有行（byId）同理：不能因为 categories
  //    暂时读不到就把库里的行抹掉。
  for (const rowId of [
    ...(edit && !emitted.has(edit.rowId) ? [edit.rowId] : []),
    ...[...byId.keys()].filter((id) => !emitted.has(id)),
  ]) {
    if (emitted.has(rowId)) continue
    emitted.add(rowId)
    const prev = byId.get(rowId)
    rows.push({
      rowId,
      label: prev?.label ?? '',
      source: prev?.source ?? 'legacy',
      ...(prev?.derivedSnapshot ? { derivedSnapshot: prev.derivedSnapshot } : {}),
    })
  }

  return serializeRows(rows, {
    spec: D1_ADJ_ROWS_SPEC,
    reader: {
      readField: (rowId, field) => {
        if (edit && rowId === edit.rowId && field === edit.field) return edit.value
        const row = byId.get(rowId) ?? { rowId, label: '', source: 'legacy' as const }
        return readRowFieldWithFallback(row, responses, D1_ADJ_ROWS_SPEC, field)
      },
      readDerivedSnapshot: (rowId) => byId.get(rowId)?.derivedSnapshot ?? null,
    },
  })
}

/**
 * 从 D1-2 读实际票据种类（固定的银承/商承恒排在前，其余按 D1-2 顺序追加）。
 *
 * 🔴 必须支持动态种类：源模板 D1-2 固定行就有三个（银行承兑汇票 / **财务公司承兑汇票** /
 * 商业承兑汇票），四表库 seed 还会按客户科目表产出「信用证」等动态行（实测项目
 * 0ec33ac9 的 1121.03 信用证 期初 55,021,577.23）。改造前审定表只匹配「银行」/「商业」
 * → 这些金额在审定表**无落点**，净值与 TB 必然出现假差异。
 */
export function readD1Categories(map: D1ResponseMap): D1Category[] {
  const out: D1Category[] = D1_FIXED_CATEGORIES.map((c) => ({ ...c }))
  for (const raw of readJsonArray(map, D1_CAT_ROWS_KEY)) {
    const rowId = String(raw?.rowId ?? '').trim()
    const label = String(raw?.category ?? '').trim()
    const slug = d1CategorySlug(rowId, label)
    if (!slug) continue
    const existing = out.find((c) => c.slug === slug)
    if (existing) {
      // 固定行沿用源模板行名（用户改名也不覆盖固定语义）；非固定行同步最新名
      if (!existing.isFixed && label) existing.label = label
      continue
    }
    out.push({ slug, label: label || rowId, isFixed: false, rowId })
  }
  return out
}

/**
 * 从 D1-2 行集算各票据种类金额（供 D1-1 原值区块 cross-sheet 取数）。
 *
 * 🔴 `currentUnadjusted` 必须在此**现算**：`useD1DetailCategory.serializeRows()` 有意
 * 只持久化录入列（`priorUnadjusted`/`currentIncrease`/`currentDecrease`/aje/rje），
 * 派生列不落库。改造前审定表直接读 `catRow.currentUnadjusted` → 恒 `undefined` → 0，
 * 即「D1-2 填了数、审定表期末仍是 0」。
 *
 * 口径取源模板 D1-2 `H11=B11+F11-G11`：期末未审 = 期初**未审** + 本期增加 − 本期减少。
 */
export function readD1CategoryAmounts(map: D1ResponseMap): Record<string, D1PeriodAmounts> {
  const out: Record<string, D1PeriodAmounts> = {}
  for (const raw of readJsonArray(map, D1_CAT_ROWS_KEY)) {
    const slug = d1CategorySlug(String(raw?.rowId ?? ''), String(raw?.category ?? ''))
    if (!slug) continue
    const priorUnadjusted = n(raw?.priorUnadjusted)
    const increase = n(raw?.currentIncrease)
    const decrease = n(raw?.currentDecrease)
    const amounts = d1WithAudited({
      priorUnadjusted,
      priorAje: n(raw?.priorAje),
      priorRje: n(raw?.priorRje),
      currentUnadjusted: priorUnadjusted + increase - decrease,
      currentAje: n(raw?.currentAje),
      currentRje: n(raw?.currentRje),
    })
    out[slug] = out[slug] ? d1SumAmounts([out[slug], amounts]) : amounts
  }
  return out
}

/**
 * 从 D1-4「按票据种类小计」块读坏账准备（供 D1-1 坏账区块 cross-sheet 取数）。
 *
 * 源模板 `D1-1!B12='坏账准备明细表D1-4'!B23`（银行承兑汇票小计）/ `!B24`（商业承兑汇票小计），
 * 期末列 `F12=!K23`。D1-4 的「按单项/按组合」是**另一个维度**（计提方法），不能直接喂
 * 审定表的票据种类行，故源模板专门留了这两行小计。
 */
export function readD1BadDebtByNoteType(map: D1ResponseMap): Record<string, D1PeriodAmounts> {
  const out: Record<string, D1PeriodAmounts> = {}
  for (const raw of readJsonArray(map, D1_BD_NOTETYPE_KEY)) {
    const slug = d1CategorySlug(String(raw?.rowId ?? ''), String(raw?.noteType ?? raw?.category ?? ''))
    if (!slug) continue
    const priorUnadjusted = n(raw?.priorUnadjusted)
    const amounts = d1WithAudited({
      priorUnadjusted,
      priorAje: n(raw?.priorAje),
      priorRje: n(raw?.priorRje),
      currentUnadjusted: n(raw?.currentUnadjusted),
      currentAje: n(raw?.currentAje),
      currentRje: n(raw?.currentRje),
    })
    out[slug] = out[slug] ? d1SumAmounts([out[slug], amounts]) : amounts
  }
  return out
}

/**
 * D1-4 坏账准备**合计**（按单项 + 按组合），派生列现算。
 *
 * 🔴 不能直接读行里的 `currentAudited` / `priorAudited`：`useD1BadDebt.serializeRows()`
 * 与 `useD1DetailCategory.serializeRows()` 一样**有意只持久化录入列**，派生列不落库。
 * 改造前 `useD1CrossSheet.badDebtTotalAudited` 直接读 `currentAudited` → 恒 0 →
 * `eclVsBadDebtDiff` 把整个 ECL 应计提额当成差异常亮。
 *
 * 口径与 `useD1FormulaEngine.calcBadDebtEndBalance` 逐字一致
 * （期初审定 + 计提 − 收回 − 转回 − 核销 + 其他）。
 */
export function readD1BadDebtTotal(map: D1ResponseMap): D1PeriodAmounts {
  const rows: D1PeriodAmounts[] = []
  for (const key of [D1_BD_INDIVIDUAL_KEY, D1_BD_PORTFOLIO_KEY]) {
    for (const raw of readJsonArray(map, key)) {
      const priorUnadjusted = n(raw?.priorUnadjusted)
      const priorAje = n(raw?.priorAje)
      const priorRje = n(raw?.priorRje)
      const currentUnadjusted =
        d1Audited(priorUnadjusted, priorAje, priorRje) +
        n(raw?.currentProvision) -
        n(raw?.currentRecovery) -
        n(raw?.currentReversal) -
        n(raw?.currentWriteOff) +
        n(raw?.currentOther)
      rows.push(
        d1WithAudited({
          priorUnadjusted,
          priorAje,
          priorRje,
          currentUnadjusted,
          currentAje: n(raw?.currentAje),
          currentRje: n(raw?.currentRje),
        }),
      )
    }
  }
  return d1SumAmounts(rows)
}

/** D1-2 原值**合计**（派生列现算，理由同 `readD1BadDebtTotal`）。 */
export function readD1CategoryTotal(map: D1ResponseMap): D1PeriodAmounts {
  return d1SumAmounts(Object.values(readD1CategoryAmounts(map)))
}

/**
 * D1-4 坏账准备**变动列**合计（转回 / 核销），供 D1-16 转回核销检查表做跨表核对。
 *
 * 🔴 改造前 `useD1WriteoffCheck` 把「D1-4 转回变动合计」读成
 * `D1-adj-bad-debt-reversal` —— 而那个键**正是它自己**「同步到 D1-4」时写的，
 * D1-4（`useD1BadDebt`）从不读也从不写它 → 变成**自比自**（点过同步后差异恒 0），
 * 且「同步到 D1-4」按钮对 D1-4 毫无影响。现改为直接读 D1-4 真实行数据。
 */
export function readD1BadDebtChangeTotals(map: D1ResponseMap): {
  reversal: number
  writeOff: number
  /** D1-4 是否已有行数据（否则返回 null 语义由调用方决定） */
  present: boolean
} {
  let reversal = 0
  let writeOff = 0
  let present = false
  for (const key of [D1_BD_INDIVIDUAL_KEY, D1_BD_PORTFOLIO_KEY]) {
    const rows = readJsonArray(map, key)
    if (rows.length) present = true
    for (const raw of rows) {
      // 「转回」口径含「收回」（源模板 D1-4 H 列「转回」；前端另有 currentRecovery 列）
      reversal += n(raw?.currentReversal) + n(raw?.currentRecovery)
      writeOff += n(raw?.currentWriteOff)
    }
  }
  return { reversal, writeOff, present }
}

/**
 * 把转回 / 核销金额回写进 D1-4「按组合计提」父行（纯函数，返回新的 JSON 串）。
 *
 * 供 D1-16 的「同步到 D1-4」按钮真正生效：改造前它写的是 D1-4 从不读的
 * `D1-adj-bad-debt-*` 键。落点选「按组合计提」父行 —— D1-16 的合计不区分
 * 单项/组合，而组合是缺省归属；审计师可在 D1-4 内再拆到「其中：」明细行。
 *
 * 只覆盖传入的列，其余字段与其它行原样保留（缺行时补出固定父行）。
 */
export function patchD1PortfolioChangeColumns(
  map: D1ResponseMap,
  patch: { currentReversal?: number; currentWriteOff?: number },
): string {
  const rows = readJsonArray(map, D1_BD_PORTFOLIO_KEY)
  const list = rows.length
    ? rows.map((r) => ({ ...r }))
    : [
        {
          rowId: 'fixed-portfolio',
          category: 'portfolio',
          label: '按组合计提',
          isSubRow: false,
          priorUnadjusted: 0,
          priorAje: 0,
          priorRje: 0,
          currentProvision: 0,
          currentRecovery: 0,
          currentReversal: 0,
          currentWriteOff: 0,
          currentOther: 0,
          currentAje: 0,
          currentRje: 0,
        } as Record<string, unknown>,
      ]
  const target =
    list.find((r) => String(r?.rowId ?? '') === 'fixed-portfolio') ?? list[0]
  if (patch.currentReversal !== undefined) target.currentReversal = patch.currentReversal
  if (patch.currentWriteOff !== undefined) target.currentWriteOff = patch.currentWriteOff
  return JSON.stringify(list)
}

export interface D1AdjudicationTotals {
  categories: D1Category[]
  gross: Record<string, D1PeriodAmounts>
  provision: Record<string, D1PeriodAmounts>
  net: Record<string, D1PeriodAmounts>
  grossTotal: D1PeriodAmounts
  provisionTotal: D1PeriodAmounts
  netTotal: D1PeriodAmounts
  /** 原值行是否来自 D1-2 cross-sheet（逐 slug）。 */
  grossFromCrossSheet: Record<string, boolean>
  /** 坏账行是否来自 D1-4 按票据种类小计（逐 slug）。 */
  provisionFromCrossSheet: Record<string, boolean>
  /**
   * 逐格四态（Task 33）：`{slug: {field: 'S1'|'S2'|'S3'|'S4'}}`，只对有 cross-sheet 派生值的
   * 行有条目（无上游 ⇒ 纯手工、无"覆盖"概念）。UI 据此显示「已人工覆盖」标记与「恢复取数」。
   */
  grossCellStates: Record<string, D1AdjRowCellStates>
  provisionCellStates: Record<string, D1AdjRowCellStates>
  /** 是否存在任何非零金额（披露表据此决定主表是否只读）。 */
  hasData: boolean
}

/**
 * 审定表三区块的**唯一**取数入口：D1-1 自身渲染、披露①分类表、D1-10 监盘、
 * D1-11 关联方全部消费本函数，保证「界面上看到的」== 「推给附注的」== 「跨表用的」。
 *
 * 取数优先级（逐分类逐列）：
 *   原值：D1-2 明细（cross-sheet）> 审定表手工值
 *   坏账：D1-4 按票据种类小计（cross-sheet）> 审定表手工值
 *   净值：恒 = 原值 − 坏账（不可手工）
 *
 * 🔴 「审定表手工值」自 Task 32 起走 :func:`readD1AdjRowAmounts`（**行对象优先、缺则回落
 *    per-cell 锚点**），取代原来的纯 per-cell `readD1AnchorAmounts`。行数组不存在时两者
 *    逐字等价 ⇒ 这是零行为变化的升级（判据 `d1AdjRowsFallback.spec.ts` 钉住等价性）。
 *
 * 🔴 **cross-sheet 仍在无条件覆盖手工值**（`fromCat ?? 手工`）—— 这是已登记的静默丢数据
 *    缺陷，修它需要逐格四态状态机（Task 33），而四态的第三个量 `snap`
 *    （`derivedSnapshot`）**只能由行对象承载**，per-cell 纯文本 remark 装不下 ⇒
 *    必须等写侧切换到行数组之后。本函数此处不擅自改覆盖语义（改一半会让两种口径并存）。
 */
export function readD1AdjudicationTotals(map: D1ResponseMap): D1AdjudicationTotals {
  const categories = readD1Categories(map)
  const catAmounts = readD1CategoryAmounts(map)
  const bdAmounts = readD1BadDebtByNoteType(map)
  // 行数组只读一次，逐分类复用（避免 N 次 JSON.parse）。
  const adjRows = readD1AdjRows(map)

  const gross: Record<string, D1PeriodAmounts> = {}
  const provision: Record<string, D1PeriodAmounts> = {}
  const net: Record<string, D1PeriodAmounts> = {}
  const grossFromCrossSheet: Record<string, boolean> = {}
  const provisionFromCrossSheet: Record<string, boolean> = {}
  const grossCellStates: Record<string, D1AdjRowCellStates> = {}
  const provisionCellStates: Record<string, D1AdjRowCellStates> = {}

  for (const c of categories) {
    // 🔴 Task 33：有上游派生值时走**逐格四态**（不再整行 `fromCat ?? 手工`）——
    //    覆盖是逐格的，审计师可能只改了「账项调整」一列而其余列跟随上游，
    //    整行二选一必然丢掉其中一侧。无上游时是纯手工，无"覆盖"概念。
    const fromCat = catAmounts[c.slug]
    let g: D1PeriodAmounts
    if (fromCat) {
      const merged = mergeD1AdjRowByCellState(map, 'gross', c.slug, fromCat, adjRows)
      g = merged.amounts
      grossCellStates[c.slug] = merged.states
    } else {
      g = readD1AdjRowAmounts(map, 'gross', c.slug, adjRows)
    }
    grossFromCrossSheet[c.slug] = Boolean(fromCat)

    const fromBd = bdAmounts[c.slug]
    let p: D1PeriodAmounts
    if (fromBd) {
      const merged = mergeD1AdjRowByCellState(map, 'bd', c.slug, fromBd, adjRows)
      p = merged.amounts
      provisionCellStates[c.slug] = merged.states
    } else {
      p = readD1AdjRowAmounts(map, 'bd', c.slug, adjRows)
    }
    provisionFromCrossSheet[c.slug] = Boolean(fromBd)

    gross[c.slug] = g
    provision[c.slug] = p
    net[c.slug] = d1NetAmounts(g, p)
  }

  const grossTotal = d1SumAmounts(categories.map((c) => gross[c.slug]))
  const provisionTotal = d1SumAmounts(categories.map((c) => provision[c.slug]))
  const netTotal = d1NetAmounts(grossTotal, provisionTotal)
  const hasData =
    Math.abs(grossTotal.priorUnadjusted) > 0.005 ||
    Math.abs(grossTotal.currentUnadjusted) > 0.005 ||
    Math.abs(provisionTotal.priorUnadjusted) > 0.005 ||
    Math.abs(provisionTotal.currentUnadjusted) > 0.005 ||
    Math.abs(grossTotal.priorAudited) > 0.005 ||
    Math.abs(grossTotal.currentAudited) > 0.005

  return {
    categories,
    gross,
    provision,
    net,
    grossTotal,
    provisionTotal,
    netTotal,
    grossFromCrossSheet,
    provisionFromCrossSheet,
    grossCellStates,
    provisionCellStates,
    hasData,
  }
}
