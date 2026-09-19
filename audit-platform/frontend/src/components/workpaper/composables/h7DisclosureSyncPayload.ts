/**
 * H7 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、24（两张两级表头的列转置表）
 * - 国企：note_template_soe §八、24（两张 5 列单级表）
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 4)
 */
import {
  H7_DISCLOSURE_SHEET_NAME,
  H7_LEGACY_OBSOLETE_TABLES,
  H7_LISTED_SUBTABLE,
  H7_NOTE_SECTION,
  H7_SOE_SUBTABLE,
  isH7DisclosureApplicable,
  resolveH7CurrentStandard,
  type H7DisclosureVariant,
} from './h7NoteSectionMap'
import {
  H7_COST_MOVEMENT_ROWS,
  H7_FAIR_MOVEMENT_ROWS,
  H7_TOTAL_COL_KEY,
  createDefaultH7Categories,
  h7CellValue,
  h7IndustryLabel,
  h7TotalCellValue,
  orderH7Categories,
  type H7ListedCategory,
  type H7ListedSyncSnapshot,
  type H7MovementRowDef,
} from './h7ListedDisclosureModel'
import {
  buildSoeDisplayRows,
  type H7SoeSyncSnapshot,
} from './h7SoeDisclosureModel'
import type { ColumnDef } from './disclosureColumnDefs'

export interface H7SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns?: Record<string, ColumnDef[]>
}

/**
 * 上市列头：项目（rowspan 2，无 group）+ 各产业下的类别列（`group` = 产业名）
 * + 合计（rowspan 2，无 group）—— 与源模板合并区 `A9:A10` / `B9:C9` … / `J9:J10` 同构。
 *
 * 🔴 两级表头**不得**标 `flat`（`flat` 会让后端 `_extract_column_groups` 直接返 `[]`，
 * 两级分组就丢了）。
 */
export function h7ListedColumnsFor(
  categories: readonly H7ListedCategory[] = createDefaultH7Categories(),
): ColumnDef[] {
  const ordered = orderH7Categories(categories)
  return [
    { key: 'label', label: '项目', is_label: true },
    ...ordered.map((c) => ({
      key: c.key,
      label: c.label,
      group: h7IndustryLabel(c.industry),
      format: 'amount' as const,
    })),
    { key: H7_TOTAL_COL_KEY, label: '合计', format: 'amount' as const },
  ]
}

/**
 * 两张上市表列头同构（源模板 R9/R10 与 R51/R52 一致）。
 *
 * 🔴 默认入参必须给完整默认类别：平台覆盖率 sweep
 * （`disclosureColumnsCoverage.spec.ts`）会用**零入参**调用 `build*Columns`，
 * 缺省时只剩「项目 + 合计」两列（均无 group）→ 被判为「flat/group 未表态」。
 */
export function buildH7ListedColumns(
  categories: readonly H7ListedCategory[] = createDefaultH7Categories(),
): Record<string, ColumnDef[]> {
  const cols = h7ListedColumnsFor(categories)
  return {
    [H7_LISTED_SUBTABLE.cost]: cols,
    [H7_LISTED_SUBTABLE.fair]: cols.map((c) => ({ ...c })),
  }
}

/** 国企列头（5 列单级 → 必须显式 flat，否则前缀推断会造凭空父表头） */
const H7_SOE_MAIN_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'begin', label: '期初账面价值', format: 'amount' },
  { key: 'increase', label: '本期增加额', format: 'amount' },
  { key: 'decrease', label: '本期减少额', format: 'amount' },
  { key: 'end', label: '期末账面价值', format: 'amount' },
]

export const H7_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  [H7_SOE_SUBTABLE.cost]: H7_SOE_MAIN_COLUMNS,
  [H7_SOE_SUBTABLE.fair]: H7_SOE_MAIN_COLUMNS.map((c) => ({ ...c })),
}

/**
 * `_note_texts` section → 中文标题。
 *
 * 🔴 缺 `title` 时后端 `_format_note_texts` 用 `section` 兜底 → 附注正文渲染成
 * `【listed-policy】`（违反 UI 全中文化）。
 */
export const H7_NOTE_TEXT_TITLES: Record<string, string> = {
  'listed-policy': '计量模式与折旧政策',
  'listed-impairment': '减值测试与可收回金额说明',
  'listed-supplement': '补充披露（数量、寿命、风险与管理措施）',
  'soe-policy': '计量政策与折旧方法',
  'soe-fair-basis': '公允价值确认依据',
  'soe-supplement': '风险情况与管理措施',
}

/** 构造 `_note_texts`：过滤空白 + 补中文 title（两变体共用） */
export function buildH7NoteTexts(
  items: ReadonlyArray<{ section: string; text: string | null | undefined }>,
): Array<{ section: string; title: string; text: string }> {
  return items
    .filter((it) => String(it.text ?? '').trim())
    .map((it) => ({
      section: it.section,
      title: H7_NOTE_TEXT_TITLES[it.section] || it.section,
      text: String(it.text).trim(),
    }))
}

function buildMovementRows(
  rows: readonly H7MovementRowDef[],
  map: H7ListedSyncSnapshot['cost'],
  categories: readonly H7ListedCategory[],
): Record<string, unknown>[] {
  const ordered = orderH7Categories(categories)
  const out: Record<string, unknown>[] = []
  for (const def of rows) {
    const row: Record<string, unknown> = { label: def.label }
    if (def.kind === 'section') {
      row.is_section = true
    } else {
      for (const c of ordered) row[c.key] = h7CellValue(map, def, c.key, rows)
      row[H7_TOTAL_COL_KEY] = h7TotalCellValue(map, def, ordered, rows)
      if (def.kind !== 'detail' && def.kind !== 'ellipsis') row.is_total = true
    }
    out.push(row)
  }
  return out
}

export function buildH7ListedSubTableData(
  state: H7ListedSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [H7_LISTED_SUBTABLE.cost]: buildMovementRows(
      H7_COST_MOVEMENT_ROWS, state.cost, state.categories,
    ),
    [H7_LISTED_SUBTABLE.fair]: buildMovementRows(
      H7_FAIR_MOVEMENT_ROWS, state.fair, state.categories,
    ),
  }
  // 上市第 2 张表原名是表头首格泄漏 `项  目`（与第 1 张表同名时会互相覆盖）→ 正名后清旧键
  out._removed_table_keys = [
    ...H7_LEGACY_OBSOLETE_TABLES,
  ] as unknown as Record<string, unknown>[]

  const notes = buildH7NoteTexts([
    { section: 'listed-policy', text: state.notePolicy },
    { section: 'listed-impairment', text: state.noteImpairment },
    { section: 'listed-supplement', text: state.noteSupplement },
  ])
  if (notes.length) out._note_texts = notes as unknown as Record<string, unknown>[]
  return out
}

function buildSoeRows(
  blocks: H7SoeSyncSnapshot['cost'],
): Record<string, unknown>[] {
  return buildSoeDisplayRows(blocks).map((r) => ({
    label: r.label,
    begin: r.begin,
    increase: r.increase,
    decrease: r.decrease,
    end: r.end,
    ...(r.kind === 'total' ? { is_total: true } : {}),
    row_kind: r.kind,
  }))
}

export function buildH7SoeSubTableData(
  state: H7SoeSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [H7_SOE_SUBTABLE.cost]: buildSoeRows(state.cost),
    [H7_SOE_SUBTABLE.fair]: buildSoeRows(state.fair),
  }
  const notes = buildH7NoteTexts([
    { section: 'soe-policy', text: state.notePolicy },
    { section: 'soe-fair-basis', text: state.noteFairBasis },
    { section: 'soe-supplement', text: state.noteSupplement },
  ])
  if (notes.length) out._note_texts = notes as unknown as Record<string, unknown>[]
  return out
}

export function buildH7ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H7ListedSyncSnapshot,
): H7SyncFromWorkpaperPayload[] {
  const variant: H7DisclosureVariant = 'listed'
  if (!isH7DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: H7_DISCLOSURE_SHEET_NAME.listed,
    section_id: H7_NOTE_SECTION.listed,
    current_standard: resolveH7CurrentStandard(variant, applicableStandards),
    sub_table_data: buildH7ListedSubTableData(state),
    columns: buildH7ListedColumns(state.categories),
  }]
}

export function buildH7SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H7SoeSyncSnapshot,
): H7SyncFromWorkpaperPayload[] {
  const variant: H7DisclosureVariant = 'soe'
  if (!isH7DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: H7_DISCLOSURE_SHEET_NAME.soe,
    section_id: H7_NOTE_SECTION.soe,
    current_standard: resolveH7CurrentStandard(variant, applicableStandards),
    sub_table_data: buildH7SoeSubTableData(state),
    columns: H7_SOE_COLUMNS,
  }]
}
