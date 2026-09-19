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

// ─── I1-11 源表对齐：日期分段含减值摊销测算 ───────────────────────────────────

function round2(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.round(n * 100) / 100
}

function round4(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.round(n * 10000) / 10000
}

/** 解析 YYYY-MM-DD / Date → Date；无效返回 null */
export function parseAmortDate(value: string | Date | null | undefined): Date | null {
  if (value == null || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  const s = String(value).trim().replace(/\./g, '-').replace(/\//g, '-')
  const m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/)
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Number.isNaN(d.getTime()) ? null : d
}

function fmtDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * Excel DATEDIF(from, to, "m") + 1（含首尾月）。
 * to < from 时返回 0。
 */
export function datedifMonthsInclusive(from: Date, to: Date): number {
  if (to < from) return 0
  const months = (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth())
  return months + 1
}

/** Excel DATEDIF(from, to, "m")（不含 +1） */
export function datedifMonths(from: Date, to: Date): number {
  if (to < from) return 0
  return (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth())
}

/**
 * 测算到期日 J = DATE(YEAR(F), MONTH(F)+I, DAY(F)-1)
 * 对齐源表 I1-11 公式。
 */
export function calcFullAmortDate(startDate: string | Date | null | undefined, lifeMonths: number): string {
  const start = parseAmortDate(startDate)
  if (!start || lifeMonths <= 0) return ''
  const end = new Date(start.getFullYear(), start.getMonth() + lifeMonths, start.getDate() - 1)
  return fmtDate(end)
}

/**
 * 使用期限(年) → 摊销期限(月)。支持纯数字或「N年」文本。
 */
export function parseUsefulLifeToMonths(usefulLife: number | string | null | undefined): number {
  if (usefulLife == null || usefulLife === '') return 0
  if (typeof usefulLife === 'number') {
    if (!Number.isFinite(usefulLife) || usefulLife <= 0) return 0
    // 若已是月数（>100 更像月），直接返回；否则按年×12
    return usefulLife > 100 ? Math.round(usefulLife) : Math.round(usefulLife * 12)
  }
  const s = String(usefulLife).trim()
  if (!s) return 0
  if (s.endsWith('年')) {
    const n = Number(s.slice(0, -1))
    return Number.isFinite(n) && n > 0 ? Math.round(n * 12) : 0
  }
  const n = Number(s)
  if (!Number.isFinite(n) || n <= 0) return 0
  return n > 100 ? Math.round(n) : Math.round(n * 12)
}

// ─── I1-10 源表对齐：剩余年限法（不含减值）────────────────────────────────────

export interface RemainingLifeAmortTestResult {
  /** 期初净值 F = 原值 − 累计摊销 − 减值（本表减值通常为 0）− 残值 */
  beginNbv: number
  lifeMonths: number
  fullAmortDate: string
  /** 至期初日已摊销月份 */
  monthsElapsedAtBegin: number
  /** 剩余摊销月份 J（期初日口径） */
  remainingMonths: number
  /** 本期摊销月份（改进：按期间起止四分支，非源表 L=DATEDIF(开始,截止)+1） */
  periodMonths: number
  /** 测算每月摊销额 K = F/J */
  monthlyAmort: number
  /** 测算本期摊销额 M = K×本期月数 */
  periodAmortization: number
  /** 本期摊销额差异 O = 测算 − 账面 */
  periodDiff: number
  /** 累计摊销(测算) = 期初累计 + 本期测算 */
  calcAccAmort: number
  /** 累计摊销差异 = 账面期末累计 − 测算累计 */
  accAmortDiff: number
}

/**
 * I1-10 不含减值剩余年限法整行测算（对齐源 xlsx「摊销测算表（不含减值）I1-10」F~O）。
 *
 * 源表核心：
 * - F = C−D−E（期初净值）
 * - I = 使用期限(年)×12
 * - J = I − ((YEAR(期初)−YEAR(开始))×12 + MONTH(期初)−MONTH(开始))
 * - K = F/J
 * - L_源 = DATEDIF(开始, 截止, "M")+1  ← 对期初前已投入使用的资产会虚增「本期月数」
 * - M = K×L；O = M−N
 *
 * 改进点相对源表：
 * 1. 「本期月数」改为与 I1-11 一致的期间四分支（受开始日/到期日/期初日/截止日约束）
 * 2. 本期月数不超过剩余摊销月份
 * 3. 支持残值（默认 0，与无形资产实务及源表无残值列一致）
 * 4. 剩余月数/已用月数做 [0, life] 夹紧，避免开始日晚于期初日时 J>寿命
 */
export function calcRemainingLifeAmortTest(input: {
  cost: number
  salvage?: number
  accAmortBegin?: number
  /** 期初减值；不含减值表通常为 0，仍保留以对齐源列 E */
  impairmentBegin?: number
  usefulLifeYears: number | string
  startDate?: string | null
  periodBegin?: string | null
  periodEnd?: string | null
  bookPeriodAmort?: number
  bookAccAmortEnd?: number
}): RemainingLifeAmortTestResult {
  const empty: RemainingLifeAmortTestResult = {
    beginNbv: 0,
    lifeMonths: 0,
    fullAmortDate: '',
    monthsElapsedAtBegin: 0,
    remainingMonths: 0,
    periodMonths: 0,
    monthlyAmort: 0,
    periodAmortization: 0,
    periodDiff: 0,
    calcAccAmort: 0,
    accAmortDiff: 0,
  }

  const cost = Number(input.cost) || 0
  const salvage = Math.max(Number(input.salvage) || 0, 0)
  const accBegin = Math.max(Number(input.accAmortBegin) || 0, 0)
  const impairBegin = Math.max(Number(input.impairmentBegin) || 0, 0)
  const lifeMonths = parseUsefulLifeToMonths(input.usefulLifeYears)
  const beginNbv = round2(cost - salvage - accBegin - impairBegin)
  const bookPeriod = Number(input.bookPeriodAmort) || 0
  const bookAccEnd = input.bookAccAmortEnd != null
    ? Number(input.bookAccAmortEnd) || 0
    : accBegin

  if (cost <= 0 || lifeMonths <= 0) {
    return {
      ...empty,
      beginNbv,
      lifeMonths,
      calcAccAmort: round2(accBegin),
      accAmortDiff: round2(bookAccEnd - accBegin),
      periodDiff: round2(0 - bookPeriod),
    }
  }

  const start = parseAmortDate(input.startDate)
  const periodBegin = parseAmortDate(input.periodBegin)
  const periodEnd = parseAmortDate(input.periodEnd)
  const fullAmortDate = calcFullAmortDate(start, lifeMonths)
  const endDate = parseAmortDate(fullAmortDate)

  // ── 剩余月数 J（源表：相对期初日）──────────────────────────────────────────
  let monthsElapsedAtBegin = 0
  if (start && periodBegin) {
    monthsElapsedAtBegin = Math.max(
      0,
      (periodBegin.getFullYear() - start.getFullYear()) * 12
        + (periodBegin.getMonth() - start.getMonth()),
    )
  } else if (start && periodEnd) {
    // 无期初日时退化为相对截止日已摊月数（再反推剩余）
    monthsElapsedAtBegin = Math.max(0, datedifMonthsInclusive(start, periodEnd) - 1)
  }
  monthsElapsedAtBegin = Math.min(monthsElapsedAtBegin, lifeMonths)
  const remainingMonths = Math.max(lifeMonths - monthsElapsedAtBegin, 0)

  // ── 本期月数（改进：四分支，取代源表 L=DATEDIF(G,截止)+1）──────────────────
  let periodMonths = 0
  if (start && periodBegin && periodEnd && endDate) {
    if (start < periodBegin && endDate > periodEnd) {
      periodMonths = datedifMonthsInclusive(periodBegin, periodEnd)
    } else if (start < periodBegin && endDate <= periodEnd) {
      periodMonths = datedifMonthsInclusive(periodBegin, endDate)
    } else if (start >= periodBegin && endDate > periodEnd) {
      periodMonths = datedifMonthsInclusive(start, periodEnd)
    } else if (start >= periodBegin && endDate <= periodEnd) {
      periodMonths = datedifMonthsInclusive(start, endDate)
    }
  } else if (!start && remainingMonths > 0) {
    // 无开始日期：默认按完整会计年度 12 个月（与手工录入剩余月数场景兼容）
    periodMonths = 12
  }
  periodMonths = Math.max(Math.min(periodMonths, remainingMonths, lifeMonths), 0)

  const monthlyAmort = remainingMonths > 0 && beginNbv !== 0
    ? round4(beginNbv / remainingMonths)
    : 0
  const periodAmortization = round2(monthlyAmort * periodMonths)
  const calcAccAmort = round2(accBegin + periodAmortization)

  return {
    beginNbv,
    lifeMonths,
    fullAmortDate,
    monthsElapsedAtBegin,
    remainingMonths,
    periodMonths,
    monthlyAmort,
    periodAmortization,
    periodDiff: round2(periodAmortization - bookPeriod),
    calcAccAmort,
    accAmortDiff: round2(bookAccEnd - calcAccAmort),
  }
}

export interface AmortWithImpairmentTestResult {
  lifeMonths: number
  fullAmortDate: string
  /** 已摊销月份 K（截至审计截止日） */
  monthsAmortized: number
  /** 剩余摊销月份 L */
  remainingMonths: number
  /** 截止减值日累计摊销月份 M */
  monthsToImpairment: number
  /** 本期摊销月份 N */
  periodMonths: number
  /** 本期减值前月数 O */
  monthsBeforeImpairment: number
  /** 本期减值后月数 P */
  monthsAfterImpairment: number
  /** 减值前月摊销额 Q */
  preMonthly: number
  /** 减值时测算累计摊销 R */
  accAmortAtImpairment: number
  /** 减值后月摊销额 S */
  postMonthly: number
  /** 当期摊销费用 T */
  periodAmortization: number
  /** 月摊销额差异 U = 账面月摊销 − 减值后月摊销 */
  monthlyDiff: number
  /** 累计摊销(测算) V */
  calcAccAmort: number
  /** 累计摊销差异 W = 账面累计 − 测算累计 */
  accAmortDiff: number
}

/**
 * I1-11 含减值摊销整行测算（对齐源 xlsx 公式 Q~W + 月数 I~P）。
 *
 * 核心逻辑：
 * - 减值前月摊销 Q = 原值 / 摊销期限月（残值率按源表取 0；若传入 salvage 则扣减）
 * - 减值时累计 R = Q × M
 * - 减值后月摊销 S = max(原值−残值−R−减值, 0) / (I−M)
 * - 本期费用 T = Q×O + S×P
 *
 * 改进点相对源表：
 * 1. 支持行级减值日期（源表仅有全局 $F$8）
 * 2. 「本期折旧月份」统一为「本期摊销月份」
 * 3. 残值可配置（默认 0，与源表一致）
 */
export function calcAmortWithImpairmentTest(input: {
  cost: number
  /** 残值金额（默认 0，对齐源表残值率=0） */
  salvage?: number
  /** 使用年限（年）或寿命月数（>100 视为月） */
  usefulLifeYears: number | string
  startDate?: string | null
  periodBegin?: string | null
  periodEnd?: string | null
  impairmentDate?: string | null
  impairmentAmount?: number
  bookMonthly?: number
  bookAccAmortEnd?: number
}): AmortWithImpairmentTestResult {
  const empty: AmortWithImpairmentTestResult = {
    lifeMonths: 0,
    fullAmortDate: '',
    monthsAmortized: 0,
    remainingMonths: 0,
    monthsToImpairment: 0,
    periodMonths: 0,
    monthsBeforeImpairment: 0,
    monthsAfterImpairment: 0,
    preMonthly: 0,
    accAmortAtImpairment: 0,
    postMonthly: 0,
    periodAmortization: 0,
    monthlyDiff: 0,
    calcAccAmort: 0,
    accAmortDiff: 0,
  }

  const cost = Number(input.cost) || 0
  const salvage = Math.max(Number(input.salvage) || 0, 0)
  const impair = Math.max(Number(input.impairmentAmount) || 0, 0)
  const lifeMonths = parseUsefulLifeToMonths(input.usefulLifeYears)
  if (cost <= 0 || lifeMonths <= 0) return { ...empty, lifeMonths }

  const start = parseAmortDate(input.startDate)
  const periodBegin = parseAmortDate(input.periodBegin)
  const periodEnd = parseAmortDate(input.periodEnd)
  const impairDate = parseAmortDate(input.impairmentDate)
  const fullAmortDate = calcFullAmortDate(start, lifeMonths)
  const endDate = parseAmortDate(fullAmortDate)

  // 无开始日期时无法按源表推月数，退化为「全期按减值后率」
  if (!start || !periodEnd || !endDate) {
    const depreciable = Math.max(cost - salvage - impair, 0)
    const postMonthly = round4(depreciable / lifeMonths)
    const periodMonths = 12
    return {
      lifeMonths,
      fullAmortDate,
      monthsAmortized: 0,
      remainingMonths: lifeMonths,
      monthsToImpairment: 0,
      periodMonths,
      monthsBeforeImpairment: 0,
      monthsAfterImpairment: periodMonths,
      preMonthly: round4((cost - salvage) / lifeMonths),
      accAmortAtImpairment: 0,
      postMonthly,
      periodAmortization: round2(postMonthly * periodMonths),
      monthlyDiff: round2((input.bookMonthly ?? 0) - postMonthly),
      calcAccAmort: round2(postMonthly * periodMonths),
      accAmortDiff: round2((input.bookAccAmortEnd ?? 0) - postMonthly * periodMonths),
    }
  }

  // K: 已摊销月份（至 min(截止日, 到期日)）
  const asOfEnd = endDate < periodEnd ? endDate : periodEnd
  const monthsAmortized = Math.min(datedifMonthsInclusive(start, asOfEnd), lifeMonths)
  const remainingMonths = Math.max(lifeMonths - monthsAmortized, 0)

  // N: 本期摊销月份（对齐源表 N 四分支）
  let periodMonths = 0
  if (periodBegin) {
    if (start < periodBegin && endDate > periodEnd) {
      periodMonths = datedifMonthsInclusive(periodBegin, periodEnd)
    } else if (start < periodBegin && endDate <= periodEnd) {
      periodMonths = datedifMonthsInclusive(periodBegin, endDate)
    } else if (start >= periodBegin && endDate > periodEnd) {
      periodMonths = datedifMonthsInclusive(start, periodEnd)
    } else if (start >= periodBegin && endDate <= periodEnd) {
      periodMonths = datedifMonthsInclusive(start, endDate)
    }
  } else {
    periodMonths = Math.min(12, monthsAmortized)
  }
  periodMonths = Math.max(Math.min(periodMonths, lifeMonths), 0)

  // M / P / O — 无减值日期或减值金额为 0：本期全落减值前
  let monthsToImpairment = 0
  let monthsAfter = 0
  if (impairDate && impair > 0) {
    monthsToImpairment = Math.min(datedifMonthsInclusive(start, impairDate), lifeMonths)
    if (periodBegin && impairDate < periodBegin) {
      // 减值日早于本期初 → 本期全为减值后
      monthsAfter = periodMonths
    } else {
      const afterFrom = start > impairDate ? start : impairDate
      const afterTo = endDate < periodEnd ? endDate : periodEnd
      monthsAfter = Math.max(Math.min(datedifMonths(afterFrom, afterTo), periodMonths), 0)
    }
  }
  const monthsBefore = Math.max(periodMonths - monthsAfter, 0)

  // Q / R / S（源表残值率硬编码 0；此处允许 salvage）
  const preMonthly = round4((cost - salvage) / lifeMonths)
  const accAtImp = round2(preMonthly * monthsToImpairment)
  const remAfterImp = lifeMonths - monthsToImpairment
  const postBase = cost - salvage - accAtImp - impair
  const postMonthly = remAfterImp > 0 && postBase > 0 ? round4(postBase / remAfterImp) : 0

  const periodAmortization = round2(preMonthly * monthsBefore + postMonthly * monthsAfter)
  // V = Q*M + S*(K-M)
  const calcAccAmort = round2(preMonthly * monthsToImpairment + postMonthly * Math.max(monthsAmortized - monthsToImpairment, 0))
  const bookMonthly = input.bookMonthly ?? 0
  const bookAcc = input.bookAccAmortEnd ?? 0

  return {
    lifeMonths,
    fullAmortDate,
    monthsAmortized,
    remainingMonths,
    monthsToImpairment,
    periodMonths,
    monthsBeforeImpairment: monthsBefore,
    monthsAfterImpairment: monthsAfter,
    preMonthly,
    accAmortAtImpairment: accAtImp,
    postMonthly,
    periodAmortization,
    monthlyDiff: round2(bookMonthly - postMonthly),
    calcAccAmort,
    accAmortDiff: round2(bookAcc - calcAccAmort),
  }
}
