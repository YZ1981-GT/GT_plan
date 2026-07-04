/**
 * useF2OverheadDetail — F2-43 制造费用明细表
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { calcSubtotal } from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  newRowId,
  enrichOverheadRow,
  parseRows,
  type OverheadRow,
} from './useF2ProductionCostFormulas'

const ROWS_KEY = 'F2-43-rows'
const NOTE_KEY = 'F2-43-note'

function emptyRow(): OverheadRow {
  return {
    rowId: newRowId(), costItem: '',
    budgetAmt: 0, actualAmt: 0, allocatedAmt: 0, remark: '',
  }
}

export function useF2OverheadDetail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const rows = ref<OverheadRow[]>([emptyRow()])
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(ROWS_KEY))
    rows.value = parseRows(raw, () => rows.value)
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichOverheadRow))

  const totals = computed(() => ({
    budget: calcSubtotal(rows.value.map((r) => r.budgetAmt)),
    actual: calcSubtotal(rows.value.map((r) => r.actualAmt)),
    allocated: calcSubtotal(rows.value.map((r) => r.allocatedAmt)),
  }))

  const mismatchCount = computed(() =>
    enrichedRows.value.filter((r) => r.allocMismatch).length,
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

  function updateRow(rowId: string, patch: Partial<OverheadRow>): void {
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
    totals,
    mismatchCount,
    auditNote,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useF2OverheadDetail
