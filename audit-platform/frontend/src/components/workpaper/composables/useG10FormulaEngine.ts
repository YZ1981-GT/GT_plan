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

/** 审定数 = 未审 + AJE + RJE */
export function calcAdjustedAmount(unadjusted: number, aje: number, rje = 0): number {
  return unadjusted + aje + rje
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

/** (三)账面余额 = (一)初始金额 + (二)累计公允价值变动 */
export function calcBookFromParts(initial: number, fvAccum: number): number {
  return parseNum(initial) + parseNum(fvAccum)
}

/** G10-2 明细：期末余额 = 期初审定 + 本期初始确认 + FV变动 + 利息 − 本期减少 */
export function calcG10DetailClosingBalance(
  openingAdjusted: number,
  movementInitial: number,
  movementFvChange: number,
  interestExpense: number,
  currentDecrease: number,
): number {
  return calcCreditBalance(
    openingAdjusted,
    parseNum(movementInitial) + parseNum(movementFvChange) + parseNum(interestExpense),
    currentDecrease,
  )
}
