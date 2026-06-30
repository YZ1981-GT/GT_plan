/**
 * useD4FormulaEngine — D4 营业收入共享纯函数公式引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * 覆盖损益类/贷方科目（6001主营+6051其他）的全部公式计算需求。
 *
 * 核心差异 vs D2/D3：损益类取发生额（非余额），无期初期末余额概念。
 * 审定 = 未审 + AJE + RJE；变动率 = (本期 - 上期) / 上期。
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Requirements: 1.5, 2.3, 3.2, 4.2, 8.2, 11.3, 13.2, 14.1, 14.11, 25.1-25.4
 */

// ─── 数值解析 ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/空串/NaN/Infinity → 0
 *
 * 审计底稿中大量字段可能为空或无效值，统一转为数字 0 以确保公式运算不出 NaN。
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  if (!isFinite(n)) return 0
  return n
}

// ─── 审定表公式 ──────────────────────────────────────────────────────────────

/**
 * 审定数 = 未审 + AJE + RJE
 *
 * 损益类贷方科目公式，适用于 D4-1 审定表所有行。
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

/**
 * 月度合计 = SUM(1月~12月)
 *
 * D4-2 主营明细22列宽表中的本期未审合计（N列 = SUM(B~M)）。
 */
export function calcMonthlyTotal(months: number[]): number {
  return months.reduce((sum, v) => sum + v, 0)
}

/**
 * 审定数（含调整）= 未审合计 + 审计调整
 *
 * D4-2 中 P列 = N列 + O列（本期审定 = 本期未审合计 + 本期审计调整）。
 */
export function calcAuditedWithAdj(unadjustedTotal: number, adjustment: number): number {
  return unadjustedTotal + adjustment
}

// ─── 变动分析公式 ────────────────────────────────────────────────────────────

/**
 * 变动率计算，含特殊处理：
 * - 本期=0 且 上期=0 → ''（无意义，不显示）
 * - 上期=0（且本期≠0）→ 'N/A'（无法计算百分比变动）
 * - 其他 → (本期 - 上期) / 上期
 *
 * 适用于 D4-2 T/U列、D4-3变动比例、D4-6~11分析程序等。
 */
export function calcChangeRate(current: number, prior: number): number | '' | 'N/A' {
  if (current === 0 && prior === 0) return ''
  if (prior === 0) return 'N/A'
  return (current - prior) / prior
}

/**
 * 变动额 = 本期 - 上期
 *
 * D4-3 变动额列、D4-6指标变动金额等。
 */
export function calcChangeAmount(current: number, prior: number): number {
  return current - prior
}

// ─── 合计/小计公式 ──────────────────────────────────────────────────────────

/**
 * 小计/合计 = SUM(数组)
 *
 * 通用求和，适用于 D4-1小计/合计行、D4-2合计行、D4-3合计行等。
 */
export function calcSubtotal(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0)
}

// ─── 毛利率公式 ─────────────────────────────────────────────────────────────

/**
 * 毛利率 = (收入 - 成本) / 收入
 *
 * 收入=0时返回0（避免除以零）。适用于 D4-7月度毛利/D4-8产品毛利/D4-33其他毛利。
 */
export function calcGrossMarginRate(revenue: number, cost: number): number {
  if (revenue === 0) return 0
  return (revenue - cost) / revenue
}

// ─── 占比公式 ────────────────────────────────────────────────────────────────

/**
 * 占比 = 本项 / 合计 × 100%
 *
 * 合计=0时返回0。适用于 D4-3占比列、D4-9客户集中度等。
 * 返回百分比值（如 25.5 代表 25.5%）。
 */
export function calcProportion(item: number, total: number): number {
  if (total === 0) return 0
  return (item / total) * 100
}

// ─── 关联方价格差异率 ───────────────────────────────────────────────────────

/**
 * 价格差异率 = (关联方单价 - 非关联方单价) / 非关联方单价 × 100%
 *
 * 非关联方单价=0时返回0（避免除以零）。D4-21关联方价格分析使用。
 * 返回百分比值（如 15.2 代表 15.2%）。
 */
export function calcPriceDiffRate(relatedPrice: number, nonRelatedPrice: number): number {
  if (nonRelatedPrice === 0) return 0
  return ((relatedPrice - nonRelatedPrice) / nonRelatedPrice) * 100
}

// ─── 阈值判定 ────────────────────────────────────────────────────────────────

/**
 * 变动率绝对值是否超阈值
 *
 * 空串或'N/A'返回 false（无法判定），数值型取绝对值与阈值比较。
 * 适用于30%/20%/10%/5%多级阈值高亮。
 */
export function isChangeRateExceeding(rate: number | '' | 'N/A', threshold: number): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}

// ─── 检查程序公式 ────────────────────────────────────────────────────────────

/**
 * 异常率 = 异常笔数 / 已检查笔数 × 100%
 *
 * 已检查笔数=0时返回0。D4-14/15/17/18检查程序汇总使用。
 * 返回百分比值。
 */
export function calcAnomalyRate(anomalyCount: number, totalChecked: number): number {
  if (totalChecked === 0) return 0
  return (anomalyCount / totalChecked) * 100
}

/**
 * 覆盖率 = 已检查金额 / 收入合计 × 100%
 *
 * 收入合计=0时返回0。D4-12合同检查覆盖率使用。
 * 返回百分比值。
 */
export function calcCoverageRate(checkedAmount: number, revenueTotal: number): number {
  if (revenueTotal === 0) return 0
  return (checkedAmount / revenueTotal) * 100
}

// ─── 截止测试公式 ────────────────────────────────────────────────────────────

/**
 * 截止跨期判断: 凭证日期与参考日期位于资产负债表日两侧 → true
 *
 * 即一个日期在BS日之前或当天，另一个在BS日之后或当天，且两者分居两侧。
 * 无效日期返回 false。D4-17/D4-18截止测试使用。
 */
export function isCrossPeriod(voucherDate: string, referenceDate: string, balanceSheetDate: string): boolean {
  const vd = new Date(voucherDate).getTime()
  const rd = new Date(referenceDate).getTime()
  const bs = new Date(balanceSheetDate).getTime()
  if (isNaN(vd) || isNaN(rd) || isNaN(bs)) return false
  // 一个在BS日或之前，另一个在BS日或之后（分居两侧）
  return (vd <= bs && rd >= bs) || (vd >= bs && rd <= bs)
}

/**
 * 跨期天数 = |凭证日期 - 参考日期| (返回绝对值天数)
 *
 * 无效日期返回 0。D4-17/D4-18截止测试天数计算。
 */
export function calcCrossPeriodDays(voucherDate: string, referenceDate: string): number {
  const vd = new Date(voucherDate).getTime()
  const rd = new Date(referenceDate).getTime()
  if (isNaN(vd) || isNaN(rd)) return 0
  const diffMs = Math.abs(vd - rd)
  return Math.round(diffMs / (1000 * 60 * 60 * 24))
}

// ─── 资金回流判定 ────────────────────────────────────────────────────────────

/**
 * 资金回流可疑判定: 同一对手短期内入+出且金额接近(差异<threshold, 默认10%)
 *
 * 条件：
 * 1. Math.abs(inAmount - outAmount) / Math.max(inAmount, outAmount) < threshold
 * 2. daysDiff < 30
 *
 * D4-32 资金流水检查使用。threshold 默认 0.1 (10%)。
 */
export function isSuspiciousFundFlow(
  inAmount: number,
  outAmount: number,
  daysDiff: number,
  threshold: number = 0.1
): boolean {
  const maxAmount = Math.max(inAmount, outAmount)
  if (maxAmount === 0) return false
  const diffRatio = Math.abs(inAmount - outAmount) / maxAmount
  return diffRatio < threshold && daysDiff < 30
}

// ─── IPO/舞弊组可见性 ───────────────────────────────────────────────────────

/** IPO组关键字（小写） */
const IPO_KEYWORDS = ['ipo', 'listed', 'neeq', 'restructuring', 'fraud_risk'] as const

/**
 * IPO/舞弊组可见性: business_category包含指定关键字(大小写不敏感)
 *
 * 关键字：'ipo' | 'listed' | 'neeq' | 'restructuring' | 'fraud_risk'
 * D4 一级Tab"IPO/舞弊"组的 v-if 条件。
 */
export function isIpoGroupVisible(businessCategory: string): boolean {
  const lower = businessCategory.toLowerCase()
  return IPO_KEYWORDS.some(keyword => lower.includes(keyword))
}
