/**
 * I4 长期待摊费用 — 摊销计算引擎（纯函数，无副作用）
 * 支持直线法 + 工作量法（H折旧引擎的子集，仅2种方法）
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Requirements: 6.4-6.5
 */

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

function round4(n: number): number {
  return Math.round((n + Number.EPSILON) * 10000) / 10000
}

function parseAmortDate(v: string | Date | null | undefined): Date | null {
  if (v == null || v === '') return null
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? null : v
  const s = String(v).trim()
  if (!s) return null
  const m = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/)
  if (m) {
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
    return Number.isNaN(d.getTime()) ? null : d
  }
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

function fmtDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Excel DATEDIF(from, to, "m") + 1（含首尾月） */
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
 * 使用年限 → 使用月限。支持数字、「N年」文本；>100 视为已是月数。
 * 对齐源表 I4-6：H = IF(RIGHT(F)<>"年", F*12, …)
 */
export function parseUsefulLifeToMonths(usefulLife: number | string | null | undefined): number {
  if (usefulLife == null || usefulLife === '') return 0
  if (typeof usefulLife === 'number') {
    if (!Number.isFinite(usefulLife) || usefulLife <= 0) return 0
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

/**
 * 测算到期日 = DATE(YEAR(开始), MONTH(开始)+月限, DAY(开始)-1)
 * 对齐源表 I4-6：I 列；开始日缺失时返回空串（避免 Excel 显示 1900-1-0）
 */
export function calcFullAmortDate(startDate: string | Date | null | undefined, lifeMonths: number): string {
  const start = parseAmortDate(startDate)
  if (!start || lifeMonths <= 0) return ''
  const end = new Date(start.getFullYear(), start.getMonth() + lifeMonths, start.getDate() - 1)
  return fmtDate(end)
}

/**
 * 直线法月摊销 = 原始金额 ÷ 摊销总月数
 */
export function calcStraightLineAmort(originalAmount: number, totalMonths: number): number {
  if (totalMonths <= 0) return 0
  return originalAmount / totalMonths
}

/**
 * 工作量法月摊销 = 原始金额 × (本月工作量 ÷ 总预计工作量)
 */
export function calcUnitsOfProductionAmort(originalAmount: number, currentUnits: number, totalUnits: number): number {
  if (totalUnits <= 0) return 0
  return originalAmount * (currentUnits / totalUnits)
}

/** 摊销标准 = 原值 ÷ 工作标准（I4-7） */
export function calcAmortStandard(originalAmount: number, workStandard: number): number {
  if (workStandard <= 0) return 0
  return originalAmount / workStandard
}

/** 按摊销标准测算 = 工作量 × 摊销标准（I4-7） */
export function calcUnitsAmortByStandard(units: number, amortStandard: number): number {
  return (units || 0) * (amortStandard || 0)
}

/** 摊销额差异 = 测算 − 账面（I4-7） */
export function calcAmortDiff(calculated: number, book: number): number {
  return (calculated || 0) - (book || 0)
}

export function calcRemainingMonths(totalMonths: number, elapsedMonths: number): number {
  return totalMonths - elapsedMonths
}

export function calcAmortizationRate(elapsed: number, total: number): number {
  if (total <= 0) return 0
  return elapsed / total
}

// ─── I4-6 源表对齐：直线法整行测算 ───────────────────────────────────────────

export interface StraightLineAmortTestResult {
  lifeMonths: number
  fullAmortDate: string
  /** 已摊销月份 J（至截止日或到期日孰早） */
  monthsAmortized: number
  remainingMonths: number
  /** 本期摊销月份（期间四分支，修正源表对老资产虚增） */
  periodMonths: number
  /** 测算月摊销额 M = 原值 / 月限 */
  calcMonthlyAmort: number
  /** 当期摊销 N = M × L */
  periodAmortization: number
  /** 月摊销额差异 O = 账面月摊 − 测算月摊（源表方向） */
  monthlyDiff: number
  /** 累计摊销费用(测算) P = M × J */
  calcAccumAmort: number
  /** 累计摊销额差异 Q = 账面累计 − 测算累计（源表方向） */
  accumDiff: number
}

/**
 * I4-6 直线法整行测算（对齐源 xlsx「摊销测算I4-6」C~Q）。
 *
 * 改进点：
 * 1. 开始日为空时不推算到期日（避免源表 1900-1-0）
 * 2. 本期月数用期间四分支，并夹紧至剩余月数/12，避免对期初前已投入使用项目虚增
 */
export function calcStraightLineAmortTest(input: {
  originalAmount: number
  usefulLife: number | string
  startDate?: string | null
  periodBegin?: string | null
  periodEnd?: string | null
  bookMonthlyAmort?: number
  bookAccumAmort?: number
}): StraightLineAmortTestResult {
  const empty: StraightLineAmortTestResult = {
    lifeMonths: 0,
    fullAmortDate: '',
    monthsAmortized: 0,
    remainingMonths: 0,
    periodMonths: 0,
    calcMonthlyAmort: 0,
    periodAmortization: 0,
    monthlyDiff: 0,
    calcAccumAmort: 0,
    accumDiff: 0,
  }

  const cost = Number(input.originalAmount) || 0
  const lifeMonths = parseUsefulLifeToMonths(input.usefulLife)
  if (lifeMonths <= 0) return empty

  const start = parseAmortDate(input.startDate)
  const periodBegin = parseAmortDate(input.periodBegin)
  const periodEnd = parseAmortDate(input.periodEnd)
  const fullAmortDate = calcFullAmortDate(start, lifeMonths)
  const endDate = parseAmortDate(fullAmortDate)

  let monthsAmortized = 0
  if (start && periodEnd) {
    const to = endDate && endDate < periodEnd ? endDate : periodEnd
    monthsAmortized = datedifMonthsInclusive(start, to)
    monthsAmortized = Math.max(0, Math.min(monthsAmortized, lifeMonths))
  }

  const remainingMonths = Math.max(lifeMonths - monthsAmortized, 0)
  const calcMonthlyAmort = round4(cost / lifeMonths)

  let periodMonths = 0
  if (start && endDate && periodBegin && periodEnd) {
    if (start <= periodBegin && endDate > periodEnd) {
      periodMonths = datedifMonthsInclusive(periodBegin, periodEnd)
    } else if (start <= periodBegin && endDate <= periodEnd) {
      periodMonths = datedifMonthsInclusive(periodBegin, endDate)
    } else if (start > periodBegin && endDate > periodEnd) {
      periodMonths = datedifMonthsInclusive(start, periodEnd)
    } else if (start >= periodBegin && endDate <= periodEnd) {
      periodMonths = datedifMonthsInclusive(start, endDate)
    }
  } else if (!start && periodBegin && periodEnd) {
    periodMonths = Math.min(12, lifeMonths)
  }
  periodMonths = Math.max(Math.min(periodMonths, remainingMonths || lifeMonths, 12), 0)

  const periodAmortization = round2(calcMonthlyAmort * periodMonths)
  const calcAccumAmort = round2(calcMonthlyAmort * monthsAmortized)
  const bookMonthly = Number(input.bookMonthlyAmort) || 0
  const bookAccum = Number(input.bookAccumAmort) || 0

  return {
    lifeMonths,
    fullAmortDate,
    monthsAmortized,
    remainingMonths,
    periodMonths,
    calcMonthlyAmort,
    periodAmortization,
    monthlyDiff: round2(bookMonthly - calcMonthlyAmort),
    calcAccumAmort,
    accumDiff: round2(bookAccum - calcAccumAmort),
  }
}
