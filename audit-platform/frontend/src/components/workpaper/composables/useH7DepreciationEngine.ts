/**
 * useH7DepreciationEngine — H7 生产性生物资产折旧纯函数引擎（成本模式直线法）
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 2.2
 * Requirements: 11.1-11.4
 *
 * 所有函数为纯函数（无副作用），方便PBT验证。
 * 生产性生物资产折旧采用直线法（年限平均法）。
 */

// ─── 直线法年折旧 ────────────────────────────────────────────────────────────

/**
 * 年折旧额 = 原值 × (1 - 残值率) / 使用寿命(年)
 * Property P5: ∀ cost>0, salvageRate∈[0,1), usefulLife>0:
 *   calcStraightLine(cost, rate, life) === cost × (1-rate) / life
 *
 * @param cost 资产原值（>0）
 * @param salvageRate 预计残值率（0~1之间，如 0.05 表示5%）
 * @param usefulLife 预计使用寿命（年，>0）
 */
export function calcStraightLine(cost: number, salvageRate: number, usefulLife: number): number {
  if (usefulLife <= 0) return 0
  return (cost * (1 - salvageRate)) / usefulLife
}

// ─── 月折旧额 ────────────────────────────────────────────────────────────────

/**
 * 月折旧额 = 年折旧额 / 12
 * Property P6: ∀ annualDep: calcMonthlyDep(annual) === annual / 12
 *
 * @param annualDep 年折旧额
 */
export function calcMonthlyDep(annualDep: number): number {
  return annualDep / 12
}

// ─── 减值后折旧 ──────────────────────────────────────────────────────────────

/**
 * 减值后年折旧额 = 净值(减值后) × (1 - 残值率) / 剩余使用寿命(年)
 * Property P12: ∀ netValue>0, salvageRate∈[0,1), remainLife>0:
 *   calcDepAfterImpairment(nv, rate, life) === nv × (1-rate) / life
 *
 * @param netValue 减值后净值（原值 - 累计折旧 - 减值准备）
 * @param salvageRate 预计残值率
 * @param remainLife 剩余使用寿命（年，>0）
 */
export function calcDepAfterImpairment(
  netValue: number,
  salvageRate: number,
  remainLife: number,
): number {
  if (remainLife <= 0) return 0
  return (netValue * (1 - salvageRate)) / remainLife
}

// ─── 累计折旧 ────────────────────────────────────────────────────────────────

/**
 * 累计折旧 = 月折旧额 × 已使用月数
 *
 * @param monthlyDep 月折旧额
 * @param months 已使用月数
 */
export function calcAccDep(monthlyDep: number, months: number): number {
  return monthlyDep * months
}
