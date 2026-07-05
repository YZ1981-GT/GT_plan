/**
 * 应付账款 — 公式引擎（贷方科目 2202）
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 2.1
 * 8个纯函数 + parseNum + 辅助函数
 */

/** 安全数值解析：null/undefined/NaN/空→0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

/** Property 1: 贷方余额 = 期初 + 贷方 - 借方 */
export function calcCreditBalance(opening: number, credit: number, debit: number): number {
  return opening + credit - debit
}

/** Property 2: 审定数 = 未审 + AJE + RJE */
export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

/** 账龄合计 = 各账龄段SUM */
export function calcAgingTotal(...segments: number[]): number {
  return segments.reduce((s, v) => s + v, 0)
}

/** Property 3: 账龄交叉校验 = |账龄合计 - 期末余额| < 0.01 */
export function calcAgingCrossCheck(agingTotal: number, closingBalance: number): boolean {
  return Math.abs(agingTotal - closingBalance) < 0.01
}

/** Property 4: 集中度 = 金额/总额 × 100，总额=0→0 */
export function calcConcentration(amount: number, total: number): number {
  if (total === 0) return 0
  return (amount / total) * 100
}

/** Property 5: 变动率 = (本期-上期)/上期 × 100，上期=0→'N/A' */
export function calcChangeRate(current: number, prior: number): number | 'N/A' {
  if (prior === 0) return 'N/A'
  return ((current - prior) / prior) * 100
}

/** Property 6: 借贷平衡 = |SUM(debits) - SUM(credits)| < 0.01 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + v, 0)
  const c = credits.reduce((s, v) => s + v, 0)
  return Math.abs(d - c) < 0.01
}

/** Property 7: 挂账天数 = MAX(0, (当前日期 - 起始日) / 86400000) 取整 */
export function calcOutstandingDays(currentDate: Date, startDate: Date): number {
  const diff = currentDate.getTime() - startDate.getTime()
  return Math.max(0, Math.floor(diff / 86400000))
}

/** Property 8 辅助：小计求和 */
export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + v, 0)
}

// --- 兼容别名 (旧调用方保留) ---
export const calcAuditedAmount = calcAdjustedAmount
export function calcEndBalance(prior: number, debit: number, credit: number): number {
  return calcCreditBalance(prior, credit, debit)
}
export function calcChangeAmount(current: number, prior: number): number {
  return current - prior
}
export function isChangeRateExceeding(rate: number | 'N/A', threshold: number): boolean {
  if (rate === 'N/A') return false
  return Math.abs(rate) > threshold
}
