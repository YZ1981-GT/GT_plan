/**
 * useF3Adjustment — F3-3 调整分录（10列）
 * Spec: .kiro/specs/f3-notes-payable/ Task 6 (F3-3)
 * 比照 useD4Adjustment
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useF3FormulaEngine'
import type { ChecklistResponse } from './useF3FormData'
import type { UseF3BaseOptions } from './useF3Adjudication'

export interface F3AdjustmentRow {
  rowId: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparer: string
  remark: string
}

const STORAGE_KEY = 'F3-3-rows'
const BALANCE_TOLERANCE = 0.01

function generateRowId(): string {
  return `f3a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number): F3AdjustmentRow {
  return {
    rowId: generateRowId(),
    seq,
    entryType: 'AJE',
    date: '',
    summary: '',
    accountCode: '2201',
    accountName: '应付票据',
    debitAmount: 0,
    creditAmount: 0,
    preparer: '',
    remark: '',
  }
}

function safeParseRows(jsonStr: string | null | undefined): F3AdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyRow(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
      date: raw.date || '',
      summary: raw.summary || '',
      accountCode: raw.accountCode || '2201',
      accountName: raw.accountName || '应付票据',
      debitAmount: parseNum(raw.debitAmount),
      creditAmount: parseNum(raw.creditAmount),
      preparer: raw.preparer || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

export function useF3Adjustment(options: UseF3BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const storedData = ref<F3AdjustmentRow[]>([])

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [emptyRow(1)]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  const rows: ComputedRef<F3AdjustmentRow[]> = computed(() => storedData.value)

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => isDebitCreditBalanced(
    rows.value.map((r) => r.debitAmount),
    rows.value.map((r) => r.creditAmount),
  ))

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyRow(storedData.value.length + 1))
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || storedData.value.length <= 1) return
    const idx = storedData.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedData.value.splice(idx, 1)
    storedData.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return
    const strFields = ['entryType', 'date', 'summary', 'accountCode', 'accountName', 'preparer', 'remark']
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else if (field === 'debitAmount' || field === 'creditAmount') (row as any)[field] = parseNum(value)
    persistRows()
  }

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(storedData.value) })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items: [item] } }))
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return { rows, debitTotal, creditTotal, balanceDiff, isBalanced, addRow, removeRow, updateCell }
}

export default useF3Adjustment
