/**
 * K1 其他应收款 — 公式引擎（纯函数）
 *
 * 科目：1221其他应收款（借方/资产类）+ 坏账准备（贷方/资产备抵类）
 *
 * 核心公式：
 * - 审定数 = 未审 + AJE + RJE
 * - 资产类期末 = 期初 + 借方 - 贷方
 * - 备抵类期末 = 期初 + 贷方 - 借方
 * - 期末坏账 = 期初 + 计提 - 转回 - 核销
 * - 净值 = 应收 - 坏账
 * - 三角勾稽差额 = (期初 + 增加 - 减少) - 期末
 * - 占比 = 单项 / 合计（除零返null）
 * - 变动率 = (本期 - 上期) / |上期|（除零返null）
 *
 * Spec: .kiro/specs/k1-other-receivables/ Requirements 2.3-2.7, 4.2-4.3, 12.4-12.10
 */

/** 审定数 = 未审 + AJE + RJE */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末 = 期初 + 借方 - 贷方 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/** 备抵类期末 = 期初 + 贷方 - 借方 */
export function calcContraEndBalance(begin: number, credit: number, debit: number): number {
  return begin + credit - debit
}

/** 期末坏账 = 期初 + 计提 - 转回 - 核销 */
export function calcBadDebtEnd(begin: number, provision: number, reversal: number, writeoff: number): number {
  return begin + provision - reversal - writeoff
}

/** 净值 = 应收 - 坏账 */
export function calcNetValue(receivable: number, badDebt: number): number {
  return receivable - badDebt
}

/** 三角勾稽差额 = (期初 + 增加 - 减少) - 期末，差额=0表示平衡 */
export function calcTriangleReconciliation(begin: number, inc: number, dec: number, end: number): number {
  return (begin + inc - dec) - end
}

/** 占比 = 单项 / 合计，合计<=0返回null避免除零 */
export function calcProportion(item: number, total: number): number | null {
  return total > 0 ? item / total : null
}

/** 合计 = 数组求和 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((sum, v) => sum + v, 0)
}

/** 变动率 = (本期 - 上期) / |上期|，上期=0返回null避免除零 */
export function calcChangeRate(current: number, prior: number): number | null {
  return prior !== 0 ? (current - prior) / Math.abs(prior) : null
}
