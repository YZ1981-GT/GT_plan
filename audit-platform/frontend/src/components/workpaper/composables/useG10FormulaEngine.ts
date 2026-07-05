/**
 * G10 交易性金融负债 — 公式引擎（纯函数）
 * Spec: .kiro/specs/g10-trading-financial-liabilities/
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const s = String(v).trim()
  if (!s || s === 'NaN') return 0
  const n = Number(s)
  return Number.isFinite(n) ? n : 0
}

/** 贷方余额 = 期初 + 贷方 - 借方 */
export function calcCreditBalance(opening: number, credit: number, debit: number): number {
  return opening + credit - debit
}

/** 审定数 = 未审 + 账项调整 */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number {
  return unadjusted + adjustment
}

/** 变动额 = 期末审定 - 期初审定 */
export function calcChangeAmount(currentAudited: number, priorAudited: number): number {
  return currentAudited - priorAudited
}

/** 变动率 = (本期 - 上期) / |上期|；上期为 0 时 null（比率非百分比） */
export function calcChangeRate(priorAudited: number, currentAudited: number): number | null {
  if (priorAudited === 0) return null
  return (currentAudited - priorAudited) / Math.abs(priorAudited)
}

export function isChangeRateExceeding(rate: number | null, threshold: number): boolean {
  if (rate === null) return false
  return Math.abs(rate) > threshold
}

/** L3 调节表期末（负债方向） */
export function calcL3Reconciliation(
  opening: number,
  currentNew: number,
  currentTerminated: number,
  transferIn: number,
  transferOut: number,
  fvChange: number,
  interest: number,
  other: number,
): number {
  return (
    parseNum(opening)
    + parseNum(currentNew)
    - parseNum(currentTerminated)
    + parseNum(transferIn)
    - parseNum(transferOut)
    + parseNum(fvChange)
    + parseNum(interest)
    + parseNum(other)
  )
}

export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + parseNum(v), 0)
  const c = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(d - c) < 0.01
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}
