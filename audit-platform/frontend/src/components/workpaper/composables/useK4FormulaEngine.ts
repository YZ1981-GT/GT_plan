/**
 * K4 其他流动负债 — 公式引擎（纯函数）
 *
 * 科目：2245其他流动负债（**贷方/负债类**）
 *
 * ⚠️ 负债类！方向与资产类（期初+借-贷）相反！
 *   负债类期末 = 期初 + 贷方 - 借方
 *   增加 = 贷方发生；减少 = 借方发生
 *
 * 核心公式：
 * - 审定数 = 未审 + AJE + RJE
 * - 负债类期末 = 期初 + 贷方 - 借方
 * - 三角勾稽差额 = begin + inc - dec - end，恒等时为0
 * - 合计 = Σarr（空数组 → 0）
 * - 变动率 = (current - prior) / prior（特殊：prior=0∧current=0→null，prior=0∧current≠0→1）
 *
 * 设计原则：纯函数，无Vue响应式，无副作用，可PBT验证
 * 所有函数对 NaN / undefined 输入视为 0 处理
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/ Requirements 2.2-2.3, 6.1-6.5
 */

// ─── Helpers ────────────────────────────────────────────────────────────────

/** 将 NaN / undefined / null 转为 0 */
function safeNum(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isNaN(n) ? 0 : n
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
 * Requirement 6.1
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return safeNum(unadj) + safeNum(aje) + safeNum(rje)
}

/**
 * 负债类期末余额 = 期初 + 贷方 - 借方
 *
 * ⚠️ 负债类！与资产类（期初+借-贷）方向相反！
 *
 * @param begin 期初余额
 * @param credit 本期贷方发生额（增加）
 * @param debit 本期借方发生额（减少）
 * @returns 期末余额
 *
 * Requirement 6.2
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return safeNum(begin) + safeNum(credit) - safeNum(debit)
}

/**
 * 三角勾稽差额 = begin + inc - dec - end
 *
 * 对于负债类：增加=贷方(inc)，减少=借方(dec)
 * 如果恒等（期末=期初+增加-减少）则返回 0
 *
 * @param begin 期初余额
 * @param inc 增加额（贷方发生）
 * @param dec 减少额（借方发生）
 * @param end 期末余额
 * @returns 差额，0表示勾稽平衡
 *
 * Requirement 6.3
 */
export function calcTriangleReconciliation(begin: number, inc: number, dec: number, end: number): number {
  return safeNum(begin) + safeNum(inc) - safeNum(dec) - safeNum(end)
}

/**
 * 合计 = Σarr
 *
 * 空数组返回 0；数组元素中的 NaN/undefined 视为 0
 *
 * @param arr 待求和数组
 * @returns 合计值
 *
 * Requirement 6.4
 */
export function calcSubtotal(arr: number[]): number {
  if (!arr || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + safeNum(v), 0)
}

/**
 * 变动率 = (current - prior) / prior
 *
 * 特殊处理：
 *   - prior=0 且 current=0 → null（无意义）
 *   - prior=0 且 current≠0 → 1（100%增长）
 *   - 否则 → (current - prior) / prior
 *
 * @param current 本期金额
 * @param prior 上期金额
 * @returns 变动率（小数形式，如0.5表示50%）或 null
 *
 * Requirement 6.5
 */
export function calcChangeRate(current: number, prior: number): number | null {
  const c = safeNum(current)
  const p = safeNum(prior)
  if (p === 0) {
    return c === 0 ? null : 1
  }
  return (c - p) / p
}
