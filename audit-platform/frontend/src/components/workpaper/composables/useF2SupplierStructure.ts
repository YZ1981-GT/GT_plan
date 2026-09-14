/** F2-68 重要供应商结构分析双区模型状态管理。 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  defaultSupplierStructureSheet,
  emptySupplierStructureRow,
  enrichSupplierStructureRows,
  migrateSupplierStructureSheet,
  supplierStructureSummary,
  type SupplierPeriod,
  type SupplierStructureRow,
  type SupplierStructureSheet,
} from './useF2SupplierStructureFormulas'

const ROWS_KEY = 'F2-68-rows'
const NOTE_KEY = 'F2-68-note'

export function useF2SupplierStructure(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const sheet = ref<SupplierStructureSheet>(defaultSupplierStructureSheet())
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
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateSupplierStructureSheet(parsed)
        sheet.value = migrated
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

  const currentRows = computed(() => enrichSupplierStructureRows(sheet.value.currentRows))
  const priorRows = computed(() => enrichSupplierStructureRows(sheet.value.priorRows))
  const currentSummary = computed(() => supplierStructureSummary(sheet.value.currentRows))
  const priorSummary = computed(() => supplierStructureSummary(sheet.value.priorRows))

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(sheet.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function mutatePeriod(
    period: SupplierPeriod,
    mutation: (rows: SupplierStructureRow[]) => SupplierStructureRow[],
  ): void {
    if (readonly.value) return
    const key = period === 'current' ? 'currentRows' : 'priorRows'
    sheet.value = { ...sheet.value, [key]: mutation(sheet.value[key]) }
    persist()
  }

  function addRow(period: SupplierPeriod): void {
    mutatePeriod(period, (rows) => [...rows, emptySupplierStructureRow()])
  }

  function removeRow(period: SupplierPeriod, id: string): void {
    const key = period === 'current' ? 'currentRows' : 'priorRows'
    if (sheet.value[key].length <= 1) return
    mutatePeriod(period, (rows) => rows.filter((row) => row.id !== id))
  }

  function updateRow(
    period: SupplierPeriod,
    id: string,
    patch: Partial<SupplierStructureRow>,
  ): void {
    mutatePeriod(period, (rows) =>
      rows.map((row) => row.id === id ? { ...row, ...patch } : row),
    )
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
    sheet,
    currentRows,
    priorRows,
    currentSummary,
    priorSummary,
    auditNote,
    addRow,
    removeRow,
    updateRow,
  }
}

export default useF2SupplierStructure
