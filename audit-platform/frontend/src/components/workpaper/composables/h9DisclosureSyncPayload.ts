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

/**
 * 租赁负债子表列头：逐字取自源模板 R7（上市 上年年末余额 / 国企 期初余额）。
 *
 * 🔴 首列 `flat: true`：源模板表头单行，不声明时后端 `_extract_column_groups` 返 `None`
 * → 回退前缀推断造凭空父表头。**seed 与推送两处都要加**（H8 实测教训）。
 */
const H9_LISTED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
  { key: 'prior_balance', label: '上年年末余额', format: 'amount' },
]
const H9_SOE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
  { key: 'begin_balance', label: '期初余额', format: 'amount' },
]

/**
 * `_note_texts` section → 中文标题。
 *
 * 🔴 缺 `title` 时后端 `_format_note_texts` 用 `section` 兜底 → 附注正文渲染成
 * `【listed-interest】`（违反 UI 全中文化）。
 */
export const H9_NOTE_TEXT_TITLES: Record<string, string> = {
  'listed-interest': '租赁负债利息费用说明',
  'soe-guidance': '补充披露说明',
}

/** 构造 `_note_texts`：过滤空白 + 补中文 title（两变体共用） */
export function buildH9NoteTexts(
  items: ReadonlyArray<{ section: string; text: string | null | undefined }>,
): Array<{ section: string; title: string; text: string }> {
  return items
    .filter((it) => String(it.text ?? '').trim())
    .map((it) => ({
      section: it.section,
      title: H9_NOTE_TEXT_TITLES[it.section] || it.section,
      text: String(it.text).trim(),
    }))
}

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

  const sub: Record<string, Record<string, unknown>[]> = {
    [H9_LISTED_SUBTABLE.main]: rows,
  }
  const notes = buildH9NoteTexts([
    { section: 'listed-interest', text: resolveListedInterestNote(state) },
  ])
  if (notes.length) sub._note_texts = notes as unknown as Record<string, unknown>[]
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
  const notes = buildH9NoteTexts([
    { section: 'soe-guidance', text: state.supplementNote },
  ])
  if (notes.length) sub._note_texts = notes as unknown as Record<string, unknown>[]
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
