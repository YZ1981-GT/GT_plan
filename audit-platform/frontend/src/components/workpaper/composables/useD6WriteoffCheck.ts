/**
 * useD6WriteoffCheck — D6-9 减值准备转回核销检查（双段，简化版）
 *
 * reversalRows: D6-9-reversal-rows
 * writeoffRows: D6-9-writeoff-rows
 * auditNotes: D6-9-note-explanation / D6-9-note-conclusion
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum } from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'

export interface D6ReversalRow {
  rowId: string
  customerName: string
  reason: string
  recoveryMethod: string
  originalBasis: string
  reversalAmount: number
  priorProvisionAmount: number
  reasonabilityAnalysis: string
  indexRef: string
}

export interface D6WriteoffRow {
  rowId: string
  customerName: string
  writeoffAmount: number
  writeoffReason: string
  writeoffProcedure: string
  isRelatedParty: string
  reasonabilityAnalysis: string
  indexRef: string
  remark: string
}

export const RECOVERY_METHODS = [
  '现金收回', '银行转账', '票据兑现', '以物抵债', '债务重组', '其他',
] as const

export const RELATED_PARTY_OPTIONS = ['是', '否'] as const

export interface UseD6WriteoffCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}

const ITEM_ID_REVERSAL = 'D6-9-reversal-rows'
const ITEM_ID_WRITEOFF = 'D6-9-writeoff-rows'

function generateRowId(): string {
  return `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function parseReversalRows(jsonStr: string | null | undefined): D6ReversalRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      customerName: raw.customerName || '',
      reason: raw.reason || '',
      recoveryMethod: raw.recoveryMethod || '',
      originalBasis: raw.originalBasis || '',
      reversalAmount: parseNum(raw.reversalAmount),
      priorProvisionAmount: parseNum(raw.priorProvisionAmount),
      reasonabilityAnalysis: raw.reasonabilityAnalysis || '',
      indexRef: raw.indexRef || '',
    }))
  } catch {
    return []
  }
}

function parseWriteoffRows(jsonStr: string | null | undefined): D6WriteoffRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      customerName: raw.customerName || '',
      writeoffAmount: parseNum(raw.writeoffAmount),
      writeoffReason: raw.writeoffReason || '',
      writeoffProcedure: raw.writeoffProcedure || '',
      isRelatedParty: raw.isRelatedParty || '否',
      reasonabilityAnalysis: raw.reasonabilityAnalysis || '',
      indexRef: raw.indexRef || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

function createEmptyReversalRow(): D6ReversalRow {
  return {
    rowId: generateRowId(),
    customerName: '',
    reason: '',
    recoveryMethod: '',
    originalBasis: '',
    reversalAmount: 0,
    priorProvisionAmount: 0,
    reasonabilityAnalysis: '',
    indexRef: '',
  }
}

function createEmptyWriteoffRow(): D6WriteoffRow {
  return {
    rowId: generateRowId(),
    customerName: '',
    writeoffAmount: 0,
    writeoffReason: '',
    writeoffProcedure: '',
    isRelatedParty: '否',
    reasonabilityAnalysis: '',
    indexRef: '',
    remark: '',
  }
}

export function useD6WriteoffCheck(options: UseD6WriteoffCheckOptions) {
  const { allResponses, debouncedSave } = options

  const reversalRows = ref<D6ReversalRow[]>([])
  const writeoffRows = ref<D6WriteoffRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_REVERSAL)?.remark,
    (jsonStr) => { reversalRows.value = parseReversalRows(jsonStr) },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_ID_WRITEOFF)?.remark,
    (jsonStr) => { writeoffRows.value = parseWriteoffRows(jsonStr) },
    { immediate: true },
  )

  function persistReversal(): void {
    debouncedSave(ITEM_ID_REVERSAL, { remark: JSON.stringify(reversalRows.value) })
  }

  function persistWriteoff(): void {
    debouncedSave(ITEM_ID_WRITEOFF, { remark: JSON.stringify(writeoffRows.value) })
  }

  const reversalTotal: ComputedRef<number> = computed(() =>
    reversalRows.value.reduce((sum, r) => sum + r.reversalAmount, 0),
  )

  const writeoffTotal: ComputedRef<number> = computed(() =>
    writeoffRows.value.reduce((sum, r) => sum + r.writeoffAmount, 0),
  )

  function addReversalRow(): void {
    reversalRows.value = [...reversalRows.value, createEmptyReversalRow()]
    persistReversal()
  }

  function addWriteoffRow(): void {
    writeoffRows.value = [...writeoffRows.value, createEmptyWriteoffRow()]
    persistWriteoff()
  }

  function removeReversalRow(rowId: string): void {
    reversalRows.value = reversalRows.value.filter(r => r.rowId !== rowId)
    persistReversal()
  }

  function removeWriteoffRow(rowId: string): void {
    writeoffRows.value = writeoffRows.value.filter(r => r.rowId !== rowId)
    persistWriteoff()
  }

  function updateReversalCell(rowId: string, field: string, value: any): void {
    const NUMERIC = ['reversalAmount', 'priorProvisionAmount']
    reversalRows.value = reversalRows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (NUMERIC.includes(field)) {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return updated
    })
    persistReversal()
  }

  function updateWriteoffCell(rowId: string, field: string, value: any): void {
    const NUMERIC = ['writeoffAmount']
    writeoffRows.value = writeoffRows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (NUMERIC.includes(field)) {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return updated
    })
    persistWriteoff()
  }

  const auditNotes = ref({ explanation: '', conclusion: '' })

  watch(
    () => allResponses.value.get('D6-9-note-explanation')?.remark,
    (v) => { auditNotes.value.explanation = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get('D6-9-note-conclusion')?.remark,
    (v) => { auditNotes.value.conclusion = v || '' },
    { immediate: true },
  )
  watch(
    () => auditNotes.value.explanation,
    (v) => debouncedSave('D6-9-note-explanation', { remark: v }),
  )
  watch(
    () => auditNotes.value.conclusion,
    (v) => debouncedSave('D6-9-note-conclusion', { remark: v }),
  )

  return {
    reversalRows,
    writeoffRows,
    reversalTotal,
    writeoffTotal,
    addReversalRow,
    addWriteoffRow,
    removeReversalRow,
    removeWriteoffRow,
    updateReversalCell,
    updateWriteoffCell,
    auditNotes,
  }
}

export default useD6WriteoffCheck
