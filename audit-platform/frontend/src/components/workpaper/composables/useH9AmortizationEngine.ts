/**
 * H9 租赁负债 — 摊销表引擎（纯函数，无副作用）
 * 核心：CAS21实际利率法（企业会计准则第21号——租赁 §18-19）
 * - 每期利息 = 期初余额 × 实际利率
 * - 本金偿还 = 每期付款 - 利息费用
 * - 期末余额 = 期初余额 - 本金偿还
 * - 最后一期调整尾差使期末余额归零
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Requirements: 7.1-7.5
 */

// ═══ 类型定义 ═══

export interface AmortizationRow {
  period: number
  beginBalance: number
  payment: number
  interest: number
  principal: number
  endBalance: number
}

// ═══ 核心纯函数 ═══

/**
 * 每期利息 = 期初余额 × 实际利率
 * CAS21 §18：承租人应当按照租赁负债的余额和租赁内含利率（或增量借款利率）
 * 计算租赁负债在租赁期各个期间的利息费用。
 *
 * @param beginBalance 期初余额（>=0）
 * @param rate 实际利率（每期利率，非年化）
 * @returns 利息费用
 */
export function calcInterest(beginBalance: number, rate: number): number {
  return beginBalance * rate
}

/**
 * 本金偿还 = 每期付款 - 利息费用
 * CAS21 §19：每期租赁付款额中扣除利息费用后的余额为本金偿还部分。
 *
 * @param payment 每期付款额
 * @param interest 利息费用
 * @returns 本金偿还额（可能为负，表示余额增长）
 */
export function calcPrincipal(payment: number, interest: number): number {
  return payment - interest
}

/**
 * 期末余额 = 期初余额 - 本金偿还
 * 每期偿还后租赁负债余额递减。
 *
 * @param beginBalance 期初余额
 * @param principal 本金偿还额
 * @returns 期末余额
 */
export function calcEndBalance(beginBalance: number, principal: number): number {
  return beginBalance - principal
}

/**
 * 生成完整摊销表（实际利率法）
 * 最后一期调整付款额使期末余额精确归零（处理尾差）。
 *
 * @param initialBalance 租赁负债初始确认金额（>0）
 * @param payment 每期固定付款额
 * @param rate 每期实际利率
 * @param periods 总期数
 * @returns 完整摊销表行数组
 *
 * 边界情况：
 * - periods=0 → 空数组
 * - rate=0 → 全部付款归本金（无利息）
 * - payment < interest → 负本金（余额增长），仍正确计算
 */
export function generateSchedule(
  initialBalance: number,
  payment: number,
  rate: number,
  periods: number,
): AmortizationRow[] {
  if (periods <= 0) return []

  const schedule: AmortizationRow[] = []
  let balance = initialBalance

  for (let n = 1; n <= periods; n++) {
    const beginBalance = balance
    const interest = calcInterest(beginBalance, rate)

    if (n < periods) {
      // 非最后一期：正常计算
      const principal = calcPrincipal(payment, interest)
      const endBalance = calcEndBalance(beginBalance, principal)
      schedule.push({
        period: n,
        beginBalance,
        payment,
        interest,
        principal,
        endBalance,
      })
      balance = endBalance
    } else {
      // 最后一期：调整付款使期末归零（处理尾差）
      const lastPayment = beginBalance + interest
      const lastPrincipal = calcPrincipal(lastPayment, interest)
      const lastEndBalance = calcEndBalance(beginBalance, lastPrincipal)
      schedule.push({
        period: n,
        beginBalance,
        payment: lastPayment,
        interest,
        principal: lastPrincipal,
        endBalance: lastEndBalance,
      })
    }
  }

  return schedule
}

/**
 * 验证摊销表：最后一期期末余额是否≈0
 * 允许 ±1元 尾差（审计实务惯例）
 *
 * @param schedule 摊销表行数组
 * @returns { isValid: 是否有效, tailDiff: 尾差金额 }
 *
 * 空摊销表视为有效（无需验证）。
 */
export function validateSchedule(schedule: AmortizationRow[]): { isValid: boolean; tailDiff: number } {
  if (schedule.length === 0) {
    return { isValid: true, tailDiff: 0 }
  }
  const lastRow = schedule[schedule.length - 1]
  const tailDiff = lastRow.endBalance
  return {
    isValid: Math.abs(tailDiff) < 1,
    tailDiff,
  }
}
