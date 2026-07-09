/**
 * K2 其他流动资产 — 摊销测算引擎（纯函数，无副作用）
 *
 * 支持两种摊销方法：
 * 1. 直线法：cost / totalPeriods × currentPeriods（以"月"为单位）
 * 2. 进度法：cost × (currentProgress - priorProgress)
 *
 * Spec: .kiro/specs/k2-other-current-assets/ Requirements 5.2-5.5, 8.3-8.5
 */

/** NaN 安全：将 NaN 视为 0 */
function safe(v: number): number {
  return Number.isNaN(v) ? 0 : v
}

/**
 * 直线法摊销 = cost / totalPeriods × currentPeriods
 * totalPeriods = 使用月限（摊销期总月数）
 * currentPeriods = 本期摊销月份
 *
 * 特殊处理：totalPeriods=0 → 返回0（兜底，避免除以零）
 * @param cost 合同取得成本
 * @param totalPeriods 摊销期总期数（月）
 * @param currentPeriods 本期期数（月）
 * @returns 本期应摊销金额
 */
export function calcStraightLineAmort(cost: number, totalPeriods: number, currentPeriods: number): number {
  const c = safe(cost)
  const tp = safe(totalPeriods)
  const cp = safe(currentPeriods)
  if (tp === 0) return 0
  return (c / tp) * cp
}

/**
 * 进度法摊销 = cost × (currentProgress - priorProgress)
 * currentProgress/priorProgress 为 0~1 之间的履约进度比例
 *
 * 特殊处理：currentProgress < priorProgress → 返回0（进度回退兜底）
 * @param cost 合同取得成本
 * @param currentProgress 本期累计履约进度（0~1）
 * @param priorProgress 上期累计履约进度（0~1）
 * @returns 本期应摊销金额
 */
export function calcProgressAmort(cost: number, currentProgress: number, priorProgress: number): number {
  const c = safe(cost)
  const cp = safe(currentProgress)
  const pp = safe(priorProgress)
  if (cp < pp) return 0
  return c * (cp - pp)
}

/**
 * 摊余成本 = cost - accumulated
 * @param cost 合同取得成本（原值）
 * @param accumulated 累计已摊销金额
 * @returns 摊余成本（账面净值）
 */
export function calcAmortizedBalance(cost: number, accumulated: number): number {
  return safe(cost) - safe(accumulated)
}

/**
 * 摊销差异 = calculated - booked
 * 正值表示测算>企业账面（企业少摊），负值表示测算<企业账面（企业多摊）
 * @param calculated 测算应摊销金额
 * @param booked 企业账面已摊销金额
 * @returns 差异金额
 */
export function calcAmortVariance(calculated: number, booked: number): number {
  return safe(calculated) - safe(booked)
}
