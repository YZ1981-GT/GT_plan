/**
 * useF2PurchasePrice — F2-61 原材料采购价格分析（118行×17列，4区段Tab）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcSubtotal, calcUnitPrice } from './useF2InvMaiFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export type PurchasePriceSegment = 'basic' | 'h1' | 'h2' | 'summary'

export interface MonthPurchase {
  amount: number
  qty: number
}

export interface PurchasePriceRow {
  id: string
  materialName: string
  spec: string
  unit: string
  months: MonthPurchase[]
  priorAvgPrice: number
}

export const MONTH_LABELS = [
  '1月', '2月', '3月', '4月', '5月', '6月',
  '7月', '8月', '9月', '10月', '11月', '12月',
] as const

const ROWS_KEY = 'F2-61-rows'
const NOTE_KEY = 'F2-61-note'
const ABNORMAL_THRESHOLD = 0.3

function emptyMonths(): MonthPurchase[] {
  return Array.from({ length: 12 }, () => ({ amount: 0, qty: 0 }))
}

function emptyRow(id: string): PurchasePriceRow {
  return {
    id, materialName: '', spec: '', unit: '',
    months: emptyMonths(), priorAvgPrice: 0,
  }
}

export interface EnrichedMonth extends MonthPurchase {
  monthIndex: number
  unitPrice: number | ''
  priceAbnormal: boolean
}

export interface EnrichedPurchasePriceRow extends PurchasePriceRow {
  enrichedMonths: EnrichedMonth[]
  annualTotalAmount: number
  annualTotalQty: number
  annualAvgPrice: number
  changeRate: number
  isAbnormal: boolean
}

export function enrichPurchasePriceRow(r: PurchasePriceRow): EnrichedPurchasePriceRow {
  const annualTotalAmount = calcSubtotal(r.months.map((m) => m.amount))
  const annualTotalQty = calcSubtotal(r.months.map((m) => m.qty))
  const annualAvgPrice = annualTotalQty
    ? annualTotalAmount / annualTotalQty
    : 0
  const changeRate = r.priorAvgPrice
    ? ((annualAvgPrice - r.priorAvgPrice) / r.priorAvgPrice) * 100
    : 0

  const enrichedMonths: EnrichedMonth[] = r.months.map((m, monthIndex) => {
    const unitPrice = calcUnitPrice(m.amount, m.qty)
    const priceAbnormal = typeof unitPrice === 'number'
      && annualAvgPrice > 0
      && Math.abs((unitPrice - annualAvgPrice) / annualAvgPrice) > ABNORMAL_THRESHOLD
    return { ...m, monthIndex, unitPrice, priceAbnormal }
  })

  return {
    ...r,
    enrichedMonths,
    annualTotalAmount,
    annualTotalQty,
    annualAvgPrice,
    changeRate,
    isAbnormal: Math.abs(changeRate) > 30,
  }
}

export function useF2PurchasePrice(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const activeSegment = ref<PurchasePriceSegment>('basic')
  const searchQuery = ref('')
  const rows = ref<PurchasePriceRow[]>([emptyRow('1')])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as PurchasePriceRow[]
        if (parsed.length) {
          rows.value = parsed.map((r) => ({
            ...r,
            months: r.months?.length === 12 ? r.months : emptyMonths(),
          }))
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichPurchasePriceRow))

  const filteredRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      r.materialName.toLowerCase().includes(q)
      || r.spec.toLowerCase().includes(q),
    )
  })

  const abnormalCount = computed(() =>
    enrichedRows.value.filter((r) =>
      r.enrichedMonths.some((m) => m.priceAbnormal) || r.isAbnormal,
    ).length,
  )

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateRow(id: string, patch: Partial<PurchasePriceRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  function updateMonth(rowId: string, monthIndex: number, patch: Partial<MonthPurchase>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== rowId) return r
      const months = r.months.map((m, i) =>
        i === monthIndex ? { ...m, ...patch } : m,
      )
      return { ...r, months }
    })
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入材料名称', '新增材料', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      rows.value = [...rows.value, { ...emptyRow(String(Date.now())), materialName: value }]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return {
    activeSegment,
    searchQuery,
    filteredRows,
    abnormalCount,
    auditNote,
    updateRow,
    updateMonth,
    addRow,
    removeRow,
  }
}

export default useF2PurchasePrice
