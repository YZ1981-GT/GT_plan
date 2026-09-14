/**
 * K7 递延收益 — 公式引擎（纯函数）
 *
 * 科目：2401递延收益（**贷方/负债类**）
 *
 * ⚠️ 负债类！方向与资产类（期初+借-贷）相反！
 *   负债类期末 = 期初 + 收到(贷方增加) - 分摊(借方减少)
 *
 * 核心公式：
 * - 审定数 = 未审 + AJE + RJE
 * - 负债类期末 = 期初 + 收到 - 分摊
 * - 合计 = Σarr（空数组 → 0）
 *
 * 设计原则：纯函数，无Vue响应式，无副作用，可PBT验证
 * 所有函数对 NaN / undefined 输入视为 0 处理
 *
 * Spec: .kiro/specs/k7-deferred-income/ Requirements 2.2-2.3, 7.1-7.2, 7.6
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
 * Requirement 7.1
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return safeNum(unadj) + safeNum(aje) + safeNum(rje)
}

/**
 * 负债类期末余额 = 期初 + 收到(贷方增加) - 分摊(借方减少)
 *
 * ⚠️ 负债类！与资产类（期初+借-贷）方向相反！
 * 递延收益2401：收到政府补助增加贷方，分摊计入损益减少借方
 *
 * @param begin 期初余额
 * @param received 本期收到（增加/贷方发生额）
 * @param amortized 本期分摊（减少/借方发生额）
 * @returns 期末余额
 *
 * Requirement 7.2
 */
export function calcLiabilityEndBalance(begin: number, received: number, amortized: number): number {
  return safeNum(begin) + safeNum(received) - safeNum(amortized)
}

/**
 * 合计 = Σarr
 *
 * 空数组返回 0；数组元素中的 NaN/undefined 视为 0
 *
 * @param arr 待求和数组
 * @returns 合计值
 *
 * Requirement 7.6
 */
export function calcSubtotal(arr: number[]): number {
  if (!arr || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + safeNum(v), 0)
}
