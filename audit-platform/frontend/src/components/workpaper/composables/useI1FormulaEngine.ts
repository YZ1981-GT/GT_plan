/**
 * I1 无形资产 — 公式引擎（纯函数，无副作用）
 * 科目：1701无形资产（借方/资产类）+ 1702累计摊销（贷方/资产备抵类）+ 1703无形资产减值准备（贷方/资产备抵类）
 * Spec: .kiro/specs/i1-intangible-assets/
 */

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末余额（借方科目1701无形资产）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/** 备抵类期末余额（贷方科目1702累计摊销/1703减值准备）：期末 = 期初 + 贷方发生 - 借方发生 */
export function calcContraEndBalance(begin: number, debit: number, credit: number): number {
  return begin + credit - debit
}

/**
 * 三角勾稽校验：差额 = 期末 - (期初 + 增加 - 减少)
 * 返回0表示勾稽平衡，非0表示存在差异
 */
export function calcTriangleReconciliation(begin: number, increase: number, decrease: number, end: number): number {
  return end - (begin + increase - decrease)
}

/** 净值 = 原值 - 累计摊销 - 减值准备 */
export function calcNetValue(cost: number, accAmort: number, impairment: number): number {
  return cost - accAmort - impairment
}

/** 变动率(%) = (本期 - 上期) / 上期 × 100；上期为0时返回null */
export function calcChangeRate(current: number, prior: number): number | null {
  if (prior === 0) return null
  return (current - prior) / prior * 100
}

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

/** 占比(%) = 项目 / 合计 × 100；合计为0时返回null */
export function calcProportion(item: number, total: number): number | null {
  if (total === 0) return null
  return item / total * 100
}

/** 处置损益 = 处置收入 - 净值 */
export function calcDisposalGainLoss(income: number, netValue: number): number {
  return income - netValue
}

/** 权属差异 = 账面价值 - 权证价值 */
export function calcTitleDiff(bookValue: number, certValue: number): number {
  return bookValue - certValue
}

/** 借贷平衡检查：借方合计 === 贷方合计（精度0.01） */
export function isBalanced(entries: { debit: number; credit: number }[]): boolean {
  const totalDebit = entries.reduce((s, e) => s + e.debit, 0)
  const totalCredit = entries.reduce((s, e) => s + e.credit, 0)
  return Math.abs(totalDebit - totalCredit) < 0.01
}

/** 分配合计：各分配项之和 */
export function calcAllocTotal(allocations: number[]): number {
  return allocations.reduce((s, a) => s + a, 0)
}
