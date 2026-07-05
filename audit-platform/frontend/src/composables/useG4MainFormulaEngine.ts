/**
 * G4 债权投资(main) — 公式引擎（借方/资产类科目 1501）
 *
 * 14个纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 *
 * 核心公式链：
 * - 借方余额：期初 + 借方 - 贷方（资产类）
 * - 余额小计：成本 + 利息调整 + 应计利息
 * - 摊余成本：账面余额小计 - 减值准备
 * - 实际利率法：摊余成本 × 实际利率 [× days/365]
 * - 期末账面：期初 + 利息收入 - 现金流入 - 已收回本金
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Requirements 8.1~8.15
 */

// ═══ parseNum: 安全数值转换（null/undefined/NaN/空串 → 0）═══

export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ═══ P1: 借方余额 = 期初 + 借方 - 贷方 ═══

export function calcDebitBalance(opening: number, debit: number, credit: number): number {
  return parseNum(opening) + parseNum(debit) - parseNum(credit)
}

// ═══ P2: 审定数 = 未审 + AJE + RJE ═══

export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number {
  return parseNum(unadjusted) + parseNum(aje) + parseNum(rje)
}

// ═══ P3: 余额小计 = 成本 + 利息调整 + 应计利息 ═══

export function calcBalanceSubtotal(cost: number, interestAdjustment: number, accruedInterest: number): number {
  return parseNum(cost) + parseNum(interestAdjustment) + parseNum(accruedInterest)
}

// ═══ P4: 摊余成本 = 账面余额小计 - 减值准备 ═══

export function calcAmortizedCost(bookBalanceSubtotal: number, impairment: number): number {
  return parseNum(bookBalanceSubtotal) - parseNum(impairment)
}

// ═══ P5: 实际利息收入（整年 or 按天数） ═══

export function calcEffectiveInterest(amortizedCost: number, effectiveRate: number, days?: number): number {
  const cost = parseNum(amortizedCost)
  const rate = parseNum(effectiveRate)
  if (days === undefined || days === null) return cost * rate
  return cost * rate * parseNum(days) / 365
}

// ═══ P6: 现金流入 = 面值 × 票面利率 [× days/365] ═══

export function calcCashInflow(faceValue: number, couponRate: number, days?: number): number {
  const face = parseNum(faceValue)
  const rate = parseNum(couponRate)
  if (days === undefined || days === null) return face * rate
  return face * rate * parseNum(days) / 365
}

// ═══ P7: 期末账面总额 = 期初 + 利息收入 - 现金流入 - 已收回本金 ═══

export function calcEndingBalance(opening: number, effectiveInterest: number, cashInflow: number, principalRepaid: number): number {
  return parseNum(opening) + parseNum(effectiveInterest) - parseNum(cashInflow) - parseNum(principalRepaid)
}

// ═══ P8: 初始入账价值 = 购买对价 + 交易费用 ═══

export function calcInitialCarryingAmount(purchasePrice: number, transactionCost: number): number {
  return parseNum(purchasePrice) + parseNum(transactionCost)
}

// ═══ P9: 借贷平衡判断 — |SUM(debits) - SUM(credits)| < 0.01 ═══

export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}

// ═══ P10: 期末分项 = 期初 + 变动（成本/利息调整/应计利息通用） ═══

export function calcPeriodEndComponent(openingComponent: number, periodChange: number): number {
  return parseNum(openingComponent) + parseNum(periodChange)
}

// ═══ P11: 变动率 = (current - prior) / prior，prior=0时返回null ═══

export function calcChangeRate(prior: number, current: number): number | null {
  const p = parseNum(prior)
  if (p === 0) return null
  return (parseNum(current) - p) / p
}

// ═══ P12: 一年内到期小计 = 账面余额 - 减值 ═══

export function calcOneYearMaturity(bookBalanceSubtotal: number, impairment: number): number {
  return parseNum(bookBalanceSubtotal) - parseNum(impairment)
}

// ═══ P13: 账面价值 = 摊余成本 - 一年内到期小计 ═══

export function calcBookValue(amortizedCost: number, oneYearMaturity: number): number {
  return parseNum(amortizedCost) - parseNum(oneYearMaturity)
}
