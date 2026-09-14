/** G12-3 调整分录汇总 — 存储与回写辅助 */
import { G12_ACCOUNT_CODE } from './g12Constants'
import { parseNum, isDebitCreditBalanced } from './useG12FormulaEngine'

export type G12AdjCategory = 'account' | 'report' | 'other'

export interface G12AdjustmentEntryLike {
  category?: string
  entryType?: string
  accountCode?: string
  debitAmount?: number
  creditAmount?: number
}

export interface G12AdjustmentSummary {
  rowCount: number
  ajeCount: number
  rjeCount: number
  totalDebits: number
  totalCredits: number
  balanceDiff: number
  /** 6103 借−贷净额（回写 G12-1 net_hedge） */
  net6103: number
  ajeNet6103: number
  rjeNet6103: number
}

export const G12_ADJ_CATEGORY_OPTIONS: { value: G12AdjCategory; label: string; entryType: 'AJE' | 'RJE' }[] = [
  { value: 'account', label: '账项调整', entryType: 'AJE' },
  { value: 'report', label: '报表调整', entryType: 'RJE' },
  { value: 'other', label: '其他', entryType: 'AJE' },
]

export const G12_ADJ_FS_ITEMS = [
  '净敞口套期收益',
  '公允价值变动损益',
  '其他综合收益',
  '存货',
  '衍生金融资产/负债',
] as const

export const G12_ADJ_NOTE_ITEMS = [
  '净敞口套期收益',
  '套期工具公允价值',
  '现金流量套期储备',
] as const

export const G12_ADJ_ACCOUNT_OPTIONS: { code: string; name: string }[] = [
  { code: G12_ACCOUNT_CODE, name: '净敞口套期收益' },
  { code: '6101', name: '公允价值变动损益' },
  { code: '4002', name: '其他综合收益' },
  { code: '1403', name: '存货' },
  { code: '3101', name: '衍生工具' },
  { code: '1002', name: '银行存款' },
  { code: '4104', name: '利润分配—未分配利润' },
]

export function categoryToEntryType(category: string | undefined): 'AJE' | 'RJE' {
  const hit = G12_ADJ_CATEGORY_OPTIONS.find((o) => o.value === category)
  if (hit) return hit.entryType
  if (category === 'RJE' || category === 'report') return 'RJE'
  return 'AJE'
}

export function entryTypeToCategory(entryType: string | undefined): G12AdjCategory {
  return entryType === 'RJE' ? 'report' : 'account'
}

export function isG12RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return ['6103', '6101', '4002', '1403', '3101'].some((p) => c === p || c.startsWith(p))
}

export function calcG12AdjustmentNet6103(rows: G12AdjustmentEntryLike[]): number {
  return rows
    .filter((r) => String(r.accountCode ?? '').startsWith(G12_ACCOUNT_CODE))
    .reduce((s, r) => s + parseNum(r.debitAmount) - parseNum(r.creditAmount), 0)
}

export function aggregateG12AdjustmentAjeRje(rows: G12AdjustmentEntryLike[]): { aje: number; rje: number } {
  let aje = 0
  let rje = 0
  for (const r of rows) {
    if (!String(r.accountCode ?? '').startsWith(G12_ACCOUNT_CODE)) continue
    const net = parseNum(r.debitAmount) - parseNum(r.creditAmount)
    const et = r.entryType ?? categoryToEntryType(r.category)
    if (et === 'RJE') rje += net
    else aje += net
  }
  return { aje, rje }
}

export function summarizeG12Adjustment(rows: G12AdjustmentEntryLike[]): G12AdjustmentSummary {
  const debits = rows.map((r) => parseNum(r.debitAmount))
  const credits = rows.map((r) => parseNum(r.creditAmount))
  const totalDebits = debits.reduce((s, v) => s + v, 0)
  const totalCredits = credits.reduce((s, v) => s + v, 0)
  const { aje, rje } = aggregateG12AdjustmentAjeRje(rows)
  return {
    rowCount: rows.length,
    ajeCount: rows.filter((r) => (r.entryType ?? categoryToEntryType(r.category)) === 'AJE').length,
    rjeCount: rows.filter((r) => (r.entryType ?? categoryToEntryType(r.category)) === 'RJE').length,
    totalDebits,
    totalCredits,
    balanceDiff: totalDebits - totalCredits,
    net6103: calcG12AdjustmentNet6103(rows),
    ajeNet6103: aje,
    rjeNet6103: rje,
  }
}

export function isG12AdjustmentBalanced(rows: G12AdjustmentEntryLike[]): boolean {
  return isDebitCreditBalanced(
    rows.map((r) => parseNum(r.debitAmount)),
    rows.map((r) => parseNum(r.creditAmount)),
  )
}

export interface G12AdjustmentGroup {
  key: string
  adjustmentDesc: string
  rows: Array<G12AdjustmentEntryLike & { rowId?: string; seq?: number }>
  totalDebit: number
  totalCredit: number
  balanced: boolean
}

/** 按调整事项说明分组（对齐 Excel 同一事项多行分录） */
export function groupG12AdjustmentsByDesc<T extends G12AdjustmentEntryLike & { adjustmentDesc?: string; rowId?: string }>(
  rows: T[],
): Array<G12AdjustmentGroup & { rows: T[] }> {
  const map = new Map<string, T[]>()
  for (const r of rows) {
    const desc = (r.adjustmentDesc ?? '').trim() || '（未命名调整事项）'
    const key = desc
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(r)
  }
  return [...map.entries()].map(([key, groupRows]) => {
    const totalDebit = groupRows.reduce((s, r) => s + parseNum(r.debitAmount), 0)
    const totalCredit = groupRows.reduce((s, r) => s + parseNum(r.creditAmount), 0)
    return {
      key,
      adjustmentDesc: key,
      rows: groupRows,
      totalDebit,
      totalCredit,
      balanced: Math.abs(totalDebit - totalCredit) < 0.01,
    }
  })
}
