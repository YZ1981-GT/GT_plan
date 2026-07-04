/**
 * useF3InterestCalc — F3-4 带息票据利息测算（13列）
 * Spec: .kiro/specs/f3-notes-payable/ Task 5.2
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcInterest, calcAccruedDays, calcTermDays, calcSubtotal } from './useF3FormulaEngine'
import type { ChecklistResponse } from './useF3FormData'
import type { UseF3BaseOptions } from './useF3Adjudication'

export interface F3InterestCalcRow {
  rowId: string
  seq: number
  drawer: string
  faceValue: number
  interestRate: number
  issueDate: string
  dueDate: string
  termDays: number
  interestStart: string
  interestEnd: string
  accruedDays: number
  payableInterest: number
  bookInterest: number
  variance: number
}

export interface F3NoteOcrFields {
  noteNo?: string
  drawer?: string
  acceptor?: string
  faceValue?: number | string
  interestRate?: number | string
  issueDate?: string
  dueDate?: string
  interestStart?: string
  interestEnd?: string
}

const STORAGE_KEY = 'F3-4-rows'
const VARIANCE_WARN = 100

function generateRowId(): string {
  return `f3i-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number): F3InterestCalcRow {
  return {
    rowId: generateRowId(), seq, drawer: '', faceValue: 0, interestRate: 0,
    issueDate: '', dueDate: '', termDays: 0, interestStart: '', interestEnd: '',
    accruedDays: 0, payableInterest: 0, bookInterest: 0, variance: 0,
  }
}

function computeRow(stored: Omit<F3InterestCalcRow, 'termDays' | 'accruedDays' | 'payableInterest' | 'variance'>): F3InterestCalcRow {
  const termDays = stored.termDays > 0 ? stored.termDays : calcTermDays(stored.issueDate, stored.dueDate)
  const accruedDays = calcAccruedDays(stored.interestStart, stored.interestEnd)
  const payableInterest = calcInterest(stored.faceValue, stored.interestRate, accruedDays)
  const variance = payableInterest - stored.bookInterest
  return { ...stored, termDays, accruedDays, payableInterest, variance }
}

function safeParseRows(jsonStr: string | null | undefined): F3InterestCalcRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => computeRow({
      ...emptyRow(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      drawer: raw.drawer || '',
      faceValue: parseNum(raw.faceValue ?? raw.principal),
      interestRate: parseNum(raw.interestRate ?? raw.rate),
      issueDate: raw.issueDate || '',
      dueDate: raw.dueDate || '',
      termDays: parseNum(raw.termDays),
      interestStart: raw.interestStart || raw.accrualStart || '',
      interestEnd: raw.interestEnd || raw.accrualEnd || '',
      bookInterest: parseNum(raw.bookInterest ?? raw.companyInterest),
    }))
  } catch {
    return []
  }
}

export function useF3InterestCalc(options: UseF3BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const storedData = ref<F3InterestCalcRow[]>([])
  const auditConclusion = ref('')

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [computeRow(emptyRow(1))]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get('F3-4-conclusion')?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  const rows: ComputedRef<F3InterestCalcRow[]> = computed(() => storedData.value)

  const subtotalRow = computed(() => computeRow({
    ...emptyRow(0),
    rowId: 'subtotal',
    drawer: '合计',
    faceValue: calcSubtotal(rows.value.map((r) => r.faceValue)),
    bookInterest: calcSubtotal(rows.value.map((r) => r.bookInterest)),
  }))

  const totals = computed(() => ({
    faceValue: subtotalRow.value.faceValue,
    payableInterest: calcSubtotal(rows.value.map((r) => r.payableInterest)),
    bookInterest: subtotalRow.value.bookInterest,
    variance: calcSubtotal(rows.value.map((r) => r.variance)),
  }))

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(computeRow(emptyRow(storedData.value.length + 1)))
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
    const strFields = ['drawer', 'issueDate', 'dueDate', 'interestStart', 'interestEnd']
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    const idx = storedData.value.indexOf(row)
    storedData.value[idx] = computeRow(row)
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
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get('F3-4-conclusion'),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
  }

  watch(auditConclusion, (val) => {
    allResponses.value.set('F3-4-conclusion', { item_id: 'F3-4-conclusion', conclusion: null, remark: val })
    debounceSave()
  })

  function rowClassName({ row }: { row: F3InterestCalcRow }): string {
    return Math.abs(row.variance) > VARIANCE_WARN ? 'variance-warn' : ''
  }

  function mergeOcrFields(rowId: string, fields: F3NoteOcrFields, overwrite = false): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return

    const setIf = (field: keyof F3InterestCalcRow, val: unknown): void => {
      if (val == null || val === '') return
      const cur = (row as any)[field]
      if (!overwrite && cur && cur !== 0 && cur !== '') return
      if (field === 'faceValue' || field === 'interestRate') (row as any)[field] = parseNum(val)
      else (row as any)[field] = String(val)
    }

    setIf('drawer', fields.drawer)
    setIf('faceValue', fields.faceValue)
    setIf('interestRate', fields.interestRate)
    setIf('issueDate', fields.issueDate)
    setIf('dueDate', fields.dueDate)
    setIf('interestStart', fields.interestStart)
    setIf('interestEnd', fields.interestEnd)

    const idx = storedData.value.indexOf(row)
    storedData.value[idx] = computeRow(row)
    persistRows()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return { rows, subtotalRow, totals, auditConclusion, addRow, removeRow, updateCell, rowClassName, mergeOcrFields, varianceWarn: VARIANCE_WARN }
}

export default useF3InterestCalc
