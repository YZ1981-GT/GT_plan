/**
 * useJ3FormulaEngine — J3 股份支付费用分摊纯函数引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * J3 无独立科目，费用走 EventBus → M4(权益结算)/J1(现金结算)/K8K9(管理费用)。
 *
 * 核心公式（CAS11）：
 * - 累计费用 = 总公允价值 × MIN(已服务年数/等待期, 1)
 * - 本期费用 = 累计费用 - 以前年度累计已确认
 * - 剩余费用 = 总公允价值 - 累计费用
 * - 总公允价值 = 单位公允价值 × 数量
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 2.2-2.6, 4.1-4.4
 */

// ─── 数值解析 ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/空串/NaN/Infinity → 0
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── 等待期费用分摊 ──────────────────────────────────────────────────────────

/**
 * 累计确认费用 = 总公允价值 × MIN(已服务年数/等待期, 1)
 *
 * CAS11：等待期内每个资产负债表日，将取得的服务按授予日公允价值计量，
 * 确认为成本或费用和资本公积（权益结算）或应付职工薪酬（现金结算）。
 *
 * @param totalFV 总公允价值（>0）
 * @param vestingPeriod 等待期（年，>0）
 * @param serviceYears 已服务年数（>=0）
 * @returns 累计应确认费用
 */
export function calcCumulativeExpense(totalFV: number, vestingPeriod: number, serviceYears: number): number {
  if (totalFV <= 0 || vestingPeriod <= 0) return 0
  if (serviceYears <= 0) return 0
  return totalFV * Math.min(serviceYears / vestingPeriod, 1)
}

/**
 * 本期确认费用 = 累计应确认 - 以前年度累计已确认
 *
 * CAS11：每个资产负债表日确认的费用 = 累计应确认金额 - 以前期间已确认金额。
 * 确保估计变更（如员工离职率变化）能正确调整。
 *
 * @param totalFV 总公允价值
 * @param vestingPeriod 等待期（年）
 * @param serviceYears 已服务年数
 * @param priorCumulative 以前年度累计已确认金额
 * @returns 本期应确认费用
 */
export function calcVestingExpense(
  totalFV: number,
  vestingPeriod: number,
  serviceYears: number,
  priorCumulative: number,
): number {
  const cumulative = calcCumulativeExpense(totalFV, vestingPeriod, serviceYears)
  return cumulative - priorCumulative
}

/**
 * 剩余待确认费用 = 总公允价值 - 已确认累计费用
 *
 * @param totalFV 总公允价值
 * @param cumulativeExpense 已确认累计费用
 * @returns 剩余待确认金额
 */
export function calcRemainingExpense(totalFV: number, cumulativeExpense: number): number {
  return totalFV - cumulativeExpense
}

// ─── 公允价值计算 ────────────────────────────────────────────────────────────

/**
 * 总公允价值 = 单位公允价值 × 权益工具数量
 *
 * @param unitFV 每份权益工具公允价值（>0）
 * @param quantity 权益工具数量（整数，>0）
 * @returns 总公允价值
 */
export function calcTotalFairValue(unitFV: number, quantity: number): number {
  return unitFV * quantity
}

// ─── 合计/小计公式 ──────────────────────────────────────────────────────────

/**
 * 合计行 = SUM(数组)
 *
 * 通用求和，适用于 J3-1/J3-2 所有合计行。
 */
export function calcSubtotal(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0)
}

// ─── 变动分析 ────────────────────────────────────────────────────────────────

/**
 * 变动额 = 本期 - 上期
 */
export function calcChangeAmount(current: number, prior: number): number {
  return current - prior
}

/**
 * 变动率（期初=0时返回'N/A'）
 */
export function calcChangeRate(prior: number, current: number): number | '' | 'N/A' {
  if (prior === 0 && current === 0) return ''
  if (prior === 0) return 'N/A'
  return (current - prior) / prior
}
