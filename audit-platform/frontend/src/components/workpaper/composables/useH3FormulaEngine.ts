/**
 * H3 投资性房地产 — 公式引擎（纯函数，无副作用）
 * 科目：1503投资性房地产（借方/资产类）+ 成本模式下1504累计折旧（贷方/资产备抵类）
 * 核心特征：双计量模式(成本/公允价值) + 互转三方向 + 租金27公式
 * Spec: .kiro/specs/h3-investment-property/
 */

// ---------- 基础审定公式 ----------

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末余额（借方科目1503）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/** 备抵类期末余额（贷方科目1504累计折旧）：期末 = 期初 + 贷方发生 - 借方发生 */
export function calcContraEndBalance(begin: number, debit: number, credit: number): number {
  return begin + credit - debit
}

// ---------- 成本模式公式 ----------

/**
 * 成本模式三角勾稽差额
 * 差额 = end - (begin + increase - decrease + transfer)
 * 返回0表示勾稽平衡，非0表示存在差异
 */
export function calcCostTriangle(
  begin: number,
  increase: number,
  decrease: number,
  transfer: number,
  end: number,
): number {
  return end - (begin + increase - decrease + transfer)
}

// ---------- 公允价值模式公式 ----------

/** 公允模式期末 = 期初 + 增加 - 减少 + 转换 + 公允价值变动 */
export function calcFairEndBalance(
  begin: number,
  increase: number,
  decrease: number,
  transfer: number,
  fairChange: number,
): number {
  return begin + increase - decrease + transfer + fairChange
}

/** 公允价值变动 = 期末公允 - 期初公允 */
export function calcFairValueChange(endFair: number, beginFair: number): number {
  return endFair - beginFair
}

// ---------- 合计 ----------

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

// ---------- 租金收入公式 ----------

/** 年租金 = 月租 × 月数 × (1 - 空置率) */
export function calcRentalIncome(monthlyRent: number, months: number, vacancyRate: number): number {
  return monthlyRent * months * (1 - vacancyRate)
}

/** 租金回报率 = 年租金 / 账面价值；账面价值为0时返回null */
export function calcRentalYield(annualRent: number, bookValue: number): number | null {
  if (bookValue === 0) return null
  return annualRent / bookValue
}

/** 空置损失 = 月租 × 空置月数 */
export function calcVacancyLoss(monthlyRent: number, vacantMonths: number): number {
  return monthlyRent * vacantMonths
}

/** 每平米租金 = 月租 / 面积；面积为0时返回null */
export function calcPerSqmRent(monthlyRent: number, area: number): number | null {
  if (area === 0) return null
  return monthlyRent / area
}

// ---------- 折旧公式（成本模式） ----------

/** 月折旧（直线法）= 原值 × (1 - 残值率) / 使用年限 / 12 */
export function calcStraightLineDepreciation(cost: number, salvageRate: number, usefulLife: number): number {
  return (cost * (1 - salvageRate)) / usefulLife / 12
}

/**
 * 含减值月折旧（对齐 H1-12 / Excel H3-7 含减值底稿）
 * 减值后：剩余可折旧额 = 原值 − 减值时累计折旧 − 减值准备 − 残值
 * 新月折旧 = 剩余可折旧额 / 剩余月数
 */
export function calcDepreciationWithImpairment(
  cost: number,
  salvageRate: number,
  usefulLife: number,
  impairment: number,
  elapsedMonths: number,
  accDepAtImpairment?: number,
): number {
  const totalMonths = usefulLife * 12
  const remainingMonths = totalMonths - elapsedMonths
  if (remainingMonths <= 0 || usefulLife <= 0) return 0
  const salvage = cost * salvageRate
  const preMonthly = calcStraightLineDepreciation(cost, salvageRate, usefulLife)
  const accDep = accDepAtImpairment != null
    ? Math.max(accDepAtImpairment, 0)
    : preMonthly * Math.max(elapsedMonths, 0)
  const carrying = cost - accDep - Math.max(impairment, 0)
  const remainingDepreciable = Math.max(carrying - salvage, 0)
  return remainingDepreciable / remainingMonths
}

// ---------- DCF 现值（减值测试用） ----------

/** DCF现值 = Σ(cf_i / (1+r)^(i+1))，i从0开始 */
export function calcDcfPresentValue(cashFlows: number[], discountRate: number): number {
  if (cashFlows.length === 0) return 0
  if (discountRate <= -1) return 0
  return cashFlows.reduce((pv, cf, i) => pv + cf / Math.pow(1 + discountRate, i + 1), 0)
}

/** 终值（永续价值）= 永续现金流 / (折现率 − 增长率)；r≤g 时返回 0 */
export function calcTerminalValue(perpetuityCF: number, discountRate: number, growthRate: number): number {
  if (discountRate <= growthRate) return 0
  return perpetuityCF / (discountRate - growthRate)
}

// ---------- 借贷平衡 ----------

/**
 * 借贷平衡检查
 * 比较借方合计与贷方合计，使用 1e-6 容差处理浮点精度
 * 返回true表示平衡
 */
export function isBalanced(entries: { debit: number; credit: number }[]): boolean {
  const totalDebit = entries.reduce((sum, e) => sum + e.debit, 0)
  const totalCredit = entries.reduce((sum, e) => sum + e.credit, 0)
  return Math.abs(totalDebit - totalCredit) < 1e-6
}
