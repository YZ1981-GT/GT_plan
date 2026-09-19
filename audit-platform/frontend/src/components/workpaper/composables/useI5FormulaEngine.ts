/**
 * I5 其他非流动资产 — 公式引擎（纯函数，无副作用）
 * 科目：1911其他非流动资产（借方/资产类）
 * 核心特征：标准资产类 期末 = 期初 + 增加 - 减少
 * I循环最简单底稿，无摊销/减值等特殊逻辑
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 */

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/**
 * 资产类期末余额（借方科目1911其他非流动资产）
 * 期末 = 期初 + 增加 - 减少
 */
export function calcAssetEndBalance(begin: number, increase: number, decrease: number): number {
  return begin + increase - decrease
}

/**
 * 三角勾稽校验：返回差额
 * 差额 = (期初 + 增加 - 减少) - 期末
 * 返回0表示勾稽平衡，非0表示存在差异（红色高亮）
 */
export function calcTriangleReconciliation(begin: number, increase: number, decrease: number, end: number): number {
  return (begin + increase - decrease) - end
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
