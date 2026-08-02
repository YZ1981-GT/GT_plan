/**
 * I6 研发费用披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、66
 * - 国企：note_template_soe §八、67
 */
import {
  I6_DISCLOSURE_SHEET_NAME,
  I6_LISTED_SUBTABLE,
  I6_NOTE_SECTION,
  I6_SOE_SUBTABLE,
  isI6DisclosureApplicable,
  resolveI6CurrentStandard,
  type I6DisclosureVariant,
} from './i6NoteSectionMap'
import { summarizeI6Disclosure, type I6DisclosureRow } from './i6DisclosureModel'
import type { ColumnDef } from './disclosureColumnDefs'

export interface I6SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 note_template §五、66/§八、67 研发费用按性质表 */
  columns?: Record<string, ColumnDef[]>
}

// 研发费用按性质表列头（项目/本期发生额/上期发生额），上市国企同构，flat 单行表头
const I6_EXPENSE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: '本期发生额', label: '本期发生额', format: 'amount', flat: true },
  { key: '上期发生额', label: '上期发生额', format: 'amount', flat: true },
]

export interface I6DisclosureSyncSnapshot {
  rows: I6DisclosureRow[]
  capitalizationNote?: string
  projectsNote?: string
  supplementNote?: string
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _hasAmount(row: I6DisclosureRow): boolean {
  return Math.abs(_num(row.currentAmount)) + Math.abs(_num(row.priorAmount)) > 0.005
    || !!(row.item && row.item.trim() && row.item !== '合计')
}

export function buildI6ExpenseSubTable(rows: I6DisclosureRow[]): Record<string, unknown>[] {
  const dataRows = (rows || [])
    .filter((r) => r.item !== '合计' && _hasAmount(r))
    .map((r) => ({
      label: r.item || '（未命名）',
      本期发生额: _num(r.currentAmount),
      上期发生额: _num(r.priorAmount),
      row_type: 'data' as const,
    }))

  const totals = summarizeI6Disclosure(rows.filter((r) => r.item !== '合计'))
  dataRows.push({
    label: '合计',
    本期发生额: totals.currentAmount,
    上期发生额: totals.priorAmount,
    row_type: 'total' as const,
  })

  return dataRows
}

function buildNoteTexts(snap: I6DisclosureSyncSnapshot, variant: I6DisclosureVariant): Record<string, unknown>[] {
  const notes: Array<{ section: string; title: string; text: string }> = []
  const push = (section: string, title: string, text?: string) => {
    const t = (text || '').trim()
    if (t) notes.push({ section, title, text: t })
  }

  if (variant === 'listed') {
    push('listed-capitalization', '研发支出资本化情况说明', snap.capitalizationNote)
    push('listed-projects', '重要研发项目说明', snap.projectsNote)
  } else {
    push('soe-supplement', '研发费用补充说明', snap.supplementNote)
  }

  return notes as unknown as Record<string, unknown>[]
}

export function buildI6ListedSubTableData(snap: I6DisclosureSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [I6_LISTED_SUBTABLE.expenseByNature]: buildI6ExpenseSubTable(snap.rows),
  }
  const notes = buildNoteTexts(snap, 'listed')
  if (notes.length) out._note_texts = notes
  return out
}

export function buildI6SoeSubTableData(snap: I6DisclosureSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [I6_SOE_SUBTABLE.expenseByNature]: buildI6ExpenseSubTable(snap.rows),
  }
  const notes = buildNoteTexts(snap, 'soe')
  if (notes.length) out._note_texts = notes
  return out
}

export function buildI6ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: I6DisclosureSyncSnapshot,
): I6SyncFromWorkpaperPayload[] {
  const variant: I6DisclosureVariant = 'listed'
  if (!isI6DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I6_DISCLOSURE_SHEET_NAME.listed,
    section_id: I6_NOTE_SECTION.listed,
    current_standard: resolveI6CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI6ListedSubTableData(snap),
    columns: { [I6_LISTED_SUBTABLE.expenseByNature]: I6_EXPENSE_COLUMNS },
  }]
}

export function buildI6SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: I6DisclosureSyncSnapshot,
): I6SyncFromWorkpaperPayload[] {
  const variant: I6DisclosureVariant = 'soe'
  if (!isI6DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I6_DISCLOSURE_SHEET_NAME.soe,
    section_id: I6_NOTE_SECTION.soe,
    current_standard: resolveI6CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI6SoeSubTableData(snap),
    columns: { [I6_SOE_SUBTABLE.expenseByNature]: I6_EXPENSE_COLUMNS },
  }]
}
