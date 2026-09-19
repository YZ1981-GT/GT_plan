/**
 * F2-62 原材料单价分析表（对齐源模板）
 *
 * 一、同一供应商，采购不同物料单价分析
 * 二、同一原材料，在不同供应商处各月采购单价分析
 * 三、同一类原材料，不同规格材料跨年度采购单价分析
 *
 * 所有采购单价均自动计算：采购金额 ÷ 采购数量。
 */
import { calcSubtotal } from './useF2SpecialFormulaEngine'

export const UNIT_PRICE_MONTH_LABELS = [
  '1月', '2月', '3月', '4月', '5月', '6月',
  '7月', '8月', '9月', '10月', '11月', '12月',
] as const

export const F2_62_OBJECTIVE =
  '从供应商、原材料和规格三个维度比较采购单价，识别同一交易对手差异定价、'
  + '同一材料跨供应商价格偏离及同类材料跨年度价格异常，验证采购成本真实性与公允性。'

export const F2_62_FRAUD_TIP =
  '根据《中国注册会计师审计准则问题解答第18号——识别和应对第三方配合实施财务舞弊》：'
  + '关注第三方供应商虚增或虚减原材料采购单价、套取资金支付账外成本费用、'
  + '延迟或提前确认费用，以及第三方代为承担成本费用。'

export interface UnitPriceCell {
  amount: number
  qty: number
}

export interface MonthlyComparisonItem {
  id: string
  name: string
  months: UnitPriceCell[]
}

export interface MonthlyComparisonGroup {
  id: string
  name: string
  items: MonthlyComparisonItem[]
}

export interface AnnualPeriodCell extends UnitPriceCell {
  label: string
}

export interface SpecComparisonItem {
  id: string
  spec: string
  periods: AnnualPeriodCell[]
}

export interface SpecComparisonGroup {
  id: string
  categoryName: string
  items: SpecComparisonItem[]
}

export interface UnitPriceSheet {
  /** 一、供应商为组，item 为物料 */
  supplierGroups: MonthlyComparisonGroup[]
  /** 二、原材料为组，item 为供应商 */
  materialGroups: MonthlyComparisonGroup[]
  /** 三、同类原材料为组，item 为规格 */
  specGroups: SpecComparisonGroup[]
}

export interface EnrichedMonth extends UnitPriceCell {
  monthIndex: number
  unitPrice: number | null
}

export interface EnrichedMonthlyItem extends MonthlyComparisonItem {
  enrichedMonths: EnrichedMonth[]
  totalAmount: number
  totalQty: number
  avgPrice: number | null
  /** 同组平均价偏离率 */
  groupDeviation: number | null
  isAbnormal: boolean
}

export interface EnrichedMonthlyGroup extends Omit<MonthlyComparisonGroup, 'items'> {
  items: EnrichedMonthlyItem[]
  monthAmounts: number[]
  monthQtys: number[]
  monthPrices: (number | null)[]
  totalAmount: number
  totalQty: number
  avgPrice: number | null
  abnormalCount: number
}

export interface EnrichedAnnualPeriod extends AnnualPeriodCell {
  unitPrice: number | null
}

export interface EnrichedSpecItem extends Omit<SpecComparisonItem, 'periods'> {
  periods: EnrichedAnnualPeriod[]
  latestChangeRate: number | null
  isAbnormal: boolean
}

export interface EnrichedSpecGroup extends Omit<SpecComparisonGroup, 'items'> {
  items: EnrichedSpecItem[]
  abnormalCount: number
}

export const GROUP_DEVIATION_THRESHOLD = 0.2
export const YEAR_CHANGE_THRESHOLD = 0.2

export function newUnitPriceId(prefix = 'f2up'): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyUnitPriceCell(): UnitPriceCell {
  return { amount: 0, qty: 0 }
}

export function emptyMonthlyItem(): MonthlyComparisonItem {
  return {
    id: newUnitPriceId('item'),
    name: '',
    months: Array.from({ length: 12 }, () => emptyUnitPriceCell()),
  }
}

export function emptyMonthlyGroup(): MonthlyComparisonGroup {
  return {
    id: newUnitPriceId('group'),
    name: '',
    items: [emptyMonthlyItem()],
  }
}

export function emptySpecItem(): SpecComparisonItem {
  return {
    id: newUnitPriceId('spec'),
    spec: '',
    periods: [
      { label: '本期', amount: 0, qty: 0 },
      { label: '上期', amount: 0, qty: 0 },
      { label: '上上期', amount: 0, qty: 0 },
    ],
  }
}

export function emptySpecGroup(): SpecComparisonGroup {
  return {
    id: newUnitPriceId('category'),
    categoryName: '',
    items: [emptySpecItem()],
  }
}

export function defaultUnitPriceSheet(): UnitPriceSheet {
  return {
    supplierGroups: [emptyMonthlyGroup()],
    materialGroups: [emptyMonthlyGroup()],
    specGroups: [emptySpecGroup()],
  }
}

export function calcUnitPrice(amount: number, qty: number): number | null {
  return qty ? amount / qty : null
}

export function calcChangeRate(current: number | null, prior: number | null): number | null {
  if (current === null || prior === null || prior === 0) return null
  return (current - prior) / prior
}

export function isBlankMonthlyItem(item: MonthlyComparisonItem): boolean {
  return !(item.name || '').trim()
    && item.months.every((m) => Number(m.amount || 0) === 0 && Number(m.qty || 0) === 0)
}

export function isBlankMonthlyGroup(group: MonthlyComparisonGroup): boolean {
  return !(group.name || '').trim() && group.items.every(isBlankMonthlyItem)
}

export function isBlankSpecItem(item: SpecComparisonItem): boolean {
  return !(item.spec || '').trim()
    && item.periods.every((p) => Number(p.amount || 0) === 0 && Number(p.qty || 0) === 0)
}

export function isBlankSpecGroup(group: SpecComparisonGroup): boolean {
  return !(group.categoryName || '').trim() && group.items.every(isBlankSpecItem)
}

function normalizeMonthlyItem(item: Partial<MonthlyComparisonItem>): MonthlyComparisonItem {
  const base = emptyMonthlyItem()
  return {
    ...base,
    ...item,
    id: item.id || base.id,
    months: Array.isArray(item.months) && item.months.length === 12
      ? item.months.map((m) => ({ ...emptyUnitPriceCell(), ...m }))
      : base.months,
  }
}

export function pruneMonthlyGroups(groups: MonthlyComparisonGroup[]): MonthlyComparisonGroup[] {
  const normalized = groups.map((group) => {
    const items = (group.items || []).map(normalizeMonthlyItem)
    const filledItems = items.filter((item) => !isBlankMonthlyItem(item))
    return {
      ...group,
      id: group.id || newUnitPriceId('group'),
      items: filledItems.length ? filledItems : [emptyMonthlyItem()],
    }
  }).filter((group) => !isBlankMonthlyGroup(group))
  return normalized.length ? normalized : [emptyMonthlyGroup()]
}

export function pruneSpecGroups(groups: SpecComparisonGroup[]): SpecComparisonGroup[] {
  const normalized = groups.map((group) => {
    const items = (group.items || []).map((item) => {
      const base = emptySpecItem()
      return {
        ...base,
        ...item,
        id: item.id || base.id,
        periods: Array.isArray(item.periods) && item.periods.length === 3
          ? item.periods.map((p, i) => ({ ...base.periods[i], ...p }))
          : base.periods,
      }
    })
    const filledItems = items.filter((item) => !isBlankSpecItem(item))
    return {
      ...group,
      id: group.id || newUnitPriceId('category'),
      items: filledItems.length ? filledItems : [emptySpecItem()],
    }
  }).filter((group) => !isBlankSpecGroup(group))
  return normalized.length ? normalized : [emptySpecGroup()]
}

function enrichMonthlyItem(
  item: MonthlyComparisonItem,
  groupAvgPrice: number | null,
): EnrichedMonthlyItem {
  const totalAmount = calcSubtotal(item.months.map((m) => m.amount))
  const totalQty = calcSubtotal(item.months.map((m) => m.qty))
  const avgPrice = calcUnitPrice(totalAmount, totalQty)
  const groupDeviation = calcChangeRate(avgPrice, groupAvgPrice)
  const isAbnormal = groupDeviation !== null
    && Math.abs(groupDeviation) > GROUP_DEVIATION_THRESHOLD
  return {
    ...item,
    enrichedMonths: item.months.map((m, monthIndex) => ({
      ...m,
      monthIndex,
      unitPrice: calcUnitPrice(m.amount, m.qty),
    })),
    totalAmount,
    totalQty,
    avgPrice,
    groupDeviation,
    isAbnormal,
  }
}

export function enrichMonthlyGroup(group: MonthlyComparisonGroup): EnrichedMonthlyGroup {
  const monthAmounts = Array.from({ length: 12 }, (_, i) =>
    calcSubtotal(group.items.map((item) => item.months[i]?.amount ?? 0)),
  )
  const monthQtys = Array.from({ length: 12 }, (_, i) =>
    calcSubtotal(group.items.map((item) => item.months[i]?.qty ?? 0)),
  )
  const totalAmount = calcSubtotal(monthAmounts)
  const totalQty = calcSubtotal(monthQtys)
  const avgPrice = calcUnitPrice(totalAmount, totalQty)
  const items = group.items.map((item) => enrichMonthlyItem(item, avgPrice))
  return {
    ...group,
    items,
    monthAmounts,
    monthQtys,
    monthPrices: monthAmounts.map((amount, i) => calcUnitPrice(amount, monthQtys[i])),
    totalAmount,
    totalQty,
    avgPrice,
    abnormalCount: items.filter((item) => item.isAbnormal).length,
  }
}

export function enrichMonthlyGroups(groups: MonthlyComparisonGroup[]): EnrichedMonthlyGroup[] {
  return groups.map(enrichMonthlyGroup)
}

export function enrichSpecGroup(group: SpecComparisonGroup): EnrichedSpecGroup {
  const items = group.items.map((item): EnrichedSpecItem => {
    const periods = item.periods.map((p) => ({
      ...p,
      unitPrice: calcUnitPrice(p.amount, p.qty),
    }))
    const latestChangeRate = calcChangeRate(periods[0].unitPrice, periods[1].unitPrice)
    const isAbnormal = latestChangeRate !== null
      && Math.abs(latestChangeRate) > YEAR_CHANGE_THRESHOLD
    return { ...item, periods, latestChangeRate, isAbnormal }
  })
  return {
    ...group,
    items,
    abnormalCount: items.filter((item) => item.isAbnormal).length,
  }
}

export function enrichSpecGroups(groups: SpecComparisonGroup[]): EnrichedSpecGroup[] {
  return groups.map(enrichSpecGroup)
}

interface LegacyUnitPriceRow {
  id?: string
  materialName?: string
  spec?: string
  qtyT?: number
  qtyT1?: number
  qtyT2?: number
  priceT?: number
  priceT1?: number
  priceT2?: number
}

export function migrateUnitPriceSheet(legacy: unknown): UnitPriceSheet {
  const fallback = defaultUnitPriceSheet()
  if (!legacy) return fallback

  if (typeof legacy === 'object' && legacy !== null && 'supplierGroups' in legacy) {
    const sheet = legacy as UnitPriceSheet
    return {
      supplierGroups: pruneMonthlyGroups(sheet.supplierGroups || []),
      materialGroups: pruneMonthlyGroups(sheet.materialGroups || []),
      specGroups: pruneSpecGroups(sheet.specGroups || []),
    }
  }

  // 旧版 T/T-1/T-2 扁平行自然迁移到第三部分“不同规格跨年度比较”
  if (Array.isArray(legacy) && legacy.length) {
    const byCategory = new Map<string, SpecComparisonItem[]>()
    for (const raw of legacy as LegacyUnitPriceRow[]) {
      const category = (raw.materialName || '').trim() || '未分类原材料'
      const item = emptySpecItem()
      item.id = raw.id || item.id
      item.spec = raw.spec || ''
      const qtys = [raw.qtyT, raw.qtyT1, raw.qtyT2]
      const prices = [raw.priceT, raw.priceT1, raw.priceT2]
      item.periods = item.periods.map((period, i) => ({
        ...period,
        qty: Number(qtys[i] || 0),
        amount: Number(qtys[i] || 0) * Number(prices[i] || 0),
      }))
      const list = byCategory.get(category) || []
      list.push(item)
      byCategory.set(category, list)
    }
    const specGroups = Array.from(byCategory, ([categoryName, items]) => ({
      id: newUnitPriceId('category'),
      categoryName,
      items,
    }))
    return {
      supplierGroups: fallback.supplierGroups,
      materialGroups: fallback.materialGroups,
      specGroups: pruneSpecGroups(specGroups),
    }
  }

  return fallback
}
