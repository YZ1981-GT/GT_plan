/**
 * K1-1 审定表 — 致同 Excel 行结构定义
 *
 * 一、其他应收款（原值/坏账/净值）→ 单项 + 三组合
 * 二、账龄分布（原值/坏账/净值）→ 5年6档
 * 三、款项性质分布（原值/坏账/净值）→ 保证金/押金/备用金/往来款/其他
 */
import { DEFAULT_K2_AGING_BUCKETS } from './k1PolicyCrossHelpers'

export type K1AdjBlockKind = 'portfolio' | 'aging' | 'nature'

export interface K1AdjRowDef {
  rowKey: string
  label: string
  /** 从 K1-2 同步时的分类键 */
  syncKey?: string
  isSubtotal?: boolean
  linkSheet?: string
  linkHint?: string
}

export const K1_PORTFOLIO_ROW_DEFS: K1AdjRowDef[] = [
  { rowKey: 'r0', label: '单项计提', syncKey: 'individual' },
  { rowKey: 'r1', label: '账龄组合', syncKey: 'aging', linkSheet: 'K1-8', linkHint: '与 K1-8 账龄组合一致' },
  { rowKey: 'r2', label: '客户类型组合', syncKey: 'customer', linkSheet: 'K1-6', linkHint: '与 K1-6 组合划分一致' },
  { rowKey: 'r3', label: '其他组合', syncKey: 'other', linkSheet: 'K1-8' },
]

export const K1_AGING_ROW_DEFS: K1AdjRowDef[] = [
  ...DEFAULT_K2_AGING_BUCKETS.map((label, i) => ({
    rowKey: `a${i}`,
    label,
    syncKey: `aging-${i}`,
  })),
  { rowKey: 'subtotal', label: '小计', isSubtotal: true },
]

export const K1_NATURE_ROW_DEFS: K1AdjRowDef[] = [
  { rowKey: 'n0', label: '保证金', syncKey: 'margin' },
  { rowKey: 'n1', label: '押金', syncKey: 'deposit' },
  { rowKey: 'n2', label: '备用金', syncKey: 'petty' },
  { rowKey: 'n3', label: '往来款', syncKey: 'intercompany' },
  { rowKey: 'n4', label: '其他', syncKey: 'other-nature' },
  { rowKey: 'subtotal', label: '小计', isSubtotal: true },
]

export const K1_PORTFOLIO_COUNT = K1_PORTFOLIO_ROW_DEFS.length
export const K1_AGING_COUNT = K1_AGING_ROW_DEFS.filter((r) => !r.isSubtotal).length
export const K1_NATURE_COUNT = K1_NATURE_ROW_DEFS.filter((r) => !r.isSubtotal).length

/** 款项性质 → 性质分布 syncKey */
export function classifyK1Nature(nature: string): string {
  const n = String(nature || '').trim()
  if (/保证金/.test(n)) return 'margin'
  if (/押金/.test(n)) return 'deposit'
  if (/备用金/.test(n)) return 'petty'
  if (/往来|代垫|关联/.test(n)) return 'intercompany'
  return 'other-nature'
}

/** K1-2 明细行 → 组合计提分类（无 AI 列时用 stage 近似） */
export function classifyK1Portfolio(stage: number): 'individual' | 'aging' {
  return stage === 3 ? 'individual' : 'aging'
}
