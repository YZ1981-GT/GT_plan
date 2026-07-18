/**
 * F5 营业成本 — 公式引擎（借方/损益类科目 6401）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 2.1
 * 12个纯函数 + parseNum 辅助
 *
 * 损益类特点：无"期初期末"概念，只有"本期/上期"发生额对比。
 * 核心链：审定=未审+AJE+RJE；成本倒轧=期初+购入-期末-其他=投入+人工+制造=完工=营业成本。
 */

/** 安全数值解析：null/undefined/NaN/空→0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

/** Property 1: 审定 = 未审 + AJE + RJE（损益类发生额） */
export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

/** 变动额 = 本期 - 上期 */
export function calcChangeAmount(current: number, prior: number): number {
  return current - prior
}

/** Property 7: 变动率 = (本期-上期)/上期 × 100，上期=0→'N/A' */
export function calcChangeRate(current: number, prior: number): number | 'N/A' {
  if (prior === 0) return 'N/A'
  return ((current - prior) / prior) * 100
}

/** Property 3: 毛利率 = (收入-成本)/收入 × 100，收入=0→'N/A' */
export function calcGrossMargin(revenue: number, cost: number): number | 'N/A' {
  if (revenue === 0) return 'N/A'
  return ((revenue - cost) / revenue) * 100
}

/** Property 2: 投入生产 / 直接材料成本 = 期初原材料 + 本期购入 - 期末原材料 - 其他发出
 *  （源表可含「其他增加额」：opening + purchase + otherInc - closing - otherOut）
 */
export function calcCostRollforward(
  opening: number,
  purchase: number,
  closing: number,
  other: number,
  otherIncrease = 0,
): number {
  return opening + purchase + otherIncrease - closing - other
}

/** 产品总成本 / 产品生产成本 = 投入生产 + 直接人工 + 制造费用 [+ 专用工模具] */
export function calcTotalProductionCost(
  input: number,
  labor: number,
  overhead: number,
  specialTooling = 0,
): number {
  return input + labor + overhead + specialTooling
}

/** Property 4: 完工产品成本 / 产成品成本 = 期初在产品 + 产品总成本 - 期末在产品 */
export function calcFinishedGoodsCost(
  wipOpening: number,
  totalCost: number,
  wipClosing: number,
): number {
  return wipOpening + totalCost - wipClosing
}

/** Property 5: 本期营业成本 / 主营业务成本
 *  简化：期初产成品 + 完工 - 期末 - 其他发出
 *  完整源表：⒀+⒁+⒂-⒃-⒄-⒅-⒆
 */
export function calcCOGS(
  fgOpening: number,
  finishedCost: number,
  fgClosing: number,
  other: number,
  fgOtherIncrease = 0,
  selfUse = 0,
  internalUse = 0,
): number {
  return finishedCost + fgOpening + fgOtherIncrease - fgClosing - selfUse - internalUse - other
}

/** F5-7 源表：直接材料成本 ⑹ = ⑴+⑵+⑶−⑷−⑸ */
export function calcF57DirectMaterial(
  opening: number,
  purchaseNet: number,
  otherIncrease: number,
  closing: number,
  otherIssue: number,
): number {
  return opening + purchaseNet + otherIncrease - closing - otherIssue
}

/** F5-7 源表：产品生产成本 ⑽ = ⑹+⑺+⑻+⑼（不含「其中：材料费用」明细行） */
export function calcF57ProductionCost(
  directMaterial: number,
  directLabor: number,
  overhead: number,
  specialTooling: number,
): number {
  return directMaterial + directLabor + overhead + specialTooling
}

/** F5-7 源表：产成品成本 ⒀ = ⑽+⑾−⑿ */
export function calcF57FinishedGoodsCost(
  productionCost: number,
  openingWIP: number,
  closingWIP: number,
): number {
  return productionCost + openingWIP - closingWIP
}

/** F5-7 源表：主营业务成本 ⒇ = ⒀+⒁+⒂−⒃−⒄−⒅−⒆ */
export function calcF57MainBusinessCOGS(
  finishedCost: number,
  openingFG: number,
  fgOtherIncrease: number,
  closingFG: number,
  selfUse: number,
  internalUse: number,
  fgOtherIssue: number,
): number {
  return finishedCost + openingFG + fgOtherIncrease - closingFG - selfUse - internalUse - fgOtherIssue
}

/** Property 6: 数量差异 = 销售数量 - 结转成本数量 */
export function calcQuantityVariance(salesQty: number, costQty: number): number {
  return salesQty - costQty
}

/** 差异率 = 数量差异 / 销售数量 × 100，销售量=0→'N/A' */
export function calcVarianceRate(variance: number, salesQty: number): number | 'N/A' {
  if (salesQty === 0) return 'N/A'
  return (variance / salesQty) * 100
}

/** Property 8: 波动系数 = 标准差(values) / 均值(values)，均值=0→0（衡量月度波动） */
export function calcCoeffOfVariation(values: number[]): number {
  if (values.length === 0) return 0
  const mean = values.reduce((s, v) => s + v, 0) / values.length
  if (mean === 0) return 0
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length
  const stddev = Math.sqrt(variance)
  return Math.abs(stddev / mean)
}

/** Property 10: 借贷平衡 = |SUM(debits) - SUM(credits)| < 0.01 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const d = debits.reduce((s, v) => s + v, 0)
  const c = credits.reduce((s, v) => s + v, 0)
  return Math.abs(d - c) < 0.01
}

// --- 辅助函数 ---

/** 小计求和（用于月度合计/品种小计等） */
export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + v, 0)
}

/** 变动/差异率是否超阈值（'N/A' 不触发） */
export function isRateExceeding(rate: number | 'N/A', threshold: number): boolean {
  if (rate === 'N/A') return false
  return Math.abs(rate) > threshold
}
