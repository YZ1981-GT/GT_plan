/**
 * 存货底稿核心组 — 公式引擎（借方科目）
 *
 * 性能优化：LRU Map 缓存高频纯函数结果（Req 20.8）
 * 简单加减法函数不缓存（开销 > 收益），仅缓存涉及除法/日期解析等计算
 */

/** LRU-like Map 缓存，容量 512 条，超出清空重建（简洁高效） */
const _formulaCache = new Map<string, unknown>()
const CACHE_MAX = 512

function cached<T>(key: string, compute: () => T): T {
  if (_formulaCache.has(key)) return _formulaCache.get(key) as T
  const result = compute()
  if (_formulaCache.size >= CACHE_MAX) _formulaCache.clear()
  _formulaCache.set(key, result)
  return result
}

/** 清除公式缓存（测试/重载用） */
export function clearFormulaCache(): void {
  _formulaCache.clear()
}

/** 获取缓存命中统计（调试用） */
export function getFormulaCacheSize(): number {
  return _formulaCache.size
}

export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}
export function calcEndBalance(prior: number, debit: number, credit: number): number {
  return prior + debit - credit
}
export function calcChangeAmount(current: number, prior: number): number {
  return current - prior
}
export function calcChangeRate(prior: number, current: number): number | '' | 'N/A' {
  return cached(`cr:${prior}:${current}`, () => {
    if (prior === 0 && current === 0) return ''
    if (prior === 0) return 'N/A'
    return (current - prior) / prior
  })
}
export function calcSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + v, 0)
}

export function calcNetValue(gross: number, impairment: number): number {
  return gross - impairment
}

export function calcAuditedEnd(opening: number, increase: number, decrease: number, adjustment: number): number {
  return opening + increase - decrease + adjustment
}

export function calcEndAmount(opening: number, increase: number, decrease: number): number {
  return opening + increase - decrease
}

export function calcUnitPrice(amount: number, quantity: number): number | '' {
  if (!quantity) return ''
  return amount / quantity
}

export function isChangeRateExceeding(rate: number | '' | 'N/A', threshold: number): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}

export function isDebitCreditBalanced(debits: number[], credits: number[], tolerance = 0.005): boolean {
  return Math.abs(calcSubtotal(debits) - calcSubtotal(credits)) < tolerance
}

/** 库龄四段合计 */
export function calcAgingTotal(lt1: number, y1to2: number, y2to3: number, gt3: number): number {
  return lt1 + y1to2 + y2to3 + gt3
}

/** 存货周转率 = 营业成本 / 平均存货余额 */
export function calcTurnoverRate(cogs: number, avgInventory: number): number {
  return cached(`tr:${cogs}:${avgInventory}`, () => {
    if (!avgInventory) return 0
    return cogs / avgInventory
  })
}

/** 检查覆盖率 = 已查金额 / 账面金额 × 100 */
export function calcCoverageRatio(checked: number, bookTotal: number): number {
  return cached(`cov:${checked}:${bookTotal}`, () => {
    if (!bookTotal) return 0
    return (checked / bookTotal) * 100
  })
}

/** 产销率 = 销量 / 产量 × 100 */
export function calcProductionSalesRate(sales: number, production: number): number {
  return cached(`psr:${sales}:${production}`, () => {
    if (!production) return 0
    return (sales / production) * 100
  })
}

/** 两日期之间天数差（绝对值） */
export function calcDaysBetween(dateA: string, dateB: string): number {
  return cached(`days:${dateA}:${dateB}`, () => {
    const a = new Date(dateA + 'T00:00:00')
    const b = new Date(dateB + 'T00:00:00')
    if (isNaN(a.getTime()) || isNaN(b.getTime())) return 0
    return Math.round(Math.abs(a.getTime() - b.getTime()) / (24 * 60 * 60 * 1000))
  })
}

/**
 * 截止正确判定（纯函数）
 *
 * 入库日期和记账日期都在期末日期当日或之前 → 截止正确(true)
 * 任一日期在期末之后 → 截止不正确(false)
 * 无效日期输入 → false
 */
export function isCutoffCorrect(docDate: string, bookDate: string, periodEnd: string): boolean {
  return cached(`cut:${docDate}:${bookDate}:${periodEnd}`, () => {
    const doc = new Date(docDate + 'T00:00:00')
    const book = new Date(bookDate + 'T00:00:00')
    const end = new Date(periodEnd + 'T00:00:00')
    if (isNaN(doc.getTime()) || isNaN(book.getTime()) || isNaN(end.getTime())) return false
    return doc.getTime() <= end.getTime() && book.getTime() <= end.getTime()
  })
}
