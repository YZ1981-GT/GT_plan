/**
 * N4 税金及附加披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源
 * --------
 * - **列结构 / 行型 / 文本** = `backend/wp_templates/N/N4 税金及附加.xlsx` 的
 *   `附注披露信息（上市公司）`（A1:L18）与 `附注披露信息（国企）`（A1:K17），逐行实测。
 * - **章节号** = `backend/data/note_template_variant_matrix.json` 的 `shui_jin_ji_fu_jia`
 *   → listed 五、63；`soe_standalone` / `soe_consolidated` 为 `null`。
 * - **表名 / 行集合** = `note_template_listed.json`
 *   （由 `backend/scripts/fix/fix_note_n_cycle_tax_structure.py` 幂等维护）
 * - **sheet 名** = `workpaper_sheet_classification`（wp_code=N4）实测全角括号
 *
 * 🔴 **国企版不披露税金及附加**：源模板 `附注披露信息（国企）` 的 R5/R6 是
 * `附注披露信息：` / **`无`** —— 整个 sheet 没有表。`variant_matrix` 里 `soe_*` 为
 * `null` 是正确的，不得"补齐"。故 `buildN4SyncPayload('soe', …)` **恒返回 `null`**，
 * 国企 Tab 只展示「本版不适用」说明页。
 *
 * 现状缺陷：上市披露组件是自造的 **6 列**表（在源模板 3 列之外加了变动额 / 变动率 /
 * 变动原因 —— 那是审计过程，属 N4-1 审定表），且两版都没有同步链路。
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'
import type { TableNamespaceSpec } from './disclosureSyncedTables'
import { nz, sumNullable, type NullableAmount } from './shared/disclosureConsistency'

export type N4DisclosureVariant = 'listed' | 'soe'

/**
 * 附注章节号。
 * `soe` 恒为 `null` —— 源模板国企版不披露（不是"缺章节"）。
 */
export const N4_NOTE_SECTION = {
  listed: '五、63',
  soe: null,
} as const satisfies Record<N4DisclosureVariant, string | null>

/** 底稿披露 sheet 真实 tab 名（逐字取自 `workpaper_sheet_classification`） */
export const N4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<N4DisclosureVariant, string>

/** 子表键（逐字取自附注模板 `tables[].name`）；国企无表 */
export const N4_SUB_TABLE_KEYS = {
  listed: { taxes: '税金及附加' },
} as const

/** 表名命名空间（孤儿清理基线播种） */
export const N4_TABLE_NAMESPACE: Record<'listed', TableNamespaceSpec> = {
  listed: { known: Object.values(N4_SUB_TABLE_KEYS.listed) },
}

export const N4_TOTAL_LABEL = '合计'

/** 国企不适用的源模板依据（Tab 内展示，禁改写为"功能未做"） */
export const N4_SOE_NOT_APPLICABLE_REASON =
  '致同源模板《N4 税金及附加》的「附注披露信息（国企）」sheet 内容为「附注披露信息：无」，'
  + '即国有企业格式财务报表不单独披露税金及附加明细，'
  + '故本版无披露表、也不产生附注章节（附注章节矩阵 shui_jin_ji_fu_jia 的国企变体为空）。'

export function resolveN4CurrentStandard(
  applicableStandards?: readonly string[] | null,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
    return 'listed_consolidated'
  }
  return 'listed_standalone'
}

// ─── 列定义（逐字对齐附注模板 headers）───────────────────────────────────────

const AMT = 'amount' as const

/** 上市：3 列双期发生额表（源模板 R7） */
export function buildN4ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [N4_SUB_TABLE_KEYS.listed.taxes]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'current', label: '本期发生额', format: AMT },
      { key: 'prior', label: '上期发生额', format: AMT },
    ]),
  }
}

/**
 * 变体分发。国企无列定义（不披露）→ 返回空对象。
 *
 * 🔴 不能命名为 `buildN4Columns`：`disclosureColumnsCoverage` 守卫会 sweep 所有
 * `build*Columns` 并**用空入参调用**，带 variant 的 builder 会拿到 `undefined`。
 */
export function n4ColumnsFor(variant: N4DisclosureVariant): Record<string, ColumnDef[]> {
  return variant === 'listed' ? buildN4ListedColumns() : {}
}

// ─── Snapshot ────────────────────────────────────────────────────────────────

export interface N4TaxRow {
  item: string
  /** 本期发生额 */
  current: NullableAmount
  /** 上期发生额 */
  prior: NullableAmount
}

export interface N4DisclosureSnapshot {
  taxRows: readonly N4TaxRow[]
  /** 说明 / 结论文本（按子节，空串不同步） */
  notes?: Record<string, string>
  previouslySyncedTables?: readonly string[]
}

export interface N4SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  year: number
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

// ─── helpers ─────────────────────────────────────────────────────────────────

/** 行型判定先去空白（源模板写 `合  计`） */
export function normalizeN4RowLabel(label: unknown): string {
  return String(label ?? '').replace(/\s+/g, '')
}

export function isN4TotalLabel(label: unknown): boolean {
  const s = normalizeN4RowLabel(label)
  return s.startsWith('小计') || s.startsWith('合计')
}

const NOTE_TITLES: Record<string, string> = {
  standard: '计缴标准说明',
  conclusion: '披露说明与结论',
}

const NOTE_ORDER = ['standard', 'conclusion']

export function buildN4NoteTexts(
  notes?: Record<string, string>,
): Array<{ section: string; title: string; text: string }> {
  if (!notes) return []
  const keys = [
    ...NOTE_ORDER.filter((k) => k in notes),
    ...Object.keys(notes).filter((k) => !NOTE_ORDER.includes(k)),
  ]
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const k of keys) {
    const text = String(notes[k] ?? '').trim()
    if (!text) continue
    out.push({ section: `n4-disclosure-${k}`, title: NOTE_TITLES[k] || k, text })
  }
  return out
}

// ─── payload 构造（纯函数）───────────────────────────────────────────────────

/**
 * 构造同步载荷。
 *
 * @returns `variant === 'soe'` 时恒为 `null`（源模板国企版不披露）
 */
export function buildN4SyncPayload(
  variant: N4DisclosureVariant,
  snapshot: N4DisclosureSnapshot,
  ctx: { wpId: string; year: number; applicableStandards?: readonly string[] | null },
): N4SyncPayload | null {
  if (variant !== 'listed') return null

  const key = N4_SUB_TABLE_KEYS.listed.taxes
  const columns = buildN4ListedColumns()
  const rows = snapshot.taxRows || []

  const dataRows = rows.map((r) => ({
    label: String(r.item ?? ''),
    current: nz(r.current),
    prior: nz(r.prior),
  }))

  const totalRow: Record<string, unknown> = {
    label: N4_TOTAL_LABEL,
    current: sumNullable(dataRows.map((r) => r.current)),
    prior: sumNullable(dataRows.map((r) => r.prior)),
    is_total: true,
  }

  const subTableData: Record<string, unknown> = { [key]: [...dataRows, totalRow] }

  const texts = buildN4NoteTexts(snapshot.notes)
  if (texts.length > 0) subTableData._note_texts = texts

  return {
    wp_id: ctx.wpId,
    sheet_name: N4_DISCLOSURE_SHEET_NAME.listed,
    section_id: N4_NOTE_SECTION.listed,
    current_standard: resolveN4CurrentStandard(ctx.applicableStandards),
    year: ctx.year,
    sub_table_data: subTableData,
    columns,
  }
}

export default buildN4SyncPayload
