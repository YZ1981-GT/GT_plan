/**
 * @deprecated 请使用 useG7FormulaEngine；保留别名以兼容旧引用
 */
export {
  parseNum,
  calcAdjustedAmount,
  calcAdjustedAmount as calcAuditedAmount,
  calcDebitBalance,
  calcDebitBalance as calcEndBalance,
  calcChangeRate,
  calcBookValue,
  calcEndingCost,
  calcEndingEquityAdj,
  isDebitCreditBalanced,
} from './useG7FormulaEngine'

export function calcChangeAmount(current: number, prior: number): number {
  return current - prior
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + v, 0)
}

export function isChangeRateExceeding(
  rate: number | null | '' | 'N/A',
  threshold: number,
): boolean {
  if (rate === '' || rate === 'N/A' || rate === null) return false
  return Math.abs(rate) > threshold
}
