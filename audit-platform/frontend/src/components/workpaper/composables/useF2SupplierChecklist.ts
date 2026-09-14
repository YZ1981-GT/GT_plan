/** F2-69 供应商核查清单状态管理。 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  emptySupplierChecklistRow,
  enrichSupplierChecklistRow,
  migrateSupplierChecklistRows,
  supplierChecklistSummary,
  type CheckMethodField,
  type SupplierChecklistRow,
} from './useF2SupplierChecklistFormulas'

const ROWS_KEY = 'F2-69-rows'
const NOTE_KEY = 'F2-69-note'

export function useF2SupplierChecklist(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const rows = ref<SupplierChecklistRow[]>([emptySupplierChecklistRow()])
  const searchQuery = ref('')
  const auditNote = ref('')

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
    }
  }

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw && raw === JSON.stringify(rows.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateSupplierChecklistRows(parsed)
        rows.value = migrated
        if (!readonly.value && JSON.stringify(parsed) !== JSON.stringify(migrated)) {
          opts.allResponses.value.set(ROWS_KEY, {
            item_id: ROWS_KEY,
            conclusion: null,
            remark: JSON.stringify(migrated),
          })
          if (debounceTimer) clearTimeout(debounceTimer)
          debounceTimer = setTimeout(() => {
            debounceTimer = null
            flushSave()
          }, 300)
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichSupplierChecklistRow))
  const filteredRows = computed(() => {
    const query = searchQuery.value.trim().toLowerCase()
    if (!query) return enrichedRows.value
    return enrichedRows.value.filter((row) =>
      row.supplierName.toLowerCase().includes(query)
      || row.selectionReason.toLowerCase().includes(query)
      || row.remark.toLowerCase().includes(query),
    )
  })
  const summary = computed(() => supplierChecklistSummary(rows.value))

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function updateRow(id: string, patch: Partial<SupplierChecklistRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((row) => row.id === id ? { ...row, ...patch } : row)
    persist()
  }

  function toggleMethod(id: string, field: CheckMethodField, checked: boolean): void {
    updateRow(id, { [field]: checked } as Pick<SupplierChecklistRow, CheckMethodField>)
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, emptySupplierChecklistRow()]
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((row) => row.id !== id)
    persist()
  }

  watch(auditNote, (value) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, {
      item_id: NOTE_KEY,
      conclusion: null,
      remark: value,
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    rows,
    searchQuery,
    enrichedRows,
    filteredRows,
    summary,
    auditNote,
    updateRow,
    toggleMethod,
    addRow,
    removeRow,
  }
}

export default useF2SupplierChecklist
