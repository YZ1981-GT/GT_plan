/**
 * K6 持有待售资产和负债 — 公式引擎（纯函数）
 *
 * 科目：持有待售资产（**借方/资产类**）+ 持有待售负债（**贷方/负债类**）
 *
 * ⚠️ 混合科目！资产类与负债类方向不同！
 *   资产类期末 = 期初 + 增加 - 减少 - 减值
 *   负债类期末 = 期初 + 增加 - 减少
 *
 * 核心公式：
 * - 审定数 = 未审 + AJE + RJE
 * - 账面价值 = 原值 - 累计折旧摊销 - 减值准备
 * - 资产类期末 = 期初 + 增加 - 减少 - 减值
 * - 负债类期末 = 期初 + 增加 - 减少
 * - 变动率 = (审定 - 上期) / 上期（兜底除零）
 * - 合计 = Σarr（空数组 → 0）
 *
 * 设计原则：纯函数，无Vue响应式，无副作用，可PBT验证
 * 所有函数对 NaN / undefined / Infinity 输入安全处理
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Requirements 2.3-2.4, 3.2, 9.1-9.2, 9.7
 */

// ─── Helpers ────────────────────────────────────────────────────────────────

/** 将 NaN / undefined / null / Infinity 转为 0 */
function safeNum(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  if (Number.isNaN(n) || !Number.isFinite(n)) return 0
  return n
}

// ─── 公式函数 ───────────────────────────────────────────────────────────────

/**
 * 审定数 = 未审 + AJE + RJE
 *
 * @param unadj 未审数
 * @param aje 审计调整分录
 * @param rje 重分类调整分录
 * @returns 审定数
 *
 * Requirement 9.1
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return safeNum(unadj) + safeNum(aje) + safeNum(rje)
}

/**
 * 账面价值 = 原值 - 累计折旧摊销 - 减值准备
 *
 * @param cost 原值（账面原值）
 * @param dep 累计折旧摊销
 * @param impairment 减值准备
 * @returns 账面价值
 *
 * Requirement 9.2, 3.2
 */
export function calcBookValue(cost: number, dep: number, impairment: number): number {
  return safeNum(cost) - safeNum(dep) - safeNum(impairment)
}

/**
 * 合计 = Σarr
 *
 * 空数组返回 0；数组元素中的 NaN/undefined/Infinity 视为 0
 *
 * @param arr 待求和数组
 * @returns 合计值
 *
 * Requirement 9.7
 */
export function calcSubtotal(arr: number[]): number {
  if (!arr || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + safeNum(v), 0)
}

/**
 * 资产类期末 = 期初 + 增加 - 减少 - 减值
 *
 * 持有待售资产（借方）：期末余额 = 期初 + 本期增加 - 本期减少 - 减值准备
 *
 * @param opening 期初余额
 * @param increase 本期增加
 * @param decrease 本期减少
 * @param impairment 减值准备
 * @returns 期末余额
 *
 * Requirement 2.3
 */
export function calcAssetPeriodEnd(opening: number, increase: number, decrease: number, impairment: number): number {
  return safeNum(opening) + safeNum(increase) - safeNum(decrease) - safeNum(impairment)
}

/**
 * 负债类期末 = 期初 + 增加 - 减少
 *
 * 持有待售负债（贷方）：期末余额 = 期初 + 本期增加 - 本期减少
 *
 * @param opening 期初余额
 * @param increase 本期增加（贷方发生额）
 * @param decrease 本期减少（借方发生额）
 * @returns 期末余额
 *
 * Requirement 2.4 (负债区块)
 */
export function calcLiabilityPeriodEnd(opening: number, increase: number, decrease: number): number {
  return safeNum(opening) + safeNum(increase) - safeNum(decrease)
}

/**
 * 变动率 = (审定 - 上期) / 上期
 *
 * 特殊处理除零：
 *   - 上期=0 且 审定=0 → null（无变动，无意义）
 *   - 上期=0 且 审定≠0 → 1（100%增长）
 *   - 否则 → (审定 - 上期) / 上期
 *
 * @param prior 上期金额
 * @param current 本期审定金额
 * @returns 变动率（小数形式，如0.5表示50%）或 null
 */
export function calcVariationRate(prior: number, current: number): number | null {
  const p = safeNum(prior)
  const c = safeNum(current)
  if (p === 0) {
    return c === 0 ? null : 1
  }
  return (c - p) / p
}
