/**
 * G8 其他权益工具投资 — 公式引擎（纯函数）
 * Spec: .kiro/specs/g8-other-equity-instruments/
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const s = String(v).trim()
  if (!s || s === 'NaN') return 0
  const n = Number(s)
  return Number.isFinite(n) ? n : 0
}

/** 借方余额 = 期初 + 借方 - 贷方（科目 1503） */
export function calcDebitBalance(opening: number, debit: number, credit: number): number {
  return parseNum(opening) + parseNum(debit) - parseNum(credit)
}

/** 审定数 = 未审 + 账项调整（G8 无 AJE/RJE 分列） */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number {
  return parseNum(unadjusted) + parseNum(adjustment)
}

/** G8-2 期末余额 = 期初审定 + 增加 - 减少 + 公允价值变动 */
export function calcEndingBalance(
  openingAdjusted: number,
  increase: number,
  decrease: number,
  fvChange: number,
): number {
  return (
    parseNum(openingAdjusted)
    + parseNum(increase)
    - parseNum(decrease)
    + parseNum(fvChange)
  )
}

/**
 * G8-2 OCI 期末累计 = 期初累计 + 本期 OCI − 转入留存收益
 *（处置等情形下 OCI 可转入留存收益，CAS22）
 */
export function calcOciCumulativeEnding(
  openingCumulative: number,
  currentChange: number,
  toRetainedEarnings: number,
): number {
  return (
    parseNum(openingCumulative)
    + parseNum(currentChange)
    - parseNum(toRetainedEarnings)
  )
}

/** G8-4 公允价值 = 数量 × 单价（保留 2 位小数） */
export function calcFairValueAmount(qty: number, unitPrice: number): number {
  return Math.round(parseNum(qty) * parseNum(unitPrice) * 100) / 100
}

/** G8-4 公允价值差异 = 审定 - 未审 */
export function calcFairValueDiff(audited: number, unadjusted: number): number {
  return Math.round((parseNum(audited) - parseNum(unadjusted)) * 100) / 100
}

/** 数量变动对公允价值差异的影响 = (审定数量 − 未审数量) × 未审单价 */
export function calcFairValueQtyImpact(
  auditedQty: number,
  unadjQty: number,
  unadjPrice: number,
): number {
  return Math.round(
    (parseNum(auditedQty) - parseNum(unadjQty)) * parseNum(unadjPrice) * 100,
  ) / 100
}

/** 价格变动对公允价值差异的影响 = 审定数量 × (审定单价 − 未审单价) */
export function calcFairValuePriceImpact(
  auditedQty: number,
  auditedPrice: number,
  unadjPrice: number,
): number {
  return Math.round(
    parseNum(auditedQty) * (parseNum(auditedPrice) - parseNum(unadjPrice)) * 100,
  ) / 100
}

/** 变动额 = 期末审定 - 期初审定 */
export function calcChangeAmount(currentAudited: number, priorAudited: number): number {
  return parseNum(currentAudited) - parseNum(priorAudited)
}

/** 变动率；上期为 0 时 null */
export function calcChangeRate(priorAudited: number, currentAudited: number): number | null {
  if (priorAudited === 0) return null
  return (currentAudited - priorAudited) / Math.abs(priorAudited)
}

export function isChangeRateExceeding(rate: number | null, threshold: number): boolean {
  if (rate === null) return false
  return Math.abs(rate) > threshold
}

export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + parseNum(v), 0)
  const c = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(d - c) < 0.01
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}
