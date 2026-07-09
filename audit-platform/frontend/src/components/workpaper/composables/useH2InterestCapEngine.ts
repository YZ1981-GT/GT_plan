/**
 * H2 在建工程 — 利息资本化引擎（纯函数，无副作用）
 * 2分支：无专门借款（加权资本化率×累计支出加权）/ 有专门借款（利息-闲置收益+一般借款补充）
 * CAS17借款费用准则
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Requirements: 10.4, 10.5, 12.4
 */

// ---------- 无专门借款分支 ----------

/**
 * 加权资本化率 = Σ(principal × rate × days/365) / Σ(principal × days/365)
 * 本质：按本金加权天数加权的利率
 * 分母为0时返回0（无有效借款数据）
 */
export function calcWeightedCapRate(
  loans: { principal: number; rate: number; days: number }[],
): number {
  let numerator = 0
  let denominator = 0
  for (const loan of loans) {
    const weight = loan.principal * loan.days / 365
    numerator += weight * loan.rate
    denominator += weight
  }
  if (denominator === 0) return 0
  return numerator / denominator
}

/**
 * 累计支出加权平均数 = Σ(amount × days) / totalDays
 * 各笔支出按其资金占用天数加权
 * totalDays为0时返回0（避免除零）
 */
export function calcWeightedExpenditure(
  expenditures: { amount: number; days: number }[],
  totalDays: number,
): number {
  if (totalDays === 0) return 0
  let weightedSum = 0
  for (const exp of expenditures) {
    weightedSum += exp.amount * exp.days
  }
  return weightedSum / totalDays
}

/**
 * 无专门借款资本化金额 = 累计支出加权平均数 × 加权资本化率
 */
export function calcCapAmountNoBorrow(weightedExp: number, capRate: number): number {
  return weightedExp * capRate
}

// ---------- 有专门借款分支 ----------

/**
 * 专门借款资本化金额 = 专门借款利息 - 闲置资金投资收益
 * CAS17：尚未动用的专门借款的闲置投资收益应从资本化金额中扣除
 */
export function calcSpecialLoanCap(interest: number, idleIncome: number): number {
  return interest - idleIncome
}

/**
 * 一般借款补充资本化 = 超出专门借款的累计支出加权平均数 × 一般借款加权资本化率
 * 当累计支出超过专门借款金额时，超出部分按一般借款利率资本化
 */
export function calcGeneralLoanSupp(excessWeightedExp: number, generalCapRate: number): number {
  return excessWeightedExp * generalCapRate
}

/**
 * 有专门借款合计资本化金额 = 专门借款资本化 + 一般借款补充资本化
 */
export function calcTotalCapWithBorrow(specialCap: number, generalSupp: number): number {
  return specialCap + generalSupp
}

// ---------- DCF / 终值（减值测算辅助） ----------

/**
 * DCF现值 = Σ(cf_i / (1 + discountRate)^(i+1))  for i = 0..n-1
 * 各期现金流按折现率逐年折现求和
 * 空数组返回0；折现率≤0时返回0
 */
export function calcDcfPresentValue(cashFlows: number[], discountRate: number): number {
  if (cashFlows.length === 0 || discountRate <= 0) return 0
  let pv = 0
  for (let i = 0; i < cashFlows.length; i++) {
    pv += cashFlows[i] / Math.pow(1 + discountRate, i + 1)
  }
  return pv
}

/**
 * 终值（永续增长模型）= perpetuityCF / (discountRate - growthRate)
 * Gordon Growth Model
 * 当 discountRate ≤ growthRate 时模型无效，返回0
 */
export function calcTerminalValue(
  perpetuityCF: number,
  discountRate: number,
  growthRate: number,
): number {
  if (discountRate <= growthRate) return 0
  return perpetuityCF / (discountRate - growthRate)
}
