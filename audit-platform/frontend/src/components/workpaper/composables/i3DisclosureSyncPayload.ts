/**
 * I3 商誉披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、28
 * - 国企：note_template_soe §八、29
 */
import {
  I3_DISCLOSURE_SHEET_NAME,
  I3_LISTED_SUBTABLE,
  I3_NOTE_SECTION,
  I3_SOE_SUBTABLE,
  isI3DisclosureApplicable,
  resolveI3CurrentStandard,
  type I3DisclosureVariant,
} from './i3NoteSectionMap'
import type { I3DisclosureMatrixRow, I3DisclosureDynamicRow } from './useI3Disclosure'
import { matrixRowSyncAmounts } from './useI3Disclosure'
import type { ColumnDef } from './disclosureColumnDefs'

export interface I3SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 I3TabDisclosure el-table-column */
  columns?: Record<string, ColumnDef[]>
}

// 商誉账面原值变动表（两级表头：本期增加/本期减少含子列）
const I3_BOOK_VALUE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '被投资单位名称或形成商誉的事项', is_label: true },
  { key: '期初余额', label: '期初余额', format: 'amount' },
  { key: 'inc_merge', label: '企业合并形成', group: '本期增加', format: 'amount' },
  { key: 'inc_jv', label: '取得构成业务的共同经营的利益份额形成', group: '本期增加', format: 'amount' },
  { key: 'inc_other', label: '其他', group: '本期增加', format: 'amount' },
  { key: 'dec_disposal', label: '处置', group: '本期减少', format: 'amount' },
  { key: 'dec_other', label: '其他', group: '本期减少', format: 'amount' },
  { key: '期末余额', label: '期末余额', format: 'amount' },
]

// 商誉减值准备变动表（两级表头）
const I3_IMPAIRMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '被投资单位名称或形成商誉的事项', is_label: true },
  { key: '期初余额', label: '期初余额', format: 'amount' },
  { key: 'inc_provision', label: '计提', group: '本期增加', format: 'amount' },
  { key: 'inc_other', label: '其他增加', group: '本期增加', format: 'amount' },
  { key: 'dec_disposal', label: '处置', group: '本期减少', format: 'amount' },
  { key: 'dec_other', label: '其他减少', group: '本期减少', format: 'amount' },
  { key: '期末余额', label: '期末余额', format: 'amount' },
]

// 国企商誉变动表 flat 5 列（对齐 fix_note_i_cycle_structure.py I3_SOE_TABLE1/2）
const I3_SOE_FLAT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '被投资单位名称或形成商誉的事项', is_label: true, flat: true },
  { key: '期初余额', label: '期初余额', format: 'amount', flat: true },
  { key: '本期增加', label: '本期增加', format: 'amount', flat: true },
  { key: '本期减少', label: '本期减少', format: 'amount', flat: true },
  { key: '期末余额', label: '期末余额', format: 'amount', flat: true },
]

/**
 * 关键假设参数表（资产组/毛利率/增长率/折现率）。
 *
 * 🔴 与 `note_template_listed` §五、28「商誉减值测试关键假设」逐字同构（Task 15）：
 * 三个比率列 `format: 'percent'`（**不是** amount：不套千分符与「元」单位），
 * 并标 `flat: true` —— 此前既无 `flat` 也无 `group`（P3「未表态」），
 * 会让后端 `_infer_groups_from_headers` 对 4 列 headers 反猜父表头。
 */
const I3_ASSUMPTION_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '资产组/业务', is_label: true, flat: true },
  { key: '毛利率', label: '毛利率', format: 'percent', flat: true },
  { key: '增长率', label: '增长率', format: 'percent', flat: true },
  { key: '折现率', label: '折现率', format: 'percent', flat: true },
]

// 业绩承诺表（项目/业绩承诺完成情况/商誉减值金额）
const I3_PERFORMANCE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: '业绩承诺完成情况', label: '业绩承诺完成情况', flat: true },
  { key: '商誉减值金额', label: '商誉减值金额', format: 'amount', flat: true },
]

export interface I3DisclosureSyncSnapshot {
  bookValueRows: I3DisclosureMatrixRow[]
  impairmentRows: I3DisclosureMatrixRow[]
  cguRows?: I3DisclosureDynamicRow[]
  /** 减值测试过程 / 关键假设 / 敏感性 / 结论 / 其他 */
  noteProcess?: string
  noteAssumptions?: string
  noteSensitivity?: string
  noteResult?: string
  noteOther?: string
  noteCgu?: string
  /** 业绩承诺行（上市） */
  performanceRows?: Array<{
    name: string
    commitmentStatus: string
    impairmentAmount: number
  }>
  /** 关键假设参数表（上市） */
  assumptionParams?: Array<{
    label: string
    grossMargin?: string
    growthRate?: string
    discountRate?: string
  }>
}

function _hasAmt(r: I3DisclosureMatrixRow, layer: 'bookValue' | 'impairment'): boolean {
  const a = matrixRowSyncAmounts(r, layer)
  return Math.abs(r.beginBalance) + Math.abs(a.increase) + Math.abs(a.decrease) + Math.abs(a.endBalance) > 0.005
    || !!(r.investee && r.investee.trim() && r.investee !== '合计')
}

export function buildI3MovementSubTable(
  rows: I3DisclosureMatrixRow[],
  layer: 'bookValue' | 'impairment' = 'bookValue',
): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.investee.includes('合计') && _hasAmt(r, layer))
  const mapped = data.map((r) => {
    const a = matrixRowSyncAmounts(r, layer)
    return {
      label: r.investee,
      期初余额: Number(r.beginBalance) || 0,
      本期增加: a.increase,
      本期减少: a.decrease,
      期末余额: a.endBalance,
      row_type: 'data' as const,
    }
  })
  const begin = mapped.reduce((s, r) => s + Number(r.期初余额), 0)
  const inc = mapped.reduce((s, r) => s + Number(r.本期增加), 0)
  const dec = mapped.reduce((s, r) => s + Number(r.本期减少), 0)
  return [
    ...mapped,
    {
      label: '合计',
      期初余额: begin,
      本期增加: inc,
      本期减少: dec,
      期末余额: Math.round((begin + inc - dec) * 100) / 100,
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

function buildAssumptionParamTable(
  params: NonNullable<I3DisclosureSyncSnapshot['assumptionParams']>,
): Record<string, unknown>[] {
  return params
    .filter((p) => p.label.trim())
    .map((p) => ({
      label: p.label,
      毛利率: p.grossMargin || '',
      增长率: p.growthRate || '',
      折现率: p.discountRate || '',
      row_type: 'data' as const,
    }))
}

function buildPerformanceTable(
  rows: NonNullable<I3DisclosureSyncSnapshot['performanceRows']>,
): Record<string, unknown>[] {
  return rows
    .filter((r) => r.name.trim())
    .map((r) => ({
      label: r.name,
      业绩承诺完成情况: r.commitmentStatus || '',
      商誉减值金额: Number(r.impairmentAmount) || 0,
      row_type: 'data' as const,
    }))
}

function buildNoteTexts(snap: I3DisclosureSyncSnapshot, variant: I3DisclosureVariant): Record<string, unknown>[] {
  const notes: Array<{ section: string; text: string }> = []
  const push = (section: string, text?: string) => {
    const t = (text || '').trim()
    if (t) notes.push({ section, text: t })
  }
  if (variant === 'listed') {
    push('listed-cgu', snap.noteCgu)
    push('listed-process', snap.noteProcess)
    push('listed-assumptions', snap.noteAssumptions)
    push('listed-sensitivity', snap.noteSensitivity)
    push('listed-result', snap.noteResult)
    push('listed-other', snap.noteOther)
  } else {
    // 国企：合并为一篇减值测试说明
    const soeMain = [
      snap.noteProcess,
      snap.noteAssumptions,
      snap.noteResult,
      snap.noteOther,
    ].filter((x) => (x || '').trim()).join('\n\n')
    push('soe-impairment-method', soeMain)
    push('soe-cgu', snap.noteCgu)
  }
  return notes as unknown as Record<string, unknown>[]
}

export function buildI3ListedSubTableData(snap: I3DisclosureSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [I3_LISTED_SUBTABLE.bookValue]: buildI3MovementSubTable(snap.bookValueRows, 'bookValue'),
    [I3_LISTED_SUBTABLE.impairment]: buildI3MovementSubTable(snap.impairmentRows, 'impairment'),
  }
  if (snap.assumptionParams?.length) {
    out[I3_LISTED_SUBTABLE.assumptions] = buildAssumptionParamTable(snap.assumptionParams)
  }
  if (snap.performanceRows?.length) {
    out[I3_LISTED_SUBTABLE.performance] = buildPerformanceTable(snap.performanceRows)
  }
  const notes = buildNoteTexts(snap, 'listed')
  if (notes.length) out._note_texts = notes
  return out
}

export function buildI3SoeSubTableData(snap: I3DisclosureSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [I3_SOE_SUBTABLE.bookValue]: buildI3MovementSubTable(snap.bookValueRows, 'bookValue'),
    [I3_SOE_SUBTABLE.impairment]: buildI3MovementSubTable(snap.impairmentRows, 'impairment'),
  }
  const notes = buildNoteTexts(snap, 'soe')
  if (notes.length) out._note_texts = notes
  return out
}

export function buildI3ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: I3DisclosureSyncSnapshot,
): I3SyncFromWorkpaperPayload[] {
  const variant: I3DisclosureVariant = 'listed'
  if (!isI3DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I3_DISCLOSURE_SHEET_NAME.listed,
    section_id: I3_NOTE_SECTION.listed,
    current_standard: resolveI3CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI3ListedSubTableData(snap),
    columns: {
      [I3_LISTED_SUBTABLE.bookValue]: I3_BOOK_VALUE_COLUMNS,
      [I3_LISTED_SUBTABLE.impairment]: I3_IMPAIRMENT_COLUMNS,
      [I3_LISTED_SUBTABLE.assumptions]: I3_ASSUMPTION_COLUMNS,
      [I3_LISTED_SUBTABLE.performance]: I3_PERFORMANCE_COLUMNS,
    },
  }]
}

export function buildI3SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: I3DisclosureSyncSnapshot,
): I3SyncFromWorkpaperPayload[] {
  const variant: I3DisclosureVariant = 'soe'
  if (!isI3DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I3_DISCLOSURE_SHEET_NAME.soe,
    section_id: I3_NOTE_SECTION.soe,
    current_standard: resolveI3CurrentStandard(variant, applicableStandards),
    sub_table_data: buildI3SoeSubTableData(snap),
    columns: {
      [I3_SOE_SUBTABLE.bookValue]: I3_SOE_FLAT_COLUMNS,
      [I3_SOE_SUBTABLE.impairment]: I3_SOE_FLAT_COLUMNS,
    },
  }]
}
