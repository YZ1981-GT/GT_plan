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

export interface H8SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
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

  return {
    [H8_LISTED_SUBTABLE.movement]: rows,
    _note_texts: [
      { section: 'listed-short-low', text: state.noteShortLow || '' },
      { section: 'listed-impairment', text: state.noteImpairment || '' },
    ] as unknown as Record<string, unknown>[],
  }
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
  return {
    [H8_SOE_SUBTABLE.movement]: movementRows,
    _note_texts: [
      { section: 'soe-impairment', text: state.noteImpairment || '' },
    ] as unknown as Record<string, unknown>[],
  }
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
  }]
}
