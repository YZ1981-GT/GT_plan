/**
 * H8 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、25
 * - 国企：note_template_soe §八、26
 */
import {
  H8_DISCLOSURE_SHEET_NAME,
  H8_LISTED_SUBTABLE,
  H8_NOTE_SECTION,
  H8_SOE_SUBTABLE,
  isH8DisclosureApplicable,
  resolveH8CurrentStandard,
  type H8DisclosureVariant,
} from './h8NoteSectionMap'
import {
  H8_LISTED_MOVEMENT_ROWS,
  h8ListedCellValue,
  h8ListedTotalCellValue,
  type H8ListedSyncSnapshot,
} from './h8ListedDisclosureModel'
import {
  H8_SOE_LAYER_META,
  flattenSoeMovement,
  type H8SoeSyncSnapshot,
} from './h8SoeDisclosureModel'
import type { ColumnDef } from './disclosureColumnDefs'

export interface H8SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 H8TabDisclosure 使用权资产变动表 */
  columns?: Record<string, ColumnDef[]>
}

/**
 * 上市变动表列头随类别动态（项目 + 类别 + 合计），键对齐 buildH8ListedSubTableData。
 *
 * 🔴 首列必须 `flat: true`：源模板表头是单行，不声明时后端
 * `_extract_column_groups` 返回 `None` → 回退 `_infer_groups_from_headers` 前缀推断，
 * 会凭空造出父表头（实测国企侧被推成 `[{group:'本期',start:2,span:2}]`）。
 * `flat` 标在任意一列即对整表生效。
 */
export function buildH8ListedColumns(state: H8ListedSyncSnapshot): Record<string, ColumnDef[]> {
  const cats = state.categories || []
  return {
    [H8_LISTED_SUBTABLE.movement]: [
      { key: 'label', label: '项目', is_label: true, flat: true },
      ...cats.map((c) => ({ key: c.label, label: c.label, format: 'amount' as const })),
      { key: '合计', label: '合计', format: 'amount' },
    ],
  }
}

/**
 * 国企变动表列头（项目/期初余额/本期增加/本期减少/期末余额），键对齐 flattenSoeMovement。
 *
 * 🔴 `flat: true` 同上 —— 缺它时 `本期增加`/`本期减少` 会被前缀推断归到凭空的「本期」父表头下。
 */
const H8_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  [H8_SOE_SUBTABLE.movement]: [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'begin', label: '期初余额', format: 'amount' },
    { key: 'increase', label: '本期增加', format: 'amount' },
    { key: 'decrease', label: '本期减少', format: 'amount' },
    { key: 'end', label: '期末余额', format: 'amount' },
  ],
}

/**
 * `_note_texts` section → 中文标题。
 *
 * 🔴 缺 `title` 时后端 `_format_note_texts` 用 `section` 兜底 → 附注正文会渲染成
 * `【listed-short-low】` 这类英文键（违反 UI 全中文化）。
 */
export const H8_NOTE_TEXT_TITLES: Record<string, string> = {
  'listed-short-low': '短期租赁及低价值资产租赁费用说明',
  'listed-impairment': '使用权资产减值情况说明',
  'soe-impairment': '使用权资产减值情况说明',
}

/** 构造 `_note_texts`：过滤空白文本 + 补中文 title（两变体共用） */
export function buildH8NoteTexts(
  items: ReadonlyArray<{ section: string; text: string | null | undefined }>,
): Array<{ section: string; title: string; text: string }> {
  return items
    .filter((it) => String(it.text ?? '').trim())
    .map((it) => ({
      section: it.section,
      title: H8_NOTE_TEXT_TITLES[it.section] || it.section,
      text: String(it.text).trim(),
    }))
}

export function buildH8ListedSubTableData(state: H8ListedSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const cats = state.categories
  const rows: Record<string, unknown>[] = []
  for (const def of H8_LISTED_MOVEMENT_ROWS) {
    if (def.kind === 'section') {
      rows.push({ label: def.label, is_section: true })
      continue
    }
    const row: Record<string, unknown> = {
      label: def.label,
      is_total: def.kind === 'calc' || def.kind === 'book' || def.kind === 'subtotal',
    }
    for (const c of cats) {
      row[c.label] = h8ListedCellValue(state.movement, def, c.key)
    }
    row['合计'] = h8ListedTotalCellValue(state.movement, def, cats)
    rows.push(row)
  }

  const out: Record<string, Record<string, unknown>[]> = {
    [H8_LISTED_SUBTABLE.movement]: rows,
  }
  // 空白文本不产生条目；全空时不产生 `_note_texts` 键
  const notes = buildH8NoteTexts([
    { section: 'listed-short-low', text: state.noteShortLow },
    { section: 'listed-impairment', text: state.noteImpairment },
  ])
  if (notes.length) out._note_texts = notes as unknown as Record<string, unknown>[]
  return out
}

export function buildH8SoeSubTableData(state: H8SoeSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const movementRows: Record<string, unknown>[] = []
  for (const flat of flattenSoeMovement(state.layers)) {
    const meta = H8_SOE_LAYER_META[flat.layer]
    movementRows.push({
      label: flat.label,
      begin: flat.begin,
      increase: meta.movementNa || flat.allNa ? null : flat.increase,
      decrease: meta.movementNa || flat.allNa ? null : flat.decrease,
      end: flat.end,
      is_total: flat.kind === 'total',
      layer: flat.layer,
    })
  }
  const out: Record<string, Record<string, unknown>[]> = {
    [H8_SOE_SUBTABLE.movement]: movementRows,
  }
  const notes = buildH8NoteTexts([
    { section: 'soe-impairment', text: state.noteImpairment },
  ])
  if (notes.length) out._note_texts = notes as unknown as Record<string, unknown>[]
  return out
}

export function buildH8ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H8ListedSyncSnapshot,
): H8SyncFromWorkpaperPayload[] {
  const variant: H8DisclosureVariant = 'listed'
  if (!isH8DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: H8_DISCLOSURE_SHEET_NAME.listed,
    section_id: H8_NOTE_SECTION.listed,
    current_standard: resolveH8CurrentStandard(variant, applicableStandards),
    sub_table_data: buildH8ListedSubTableData(state),
    columns: buildH8ListedColumns(state),
  }]
}

export function buildH8SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H8SoeSyncSnapshot,
): H8SyncFromWorkpaperPayload[] {
  const variant: H8DisclosureVariant = 'soe'
  if (!isH8DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: H8_DISCLOSURE_SHEET_NAME.soe,
    section_id: H8_NOTE_SECTION.soe,
    current_standard: resolveH8CurrentStandard(variant, applicableStandards),
    sub_table_data: buildH8SoeSubTableData(state),
    columns: H8_SOE_COLUMNS,
  }]
}
