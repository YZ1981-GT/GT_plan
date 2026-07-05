/**
 * G3 应收股利 — 公式引擎（借方科目 1131）
 *
 * 核心公式：
 * - 股利测算：持股数量 × 每股股利
 * - 借方余额：期初 + 借方(宣告) - 贷方(收回)（资产类）
 * - 分红率：分红总额 / 净利润 × 100%（净利润≤0→0）
 * - 权益份额：净资产 × 持股比例/100
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Requirement 9
 */

export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

/** 应收股利 = 持股数量 × 每股股利 */
export function calcDividend(shares: number, dps: number): number {
  return shares * dps
}

/** 实际分红率 = 分红总额 / 净利润 × 100%（净利润≤0→0） */
export function calcPayoutRatio(dividendTotal: number, netProfit: number): number {
  if (netProfit <= 0) return 0
  return (dividendTotal / netProfit) * 100
}

/** 借方余额 = 期初 + 借方 - 贷方 */
export function calcDebitBalance(opening: number, debit: number, credit: number): number {
  return opening + debit - credit
}

/** 审定 = 未审 + AJE + RJE */
export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

/** 逾期天数 = MAX(0, 当前日期 - 约定日) */
export function calcOverdueDays(currentDate: Date, dueDate: Date): number {
  const diff = currentDate.getTime() - dueDate.getTime()
  return diff > 0 ? Math.floor(diff / 86400000) : 0
}

/** 期末应收 = 应收股利 - 已收金额 */
export function calcNetReceivable(receivable: number, received: number): number {
  return receivable - received
}

/** 权益份额 = 净资产 × 持股比例/100 */
export function calcEquityShare(netAssets: number, ratio: number): number {
  return netAssets * ratio / 100
}

/** 借贷平衡校验 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + v, 0)
  const c = credits.reduce((s, v) => s + v, 0)
  return Math.abs(d - c) < 0.01
}

/** 审定数（alias） */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return calcAdjustedAmount(unadjusted, aje, rje)
}

/** 期末余额 = 期初 + 借方 - 贷方（alias） */
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
