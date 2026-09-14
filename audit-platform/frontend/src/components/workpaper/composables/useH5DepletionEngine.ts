/**
 * H5 油气资产 — 折耗引擎（纯函数，无副作用）
 * 科目：1611油气资产（借方/资产类）+ 累计折耗（贷方/备抵类）
 * 核心方法：单位产量法（折耗 = 可折耗金额 × 当期产量 ÷ 预计可采储量）
 * Spec: .kiro/specs/h5-oil-gas-assets/
 *
 * 边界约定：
 *  - 所有函数输入若为 NaN/undefined/null → 视为 0
 *  - 除法分母为 0 → 返回 0（不抛异常）
 *  - 产量 > 储量时 → 折耗封顶为可折耗余额
 *
 * Requirements: 7.4, 9.1-9.5
 */

// ─── 辅助 ───────────────────────────────────────────────────────────────────────

/** 将 NaN/undefined/null 安全转为 0 */
function safe(v: number): number {
  return Number.isFinite(v) ? v : 0
}

// ─── 折耗公式 ─────────────────────────────────────────────────────────────────

/**
 * 单位产量法折耗 = (cost - salvage) × production / reserves
 * 储量为 0 时返回 0（不除零）
 *
 * Requirements: 7.4, 9.1
 * Property P4: ∀ cost,salvage,prod,reserves(>0): result === (cost-salvage)*prod/reserves
 * Property P5: ∀ reserves=0: result === 0
 */
export function calcUnitDepletion(
  cost: number,
  salvage: number,
  production: number,
  reserves: number,
): number {
  const r = safe(reserves)
  if (r === 0) return 0
  return (safe(cost) - safe(salvage)) * safe(production) / r
}

/**
 * 折耗率(%) = accDepletion / cost × 100
 * cost 为 0 时返回 0
 *
 * Requirements: 9.2
 */
export function calcDepletionRate(accDepletion: number, cost: number): number {
  const c = safe(cost)
  if (c === 0) return 0
  return (safe(accDepletion) / c) * 100
}

/**
 * 剩余可采储量 = totalReserves - accProduction
 *
 * Requirements: 9.3
 */
export function calcRemainingReserves(totalReserves: number, accProduction: number): number {
  return safe(totalReserves) - safe(accProduction)
}

/**
 * 含减值后折耗 = (netValue - salvage) × production / remainReserves
 * remainReserves 为 0 时返回 0（不除零）
 *
 * Requirements: 9.4
 */
export function calcDepletionAfterImpairment(
  netValue: number,
  salvage: number,
  production: number,
  remainReserves: number,
): number {
  const rr = safe(remainReserves)
  if (rr === 0) return 0
  return (safe(netValue) - safe(salvage)) * safe(production) / rr
}

/**
 * 折耗封顶（可折耗余额） = cost - salvage - accDepletion
 * 当 production > reserves 时，本期折耗不应超过此值
 *
 * Requirements: 9.5
 * Property P6: ∀ cost,salvage,accDepletion: result === cost - salvage - accDepletion
 */
export function calcDepletionCapped(
  cost: number,
  salvage: number,
  accDepletion: number,
): number {
  return safe(cost) - safe(salvage) - safe(accDepletion)
}
