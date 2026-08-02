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
 * 合计行求和 = SUM(数组元素)，忽略NaN/null/undefined
 * 空数组返回0；非数组返回0
 * 适用：审定表合计行、明细表分类小计
 * Validates: Requirements 9.6
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}
