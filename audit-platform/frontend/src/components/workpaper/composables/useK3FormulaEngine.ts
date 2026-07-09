/**
 * K3 其他应付款 — 公式引擎（纯函数）
 *
 * 科目：2241其他应付款（**贷方/负债类**）
 *
 * ⚠️ 负债类！方向与资产类（期初+借-贷）相反！
 *   负债类期末 = 期初 + 贷方 - 借方
 *   增加 = 贷方发生；减少 = 借方发生
 *
 * 核心公式：
 * - 审定数 = 未审 + AJE + RJE
 * - 负债类期末 = 期初 + 贷方 - 借方
 * - 三角勾稽差额 = end - (begin + inc - dec)，恒等时为0
 * - 占比 = 单项 / 合计（total=0 → null）
 * - 合计 = Σarr（空数组 → 0）
 * - 变动率 = (current - prior) / prior（特殊：prior=0∧current=0→0，prior=0∧current≠0→1）
 *
 * Spec: .kiro/specs/k3-other-payables/ Requirements 2.2-2.3, 7.1, 9.1-9.6
 */

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
  return unadj + aje + rje
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
 * Requirement 9.2
 */
export function calcLiabilityEndBalance(begin: number, credit: number, debit: number): number {
  return begin + credit - debit
}

/**
 * 三角勾稽差额 = end - (begin + inc - dec)
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
 * Requirement 9.3
 */
export function calcTriangleReconciliation(begin: number, inc: number, dec: number, end: number): number {
  return end - (begin + inc - dec)
}

/**
 * 占比 = item / total
 *
 * 如果 total === 0 返回 null（避免除零）
 *
 * @param item 单项金额
 * @param total 合计金额
 * @returns 占比或null
 *
 * Requirement 9.4
 */
export function calcProportion(item: number, total: number): number | null {
  return total === 0 ? null : item / total
}

/**
 * 合计 = Σarr
 *
 * 空数组返回 0
 *
 * @param arr 待求和数组
 * @returns 合计值
 *
 * Requirement 9.5
 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((sum, v) => sum + v, 0)
}

/**
 * 变动率 = (current - prior) / prior
 *
 * 特殊处理：
 *   - prior=0 且 current=0 → 0（无变动）
 *   - prior=0 且 current≠0 → 1（100%增长）
 *   - 否则 → (current - prior) / prior
 *
 * @param current 本期金额
 * @param prior 上期金额
 * @returns 变动率（小数形式，如0.5表示50%）
 *
 * Requirement 9.6
 */
export function calcChangeRate(current: number, prior: number): number {
  if (prior === 0) {
    return current === 0 ? 0 : 1
  }
  return (current - prior) / prior
}
