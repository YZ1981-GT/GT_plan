import type { CutoffRow } from './useCycleCutoff'

/** 记账金额与单据金额是否不一致 */
export function amountMismatch(row: CutoffRow): boolean {
  const a = row.amount
  const b = row.documentAmount
  if (Math.abs(a) < 0.005 && Math.abs(b) < 0.005) return false
  if (Math.abs(b) < 0.005) return false
  return Math.abs(a - b) >= 0.02
}

/** 上期期末（首年承接用） */
export function priorPeriodCutoffDate(cutoffDate: string): string {
  if (!/^\d{4}-\d{2}-\d{2}/.test(cutoffDate)) return ''
  const y = Number(cutoffDate.slice(0, 4)) - 1
  if (!Number.isFinite(y) || y < 1900) return ''
  return `${y}-12-31`
}

/** 是否资本化/开发支出相关摘要 */
export function suggestsCapitalization(description: string): boolean {
  return /资本化|开发支出|1717|无形资产/.test(String(description ?? ''))
}

/** 是否涉及费用化/6602（I2↔I6 联动提示） */
export function suggestsRdExpense(description: string): boolean {
  return /6602|费用化|研发费用/.test(String(description ?? ''))
}
