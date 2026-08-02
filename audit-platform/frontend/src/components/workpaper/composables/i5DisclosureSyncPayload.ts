/**
 * I5 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、31（期末余额 / 上年年末余额 = 账面价值）
 * - 国企：note_template_soe §八、32（期末余额 / 期初余额）
 */
import {
  I5_DISCLOSURE_SHEET_NAME,
  I5_LISTED_SUBTABLE,
  I5_NOTE_SECTION,
  I5_SOE_SUBTABLE,
  isI5DisclosureApplicable,
  resolveI5CurrentStandard,
  type I5DisclosureVariant,
} from './i5NoteSectionMap'
import {
  summarizeI5Disclosure,
  type I5DisclosureRow,
} from './i5DisclosureModel'
import type { ColumnDef } from './disclosureColumnDefs'

export interface I5SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 note_template §五、31/§八、32 */
  columns?: Record<string, ColumnDef[]>
}

// 上市披露列：两级表头 7 列（对齐 fix_note_i_cycle_structure.py I5_LISTED_COLUMNS）
// 「期末数」/「上年年末数」各含 账面余额/减值准备/账面价值
const I5_LISTED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true },
  { key: 'end_book', label: '账面余额', group: '期末数', format: 'amount' },
  { key: 'end_impair', label: '减值准备', group: '期末数', format: 'amount' },
  { key: 'end_carrying', label: '账面价值', group: '期末数', format: 'amount' },
  { key: 'prior_book', label: '账面余额', group: '上年年末数', format: 'amount' },
  { key: 'prior_impair', label: '减值准备', group: '上年年末数', format: 'amount' },
  { key: 'prior_carrying', label: '账面价值', group: '上年年末数', format: 'amount' },
]

// 国企披露列：项目/期末余额/年初余额 flat（note_template §八、32，源 xlsx C6）
const I5_SOE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: '期末余额', label: '期末余额', format: 'amount', flat: true },
  { key: '年初余额', label: '年初余额', format: 'amount', flat: true },
]

export interface I5DisclosureSyncSnapshot {
  rows: I5DisclosureRow[]
  otherNote?: string
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _rowSignificant(r: I5DisclosureRow): boolean {
  return !!(
    r.item
    || Math.abs(
      _num(r.endGross) + _num(r.endImpairment) + _num(r.endBookValue)
      + _num(r.priorGross) + _num(r.priorImpairment) + _num(r.priorBookValue),
    ) > 0.005
  )
}

export function buildI5ListedSubTableData(state: I5DisclosureSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const dataRows = (state.rows || [])
    .filter(_rowSignificant)
    .map((r) => ({
      label: r.item || '（未命名）',
      end_book: _num(r.endGross),
      end_impair: _num(r.endImpairment),
      end_carrying: _num(r.endBookValue),
      prior_book: _num(r.priorGross),
      prior_impair: _num(r.priorImpairment),
      prior_carrying: _num(r.priorBookValue),
      is_total: false,
    }))

  const totals = summarizeI5Disclosure(state.rows || [])
  dataRows.push({
    label: '合计',
    end_book: totals.endGross,
    end_impair: totals.endImpairment,
    end_carrying: totals.endBookValue,
    prior_book: totals.priorGross,
    prior_impair: totals.priorImpairment,
    prior_carrying: totals.priorBookValue,
    is_total: true,
  })

  const notes = [
    { section: 'listed-other', title: '其他非流动资产说明', text: (state.otherNote || '').trim() },
  ].filter((n) => n.text)

  return {
    [I5_LISTED_SUBTABLE.main]: dataRows,
    ...(notes.length ? { _note_texts: notes as unknown as Record<string, unknown>[] } : {}),
  }
}

export function buildI5SoeSubTableData(state: I5DisclosureSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const dataRows = (state.rows || [])
    .filter(_rowSignificant)
    .map((r) => ({
      label: r.item || '（未命名）',
      期末余额: _num(r.endBookValue),
      年初余额: _num(r.priorBookValue),
      is_total: false,
    }))

  const totals = summarizeI5Disclosure(state.rows || [])
  dataRows.push({
    label: '合计',
    期末余额: totals.endBookValue,
    年初余额: totals.priorBookValue,
    is_total: true,
  })

  const notes = [
    { section: 'soe-other', title: '其他非流动资产说明', text: (state.otherNote || '').trim() },
  ].filter((n) => n.text)

  return {
    [I5_SOE_SUBTABLE.main]: dataRows,
    ...(notes.length ? { _note_texts: notes as unknown as Record<string, unknown>[] } : {}),
  }
}

export function buildI5ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: I5DisclosureSyncSnapshot,
): I5SyncFromWorkpaperPayload[] {
  const variant: I5DisclosureVariant = 'listed'
  if (!isI5DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I5_DISCLOSURE_SHEET_NAME.listed,
    section_id: I5_NOTE_SECTION.listed,
    current_standard: resolveI5CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI5ListedSubTableData(state),
    columns: { [I5_LISTED_SUBTABLE.main]: I5_LISTED_COLUMNS },
  }]
}

export function buildI5SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: I5DisclosureSyncSnapshot,
): I5SyncFromWorkpaperPayload[] {
  const variant: I5DisclosureVariant = 'soe'
  if (!isI5DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I5_DISCLOSURE_SHEET_NAME.soe,
    section_id: I5_NOTE_SECTION.soe,
    current_standard: resolveI5CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI5SoeSubTableData(state),
    columns: { [I5_SOE_SUBTABLE.main]: I5_SOE_COLUMNS },
  }]
}
