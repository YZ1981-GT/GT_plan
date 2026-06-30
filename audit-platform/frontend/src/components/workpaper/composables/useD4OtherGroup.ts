/**
 * useD4OtherGroup — D4-33~36 其他收入组 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 15.1
 *
 * 职责：
 * - D4-33 otherMarginRows: product/revenue/cost/margin (auto from D4-3 data)
 * - D4-34 otherContractRows: contractName/amount/term/shouldRecognize/actualRecognize/diff
 * - D4-35 otherCheckRows: same as D4-14 structure (voucher check)
 * - D4-36 otherCutoffRows: same as D4-17/18 structure (cutoff test)
 * - Each section stored as `D4-{N}-rows`
 *
 * Requirements: 15.1-15.8
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcGrossMarginRate,
  calcSubtotal,
  isCrossPeriod,
  calcCrossPeriodDays,
  calcAnomalyRate,
} from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface OtherMarginRow {
  rowId: string
  product: string
  revenue: number
  cost: number
  margin: number           // auto = (revenue - cost) / revenue
}

export interface OtherContractRow {
  rowId: string
  contractName: string
  amount: number
  term: string
  shouldRecognize: number
  actualRecognize: number
  diff: number             // auto = actualRecognize - shouldRecognize
  remark: string
}

export interface OtherCheckRow {
  rowId: string
  voucherNo: string
  voucherDate: string
  customerName: string
  amount: number
  hasContract: 'Y' | 'N' | ''
  hasDelivery: 'Y' | 'N' | ''
  hasInvoice: 'Y' | 'N' | ''
  isAnomalous: boolean
  remark: string
}

export interface OtherCutoffRow {
  rowId: string
  voucherNo: string
  voucherDate: string
  customerName: string
  amount: number
  shipDate: string
  signDate: string
  acceptDate: string
  isCrossPeriod: boolean     // auto
  crossPeriodDays: number    // auto
  adjustSuggestion: string
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

export function useD4OtherGroup(options: UseD4BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // Balance sheet date for cutoff determination
  const balanceSheetDate = computed(() => {
    const resp = allResponses.value.get('D4-balance-sheet-date')
    return resp?.remark || '2025-12-31'
  })

  // ─── D4-33 其他毛利 ────────────────────────────────────────────────

  const otherMarginRows = ref<OtherMarginRow[]>([])

  function loadOtherMarginRows(): void {
    const resp = allResponses.value.get('D4-33-rows')
    otherMarginRows.value = safeParseRows<OtherMarginRow>(resp?.remark).map(r => ({
      ...r,
      margin: calcGrossMarginRate(parseNum(r.revenue), parseNum(r.cost)),
    }))
  }

  watch(
    () => allResponses.value.get('D4-33-rows')?.remark,
    () => loadOtherMarginRows(),
    { immediate: true },
  )

  // ─── D4-34 合同测算 ────────────────────────────────────────────────

  const otherContractRows = ref<OtherContractRow[]>([])

  function loadOtherContractRows(): void {
    const resp = allResponses.value.get('D4-34-rows')
    otherContractRows.value = safeParseRows<OtherContractRow>(resp?.remark).map(r => ({
      ...r,
      diff: parseNum(r.actualRecognize) - parseNum(r.shouldRecognize),
    }))
  }

  watch(
    () => allResponses.value.get('D4-34-rows')?.remark,
    () => loadOtherContractRows(),
    { immediate: true },
  )

  // ─── D4-35 其他检查 (same as D4-14) ───────────────────────────────

  const otherCheckRows = ref<OtherCheckRow[]>([])

  function loadOtherCheckRows(): void {
    const resp = allResponses.value.get('D4-35-rows')
    otherCheckRows.value = safeParseRows<OtherCheckRow>(resp?.remark)
  }

  watch(
    () => allResponses.value.get('D4-35-rows')?.remark,
    () => loadOtherCheckRows(),
    { immediate: true },
  )

  const otherCheckAnomalyRate = computed<number>(() => {
    if (otherCheckRows.value.length === 0) return 0
    const anomalyCount = otherCheckRows.value.filter(r => r.isAnomalous).length
    return calcAnomalyRate(anomalyCount, otherCheckRows.value.length)
  })

  // ─── D4-36 其他截止 (same as D4-17/18) ────────────────────────────

  const otherCutoffRows = ref<OtherCutoffRow[]>([])

  function loadOtherCutoffRows(): void {
    const resp = allResponses.value.get('D4-36-rows')
    const bsDate = balanceSheetDate.value
    otherCutoffRows.value = safeParseRows<OtherCutoffRow>(resp?.remark).map(r => {
      const referenceDate = r.shipDate || r.signDate || r.acceptDate || r.voucherDate
      return {
        ...r,
        isCrossPeriod: isCrossPeriod(r.voucherDate, referenceDate, bsDate),
        crossPeriodDays: calcCrossPeriodDays(r.voucherDate, referenceDate),
      }
    })
  }

  watch(
    () => allResponses.value.get('D4-36-rows')?.remark,
    () => loadOtherCutoffRows(),
    { immediate: true },
  )

  const otherCutoffSummary = computed(() => {
    const crossRows = otherCutoffRows.value.filter(r => r.isCrossPeriod)
    return {
      total: otherCutoffRows.value.length,
      crossCount: crossRows.length,
      crossAmount: calcSubtotal(crossRows.map(r => parseNum(r.amount))),
      adjustAmount: calcSubtotal(crossRows.filter(r => r.adjustSuggestion).map(r => parseNum(r.amount))),
    }
  })

  // ─── Generic Row Operations ─────────────────────────────────────────

  function addRow(section: string): void {
    if (readonly.value) return
    switch (section) {
      case 'D4-33':
        otherMarginRows.value.push({
          rowId: generateRowId(), product: '', revenue: 0, cost: 0, margin: 0,
        })
        persistSection('D4-33-rows', otherMarginRows.value)
        break
      case 'D4-34':
        otherContractRows.value.push({
          rowId: generateRowId(), contractName: '', amount: 0, term: '',
          shouldRecognize: 0, actualRecognize: 0, diff: 0, remark: '',
        })
        persistSection('D4-34-rows', otherContractRows.value)
        break
      case 'D4-35':
        otherCheckRows.value.push({
          rowId: generateRowId(), voucherNo: '', voucherDate: '', customerName: '',
          amount: 0, hasContract: '', hasDelivery: '', hasInvoice: '', isAnomalous: false, remark: '',
        })
        persistSection('D4-35-rows', otherCheckRows.value)
        break
      case 'D4-36':
        otherCutoffRows.value.push({
          rowId: generateRowId(), voucherNo: '', voucherDate: '', customerName: '',
          amount: 0, shipDate: '', signDate: '', acceptDate: '',
          isCrossPeriod: false, crossPeriodDays: 0, adjustSuggestion: '', remark: '',
        })
        persistSection('D4-36-rows', otherCutoffRows.value)
        break
    }
  }

  function removeRow(section: string, rowId: string): void {
    if (readonly.value) return
    switch (section) {
      case 'D4-33':
        otherMarginRows.value = otherMarginRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-33-rows', otherMarginRows.value)
        break
      case 'D4-34':
        otherContractRows.value = otherContractRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-34-rows', otherContractRows.value)
        break
      case 'D4-35':
        otherCheckRows.value = otherCheckRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-35-rows', otherCheckRows.value)
        break
      case 'D4-36':
        otherCutoffRows.value = otherCutoffRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-36-rows', otherCutoffRows.value)
        break
    }
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
      const keys = ['D4-33-rows', 'D4-34-rows', 'D4-35-rows', 'D4-36-rows']
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
    // D4-33
    otherMarginRows,
    // D4-34
    otherContractRows,
    // D4-35
    otherCheckRows,
    otherCheckAnomalyRate,
    // D4-36
    otherCutoffRows,
    otherCutoffSummary,
    // Operations
    addRow,
    removeRow,
  }
}

export default useD4OtherGroup
