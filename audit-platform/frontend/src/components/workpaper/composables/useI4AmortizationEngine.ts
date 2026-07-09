/**
 * I4 长期待摊费用 — 摊销计算引擎（纯函数，无副作用）
 * 支持直线法 + 工作量法（H折旧引擎的子集，仅2种方法）
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Requirements: 6.4-6.5
 */

/**
 * 直线法月摊销 = 原始金额 ÷ 摊销总月数
 * @param originalAmount 原始金额（待摊费用总额）
 * @param totalMonths 摊销总月数
 * @returns 月摊销额；totalMonths <= 0 时返回 0（防御性，由调用方校验）
 */
export function calcStraightLineAmort(originalAmount: number, totalMonths: number): number {
  if (totalMonths <= 0) return 0
  return originalAmount / totalMonths
}

/**
 * 工作量法月摊销 = 原始金额 × (本月工作量 ÷ 总预计工作量)
 * @param originalAmount 原始金额（待摊费用总额）
 * @param currentUnits 本月实际工作量
 * @param totalUnits 总预计工作量
 * @returns 月摊销额；totalUnits <= 0 时返回 0（防御性，由调用方校验）
 */
export function calcUnitsOfProductionAmort(originalAmount: number, currentUnits: number, totalUnits: number): number {
  if (totalUnits <= 0) return 0
  return originalAmount * (currentUnits / totalUnits)
}

/**
 * 剩余月数 = 总月数 - 已摊月数
 * @param totalMonths 摊销总月数
 * @param elapsedMonths 已摊销月数
 * @returns 剩余月数（可能为负数表示超期，调用方自行处理）
 */
export function calcRemainingMonths(totalMonths: number, elapsedMonths: number): number {
  return totalMonths - elapsedMonths
}

/**
 * 摊销进度 = 已摊月数 ÷ 总月数
 * @param elapsed 已摊销月数（或已完成量）
 * @param total 总月数（或总量）
 * @returns 摊销进度比率 [0, ∞)；total <= 0 时返回 0
 */
export function calcAmortizationRate(elapsed: number, total: number): number {
  if (total <= 0) return 0
  return elapsed / total
}
