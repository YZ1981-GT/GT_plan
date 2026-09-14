/** G10 科目码匹配 + 负债类型 → 审定表分项映射 */
import {
  G10_ACCOUNT_ALIASES,
  G10_ACCOUNT_CODE,
  G10_ACCOUNT_NAME,
  G10_LIABILITY_TYPE_OPTIONS,
} from './g10Constants'
import type { G10LiabilityLineSuffix } from './g10AdjudicationItems'

export const G10_ADJ_WRITEBACK_DEFAULT_ROW = 'book_other'

/** 可回写的 (三) 账面余额分项（默认调整落点） */
export const G10_ADJUDICATION_WRITEBACK_OPTIONS: Array<{ rowKey: string; label: string }> = [
  { rowKey: 'book_trading_bond', label: '(三) 发行的交易性债券' },
  { rowKey: 'book_derivative_liability', label: '(三) 衍生金融负债' },
  { rowKey: 'book_other', label: '(三) 其他' },
  { rowKey: 'book_designated_bond', label: '(三) 指定—债券' },
  { rowKey: 'book_hybrid_tool', label: '(三) 混合工具' },
  { rowKey: 'book_other_designated', label: '(三) 指定—其他' },
]

/** G10-2 负债类型 → 审定表叶节点 suffix（不含组首行） */
export const G10_LIABILITY_TYPE_TO_SUFFIX: Record<string, G10LiabilityLineSuffix> = {
  交易性债券: 'trading_bond',
  卖出回购: 'other',
  衍生金融负债: 'derivative_liability',
  融券负债: 'other',
  结构化产品: 'hybrid_tool',
  其他: 'other',
}

export function isG10AccountCode(code: string | null | undefined): boolean {
  const c = String(code ?? '').trim()
  if (!c) return false
  return G10_ACCOUNT_ALIASES.some((prefix) => c === prefix || c.startsWith(prefix))
}

export function g10DefaultAccountCode(): string {
  return G10_ACCOUNT_CODE
}

export function g10AccountLabel(resolvedCode?: string | null): string {
  const code = resolvedCode?.trim() || G10_ACCOUNT_ALIASES.join('/')
  return `${G10_ACCOUNT_NAME}（${code}）`
}

/** 从负债类型 / 摘要推断 G10-1 (三) 回写目标行 */
export function resolveG10LiabilitySuffix(input: {
  liabilityType?: string
  liabilityName?: string
  isDerivative?: boolean
  summary?: string
  remark?: string
}): G10LiabilityLineSuffix {
  const type = String(input.liabilityType ?? '').trim()
  if (type && G10_LIABILITY_TYPE_TO_SUFFIX[type]) {
    return G10_LIABILITY_TYPE_TO_SUFFIX[type]
  }
  const text = `${input.liabilityName ?? ''} ${input.summary ?? ''} ${input.remark ?? ''}`
  if (/指定|FVTPL|混合工具/.test(text)) {
    if (/混合|结构化/.test(text)) return 'hybrid_tool'
    if (/债券/.test(text)) return 'designated_bond'
    return 'other_designated'
  }
  if (input.isDerivative || /衍生|期权|互换|期货|远期/.test(text)) return 'derivative_liability'
  if (/债券/.test(text)) return 'trading_bond'
  if (/融券/.test(text)) return 'other'
  if (/回购/.test(text)) return 'other'
  return 'other'
}

export function inferG10AdjudicationRowKey(input: {
  liabilityType?: string
  liabilityName?: string
  summary?: string
  remark?: string
  isDerivative?: boolean
  adjudicationRowKey?: string
}): string {
  if (input.adjudicationRowKey?.trim()) return input.adjudicationRowKey.trim()
  const suffix = resolveG10LiabilitySuffix(input)
  return `book_${suffix}`
}

export function isG10LiabilityType(value: string): boolean {
  return (G10_LIABILITY_TYPE_OPTIONS as readonly string[]).includes(value)
}

/** 负债项目名称归一化（G10-2 ↔ G10-5 逐行匹配） */
export function matchG10LiabilityKey(name: string): string {
  return (name || '').trim().toLowerCase()
}

/** 从辅助核算名称推断负债类型 */
export function inferG10LiabilityTypeFromName(name: string): string {
  const text = (name || '').trim()
  if (/衍生|期权|互换|期货|远期/.test(text)) return '衍生金融负债'
  if (/债券|融资券|短融|CP/.test(text)) return '交易性债券'
  if (/回购/.test(text)) return '卖出回购'
  if (/融券/.test(text)) return '融券负债'
  if (/结构化|混合/.test(text)) return '结构化产品'
  return '其他'
}

/** 从名称推断类别（指定类 / 交易类） */
export function inferG10LiabilityCategory(name: string): string {
  return /指定|FVTPL|混合工具/.test(name || '') ? '指定类' : '交易类'
}
