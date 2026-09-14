/**
 * F2-61 原材料采购价格分析表（对齐致同源模板）
 *
 * 模板结构：同一组主要原材料按四个维度逐月展开——
 *   ① 入库金额（元）：1~12月 + 上期末 + 本期合计金额(=Σ月) + 上期合计金额（手工）
 *   ② 入库数量：同结构，本期合计数量 = Σ月
 *   ③ 入库单价（元）：全自动 = 金额 ÷ 数量；本期平均 = 合计金额 ÷ 合计数量
 *   ④ 市场单价（元）：逐月手工；本期平均 = 已填月份简单平均；上期平均手工
 * 编制逻辑：借"金额=数量×单价"勾稽 + 采购价 vs 市场价对比，
 * 识别第三方配合舞弊（问题解答第18号）。
 */
import { calcSubtotal } from './useF2SpecialFormulaEngine'

export const PURCHASE_MONTH_LABELS = [
  '1月', '2月', '3月', '4月', '5月', '6月',
  '7月', '8月', '9月', '10月', '11月', '12月',
] as const

export const F2_61_OBJECTIVE =
  '按报告期逐月比较主要原材料的采购金额、数量、单价，并与市场单价对照，'
  + '识别采购价格异常波动与偏离市场价格的情形，验证采购成本的真实性与公允性。'

export const F2_61_FRAUD_TIP =
  '根据《中国注册会计师审计准则问题解答第18号——识别和应对第三方配合实施财务舞弊》：'
  + '关注第三方供应商虚增或虚减原材料采购单价，套取资金支付账外成本费用，'
  + '延迟或提前确认费用、第三方代为承担成本费用。'

/** 单月三维数据：入库金额 / 入库数量（单价自动）+ 市场单价 */
export interface PurchaseMonthCell {
  amount: number
  qty: number
  marketPrice: number
}

export interface PurchasePriceMaterial {
  id: string
  materialName: string
  unit: string
  months: PurchaseMonthCell[]
  /** 上期末列（模板 N 列）：上期末金额/数量/市场单价 */
  priorEnd: PurchaseMonthCell
  /** 上期合计金额（模板 P 列，手工） */
  priorTotalAmount: number
  /** 上期合计数量（手工） */
  priorTotalQty: number
  /** 上期平均市场单价（手工） */
  priorAvgMarketPrice: number
  remark: string
}

export interface PurchasePriceSheet {
  materials: PurchasePriceMaterial[]
}

/** 单价异常阈值：月度采购单价偏离本期平均 ±30% */
export const PRICE_VARIANCE_THRESHOLD = 0.3
/** 市场价差异阈值：采购均价 vs 市场均价 ±10% */
export const MARKET_DIFF_THRESHOLD = 0.1

export interface EnrichedPurchaseMonth extends PurchaseMonthCell {
  monthIndex: number
  /** 入库单价 = 金额 ÷ 数量（数量为0时 null） */
  unitPrice: number | null
  /** 月度单价偏离本期平均 > 阈值 */
  priceAbnormal: boolean
}

export interface EnrichedPurchaseMaterial extends PurchasePriceMaterial {
  enrichedMonths: EnrichedPurchaseMonth[]
  /** 本期合计金额 = Σ月金额 */
  currentTotalAmount: number
  /** 本期合计数量 = Σ月数量 */
  currentTotalQty: number
  /** 本期平均单价 = 合计金额 ÷ 合计数量 */
  currentAvgPrice: number | null
  /** 上期平均单价 = 上期合计金额 ÷ 上期合计数量 */
  priorAvgPrice: number | null
  /** 上期末单价 = 上期末金额 ÷ 上期末数量 */
  priorEndUnitPrice: number | null
  /** 本期平均市场单价 = 已填月份市场价简单平均 */
  currentAvgMarketPrice: number | null
  /** 采购均价 vs 市场均价 差异率 */
  marketDiffRate: number | null
  /** 有月度单价异常 */
  hasMonthlyVariance: boolean
  /** 与市场价差异超阈值 */
  hasMarketDiff: boolean
  highlight: boolean
}

export interface PurchasePriceTotals {
  monthAmounts: number[]
  monthQtys: number[]
  monthUnitPrices: (number | null)[]
  monthMarketAvgs: (number | null)[]
  priorEndAmount: number
  priorEndQty: number
  currentTotalAmount: number
  currentTotalQty: number
  priorTotalAmount: number
  priorTotalQty: number
  /** 小计单价 = Σ金额 ÷ Σ数量（加权） */
  currentAvgPrice: number | null
  priorAvgPrice: number | null
}

export function newPurchasePriceId(): string {
  return `f2pp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyPurchaseMonthCell(): PurchaseMonthCell {
  return { amount: 0, qty: 0, marketPrice: 0 }
}

export function emptyPurchaseMaterial(): PurchasePriceMaterial {
  return {
    id: newPurchasePriceId(),
    materialName: '',
    unit: '',
    months: Array.from({ length: 12 }, () => emptyPurchaseMonthCell()),
    priorEnd: emptyPurchaseMonthCell(),
    priorTotalAmount: 0,
    priorTotalQty: 0,
    priorAvgMarketPrice: 0,
    remark: '',
  }
}

export function defaultPurchasePriceSheet(): PurchasePriceSheet {
  return { materials: [emptyPurchaseMaterial()] }
}

export function isBlankPurchaseMaterial(row: PurchasePriceMaterial): boolean {
  const monthsBlank = row.months.every(
    (m) => Number(m.amount || 0) === 0 && Number(m.qty || 0) === 0 && Number(m.marketPrice || 0) === 0,
  )
  const priorBlank = Number(row.priorEnd?.amount || 0) === 0
    && Number(row.priorEnd?.qty || 0) === 0
    && Number(row.priorEnd?.marketPrice || 0) === 0
    && Number(row.priorTotalAmount || 0) === 0
    && Number(row.priorTotalQty || 0) === 0
    && Number(row.priorAvgMarketPrice || 0) === 0
  return !(row.materialName || '').trim()
    && !(row.unit || '').trim()
    && !(row.remark || '').trim()
    && monthsBlank
    && priorBlank
}

export function pruneBlankPurchaseMaterials(
  rows: PurchasePriceMaterial[],
): PurchasePriceMaterial[] {
  const filled = rows.filter((row) => !isBlankPurchaseMaterial(row))
  return filled.length ? filled : [emptyPurchaseMaterial()]
}

export function calcPurchaseUnitPrice(amount: number, qty: number): number | null {
  if (!qty) return null
  return amount / qty
}

export function enrichPurchaseMaterial(row: PurchasePriceMaterial): EnrichedPurchaseMaterial {
  const currentTotalAmount = calcSubtotal(row.months.map((m) => m.amount))
  const currentTotalQty = calcSubtotal(row.months.map((m) => m.qty))
  const currentAvgPrice = calcPurchaseUnitPrice(currentTotalAmount, currentTotalQty)
  const priorAvgPrice = calcPurchaseUnitPrice(row.priorTotalAmount, row.priorTotalQty)
  const priorEndUnitPrice = calcPurchaseUnitPrice(row.priorEnd.amount, row.priorEnd.qty)

  const filledMarket = row.months.map((m) => m.marketPrice).filter((v) => Number(v) > 0)
  const currentAvgMarketPrice = filledMarket.length
    ? calcSubtotal(filledMarket) / filledMarket.length
    : null

  const enrichedMonths: EnrichedPurchaseMonth[] = row.months.map((m, monthIndex) => {
    const unitPrice = calcPurchaseUnitPrice(m.amount, m.qty)
    const priceAbnormal = unitPrice !== null
      && currentAvgPrice !== null
      && currentAvgPrice > 0
      && Math.abs((unitPrice - currentAvgPrice) / currentAvgPrice) > PRICE_VARIANCE_THRESHOLD
    return { ...m, monthIndex, unitPrice, priceAbnormal }
  })

  const marketDiffRate = currentAvgPrice !== null && currentAvgMarketPrice
    ? (currentAvgPrice - currentAvgMarketPrice) / currentAvgMarketPrice
    : null

  const hasMonthlyVariance = enrichedMonths.some((m) => m.priceAbnormal)
  const hasMarketDiff = marketDiffRate !== null
    && Math.abs(marketDiffRate) > MARKET_DIFF_THRESHOLD

  return {
    ...row,
    enrichedMonths,
    currentTotalAmount,
    currentTotalQty,
    currentAvgPrice,
    priorAvgPrice,
    priorEndUnitPrice,
    currentAvgMarketPrice,
    marketDiffRate,
    hasMonthlyVariance,
    hasMarketDiff,
    highlight: hasMonthlyVariance || hasMarketDiff,
  }
}

export function enrichPurchaseMaterials(
  rows: PurchasePriceMaterial[],
): EnrichedPurchaseMaterial[] {
  return rows.map(enrichPurchaseMaterial)
}

export function calcPurchasePriceTotals(
  rows: EnrichedPurchaseMaterial[],
): PurchasePriceTotals {
  const monthAmounts = Array.from({ length: 12 }, (_, i) =>
    calcSubtotal(rows.map((r) => r.months[i]?.amount ?? 0)),
  )
  const monthQtys = Array.from({ length: 12 }, (_, i) =>
    calcSubtotal(rows.map((r) => r.months[i]?.qty ?? 0)),
  )
  const monthUnitPrices = monthAmounts.map((amt, i) =>
    calcPurchaseUnitPrice(amt, monthQtys[i]),
  )
  const monthMarketAvgs = Array.from({ length: 12 }, (_, i) => {
    const vals = rows.map((r) => r.months[i]?.marketPrice ?? 0).filter((v) => v > 0)
    return vals.length ? calcSubtotal(vals) / vals.length : null
  })
  const currentTotalAmount = calcSubtotal(rows.map((r) => r.currentTotalAmount))
  const currentTotalQty = calcSubtotal(rows.map((r) => r.currentTotalQty))
  const priorTotalAmount = calcSubtotal(rows.map((r) => r.priorTotalAmount))
  const priorTotalQty = calcSubtotal(rows.map((r) => r.priorTotalQty))
  return {
    monthAmounts,
    monthQtys,
    monthUnitPrices,
    monthMarketAvgs,
    priorEndAmount: calcSubtotal(rows.map((r) => r.priorEnd.amount)),
    priorEndQty: calcSubtotal(rows.map((r) => r.priorEnd.qty)),
    currentTotalAmount,
    currentTotalQty,
    priorTotalAmount,
    priorTotalQty,
    currentAvgPrice: calcPurchaseUnitPrice(currentTotalAmount, currentTotalQty),
    priorAvgPrice: calcPurchaseUnitPrice(priorTotalAmount, priorTotalQty),
  }
}

/** 旧版行结构（半年分段实现）：months 仅 {amount, qty}，另有 spec/priorAvgPrice */
interface LegacyPurchaseRow {
  id?: string
  materialName?: string
  spec?: string
  unit?: string
  months?: Array<{ amount?: number; qty?: number; marketPrice?: number }>
  priorAvgPrice?: number
  remark?: string
}

export function migratePurchasePriceSheet(legacy: unknown): PurchasePriceSheet {
  const sheet = defaultPurchasePriceSheet()
  if (!legacy) return sheet

  if (typeof legacy === 'object' && legacy !== null && 'materials' in legacy) {
    const s = legacy as PurchasePriceSheet
    const rows = (s.materials || []).map((r) => ({
      ...emptyPurchaseMaterial(),
      ...r,
      id: r.id || newPurchasePriceId(),
      months: Array.isArray(r.months) && r.months.length === 12
        ? r.months.map((m) => ({ ...emptyPurchaseMonthCell(), ...m }))
        : Array.from({ length: 12 }, () => emptyPurchaseMonthCell()),
      priorEnd: { ...emptyPurchaseMonthCell(), ...(r.priorEnd || {}) },
    }))
    return { materials: pruneBlankPurchaseMaterials(rows) }
  }

  if (Array.isArray(legacy) && legacy.length) {
    const rows = (legacy as LegacyPurchaseRow[]).map((r) => {
      const base = emptyPurchaseMaterial()
      // 旧版"规格"并入材料名称，避免信息丢失
      const name = [r.materialName, r.spec].filter((s) => (s || '').trim()).join(' ')
      return {
        ...base,
        id: String(r.id || newPurchasePriceId()),
        materialName: name,
        unit: String(r.unit || ''),
        months: Array.isArray(r.months) && r.months.length === 12
          ? r.months.map((m) => ({
              amount: Number(m?.amount ?? 0),
              qty: Number(m?.qty ?? 0),
              marketPrice: Number(m?.marketPrice ?? 0),
            }))
          : base.months,
        priorAvgMarketPrice: Number(r.priorAvgPrice ?? 0),
        remark: String(r.remark || ''),
      }
    })
    return { materials: pruneBlankPurchaseMaterials(rows) }
  }

  return sheet
}
