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
 * 折现系数 = 1/(1+r)^n
 * rate 为小数（如 0.05）；n 为折现期数（年或月，与 rate 口径一致）
 */
export function calcDiscountFactor(rate: number, periods: number): number {
  const r = safeNum(rate)
  const n = safeNum(periods)
  if (r <= -1) return 0
  return 1 / Math.pow(1 + r, n)
}

/**
 * 租赁付款额现值 = Σ(付款额 × 折现系数)
 * 对应 xlsx H8-7 section 2.2 / 3.2
 */
export function calcLeasePaymentsPV(
  payments: Array<{ amount: number; periods: number }>,
  rate: number,
): number {
  const r = safeNum(rate)
  return payments.reduce(
    (sum, p) => sum + safeNum(p.amount) * calcDiscountFactor(r, p.periods),
    0,
  )
}

/**
 * 等额年金现值（期末付款）：amount × [1 − (1+r)^−n] / r；r=0 时 = amount×n
 * 便于 H8-7 变更后快速测算新租赁负债
 */
export function calcAnnuityPV(amount: number, rate: number, periods: number): number {
  const a = safeNum(amount)
  const r = safeNum(rate)
  const n = Math.max(0, Math.floor(safeNum(periods)))
  if (n === 0 || a === 0) return 0
  if (r === 0) return a * n
  return a * (1 - Math.pow(1 + r, -n)) / r
}

/**
 * 等额年金现值（期初付款 / 预付）：期末年金 × (1+r)；r=0 时 = amount×n
 * 对齐 xlsx H8-7 首期折现系数=1.0000 的常见口径
 */
export function calcAnnuityDuePV(amount: number, rate: number, periods: number): number {
  const ordinary = calcAnnuityPV(amount, rate, periods)
  const r = safeNum(rate)
  if (ordinary === 0) return 0
  if (r === 0) return ordinary
  return ordinary * (1 + r)
}

/**
 * 按付款时点生成折现期数序列
 * - 期末：1..n
 * - 期初：0..n-1
 */
export function buildDiscountPeriods(
  periods: number,
  timing: '期初' | '期末' = '期末',
): number[] {
  const n = Math.max(0, Math.floor(safeNum(periods)))
  if (n === 0) return []
  if (timing === '期初') return Array.from({ length: n }, (_, i) => i)
  return Array.from({ length: n }, (_, i) => i + 1)
}

/** 单期付款折现行 */
export interface H8PaymentPVRow {
  seq: number
  amount: number
  periods: number
  discountFactor: number
  presentValue: number
}

/**
 * 由等额付款生成逐期折现表，并返回合计现值
 */
export function buildEqualPaymentSchedule(
  amount: number,
  rate: number,
  periods: number,
  timing: '期初' | '期末' = '期末',
): { rows: H8PaymentPVRow[]; totalPV: number } {
  const a = safeNum(amount)
  const periodList = buildDiscountPeriods(periods, timing)
  const rows: H8PaymentPVRow[] = periodList.map((p, i) => {
    const df = calcDiscountFactor(rate, p)
    const pv = a * df
    return { seq: i + 1, amount: a, periods: p, discountFactor: df, presentValue: pv }
  })
  const totalPV = rows.reduce((s, r) => s + r.presentValue, 0)
  return { rows, totalPV }
}

/**
 * 由自定义付款流生成折现表
 */
export function buildCustomPaymentSchedule(
  payments: Array<{ amount: number; periods: number }>,
  rate: number,
): { rows: H8PaymentPVRow[]; totalPV: number } {
  const rows: H8PaymentPVRow[] = payments.map((p, i) => {
    const amount = safeNum(p.amount)
    const periods = safeNum(p.periods)
    const df = calcDiscountFactor(rate, periods)
    return {
      seq: i + 1,
      amount,
      periods,
      discountFactor: df,
      presentValue: amount * df,
    }
  })
  return { rows, totalPV: rows.reduce((s, r) => s + r.presentValue, 0) }
}

/**
 * 租赁负债调整额 = 变更后付款额现值 − 变更日账面租赁负债
 * CAS21第29条：其他变更以修订折现率重新计量租赁负债
 */
export function calcLiabilityAdjustment(
  newLiabilityPV: number,
  carryingLiability: number,
): number {
  return safeNum(newLiabilityPV) - safeNum(carryingLiability)
}

/**
 * 范围减少：按比例终止部分 ROU/负债，差额计入损益
 * reductionRatio ∈ [0,1]（如 0.3 = 终止 30%）
 */
export function calcScopeReduction(
  carryingLiability: number,
  carryingROU: number,
  reductionRatio: number,
): {
  ratio: number
  terminatedLiability: number
  terminatedROU: number
  gainLoss: number
  remainingLiability: number
  remainingROU: number
  /** ROU 调整额（通常为负）= −terminatedROU */
  rouAdjustment: number
} {
  const ratio = Math.min(1, Math.max(0, safeNum(reductionRatio)))
  const liab = safeNum(carryingLiability)
  const rou = safeNum(carryingROU)
  const terminatedLiability = liab * ratio
  const terminatedROU = rou * ratio
  return {
    ratio,
    terminatedLiability,
    terminatedROU,
    gainLoss: calcTerminationGainLoss(terminatedLiability, terminatedROU),
    remainingLiability: liab - terminatedLiability,
    remainingROU: rou - terminatedROU,
    rouAdjustment: -terminatedROU,
  }
}

/**
 * 用 H8-6 计量参数估算变更日租赁负债账面（简易按年滚动）
 * discountRatePct：与 H8-6 UI 一致，为百分数（5 = 5%）
 * rentalPerPeriod：按年分支视为年付款；按月分支需传入年化或配合 yearsElapsed
 */
export function estimateLiabilityAtDate(params: {
  leaseLiabilityInitial: number
  discountRatePct: number
  rentalPerPeriod: number
  leaseTermMonths: number
  /** 自起租至变更日已过年数（可含小数） */
  yearsElapsed: number
  paymentTiming?: '期初' | '期末'
}): number {
  let bal = safeNum(params.leaseLiabilityInitial)
  const r = safeNum(params.discountRatePct) / 100
  const pay = safeNum(params.rentalPerPeriod)
  const maxYears = Math.max(0, Math.ceil(safeNum(params.leaseTermMonths) / 12))
  const years = Math.min(maxYears, Math.max(0, Math.floor(safeNum(params.yearsElapsed))))
  for (let i = 0; i < years; i++) {
    const interest = bal * r
    // 期初付款：首年可能已在初始计量时作为预付从负债中剔除；简化：每年 bal = bal*(1+r) - pay
    bal = bal + interest - pay
    if (bal < 0) bal = 0
  }
  return bal
}

/** 是/否/空 三态（H8-7 判定树） */
export type H8YesNo = '是' | '否' | ''

/** 变更类型（CAS21第28-30条） */
export type H8ModificationTypeDerived = '单独租赁' | '范围减少' | '其他变更' | ''

/**
 * 由判定树推导变更类型（1.1 与 1.2 互斥）：
 * - 扩大范围 + 对价相当单独价格 → 单独租赁
 * - 否则若减少范围/缩短租赁期 → 范围减少
 * - 否则已回答判定条件 → 其他变更（重新计量）
 */
export function deriveModificationType(
  expandsScope: H8YesNo,
  standalonePrice: H8YesNo,
  scopeReduction: H8YesNo,
): H8ModificationTypeDerived {
  // 1.1 两条件同时满足 → 单独租赁（与 1.2 互斥）
  if (expandsScope === '是' && standalonePrice === '是') return '单独租赁'
  // 1.2：范围减少 / 其他变更（须明确勾选）
  if (scopeReduction === '是') return '范围减少'
  if (scopeReduction === '否') return '其他变更'
  return ''
}

/** 是否应按单独租赁处理（1.1 两条件同时满足） */
export function isSeparateLease(expandsScope: H8YesNo, standalonePrice: H8YesNo): boolean {
  return expandsScope === '是' && standalonePrice === '是'
}

/**
 * 按变更类型给出默认会计处理说明（可被用户覆盖）
 */
export function suggestAccountingTreatment(type: H8ModificationTypeDerived): string {
  switch (type) {
    case '单独租赁':
      return '应当将该租赁变更作为一项单独租赁进行会计处理（CAS21第28条）'
    case '范围减少':
      return '按减少比例终止部分使用权资产与租赁负债，差额计入当期损益（CAS21第29条）'
    case '其他变更':
      return '分摊变更后合同对价，重新确定租赁期，按变更后付款额与修订折现率现值重新计量租赁负债，并相应调整使用权资产（CAS21第29-30条）'
    default:
      return ''
  }
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
