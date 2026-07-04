/**
 * useF2ImpairmentReversal — F2-49 跌价转回
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcNRV,
  calcImpairmentProvision,
  calcReversalAmount,
} from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'

export interface ImpairmentReversalRow {
  rowId: string
  itemName: string
  bookCost: number
  priorProvision: number
  sellingPrice: number
  completionCost: number
  sellingExpense: number
  currentNrv: number
  currentRequired: number
  shouldReverse: boolean
  reversalAmount: number
  reversalCap: number
  rationale: string
}

const ROWS_KEY = 'F2-49-rows'
const NOTE_KEY = 'F2-49-note'

function genId(): string {
  return `f2rev-${Date.now().toString(36)}`
}

function enrichRow(r: ImpairmentReversalRow) {
  const currentNrv = calcNRV(r.sellingPrice, r.completionCost, r.sellingExpense, 0)
  const currentRequired = calcImpairmentProvision(r.bookCost, currentNrv)
  const shouldReverse = r.priorProvision > currentRequired
  const reversalCap = r.priorProvision
  const reversalAmount = calcReversalAmount(r.priorProvision, currentRequired, reversalCap)
  const needsRationale = shouldReverse && !r.rationale.trim()
  return { ...r, currentNrv, currentRequired, shouldReverse, reversalAmount, reversalCap, needsRationale }
}

export function useF2ImpairmentReversal(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const activeSegment = ref<'prior' | 'current'>('prior')

  const rows = ref<ImpairmentReversalRow[]>([{
    rowId: genId(), itemName: '', bookCost: 0, priorProvision: 0,
    sellingPrice: 0, completionCost: 0, sellingExpense: 0,
    currentNrv: 0, currentRequired: 0, shouldReverse: false,
    reversalAmount: 0, reversalCap: 0, rationale: '',
  }])
  const auditNote = ref('')

  watch(() => allResponses.value.get(ROWS_KEY)?.remark, (v) => {
    if (!v) return
    try {
      const parsed = JSON.parse(v)
      if (Array.isArray(parsed) && parsed.length) rows.value = parsed
    } catch { /* ignore */ }
  }, { immediate: true })

  watch(() => allResponses.value.get(NOTE_KEY)?.remark, (v) => { auditNote.value = v || '' }, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichRow))

  const summary = computed(() => ({
    reverseCount: enrichedRows.value.filter((r) => r.shouldReverse).length,
    reverseTotal: calcSubtotal(enrichedRows.value.map((r) => r.reversalAmount)),
    missingRationale: enrichedRows.value.filter((r) => r.needsRationale).length,
  }))

  function persist(): void {
    allResponses.value.set(ROWS_KEY, { item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      const items = [allResponses.value.get(ROWS_KEY), allResponses.value.get(NOTE_KEY)].filter(Boolean)
      if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
    }, 2000)
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, {
      rowId: genId(), itemName: '', bookCost: 0, priorProvision: 0,
      sellingPrice: 0, completionCost: 0, sellingExpense: 0,
      currentNrv: 0, currentRequired: 0, shouldReverse: false,
      reversalAmount: 0, reversalCap: 0, rationale: '',
    }]
    persist()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateRow(rowId: string, patch: Partial<ImpairmentReversalRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, ...patch }
      if (typeof patch.bookCost === 'number' || typeof patch.priorProvision === 'number') {
        next.bookCost = parseNum(next.bookCost)
        next.priorProvision = parseNum(next.priorProvision)
      }
      return next
    })
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    persist()
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); persist() } })

  return { activeSegment, enrichedRows, summary, auditNote, addRow, removeRow, updateRow }
}

export default useF2ImpairmentReversal
