/**
 * useS35FormulaEngine — S35 明细核查子表公式引擎（纯函数）
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/  Task 4.2
 * Requirements: 4.2
 *
 * 三个明细核查子表的公式：
 * - S35-1-1: 合计 = SUM(数值列), 占比 = 合计 / 发行人相应指标金额
 * - S35-2-1: 投资占比 = 投资金额 / 归母净利润
 * - S35-3-1: 无公式
 *
 * Property 5: 明细子表汇总公式确定性
 * Validates: Requirements 4.2
 *
 * 所有函数为纯函数，导出供 PBT 测试。
 */

// ─── S35-1-1 关联交易核查公式 ───

/**
 * 合计 = SUM(母公司 + 子公司1 + 子公司2 + ...)
 * 忽略 null/undefined/NaN，纯数值求和。
 *
 * @param amounts - 各公司金额数组（母公司 + 各子公司）
 * @returns 合计金额，若全部为无效值则返回 0
 *
 * Property 5: 明细子表汇总公式确定性
 * Validates: Requirements 4.2
 */
export function calcS35_1_1_Total(amounts: (number | null | undefined)[]): number {
  let sum = 0
  for (const v of amounts) {
    if (v != null && !Number.isNaN(v)) {
      sum += v
    }
  }
  return sum
}

/**
 * 占比 = 合计 / 发行人相应指标金额
 * 除数为 0 或无效时返回 null（不显示占比）。
 *
 * @param total - 合计金额（SUM 结果）
 * @param indicator - 发行人相应指标金额
 * @returns 占比（小数），或 null（除数无效）
 *
 * Property 5: 明细子表汇总公式确定性
 * Validates: Requirements 4.2
 */
export function calcS35_1_1_Ratio(
  total: number | null | undefined,
  indicator: number | null | undefined,
): number | null {
  if (total == null || Number.isNaN(total)) return null
  if (indicator == null || Number.isNaN(indicator) || indicator === 0) return null
  return total / indicator
}

// ─── S35-2-1 财务性投资核查公式 ───

/**
 * 投资占比 = 投资金额 / 归母净利润
 * 除数为 0 或无效时返回 null。
 *
 * @param investAmount - 投资金额
 * @param netProfit - 归母净利润
 * @returns 投资占比（小数），或 null（除数无效）
 *
 * Property 5: 明细子表汇总公式确定性
 * Validates: Requirements 4.2
 */
export function calcS35_2_1_InvestRatio(
  investAmount: number | null | undefined,
  netProfit: number | null | undefined,
): number | null {
  if (investAmount == null || Number.isNaN(investAmount)) return null
  if (netProfit == null || Number.isNaN(netProfit) || netProfit === 0) return null
  return investAmount / netProfit
}

// ─── S35-3-1 现金分红核查：无公式 ───

// ─── 格式化辅助 ───

/**
 * 格式化占比为百分比字符串（保留 2 位小数）。
 * null → '—'
 */
export function formatPercent(ratio: number | null): string {
  if (ratio == null) return '—'
  return `${(ratio * 100).toFixed(2)}%`
}

/**
 * 格式化金额（千分位，保留 2 位小数）。
 * null/undefined → '—'
 */
export function formatAmount(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
