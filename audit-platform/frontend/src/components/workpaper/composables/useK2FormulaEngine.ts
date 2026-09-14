/**
 * K2 其他流动资产 — 公式引擎（纯函数）
 *
 * 科目：1231其他流动资产（借方/资产类）
 *
 * 核心公式：
 * - 审定数 = 未审 + AJE + RJE
 * - 资产类期末 = 期初 + 借方 - 贷方
 * - 三角勾稽差额 = 期末 - (期初 + 增加 - 减少)
 * - 合计 = Σarr
 * - 变动率 = (本期 - 上期) / |上期| × 100（上期=0 → null）
 *
 * Spec: .kiro/specs/k2-other-current-assets/ Requirements 2.2-2.3, 8.1-8.2, 8.6-8.7
 */

/** NaN 安全：将 NaN 视为 0 */
function safe(v: number): number {
  return Number.isNaN(v) ? 0 : v
}

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return safe(unadj) + safe(aje) + safe(rje)
}

/** 资产类期末余额 = 期初 + 借方 - 贷方（借方/资产类 1231） */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return safe(begin) + safe(debit) - safe(credit)
}

/** 三角勾稽差额 = 期末 - (期初 + 增加 - 减少)，返回差额，0表示平衡 */
export function calcTriangleReconciliation(begin: number, inc: number, dec: number, end: number): number {
  return safe(end) - (safe(begin) + safe(inc) - safe(dec))
}

/** 合计行 = 数组求和 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((sum, v) => sum + safe(v), 0)
}

/** 变动率 = (本期 - 上期) / |上期| × 100，上期为0时返回null（避免除以零） */
export function calcChangeRate(current: number, prior: number): number | null {
  const c = safe(current)
  const p = safe(prior)
  return p !== 0 ? ((c - p) / Math.abs(p)) * 100 : null
}
