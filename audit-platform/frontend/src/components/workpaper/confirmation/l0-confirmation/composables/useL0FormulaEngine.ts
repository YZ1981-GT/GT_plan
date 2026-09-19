/**
 * useL0FormulaEngine — L0 债务循环函证公式引擎（纯函数，可 PBT）
 *
 * 4 个纯函数：
 * - calcBlockTotal：区块合计 = Σ金额列
 * - calcRepaymentRatio：还款检查比例 = 已检查还款 / 期末余额
 * - calcReconcileDiff：对账差异 = 账面余额 - 银行对账单余额
 * - isAbnormal：是否异常 = |对账差异| > 0
 */

/**
 * 安全数值解析（NaN → 0）
 */
function parseNum(v: unknown): number {
  const n = Number(v)
  return isNaN(n) ? 0 : n
}

/**
 * 区块合计 = Σ金额列
 * 空数组 → 0；非数值按 0 处理
 */
export function calcBlockTotal(amounts: number[]): number {
  if (!amounts || amounts.length === 0) return 0
  let sum = 0
  for (const v of amounts) {
    sum += parseNum(v)
  }
  return sum
}

/**
 * 还款检查比例 = 已检查还款金额 / 期末余额
 * 期末余额 = 0 → 返回 0（避免除零）
 */
export function calcRepaymentRatio(repaid: number, balance: number): number {
  if (balance === 0) return 0
  return repaid / balance
}

/**
 * 对账差异 = 账面余额 - 银行对账单余额
 */
export function calcReconcileDiff(book: number, statement: number): number {
  return book - statement
}

/**
 * 是否异常 = |对账差异| > 0
 */
export function isAbnormal(variance: number): boolean {
  return Math.abs(variance) > 0
}
