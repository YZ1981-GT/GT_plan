/**
 * H1 固定资产 — 公式引擎（纯函数，无副作用）
 * 科目：1601固定资产（借方/资产类）+ 1602累计折旧（贷方/资产备抵类）
 * Spec: .kiro/specs/h1-fixed-assets/
 */

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末余额（借方科目1601）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/** 备抵类期末余额（贷方科目1602累计折旧）：期末 = 期初 + 贷方发生 - 借方发生 */
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

/** 净值 = 原值 - 累计折旧 - 减值准备 */
export function calcNetValue(originalCost: number, accDepreciation: number, impairment: number): number {
  return originalCost - accDepreciation - impairment
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

/** 成新率(%) = 净值 / 原值 × 100；原值为0时返回null */
export function calcNewRate(netValue: number, originalCost: number): number | null {
  if (originalCost === 0) return null
  return netValue / originalCost * 100
}

/** 处置损益 = 处置收入 - 净值 - 处置费用 */
export function calcDisposalGainLoss(income: number, netValue: number, disposalCost: number): number {
  return income - netValue - disposalCost
}

/** 关联价格差异率(%) = (交易价格 - 公允价值) / 公允价值 × 100；公允价值为0时返回null */
export function calcPriceDiffRate(transactionPrice: number, fairValue: number): number | null {
  if (fairValue === 0) return null
  return (transactionPrice - fairValue) / fairValue * 100
}

/** 权属差异 = 账面价值 - 证载价值 */
export function calcTitleDiff(bookValue: number, certValue: number): number {
  return bookValue - certValue
}

/** 租赁收益率(%) = 净收益 / 原值 × 100；原值为0时返回null */
export function calcLeaseReturnRate(netIncome: number, originalCost: number): number | null {
  if (originalCost === 0) return null
  return netIncome / originalCost * 100
}
