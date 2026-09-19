/**
 * K0-5/K0-6 替代程序公式引擎（纯函数，可 PBT，K05/K06共用）
 *
 * 5个纯函数：
 * - calcBlockTotal: 区块合计 = Σ金额列
 * - calcCheckRatio: 检查比例 = 已检查金额 / 期末余额
 * - calcRowVariance: 行差异 = 账面金额 - 证据金额
 * - calcReconcileDiff: 对账差异 = 本方余额 - 对方余额
 * - isAbnormal: 是否异常 = |差异| > 0
 */

/**
 * 安全数值转换：任意输入→number，NaN/Infinity→0
 * @param v - 任意输入值
 * @returns 有效数值，无效时返回0
 */
export function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 区块合计：对金额数组求和
 * - 空数组 → 0
 * - 每个元素经 parseNum 兜底（NaN→0）
 *
 * **Validates: Requirements 6.1**
 *
 * @param amounts - 金额数组
 * @returns 合计值
 */
export function calcBlockTotal(amounts: number[]): number {
  if (!amounts.length) return 0
  return amounts.reduce((sum, v) => sum + parseNum(v), 0)
}

/**
 * 检查比例：已检查金额 / 期末余额
 * - 期末余额 ≤ 0 → 返回 0（避免除零和负余额场景）
 * - 参数经 parseNum 兜底
 *
 * **Validates: Requirements 6.2**
 *
 * @param checked - 已检查金额
 * @param balance - 期末余额
 * @returns 检查比例（0~∞）
 */
export function calcCheckRatio(checked: number, balance: number): number {
  const b = parseNum(balance)
  if (b <= 0) return 0
  return parseNum(checked) / b
}

/**
 * 行差异：账面金额 - 证据金额
 * - 零差异恒等：calcRowVariance(v, v) === 0
 * - 参数经 parseNum 兜底
 *
 * **Validates: Requirements 6.3**
 *
 * @param book - 账面金额
 * @param evidence - 证据金额
 * @returns 差异值
 */
export function calcRowVariance(book: number, evidence: number): number {
  return parseNum(book) - parseNum(evidence)
}

/**
 * 对账差异：本方余额 - 对方余额
 * - 零差异恒等：calcReconcileDiff(v, v) === 0
 * - 参数经 parseNum 兜底
 *
 * **Validates: Requirements 6.4**
 *
 * @param self - 本方余额
 * @param other - 对方余额
 * @returns 对账差异
 */
export function calcReconcileDiff(self: number, other: number): number {
  return parseNum(self) - parseNum(other)
}

/**
 * 异常判定：|差异| > 0 即为异常
 * - 参数经 parseNum 兜底
 *
 * **Validates: Requirements 6.5**
 *
 * @param variance - 差异值（来自 calcRowVariance 或 calcReconcileDiff）
 * @returns true=异常，false=无差异
 */
export function isAbnormal(variance: number): boolean {
  return Math.abs(parseNum(variance)) > 0
}

/**
 * Composable 封装：供 Vue 组件以 composable 模式消费
 *
 * @example
 * ```ts
 * const { calcBlockTotal, calcCheckRatio, calcRowVariance, calcReconcileDiff, isAbnormal } = useK0FormulaEngine()
 * ```
 */
export function useK0FormulaEngine() {
  return {
    parseNum,
    calcBlockTotal,
    calcCheckRatio,
    calcRowVariance,
    calcReconcileDiff,
    isAbnormal,
  }
}
