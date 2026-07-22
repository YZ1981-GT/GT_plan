/**
 * G13 公允价值变动收益 — 公式引擎（纯函数）
 * Spec: .kiro/specs/g13-fair-value-changes/
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 审定数 = 未审 + 调整 */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number {
  return unadjusted + adjustment
}

/** 公允价值变动 = 期末 - 期初 */
export function calcFVChange(opening: number, closing: number): number {
  return closing - opening
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

/** 借贷平衡 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + parseNum(v), 0)
  const c = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(d - c) < 0.01
}

/** 差异 = fvChange - adjustedAmount（交叉验证） */
export function calcVariance(fvChange: number, adjustedAmount: number): number {
  return fvChange - adjustedAmount
}

export function isFvReconciled(fvChange: number, adjustedAmount: number, tolerance = 0.01): boolean {
  return Math.abs(fvChange - adjustedAmount) <= tolerance
}

/**
 * 对应科目公允价值恒等式（对齐致同 G13-2）：
 * 公允价值 = 成本 + 累计公允价值变动
 */
export function calcFairValueFromParts(cost: number, cumulativeFvChange: number): number {
  return parseNum(cost) + parseNum(cumulativeFvChange)
}

/** 核对：成本 + 累计公允价值变动 = 公允价值 */
export function isBsFvReconciled(
  cost: number,
  cumulativeFvChange: number,
  fairValue: number,
  tolerance = 0.01,
): boolean {
  return Math.abs(calcFairValueFromParts(cost, cumulativeFvChange) - parseNum(fairValue)) <= tolerance
}

/** 计入损益 ↔ 损益科目审定数勾稽 */
export function isPlReconciled(amountInPl: number, audited: number, tolerance = 0.01): boolean {
  return Math.abs(parseNum(amountInPl) - parseNum(audited)) <= tolerance
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}
