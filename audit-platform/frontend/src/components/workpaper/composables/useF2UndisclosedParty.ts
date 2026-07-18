/** F2-67 识别未披露关联方：人员身份交叉核对状态管理。 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  emptyUndisclosedPartyRow,
  enrichUndisclosedPartyRow,
  migrateUndisclosedPartyRows,
  type UndisclosedPartyRow,
} from './useF2UndisclosedPartyFormulas'

const ROWS_KEY = 'F2-67-rows'
const NOTE_KEY = 'F2-67-note'

export function useF2UndisclosedParty(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const searchQuery = ref('')
  const rows = ref<UndisclosedPartyRow[]>([emptyUndisclosedPartyRow()])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw && raw === JSON.stringify(rows.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateUndisclosedPartyRows(parsed)
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

  const enrichedRows = computed(() => rows.value.map(enrichUndisclosedPartyRow))

  const filteredRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      r.name.toLowerCase().includes(q)
      || r.identity.toLowerCase().includes(q)
      || r.note.toLowerCase().includes(q),
    )
  })

  const riskSummary = computed(() => ({
    matched: enrichedRows.value.filter((r) => r.isAbnormal).length,
    totalPurchaseAmount: enrichedRows.value.reduce(
      (sum, row) => sum + row.annualPurchaseAmount,
      0,
    ),
    total: enrichedRows.value.filter((row) => row.name.trim()).length,
  }))

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateRow(id: string, patch: Partial<UndisclosedPartyRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, emptyUndisclosedPartyRow()]
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
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
    rows,
    searchQuery,
    filteredRows,
    riskSummary,
    auditNote,
    updateRow,
    addRow,
    removeRow,
  }
}

export type { UndisclosedPartyRow } from './useF2UndisclosedPartyFormulas'

export default useF2UndisclosedParty
