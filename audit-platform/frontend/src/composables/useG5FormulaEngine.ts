/**
 * useG5FormulaEngine — G5 长期应收款公式引擎
 *
 * 22 个纯函数 + parseNum，无副作用，支持 fast-check PBT 验证。
 * 科目 1531 长期应收款（借方/资产类）。
 *
 * 特色公式：
 * - 内含利率法 (G5-5): 融资收益 = 净投资额 × 内含利率
 * - 实际利率法 (G5-6): 融资收益 = 摊余成本 × 实际利率
 * - ECL公式链 (G5-10): ⑥=⑤×②A+①×(②A-②)
 * - 三阶段判定 (G5-9): Stage1/Stage2/Stage3
 */

// ═══ parseNum: 安全数值转换 ═══

/** 将 null/undefined/NaN/空串/非数字字符串 → 0，有效数字原样返回 */
export function parseNum(v: any): number {
  if (v === null || v === undefined || v === '') return 0
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isNaN(n) ? 0 : n
}

// ═══ 基础公式 ═══

/** P1: 借方余额 = 期初 + 借方 - 贷方 */
export function calcDebitBalance(opening: any, debit: any, credit: any): number {
  return parseNum(opening) + parseNum(debit) - parseNum(credit)
}

/** P2: 审定数 = 未审 + AJE + RJE */
export function calcAdjustedAmount(unadjusted: any, aje: any, rje: any): number {
  return parseNum(unadjusted) + parseNum(aje) + parseNum(rje)
}

/** P13: 净值 = 原值 - 坏账准备 */
export function calcNetValue(grossValue: any, badDebtProvision: any): number {
  return parseNum(grossValue) - parseNum(badDebtProvision)
}

/** P14: 报表列示数 = 净值 - 一年内到期 */
export function calcReportAmount(netValue: any, oneYearMaturity: any): number {
  return parseNum(netValue) - parseNum(oneYearMaturity)
}

/** P17: 变动率 = (期末-期初)/期初, 期初=0 返回 null */
export function calcChangeRate(prior: any, current: any): number | null {
  const p = parseNum(prior)
  if (p === 0) return null
  return (parseNum(current) - p) / p
}

// ═══ 融资租赁（内含利率法）═══

/** P18: 净投资额 = 应收融资租赁款 - 未实现融资收益 */
export function calcNetInvestment(receivable: any, unrealizedIncome: any): number {
  return parseNum(receivable) - parseNum(unrealizedIncome)
}

/** P3: 融资收益 = 净投资额 × 内含利率（内含利率法核心） */
export function calcLeaseFinancingIncome(netInvestment: any, implicitRate: any): number {
  return parseNum(netInvestment) * parseNum(implicitRate)
}

/** 期末应收融资租赁款 = 期初应收 - 本期收款 */
export function calcEndingReceivable(openingReceivable: any, periodCollection: any): number {
  return parseNum(openingReceivable) - parseNum(periodCollection)
}

/** 期末未实现融资收益 = 期初未实现 - 本期确认收益 */
export function calcEndingUnrealizedIncome(openingUnrealized: any, periodIncome: any): number {
  return parseNum(openingUnrealized) - parseNum(periodIncome)
}

// ═══ 分期销售（实际利率法）═══

/** P4: 融资收益 = 摊余成本 × 实际利率（实际利率法核心） */
export function calcInstallmentFinancingIncome(amortizedCost: any, effectiveRate: any): number {
  return parseNum(amortizedCost) * parseNum(effectiveRate)
}

/** P6: 期末摊余成本 = 期初摊余 + 融资收益 - 收款 */
export function calcSalesAmortizedCost(openingCost: any, income: any, collection: any): number {
  return parseNum(openingCost) + parseNum(income) - parseNum(collection)
}

// ═══ ECL 公式链 ═══

/** P11: 坏账准备 = 余额 × 损失率 (③=①×②) */
export function calcImpairmentProvision(bookBalance: any, creditLossRate: any): number {
  return parseNum(bookBalance) * parseNum(creditLossRate)
}

/** P8: 坏账调整 = 余额调整×调整后损失率 + 原余额×(调整后损失率-原损失率) (⑥=⑤×②A+①×(②A-②)) */
export function calcImpairmentAdjustment(balanceAdj: any, adjRate: any, origBalance: any, origRate: any): number {
  const ba = parseNum(balanceAdj)
  const ar = parseNum(adjRate)
  const ob = parseNum(origBalance)
  const or2 = parseNum(origRate)
  return ba * ar + ob * (ar - or2)
}

/** 审定余额 = 原余额 + 余额调整 (⑦=①+⑤) */
export function calcAdjustedBalance(orig: any, adj: any): number {
  return parseNum(orig) + parseNum(adj)
}

/** 审定坏账准备 = 未审坏账 + 坏账调整 (⑧=③+⑥) */
export function calcAdjustedImpairment(origImpairment: any, impairmentAdj: any): number {
  return parseNum(origImpairment) + parseNum(impairmentAdj)
}

/** P7: 审定账面价值 = 审定余额 - 审定坏账 (⑨=⑦-⑧) */
export function calcAdjustedBookValue(adjBalance: any, adjImpairment: any): number {
  return parseNum(adjBalance) - parseNum(adjImpairment)
}

// ═══ 三阶段判定 ═══

/** P9/P10: 三阶段划分 — Stage3优先 */
export function determineStage(
  hasSignificantIncrease: boolean,
  hasLowCreditRisk: boolean,
  hasCreditImpairment: boolean,
): 'Stage1' | 'Stage2' | 'Stage3' {
  if (hasCreditImpairment) return 'Stage3'
  if (hasSignificantIncrease && !hasLowCreditRisk) return 'Stage2'
  return 'Stage1'
}

// ═══ 校验函数 ═══

/** P11: 借贷平衡 — |SUM(debits)-SUM(credits)| < 0.01 */
export function isDebitCreditBalanced(debits: any[], credits: any[]): boolean {
  const sumD = (debits || []).reduce((s, v) => s + parseNum(v), 0)
  const sumC = (credits || []).reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}

/** P12: 转回有效性 — 转回金额 ≤ 累计计提 */
export function isReversalValid(reversalAmount: any, accumulatedProvision: any): boolean {
  return parseNum(reversalAmount) <= parseNum(accumulatedProvision)
}

/** P15: 账龄合计 = 各账龄段之和 */
export function calcAgingTotal(y1: any, y2: any, y3: any, y4: any, y5: any, y5plus: any): number {
  return parseNum(y1) + parseNum(y2) + parseNum(y3) + parseNum(y4) + parseNum(y5) + parseNum(y5plus)
}

/** 本年计提 = 审定坏账 - 上年坏账 + 本年转回 */
export function calcCurrentYearProvision(adjustedProvision: any, priorYear: any, reversal: any): number {
  return parseNum(adjustedProvision) - parseNum(priorYear) + parseNum(reversal)
}
