/**
 * D4 营业收入/营业成本披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、62「营业收入和营业成本」/
 *          note_template_soe.json 八、64「营业收入、营业成本」
 *
 * 表名逐字取自附注模板（Task 3.2 已修正为源模板对齐版）：
 *  - （4）listed: "营业收入、营业成本按分解信息"（非旧名"…按商品转让时间划分"）
 *  - （4）soe:    "营业收入分解信息"（非旧名"…按商品转让时间划分"）
 *  - （6）both:   "与剩余履约义务有关的信息"（非旧段落文本泄漏名）
 *  - （8）listed: "试运行销售收入"（国企无此表）
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data
 *  - sub_table_data._note_texts → 附注 text_content（文本框内容与披露表保持一致）
 *  - sub_table_data._removed_table_keys → 后端删旧键（求差集防误删）
 *  - columns → _sub_table_columns（投影器据此产出表头）
 *
 * 🔴 覆盖必须完整：note_sub_table_projector 对 `_source=workpaper` 只渲染推送过的子表。
 * 🔴 sub_table_data 各子表键 ↔ columns 键必须相同（后端投影器按名匹配）。
 * 🔴 列声明 group（两级表头）或 flat（单级），禁止不表态（Property 13）。
 * 🔴 `_removed_table_keys` 与本次推送键无交集（Property 20）。
 *
 * spec: d4-four-table-extraction-and-disclosure-alignment (Task 5.5)
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
 */
import type { ColumnDef } from './disclosureColumnDefs'
import {
  buildD4TwoPeriodColumns,
  buildD4TransposeColumns,
  buildD4ObligationColumns,
  deriveObligationTotal,
  type D4TwoPeriodRow,
  type D4TransposeRow,
  type D4ObligationRow,
  type D4TransposeCategory,
  D4_DEFAULT_CATEGORIES,
} from './d4DisclosureModel'

export type D4DisclosureVariant = 'listed' | 'soe'

export const D4_NOTE_SECTION = {
  listed: '五、62',
  soe: '八、64',
} as const satisfies Record<D4DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（🔴 D4 为全角括号，见 workpaper_sheet_classification wp_code=D4-*；
// 与 D7 半角括号不同，错一字符 GtWpRenderer ?sheet= 精确匹配失败会回退底稿目录）。
export const D4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<D4DisclosureVariant, string>

export function resolveD4CurrentStandard(
  variant: D4DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

// ─── 表名（逐字取自附注模板 五、62 / 八、64，Task 3.2 已对齐源模板）────────────
const T = {
  listed: {
    main: '营业收入和营业成本',
    industry: '营业收入、营业成本按行业（或产品类型）划分',
    region: '营业收入、营业成本按地区划分',
    timing: '营业收入、营业成本按分解信息',       // Req 6.1: 对齐源模板（旧名"…按商品转让时间划分"）
    obligation: '与剩余履约义务有关的信息',        // Req 6.4:（6）
    trialRun: '试运行销售收入',                    // Req 6.4:（8）仅上市
  },
  soe: {
    main: '营业收入、营业成本',
    industry: '按行业（或产品类型）划分',
    region: '营业收入、营业成本按地区划分',
    timing: '营业收入分解信息',                    // Req 6.1: 对齐源模板国企版
    obligation: '与剩余履约义务有关的信息',        // Req 6.4:（6）
  },
} as const

/**
 * 旧表名（改版前曾同步过的，走 `_removed_table_keys` 通知后端删旧键）。
 * 属于 Req 6.5 "底稿改版导致子表键变化"。
 */
export const D4_LEGACY_OBSOLETE_TABLES = [
  '营业收入、营业成本按商品转让时间划分',
] as const

// ─── 快照行类型（组件层传入，字段与 useD4Disclosure/d4DisclosureModel 行接口对齐）─

/** 主表行（section1Data：收入/成本 各本期/上期） */
export interface D4RevenueRowLike {
  label: string
  currentRevenue: number
  currentCost: number
  priorRevenue: number
  priorCost: number
}
/** 按行业/地区行（4 数据列） */
export interface D4FourColRowLike {
  label: string
  currentRevenue: number
  currentCost: number
  priorRevenue: number
  priorCost: number
}

export interface D4DisclosureSnapshot {
  /** section1Data（主营业务/其他业务，不含合计） */
  revenueRows: D4RevenueRowLike[]
  /** section1Total（合计行） */
  revenueTotal: D4RevenueRowLike
  /** section2（按行业/产品类型划分，动态行） */
  industryRows: D4FourColRowLike[]
  /** section3（按地区划分，动态行） */
  regionRows: D4FourColRowLike[]
  /** section4（按分解信息，列转置动态类别列） */
  timingRows: D4TransposeRow[]
  /** section4 的动态类别列定义 */
  timingCategories?: D4TransposeCategory[]
  /** section6（与剩余履约义务有关的信息，动态行） */
  section6Rows?: D4ObligationRow[]
  /** section8（试运行销售收入，仅上市，两期表行） */
  section8Rows?: D4TwoPeriodRow[]
  /** 审计年度（用于（6）年度列派生），缺省 2025 */
  auditYear?: number
  /** 各子节说明文本（note-1..note-8），与披露表文本框保持一致后同步到附注 text_content */
  notes: Record<string, string>
}

export interface D4SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

type NullableAmount = number | null

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const str = (v: unknown): string => String(v ?? '')
const toN = (v: unknown): NullableAmount => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** 可空求和：全为 null 时返回 null（不塌成 0）。 */
function sumNullable(vals: readonly NullableAmount[]): NullableAmount {
  let has = false
  let total = 0
  for (const v of vals) {
    if (v === null || v === undefined) continue
    has = true
    total += v
  }
  return has ? Math.round(total * 100) / 100 : null
}

/**
 * 构建 D4 → 附注 sync-from-workpaper 载荷。
 *
 * 上市：五、62（6 张子表）；国企：八、64（5 张子表，无试运行销售收入）。
 * 所有表的 columns 声明 group（两级）或 flat（单级）—— Property 13。
 * 载荷包含 `_removed_table_keys`（遗留旧表名求差集）—— Req 6.5 / Property 20。
 * `_note_texts` 在 sub_table_data 内、带中文 title、过滤空文本 —— Req 6.6。
 */
export function buildD4SyncPayload(
  variant: D4DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D4DisclosureSnapshot,
): D4SyncPayload {
  const isSoe = variant === 'soe'
  const isListed = variant === 'listed'
  const names = isSoe ? T.soe : T.listed
  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const put = (name: string, rows: unknown, cols: ColumnDef[]) => {
    sub[name] = rows
    columns[name] = cols
  }

  // ① 营业收入和营业成本主表（明细 + 合计）— 两级 group
  const mainCols = buildD4TwoPeriodColumns('main')
  const mainRow = (r: D4RevenueRowLike, isTotal = false) => ({
    label: str(r.label),
    endRevenue: num(r.currentRevenue),
    endCost: num(r.currentCost),
    priorRevenue: num(r.priorRevenue),
    priorCost: num(r.priorCost),
    ...(isTotal ? { is_total: true } : {}),
  })
  put(
    names.main,
    [...snapshot.revenueRows.map((r) => mainRow(r)), mainRow(snapshot.revenueTotal, true)],
    mainCols,
  )

  // ② 按行业（或产品类型）划分 — 两级 group，含上期两列（Req 6.2）
  const industryCols = buildD4TwoPeriodColumns('main')
  // label 列保持既有（标签列按变体应该不同但表头对齐 model）
  industryCols[0] = { ...industryCols[0], label: '主要产品类型（或行业）' }
  put(
    names.industry,
    buildFourColRows(snapshot.industryRows ?? []),
    industryCols,
  )

  // ③ 按地区划分 — 两级 group，叶子列名按变体不同（Property 12）
  const regionCols = buildD4TwoPeriodColumns(isSoe ? 'region_soe' : 'region_listed')
  regionCols[0] = { ...regionCols[0], label: '主要经营地区' }
  put(
    names.region,
    buildFourColRows(snapshot.regionRows ?? []),
    regionCols,
  )

  // ④ 按分解信息（列转置 + 动态类别列）— 两级 group（Req 6.3）
  const categories = snapshot.timingCategories ?? [...D4_DEFAULT_CATEGORIES]
  const transposeCols = buildD4TransposeColumns(categories)
  // 国企（4）首列头 = '合同分类/报告分部'
  if (isSoe) {
    transposeCols[0] = { ...transposeCols[0], label: '合同分类/报告分部' }
  }
  put(
    names.timing,
    snapshot.timingRows ?? [],
    transposeCols,
  )

  // ⑤（6）与剩余履约义务有关的信息 — flat 单级表头（Req 6.4 / 6.7）
  const auditYear = snapshot.auditYear ?? 2025
  const obligationCols = buildD4ObligationColumns(auditYear)
  const obligationRows = buildObligationPayloadRows(snapshot.section6Rows ?? [], auditYear)
  put(names.obligation, obligationRows, obligationCols)

  // ⑥（8）试运行销售收入 — 仅上市，两级 group（Req 6.4）
  if (isListed && 'trialRun' in names) {
    const trialRunCols = buildD4TwoPeriodColumns('main')
    const trialRunRows = buildTrialRunPayloadRows(snapshot.section8Rows ?? [])
    put(names.trialRun, trialRunRows, trialRunCols)
  }

  // ⑦ 文本框内容 — _note_texts 在 sub_table_data 内（Req 6.6）
  sub._note_texts = buildD4NoteTexts(variant, snapshot.notes)

  // ⑧ _removed_table_keys：previouslySynced ∩ (allKnownKeys \ currentPushKeys)（Req 6.5）
  const pushKeys = new Set(Object.keys(sub).filter(k => !k.startsWith('_')))
  const removed = D4_LEGACY_OBSOLETE_TABLES.filter(k => !pushKeys.has(k))
  if (removed.length > 0) {
    sub._removed_table_keys = removed
  }

  return {
    wp_id: wpId,
    sheet_name: D4_DISCLOSURE_SHEET_NAME[variant],
    section_id: D4_NOTE_SECTION[variant],
    current_standard: resolveD4CurrentStandard(variant, applicableStandards),
    sub_table_data: sub,
    columns,
  }
}

// ─── 内部构造函数 ─────────────────────────────────────────────────────────────

/** 按行业/地区/时段的四列表行构造（含上期 + 合计） */
function buildFourColRows(rows: D4FourColRowLike[]): unknown[] {
  return [
    ...rows.map((r) => ({
      label: str(r.label),
      endRevenue: num(r.currentRevenue),
      endCost: num(r.currentCost),
      priorRevenue: num(r.priorRevenue),
      priorCost: num(r.priorCost),
    })),
    {
      label: '合计',
      endRevenue: sumNullable(rows.map((r) => toN(r.currentRevenue))),
      endCost: sumNullable(rows.map((r) => toN(r.currentCost))),
      priorRevenue: sumNullable(rows.map((r) => toN(r.priorRevenue))),
      priorCost: sumNullable(rows.map((r) => toN(r.priorCost))),
      is_total: true,
    },
  ]
}

/** （6）义务表行构造（合计列派生） */
function buildObligationPayloadRows(rows: D4ObligationRow[], auditYear: number): unknown[] {
  return rows.map((r) => ({
    ...r,
    total: deriveObligationTotal(r, auditYear),
  }))
}

/** （8）试运行销售收入行构造 */
function buildTrialRunPayloadRows(rows: D4TwoPeriodRow[]): unknown[] {
  return rows.map((r) => ({
    label: str(r.label),
    endRevenue: toN(r.endRevenue),
    endCost: toN(r.endCost),
    priorRevenue: toN(r.priorRevenue),
    priorCost: toN(r.priorCost),
  }))
}

// ─── _note_texts（Req 6.6） ──────────────────────────────────────────────────

/**
 * 说明文本子节（key = useD4Disclosure 的 note-N；标题与披露表子节一致）。
 * 上市 8 节（含试运行销售收入 note-8）/ 国企 7 节。
 * 🔴 title 使用中文（Req 6.6），过滤空文本。
 */
export const D4_NOTE_TEXT_SECTIONS: Record<D4DisclosureVariant, Array<{ key: string; title: string }>> = {
  listed: [
    { key: 'note-1', title: '营业收入和营业成本说明' },
    { key: 'note-2', title: '按行业（或产品类型）划分说明' },
    { key: 'note-3', title: '按地区划分说明' },
    { key: 'note-4', title: '收入分解信息说明' },
    { key: 'note-5', title: '履约义务的说明' },
    { key: 'note-6', title: '与剩余履约义务有关的信息' },
    { key: 'note-7', title: '重大合同变更说明' },
    { key: 'note-8', title: '试运行销售收入说明' },
  ],
  soe: [
    { key: 'note-1', title: '营业收入、营业成本说明' },
    { key: 'note-2', title: '按行业（或产品类型）划分说明' },
    { key: 'note-3', title: '按地区划分说明' },
    { key: 'note-4', title: '收入分解信息说明' },
    { key: 'note-5', title: '履约义务相关信息' },
    { key: 'note-6', title: '与剩余履约义务有关的信息' },
    { key: 'note-7', title: '重大合同变更说明' },
  ],
}

/** 各子节说明 → _note_texts（仅非空），保证附注 text_content 与披露表文本框一致。 */
export function buildD4NoteTexts(
  variant: D4DisclosureVariant,
  notes: Record<string, string>,
): Array<{ section: string; title: string; text: string }> {
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const { key, title } of D4_NOTE_TEXT_SECTIONS[variant]) {
    const text = String(notes?.[key] ?? '').trim()
    if (text) out.push({ section: `${variant}-${key}`, title, text })
  }
  return out
}
