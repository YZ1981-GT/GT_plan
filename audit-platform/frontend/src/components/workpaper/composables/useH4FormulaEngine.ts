/**
 * H4 工程物资 — 公式引擎（纯函数，无副作用）
 * 科目：1605工程物资（借方/资产类）
 * Spec: .kiro/specs/h4-engineering-materials/
 */

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末余额（借方科目1605）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/**
 * 三角勾稽校验：差额 = 期末 - (期初 + 增加 - 减少)
 * 返回0表示勾稽平衡，非0表示存在差异
 */
export function calcTriangleReconciliation(begin: number, increase: number, decrease: number, end: number): number {
  return end - (begin + increase - decrease)
}

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

/**
 * 差异率(%) = (实际 - 预期) / 预期 × 100
 * 预期为0时：实际也为0返回0，否则返回100（表示完全偏离）
 */
export function calcDiffRate(actual: number, expected: number): number {
  if (expected === 0) return actual === 0 ? 0 : 100
  return (actual - expected) / expected * 100
}

/**
 * 关联价差率(%) = (交易价格 - 市场价格) / 市场价格 × 100
 * 市场价格为0时：交易价格也为0返回0，否则返回100（表示完全偏离）
 */
export function calcPriceDiffRate(transPrice: number, marketPrice: number): number {
  if (marketPrice === 0) return transPrice === 0 ? 0 : 100
  return (transPrice - marketPrice) / marketPrice * 100
}
