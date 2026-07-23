/**
 * I2 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、27
 * - 国企：note_template_soe §八、28
 */
import {
  I2_DISCLOSURE_SHEET_NAME,
  I2_LISTED_SUBTABLE,
  I2_NOTE_SECTION,
  I2_SOE_SUBTABLE,
  isI2DisclosureApplicable,
  resolveI2CurrentStandard,
  type I2DisclosureVariant,
} from './i2NoteSectionMap'
import {
  type I2NatureRow,
  type I2MovementRow,
  type I2ImportantCapRow,
  type I2ImpairmentRow,
  summarizeNature,
  summarizeMovement,
  recalcMovementEnd,
} from './i2DisclosureModel'
import type { ColumnDef } from './disclosureColumnDefs'

export interface I2SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 I2TabDisclosure el-table-column（两级表头扁平合并） */
  columns?: Record<string, ColumnDef[]>
}

// 研发投入按性质表（本期/上期 × 费用化/资本化），label 取自 I2TabDisclosureListed
const I2_NATURE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: '本期费用化金额', label: '本期费用化', format: 'amount' },
  { key: '本期资本化金额', label: '本期资本化', format: 'amount' },
  { key: '上期费用化金额', label: '上期费用化', format: 'amount' },
  { key: '上期资本化金额', label: '上期资本化', format: 'amount' },
]

// 上市开发支出滚动表（两级表头扁平合并）
const I2_LISTED_MOVEMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: '期初余额', label: '期初数', format: 'amount' },
  { key: '本期增加_内部开发支出', label: '本期增加-内部开发', format: 'amount' },
  { key: '本期增加_其他', label: '本期增加-其他', format: 'amount' },
  { key: '本期减少_确认为无形资产', label: '本期减少-转无形资产', format: 'amount' },
  { key: '本期减少_计入当期损益', label: '本期减少-计入损益', format: 'amount' },
  { key: '期末余额', label: '期末数', format: 'amount' },
  { key: '资本化开始时点', label: '资本化开始时点' },
  { key: '资本化的具体依据', label: '资本化依据' },
  { key: '截至期末的研发进度', label: '研发进度' },
]

// 重要资本化研发项目表
const I2_IMPORTANT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: '研发进度', label: '研发进度' },
  { key: '预计完成时间', label: '预计完成时间' },
  { key: '预计经济利益产生方式', label: '预计经济利益产生方式' },
  { key: '开始资本化的时点', label: '开始资本化时点' },
  { key: '开始资本化的具体依据', label: '资本化具体依据' },
]

// 减值准备分项表
const I2_IMPAIRMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: '期初余额', label: '期初余额', format: 'amount' },
  { key: '本期计提', label: '本期计提', format: 'amount' },
  { key: '本期减少', label: '本期减少', format: 'amount' },
  { key: '期末余额', label: '期末余额', format: 'amount' },
]

// 国企开发支出滚动表（本期减少三分列：转无形资产/转入当期损益/其他）
const I2_SOE_MOVEMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: '期初余额', label: '期初数', format: 'amount' },
  { key: '本期增加_内部开发支出', label: '本期增加-内部开发', format: 'amount' },
  { key: '本期增加_其他', label: '本期增加-其他', format: 'amount' },
  { key: '本期减少_确认为无形资产', label: '本期减少-转无形资产', format: 'amount' },
  { key: '本期减少_转入当期损益', label: '本期减少-转入当期损益', format: 'amount' },
  { key: '本期减少_其他', label: '本期减少-其他', format: 'amount' },
  { key: '期末余额', label: '期末数', format: 'amount' },
  { key: '资本化开始时点', label: '资本化开始时点' },
  { key: '资本化的具体依据', label: '资本化依据' },
  { key: '截至期末的研发进度', label: '研发进度' },
]

export interface I2ListedSyncSnapshot {
  natureRows: I2NatureRow[]
  movementRows: I2MovementRow[]
  importantRows: I2ImportantCapRow[]
  impairmentRows: I2ImpairmentRow[]
  noteText: string
  noteCap: string
  noteImpairTest: string
  notePurchased: string
}

export interface I2SoeSyncSnapshot {
  movementRows: I2MovementRow[]
  noteText: string
}

function _hasMovementAmount(r: I2MovementRow): boolean {
  return Math.abs(r.beginBalance) + Math.abs(r.increaseInternal) + Math.abs(r.increaseOther)
    + Math.abs(r.decreaseToIntangible) + Math.abs(r.decreaseToExpense) + Math.abs(r.decreaseOther)
    + Math.abs(r.endBalance) > 0.005
    || !!(r.name && r.name.trim())
}

export function buildI2ListedMovementSubTable(rows: I2MovementRow[]): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.isTotal && _hasMovementAmount(r))
  data.forEach(recalcMovementEnd)
  const mapped = data.map((r) => ({
    label: r.name,
    期初余额: r.beginBalance,
    本期增加_内部开发支出: r.increaseInternal,
    本期增加_其他: r.increaseOther,
    本期减少_确认为无形资产: r.decreaseToIntangible,
    本期减少_计入当期损益: r.decreaseToExpense,
    期末余额: r.endBalance,
    资本化开始时点: r.capStartDate,
    资本化的具体依据: r.capBasis,
    截至期末的研发进度: r.progress,
    row_type: 'data' as const,
  }))
  const sum = summarizeMovement(data)
  return [
    ...mapped,
    {
      label: '合计',
      期初余额: sum.begin,
      本期增加_内部开发支出: sum.increaseInternal,
      本期增加_其他: sum.increaseOther,
      本期减少_确认为无形资产: sum.decreaseToIntangible,
      本期减少_计入当期损益: sum.decreaseToExpense,
      期末余额: sum.end,
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

export function buildI2ListedNatureSubTable(rows: I2NatureRow[]): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.isTotal)
  const mapped = data
    .filter((r) => r.name || r.currentExpensed || r.currentCapitalized || r.priorExpensed || r.priorCapitalized)
    .map((r) => ({
      label: r.name,
      本期费用化金额: r.currentExpensed,
      本期资本化金额: r.currentCapitalized,
      上期费用化金额: r.priorExpensed,
      上期资本化金额: r.priorCapitalized,
      row_type: 'data' as const,
    }))
  const sum = summarizeNature(data)
  return [
    ...mapped,
    {
      label: '合计',
      本期费用化金额: sum.currentExpensed,
      本期资本化金额: sum.currentCapitalized,
      上期费用化金额: sum.priorExpensed,
      上期资本化金额: sum.priorCapitalized,
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

export function buildI2ImportantSubTable(rows: I2ImportantCapRow[]): Record<string, unknown>[] {
  return rows
    .filter((r) => r.name.trim())
    .map((r) => ({
      label: r.name,
      研发进度: r.progress,
      预计完成时间: r.expectedCompletion,
      预计经济利益产生方式: r.economicBenefit,
      开始资本化的时点: r.capStartDate,
      开始资本化的具体依据: r.capBasis,
      row_type: 'data' as const,
    }))
}

export function buildI2ImpairmentSubTable(rows: I2ImpairmentRow[]): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.isTotal && (r.name || r.beginBalance || r.provision || r.decrease))
  const mapped = data.map((r) => {
    const end = Math.round((r.beginBalance + r.provision - r.decrease) * 100) / 100
    return {
      label: r.name,
      期初余额: r.beginBalance,
      本期计提: r.provision,
      本期减少: r.decrease,
      期末余额: end,
      row_type: 'data' as const,
    }
  })
  const begin = data.reduce((s, r) => s + r.beginBalance, 0)
  const provision = data.reduce((s, r) => s + r.provision, 0)
  const decrease = data.reduce((s, r) => s + r.decrease, 0)
  return [
    ...mapped,
    {
      label: '合计',
      期初余额: begin,
      本期计提: provision,
      本期减少: decrease,
      期末余额: Math.round((begin + provision - decrease) * 100) / 100,
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

export function buildI2SoeMovementSubTable(rows: I2MovementRow[]): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.isTotal && _hasMovementAmount(r))
  data.forEach(recalcMovementEnd)
  const mapped = data.map((r) => ({
    label: r.name,
    期初余额: r.beginBalance,
    本期增加_内部开发支出: r.increaseInternal,
    本期增加_其他: r.increaseOther,
    本期减少_确认为无形资产: r.decreaseToIntangible,
    本期减少_转入当期损益: r.decreaseToExpense,
    本期减少_其他: r.decreaseOther,
    期末余额: r.endBalance,
    资本化开始时点: r.capStartDate,
    资本化的具体依据: r.capBasis,
    截至期末的研发进度: r.progress,
    row_type: 'data' as const,
  }))
  const sum = summarizeMovement(data)
  return [
    ...mapped,
    {
      label: '合计',
      期初余额: sum.begin,
      本期增加_内部开发支出: sum.increaseInternal,
      本期增加_其他: sum.increaseOther,
      本期减少_确认为无形资产: sum.decreaseToIntangible,
      本期减少_转入当期损益: sum.decreaseToExpense,
      本期减少_其他: sum.decreaseOther,
      期末余额: sum.end,
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

export function buildI2ListedSubTableData(snap: I2ListedSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [I2_LISTED_SUBTABLE.nature]: buildI2ListedNatureSubTable(snap.natureRows),
    [I2_LISTED_SUBTABLE.movement]: buildI2ListedMovementSubTable(snap.movementRows),
  }
  const important = buildI2ImportantSubTable(snap.importantRows)
  if (important.length) out[I2_LISTED_SUBTABLE.important] = important
  const impair = buildI2ImpairmentSubTable(snap.impairmentRows)
  if (impair.length > 1) out[I2_LISTED_SUBTABLE.impairment] = impair

  const notes: Array<Record<string, string>> = []
  if (snap.noteText.trim()) notes.push({ section: 'listed-main', text: snap.noteText.trim() })
  if (snap.noteCap.trim()) notes.push({ section: 'listed-cap-important', text: snap.noteCap.trim() })
  if (snap.noteImpairTest.trim()) notes.push({ section: 'listed-impair-test', text: snap.noteImpairTest.trim() })
  if (snap.notePurchased.trim()) notes.push({ section: 'listed-purchased-rd', text: snap.notePurchased.trim() })
  if (notes.length) out._note_texts = notes as unknown as Record<string, unknown>[]
  return out
}

export function buildI2SoeSubTableData(snap: I2SoeSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [I2_SOE_SUBTABLE.movement]: buildI2SoeMovementSubTable(snap.movementRows),
  }
  if (snap.noteText.trim()) {
    out._note_texts = [{ section: 'soe-main', text: snap.noteText.trim() }] as unknown as Record<string, unknown>[]
  }
  return out
}

export function buildI2ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: I2ListedSyncSnapshot,
): I2SyncFromWorkpaperPayload[] {
  if (!isI2DisclosureApplicable('listed', applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I2_DISCLOSURE_SHEET_NAME.listed,
    section_id: I2_NOTE_SECTION.listed,
    current_standard: resolveI2CurrentStandard('listed', applicableStandards),
    sub_table_data: buildI2ListedSubTableData(snap),
    columns: {
      [I2_LISTED_SUBTABLE.nature]: I2_NATURE_COLUMNS,
      [I2_LISTED_SUBTABLE.movement]: I2_LISTED_MOVEMENT_COLUMNS,
      [I2_LISTED_SUBTABLE.important]: I2_IMPORTANT_COLUMNS,
      [I2_LISTED_SUBTABLE.impairment]: I2_IMPAIRMENT_COLUMNS,
    },
  }]
}

export function buildI2SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: I2SoeSyncSnapshot,
): I2SyncFromWorkpaperPayload[] {
  if (!isI2DisclosureApplicable('soe', applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: I2_DISCLOSURE_SHEET_NAME.soe,
    section_id: I2_NOTE_SECTION.soe,
    current_standard: resolveI2CurrentStandard('soe', applicableStandards),
    sub_table_data: buildI2SoeSubTableData(snap),
    columns: { [I2_SOE_SUBTABLE.movement]: I2_SOE_MOVEMENT_COLUMNS },
  }]
}
