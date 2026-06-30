/**
 * useD4RelatedPrice — D4-21 关联方价格公允性分析 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 13.1
 *
 * 职责：
 * - 对比分析表（关联vs非关联单价+差异率+结论）
 * - >10%黄色/>20%红色阈值
 * - relatedSalesTotal + proportionToRevenue computed
 * - addRow / removeRow
 *
 * Requirements: 13.1-13.8
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcPriceDiffRate,
  calcSubtotal,
  calcProportion,
} from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RelatedPriceRow {
  rowId: string
  product: string
  relatedCustomer: string
  relatedPrice: number
  nonRelatedCustomer: string
  nonRelatedPrice: number
  priceDiffRate: number       // auto = (rp - nrp) / nrp * 100
  reason: string
  conclusion: 'normal' | 'abnormal' | 'attention' | ''
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D4-21-rows'
const NOTE_KEY = 'D4-21-note'
const CONCLUSION_KEY = 'D4-21-conclusion'
const YELLOW_THRESHOLD = 10  // >10% 黄色
const RED_THRESHOLD = 20     // >20% 红色

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

export function useD4RelatedPrice(options: UseD4BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Rows ─────────────────────────────────────────────────────────────

  const rows = ref<RelatedPriceRow[]>([])

  function loadRows(): void {
    const resp = allResponses.value.get(STORAGE_KEY)
    const parsed = safeParseRows<RelatedPriceRow>(resp?.remark)
    rows.value = parsed.map(r => ({
      ...r,
      priceDiffRate: calcPriceDiffRate(parseNum(r.relatedPrice), parseNum(r.nonRelatedPrice)),
    }))
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => loadRows(),
    { immediate: true },
  )

  // ─── Thresholds ───────────────────────────────────────────────────────

  /** Get color class for a diff rate: >20% red, >10% yellow, else '' */
  function getDiffRateColor(rate: number): 'red' | 'yellow' | '' {
    const absRate = Math.abs(rate)
    if (absRate > RED_THRESHOLD) return 'red'
    if (absRate > YELLOW_THRESHOLD) return 'yellow'
    return ''
  }

  // ─── Computed: relatedSalesTotal + proportionToRevenue ────────────────

  const relatedSalesTotal = computed<number>(() => {
    return calcSubtotal(rows.value.map(r => parseNum(r.relatedPrice)))
  })

  const proportionToRevenue = computed<number>(() => {
    // Get total revenue from D4-1 grand total or TB
    const tbResp = allResponses.value.get('D4-1-adj-tb-6001')
    const totalRevenue = parseNum(tbResp?.remark)
    return calcProportion(relatedSalesTotal.value, totalRevenue)
  })

  // ─── Audit Note / Conclusion ──────────────────────────────────────────

  const auditNote = ref('')
  const auditConclusion = ref('')

  watch(
    () => allResponses.value.get(NOTE_KEY)?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(CONCLUSION_KEY)?.remark,
    (val) => { auditConclusion.value = val || '' },
    { immediate: true },
  )

  watch(auditNote, (val) => {
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  watch(auditConclusion, (val) => {
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  // ─── Row Operations ───────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    rows.value.push({
      rowId: generateRowId(),
      product: '',
      relatedCustomer: '',
      relatedPrice: 0,
      nonRelatedCustomer: '',
      nonRelatedPrice: 0,
      priceDiffRate: 0,
      reason: '',
      conclusion: '',
      remark: '',
    })
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // Recalculate diff rate if price fields changed
    if (field === 'relatedPrice' || field === 'nonRelatedPrice') {
      row.priceDiffRate = calcPriceDiffRate(parseNum(row.relatedPrice), parseNum(row.nonRelatedPrice))
    }
    persistRows()
  }

  // ─── Persistence ──────────────────────────────────────────────────────

  function persistRows(): void {
    const json = JSON.stringify(rows.value)
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: json })
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
      const items = [STORAGE_KEY, NOTE_KEY, CONCLUSION_KEY]
        .map(k => allResponses.value.get(k))
        .filter(Boolean)
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
    rows,
    relatedSalesTotal,
    proportionToRevenue,
    auditNote,
    auditConclusion,
    getDiffRateColor,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useD4RelatedPrice
