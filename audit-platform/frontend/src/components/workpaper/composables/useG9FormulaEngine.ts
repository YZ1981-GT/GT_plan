/**
 * G9 其他非流动金融资产 — 公式引擎（纯函数）
 * Spec: .kiro/specs/g9-other-noncurrent-financial/
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const s = String(v).trim()
  if (!s || s === 'NaN') return 0
  const n = Number(s)
  return Number.isFinite(n) ? n : 0
}

/** 借方余额 = 期初 + 借方 - 贷方（科目 1504） */
export function calcDebitBalance(opening: number, debit: number, credit: number): number {
  return parseNum(opening) + parseNum(debit) - parseNum(credit)
}

/** 审定数 = 未审 + AJE + RJE */
export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number {
  return parseNum(unadjusted) + parseNum(aje) + parseNum(rje)
}

/** G9-2 期末余额 = 期初审定 + 增加 - 减少 + FV变动 + 利息 - 减值 + OCI变动 */
export function calcEndingBalance(
  openingAdjusted: number,
  increase: number,
  decrease: number,
  fvChange: number,
  interest: number,
  impairment: number,
  ociChange: number = 0,
): number {
  return (
    parseNum(openingAdjusted)
    + parseNum(increase)
    - parseNum(decrease)
    + parseNum(fvChange)
    + parseNum(interest)
    - parseNum(impairment)
    + parseNum(ociChange)
  )
}

/** G9-4 公允价值 = 数量 × 单价（保留 2 位小数） */
export function calcFairValueAmount(qty: number, unitPrice: number): number {
  return Math.round(parseNum(qty) * parseNum(unitPrice) * 100) / 100
}

/** G9-4 公允价值差异 = 审定 - 未审（保留 2 位） */
export function calcFairValueDiff(audited: number, unadjusted: number): number {
  return Math.round((parseNum(audited) - parseNum(unadjusted)) * 100) / 100
}

/** 数量变动影响 = (审定数量 − 未审数量) × 未审单价 */
export function calcFairValueQtyImpact(
  auditedQty: number,
  unadjQty: number,
  unadjPrice: number,
): number {
  return Math.round(
    (parseNum(auditedQty) - parseNum(unadjQty)) * parseNum(unadjPrice) * 100,
  ) / 100
}

/** 价格变动影响 = 审定数量 × (审定单价 − 未审单价) */
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
  return currentAudited - priorAudited
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

/** G9-5 L3 调节表期末（10 因子） */
export function calcL3Reconciliation(
  opening: number,
  purchase: number,
  disposal: number,
  transferIn: number,
  transferOut: number,
  fvChangePL: number,
  fvChangeOCI: number,
  interest: number,
  impairment: number,
  other: number,
): number {
  return (
    parseNum(opening)
    + parseNum(purchase)
    - parseNum(disposal)
    + parseNum(transferIn)
    - parseNum(transferOut)
    + parseNum(fvChangePL)
    + parseNum(fvChangeOCI)
    + parseNum(interest)
    - parseNum(impairment)
    + parseNum(other)
  )
}

export function calcL3Variance(computedClosing: number, reportedClosing: number): number {
  return parseNum(computedClosing) - parseNum(reportedClosing)
}

export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + parseNum(v), 0)
  const c = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(d - c) < 0.01
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}
