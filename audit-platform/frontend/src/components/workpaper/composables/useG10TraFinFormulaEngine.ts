/**
 * 交易性金融负债 — 公式引擎（贷方科目）
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}
export function calcEndBalance(prior: number, debit: number, credit: number): number {
  return prior + credit - debit
}
export function calcChangeAmount(current: number, prior: number): number {
  return current - prior
}
export function calcChangeRate(prior: number, current: number): number | '' | 'N/A' {
  if (prior === 0 && current === 0) return ''
  if (prior === 0) return 'N/A'
  return (current - prior) / prior
}
export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + v, 0)
}
export function isChangeRateExceeding(rate: number | '' | 'N/A', threshold: number): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}
