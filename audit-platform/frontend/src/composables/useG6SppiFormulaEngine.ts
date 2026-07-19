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
 * - P4: 盘点倒轧 = 盘点日数量 + 增减（整数）
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
// P1: 实际利息收入 = 摊余成本 × 实际利率 × days/365（2dp）
// 实际利率法(CAS22): 利息收入按摊余成本×实际利率×计息天数/365确认
// ══════════════════════════════════════════════════════════

/**
 * 计算实际利息收入（实际利率法）
 * @param amortizedCost 期初摊余成本
 * @param effectiveRate 实际利率（如0.05表示5%）
 * @param days 计息天数（1~365）
 * @returns 实际利息收入，保留2位小数
 */
export function calcEffectiveInterest(amortizedCost: number, effectiveRate: number, days: number): number {
  return Math.round(parseNum(amortizedCost) * parseNum(effectiveRate) * parseNum(days) / 365 * 100) / 100
}

// ══════════════════════════════════════════════════════════
// P2: 现金流入 = 面值 × 票面利率 × days/365（2dp）
// SPPI合同现金流：仅含本金和利息的现金流量
// ══════════════════════════════════════════════════════════

/**
 * 计算票息现金流入（面值×票面利率×计息天数/365）
 * @param faceValue 面值
 * @param couponRate 票面利率（如0.04表示4%）
 * @param days 计息天数（1~365）
 * @returns 现金流入金额，保留2位小数
 */
export function calcCashInflow(faceValue: number, couponRate: number, days: number): number {
  return Math.round(parseNum(faceValue) * parseNum(couponRate) * parseNum(days) / 365 * 100) / 100
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

/**
 * Actual/365：由起止日期推算计息天数（不含起点、含终点的日历差）。
 * 无效/逆序/超 366 → null
 */
export function calcInterestDays(startDate: string, endDate: string): number | null {
  const start = String(startDate || '').trim()
  const end = String(endDate || '').trim()
  if (!start || !end) return null
  const a = new Date(`${start}T00:00:00`)
  const b = new Date(`${end}T00:00:00`)
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime()) || b <= a) return null
  const days = Math.round((b.getTime() - a.getTime()) / 86400000)
  if (days < 1 || days > 366) return null
  return days
}

// ══════════════════════════════════════════════════════════
// P4: 盘点倒轧 = 盘点日数量 + 增减
// 基准日数量推导：盘点日数量 ± 盘点日到基准日的增减
// ══════════════════════════════════════════════════════════

/**
 * 计算基准日（报表日）数量
 * @param countDateQty 盘点日数量
 * @param change 盘点日到基准日的增减（正=增加，负=减少）
 * @returns 基准日数量
 */
export function calcInventoryRollForward(countDateQty: number, change: number): number {
  return parseNum(countDateQty) + parseNum(change)
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
