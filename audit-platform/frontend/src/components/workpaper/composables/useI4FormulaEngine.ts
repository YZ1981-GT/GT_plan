/**
 * I4 长期待摊费用 — 公式引擎（纯函数，无副作用）
 * 科目：1801长期待摊费用（借方/资产类）
 * 核心特征：期末 = 期初 + 增加 - 摊销 - 减少
 * 摊销方法：直线法(I4-6) / 工作量法(I4-7)
 * Spec: .kiro/specs/i4-long-term-prepaid/
 */

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/**
 * 资产类期末余额（借方科目1801长期待摊费用）
 * 期末 = 期初 + 增加 - 摊销 - 减少
 */
export function calcAssetEndBalance(begin: number, increase: number, amortization: number, decrease: number): number {
  return begin + increase - amortization - decrease
}

/**
 * 三角勾稽校验：返回差额
 * 差额 = 期末 - (期初 + 增加 - 摊销 - 减少)
 * 返回0表示勾稽平衡，非0表示存在差异（红色高亮）
 */
export function calcTriangleReconciliation(begin: number, increase: number, amortization: number, decrease: number, end: number): number {
  return end - (begin + increase - amortization - decrease)
}

/** 合计行 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

/**
 * 变动率 = (当期 - 前期) / 前期
 * 前期为0时返回null（无法计算变动率）
 */
export function calcChangeRate(current: number, prior: number): number | null {
  if (prior === 0) return null
  return (current - prior) / prior
}
