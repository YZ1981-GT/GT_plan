/**
 * I1 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、26
 * - 国企：note_template_soe §八、27
 */
import {
  I1_DISCLOSURE_SHEET_NAME,
  I1_LEGACY_OBSOLETE_TABLES,
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
import type { ColumnDef } from './disclosureColumnDefs'

export interface I1SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 note_template §五、26/§八、27 无形资产表 */
  columns?: Record<string, ColumnDef[]>
}

/**
 * 上市变动表列头随类别动态（key=类别 label + 合计），逐字对齐 buildI1ListedSubTableData 行键。
 * 附属子表列头静态源对齐。
 */
export function buildI1ListedColumns(state: I1ListedSyncSnapshot): Record<string, ColumnDef[]> {
  const cats = state.categories || []
  const movement: ColumnDef[] = [
    { key: 'label', label: '项目', is_label: true },
    ...cats.map((c) => ({ key: c.label, label: c.label, format: 'amount' as const })),
    { key: '合计', label: '合计', format: 'amount' },
  ]
  return {
    [I1_LISTED_SUBTABLE.movement]: movement,
    [I1_LISTED_SUBTABLE.important]: [
      { key: 'label', label: '项  目', is_label: true, flat: true },
      { key: '账面价值', label: '账面价值', format: 'amount', flat: true },
      { key: '剩余摊销期限', label: '剩余摊销期限', flat: true },
    ],
    [I1_LISTED_SUBTABLE.titleCert]: [
      { key: 'label', label: '项  目', is_label: true, flat: true },
      { key: '账面价值', label: '账面价值', format: 'amount', flat: true },
      { key: '未办妥产权证书原因', label: '未办妥产权证书原因', flat: true },
    ],
    [I1_LISTED_SUBTABLE.dataResource]: [
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: '外购的数据资源无形资产', label: '外购的数据资源无形资产', format: 'amount', flat: true },
      { key: '自行开发的数据资源无形资产', label: '自行开发的数据资源无形资产', format: 'amount', flat: true },
      { key: '其他方式取得的数据资源无形资产', label: '其他方式取得的数据资源无形资产', format: 'amount', flat: true },
      { key: '合计', label: '合计', format: 'amount', flat: true },
    ],
    '本期摊销费用归属': [
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: '生产成本', label: '生产成本', format: 'amount', flat: true },
      { key: '制造费用', label: '制造费用', format: 'amount', flat: true },
      { key: '销售费用', label: '销售费用', format: 'amount', flat: true },
      { key: '管理费用', label: '管理费用', format: 'amount', flat: true },
      { key: '研发费用', label: '研发费用', format: 'amount', flat: true },
      { key: '其他', label: '其他', format: 'amount', flat: true },
      { key: '合计', label: '合计', format: 'amount', flat: true },
    ],
  }
}

/** 国企变动表列头（项目/期初余额/本期增加/本期减少/期末余额），键对齐 flattenI1SoeMovement 输出 */
const I1_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  [I1_SOE_SUBTABLE.movement]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'begin', label: '期初余额', format: 'amount' },
    { key: 'increase', label: '本期增加', format: 'amount' },
    { key: 'decrease', label: '本期减少', format: 'amount' },
    { key: 'end', label: '期末余额', format: 'amount' },
  ],
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
      { section: 'listed-rd-ratio', title: '研发投入比例说明', text: state.noteRdRatio || '' },
      { section: 'listed-indefinite', title: '使用寿命不确定的无形资产说明', text: state.noteIndefinite || '' },
      { section: 'listed-mortgage', title: '用于担保的无形资产', text: state.noteMortgage || '' },
      { section: 'listed-impairment', title: '无形资产减值说明', text: state.noteImpairment || '' },
      { section: 'listed-sale', title: '通过政府补助取得的土地使用权', text: state.noteSale || '' },
      { section: 'listed-important', title: '重要单项无形资产说明', text: state.noteImportant || '' },
      { section: 'listed-data-resource', title: '数据资源说明', text: state.noteDataResource || '' },
      { section: 'listed-amort-alloc', title: '本期摊销费用归属', text: state.amortAlloc ? formatAmortAllocNote(state.amortAlloc) : '' },
    ].filter((n) => (n.text || '').trim()) as unknown as Record<string, unknown>[],
  }
  if (importantRows.length) {
    out[I1_LISTED_SUBTABLE.important] = importantRows
  }
  if (titleRows.length) {
    out[I1_LISTED_SUBTABLE.titleCert] = titleRows
  }
  if (state.dataResource) {
    const dr = { ...state.dataResource, note: state.noteDataResource || state.dataResource.note || '' }
    const hasDr = Math.abs(Number(dr.costBegin) || 0)
      + Math.abs(Number(dr.costIncPurchase) || 0)
      + Math.abs(Number(dr.costIncRd) || 0)
      + Math.abs(Number(dr.costIncOther) || 0) > 0.005
    if (hasDr) {
      out[I1_LISTED_SUBTABLE.dataResource] = buildDataResourceSubTableRows(dr)
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
      { section: 'soe-indefinite', title: '使用寿命不确定的无形资产说明', text: state.noteIndefinite || '' },
      { section: 'soe-mortgage', title: '用于担保的无形资产', text: state.noteMortgage || '' },
      { section: 'soe-valuation', title: '无形资产计量方法', text: state.noteValuation || '' },
      { section: 'soe-impairment', title: '无形资产减值说明', text: state.noteImpairment || '' },
      { section: 'soe-not-ready', title: '尚未达到可使用状态的无形资产', text: state.noteNotReady || '' },
      { section: 'soe-sale', title: '通过政府补助取得的土地使用权', text: state.noteSale || '' },
      { section: 'soe-title', title: '未办妥产权证书的土地使用权', text: state.noteTitle || '' },
      { section: 'soe-amort-alloc', title: '本期摊销费用归属', text: state.amortAlloc ? formatAmortAllocNote(state.amortAlloc) : '' },
    ].filter((n) => (n.text || '').trim()) as unknown as Record<string, unknown>[],
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
    columns: buildI1ListedColumns(state),
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
    columns: I1_SOE_COLUMNS,
  }]
}
