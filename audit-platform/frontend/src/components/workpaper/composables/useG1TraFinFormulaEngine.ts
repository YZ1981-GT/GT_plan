/**
 * G1 交易性金融资产 — 公式引擎（借方科目 / 公允价值）
 */

export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

export function calcDebitBalance(opening: number, debit: number, credit: number): number {
  return opening + debit - credit
}

export function calcEndBalance(prior: number, debit: number, credit: number): number {
  return calcDebitBalance(prior, debit, credit)
}

export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return calcAdjustedAmount(unadjusted, aje, rje)
}

export function calcFairValue(quantity: number, unitFv: number): number {
  const q = quantity < 0 ? 0 : quantity
  return q * unitFv
}

export function calcUnrealizedGain(fairValue: number, cost: number): number {
  return fairValue - cost
}

export function calcRealizedGain(proceeds: number, cost: number): number {
  return proceeds - cost
}

export function calcNetGain(realizedGain: number, fee: number): number {
  return realizedGain - Math.max(fee, 0)
}

export function calcLevel1Diff(quantity: number, quote: number, bookValue: number): number {
  return calcFairValue(quantity, quote) - bookValue
}

export function calcCountDiff(counted: number, booked: number): number {
  return counted - booked
}

export function calcReconciliation(countDayBalance: number, increase: number, decrease: number): number {
  return countDayBalance + increase - decrease
}

export function calcClosingQuantity(opening: number, buy: number, sell: number): number {
  const v = opening + buy - sell
  return v < 0 ? 0 : v
}

export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + v, 0)
  const c = credits.reduce((s, v) => s + v, 0)
  return Math.abs(d - c) < 0.01
}

export function calcFairValueChange(endFv: number, beginFv: number): number {
  return endFv - beginFv
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

export function calcUnitPrice(amount: number, quantity: number): number | '' {
  if (!quantity) return ''
  return amount / quantity
}

export function calcEndAmount(opening: number, increase: number, decrease: number): number {
  return opening + increase - decrease
}
