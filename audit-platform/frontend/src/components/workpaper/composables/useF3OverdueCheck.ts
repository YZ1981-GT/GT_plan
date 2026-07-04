/**
 * useF3OverdueCheck — F3-5 逾期票据检查（15列）
 * Spec: .kiro/specs/f3-notes-payable/ Task 5.3
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { calcOverdueDays, calcSubtotal, parseNum } from './useF3FormulaEngine'
import type { ChecklistResponse } from './useF3FormData'
import type { UseF3BaseOptions } from './useF3Adjudication'

export interface F3OverdueNoteRow {
  rowId: string
  seq: number
  drawer: string
  noteType: string
  faceValue: number
  issueDate: string
  dueDate: string
  overdueDays: number
  overdueReason: string
  acceptor: string
  acceptorRating: string
  transferredToAp: string
  collectionStatus: string
  riskLevel: string
  auditAdvice: string
  remark: string
}

const STORAGE_KEY = 'F3-5-rows'

function suggestRisk(days: number): string {
  if (days > 90) return '高'
  if (days > 30) return '中'
  return '低'
}

function generateRowId(): string {
  return `f3o-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number): F3OverdueNoteRow {
  return {
    rowId: generateRowId(), seq, drawer: '', noteType: '银行承兑', faceValue: 0,
    issueDate: '', dueDate: '', overdueDays: 0, overdueReason: '', acceptor: '',
    acceptorRating: '', transferredToAp: '否', collectionStatus: '', riskLevel: '低',
    auditAdvice: '', remark: '',
  }
}

function computeRow(stored: F3OverdueNoteRow): F3OverdueNoteRow {
  const overdueDays = calcOverdueDays(stored.dueDate)
  const riskLevel = stored.riskLevel && stored.riskLevel !== '低' ? stored.riskLevel : suggestRisk(overdueDays)
  return { ...stored, overdueDays, riskLevel }
}

function safeParseRows(jsonStr: string | null | undefined): F3OverdueNoteRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => computeRow({
      ...emptyRow(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      drawer: raw.drawer || '',
      noteType: raw.noteType || '银行承兑',
      faceValue: parseNum(raw.faceValue ?? raw.amount),
      issueDate: raw.issueDate || '',
      dueDate: raw.dueDate || '',
      overdueReason: raw.overdueReason || '',
      acceptor: raw.acceptor || '',
      acceptorRating: raw.acceptorRating || raw.creditRating || '',
      transferredToAp: raw.transferredToAp || raw.convertedToAP || '否',
      collectionStatus: raw.collectionStatus || '',
      riskLevel: raw.riskLevel || '低',
      auditAdvice: raw.auditAdvice || raw.auditSuggestion || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

export function useF3OverdueCheck(options: UseF3BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const storedData = ref<F3OverdueNoteRow[]>([])
  const auditConclusion = ref('')

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [computeRow(emptyRow(1))]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get('F3-5-conclusion')?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  const rows: ComputedRef<F3OverdueNoteRow[]> = computed(() => storedData.value)

  const summary = computed(() => {
    const overdue = rows.value.filter((r) => r.overdueDays > 0)
    return {
      count: overdue.length,
      totalAmount: calcSubtotal(overdue.map((r) => r.faceValue)),
      highRisk: rows.value.filter((r) => r.riskLevel === '高' || r.riskLevel === '极高').length,
      transferred: rows.value.filter((r) => r.transferredToAp === '是').length,
    }
  })

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
    const strFields = ['drawer', 'noteType', 'issueDate', 'dueDate', 'overdueReason', 'acceptor',
      'acceptorRating', 'transferredToAp', 'collectionStatus', 'riskLevel', 'auditAdvice', 'remark']
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
    const items = [allResponses.value.get(STORAGE_KEY), allResponses.value.get('F3-5-conclusion')].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
  }

  watch(auditConclusion, (val) => {
    allResponses.value.set('F3-5-conclusion', { item_id: 'F3-5-conclusion', conclusion: null, remark: val })
    debounceSave()
  })

  function rowClassName({ row }: { row: F3OverdueNoteRow }): string {
    if (row.overdueDays > 90) return 'risk-high'
    if (row.overdueDays > 30) return 'risk-medium'
    return ''
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return { rows, summary, auditConclusion, addRow, removeRow, updateCell, rowClassName }
}

export default useF3OverdueCheck
