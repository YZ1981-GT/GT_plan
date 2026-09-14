/**
 * G11 附注披露行结构 — 对齐 Excel 上市/国企「投资收益」附注
 */
import {
  G11_ADJUDICATION_ITEMS,
  G11_DISCLOSURE_LISTED_ROWS,
  G11_DISCLOSURE_SOE_ROWS,
  type G11LineDef,
} from './g11Constants'

export interface G11DisclosureRowDef extends G11LineDef {
  /** 主表分项（计入合计）；「其中：」「减：」等展开行不计 */
  isLeaf: boolean
}

/** 与 Excel 表头一致 */
export const G11_DISCLOSURE_COL_LABELS = {
  listed: {
    item: '项目',
    current: '本期发生额',
    prior: '上期发生额',
  },
  soe: {
    item: '项目',
    current: '本期发生额',
    prior: '上期发生额',
  },
} as const

export const G11_DISCLOSURE_TOTAL_LABEL = '合  计'
export const G11_CROSS_TOLERANCE = 0.01

export const G11_ADJ_ROWS_KEY = 'G11-adj-rows'
export const G11_DETAIL_KEY = 'G11-detail-rows'
export const G11_ADJUDICATED_KEY = 'G11-1-adjudicated-amount'
export const G11_DISCLOSURE_LISTED_KEY = 'G11-disclosure-listed'
export const G11_DISCLOSURE_SOE_KEY = 'G11-disclosure-soe'

const ADJ_ROW_KEYS = new Set(G11_ADJUDICATION_ITEMS.map((d) => d.rowKey))

export function isG11DisclosureLeaf(rowKey: string): boolean {
  if (rowKey === 'total') return false
  if (rowKey.startsWith('listed_sub_') || rowKey.startsWith('soe_sub_')) return false
  return ADJ_ROW_KEYS.has(rowKey) || rowKey === 'other'
}

function enrichDefs(defs: G11LineDef[]): G11DisclosureRowDef[] {
  return defs.map((d) => ({
    ...d,
    isLeaf: isG11DisclosureLeaf(d.rowKey),
  }))
}

export const G11_LISTED_DISC_SCHEMA: G11DisclosureRowDef[] = enrichDefs(G11_DISCLOSURE_LISTED_ROWS)
export const G11_SOE_DISC_SCHEMA: G11DisclosureRowDef[] = enrichDefs(G11_DISCLOSURE_SOE_ROWS)

export function g11DisclosureSchema(variant: 'listed' | 'soe'): G11DisclosureRowDef[] {
  return variant === 'listed' ? G11_LISTED_DISC_SCHEMA : G11_SOE_DISC_SCHEMA
}

/** 审定 rowKey → 上市附注主表 rowKey（同键直映；上市未列示的审定行不进主表） */
export const G11_LISTED_MAIN_ROW_KEYS = new Set(
  G11_LISTED_DISC_SCHEMA.filter((r) => r.isLeaf).map((r) => r.rowKey),
)

export const G11_SOE_MAIN_ROW_KEYS = new Set(
  G11_SOE_DISC_SCHEMA.filter((r) => r.isLeaf).map((r) => r.rowKey),
)

/** 上市附注 — 「处置交易性金融资产取得的投资收益」明细（对齐 Excel 注1） */
export type G11TradingDisposeSuffix =
  | 'equity_stock'
  | 'debt_bond'
  | 'derivative_non_hedge'
  | 'derivative_hedge'
  | 'other'

export const G11_TRADING_DISPOSE_SUFFIXES: G11TradingDisposeSuffix[] = [
  'equity_stock',
  'debt_bond',
  'derivative_non_hedge',
  'derivative_hedge',
  'other',
]

export const G11_LISTED_TRADING_DISPOSE_ROWS: G11DisclosureRowDef[] = [
  { rowKey: 'equity_stock', label: '交易性权益工具投资——股票投资', isLeaf: true },
  { rowKey: 'debt_bond', label: '交易性债务工具投资——债券投资', isLeaf: true },
  {
    rowKey: 'derivative_non_hedge',
    label: '衍生工具——未指定为套期关系的衍生工具（含商品期货合约、外汇远期合约）',
    isLeaf: true,
  },
  {
    rowKey: 'derivative_hedge',
    label: '指定为有效套期关系的衍生工具（含公允价值套期）',
    isLeaf: true,
  },
  { rowKey: 'other', label: '其他', isLeaf: true },
]

export const G11_TRADING_DISPOSE_HINT =
  '有套期业务时须填本表明细，并注意与附注九、3保持一致。'

export const G11_TRADING_DISPOSE_SUBTYPE_OPTIONS: Array<{ value: G11TradingDisposeSuffix; label: string }> = [
  { value: 'equity_stock', label: '股票投资' },
  { value: 'debt_bond', label: '债券投资' },
  { value: 'derivative_non_hedge', label: '非套期衍生' },
  { value: 'derivative_hedge', label: '套期衍生' },
  { value: 'other', label: '其他' },
]

export const G11_SOE_REPATRIATION_PLACEHOLDER =
  '注：若投资收益汇回有重大限制的，应予以说明。若不存在此类重大限制，也应做出说明。'

/** 明细行是否属于「处置交易性」分项 */
export function isG11TradingDisposeDetailRow(row: { rowKey?: string; itemName?: string }): boolean {
  if (row.rowKey === 'trading_dispose') return true
  return /处置交易性金融资产/.test(String(row.itemName ?? ''))
}
