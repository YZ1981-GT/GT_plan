/**
 * H8 使用权资产 — CAS21计量引擎（纯函数，无副作用）
 * 核心公式：CAS21新租赁准则（企业会计准则第21号——租赁）
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Requirements: 10.1-10.4, 8.2-8.3
 */

// ─── 辅助：安全转数字（NaN/undefined/null → 0） ───────────────────────────────
function safeNum(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 初始计量：使用权资产 = 租赁负债初始确认(H9) + 初始直接费用 - 租赁激励
 * CAS21第16条
 */
export function calcInitialMeasurement(
  leaseLiability: number,
  directCost: number,
  incentive: number
): number {
  return safeNum(leaseLiability) + safeNum(directCost) - safeNum(incentive)
}

/**
 * 折旧期确定：min(租赁期, 使用寿命)
 * CAS21第21条：承租人应当自租赁期开始日起对使用权资产计提折旧。
 * 能够合理确定租赁期届满时取得租赁资产所有权的，应当在使用寿命内计提折旧；
 * 否则在租赁期与使用寿命两者孰短期间内计提折旧。
 * 两个参数单位必须一致（月）。
 */
export function calcDepreciationPeriod(leaseTerm: number, usefulLife: number): number {
  const lt = safeNum(leaseTerm)
  const ul = safeNum(usefulLife)
  // 至少为0（防止负值）
  return Math.min(Math.max(lt, 0), Math.max(ul, 0))
}

/**
 * 终止损益：租赁负债余额 - 使用权资产净值
 * 结果>0为收益，<0为损失
 * 用于H8-12减少检查表
 */
export function calcTerminationGainLoss(
  liabilityBalance: number,
  rouNetValue: number
): number {
  return safeNum(liabilityBalance) - safeNum(rouNetValue)
}

/**
 * 重新计量：旧使用权资产 + 调整额
 * CAS21第28条：承租人应当按照规定重新计量租赁负债，同时相应调整使用权资产。
 * adjustment可正可负（租赁修改增加/减少）
 */
export function calcRemeasurement(oldROU: number, adjustment: number): number {
  return safeNum(oldROU) + safeNum(adjustment)
}

/**
 * 简化判断：是否短期租赁
 * CAS21第32条：租赁期不超过12个月的租赁为短期租赁。
 * 含购买选择权的不属于短期租赁（调用方应先排除购买选择权情形）。
 */
export function isShortTermLease(leaseTermMonths: number): boolean {
  return safeNum(leaseTermMonths) <= 12
}

/**
 * 简化判断：是否低价值资产租赁
 * CAS21第32条：单项租赁资产为全新资产时价值较低。
 * 实务中一般以40000元人民币为阈值。
 * threshold参数可选，默认40000。
 */
export function isLowValueLease(newAssetValue: number, threshold?: number): boolean {
  const t = threshold !== undefined && threshold !== null ? safeNum(threshold) : 40000
  return safeNum(newAssetValue) <= t
}
