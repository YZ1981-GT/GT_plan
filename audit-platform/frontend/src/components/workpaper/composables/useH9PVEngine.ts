/**
 * H9 租赁负债 — 现值计算引擎（纯函数，无副作用）
 * 核心：CAS21 §14 租赁负债 = 未来租赁付款额的现值
 * - 现值折现：PV = Σ(payment_i / (1+rate)^i)
 * - 等额年金现值：PV = payment × (1 - (1+rate)^(-n)) / rate
 * - 增量借款利率(IBR)：市场基准 + 信用利差 + 期限调整
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Requirements: 6.1-6.4
 */

// ═══ 核心纯函数 ═══

/**
 * 现值计算（不等额付款）
 * CAS21 §14：租赁负债应当按照租赁期开始日尚未支付的租赁付款额的现值进行初始计量。
 * PV = Σ(payments[i] / (1+rate)^(i+1))，i=0..n-1
 *
 * @param payments 各期付款金额数组
 * @param rate 每期折现率（非年化，已按付款频率折算）
 * @returns 现值合计
 *
 * 边界情况：
 * - rate=0 → PV = sum of all payments（零利率恒等，Property P8）
 * - 空数组 → 0
 */
export function calcPresentValue(payments: number[], rate: number): number {
  if (payments.length === 0) return 0
  if (rate === 0) return payments.reduce((a, b) => a + b, 0)

  let pv = 0
  for (let i = 0; i < payments.length; i++) {
    pv += payments[i] / Math.pow(1 + rate, i + 1)
  }
  return pv
}

/**
 * 等额年金现值（普通年金）
 * PV = payment × (1 - (1+rate)^(-periods)) / rate
 * CAS21 §14 等额付款简化公式。
 *
 * @param payment 每期等额付款
 * @param rate 每期折现率（>0 时使用年金公式；=0 时退化为 payment×periods）
 * @param periods 总期数
 * @returns 年金现值
 *
 * 边界情况：
 * - rate=0 → payment × periods
 * - periods=0 → 0
 * - payment=0 → 0
 */
export function calcAnnuityPV(payment: number, rate: number, periods: number): number {
  if (periods <= 0) return 0
  if (payment === 0) return 0
  if (rate === 0) return payment * periods

  return payment * (1 - Math.pow(1 + rate, -periods)) / rate
}

/**
 * 增量借款利率(IBR)确定
 * IBR = 市场基准利率 + 信用利差 + 期限调整
 * CAS21 §15：增量借款利率是指承租人在类似经济环境下为获得与使用权资产价值
 * 接近的资产、在类似期限以类似抵押条件借入资金须支付的利率。
 * 审计判断优先，引擎辅助。
 *
 * @param marketRate 市场基准利率（如LPR/国债收益率）
 * @param creditSpread 信用利差（反映承租人信用风险）
 * @param termAdjust 期限调整（反映租赁期限对利率的影响）
 * @returns 增量借款利率
 */
export function calcIBR(marketRate: number, creditSpread: number, termAdjust: number): number {
  return marketRate + creditSpread + termAdjust
}
