/**
 * H9 租赁负债 — 现值计算引擎（纯函数，无副作用）
 * 核心：CAS21 §14 租赁负债 = 未来租赁付款额的现值
 * - 现值折现：PV = Σ(payment_i / (1+rate)^i)
 * - 等额年金现值：PV = payment × (1 - (1+rate)^(-n)) / rate
 * - 增量借款利率(IBR)：市场基准 + 信用利差 + 期限调整
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Requirements: 6.1-6.4
 */

// ═══ 核心纯函数 ═══

/**
 * 现值计算（不等额付款）
 * CAS21 §14：租赁负债应当按照租赁期开始日尚未支付的租赁付款额的现值进行初始计量。
 * PV = Σ(payments[i] / (1+rate)^(i+1))，i=0..n-1
 *
 * @param payments 各期付款金额数组
 * @param rate 每期折现率（非年化，已按付款频率折算）
 * @returns 现值合计
 *
 * 边界情况：
 * - rate=0 → PV = sum of all payments（零利率恒等，Property P8）
 * - 空数组 → 0
 */
export function calcPresentValue(payments: number[], rate: number): number {
  if (payments.length === 0) return 0
  if (rate === 0) return payments.reduce((a, b) => a + b, 0)

  let pv = 0
  for (let i = 0; i < payments.length; i++) {
    pv += payments[i] / Math.pow(1 + rate, i + 1)
  }
  return pv
}

/**
 * 等额年金现值（普通年金）
 * PV = payment × (1 - (1+rate)^(-periods)) / rate
 * CAS21 §14 等额付款简化公式。
 *
 * @param payment 每期等额付款
 * @param rate 每期折现率（>0 时使用年金公式；=0 时退化为 payment×periods）
 * @param periods 总期数
 * @returns 年金现值
 *
 * 边界情况：
 * - rate=0 → payment × periods
 * - periods=0 → 0
 * - payment=0 → 0
 */
export function calcAnnuityPV(payment: number, rate: number, periods: number): number {
  if (periods <= 0) return 0
  if (payment === 0) return 0
  if (rate === 0) return payment * periods

  return payment * (1 - Math.pow(1 + rate, -periods)) / rate
}

/**
 * 增量借款利率(IBR)确定
 * IBR = 市场基准利率 + 信用利差 + 期限调整
 * CAS21 §15：增量借款利率是指承租人在类似经济环境下为获得与使用权资产价值
 * 接近的资产、在类似期限以类似抵押条件借入资金须支付的利率。
 * 审计判断优先，引擎辅助。
 *
 * @param marketRate 市场基准利率（如LPR/国债收益率）
 * @param creditSpread 信用利差（反映承租人信用风险）
 * @param termAdjust 期限调整（反映租赁期限对利率的影响）
 * @returns 增量借款利率
 */
export function calcIBR(marketRate: number, creditSpread: number, termAdjust: number): number {
  return marketRate + creditSpread + termAdjust
}

/**
 * 隐含利率（IRR）反推 — Newton-Raphson 迭代法
 * 给定现值(PV)和各期付款(payments)，反推每期折现率 rate 使得 PV = Σ(payments[i]/(1+rate)^(i+1))
 *
 * CAS21 §14：当租赁内含利率无法确定时，使用承租人增量借款利率(IBR)。
 * 本函数用于验证：已知初始确认金额(PV)和付款计划(payments)，反推验证IBR是否合理。
 *
 * @param payments 各期付款金额数组
 * @param presentValue 已知现值（租赁负债初始确认金额）
 * @param initialGuess 初始猜测利率（默认 0.005 即月利率 0.5%）
 * @param maxIterations 最大迭代次数（默认 100）
 * @param tolerance 收敛容差（默认 1e-8）
 * @returns 每期折现率（如月利率 0.004167 = 5%年化/12月），无法收敛时返回 NaN
 *
 * 边界情况：
 * - payments 为空 → NaN
 * - presentValue <= 0 → NaN
 * - 等额付款等价于求解年金利率
 */
export function calcImpliedRate(
  payments: number[],
  presentValue: number,
  initialGuess = 0.005,
  maxIterations = 100,
  tolerance = 1e-8,
): number {
  if (payments.length === 0 || presentValue <= 0) return NaN
  const totalPayments = payments.reduce((a, b) => a + b, 0)
  // 如果付款总额 <= 现值，利率为零或负（不合理）
  if (totalPayments <= presentValue) return 0

  let rate = initialGuess

  for (let iter = 0; iter < maxIterations; iter++) {
    // f(rate) = Σ(payments[i] / (1+rate)^(i+1)) - PV
    let f = -presentValue
    let fPrime = 0

    for (let i = 0; i < payments.length; i++) {
      const exp = i + 1
      const denom = Math.pow(1 + rate, exp)
      f += payments[i] / denom
      // f'(rate) = Σ(-payments[i] * (i+1) / (1+rate)^(i+2))
      fPrime -= payments[i] * exp / Math.pow(1 + rate, exp + 1)
    }

    if (Math.abs(f) < tolerance) return rate
    if (fPrime === 0) break // 避免除零

    const newRate = rate - f / fPrime
    // 利率不能为负
    if (newRate <= -1) {
      rate = rate / 2
      continue
    }
    rate = newRate
  }

  return NaN // 未收敛
}

/**
 * 将每期利率转换为年化利率
 * @param periodRate 每期利率（如月利率 0.004167）
 * @param periodsPerYear 每年期数（月付=12，季付=4，年付=1）
 * @returns 年化利率（如 0.05 = 5%）
 */
export function annualizeRate(periodRate: number, periodsPerYear = 12): number {
  if (periodRate === 0) return 0
  // 有效年利率 = (1 + periodRate)^periodsPerYear - 1
  return Math.pow(1 + periodRate, periodsPerYear) - 1
}

// ═══ 摊销表验证 ═══

/** 摊销表单行 */
export interface AmortScheduleRow {
  period: number
  /** 期初余额 */
  openingBalance: number
  /** 利息费用 = 期初 × 每期利率 */
  interestExpense: number
  /** 租赁付款额（含利息+本金） */
  payment: number
  /** 本金偿还 = 付款 - 利息 */
  principalRepayment: number
  /** 期末余额 = 期初 - 本金偿还 */
  closingBalance: number
}

/**
 * 生成实际利率法摊销表
 * CAS21 核心：每期利息费用 = 期初余额 × 实际利率（IBR）
 *
 * @param initialBalance 租赁负债初始确认金额（现值）
 * @param periodRate 每期实际利率
 * @param payments 各期付款金额数组（等额时可传相同值）
 * @returns 摊销表行数组
 */
export function buildAmortizationSchedule(
  initialBalance: number,
  periodRate: number,
  payments: number[],
): AmortScheduleRow[] {
  if (initialBalance <= 0 || payments.length === 0) return []

  const schedule: AmortScheduleRow[] = []
  let balance = initialBalance

  for (let i = 0; i < payments.length; i++) {
    const interest = balance * periodRate
    const payment = payments[i]
    const principal = payment - interest
    const closing = balance - principal

    schedule.push({
      period: i + 1,
      openingBalance: Math.round(balance * 100) / 100,
      interestExpense: Math.round(interest * 100) / 100,
      payment: Math.round(payment * 100) / 100,
      principalRepayment: Math.round(principal * 100) / 100,
      closingBalance: Math.round(closing * 100) / 100,
    })

    balance = closing
    // 余额归零后停止
    if (balance <= 0.01) break
  }

  return schedule
}

/**
 * 验证账面摊销与测算摊销的差异
 * @param bookInterest 账面本期利息费用（H9-1/H9-3 审定）
 * @param schedule 测算摊销表
 * @param currentPeriods 本期期数（年报通常12期，短期则按实际月数）
 * @returns 差异分析
 */
export function verifyAmortizationInterest(
  bookInterest: number,
  schedule: AmortScheduleRow[],
  currentPeriods = 12,
): { expectedInterest: number; diff: number; diffRate: number; isReasonable: boolean } {
  const periods = Math.min(currentPeriods, schedule.length)
  const expectedInterest = schedule.slice(0, periods).reduce((s, r) => s + r.interestExpense, 0)
  const diff = bookInterest - expectedInterest
  const diffRate = expectedInterest !== 0 ? Math.abs(diff) / expectedInterest : 0

  return {
    expectedInterest: Math.round(expectedInterest * 100) / 100,
    diff: Math.round(diff * 100) / 100,
    diffRate,
    // 容差：差异率<5% 或 差额<100元 视为合理（四舍五入/日期差异导致）
    isReasonable: diffRate < 0.05 || Math.abs(diff) < 100,
  }
}
