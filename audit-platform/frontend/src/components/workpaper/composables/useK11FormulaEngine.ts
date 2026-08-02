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
 * 源底稿核对差异 = K11金额 - 源底稿金额
 * 用于K11-2明细表各行与对应源底稿(F2/H1/I1/I3等)减值计提金额交叉核对
 * 差异为0表示一致；差异非零应红色标记提示
 * Validates: Requirements 3.2, 6.6
 */
export function calcSourceVariance(k11Amount: number, sourceAmount: number): number {
  return parseNum(k11Amount) - parseNum(sourceAmount)
}

/**
 * 合计行求和 = SUM(数组元素)，忽略NaN/null/undefined
 * 空数组返回0；非数组返回0
 * 适用：审定表合计行、明细表分类小计、减值汇总
 * Validates: Requirements 6.7
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}
