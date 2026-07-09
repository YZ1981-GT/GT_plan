/**
 * H1 固定资产 — 折旧计算引擎（纯函数，无副作用）
 * 支持4种折旧方法 + 含减值折旧 + DCF现值 + 终值 + 单调性校验
 * Spec: .kiro/specs/h1-fixed-assets/
 * Requirements: 11.5, 13.4
 */

/**
 * 直线法月折旧 = 原值 × (1 - 残值率) / 使用年限 / 12
 * @param cost 资产原值
 * @param salvageRate 残值率 (0~1)
 * @param usefulLifeYears 使用年限（年）
 * @returns 月折旧额；usefulLifeYears <= 0 时返回 0
 */
export function calcStraightLine(cost: number, salvageRate: number, usefulLifeYears: number): number {
  if (usefulLifeYears <= 0) return 0
  return cost * (1 - salvageRate) / usefulLifeYears / 12
}

/**
 * 双倍余额递减法月折旧
 * - 前期：netValue × 2 / usefulLifeYears / 12
 * - 最后两年(24个月)：转为直线法，(netValue - salvage) / 剩余月数
 *   此处简化为 netValue × 2 / usefulLifeYears / 12 在前期适用，
 *   最后24个月时切换为 (netValue) / 剩余月数（残值已在netValue中扣除由调用方处理）
 *
 * 注意：按中国CAS惯例，最后两年改用直线法，年折旧 = (净值 - 残值) / 2，
 * 但此函数接收的netValue已经是扣除残值前的账面净值，最后24个月按
 * netValue / 剩余月数(=totalMonths - elapsedMonths) 计算
 *
 * @param netValue 当前账面净值（原值 - 已计提累计折旧）
 * @param usefulLifeYears 使用年限（年）
 * @param elapsedMonths 已使用月数
 * @param totalMonths 总使用月数 (= usefulLifeYears × 12)
 * @returns 当月折旧额；usefulLifeYears <= 0 或 totalMonths <= 0 时返回 0
 */
export function calcDoubleDeclining(
  netValue: number,
  usefulLifeYears: number,
  elapsedMonths: number,
  totalMonths: number
): number {
  if (usefulLifeYears <= 0 || totalMonths <= 0) return 0
  // 最后24个月转直线法
  if (elapsedMonths >= totalMonths - 24) {
    const remainingMonths = totalMonths - elapsedMonths
    if (remainingMonths <= 0) return 0
    return netValue / remainingMonths
  }
  // 前期：双倍余额递减
  return netValue * 2 / usefulLifeYears / 12
}

/**
 * 年数总和法月折旧 = 原值 × (1 - 残值率) × 剩余年限 / 年数总和 / 12
 * 年数总和 = usefulLifeYears × (usefulLifeYears + 1) / 2
 * @param cost 资产原值
 * @param salvageRate 残值率 (0~1)
 * @param usefulLifeYears 使用年限（年）
 * @param remainingYears 剩余使用年限
 * @returns 月折旧额；usefulLifeYears <= 0 时返回 0
 */
export function calcSumOfYears(
  cost: number,
  salvageRate: number,
  usefulLifeYears: number,
  remainingYears: number
): number {
  if (usefulLifeYears <= 0) return 0
  const sumOfYears = usefulLifeYears * (usefulLifeYears + 1) / 2
  return cost * (1 - salvageRate) * remainingYears / sumOfYears / 12
}

/**
 * 工作量法月折旧 = 原值 × (1 - 残值率) / 总工作量 × 当月工作量
 * @param cost 资产原值
 * @param salvageRate 残值率 (0~1)
 * @param totalUnits 预计总工作量
 * @param currentUnits 当月实际工作量
 * @returns 当月折旧额；totalUnits <= 0 时返回 0
 */
export function calcUnitsOfProduction(
  cost: number,
  salvageRate: number,
  totalUnits: number,
  currentUnits: number
): number {
  if (totalUnits <= 0) return 0
  return cost * (1 - salvageRate) / totalUnits * currentUnits
}

/**
 * 含减值折旧（直线法接力）：
 * 减值发生后，以减值后的可折旧金额重新计算剩余月份的直线折旧
 * 可折旧金额 = 原值 - 残值 - 减值准备 = cost × (1 - salvageRate) - impairment
 * 月折旧 = 可折旧金额 / 剩余月数
 * @param cost 资产原值
 * @param salvageRate 残值率 (0~1)
 * @param usefulLifeYears 使用年限（年）
 * @param impairment 已计提减值准备
 * @param elapsedMonths 减值时已使用月数
 * @returns 减值后月折旧额；剩余月数 <= 0 时返回 0
 */
export function calcDepreciationWithImpairment(
  cost: number,
  salvageRate: number,
  usefulLifeYears: number,
  impairment: number,
  elapsedMonths: number
): number {
  const totalMonths = usefulLifeYears * 12
  const remainingMonths = totalMonths - elapsedMonths
  if (remainingMonths <= 0) return 0
  const depreciableAmount = cost * (1 - salvageRate) - impairment
  return depreciableAmount / remainingMonths
}

/**
 * DCF现值 = Σ(cashFlow_i / (1 + discountRate)^(i+1))
 * @param cashFlows 各期现金流数组（第0期对应第1年末）
 * @param discountRate 折现率 (如0.08表示8%)
 * @returns 现值合计；空数组返回0；discountRate <= -1 返回0（避免除零/负底数）
 */
export function calcDcfPresentValue(cashFlows: number[], discountRate: number): number {
  if (cashFlows.length === 0) return 0
  if (discountRate <= -1) return 0
  let pv = 0
  for (let i = 0; i < cashFlows.length; i++) {
    pv += cashFlows[i] / Math.pow(1 + discountRate, i + 1)
  }
  return pv
}

/**
 * 终值（永续价值） = 永续现金流 / (折现率 - 增长率)
 * Gordon Growth Model
 * @param perpetuityCF 永续年金现金流（预测期最后一年的稳态现金流）
 * @param discountRate 折现率
 * @param growthRate 永续增长率
 * @returns 终值；当 discountRate <= growthRate 时返回 0（避免无穷/负值）
 */
export function calcTerminalValue(perpetuityCF: number, discountRate: number, growthRate: number): number {
  if (discountRate <= growthRate) return 0
  return perpetuityCF / (discountRate - growthRate)
}

/**
 * 单调性校验：累计折旧序列是否严格递增（排除处置月份）
 * @param monthlyAccumulated 月末累计折旧数组
 * @param disposalMonths 处置月份索引数组（0-based，这些月份允许不递增）
 * @returns true表示满足单调递增；length < 2 时返回 true
 */
export function isMonotonicallyIncreasing(monthlyAccumulated: number[], disposalMonths: number[]): boolean {
  if (monthlyAccumulated.length < 2) return true
  const disposalSet = new Set(disposalMonths)
  for (let i = 0; i < monthlyAccumulated.length - 1; i++) {
    // 如果当前月或下一月是处置月份，跳过此对比
    if (disposalSet.has(i) || disposalSet.has(i + 1)) continue
    if (monthlyAccumulated[i] >= monthlyAccumulated[i + 1]) return false
  }
  return true
}
