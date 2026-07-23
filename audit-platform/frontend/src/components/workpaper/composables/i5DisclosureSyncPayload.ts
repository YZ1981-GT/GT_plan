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

// 上市披露列：项目/期末余额/上年年末余额（note_template §五、31，账面价值口径）
const I5_LISTED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: '期末余额', label: '期末余额', format: 'amount' },
  { key: '上年年末余额', label: '上年年末余额', format: 'amount' },
]

// 国企披露列：项目/期末余额/期初余额（note_template §八、32）
const I5_SOE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: '期末余额', label: '期末余额', format: 'amount' },
  { key: '期初余额', label: '期初余额', format: 'amount' },
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
      期末余额: _num(r.endBookValue),
      上年年末余额: _num(r.priorBookValue),
      // 底稿侧明细字段保留，便于附注侧排查
      期末账面余额: _num(r.endGross),
      期末减值准备: _num(r.endImpairment),
      上年账面余额: _num(r.priorGross),
      上年减值准备: _num(r.priorImpairment),
      is_total: false,
    }))

  const totals = summarizeI5Disclosure(state.rows || [])
  dataRows.push({
    label: '合计',
    期末余额: totals.endBookValue,
    上年年末余额: totals.priorBookValue,
    期末账面余额: totals.endGross,
    期末减值准备: totals.endImpairment,
    上年账面余额: totals.priorGross,
    上年减值准备: totals.priorImpairment,
    is_total: true,
  })

  return {
    [I5_LISTED_SUBTABLE.main]: dataRows,
    _note_texts: [
      { section: 'listed-other', text: state.otherNote || '' },
    ] as unknown as Record<string, unknown>[],
  }
}

export function buildI5SoeSubTableData(state: I5DisclosureSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const dataRows = (state.rows || [])
    .filter(_rowSignificant)
    .map((r) => ({
      label: r.item || '（未命名）',
      期末余额: _num(r.endBookValue),
      期初余额: _num(r.priorBookValue),
      is_total: false,
    }))

  const totals = summarizeI5Disclosure(state.rows || [])
  dataRows.push({
    label: '合计',
    期末余额: totals.endBookValue,
    期初余额: totals.priorBookValue,
    is_total: true,
  })

  return {
    [I5_SOE_SUBTABLE.main]: dataRows,
    _note_texts: [
      { section: 'soe-other', text: state.otherNote || '' },
    ] as unknown as Record<string, unknown>[],
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
