/**
 * H9 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、47
 * - 国企：note_template_soe §八、52
 */
import {
  H9_DISCLOSURE_SHEET_NAME,
  H9_LISTED_SUBTABLE,
  H9_NOTE_SECTION,
  H9_SOE_SUBTABLE,
  isH9DisclosureApplicable,
  resolveH9CurrentStandard,
  type H9DisclosureVariant,
} from './h9NoteSectionMap'
import {
  amt,
  buildListedDisplayRows,
  buildSoeDisplayRows,
  resolveListedInterestNote,
  type H9ListedDisclosureState,
  type H9SoeDisclosureState,
} from './h9DisclosureModel'

import type { ColumnDef } from './disclosureColumnDefs'

export interface H9SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 H9 披露组件 el-table-column */
  columns?: Record<string, ColumnDef[]>
}

// 租赁负债子表列头：逐字取自 H9TabDisclosureListed/Soe el-table-column（源对齐）
const H9_LISTED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
  { key: 'prior_balance', label: '上年年末余额', format: 'amount' },
]
const H9_SOE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
  { key: 'begin_balance', label: '期初余额', format: 'amount' },
]

export function buildH9ListedSubTableData(
  state: H9ListedDisclosureState,
): Record<string, Record<string, unknown>[]> {
  const rows: Record<string, unknown>[] = []
  for (const r of buildListedDisplayRows(state)) {
    if (r.kind === 'category' && !String(r.item || '').trim()
      && !r.endBalance && !r.lastYearEnd) {
      continue
    }
    rows.push({
      label: r.item,
      end_balance: r.endBalance == null ? null : amt(Number(r.endBalance)),
      prior_balance: r.lastYearEnd == null ? null : amt(Number(r.lastYearEnd)),
      is_total: r.kind === 'subtotal' || r.kind === 'total',
      row_type: r.kind === 'category' || r.kind === 'within'
        ? 'data'
        : r.kind === 'subtotal'
          ? 'subtotal'
          : 'total',
    })
  }

  const interestText = resolveListedInterestNote(state)
  const sub: Record<string, Record<string, unknown>[]> = {
    [H9_LISTED_SUBTABLE.main]: rows,
  }
  if (interestText) {
    sub._note_texts = [
      { section: 'listed-interest', text: interestText },
    ] as unknown as Record<string, unknown>[]
  }
  return sub
}

export function buildH9SoeSubTableData(
  state: H9SoeDisclosureState,
): Record<string, Record<string, unknown>[]> {
  const rows: Record<string, unknown>[] = []
  for (const r of buildSoeDisplayRows(state)) {
    rows.push({
      label: r.item,
      end_balance: r.endBalance == null ? null : amt(Number(r.endBalance)),
      begin_balance: r.beginBalance == null ? null : amt(Number(r.beginBalance)),
      is_total: r.kind === 'net',
      row_type: r.kind === 'net' ? 'total' : 'data',
    })
  }
  const sub: Record<string, Record<string, unknown>[]> = {
    [H9_SOE_SUBTABLE.main]: rows,
  }
  if (state.supplementNote?.trim()) {
    sub._note_texts = [
      { section: 'soe-guidance', text: state.supplementNote.trim() },
    ] as unknown as Record<string, unknown>[]
  }
  return sub
}

export function buildH9ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H9ListedDisclosureState,
): H9SyncFromWorkpaperPayload[] {
  const variant: H9DisclosureVariant = 'listed'
  if (!isH9DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: H9_DISCLOSURE_SHEET_NAME.listed,
    section_id: H9_NOTE_SECTION.listed,
    current_standard: resolveH9CurrentStandard(variant, applicableStandards),
    sub_table_data: buildH9ListedSubTableData(state),
    columns: { [H9_LISTED_SUBTABLE.main]: H9_LISTED_COLUMNS },
  }]
}

export function buildH9SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H9SoeDisclosureState,
): H9SyncFromWorkpaperPayload[] {
  const variant: H9DisclosureVariant = 'soe'
  if (!isH9DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: H9_DISCLOSURE_SHEET_NAME.soe,
    section_id: H9_NOTE_SECTION.soe,
    current_standard: resolveH9CurrentStandard(variant, applicableStandards),
    sub_table_data: buildH9SoeSubTableData(state),
    columns: { [H9_SOE_SUBTABLE.main]: H9_SOE_COLUMNS },
  }]
}
