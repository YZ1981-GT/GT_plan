/**
 * I1 无形资产 — 摊销计算引擎（纯函数，无副作用）
 * 支持直线法（剩余年限法）+ 含减值重算基数 + DCF现值 + 终值 + 可收回金额 + 减值金额
 * Spec: .kiro/specs/i1-intangible-assets/
 * Requirements: 11.4-11.5, 12.2, 13.2-13.3
 */

/**
 * 直线法月摊销 = (原值 - 残值) / 使用寿命月数
 * @param cost 无形资产原值
 * @param salvage 预计残值
 * @param usefulLifeMonths 使用寿命（月）
 * @returns 月摊销额；usefulLifeMonths <= 0 时返回 0
 */
export function calcStraightLineAmort(cost: number, salvage: number, usefulLifeMonths: number): number {
  if (usefulLifeMonths <= 0) return 0
  return (cost - salvage) / usefulLifeMonths
}

/**
 * 剩余年限法月摊销 = (原值 - 残值 - 累计摊销 - 减值准备) / 剩余月数
 * 适用于I1-10不含减值版本（此时impairment传0）
 * @param cost 无形资产原值
 * @param salvage 预计残值
 * @param accAmort 已计提累计摊销
 * @param impairment 已计提减值准备
 * @param remainingMonths 剩余使用月数
 * @returns 月摊销额；remainingMonths <= 0 时返回 0
 */
export function calcRemainingLifeAmort(
  cost: number,
  salvage: number,
  accAmort: number,
  impairment: number,
  remainingMonths: number
): number {
  if (remainingMonths <= 0) return 0
  return (cost - salvage - accAmort - impairment) / remainingMonths
}

/**
 * 含减值重算基数摊销（减值发生月重新计算剩余摊销基数）
 * 公式与 calcRemainingLifeAmort 相同：(原值 - 残值 - 累计摊销 - 减值) / 剩余月数
 * 独立导出以语义区分：I1-11含减值版本在减值发生后调用此函数重新计算
 * @param cost 无形资产原值
 * @param salvage 预计残值
 * @param accAmort 已计提累计摊销（含减值前已摊销部分）
 * @param impairment 已计提减值准备（含本次新计提）
 * @param remainingMonths 减值后剩余使用月数
 * @returns 减值后月摊销额；remainingMonths <= 0 时返回 0
 */
export function calcAmortWithImpairment(
  cost: number,
  salvage: number,
  accAmort: number,
  impairment: number,
  remainingMonths: number
): number {
  if (remainingMonths <= 0) return 0
  return (cost - salvage - accAmort - impairment) / remainingMonths
}

/**
 * DCF现值 = Σ(CF_i / (1+r)^(i+1))  (i从0开始，第0期对应第1年末)
 * @param cashFlows 各期预测现金流数组
 * @param discountRate 折现率 (如0.08表示8%)
 * @returns 现值合计；空数组返回0；discountRate <= 0 返回0（无效折现率）
 */
export function calcDcfPresentValue(cashFlows: number[], discountRate: number): number {
  if (cashFlows.length === 0) return 0
  if (discountRate <= 0) return 0
  let pv = 0
  for (let i = 0; i < cashFlows.length; i++) {
    pv += cashFlows[i] / Math.pow(1 + discountRate, i + 1)
  }
  return pv
}

/**
 * 终值（永续价值）= 永续现金流 / (折现率 - 增长率)
 * Gordon Growth Model（永续增长模型）
 * @param perpetuityCF 永续年金现金流（预测期最后一年的稳态现金流）
 * @param discountRate 折现率
 * @param growthRate 永续增长率
 * @returns 终值；当 discountRate <= growthRate 时返回 0（Gordon模型无效）
 */
export function calcTerminalValue(perpetuityCF: number, discountRate: number, growthRate: number): number {
  if (discountRate <= growthRate) return 0
  return perpetuityCF / (discountRate - growthRate)
}

/**
 * 可收回金额 = MAX(公允价值 - 处置费用, 使用价值DCF)
 * CAS8第六条：取两者中的较高者
 * @param fairValueLessDisposal 公允价值减去处置费用后的净额
 * @param valueInUse 使用价值（DCF现值）
 * @returns 可收回金额（两者取大）
 */
export function calcRecoverableAmount(fairValueLessDisposal: number, valueInUse: number): number {
  return Math.max(fairValueLessDisposal, valueInUse)
}

/**
 * 减值金额 = MAX(账面净值 - 可收回金额, 0)，但不超过账面净值
 * CAS8第十五条：资产减值损失一经确认不得转回（无形资产）
 * @param bookValue 账面净值（原值 - 累计摊销 - 已有减值）
 * @param recoverableAmount 可收回金额
 * @returns 应计提减值金额，范围 [0, bookValue]
 */
export function calcImpairmentAmount(bookValue: number, recoverableAmount: number): number {
  const raw = bookValue - recoverableAmount
  if (raw <= 0) return 0
  return Math.min(raw, bookValue)
}
