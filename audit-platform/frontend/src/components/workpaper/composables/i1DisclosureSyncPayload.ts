/**
 * I1 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、26
 * - 国企：note_template_soe §八、27
 */
import {
  I1_DISCLOSURE_SHEET_NAME,
  I1_LISTED_SUBTABLE,
  I1_NOTE_SECTION,
  I1_SOE_SUBTABLE,
  isI1DisclosureApplicable,
  resolveI1CurrentStandard,
  type I1DisclosureVariant,
} from './i1NoteSectionMap'
import {
  I1_LISTED_MOVEMENT_ROWS,
  i1ListedCellValue,
  i1ListedTotalCellValue,
  type I1ListedSyncSnapshot,
} from './i1ListedDisclosureModel'
import {
  I1_SOE_LAYER_META,
  flattenI1SoeMovement,
  type I1SoeSyncSnapshot,
} from './i1SoeDisclosureModel'
import {
  buildDataResourceSubTableRows,
  formatAmortAllocNote,
} from './i1DisclosureEnhance'

export interface I1SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
}

export function buildI1ListedSubTableData(state: I1ListedSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const cats = state.categories
  const rows: Record<string, unknown>[] = []
  for (const def of I1_LISTED_MOVEMENT_ROWS) {
    if (def.kind === 'section') {
      rows.push({ label: def.label, is_section: true })
      continue
    }
    const row: Record<string, unknown> = {
      label: def.label,
      is_total: def.kind === 'calc' || def.kind === 'book' || def.kind === 'subtotal',
    }
    for (const c of cats) {
      row[c.label] = i1ListedCellValue(state.movement, def, c.key)
    }
    row['合计'] = i1ListedTotalCellValue(state.movement, def, cats)
    rows.push(row)
  }

  const importantRows = (state.importantRows || [])
    .filter((r) => r.name || r.bookValue)
    .map((r) => ({
      label: r.name,
      账面价值: r.bookValue,
      剩余摊销期限: r.remainingAmortMonths,
    }))

  const titleRows = (state.titleCertRows || [])
    .filter((r) => r.name || r.bookValue)
    .map((r) => ({
      label: r.name,
      账面价值: r.bookValue,
      未办妥产权证书原因: r.reason,
    }))

  const out: Record<string, Record<string, unknown>[]> = {
    [I1_LISTED_SUBTABLE.movement]: rows,
    _note_texts: [
      { section: 'listed-rd-ratio', text: state.noteRdRatio || '' },
      { section: 'listed-indefinite', text: state.noteIndefinite || '' },
      { section: 'listed-mortgage', text: state.noteMortgage || '' },
      { section: 'listed-impairment', text: state.noteImpairment || '' },
      { section: 'listed-sale', text: state.noteSale || '' },
      { section: 'listed-important', text: state.noteImportant || '' },
      { section: 'listed-data-resource', text: state.noteDataResource || '' },
      { section: 'listed-amort-alloc', text: state.amortAlloc ? formatAmortAllocNote(state.amortAlloc) : '' },
    ] as unknown as Record<string, unknown>[],
  }
  if (importantRows.length) {
    out['⑥重要单项无形资产'] = importantRows
  }
  if (titleRows.length) {
    out['未办妥权属证书的土地使用权'] = titleRows
  }
  if (state.dataResource) {
    const dr = { ...state.dataResource, note: state.noteDataResource || state.dataResource.note || '' }
    const hasDr = Math.abs(Number(dr.costBegin) || 0)
      + Math.abs(Number(dr.costIncPurchase) || 0)
      + Math.abs(Number(dr.costIncRd) || 0)
      + Math.abs(Number(dr.costIncOther) || 0) > 0.005
    if (hasDr) {
      out['确认为无形资产的数据资源'] = buildDataResourceSubTableRows(dr)
    }
  }
  if (state.amortAlloc && Math.abs(state.amortAlloc.total) > 0.005) {
    out['本期摊销费用归属'] = [{
      label: '本期摊销费用',
      生产成本: state.amortAlloc.productionCost,
      制造费用: state.amortAlloc.manufacturing,
      销售费用: state.amortAlloc.selling,
      管理费用: state.amortAlloc.management,
      研发费用: state.amortAlloc.rd,
      其他: state.amortAlloc.other,
      合计: state.amortAlloc.total,
    }]
  }
  return out
}

export function buildI1SoeSubTableData(state: I1SoeSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const movementRows: Record<string, unknown>[] = []
  for (const flat of flattenI1SoeMovement(state.layers)) {
    const meta = I1_SOE_LAYER_META[flat.layer]
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
    [I1_SOE_SUBTABLE.movement]: movementRows,
    _note_texts: [
      { section: 'soe-indefinite', text: state.noteIndefinite || '' },
      { section: 'soe-mortgage', text: state.noteMortgage || '' },
      { section: 'soe-valuation', text: state.noteValuation || '' },
      { section: 'soe-impairment', text: state.noteImpairment || '' },
      { section: 'soe-not-ready', text: state.noteNotReady || '' },
      { section: 'soe-sale', text: state.noteSale || '' },
      { section: 'soe-title', text: state.noteTitle || '' },
      { section: 'soe-amort-alloc', text: state.amortAlloc ? formatAmortAllocNote(state.amortAlloc) : '' },
    ] as unknown as Record<string, unknown>[],
  }
}

export function buildI1ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: I1ListedSyncSnapshot,
): I1SyncFromWorkpaperPayload[] {
  const variant: I1DisclosureVariant = 'listed'
  if (!isI1DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I1_DISCLOSURE_SHEET_NAME.listed,
    section_id: I1_NOTE_SECTION.listed,
    current_standard: resolveI1CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI1ListedSubTableData(state),
  }]
}

export function buildI1SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: I1SoeSyncSnapshot,
): I1SyncFromWorkpaperPayload[] {
  const variant: I1DisclosureVariant = 'soe'
  if (!isI1DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I1_DISCLOSURE_SHEET_NAME.soe,
    section_id: I1_NOTE_SECTION.soe,
    current_standard: resolveI1CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI1SoeSubTableData(state),
  }]
}
