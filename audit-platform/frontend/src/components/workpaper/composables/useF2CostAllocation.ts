/**
 * useF2CostAllocation — F2-44 生产成本分配（联动 F2-41/42/43 来源合计）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { calcSubtotal } from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  newRowId,
  enrichAllocationRow,
  parseRows,
  readSourceTotals,
  type AllocationRow,
} from './useF2ProductionCostFormulas'

const ROWS_KEY = 'F2-44-rows'
const NOTE_KEY = 'F2-44-note'

function emptyRow(): AllocationRow {
  return {
    rowId: newRowId(), productName: '',
    allocationBase: 0, materialAlloc: 0, laborAlloc: 0, overheadAlloc: 0, remark: '',
  }
}

export function useF2CostAllocation(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const rows = ref<AllocationRow[]>([emptyRow()])
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(ROWS_KEY))
    rows.value = parseRows(raw, () => rows.value)
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const sourceTotals = computed(() => {
    const map = opts.allResponses.value
    void map.get('F2-41-rows')?.remark
    void map.get('F2-42-rows')?.remark
    void map.get('F2-43-rows')?.remark
    return readSourceTotals(map)
  })

  const baseTotal = computed(() => calcSubtotal(rows.value.map((r) => r.allocationBase)))

  const enrichedRows = computed(() =>
    rows.value.map((r) => enrichAllocationRow(r, baseTotal.value, sourceTotals.value)),
  )

  const allocationMismatch = computed(() =>
    enrichedRows.value.some((r) => Math.abs(r.variance) > 0.01),
  )

  const allocGrandTotal = computed(() =>
    calcSubtotal(enrichedRows.value.map((r) => r.totalAlloc)),
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

  function updateRow(rowId: string, patch: Partial<AllocationRow>): void {
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
    sourceTotals,
    allocGrandTotal,
    allocationMismatch,
    auditNote,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useF2CostAllocation
