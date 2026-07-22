/**
 * H2 在建工程 — 利息资本化引擎（纯函数，无副作用）
 * 2分支：无专门借款（加权资本化率×累计支出加权）/ 有专门借款（利息-闲置收益+一般借款补充）
 * CAS17借款费用准则
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Requirements: 10.4, 10.5, 12.4
 */

// ---------- 无专门借款分支 ----------

/**
 * 单笔一般借款本金加权平均数 = 本金 × 本期计息天数 / 当期天数
 * 对齐 xlsx H2-10：G = B × E / F
 */
export function calcWeightedPrincipal(
  principal: number,
  interestDays: number,
  periodDays: number,
): number {
  if (periodDays <= 0) return 0
  return principal * interestDays / periodDays
}

/**
 * 加权资本化率 = Σ(principal × rate × days/365) / Σ(principal × days/365)
 * rate 为小数形式（0.05 = 5%）
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
 * 按账面实际利息倒算资本化率（xlsx H2-10 主口径）
 * 资本化率 = Σ实际利息费用 / Σ本金加权平均数
 */
export function calcCapRateFromActualInterest(
  loans: { weightedPrincipal: number; actualInterest: number }[],
): number {
  let interestSum = 0
  let weightedSum = 0
  for (const loan of loans) {
    interestSum += loan.actualInterest
    weightedSum += loan.weightedPrincipal
  }
  if (weightedSum === 0) return 0
  return interestSum / weightedSum
}

/**
 * 累计支出加权平均数 = Σ(amount × days) / totalDays
 * 各笔支出按其资金占用天数加权（日加权法）
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

/** 月度工程支出行（对齐 xlsx H2-10/H2-11 第二节） */
export interface MonthlyExpInput {
  /** 前期开发(1) */
  prelimDev: number
  /** 工程费用(2) */
  engCost: number
  /** 借款费用(3) — 账面资本化利息也落此列 */
  borrowCost: number
  /** 建安工程(4) */
  install: number
  /** 土地(5) */
  land: number
  /** 本年减少(7) */
  decrease: number
  /** 预付工程款(8) */
  prepaid: number
  /**
   * 专门借款已占用额 SP（仅 H2-11）
   * 一般借款资本化基数须扣除本项；H2-10 可不填（视为 0）
   */
  specialLoanUsed?: number
}

/**
 * 工程支出合计(6) = (1)+(2)+(3)+(4)+(5)
 */
export function calcExpTotal(row: MonthlyExpInput): number {
  return row.prelimDev + row.engCost + row.borrowCost + row.install + row.land
}

/**
 * 月度加权平均支出链（xlsx 半月平均法）
 * H2-10 年初：J0 = G0 + I0 - D0
 * H2-11 年初：J0 = max(0, G0 + I0 - D0 - SP0)
 * 各月：Jt = max(0, J(t-1) + (Gt - Ht - Dt + It - SPt) / 2)
 * @param deductSpecialLoan 为 true 时按 H2-11 扣减 SP
 */
export function calcMonthlyWeightedExpChain(
  opening: MonthlyExpInput,
  months: MonthlyExpInput[],
  deductSpecialLoan = false,
): { openingWeighted: number; monthlyWeighted: number[] } {
  const g0 = calcExpTotal(opening)
  const sp0 = deductSpecialLoan ? (opening.specialLoanUsed ?? 0) : 0
  let openingWeighted = g0 + opening.prepaid - opening.borrowCost - sp0
  if (deductSpecialLoan) openingWeighted = Math.max(0, openingWeighted)
  const monthlyWeighted: number[] = []
  let prev = openingWeighted
  for (const m of months) {
    const g = calcExpTotal(m)
    const sp = deductSpecialLoan ? (m.specialLoanUsed ?? 0) : 0
    let w = prev + (g - m.decrease - m.borrowCost + m.prepaid - sp) / 2
    if (deductSpecialLoan) w = Math.max(0, w)
    monthlyWeighted.push(w)
    prev = w
  }
  return { openingWeighted, monthlyWeighted }
}

/**
 * 无专门借款资本化金额 = 累计支出加权平均数 × 加权资本化率
 * capRate 为小数（年利率或月利率，与加权支出期间口径一致）
 */
export function calcCapAmountNoBorrow(weightedExp: number, capRate: number): number {
  return weightedExp * capRate
}

/**
 * 年利率 → 月利率（简化：/12；精确日法则由调用方自行换算）
 */
export function annualRateToMonthly(annualRate: number): number {
  return annualRate / 12
}

// ---------- 有专门借款分支 ----------

/**
 * 专门借款资本化金额 = 专门借款利息 - 闲置资金投资收益
 * CAS17：尚未动用的专门借款的闲置投资收益应从资本化金额中扣除
 * 下限为 0（闲置收益超过利息时不产生负资本化）
 */
export function calcSpecialLoanCap(interest: number, idleIncome: number): number {
  return Math.max(0, interest - idleIncome)
}

/**
 * 一般借款补充资本化 = 超出专门借款的累计支出加权平均数 × 一般借款加权资本化率
 * 当累计支出超过专门借款金额时，超出部分按一般借款利率资本化
 * 超额支出 ≤ 0 时返回 0
 */
export function calcGeneralLoanSupp(excessWeightedExp: number, generalCapRate: number): number {
  if (excessWeightedExp <= 0 || generalCapRate === 0) return 0
  return excessWeightedExp * generalCapRate
}

/**
 * 累计资产支出加权平均数超过专门借款的部分（一般借款资本化基数）
 * excess = max(weightedExp - specialLoanAmount, 0)
 */
export function calcExcessWeightedExp(weightedExp: number, specialLoanAmount: number): number {
  return Math.max(0, weightedExp - specialLoanAmount)
}

/**
 * 差异率 = 差异 / 应予资本化合计；分母为 0 时返回 null（对应 Excel 显示「—」，避免 #DIV/0!）
 */
export function calcCapDiffRate(difference: number, totalCap: number): number | null {
  if (Math.abs(totalCap) < 1e-9) return null
  return difference / totalCap
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
