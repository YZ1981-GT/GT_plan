/**
 * useF2DirectLaborAnalysis — F2-42 直接人工分析表
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { calcSubtotal } from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  newRowId,
  enrichLaborRow,
  parseRows,
  type DirectLaborRow,
} from './useF2ProductionCostFormulas'

const ROWS_KEY = 'F2-42-rows'
const NOTE_KEY = 'F2-42-note'

function emptyRow(): DirectLaborRow {
  return {
    rowId: newRowId(), department: '', jobType: '',
    headcount: 0, hours: 0, wageRate: 0, actualLabor: 0, remark: '',
  }
}

export function useF2DirectLaborAnalysis(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const rows = ref<DirectLaborRow[]>([emptyRow()])
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(ROWS_KEY))
    rows.value = parseRows(raw, () => rows.value)
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const laborGrandTotal = computed(() =>
    calcSubtotal(rows.value.map((r) => r.headcount * r.hours * r.wageRate)),
  )

  const enrichedRows = computed(() =>
    rows.value.map((r) => enrichLaborRow(r, laborGrandTotal.value)),
  )

  const varianceCount = computed(() =>
    enrichedRows.value.filter((r) =>
      typeof r.varianceRate === 'number' && Math.abs(r.varianceRate) > 0.05,
    ).length,
  )

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateRow(rowId: string, patch: Partial<DirectLaborRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.rowId === rowId ? { ...r, ...patch } : r))
    persist()
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, emptyRow()]
    persist()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
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
    enrichedRows,
    laborGrandTotal,
    varianceCount,
    auditNote,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useF2DirectLaborAnalysis
