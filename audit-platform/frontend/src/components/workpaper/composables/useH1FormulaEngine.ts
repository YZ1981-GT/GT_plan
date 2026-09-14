/**
 * H1 固定资产 — 公式引擎（纯函数，无副作用）
 * 科目：1601固定资产（借方/资产类）+ 1602累计折旧（贷方/资产备抵类）
 * Spec: .kiro/specs/h1-fixed-assets/
 */

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末余额（借方科目1601）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/** 备抵类期末余额（贷方科目1602累计折旧）：期末 = 期初 + 贷方发生 - 借方发生 */
export function calcContraEndBalance(begin: number, debit: number, credit: number): number {
  return begin + credit - debit
}

/**
 * 三角勾稽校验：差额 = 期末 - (期初 + 增加 - 减少)
 * 返回0表示勾稽平衡，非0表示存在差异
 */
export function calcTriangleReconciliation(begin: number, increase: number, decrease: number, end: number): number {
  return end - (begin + increase - decrease)
}

/** 净值 = 原值 - 累计折旧 - 减值准备 */
export function calcNetValue(originalCost: number, accDepreciation: number, impairment: number): number {
  return originalCost - accDepreciation - impairment
}

/** 变动率(%) = (本期 - 上期) / 上期 × 100；上期为0时返回null */
export function calcChangeRate(current: number, prior: number): number | null {
  if (prior === 0) return null
  return (current - prior) / prior * 100
}

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

/** 占比(%) = 项目 / 合计 × 100；合计为0时返回null */
export function calcProportion(item: number, total: number): number | null {
  if (total === 0) return null
  return item / total * 100
}

/** 成新率(%) = 净值 / 原值 × 100；原值为0时返回null */
export function calcNewRate(netValue: number, originalCost: number): number | null {
  if (originalCost === 0) return null
  return netValue / originalCost * 100
}

/** 平均使用年限(年) = 原值 / 年折旧额；年折旧为0时返回null */
export function calcAvgUsefulLife(originalCost: number, annualDepreciation: number): number | null {
  if (!(annualDepreciation > 0)) return null
  return originalCost / annualDepreciation
}

/** 剩余年限(年) = 净值 / 年折旧额；年折旧为0时返回null */
export function calcRemainingLife(netValue: number, annualDepreciation: number): number | null {
  if (!(annualDepreciation > 0)) return null
  return netValue / annualDepreciation
}

/** 比率(%) = 分子 / 分母 × 100；分母为0时返回null */
export function calcRatioPct(numerator: number, denominator: number): number | null {
  if (!(denominator > 0)) return null
  return numerator / denominator * 100
}

/** 比率倍数 = 分子 / 分母；分母为0时返回null（如原值/产量） */
export function calcRatioMultiple(numerator: number, denominator: number): number | null {
  if (!(denominator > 0)) return null
  return numerator / denominator
}

/** 处置损益 = 处置收入 - 净值 - 处置费用 */
export function calcDisposalGainLoss(income: number, netValue: number, disposalCost: number): number {
  return income - netValue - disposalCost
}

/** 关联价格差异率(%) = (交易价格 - 公允价值) / 公允价值 × 100；公允价值为0时返回null */
export function calcPriceDiffRate(transactionPrice: number, fairValue: number): number | null {
  if (fairValue === 0) return null
  return (transactionPrice - fairValue) / fairValue * 100
}

/** 权属差异 = 账面价值 - 证载价值 */
export function calcTitleDiff(bookValue: number, certValue: number): number {
  return bookValue - certValue
}

/** 租赁收益率(%) = 净收益 / 原值 × 100；原值为0时返回null */
export function calcLeaseReturnRate(netIncome: number, originalCost: number): number | null {
  if (originalCost === 0) return null
  return netIncome / originalCost * 100
}

/** 应收融资租赁款 = 最低租赁收款额 + 初始直接费用（出租人初始计量，对齐 H1-20） */
export function calcFinanceLeaseReceivable(minLeaseReceipt: number, initialDirectCosts: number): number {
  return (Number(minLeaseReceipt) || 0) + (Number(initialDirectCosts) || 0)
}

/** 毛投资额 = 最低租赁收款额 + 未担保余值（可再加初始直接费用，由调用方决定） */
export function calcGrossLeaseInvestment(
  minLeaseReceipt: number,
  unguaranteedResidual = 0,
  initialDirectCosts = 0,
): number {
  return (Number(minLeaseReceipt) || 0)
    + (Number(unguaranteedResidual) || 0)
    + (Number(initialDirectCosts) || 0)
}

/**
 * 未确认融资收益 = (最低租赁收款额 + 未担保余值) − 租赁投资净额
 * 未担保余值缺省为 0，兼容旧口径。
 */
export function calcUnearnedFinanceIncome(
  minLeaseReceipt: number,
  netInvestment: number,
  unguaranteedResidual = 0,
): number {
  return (Number(minLeaseReceipt) || 0)
    + (Number(unguaranteedResidual) || 0)
    - (Number(netInvestment) || 0)
}

/** 现值/公允价值占比(%)；公允价值为0时返回null。≥90%通常满足融资租赁第④项 */
export function calcPvToFvRatio(presentValue: number, fairValue: number): number | null {
  if (!(Number(fairValue) > 0)) return null
  return (Number(presentValue) || 0) / Number(fairValue) * 100
}

/** 融资租赁摊销期次（实际利率法） */
export interface FinanceLeaseAmortPeriod {
  periodNo: number
  date: string
  rent: number
  financeIncome: number
  netDecrease: number
  netBalance: number
}

/**
 * 租赁内含利率 NPV（小数利率）。
 * NPV(r) = −净投资 + Σ租金/(1+r)^t + 未担保余值/(1+r)^n
 */
export function calcLeaseNpv(opts: {
  netInvestment: number
  annualRent: number
  periodCount: number
  rateDecimal: number
  unguaranteedResidual?: number
}): number {
  const n = Math.max(0, Math.floor(Number(opts.periodCount) || 0))
  const rent = Number(opts.annualRent) || 0
  const residual = Number(opts.unguaranteedResidual) || 0
  const r = Number(opts.rateDecimal) || 0
  let npv = -(Number(opts.netInvestment) || 0)
  if (n <= 0) return npv + residual
  for (let t = 1; t <= n; t++) {
    const df = (1 + r) ** t
    npv += rent / df
    if (t === n) npv += residual / df
  }
  return npv
}

/**
 * 牛顿法 + 二分兜底求解租赁内含利率（返回百分数，如 10.25 表示 10.25%）。
 * 净投资通常取「公允价值 + 初始直接费用」或已录入的租赁投资净额。
 * 无解/参数不足时返回 null。
 */
export function solveLeaseImplicitRatePct(opts: {
  netInvestment: number
  annualRent: number
  periodCount: number
  unguaranteedResidual?: number
}): number | null {
  const net = Number(opts.netInvestment) || 0
  const rent = Number(opts.annualRent) || 0
  const n = Math.floor(Number(opts.periodCount) || 0)
  const residual = Number(opts.unguaranteedResidual) || 0
  if (!(net > 0) || n <= 0 || (!(rent > 0) && !(residual > 0))) return null

  const totalCash = rent * n + residual
  if (totalCash <= net) return null // 无正利率解

  const f = (rate: number) => calcLeaseNpv({
    netInvestment: net,
    annualRent: rent,
    periodCount: n,
    rateDecimal: rate,
    unguaranteedResidual: residual,
  })

  // 牛顿法
  let rate = Math.min(0.5, Math.max(0.001, (totalCash / net - 1) / n))
  for (let i = 0; i < 40; i++) {
    const y = f(rate)
    if (Math.abs(y) < 0.01) {
      return Math.round(rate * 10000) / 100 // 百分数，保留 2 位小数对应 4 位利率精度的百分数×100→2位
    }
    const y2 = f(rate + 1e-6)
    const dy = (y2 - y) / 1e-6
    if (Math.abs(dy) < 1e-12) break
    const next = rate - y / dy
    if (next <= -0.99 || next > 5 || Number.isNaN(next)) break
    rate = next
  }
  if (Math.abs(f(rate)) < 1) {
    return Math.round(rate * 10000) / 100
  }

  // 二分兜底：利率 0% ~ 200%
  let lo = 0
  let hi = 2
  if (f(lo) * f(hi) > 0) return null
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2
    const fm = f(mid)
    if (Math.abs(fm) < 0.01) {
      return Math.round(mid * 10000) / 100
    }
    if (f(lo) * fm <= 0) hi = mid
    else lo = mid
  }
  return Math.round(((lo + hi) / 2) * 10000) / 100
}

/**
 * 按实际利率法编制未确认融资收益分配表。
 * ③融资收入 = 期初净投资 × 内含利率；④净额减少 = 租金 − 融资收入；⑤期末 = 期初 − ④
 * 若有未担保余值，并入最后一期现金流入（不改变合同租金列示时可看 tip）。
 */
export function buildFinanceLeaseAmortization(opts: {
  openingNetInvestment: number
  annualRent: number
  implicitRatePct: number
  periodCount: number
  startYear?: number
  unguaranteedResidual?: number
}): FinanceLeaseAmortPeriod[] {
  const rate = (Number(opts.implicitRatePct) || 0) / 100
  const rent = Number(opts.annualRent) || 0
  const residual = Number(opts.unguaranteedResidual) || 0
  const n = Math.max(0, Math.min(40, Math.floor(Number(opts.periodCount) || 0)))
  const startYear = opts.startYear ?? new Date().getFullYear()
  let balance = Number(opts.openingNetInvestment) || 0
  const rows: FinanceLeaseAmortPeriod[] = []
  for (let i = 0; i < n; i++) {
    const financeIncome = Math.round(balance * rate * 100) / 100
    const cashIn = i === n - 1 ? rent + residual : rent
    const netDecrease = Math.round((cashIn - financeIncome) * 100) / 100
    const netBalance = Math.round((balance - netDecrease) * 100) / 100
    rows.push({
      periodNo: i + 1,
      date: `${startYear + i}-12-31`,
      rent: cashIn,
      financeIncome,
      netDecrease,
      netBalance,
    })
    balance = netBalance
  }
  return rows
}
