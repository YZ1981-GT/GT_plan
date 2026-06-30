/**
 * useD4Analysis — D4-6~11 分析程序组通用 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 10.1
 *
 * 职责：
 * - D4-6 指标卡片网格(2列×N行) + TB自动取数
 * - D4-7 月度毛利率趋势表(12月×产品) + 波动>5%黄色
 * - D4-8 产品毛利对比 + 变动>10%红色
 * - D4-9 客户集中度(Top5/Top10/HHI) + >50%警告
 * - D4-10 客户价格变动 + >20%红色
 * - D4-11 产品价格趋势
 * - publishSignificantChange EventBus stub
 * - All use allResponses for persistence (D4-6-indicators, D4-7-rows, etc.)
 *
 * Requirements: 8.1-8.10, 17.5-17.7, 18.3
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcGrossMarginRate,
  calcProportion,
  calcChangeRate,
  calcSubtotal,
  isChangeRateExceeding,
} from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface IndicatorRow {
  key: string
  name: string
  currentValue: number
  priorValue: number
  change: number | '' | 'N/A'
  industryRef: string
  conclusion: 'normal' | 'abnormal' | 'attention' | ''
}

export interface MarginRow {
  product: string
  months: number[]       // 12个月毛利率
  priorMonths: number[]  // 上期12月
  annual: number
  priorAnnual: number
  change: number
}

export interface ProductMarginRow {
  product: string
  currentRevenue: number
  currentCost: number
  currentMargin: number  // 毛利率 auto
  priorRevenue: number
  priorCost: number
  priorMargin: number    // auto
  change: number         // auto
}

export interface CustomerRankRow {
  rank: number
  name: string
  amount: number
  proportion: number     // auto
}

export interface CustomerPriceRow {
  rowId: string
  customerName: string
  product: string
  currentPrice: number
  priorPrice: number
  change: number | '' | 'N/A'  // auto
  remark: string
}

export interface ProductPriceRow {
  rowId: string
  product: string
  currentPrice: number
  priorPrice: number
  change: number | '' | 'N/A'  // auto
  remark: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4Analysis(options: UseD4BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── D4-6 指标 ──────────────────────────────────────────────────────

  const indicators = ref<IndicatorRow[]>([])

  function loadIndicators(): void {
    const resp = allResponses.value.get('D4-6-indicators')
    const parsed = safeParseRows<IndicatorRow>(resp?.remark)
    if (parsed.length > 0) {
      indicators.value = parsed
    } else {
      // Default indicators
      indicators.value = [
        { key: 'revenue-growth', name: '营业收入增长率', currentValue: 0, priorValue: 0, change: '', industryRef: '', conclusion: '' },
        { key: 'gross-margin', name: '综合毛利率', currentValue: 0, priorValue: 0, change: '', industryRef: '', conclusion: '' },
        { key: 'receivable-turnover', name: '应收账款周转率', currentValue: 0, priorValue: 0, change: '', industryRef: '', conclusion: '' },
        { key: 'revenue-per-employee', name: '人均营业收入', currentValue: 0, priorValue: 0, change: '', industryRef: '', conclusion: '' },
        { key: 'cash-revenue-ratio', name: '现金/收入比', currentValue: 0, priorValue: 0, change: '', industryRef: '', conclusion: '' },
      ]
    }
  }

  watch(
    () => allResponses.value.get('D4-6-indicators')?.remark,
    () => loadIndicators(),
    { immediate: true },
  )

  // ─── D4-7 月度毛利率 ────────────────────────────────────────────────

  const marginMonthly = computed<MarginRow[]>(() => {
    const resp = allResponses.value.get('D4-7-rows')
    return safeParseRows<MarginRow>(resp?.remark)
  })

  // ─── D4-8 产品毛利对比 ──────────────────────────────────────────────

  const productMargins = computed<ProductMarginRow[]>(() => {
    const resp = allResponses.value.get('D4-8-rows')
    const rows = safeParseRows<ProductMarginRow>(resp?.remark)
    return rows.map(r => ({
      ...r,
      currentMargin: calcGrossMarginRate(parseNum(r.currentRevenue), parseNum(r.currentCost)),
      priorMargin: calcGrossMarginRate(parseNum(r.priorRevenue), parseNum(r.priorCost)),
      change: calcGrossMarginRate(parseNum(r.currentRevenue), parseNum(r.currentCost)) -
              calcGrossMarginRate(parseNum(r.priorRevenue), parseNum(r.priorCost)),
    }))
  })

  // ─── D4-9 客户结构 ──────────────────────────────────────────────────

  const customerStructureRaw = computed<CustomerRankRow[]>(() => {
    const resp = allResponses.value.get('D4-9-rows')
    return safeParseRows<CustomerRankRow>(resp?.remark)
  })

  const top5Customers = computed<CustomerRankRow[]>(() => {
    const sorted = [...customerStructureRaw.value].sort((a, b) => b.amount - a.amount)
    return sorted.slice(0, 5)
  })

  const top10Customers = computed<CustomerRankRow[]>(() => {
    const sorted = [...customerStructureRaw.value].sort((a, b) => b.amount - a.amount)
    return sorted.slice(0, 10)
  })

  const hhi = computed<number>(() => {
    const rows = customerStructureRaw.value
    const total = calcSubtotal(rows.map(r => parseNum(r.amount)))
    if (total === 0) return 0
    return rows.reduce((sum, r) => {
      const share = parseNum(r.amount) / total * 100
      return sum + share * share
    }, 0)
  })

  const concentrationWarning = computed<string | null>(() => {
    const rows = customerStructureRaw.value
    const total = calcSubtotal(rows.map(r => parseNum(r.amount)))
    if (total === 0) return null
    const top5Sum = calcSubtotal(top5Customers.value.map(r => parseNum(r.amount)))
    const ratio = top5Sum / total
    if (ratio > 0.5) {
      return `Top5客户集中度${(ratio * 100).toFixed(1)}%，超过50%警戒线`
    }
    return null
  })

  // ─── D4-10 客户价格变动 ─────────────────────────────────────────────

  const customerPrices = ref<CustomerPriceRow[]>([])

  function loadCustomerPrices(): void {
    const resp = allResponses.value.get('D4-10-rows')
    customerPrices.value = safeParseRows<CustomerPriceRow>(resp?.remark)
  }

  watch(
    () => allResponses.value.get('D4-10-rows')?.remark,
    () => loadCustomerPrices(),
    { immediate: true },
  )

  // ─── D4-11 产品价格趋势 ────────────────────────────────────────────

  const productPrices = ref<ProductPriceRow[]>([])

  function loadProductPrices(): void {
    const resp = allResponses.value.get('D4-11-rows')
    productPrices.value = safeParseRows<ProductPriceRow>(resp?.remark)
  }

  watch(
    () => allResponses.value.get('D4-11-rows')?.remark,
    () => loadProductPrices(),
    { immediate: true },
  )

  // ─── Row Operations ──────────────────────────────────────────────────

  function addCustomerPriceRow(): void {
    if (readonly.value) return
    customerPrices.value.push({
      rowId: generateRowId(),
      customerName: '',
      product: '',
      currentPrice: 0,
      priorPrice: 0,
      change: '',
      remark: '',
    })
    persistSection('D4-10-rows', customerPrices.value)
  }

  function removeCustomerPriceRow(rowId: string): void {
    if (readonly.value) return
    customerPrices.value = customerPrices.value.filter(r => r.rowId !== rowId)
    persistSection('D4-10-rows', customerPrices.value)
  }

  function addProductPriceRow(): void {
    if (readonly.value) return
    productPrices.value.push({
      rowId: generateRowId(),
      product: '',
      currentPrice: 0,
      priorPrice: 0,
      change: '',
      remark: '',
    })
    persistSection('D4-11-rows', productPrices.value)
  }

  function removeProductPriceRow(rowId: string): void {
    if (readonly.value) return
    productPrices.value = productPrices.value.filter(r => r.rowId !== rowId)
    persistSection('D4-11-rows', productPrices.value)
  }

  // ─── EventBus: publishSignificantChange ─────────────────────────────

  function publishSignificantChange(item: string, rate: number): void {
    try {
      window.dispatchEvent(new CustomEvent('analytical:significant-change', {
        detail: { wpCode: 'D4', indicator: item, changeRate: rate },
      }))
    } catch { /* silent */ }
  }

  // ─── Persistence ────────────────────────────────────────────────────

  function persistSection(itemId: string, data: any): void {
    const json = JSON.stringify(data)
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: json })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    try {
      const keys = ['D4-6-indicators', 'D4-7-rows', 'D4-8-rows', 'D4-9-rows', 'D4-10-rows', 'D4-11-rows']
      const items = keys.map(k => allResponses.value.get(k)).filter(Boolean)
      window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    // D4-6
    indicators,
    // D4-7
    marginMonthly,
    // D4-8
    productMargins,
    // D4-9
    top5Customers,
    top10Customers,
    hhi,
    concentrationWarning,
    // D4-10
    customerPrices,
    addCustomerPriceRow,
    removeCustomerPriceRow,
    // D4-11
    productPrices,
    addProductPriceRow,
    removeProductPriceRow,
    // EventBus
    publishSignificantChange,
  }
}

export default useD4Analysis
