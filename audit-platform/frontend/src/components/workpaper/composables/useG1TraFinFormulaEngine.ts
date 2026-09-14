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

/**
 * 有价证券盘点倒轧（G1-12）：将盘点日实存倒轧至资产负债表日。
 * 增减指「资产负债表日 → 盘点日」期间变动：
 * 报表日实存 = 盘点日实存 − 增加 + 减少
 */
export function calcReconciliation(countDayBalance: number, increase: number, decrease: number): number {
  return countDayBalance - increase + decrease
}

/** 面值总计 = 单位面值 × 数量（保留 2 位） */
export function calcFaceTotal(faceValue: number, quantity: number): number {
  return Math.round(parseNum(faceValue) * parseNum(quantity) * 100) / 100
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

/** 计息天数 = 截止日 − 起始日（日历日差，与 G2 一致） */
export function calcAccruedDays(startStr: string, endStr: string): number {
  if (!startStr || !endStr) return 0
  const start = new Date(startStr)
  const end = new Date(endStr)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 0
  const diff = end.getTime() - start.getTime()
  return diff > 0 ? Math.floor(diff / 86400000) : 0
}

/**
 * 应计利息 = 本金 × 年化利率(%) / 100 × 天数 / 基数
 * 基数默认 365（Actual/365）；可选 360
 */
export function calcInterestByBasis(
  principal: number,
  ratePct: number,
  days: number,
  basis: 360 | 365 = 365,
): number {
  if (principal < 0 || days < 0 || basis <= 0) return 0
  return (principal * ratePct / 100 * days) / basis
}

/** 取两日中较早/较晚者（非法日期回退另一侧） */
export function minDateStr(a: string, b: string): string {
  if (!a) return b
  if (!b) return a
  return a <= b ? a : b
}

export function maxDateStr(a: string, b: string): string {
  if (!a) return b
  if (!b) return a
  return a >= b ? a : b
}
