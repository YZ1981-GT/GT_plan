/**
 * G6 其他债权投资(SPPI组) — 公式引擎
 *
 * 科目1503 其他债权投资（借方/资产类）
 * 计量属性：以公允价值计量且变动计入其他综合收益（FVOCI-Debt）
 *
 * 6个纯函数 + parseNum，无副作用、无Vue响应式依赖，支持 fast-check PBT 验证。
 * 所有金额结果保留2位小数（Math.round(x * 100) / 100）。
 *
 * **SPPI组核心验证场景**：
 * - G6-5 公允价值测试：Level1/2/3公允价值差异计算
 * - G6-6 利息测算：实际利率法（CAS22）利息收入 = 摊余成本 × 实际利率 × days/365
 * - G6-7 业务模式分析：持有收取/兼有/其他三类判定
 * - G6-8 合同现金流量(SPPI)测试：仅本金+利息的现金流量验证
 * - G6-9 有价证券盘点：证券存在性确认
 * - G6-10 盘点倒轧：盘点日→基准日数量推导 + 差异分析
 *
 * 核心公式：
 * - P1: 实际利息收入 = 摊余成本 × 实际利率 × days/365（2dp）
 * - P2: 现金流入 = 面值 × 票面利率 × days/365（2dp）
 * - P3: 期末摊余成本 = 期初 + 实际利息 - 现金流入（2dp）
 * - P4: 盘点倒轧 = 盘点日数量 − 净增加（整数；净增加=资产负债表日→盘点日）
 * - P5: 公允价值差异 = 审定 - 未审（2dp）
 * - P6: 盘点差异 = 基准日数量 - 账面数量（整数）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Requirements 3.2~3.4, 6.3, 7.1
 */

// ══════════════════════════════════════════════════════════
// parseNum — 输入清洗（null/undefined/NaN/空串 → 0）
// ══════════════════════════════════════════════════════════

/**
 * 安全数值转换：将任意输入转为有效数字
 * - null / undefined / '' / NaN / 非有限数 → 0
 * - 有效数字 → 原值
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ══════════════════════════════════════════════════════════
// P1: 实际利息收入 = 摊余成本 × 实际利率 × days / yearDays（2dp）
// 实际利率法(CAS22): 利息收入按摊余成本×实际利率×计息天数/年天数确认
// ══════════════════════════════════════════════════════════

/** 计息年天数基准：ACT/365（默认）、ACT/360、30/360（欧洲 30E/360） */
export type G6DayCountBasis = 'ACT/365' | 'ACT/360' | '30/360'

export function normalizeDayCountBasis(raw: unknown): G6DayCountBasis {
  const s = String(raw || '').trim().toUpperCase().replace(/\s+/g, '')
  if (s === 'ACT/360' || s === 'ACT360' || s === 'A/360') return 'ACT/360'
  if (
    s === '30/360'
    || s === '30360'
    || s === '30E/360'
    || s === '30E360'
    || s === 'EUROPEAN30/360'
  ) {
    return '30/360'
  }
  // 裸 "360" 历史兼容视为 ACT/360
  if (s === '360') return 'ACT/360'
  return 'ACT/365'
}

export function dayCountDenominator(basis: unknown): number {
  return normalizeDayCountBasis(basis) === 'ACT/365' ? 365 : 360
}

/**
 * 计算实际利息收入（实际利率法）
 * @param amortizedCost 期初摊余成本
 * @param effectiveRate 实际利率（如0.05表示5%）
 * @param days 计息天数（1~366）
 * @param dayCountBasis 年天数基准，默认 ACT/365
 * @returns 实际利息收入，保留2位小数
 */
export function calcEffectiveInterest(
  amortizedCost: number,
  effectiveRate: number,
  days: number,
  dayCountBasis: G6DayCountBasis | string = 'ACT/365',
): number {
  const den = dayCountDenominator(dayCountBasis)
  return Math.round(parseNum(amortizedCost) * parseNum(effectiveRate) * parseNum(days) / den * 100) / 100
}

// ══════════════════════════════════════════════════════════
// P2: 现金流入 = 面值 × 票面利率 × days / yearDays（2dp）
// SPPI合同现金流：仅含本金和利息的现金流量
// ══════════════════════════════════════════════════════════

/**
 * 计算票息现金流入（面值×票面利率×计息天数/年天数）
 * @param faceValue 计息面值（可为收回本金后的剩余面值）
 * @param couponRate 票面利率（如0.04表示4%）
 * @param days 计息天数（1~366）
 * @param dayCountBasis 年天数基准，默认 ACT/365
 * @returns 现金流入金额，保留2位小数
 */
export function calcCashInflow(
  faceValue: number,
  couponRate: number,
  days: number,
  dayCountBasis: G6DayCountBasis | string = 'ACT/365',
): number {
  const den = dayCountDenominator(dayCountBasis)
  return Math.round(parseNum(faceValue) * parseNum(couponRate) * parseNum(days) / den * 100) / 100
}

/**
 * 剩余面值 = 合同面值 − 此前各期已收回本金合计（不小于 0）。
 * 当期收回本金通常视为期末发生，票息按期初剩余面值计算。
 */
export function calcRemainingFace(
  faceValue: number,
  priorPrincipalRecovered: number,
): number {
  return Math.max(
    0,
    Math.round((parseNum(faceValue) - parseNum(priorPrincipalRecovered)) * 100) / 100,
  )
}

// ══════════════════════════════════════════════════════════
// P3: 期末摊余成本 = 期初 + 实际利息 - 现金流入（2dp）
// 实际利率法核心公式：摊余成本在每个付息日调整
// ══════════════════════════════════════════════════════════

/**
 * 计算期末摊余成本
 * @param opening 期初摊余成本
 * @param interest 实际利息收入
 * @param cashInflow 现金流入（票息）
 * @param principalRecovered 已收回本金（可选，默认 0）
 * @returns 期末摊余成本，保留2位小数
 */
export function calcEndingAmortized(
  opening: number,
  interest: number,
  cashInflow: number,
  principalRecovered = 0,
): number {
  return Math.round(
    (parseNum(opening) + parseNum(interest) - parseNum(cashInflow) - parseNum(principalRecovered)) * 100,
  ) / 100
}

/** 初始入账价值 = 购买对价 + 交易费用 */
export function calcInitialCarryingAmount(purchasePrice: number, transactionCost: number): number {
  return Math.round((parseNum(purchasePrice) + parseNum(transactionCost)) * 100) / 100
}

/**
 * 计息基数：Stage1/2 用账面摊余（总额）；Stage3（已发生信用减值）用净额 = 摊余 − 减值准备。
 */
export function calcInterestBasis(
  openingAmortized: number,
  openingImpairment: number,
  stage: string,
): number {
  const gross = parseNum(openingAmortized)
  if (String(stage) === 'Stage3') {
    return Math.round((gross - parseNum(openingImpairment)) * 100) / 100
  }
  return gross
}

/**
 * 由起止日期推算计息天数。
 * - ACT/365、ACT/360：日历实际天数（不含起点、含终点）
 * - 30/360：欧洲 30E/360（日均按 ≤30）
 * 无效/逆序/超限 → null
 */
export function calcInterestDays(
  startDate: string,
  endDate: string,
  dayCountBasis: G6DayCountBasis | string = 'ACT/365',
): number | null {
  const start = String(startDate || '').trim()
  const end = String(endDate || '').trim()
  if (!start || !end) return null
  const a = new Date(`${start}T00:00:00`)
  const b = new Date(`${end}T00:00:00`)
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime()) || b <= a) return null

  const basis = normalizeDayCountBasis(dayCountBasis)
  if (basis === '30/360') {
    return calcInterestDays30E360(a, b)
  }

  const days = Math.round((b.getTime() - a.getTime()) / 86400000)
  if (days < 1 || days > 366) return null
  return days
}

/** 30E/360（欧洲）：D1=min(D1,30)，D2=min(D2,30) */
export function calcInterestDays30E360(start: Date, end: Date): number | null {
  const y1 = start.getFullYear()
  const m1 = start.getMonth() + 1
  let d1 = start.getDate()
  const y2 = end.getFullYear()
  const m2 = end.getMonth() + 1
  let d2 = end.getDate()
  if (d1 > 30) d1 = 30
  if (d2 > 30) d2 = 30
  const days = 360 * (y2 - y1) + 30 * (m2 - m1) + (d2 - d1)
  if (days <= 0 || days > 360 * 2) return null
  return days
}

// ══════════════════════════════════════════════════════════
// P4: 盘点倒轧 = 盘点日数量 − 增加 + 减少
// 增减口径：「资产负债表日 → 盘点日」（与致同模板 / G4 一致）
// ══════════════════════════════════════════════════════════

/**
 * 计算基准日（报表日）数量
 *
 * 标准口径：报表日 = 盘点日 − 增加 + 减少
 * （增加/减少均为资产负债表日→盘点日期间发生额）
 *
 * 两参数兼容：`calcInventoryRollForward(count, netIncrease)`
 * 视为「盘点日 − 净增加」，其中净增加 = 增加 − 减少。
 *
 * @param countDateQty 盘点日数量
 * @param increaseOrNetChange 增加数量，或（两参数时）净增加
 * @param decrease 减少数量（可选）
 * @returns 基准日（报表日）数量
 */
export function calcInventoryRollForward(
  countDateQty: number,
  increaseOrNetChange: number,
  decrease?: number,
): number {
  if (decrease === undefined) {
    return parseNum(countDateQty) - parseNum(increaseOrNetChange)
  }
  return parseNum(countDateQty) - parseNum(increaseOrNetChange) + parseNum(decrease)
}

/**
 * 将增减明细交易类型转为期间持仓变动符号：
 * 买入/转入 = +qty；卖出/到期/转让(转出) = −qty
 */
export function signedRollForwardChangeQty(
  transactionType: string,
  quantity: number,
): number {
  const qty = parseNum(quantity)
  switch (transactionType) {
    case 'buy':
    case '买入':
    case 'transfer_in':
    case '转入':
      return qty
    case 'sell':
    case '卖出':
    case 'mature':
    case '到期':
    case 'transfer':
    case '转让':
    case 'transfer_out':
    case '转出':
      return -qty
    default:
      return 0
  }
}

/** 倒轧方向：期后盘点=倒推；期前盘点=顺推；同日=无需倒轧 */
export type RollForwardDirection = 'backward' | 'forward' | 'sameDay' | 'unknown'

/**
 * 由盘点日与资产负债表日判定倒轧方向。
 * - count > BS → backward：报表日 = 盘点日 − 期间净增加
 * - count < BS → forward：报表日 = 盘点日 + 期间净增加
 * - 同日 → sameDay：报表日 = 盘点日
 */
export function resolveRollForwardDirection(
  countDate: string,
  balanceSheetDate: string,
): RollForwardDirection {
  const c = String(countDate || '').trim()
  const b = String(balanceSheetDate || '').trim()
  if (!c || !b) return 'unknown'
  const cd = new Date(`${c}T00:00:00`)
  const bd = new Date(`${b}T00:00:00`)
  if (Number.isNaN(cd.getTime()) || Number.isNaN(bd.getTime())) return 'unknown'
  if (cd.getTime() === bd.getTime()) return 'sameDay'
  return cd.getTime() > bd.getTime() ? 'backward' : 'forward'
}

/**
 * 按方向计算报表日数量。
 * netChange 口径始终为「两日之间持仓净增加」（买入为正、卖出为负）。
 */
export function calcInventoryRollForwardByDirection(
  countDateQty: number,
  netChange: number,
  direction: RollForwardDirection,
): number {
  const count = parseNum(countDateQty)
  const net = parseNum(netChange)
  if (direction === 'sameDay') return count
  if (direction === 'forward') return count + net
  // backward / unknown：默认期后盘点倒推（与致同模板一致）
  return count - net
}

/** 旧口径 changeQuantity（盘点→基准日调整量，用于 count+change）→ 新口径净增加 */
export function migrateLegacyChangeToNetIncrease(legacyAdjust: number): number {
  return -parseNum(legacyAdjust)
}

// ══════════════════════════════════════════════════════════
// P5: 公允价值差异 = 审定 - 未审（2dp）
// 用于G6-5 Level1/2/3公允价值测试差异计算
// ══════════════════════════════════════════════════════════

/**
 * 计算公允价值金额（Excel G6-5：数量 × 单位公允价值）
 * @param qty 数量
 * @param unitPrice 单位公允价值
 * @returns 公允价值，保留2位小数
 */
export function calcFairValueAmount(qty: number, unitPrice: number): number {
  return Math.round(parseNum(qty) * parseNum(unitPrice) * 100) / 100
}

/**
 * 计算公允价值差异
 * @param audited 审定公允价值
 * @param unadjusted 未审公允价值
 * @returns 差异金额，保留2位小数；正值=审定>未审
 */
export function calcFairValueDiff(audited: number, unadjusted: number): number {
  return Math.round((parseNum(audited) - parseNum(unadjusted)) * 100) / 100
}

/**
 * 数量变动对公允价值差异的影响
 * =（审定数量 − 未审数量）× 未审单价
 */
export function calcFairValueQtyImpact(
  auditedQty: number,
  unadjQty: number,
  unadjPrice: number,
): number {
  return Math.round(
    (parseNum(auditedQty) - parseNum(unadjQty)) * parseNum(unadjPrice) * 100,
  ) / 100
}

/**
 * 价格变动对公允价值差异的影响
 * = 审定数量 ×（审定单价 − 未审单价）
 */
export function calcFairValuePriceImpact(
  auditedQty: number,
  auditedPrice: number,
  unadjPrice: number,
): number {
  return Math.round(
    parseNum(auditedQty) * (parseNum(auditedPrice) - parseNum(unadjPrice)) * 100,
  ) / 100
}

// ══════════════════════════════════════════════════════════
// P6: 盘点差异 = 基准日数量 - 账面数量
// 正值=多(基准日>账面), 负值=少(基准日<账面)
// ══════════════════════════════════════════════════════════

/**
 * 计算盘点差异
 * @param reportDateQty 基准日数量（由calcInventoryRollForward推导）
 * @param bookQty 账面数量
 * @returns 差异数量；正值=多，负值=少
 */
export function calcInventoryVariance(reportDateQty: number, bookQty: number): number {
  return parseNum(reportDateQty) - parseNum(bookQty)
}
