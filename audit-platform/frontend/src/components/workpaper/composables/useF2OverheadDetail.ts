/**
 * useF2OverheadDetail — F2-43 制造费用明细（项目×月度矩阵）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  defaultOverheadMatrix,
  enrichOverheadMatrix,
  migrateToOverheadMatrix,
  sumOverheadAnnual,
  type OverheadMatrixData,
  type OverheadItemKey,
  type OverheadMonthKey,
} from './useF2OverheadMatrixFormulas'

const ROWS_KEY = 'F2-43-rows'
const NOTE_KEY = 'F2-43-note'
const PROCEDURE_KEY = 'F2-43-procedure'

export function useF2OverheadDetail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const matrix = ref<OverheadMatrixData>(defaultOverheadMatrix())
  const auditNote = ref('')
  const auditProcedure = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateToOverheadMatrix(parsed)
        if (migrated) matrix.value = migrated
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
    auditProcedure.value = opts.allResponses.value.get(PROCEDURE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enriched = computed(() => enrichOverheadMatrix(matrix.value))

  const annualTotal = computed(() => sumOverheadAnnual(matrix.value))

  const highVarianceCount = computed(() =>
    enriched.value.rows.filter((r) => {
      const rate = r.changeRate
      return r.kind === 'item' && typeof rate === 'number' && Math.abs(rate) > 0.2
    }).length,
  )

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
      remark: JSON.stringify(matrix.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function updateMonth(rowKey: OverheadItemKey, month: OverheadMonthKey, value: number): void {
    if (readonly.value) return
    matrix.value = {
      rows: matrix.value.rows.map((r) =>
        r.key === rowKey ? { ...r, months: { ...r.months, [month]: value } } : r,
      ),
    }
    persist()
  }

  function updateRowMeta(
    rowKey: OverheadItemKey,
    patch: { priorYear?: number; changeReason?: string },
  ): void {
    if (readonly.value) return
    matrix.value = {
      rows: matrix.value.rows.map((r) => (r.key === rowKey ? { ...r, ...patch } : r)),
    }
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
    enriched,
    annualTotal,
    highVarianceCount,
    auditNote,
    auditProcedure,
    updateMonth,
    updateRowMeta,
    setProcedure: (v: string) => persistText(PROCEDURE_KEY, v, auditProcedure),
  }
}

export default useF2OverheadDetail
