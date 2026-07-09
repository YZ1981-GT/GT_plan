/**
 * I3 商誉 — DCF纯函数引擎（无副作用，无Vue响应式依赖）
 *
 * 5个纯函数，支持 fast-check PBT 验证。
 *
 * 核心公式：
 * - 现值(PV) = Σ(FCF_i / (1+WACC)^(i+1)) + TV / (1+WACC)^n
 * - 终值(TV) = FCF_n × (1+g) / (WACC - g)  （永续增长模型 / Gordon Growth Model）
 * - WACC = E/V × Re + D/V × Rd × (1-T)
 * - 可收回金额 = MAX(公允价值-处置费用, 使用价值DCF)
 * - 敏感性 = 重新计算PV（调整折现率后）
 *
 * 错误处理：
 * - 折现率 ≤ 0 → 返回0（无法折现）
 * - 折现率 ≤ 增长率 → 阻止终值计算，返回0
 * - 空现金流数组 → 返回0
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Requirements: 6.2-6.5
 */

// ═══ P5: DCF现值 = Σ(CF_i / (1+r)^(i+1)) ═══

/**
 * 折现现金流现值计算
 * PV = Σ(cashFlows[i] / (1 + discountRate)^(i+1))  for i = 0..n-1
 *
 * @param cashFlows - 各期自由现金流数组（第0期到第n-1期）
 * @param discountRate - 折现率（WACC），如0.10表示10%
 * @returns 现值合计；空数组或折现率≤0时返回0
 */
export function calcDcfPresentValue(cashFlows: number[], discountRate: number): number {
  if (cashFlows.length === 0 || discountRate <= 0) return 0
  let pv = 0
  for (let i = 0; i < cashFlows.length; i++) {
    pv += cashFlows[i] / Math.pow(1 + discountRate, i + 1)
  }
  return pv
}

// ═══ 终值（永续增长模型 / Gordon Growth Model） ═══

/**
 * 终值计算：TV = FCF_n × (1+g) / (WACC - g)
 *
 * @param fcf - 最后一期自由现金流（FCF_n）
 * @param growthRate - 永续增长率g，如0.03表示3%
 * @param discountRate - 折现率WACC，如0.10表示10%
 * @returns 终值；当discountRate ≤ growthRate时模型无效，返回0
 */
export function calcTerminalValue(fcf: number, growthRate: number, discountRate: number): number {
  if (discountRate <= growthRate) return 0
  return (fcf * (1 + growthRate)) / (discountRate - growthRate)
}

// ═══ WACC = E/V × Re + D/V × Rd × (1-T) ═══

/**
 * 加权平均资本成本(WACC)计算
 *
 * @param equityRatio - 权益占比 E/V（如0.6表示60%）
 * @param debtRatio - 负债占比 D/V（如0.4表示40%）
 * @param costOfEquity - 权益成本 Re（如0.12表示12%）
 * @param costOfDebt - 债务成本 Rd（如0.05表示5%）
 * @param taxRate - 所得税税率 T（如0.25表示25%）
 * @returns WACC值
 */
export function calcWacc(
  equityRatio: number,
  debtRatio: number,
  costOfEquity: number,
  costOfDebt: number,
  taxRate: number,
): number {
  return equityRatio * costOfEquity + debtRatio * costOfDebt * (1 - taxRate)
}

// ═══ P6: 可收回金额 = MAX(公允价值-处置费用, 使用价值DCF) ═══

/**
 * 可收回金额 = MAX(公允价值减处置费用, 使用价值/DCF)
 * CAS8规定取两者孰高
 *
 * @param fairValueLessDisposal - 公允价值减去处置费用
 * @param valueInUse - 使用价值（DCF计算结果）
 * @returns 可收回金额
 */
export function calcRecoverableAmount(fairValueLessDisposal: number, valueInUse: number): number {
  return Math.max(fairValueLessDisposal, valueInUse)
}

// ═══ 敏感性分析：调整折现率后重新计算PV ═══

/**
 * 敏感性分析：以基准PV为参照，按调整后的折现率重新计算PV
 * 用于 WACC±1% / 增长率±0.5% / 收入±10% 场景
 *
 * @param basePV - 基准现值（用于对比，本函数仅返回新PV）
 * @param cashFlows - 各期自由现金流数组
 * @param baseRate - 基准折现率
 * @param rateChange - 折现率变动量（如+0.01表示+1%，-0.01表示-1%）
 * @returns 调整后的现值；若调整后折现率≤0则返回0
 */
export function calcSensitivity(
  basePV: number,
  cashFlows: number[],
  baseRate: number,
  rateChange: number,
): number {
  const adjustedRate = baseRate + rateChange
  return calcDcfPresentValue(cashFlows, adjustedRate)
}
