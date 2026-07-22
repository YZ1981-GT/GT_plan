/** G10 交易性金融负债 — 审定表行定义与常量 */
export interface G10LineDef {
  rowKey: string
  label: string
  group?: string
}

export const G10_ACCOUNT_CODE = '2101'
/** 科目名称（试算表按名称回退匹配） */
export const G10_ACCOUNT_NAME = '交易性金融负债'
/** 试算表/分录匹配别名（按优先级） */
export const G10_ACCOUNT_ALIASES = ['2101', '2102'] as const
/** |变动率|>20% 原因分析必填；审计说明中对 |变动率|>30% 作重点说明（对齐 Excel） */
export const G10_CHANGE_RATE_THRESHOLD = 0.2
export const G10_NOTE_CHANGE_RATE_THRESHOLD = 0.3
export const G10_VIRTUAL_SCROLL_THRESHOLD = 50

export const G10_LIABILITY_TYPE_OPTIONS = [
  '交易性债券',
  '卖出回购',
  '衍生金融负债',
  '融券负债',
  '结构化产品',
  '其他',
] as const

/** G10-2 类别（对齐 Excel「类别」列：指定类 / 交易类） */
export const G10_LIABILITY_CATEGORY_OPTIONS = ['指定类', '交易类'] as const

export const G10_FV_LEVEL_OPTIONS = ['Level1', 'Level2', 'Level3'] as const

export const G10_CONFIRMATION_OPTIONS = [
  '未发函',
  '已发函',
  '已回函相符',
  '已回函不符',
  '不适用',
] as const

import {
  G10_ADJUDICATION_ITEMS,
  G10_GROUP_LABELS,
  G10_GROUP_SUBTOTAL_LABELS,
  G10_LIABILITY_LINE_SUFFIXES,
} from './g10AdjudicationItems'

export {
  G10_ADJUDICATION_ITEMS,
  G10_GROUP_LABELS,
  G10_GROUP_SUBTOTAL_LABELS,
  G10_LIABILITY_LINE_SUFFIXES,
}

export const G10_COMPLIANCE_OPTIONS = [
  { value: 'compliant', label: '合规' },
  { value: 'non_compliant', label: '不合规' },
  { value: 'not_applicable', label: '不适用' },
] as const

export const G10_RISK_LEVEL_OPTIONS = [
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
] as const

export const G10_VALUATION_METHOD_OPTIONS = [
  '市场法', '收益法', '成本法', '期权定价模型', '其他',
] as const

import {
  G10_LISTED_MOVEMENT_ROWS,
  G10_SOE_BALANCE_ROWS,
} from './g10SchemaRows'

export type { G10DisclosureRowDef } from './g10SchemaRows'
export { G10_LISTED_MOVEMENT_ROWS, G10_SOE_BALANCE_ROWS }

/** @deprecated 使用 G10_LISTED_MOVEMENT_ROWS */
export const G10_DISCLOSURE_LISTED_ROWS = G10_LISTED_MOVEMENT_ROWS
/** @deprecated 使用 G10_SOE_BALANCE_ROWS */
export const G10_DISCLOSURE_SOE_ROWS = G10_SOE_BALANCE_ROWS

export const G10_DISCLOSURE_FORMULA_MAP = [
  { field: '附注合计-本期', source: 'G10-1审定表', formula: 'SUM(book_fv closingAdjusted) → substantive:adjudicated EventBus', account: '2101' },
  { field: '附注各行-本期', source: 'G10-2明细', formula: '按 liabilityType 汇总 closingAdjusted', account: '2101' },
  { field: '附注合计-上期', source: 'G10-adj-prior', formula: 'openingAdjusted 各业务行', account: '2101' },
  { field: '变动额/变动率', source: '计算', formula: 'currentAmount - priorAmount; rate=prior≠0', account: '-' },
] as const
