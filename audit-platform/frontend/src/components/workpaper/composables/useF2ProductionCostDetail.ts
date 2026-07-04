/**
 * useF2ProductionCostDetail — F2-41 生产成本明细表
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  newRowId,
  enrichProductionRow,
  parseRows,
  type ProductionCostRow,
} from './useF2ProductionCostFormulas'

export type ProductionSegment = 'material' | 'labor' | 'overhead'

const ROWS_KEY = 'F2-41-rows'
const NOTE_KEY = 'F2-41-note'

function emptyRow(): ProductionCostRow {
  return {
    rowId: newRowId(), productName: '',
    dmOpening: 0, dmInput: 0, dmTransfer: 0,
    dlOpening: 0, dlInput: 0, dlTransfer: 0,
    ohOpening: 0, ohInput: 0, ohTransfer: 0,
    remark: '',
  }
}

export function useF2ProductionCostDetail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const activeSegment = ref<ProductionSegment>('material')
  const rows = ref<ProductionCostRow[]>([emptyRow()])
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(ROWS_KEY))
    rows.value = parseRows(raw, () => rows.value)
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichProductionRow))

  const totals = computed(() => ({
    totalClosing: enrichedRows.value.reduce((s, r) => s + r.totalClosing, 0),
    dmClosing: enrichedRows.value.reduce((s, r) => s + r.dmClosing, 0),
    dlClosing: enrichedRows.value.reduce((s, r) => s + r.dlClosing, 0),
    ohClosing: enrichedRows.value.reduce((s, r) => s + r.ohClosing, 0),
  }))

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

  function updateRow(rowId: string, patch: Partial<ProductionCostRow>): void {
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
    activeSegment,
    enrichedRows,
    totals,
    auditNote,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useF2ProductionCostDetail
