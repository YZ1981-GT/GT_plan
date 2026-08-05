/**
 * l4NoteSectionMap — L4 应付债券 披露表↔附注模块 联动映射
 *
 * 权威来源 note_template_variant_matrix.json · ying_fu_zhai_quan：
 *   listed_standalone = 五、46
 *   soe_standalone    = 八、50
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R9
 */
import type { ColumnDef } from './disclosureColumnDefs'

export const L4_NOTE_SECTION = {
  listed: '五、46',
  soe: '八、50',
} as const

export const L4_WITHIN1Y_NOTE_SECTION = { soe: '八、46' } as const

export const L4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息核对（上市公司）',
  soe: '附注披露信息核对（国企）',
} as const

// ── 上市版子表名（必须与附注模板 tables[].name 逐字一致）──────────────────

export const L4_LISTED_SUBTABLE = {
  main: '应付债券',
  movement: '应付债券增减变动',
  within1y: '一年内到期的应付债券',
  overdue: '已到期未偿付的应付债券',
  otherFinInstrument: '划分为金融负债的其他金融工具',
} as const

export const L4_SOE_SUBTABLE = {
  main: '应付债券',
  movement: '应付债券增减变动',
} as const

// ── 列定义 ──────────────────────────────────────────────────────────────────

/** 上市主表：面值/利息调整/应计利息/合计 × 期末/上年年末 → 两级表头 */
function buildListedMainColumns(): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'endFaceValue', label: '面值', format: 'amount', group: '期末余额' },
    { key: 'endInterestAdj', label: '利息调整', format: 'amount', group: '期末余额' },
    { key: 'endAccruedInterest', label: '应计利息', format: 'amount', group: '期末余额' },
    { key: 'endTotal', label: '合计', format: 'amount', group: '期末余额' },
    { key: 'priorFaceValue', label: '面值', format: 'amount', group: '上年年末余额' },
    { key: 'priorInterestAdj', label: '利息调整', format: 'amount', group: '上年年末余额' },
    { key: 'priorAccruedInterest', label: '应计利息', format: 'amount', group: '上年年末余额' },
    { key: 'priorTotal', label: '合计', format: 'amount', group: '上年年末余额' },
  ]
}

/** 增减变动表（两版共用）：面值/利息调整/应计利息 × 期初/增加/减少/期末 → 两级 */
function buildMovementColumns(): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'beginFaceValue', label: '面值', format: 'amount', group: '期初余额' },
    { key: 'beginInterestAdj', label: '利息调整', format: 'amount', group: '期初余额' },
    { key: 'beginAccruedInterest', label: '应计利息', format: 'amount', group: '期初余额' },
    { key: 'increaseFaceValue', label: '面值', format: 'amount', group: '本期增加' },
    { key: 'increaseInterestAdj', label: '利息调整', format: 'amount', group: '本期增加' },
    { key: 'increaseAccruedInterest', label: '应计利息', format: 'amount', group: '本期增加' },
    { key: 'decreaseFaceValue', label: '面值', format: 'amount', group: '本期减少' },
    { key: 'decreaseInterestAdj', label: '利息调整', format: 'amount', group: '本期减少' },
    { key: 'decreaseAccruedInterest', label: '应计利息', format: 'amount', group: '本期减少' },
    { key: 'endFaceValue', label: '面值', format: 'amount', group: '期末余额' },
    { key: 'endInterestAdj', label: '利息调整', format: 'amount', group: '期末余额' },
    { key: 'endAccruedInterest', label: '应计利息', format: 'amount', group: '期末余额' },
  ]
}

/** 一年内到期的应付债券（单级 flat） */
function buildWithin1yColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'endAmount', label: '期末余额', format: 'amount' },
    { key: 'priorAmount', label: variant === 'listed' ? '上年年末余额' : '期初余额', format: 'amount' },
  ]
}

/** 已到期未偿付（上市专属，flat） */
function buildOverdueColumns(): ColumnDef[] {
  return [
    { key: 'bondName', label: '债券名称', is_label: true, flat: true },
    { key: 'dueDate', label: '到期日', format: 'text' },
    { key: 'amount', label: '未偿付金额', format: 'amount' },
  ]
}

/** 国企主表（单级 flat） */
function buildSoeMainColumns(): ColumnDef[] {
  return [
    { key: 'bondName', label: '债券名称', is_label: true, flat: true },
    { key: 'faceValue', label: '面值', format: 'amount' },
    { key: 'issueDate', label: '发行日期', format: 'text' },
    { key: 'term', label: '债券期限', format: 'text' },
    { key: 'balance', label: '债券余额', format: 'amount' },
    { key: 'accruedInterest', label: '应付利息', format: 'amount' },
    { key: 'rate', label: '利率', format: 'percent' },
  ]
}

// ── 导出列构建器 ────────────────────────────────────────────────────────────

export function buildL4ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [L4_LISTED_SUBTABLE.main]: buildListedMainColumns(),
    [L4_LISTED_SUBTABLE.movement]: buildMovementColumns(),
    [L4_LISTED_SUBTABLE.within1y]: buildWithin1yColumns('listed'),
    [L4_LISTED_SUBTABLE.overdue]: buildOverdueColumns(),
  }
}

export function buildL4SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [L4_SOE_SUBTABLE.main]: buildSoeMainColumns(),
    [L4_SOE_SUBTABLE.movement]: buildMovementColumns(),
  }
}

// ── Payload 构建 ─────────────────────────────────────────────────────────────

export type L4Variant = 'listed' | 'soe'

export interface L4SyncPayloadOptions {
  variant: L4Variant
  wpId: string
  projectId: string
  applicableStandards?: string[]
  /** 上市主表行 */
  mainRows?: Array<Record<string, unknown>>
  /** 增减变动表行 */
  movementRows?: Array<Record<string, unknown>>
  /** 一年内到期行 */
  within1yRows?: Array<Record<string, unknown>>
  /** 已到期未偿付行（上市） */
  overdueRows?: Array<Record<string, unknown>>
  /** 说明文本 */
  noteTexts?: Array<{ section: string; title: string; text: string }>
}

export function buildL4SyncPayload(opts: L4SyncPayloadOptions) {
  const { variant, mainRows, movementRows, within1yRows, overdueRows, noteTexts } = opts

  const sub_table_data: Record<string, unknown[]> = {}
  const columns = variant === 'listed' ? buildL4ListedColumns() : buildL4SoeColumns()

  if (variant === 'listed') {
    if (mainRows?.length) sub_table_data[L4_LISTED_SUBTABLE.main] = mainRows
    if (movementRows?.length) sub_table_data[L4_LISTED_SUBTABLE.movement] = movementRows
    if (within1yRows?.length) sub_table_data[L4_LISTED_SUBTABLE.within1y] = within1yRows
    if (overdueRows?.length) sub_table_data[L4_LISTED_SUBTABLE.overdue] = overdueRows
  } else {
    if (mainRows?.length) sub_table_data[L4_SOE_SUBTABLE.main] = mainRows
    if (movementRows?.length) sub_table_data[L4_SOE_SUBTABLE.movement] = movementRows
  }

  if (noteTexts?.length) {
    (sub_table_data as any)._note_texts = noteTexts
  }

  return {
    note_section: L4_NOTE_SECTION[variant],
    sheet_name: L4_DISCLOSURE_SHEET_NAME[variant],
    sub_table_data,
    _sub_table_columns: columns,
  }
}
