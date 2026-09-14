/**
 * G12 净敞口套期收益 — 公式引擎（纯函数）
 * Spec: .kiro/specs/g12-net-hedge-gains/
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  if (typeof v === 'string' && v.trim() === '') return 0
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

export function calcAdjustedAmount(unadjusted: number, adjustment: number): number {
  return unadjusted + adjustment
}

export function calcFVChange(opening: number, closing: number): number {
  return closing - opening
}

export function calcChangeAmount(currentAudited: number, priorAudited: number): number {
  return currentAudited - priorAudited
}

export function calcChangeRate(priorAudited: number, currentAudited: number): number | null {
  if (priorAudited === 0) return null
  return (currentAudited - priorAudited) / Math.abs(priorAudited)
}

export function isChangeRateExceeding(rate: number | null, threshold: number): boolean {
  if (rate === null) return false
  return Math.abs(rate) > threshold
}

export function calcHedgeIneffectiveness(instrumentChange: number, itemChange: number): number {
  return Math.abs(instrumentChange - itemChange)
}

export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + parseNum(v), 0)
  const c = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(d - c) < 0.01
}

export function calcVariance(computed: number, actual: number): number {
  return computed - actual
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}

export function isVoucherAbnormal(checks: Array<boolean | null>): boolean {
  return checks.some((c) => c === false)
}
