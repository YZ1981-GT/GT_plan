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
import { i1CategoryColumnKey } from './i1CategoryScope'

/**
 * 类别列的稳定 key（`{slot.key}_{seq}`，Task 12 / Property 20）。
 *
 * 🔴 禁用中文 label 作 key —— 两个类别改成同名 label 会撞键、列与数据串台（H7 已踩）。
 * `buildI1ListedColumns`（列头）与 `buildI1ListedSubTableData`（行字段）必须用**同一** key
 * 生成规则，否则 note 投影器 `r.get(column.key)` 恒 None、整表渲染空白。
 * 两者都按 `cats` 同序迭代取 `idx`，故同一次推送内列与行逐一对齐。
 */
function i1CatColKey(c: { key: string; label: string }, idx: number): string {
  return i1CategoryColumnKey({ key: c.key, label: c.label, seq: idx + 1, removable: c.key !== 'other' })
}

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
 * 上市变动表列头随类别动态（key=稳定 `{slot.key}_{seq}`、label=类别中文名 + 合计），
 * 列 key 逐字对齐 buildI1ListedSubTableData 行字段。附属子表列头静态源对齐。
 */
export function buildI1ListedColumns(state: I1ListedSyncSnapshot): Record<string, ColumnDef[]> {
  const cats = state.categories || []
  // 🔴 `flat: true` 必须声明：本表是「项目 + N 个类别 + 合计」的单级表头列转置表，
  // 不标 flat 时后端 `_infer_groups_from_headers` 会对 ≥4 列共享前缀的 headers 反猜父表头
  // （note_template_listed §五、26「无形资产情况」的 columns 侧同样标 flat=true，两侧同构）。
  const movement: ColumnDef[] = [
    { key: 'label', label: '项目', is_label: true, flat: true },
    ...cats.map((c, idx) => ({ key: i1CatColKey(c, idx), label: c.label, format: 'amount' as const })),
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

/**
 * 国企变动表列头（项目/期初余额/本期增加/本期减少/期末余额），键对齐 flattenI1SoeMovement 输出。
 *
 * 🔴 与 `note_template_soe` §八、27 逐字同构（Task 15）：
 * label 用全角双空格「项  目」（= 模板 `headers[0]`，P5 判据），并标 `flat: true`（P3 判据）。
 * 此前这里写 `label: '项目'` 且无 `flat`，但契约 spec 传的是它自己手写的一份副本
 * ⇒ P3/P5 对**生产代码**从未真正生效（假绿）。现由 spec 直接消费本常量。
 */
export const I1_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  [I1_SOE_SUBTABLE.movement]: [
    { key: 'label', label: '项  目', is_label: true, flat: true },
    { key: 'begin', label: '期初余额', format: 'amount', flat: true },
    { key: 'increase', label: '本期增加', format: 'amount', flat: true },
    { key: 'decrease', label: '本期减少', format: 'amount', flat: true },
    { key: 'end', label: '期末余额', format: 'amount', flat: true },
  ],
  // 数据资源子表：国企版模板同样有此表（§八、27），列集与上市版一致。
  // 载荷当前不推该表（`buildI1SoeSubTableData` 只产 movement），但列头声明保留
  // 与模板同构 ⇒ 将来接推送时不必再补，且契约 P3/P5 立即覆盖。
  [I1_SOE_SUBTABLE.dataResource]: [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: '外购的数据资源无形资产', label: '外购的数据资源无形资产', format: 'amount', flat: true },
    { key: '自行开发的数据资源无形资产', label: '自行开发的数据资源无形资产', format: 'amount', flat: true },
    { key: '其他方式取得的数据资源无形资产', label: '其他方式取得的数据资源无形资产', format: 'amount', flat: true },
    { key: '合计', label: '合计', format: 'amount', flat: true },
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
    cats.forEach((c, idx) => {
      row[i1CatColKey(c, idx)] = i1ListedCellValue(state.movement, def, c.key)
    })
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
