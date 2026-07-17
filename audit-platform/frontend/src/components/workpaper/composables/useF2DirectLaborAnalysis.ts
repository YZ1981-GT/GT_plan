/**
 * useF2DirectLaborAnalysis — F2-42 直接人工分析（三表联动）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  defaultLaborProductLines,
  enrichAllLaborLines,
  migrateToLaborMatrix,
  emptyLaborProductLine,
  countAbnormalUnitVariance,
  sumLaborAnnual,
  type LaborProductLine,
  type LaborMonthKey,
} from './useF2DirectLaborMatrixFormulas'

const ROWS_KEY = 'F2-42-rows'
const NOTE_KEY = 'F2-42-note'
const PROCEDURE_KEY = 'F2-42-procedure'

export function useF2DirectLaborAnalysis(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const lines = ref<LaborProductLine[]>(defaultLaborProductLines())
  const auditNote = ref('')
  const auditProcedure = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateToLaborMatrix(parsed)
        if (migrated?.length) lines.value = migrated
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
    auditProcedure.value = opts.allResponses.value.get(PROCEDURE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedLines = computed(() => enrichAllLaborLines(lines.value))

  const laborGrandTotal = computed(() => sumLaborAnnual(lines.value))

  const varianceCount = computed(() => countAbnormalUnitVariance(enrichedLines.value, 5))

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
      opts.allResponses.value.get(PROCEDURE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(lines.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function updateLine(id: string, patch: Partial<LaborProductLine>): void {
    if (readonly.value) return
    lines.value = lines.value.map((l) => (l.id === id ? { ...l, ...patch } : l))
    persist()
  }

  function updateLaborMonth(id: string, month: LaborMonthKey, value: number): void {
    if (readonly.value) return
    lines.value = lines.value.map((l) =>
      l.id === id ? { ...l, laborMonths: { ...l.laborMonths, [month]: value } } : l,
    )
    persist()
  }

  function updateOutputMonth(id: string, month: LaborMonthKey, value: number): void {
    if (readonly.value) return
    lines.value = lines.value.map((l) =>
      l.id === id ? { ...l, outputMonths: { ...l.outputMonths, [month]: value } } : l,
    )
    persist()
  }

  function addLine(): void {
    if (readonly.value) return
    lines.value = [...lines.value, emptyLaborProductLine('')]
    persist()
  }

  function removeLine(id: string): void {
    if (readonly.value || lines.value.length <= 1) return
    lines.value = lines.value.filter((l) => l.id !== id)
    persist()
  }

  function persistText(key: string, val: string, target: Ref<string>): void {
    if (readonly.value) return
    target.value = val
    opts.allResponses.value.set(key, { item_id: key, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  watch(auditNote, (val) => {
    persistText(NOTE_KEY, val, auditNote)
  })

  watch(auditProcedure, (val) => {
    persistText(PROCEDURE_KEY, val, auditProcedure)
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    enrichedLines,
    laborGrandTotal,
    varianceCount,
    auditNote,
    auditProcedure,
    updateLine,
    updateLaborMonth,
    updateOutputMonth,
    addLine,
    removeLine,
    setProcedure: (v: string) => persistText(PROCEDURE_KEY, v, auditProcedure),
  }
}

export default useF2DirectLaborAnalysis
