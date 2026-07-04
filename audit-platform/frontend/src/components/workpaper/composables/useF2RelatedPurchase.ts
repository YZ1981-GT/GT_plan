/**
 * useF2RelatedPurchase — F2-52 关联采购公允性分析
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcSubtotal, calcFairnessDeviation } from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'

export interface RelatedPurchaseRow {
  rowId: string
  relatedParty: string
  itemName: string
  relatedPrice: number
  comparablePrice: number
  quantity: number
  amount: number
  fairnessEval: string
  remark: string
}

const ROWS_KEY = 'F2-52-rows'
const NOTE_KEY = 'F2-52-note'

function genId(): string {
  return `f2rp-${Date.now().toString(36)}`
}

function enrichRow(r: RelatedPurchaseRow) {
  const deviation = calcFairnessDeviation(r.relatedPrice, r.comparablePrice)
  const amount = r.relatedPrice * r.quantity
  const isHighDeviation = typeof deviation === 'number' && Math.abs(deviation) > 10
  return { ...r, deviation, amount, isHighDeviation }
}

export function useF2RelatedPurchase(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const rows = ref<RelatedPurchaseRow[]>([{
    rowId: genId(), relatedParty: '', itemName: '', relatedPrice: 0,
    comparablePrice: 0, quantity: 0, amount: 0, fairnessEval: '', remark: '',
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
  const highDeviationCount = computed(() => enrichedRows.value.filter((r) => r.isHighDeviation).length)
  const totalAmount = computed(() => calcSubtotal(enrichedRows.value.map((r) => r.amount)))

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
      rowId: genId(), relatedParty: '', itemName: '', relatedPrice: 0,
      comparablePrice: 0, quantity: 0, amount: 0, fairnessEval: '', remark: '',
    }]
    persist()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateRow(rowId: string, patch: Partial<RelatedPurchaseRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.rowId === rowId ? { ...r, ...patch } : r))
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    persist()
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); persist() } })

  return { enrichedRows, highDeviationCount, totalAmount, auditNote, addRow, removeRow, updateRow }
}

export default useF2RelatedPurchase
