/**
 * G2 应收利息 — 公式引擎（借方科目 1132）
 *
 * 核心公式：
 * - 利息测算：面值 × 利率/100 × 天数/365（债券惯例，区别于F3的360天票据惯例）
 * - 借方余额：期初 + 借方 - 贷方（资产类）
 * - ECL三阶段：EAD × PD × LGD
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Requirement 12
 */

export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

/** 应收利息 = 面值 × 利率/100 × 天数/365（365天基准） */
export function calcInterest365(principal: number, ratePct: number, days: number): number {
  if (principal < 0 || days < 0) return 0
  return (principal * ratePct / 100 * days) / 365
}

/** 计息天数 = 截止日 - 起始日 */
export function calcAccruedDays(startStr: string, endStr: string): number {
  if (!startStr || !endStr) return 0
  const start = new Date(startStr)
  const end = new Date(endStr)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 0
  const diff = end.getTime() - start.getTime()
  return diff > 0 ? Math.floor(diff / 86400000) : 0
}

/** 借方余额 = 期初 + 借方 - 贷方 */
export function calcDebitBalance(opening: number, debit: number, credit: number): number {
  return opening + debit - credit
}

/** 审定 = 未审 + AJE + RJE */
export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

/** 审定数（alias） */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return calcAdjustedAmount(unadjusted, aje, rje)
}

/** ECL = EAD × PD × LGD */
export function calcECL(ead: number, pd: number, lgd: number): number {
  if (ead < 0 || pd < 0 || lgd < 0) return 0
  return ead * pd * lgd
}

/** 逾期天数 = MAX(0, 当前日 - 约定日) */
export function calcOverdueDays(dueDateStr: string, asOf: Date = new Date()): number {
  if (!dueDateStr) return 0
  const due = new Date(dueDateStr)
  if (Number.isNaN(due.getTime())) return 0
  const diff = asOf.getTime() - due.getTime()
  return diff > 0 ? Math.floor(diff / 86400000) : 0
}

/** 阶段判定：已减值→3, 显著增加→2, 否则→1 */
export function determineStage(impaired: boolean, significantIncrease: boolean): 1 | 2 | 3 {
  if (impaired) return 3
  if (significantIncrease) return 2
  return 1
}

/** 借贷平衡校验 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + v, 0)
  const c = credits.reduce((s, v) => s + v, 0)
  return Math.abs(d - c) < 0.01
}

/** 期末应收 = 应计利息 - 已收利息 */
export function calcNetReceivable(accrued: number, received: number): number {
  return accrued - received
}

/** ECL差异 = 测算ECL - 企业计提 */
export function calcECLVariance(calculatedECL: number, companyProvision: number): number {
  return calculatedECL - companyProvision
}

/** 期末余额（alias for calcDebitBalance） */
export function calcEndBalance(prior: number, debit: number, credit: number): number {
  return calcDebitBalance(prior, debit, credit)
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
