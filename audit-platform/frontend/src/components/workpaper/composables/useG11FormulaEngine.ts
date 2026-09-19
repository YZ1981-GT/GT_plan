/**
 * G11 投资收益 — 公式引擎（纯函数）
 * Spec: .kiro/specs/g11-investment-income/
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const s = String(v).trim()
  if (!s || s === 'NaN') return 0
  const n = Number(s)
  return Number.isFinite(n) ? n : 0
}

/** 审定数 = 未审 + 账项调整（损益类） */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number {
  return unadjusted + adjustment
}

/** 变动额 = 本期审定 - 上期审定 */
export function calcChangeAmount(currentAudited: number, priorAudited: number): number {
  return currentAudited - priorAudited
}

/** 变动率 = (本期 - 上期) / |上期|；上期为 0 时 null */
export function calcChangeRate(priorAudited: number, currentAudited: number): number | null {
  if (priorAudited === 0) return null
  return (currentAudited - priorAudited) / Math.abs(priorAudited)
}

export function isChangeRateExceeding(rate: number | null, threshold: number): boolean {
  if (rate === null) return false
  return Math.abs(rate) > threshold
}

/** 平均投资余额 = (期初 + 期末) / 2 */
export function calcAverageBalance(opening: number, closing: number): number {
  return (opening + closing) / 2
}

/** 收益率 = 收益 / 平均余额；平均余额为 0 时 null */
export function calcReturnRate(income: number, avgBalance: number): number | null {
  if (avgBalance === 0) return null
  return income / avgBalance
}

export function calcReturnRateChange(current: number | null, prior: number | null): number | null {
  if (current === null || prior === null) return null
  return current - prior
}

export function isReturnRateChangeExceeding(change: number | null, threshold: number): boolean {
  if (change === null) return false
  return Math.abs(change) > threshold
}

/** 借贷平衡 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + parseNum(v), 0)
  const c = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(d - c) < 0.01
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}

export function calcVariance(computed: number, actual: number): number {
  return computed - actual
}
