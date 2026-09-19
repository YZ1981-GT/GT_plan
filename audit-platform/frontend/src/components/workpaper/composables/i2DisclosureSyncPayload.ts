/**
 * I2 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、27
 * - 国企：note_template_soe §八、28
 */
import {
  I2_DISCLOSURE_SHEET_NAME,
  I2_LEGACY_OBSOLETE_TABLES,
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

/**
 * 研发支出按费用性质表 —— **两级表头**（源模板 `附注披露（上市公司）` B7:C7「本期发生额」/
 * D7:E7「上期发生额」，B8~E8 各为「费用化金额」「资本化金额」；A7:A8 合并为「项  目」）。
 *
 * 🔴 禁止标 `flat: true`：`note_sub_table_projector._extract_column_groups` 的规则是
 * 「任一列 flat=True → 整表返回 []」，push 路径的两级表头会被静默压扁成单级
 * （命中「底稿→附注同步不得压扁列结构」铁律，与 D2 把 6 列压成 2 列同型）。
 *
 * key / label / group 与 `note_template_listed.json` §五、27「研发支出」逐字同构
 * （seed 侧真源 = `backend/scripts/fix/fix_note_i_cycle_structure.py:_I2_NATURE_COLUMNS`），
 * 保证 seed 快照与 push 快照落到同一列结构。
 */
const I2_NATURE_COLUMNS: ColumnDef[] = [
  { key: '项目', label: '项  目', is_label: true },
  { key: 'cur_expense', label: '费用化金额', group: '本期发生额', format: 'amount' },
  { key: 'cur_capitalize', label: '资本化金额', group: '本期发生额', format: 'amount' },
  { key: 'prior_expense', label: '费用化金额', group: '上期发生额', format: 'amount' },
  { key: 'prior_capitalize', label: '资本化金额', group: '上期发生额', format: 'amount' },
]

// 上市开发支出滚动表（两级表头扁平合并）
const I2_LISTED_MOVEMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true },
  { key: '期初余额', label: '期初数', format: 'amount' },
  { key: '本期增加_内部开发支出', label: '内部开发支出', group: '本期增加', format: 'amount' },
  { key: '本期增加_其他', label: '其他增加', group: '本期增加', format: 'amount' },
  { key: '本期减少_确认为无形资产', label: '确认为无形资产', group: '本期减少', format: 'amount' },
  { key: '本期减少_计入当期损益', label: '计入当期损益', group: '本期减少', format: 'amount' },
  { key: '期末余额', label: '期末数', format: 'amount' },
  { key: '资本化开始时点', label: '资本化开始时点' },
  { key: '资本化的具体依据', label: '资本化依据' },
  { key: '截至期末的研发进度', label: '研发进度' },
]

// 重要资本化研发项目表
const I2_IMPORTANT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: '研发进度', label: '研发进度', flat: true },
  { key: '预计完成时间', label: '预计完成时间', flat: true },
  { key: '预计经济利益产生方式', label: '预计经济利益产生方式', flat: true },
  { key: '开始资本化的时点', label: '开始资本化时点', flat: true },
  { key: '开始资本化的具体依据', label: '资本化具体依据', flat: true },
]

// 减值准备分项表
const I2_IMPAIRMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: '期初余额', label: '期初余额', format: 'amount', flat: true },
  { key: '本期计提', label: '本期计提', format: 'amount', flat: true },
  { key: '本期减少', label: '本期减少', format: 'amount', flat: true },
  { key: '期末余额', label: '期末余额', format: 'amount', flat: true },
]

// 开发支出（续：资本化情况）— 4 列 flat（对齐 fix_note_i_cycle_structure.py）
const I2_CAP_DETAIL_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: '资本化开始时点', label: '资本化开始时点', flat: true },
  { key: '资本化的具体依据', label: '资本化的具体依据', flat: true },
  { key: '截至期末的研发进度', label: '截至期末的研发进度', flat: true },
]

// 国企开发支出滚动表（本期减少三分列：转无形资产/转入当期损益/其他）
const I2_SOE_MOVEMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true },
  { key: '期初余额', label: '期初数', format: 'amount' },
  { key: '本期增加_内部开发支出', label: '内部开发支出', group: '本期增加', format: 'amount' },
  { key: '本期增加_其他', label: '其他增加', group: '本期增加', format: 'amount' },
  { key: '本期减少_确认为无形资产', label: '确认为无形资产', group: '本期减少', format: 'amount' },
  { key: '本期减少_转入当期损益', label: '转入当期损益', group: '本期减少', format: 'amount' },
  { key: '本期减少_其他', label: '其他减少', group: '本期减少', format: 'amount' },
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

/**
 * 研发支出（按费用性质）子表。
 *
 * 🔴 行字段名必须与 `I2_NATURE_COLUMNS[].key` 逐字一致 —— 投影器按
 * `r.get(column.key)` 取值，改一侧不改另一侧 ⇒ 整表值全空（表头在、数据没了）。
 * 标签列键取 `项目`（模板同名），并同时写通用 `label` 供合计/兜底路径使用。
 */
export function buildI2ListedNatureSubTable(rows: I2NatureRow[]): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.isTotal)
  const mapped = data
    .filter((r) => r.name || r.currentExpensed || r.currentCapitalized || r.priorExpensed || r.priorCapitalized)
    .map((r) => ({
      项目: r.name,
      label: r.name,
      cur_expense: r.currentExpensed,
      cur_capitalize: r.currentCapitalized,
      prior_expense: r.priorExpensed,
      prior_capitalize: r.priorCapitalized,
      row_type: 'data' as const,
    }))
  const sum = summarizeNature(data)
  return [
    ...mapped,
    {
      项目: '合计',
      label: '合计',
      cur_expense: sum.currentExpensed,
      cur_capitalize: sum.currentCapitalized,
      prior_expense: sum.priorExpensed,
      prior_capitalize: sum.priorCapitalized,
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
  // 续：资本化情况（从 movementRows 提取有资本化信息的项目）
  const capDetailRows = (snap.movementRows || [])
    .filter((r) => !r.isTotal && (r.capStartDate || r.capBasis || r.progress))
    .map((r) => ({
      label: r.name || '（未命名）',
      资本化开始时点: r.capStartDate || '',
      资本化的具体依据: r.capBasis || '',
      截至期末的研发进度: r.progress || '',
    }))
  if (capDetailRows.length) out[I2_LISTED_SUBTABLE.capDetail] = capDetailRows

  const important = buildI2ImportantSubTable(snap.importantRows)
  if (important.length) out[I2_LISTED_SUBTABLE.important] = important
  const impair = buildI2ImpairmentSubTable(snap.impairmentRows)
  if (impair.length > 1) out[I2_LISTED_SUBTABLE.impairment] = impair

  const notes: Array<Record<string, string>> = [
    { section: 'listed-main', title: '开发支出说明', text: (snap.noteText || '').trim() },
    { section: 'listed-cap-important', title: '重要资本化研发项目说明', text: (snap.noteCap || '').trim() },
    { section: 'listed-impair-test', title: '开发支出减值测试', text: (snap.noteImpairTest || '').trim() },
    { section: 'listed-purchased-rd', title: '购买式研发说明', text: (snap.notePurchased || '').trim() },
  ].filter((n) => n.text)
  if (notes.length) out._note_texts = notes as unknown as Record<string, unknown>[]
  return out
}

export function buildI2SoeSubTableData(snap: I2SoeSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [I2_SOE_SUBTABLE.movement]: buildI2SoeMovementSubTable(snap.movementRows),
  }
  const noteText = (snap.noteText || '').trim()
  if (noteText) {
    out._note_texts = [{ section: 'soe-main', title: '开发支出说明', text: noteText }] as unknown as Record<string, unknown>[]
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
      [I2_LISTED_SUBTABLE.capDetail]: I2_CAP_DETAIL_COLUMNS,
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
