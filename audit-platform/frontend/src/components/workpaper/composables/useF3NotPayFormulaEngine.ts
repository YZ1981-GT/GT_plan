/**
 * F3 应付票据 — 公式引擎（贷方科目 2201）
 * Spec: .kiro/specs/f3-notes-payable/ Requirement 11
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

/** 应付利息 = 面值 × 利率/100 × 天数/360 */
export function calcInterest(principal: number, ratePct: number, days: number): number {
  if (principal < 0 || days < 0) return 0
  return (principal * ratePct / 100 * days) / 360
}

/** 逾期天数 = MAX(0, 当前日 - 到期日) */
export function calcOverdueDays(dueDateStr: string, asOf: Date = new Date()): number {
  if (!dueDateStr) return 0
  const due = new Date(dueDateStr)
  if (Number.isNaN(due.getTime())) return 0
  const diff = asOf.getTime() - due.getTime()
  return diff > 0 ? Math.floor(diff / 86400000) : 0
}

/** 贷方余额 = 期初 + 贷方(增加) - 借方(减少) */
export function calcCreditBalance(opening: number, credit: number, debit: number): number {
  return opening + credit - debit
}

/** 审定 = 未审 + AJE + RJE */
export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

/** 集中度 = amount / total × 100 */
export function calcConcentration(amount: number, total: number): number {
  if (total <= 0) return 0
  return (amount / total) * 100
}

/** 借贷平衡 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + v, 0)
  const c = credits.reduce((s, v) => s + v, 0)
  return Math.abs(d - c) < 0.01
}

export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return calcAdjustedAmount(unadjusted, aje, rje)
}

export function calcEndBalance(prior: number, debit: number, credit: number): number {
  return calcCreditBalance(prior, credit, debit)
}

export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + v, 0)
}

export function calcChangeAmount(current: number, prior: number): number {
  return current - prior
}

export function calcChangeRate(prior: number, current: number): number | '' | 'N/A' {
  if (prior === 0 && current === 0) return ''
  if (prior === 0) return 'N/A'
  return (current - prior) / prior
}

export function isChangeRateExceeding(rate: number | '' | 'N/A', threshold: number): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}

/** 应计天数 = 截止日 - 起始日 */
export function calcAccruedDays(startStr: string, endStr: string): number {
  if (!startStr || !endStr) return 0
  const start = new Date(startStr)
  const end = new Date(endStr)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 0
  const diff = end.getTime() - start.getTime()
  return diff > 0 ? Math.floor(diff / 86400000) : 0
}

/** 期限(天) = 到期日 - 出票日 */
export function calcTermDays(issueStr: string, dueStr: string): number {
  return calcAccruedDays(issueStr, dueStr)
}
