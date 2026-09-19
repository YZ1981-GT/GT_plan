/**
 * H1 固定资产 — 折旧计算引擎（纯函数，无副作用）
 * 支持4种折旧方法 + 含减值折旧 + DCF现值 + 终值 + 单调性校验
 * Spec: .kiro/specs/h1-fixed-assets/
 * Requirements: 11.5, 13.4
 */

/**
 * 直线法月折旧 = 原值 × (1 - 残值率) / 使用年限 / 12
 * @param cost 资产原值
 * @param salvageRate 残值率 (0~1)
 * @param usefulLifeYears 使用年限（年）
 * @returns 月折旧额；usefulLifeYears <= 0 时返回 0
 */
export function calcStraightLine(cost: number, salvageRate: number, usefulLifeYears: number): number {
  if (usefulLifeYears <= 0) return 0
  return cost * (1 - salvageRate) / usefulLifeYears / 12
}

/**
 * 双倍余额递减法月折旧
 * - 前期：netValue × 2 / usefulLifeYears / 12
 * - 最后两年(24个月)：转为直线法，(netValue - salvage) / 剩余月数
 *   此处简化为 netValue × 2 / usefulLifeYears / 12 在前期适用，
 *   最后24个月时切换为 (netValue) / 剩余月数（残值已在netValue中扣除由调用方处理）
 *
 * 注意：按中国CAS惯例，最后两年改用直线法，年折旧 = (净值 - 残值) / 2，
 * 但此函数接收的netValue已经是扣除残值前的账面净值，最后24个月按
 * netValue / 剩余月数(=totalMonths - elapsedMonths) 计算
 *
 * @param netValue 当前账面净值（原值 - 已计提累计折旧）
 * @param usefulLifeYears 使用年限（年）
 * @param elapsedMonths 已使用月数
 * @param totalMonths 总使用月数 (= usefulLifeYears × 12)
 * @returns 当月折旧额；usefulLifeYears <= 0 或 totalMonths <= 0 时返回 0
 */
export function calcDoubleDeclining(
  netValue: number,
  usefulLifeYears: number,
  elapsedMonths: number,
  totalMonths: number
): number {
  if (usefulLifeYears <= 0 || totalMonths <= 0) return 0
  // 最后24个月转直线法
  if (elapsedMonths >= totalMonths - 24) {
    const remainingMonths = totalMonths - elapsedMonths
    if (remainingMonths <= 0) return 0
    return netValue / remainingMonths
  }
  // 前期：双倍余额递减
  return netValue * 2 / usefulLifeYears / 12
}

/**
 * 年数总和法月折旧 = 原值 × (1 - 残值率) × 剩余年限 / 年数总和 / 12
 * 年数总和 = usefulLifeYears × (usefulLifeYears + 1) / 2
 * @param cost 资产原值
 * @param salvageRate 残值率 (0~1)
 * @param usefulLifeYears 使用年限（年）
 * @param remainingYears 剩余使用年限
 * @returns 月折旧额；usefulLifeYears <= 0 时返回 0
 */
export function calcSumOfYears(
  cost: number,
  salvageRate: number,
  usefulLifeYears: number,
  remainingYears: number
): number {
  if (usefulLifeYears <= 0) return 0
  const sumOfYears = usefulLifeYears * (usefulLifeYears + 1) / 2
  return cost * (1 - salvageRate) * remainingYears / sumOfYears / 12
}

/**
 * 工作量法月折旧 = 原值 × (1 - 残值率) / 总工作量 × 当月工作量
 * @param cost 资产原值
 * @param salvageRate 残值率 (0~1)
 * @param totalUnits 预计总工作量
 * @param currentUnits 当月实际工作量
 * @returns 当月折旧额；totalUnits <= 0 时返回 0
 */
export function calcUnitsOfProduction(
  cost: number,
  salvageRate: number,
  totalUnits: number,
  currentUnits: number
): number {
  if (totalUnits <= 0) return 0
  return cost * (1 - salvageRate) / totalUnits * currentUnits
}

/**
 * 含减值折旧（直线法接力，对齐 H1-12 含减值底稿）：
 * 减值时点账面净值 = 原值 − 减值前累计折旧 − 减值准备
 * 剩余可折旧额 = max(净值 − 残值, 0)，残值按原值×残值率
 * 新月折旧 = 剩余可折旧额 / 剩余月数
 *
 * 兼容旧调用：若不传 accDepAtImpairment，则按减值前直线法推算累计折旧。
 */
export function calcDepreciationWithImpairment(
  cost: number,
  salvageRate: number,
  usefulLifeYears: number,
  impairment: number,
  elapsedMonths: number,
  accDepAtImpairment?: number,
): number {
  const totalMonths = usefulLifeYears * 12
  const remainingMonths = totalMonths - elapsedMonths
  if (remainingMonths <= 0 || usefulLifeYears <= 0) return 0
  const salvage = cost * salvageRate
  const preMonthly = calcStraightLine(cost, salvageRate, usefulLifeYears)
  const accDep = accDepAtImpairment != null
    ? Math.max(accDepAtImpairment, 0)
    : preMonthly * Math.max(elapsedMonths, 0)
  const carrying = cost - accDep - Math.max(impairment, 0)
  const remainingDepreciable = Math.max(carrying - salvage, 0)
  return remainingDepreciable / remainingMonths
}

// ─── H1-12 底稿对齐：日期/期数/三段测算 ───────────────────────────────────────

/** 解析 YYYY-MM-DD / Date / Excel序列号 → Date；无效返回 null */
export function parseDepDate(value: string | Date | number | null | undefined): Date | null {
  if (value == null || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value === 'number' && Number.isFinite(value)) {
    // Excel 序列日（以 1899-12-30 为原点，兼容 Windows）
    const d = new Date(Date.UTC(1899, 11, 30) + value * 86400000)
    return Number.isNaN(d.getTime()) ? null : d
  }
  const s = String(value).trim().replace(/\./g, '-').replace(/\//g, '-')
  const m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/)
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Number.isNaN(d.getTime()) ? null : d
}

/**
 * 日历月份差（年*12+月），不含日。
 * 例：2020-01 → 2020-12 = 11
 */
export function calendarMonthDiff(from: Date, to: Date): number {
  return (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth())
}

/**
 * CAS/税法惯例：投入使用次月起提，停止使用次月起停提。
 * 已提折旧月份 = 自「开始使用次月」至 asOf 月末的月数，下限0，上限 usefulLifeMonths。
 */
export function calcMonthsDepreciated(
  startDate: string | Date | null | undefined,
  asOfDate: string | Date | null | undefined,
  usefulLifeMonths: number,
): number {
  const start = parseDepDate(startDate)
  const asOf = parseDepDate(asOfDate)
  if (!start || !asOf || usefulLifeMonths <= 0) return 0
  // 起提月 = 开始使用月的下一月
  const firstDepMonth = new Date(start.getFullYear(), start.getMonth() + 1, 1)
  const asOfMonth = new Date(asOf.getFullYear(), asOf.getMonth(), 1)
  if (asOfMonth < firstDepMonth) return 0
  const months = calendarMonthDiff(firstDepMonth, asOfMonth) + 1
  return Math.min(Math.max(months, 0), usefulLifeMonths)
}

/** 测算到期日（满折日）= 开始使用次月 + 使用月限 − 1 天所在月末 */
export function calcFullDepreciationDate(
  startDate: string | Date | null | undefined,
  usefulLifeMonths: number,
): string {
  const start = parseDepDate(startDate)
  if (!start || usefulLifeMonths <= 0) return ''
  const lastMonth = new Date(start.getFullYear(), start.getMonth() + usefulLifeMonths, 1)
  // 月末日
  const end = new Date(lastMonth.getFullYear(), lastMonth.getMonth() + 1, 0)
  const y = end.getFullYear()
  const m = String(end.getMonth() + 1).padStart(2, '0')
  const d = String(end.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * 本期应提折旧月份（不含减值拆分）：
 * = min(期末已提月, 使用月限) − min(期初已提月, 使用月限)，再扣减处置后停提。
 */
export function calcPeriodDepMonths(params: {
  startDate?: string | Date | null
  periodBegin?: string | Date | null
  periodEnd?: string | Date | null
  disposalDate?: string | Date | null
  usefulLifeMonths: number
}): number {
  const { startDate, periodBegin, periodEnd, disposalDate, usefulLifeMonths } = params
  if (!periodEnd || usefulLifeMonths <= 0) return 0
  // 期初：上期期末 = periodBegin 的前一日
  let beginAsOf = periodBegin ? parseDepDate(periodBegin) : null
  if (beginAsOf) {
    beginAsOf = new Date(beginAsOf.getFullYear(), beginAsOf.getMonth(), beginAsOf.getDate() - 1)
  }
  const endCap = disposalDate
    ? (() => {
        const disp = parseDepDate(disposalDate)
        const pe = parseDepDate(periodEnd)
        if (disp && pe && disp < pe) return disposalDate
        return periodEnd
      })()
    : periodEnd
  const endMonths = calcMonthsDepreciated(startDate, endCap, usefulLifeMonths)
  const beginMonths = beginAsOf
    ? calcMonthsDepreciated(startDate, beginAsOf, usefulLifeMonths)
    : Math.max(endMonths - 12, 0) // 无期初日时默认按整年回推
  return Math.max(endMonths - beginMonths, 0)
}

export interface StraightLineTestResult {
  usefulLifeMonths: number
  calcMonthly: number
  fullDepDate: string
  monthsAtBegin: number
  monthsAtEnd: number
  periodMonths: number
  periodDep: number
  calcAccDep: number
  monthlyDiff: number
  accDepDiff: number
}

/** H1-12(A) 不含减值直线法整行测算 */
export function calcStraightLineTest(input: {
  cost: number
  salvageRate: number
  usefulLifeYears: number
  startDate?: string | null
  periodBegin?: string | null
  periodEnd?: string | null
  disposalDate?: string | null
  bookMonthly?: number
  bookAccDepEnd?: number
  /** 若已直接给出已提月数，优先于日期推算 */
  elapsedMonthsEnd?: number
  elapsedMonthsBegin?: number
}): StraightLineTestResult {
  const lifeMonths = Math.max(Math.round(input.usefulLifeYears * 12), 0)
  const calcMonthly = calcStraightLine(input.cost, input.salvageRate, input.usefulLifeYears)
  const fullDepDate = calcFullDepreciationDate(input.startDate, lifeMonths)

  let monthsAtEnd = input.elapsedMonthsEnd
  let monthsAtBegin = input.elapsedMonthsBegin
  if (monthsAtEnd == null) {
    monthsAtEnd = calcMonthsDepreciated(input.startDate, input.periodEnd, lifeMonths)
  }
  if (monthsAtBegin == null) {
    if (input.periodBegin) {
      const pb = parseDepDate(input.periodBegin)
      const beginAsOf = pb
        ? new Date(pb.getFullYear(), pb.getMonth(), pb.getDate() - 1)
        : null
      monthsAtBegin = calcMonthsDepreciated(input.startDate, beginAsOf, lifeMonths)
    } else {
      monthsAtBegin = Math.max(monthsAtEnd - 12, 0)
    }
  }
  monthsAtEnd = Math.min(Math.max(monthsAtEnd, 0), lifeMonths)
  monthsAtBegin = Math.min(Math.max(monthsAtBegin, 0), lifeMonths)

  let periodMonths = calcPeriodDepMonths({
    startDate: input.startDate,
    periodBegin: input.periodBegin,
    periodEnd: input.periodEnd,
    disposalDate: input.disposalDate,
    usefulLifeMonths: lifeMonths,
  })
  // 若调用方给了起止已提月，以差值为准（覆盖日期推算）
  if (input.elapsedMonthsEnd != null || input.elapsedMonthsBegin != null) {
    periodMonths = Math.max(monthsAtEnd - monthsAtBegin, 0)
  }

  const depreciable = input.cost * (1 - input.salvageRate)
  const periodDep = Math.min(calcMonthly * periodMonths, Math.max(depreciable - calcMonthly * monthsAtBegin, 0))
  const calcAccDep = Math.min(calcMonthly * monthsAtEnd, depreciable)
  const bookMonthly = input.bookMonthly ?? 0
  const bookAcc = input.bookAccDepEnd ?? 0

  return {
    usefulLifeMonths: lifeMonths,
    calcMonthly: round2(calcMonthly),
    fullDepDate,
    monthsAtBegin,
    monthsAtEnd,
    periodMonths,
    periodDep: round2(periodDep),
    calcAccDep: round2(calcAccDep),
    monthlyDiff: round2(bookMonthly - calcMonthly),
    accDepDiff: round2(bookAcc - calcAccDep),
  }
}

export interface ImpairmentSegment {
  /** 段起点（含）已提月数 */
  fromElapsed: number
  /** 段终点（不含）已提月数；最后一段可用 Infinity */
  toElapsed: number
  monthly: number
  impairmentCumulative: number
}

export interface ImpairmentTestResult extends StraightLineTestResult {
  preImpairmentMonthly: number
  postImpairmentMonthly: number
  monthsBeforeImpairmentInPeriod: number
  monthsAfterImpairmentInPeriod: number
  accDepAtImpairment: number
  segments: ImpairmentSegment[]
}

/**
 * H1-12(B) 含单次减值：本期 = 减值前月数×原月折旧 + 减值后月数×新月折旧
 */
export function calcWithImpairmentTest(input: {
  cost: number
  salvageRate: number
  usefulLifeYears: number
  startDate?: string | null
  periodBegin?: string | null
  periodEnd?: string | null
  disposalDate?: string | null
  impairmentAmount: number
  impairmentDate?: string | null
  bookMonthly?: number
  bookAccDepEnd?: number
  elapsedMonthsEnd?: number
  elapsedMonthsBegin?: number
  /** 减值时累计折旧（可选；缺省按原直线法推算） */
  accDepAtImpairment?: number
}): ImpairmentTestResult {
  const base = calcStraightLineTest(input)
  const lifeMonths = base.usefulLifeMonths
  const preMonthly = base.calcMonthly

  if (!(input.impairmentAmount > 0)) {
    return {
      ...base,
      preImpairmentMonthly: preMonthly,
      postImpairmentMonthly: preMonthly,
      monthsBeforeImpairmentInPeriod: base.periodMonths,
      monthsAfterImpairmentInPeriod: 0,
      accDepAtImpairment: round2(preMonthly * base.monthsAtBegin),
      segments: [{ fromElapsed: 0, toElapsed: lifeMonths, monthly: preMonthly, impairmentCumulative: 0 }],
    }
  }

  // 减值时点已提月数
  let elapsedAtImp = input.impairmentDate
    ? calcMonthsDepreciated(input.startDate, input.impairmentDate, lifeMonths)
    : base.monthsAtBegin // 无日期时默认视为期初已减值（本期全用新率）
  elapsedAtImp = Math.min(Math.max(elapsedAtImp, 0), lifeMonths)

  const accAtImp = input.accDepAtImpairment != null
    ? Math.max(input.accDepAtImpairment, 0)
    : preMonthly * elapsedAtImp

  const postMonthly = calcDepreciationWithImpairment(
    input.cost,
    input.salvageRate,
    input.usefulLifeYears,
    input.impairmentAmount,
    elapsedAtImp,
    accAtImp,
  )

  // 本期落在减值前/后的月数
  const begin = base.monthsAtBegin
  const end = base.monthsAtEnd
  const monthsBefore = Math.max(Math.min(elapsedAtImp, end) - begin, 0)
  const monthsAfter = Math.max(end - Math.max(elapsedAtImp, begin), 0)

  const periodDep = round2(preMonthly * monthsBefore + postMonthly * monthsAfter)
  // 累计：减值前段用原率，减值后段用新率
  const calcAccDep = round2(
    preMonthly * Math.min(elapsedAtImp, end)
    + postMonthly * Math.max(end - elapsedAtImp, 0),
  )

  return {
    ...base,
    periodMonths: monthsBefore + monthsAfter,
    periodDep,
    calcAccDep,
    monthlyDiff: round2((input.bookMonthly ?? 0) - postMonthly),
    accDepDiff: round2((input.bookAccDepEnd ?? 0) - calcAccDep),
    preImpairmentMonthly: round2(preMonthly),
    postImpairmentMonthly: round2(postMonthly),
    monthsBeforeImpairmentInPeriod: monthsBefore,
    monthsAfterImpairmentInPeriod: monthsAfter,
    accDepAtImpairment: round2(accAtImp),
    segments: [
      { fromElapsed: 0, toElapsed: elapsedAtImp, monthly: round2(preMonthly), impairmentCumulative: 0 },
      {
        fromElapsed: elapsedAtImp,
        toElapsed: lifeMonths,
        monthly: round2(postMonthly),
        impairmentCumulative: input.impairmentAmount,
      },
    ],
  }
}

export interface MultiImpairmentEventInput {
  eventDate?: string | null
  /** 该次计提金额（增量，非累计） */
  amount: number
  /** 可选：事件时点已提月数（优先于日期） */
  elapsedMonths?: number
}

/**
 * H1-12(C) 多次减值：按减值时点切段，每段以「原值−累计折旧−累计减值−残值」/剩余月数 计月折旧
 */
export function calcMultiImpairmentTest(input: {
  cost: number
  salvageRate: number
  usefulLifeYears: number
  startDate?: string | null
  periodBegin?: string | null
  periodEnd?: string | null
  disposalDate?: string | null
  events: MultiImpairmentEventInput[]
  bookMonthly?: number
  bookAccDepEnd?: number
  elapsedMonthsEnd?: number
  elapsedMonthsBegin?: number
}): ImpairmentTestResult {
  const base = calcStraightLineTest({ ...input, salvageRate: input.salvageRate })
  const lifeMonths = base.usefulLifeMonths
  const salvage = input.cost * input.salvageRate

  // 规范化事件：推算 elapsed，按 elapsed 升序
  const normalized = (input.events ?? [])
    .filter((e) => (e.amount ?? 0) > 0)
    .map((e) => {
      const elapsed = e.elapsedMonths != null
        ? e.elapsedMonths
        : calcMonthsDepreciated(input.startDate, e.eventDate, lifeMonths)
      return { amount: e.amount, elapsed: Math.min(Math.max(elapsed, 0), lifeMonths), eventDate: e.eventDate }
    })
    .sort((a, b) => a.elapsed - b.elapsed)

  if (normalized.length === 0) {
    return calcWithImpairmentTest({ ...input, impairmentAmount: 0 })
  }

  // 构造切段
  const cutPoints = [0, ...normalized.map((e) => e.elapsed), lifeMonths]
  const uniqueCuts = [...new Set(cutPoints)].sort((a, b) => a - b)

  const segments: ImpairmentSegment[] = []
  let runningAccDep = 0
  let runningImpairment = 0
  let eventIdx = 0

  for (let i = 0; i < uniqueCuts.length - 1; i++) {
    const from = uniqueCuts[i]
    const to = uniqueCuts[i + 1]
    // 进入本段前，应用恰好发生在 from 时点的减值
    while (eventIdx < normalized.length && normalized[eventIdx].elapsed === from) {
      runningImpairment += normalized[eventIdx].amount
      eventIdx++
    }
    const remainingMonths = lifeMonths - from
    const carrying = input.cost - runningAccDep - runningImpairment
    const monthly = remainingMonths > 0 ? Math.max(carrying - salvage, 0) / remainingMonths : 0
    segments.push({
      fromElapsed: from,
      toElapsed: to,
      monthly: round2(monthly),
      impairmentCumulative: runningImpairment,
    })
    runningAccDep += monthly * (to - from)
  }

  // 本期折旧：在 [monthsAtBegin, monthsAtEnd) 上按段积分
  const begin = base.monthsAtBegin
  const end = base.monthsAtEnd
  let periodDep = 0
  let monthsBefore = 0
  let monthsAfter = 0
  const firstImpElapsed = normalized[0].elapsed
  for (const seg of segments) {
    const lo = Math.max(seg.fromElapsed, begin)
    const hi = Math.min(seg.toElapsed, end)
    const m = Math.max(hi - lo, 0)
    periodDep += seg.monthly * m
    if (seg.toElapsed <= firstImpElapsed) monthsBefore += m
    else if (seg.fromElapsed >= firstImpElapsed) monthsAfter += m
    else {
      // 段跨越首次减值点
      const before = Math.max(Math.min(firstImpElapsed, hi) - lo, 0)
      monthsBefore += before
      monthsAfter += m - before
    }
  }

  // 累计至期末
  let calcAccDep = 0
  for (const seg of segments) {
    const lo = seg.fromElapsed
    const hi = Math.min(seg.toElapsed, end)
    calcAccDep += seg.monthly * Math.max(hi - lo, 0)
  }

  const lastSeg = segments[segments.length - 1]
  const totalImp = runningImpairment

  return {
    ...base,
    periodMonths: monthsBefore + monthsAfter,
    periodDep: round2(periodDep),
    calcAccDep: round2(calcAccDep),
    monthlyDiff: round2((input.bookMonthly ?? 0) - (lastSeg?.monthly ?? 0)),
    accDepDiff: round2((input.bookAccDepEnd ?? 0) - calcAccDep),
    preImpairmentMonthly: segments[0]?.monthly ?? base.calcMonthly,
    postImpairmentMonthly: lastSeg?.monthly ?? base.calcMonthly,
    monthsBeforeImpairmentInPeriod: monthsBefore,
    monthsAfterImpairmentInPeriod: monthsAfter,
    accDepAtImpairment: round2(segments[0] ? segments[0].monthly * firstImpElapsed : 0),
    segments,
  }
}

/** 按减值情况推荐 H1-12 分支：A 无减值 / B 单次 / C 多次 */
export function recommendDepreciationBranch(input: {
  impairmentBegin?: number
  impairmentEnd?: number
  impairmentProvision?: number
  impairmentEventCount?: number
}): 'A' | 'B' | 'C' {
  const eventCount = input.impairmentEventCount ?? 0
  if (eventCount >= 2) return 'C'
  const end = input.impairmentEnd ?? 0
  const begin = input.impairmentBegin ?? 0
  const provision = input.impairmentProvision ?? 0
  if (eventCount === 1 || end > 0.005 || begin > 0.005 || provision > 0.005) return 'B'
  return 'A'
}

function round2(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.round(n * 100) / 100
}

/**
 * DCF现值 = Σ(cashFlow_i / (1 + discountRate)^(i+1))
 * @param cashFlows 各期现金流数组（第0期对应第1年末）
 * @param discountRate 折现率 (如0.08表示8%)
 * @returns 现值合计；空数组返回0；discountRate <= -1 返回0（避免除零/负底数）
 */
export function calcDcfPresentValue(cashFlows: number[], discountRate: number): number {
  if (cashFlows.length === 0) return 0
  if (discountRate <= -1) return 0
  let pv = 0
  for (let i = 0; i < cashFlows.length; i++) {
    pv += cashFlows[i] / Math.pow(1 + discountRate, i + 1)
  }
  return pv
}

/**
 * 终值（永续价值） = 永续现金流 / (折现率 - 增长率)
 * Gordon Growth Model
 * @param perpetuityCF 永续年金现金流（预测期最后一年的稳态现金流）
 * @param discountRate 折现率
 * @param growthRate 永续增长率
 * @returns 终值；当 discountRate <= growthRate 时返回 0（避免无穷/负值）
 */
export function calcTerminalValue(perpetuityCF: number, discountRate: number, growthRate: number): number {
  if (discountRate <= growthRate) return 0
  return perpetuityCF / (discountRate - growthRate)
}

/**
 * 单调性校验：累计折旧序列是否严格递增（排除处置月份）
 * @param monthlyAccumulated 月末累计折旧数组
 * @param disposalMonths 处置月份索引数组（0-based，这些月份允许不递增）
 * @returns true表示满足单调递增；length < 2 时返回 true
 */
export function isMonotonicallyIncreasing(monthlyAccumulated: number[], disposalMonths: number[]): boolean {
  if (monthlyAccumulated.length < 2) return true
  const disposalSet = new Set(disposalMonths)
  for (let i = 0; i < monthlyAccumulated.length - 1; i++) {
    // 如果当前月或下一月是处置月份，跳过此对比
    if (disposalSet.has(i) || disposalSet.has(i + 1)) continue
    if (monthlyAccumulated[i] >= monthlyAccumulated[i + 1]) return false
  }
  return true
}
