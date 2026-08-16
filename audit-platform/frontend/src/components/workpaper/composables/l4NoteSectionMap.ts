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

export const L4_WITHIN1Y_NOTE_SECTION = {
  listed: '五、43',
  soe: '八、46',
} as const

export const L4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息核对（上市公司）',
  soe: '附注披露信息核对（国企）',
} as const

// ── 上市版子表名（必须与附注模板 tables[].name 逐字一致）──────────────────
// 🔴 2026-08-15 校正（spec l-cycle-…completion R5.11~5.15）：
//    4 处与模板不一致已修正 + 删 overdue（模板不存在）+ 新增 continued/instrumentMovement。

export const L4_LISTED_SUBTABLE = {
  main: '应付债券',
  movement: '应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）',
  continued: '应付债券（续）',
  otherFinInstrument: '（3）划分为金融负债的其他金融工具',
  instrumentMovement: '期末发行在外的优先股、永续债等其他金融工具变动情况',
} as const

export const L4_SOE_SUBTABLE = {
  main: '应付债券',
  movement: '应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）',
} as const

// ── 一年内到期子表名（五、43 / 八、46，两版不同构禁共用）────────────────────

export const L4_WITHIN1Y_LISTED_SUBTABLE = {
  bond: '一年内到期的应付债券',
  bondCont: '一年内到期的应付债券（续）',
} as const

export const L4_WITHIN1Y_SOE_SUBTABLE = {
  bond: '（2）一年内到期的应付债券',
  bondCont: '一年内到期的应付债券',
} as const

/**
 * 旧表名登记表——首次推送时经 `_removed_table_keys` 与本次推送键求差集后发送。
 * 每条带理由，防「登记表本身过期」的假绿。
 */
export const L4_LEGACY_OBSOLETE_TABLES: ReadonlyArray<{ name: string; reason: string }> = [
  { name: '应付债券增减变动', reason: '模板真实表名含"的…（不包括…）"整段，旧名是截断版' },
  { name: '划分为金融负债的其他金融工具', reason: '模板真实表名带（3）序号前缀' },
  { name: '已到期未偿付的应付债券', reason: '两份附注模板（五、46/八、50）均无此表名，源 xlsx 亦无' },
]

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
    [L4_LISTED_SUBTABLE.continued]: buildWithin1yColumns('listed'),  // 续表结构同一年内到期
    [L4_LISTED_SUBTABLE.otherFinInstrument]: buildListedMainColumns(),  // 条件表，复用主表结构
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
  /** 说明文本 */
  noteTexts?: Array<{ section: string; title: string; text: string }>
}

export function buildL4SyncPayload(opts: L4SyncPayloadOptions) {
  const { variant, mainRows, movementRows, within1yRows, noteTexts } = opts

  const sub_table_data: Record<string, unknown[]> = {}
  const columns = variant === 'listed' ? buildL4ListedColumns() : buildL4SoeColumns()

  if (variant === 'listed') {
    if (mainRows?.length) sub_table_data[L4_LISTED_SUBTABLE.main] = mainRows
    if (movementRows?.length) sub_table_data[L4_LISTED_SUBTABLE.movement] = movementRows
  } else {
    if (mainRows?.length) sub_table_data[L4_SOE_SUBTABLE.main] = mainRows
    if (movementRows?.length) sub_table_data[L4_SOE_SUBTABLE.movement] = movementRows
  }

  if (noteTexts?.length) {
    (sub_table_data as any)._note_texts = noteTexts
  }

  // 旧表名清理：首次推送时把遗留的旧表名发 _removed_table_keys（与本次推送键求差集）
  const currentKeys = new Set(Object.keys(sub_table_data))
  const removedKeys = L4_LEGACY_OBSOLETE_TABLES
    .map((t) => t.name)
    .filter((name) => !currentKeys.has(name))
  if (removedKeys.length) {
    (sub_table_data as any)._removed_table_keys = removedKeys
  }

  return {
    note_section: L4_NOTE_SECTION[variant],
    sheet_name: L4_DISCLOSURE_SHEET_NAME[variant],
    sub_table_data,
    _sub_table_columns: columns,
  }
}
