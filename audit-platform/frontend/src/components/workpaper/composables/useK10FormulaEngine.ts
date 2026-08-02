import { legacyCalcIncomeStatementOccurrence } from './shared/plAdjudicationModel'
/**
 * 🔴 已收敛到共享模型 `shared/plAdjudicationModel.ts`。
 * 此处保留导出名以免破坏消费方 import，内部委托共享实现。
 * 后端已保证对侧为 0，故 debit - credit（或 credit - debit）= 非零侧 = unadjusted。
 */
export function calcIncomeStatementOccurrence(a: number, b: number): number {
  return legacyCalcIncomeStatementOccurrence(a, b)
}

/**
 * CP-K10-05: 同比变动率 = (本期 - 上期) / 上期
 * 上期为0时返回null（除零保护，前端显示"—"）
 *
 * @param current 本期发生额
 * @param prior 上期发生额
 * @returns 变动率（小数形式，如0.5表示50%增长）或null
 *
 * Validates: Requirements 7.6
 */
export function calcYoYChange(current: number, prior: number): number | null {
  const p = parseNum(prior)
  if (p === 0) return null
  return (parseNum(current) - p) / p
}

/**
 * CP-K10-06: 合计行求和 = SUM(数组元素)，忽略NaN/null/undefined
 * 空数组返回0；非数组返回0
 * 适用：审定表合计行、明细表分类小计
 *
 * Validates: Requirements 7.7
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}
