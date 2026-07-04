/**
 * useF2ImpairmentTest — F2-47 跌价准备 NRV 测试
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcNRV,
  calcImpairmentProvision,
} from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'

export interface ImpairmentTestRow {
  rowId: string
  seq: number
  itemName: string
  qty: number
  unitCost: number
  bookCost: number
  sellingPrice: number
  completionCost: number
  sellingExpense: number
  tax: number
  nrv: number
  requiredProvision: number
  existingProvision: number
  additionalProvision: number
  reversal: number
  enterpriseDiff: number
  conclusion: string
}

const ROWS_KEY = 'F2-47-rows'
const PARAMS_KEY = 'F2-47-sampling'
const CONCLUSION_KEY = 'F2-47-conclusion'

function genId(): string {
  return `f2imp-${Date.now().toString(36)}`
}

function emptyRow(seq: number): ImpairmentTestRow {
  return {
    rowId: genId(),
    seq,
    itemName: '',
    qty: 0,
    unitCost: 0,
    bookCost: 0,
    sellingPrice: 0,
    completionCost: 0,
    sellingExpense: 0,
    tax: 0,
    nrv: 0,
    requiredProvision: 0,
    existingProvision: 0,
    additionalProvision: 0,
    reversal: 0,
    enterpriseDiff: 0,
    conclusion: '',
  }
}

function enrichRow(r: ImpairmentTestRow): ImpairmentTestRow {
  const bookCost = r.qty * r.unitCost
  const nrv = calcNRV(r.sellingPrice, r.completionCost, r.sellingExpense, r.tax)
  const requiredProvision = calcImpairmentProvision(bookCost, nrv)
  const additionalProvision = Math.max(0, requiredProvision - r.existingProvision)
  const reversal = Math.max(0, r.existingProvision - requiredProvision)
  const enterpriseDiff = requiredProvision - r.existingProvision
  return {
    ...r,
    bookCost,
    nrv,
    requiredProvision,
    additionalProvision,
    reversal,
    enterpriseDiff,
  }
}

export function useF2ImpairmentTest(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const activeSegment = ref<'basic' | 'nrv' | 'conclusion'>('basic')

  const rows = ref<ImpairmentTestRow[]>([emptyRow(1)])
  const testConclusion = ref('')
  const samplingNote = ref('')

  watch(() => allResponses.value.get(ROWS_KEY)?.remark, (v) => {
    if (!v) return
    try {
      const parsed = JSON.parse(v)
      if (Array.isArray(parsed) && parsed.length) rows.value = parsed
    } catch { /* ignore */ }
  }, { immediate: true })

  watch(() => allResponses.value.get(CONCLUSION_KEY)?.remark, (v) => { testConclusion.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(PARAMS_KEY)?.remark, (v) => { samplingNote.value = v || '' }, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichRow))

  const totalSummary = computed(() => ({
    bookCost: calcSubtotal(enrichedRows.value.map((r) => r.bookCost)),
    nrv: calcSubtotal(enrichedRows.value.map((r) => r.nrv)),
    requiredProvision: calcSubtotal(enrichedRows.value.map((r) => r.requiredProvision)),
    existingProvision: calcSubtotal(enrichedRows.value.map((r) => r.existingProvision)),
    netDiff: calcSubtotal(enrichedRows.value.map((r) => r.enterpriseDiff)),
  }))

  const needsConclusionCount = computed(() =>
    enrichedRows.value.filter((r) => r.requiredProvision > 0 && !r.conclusion.trim()).length,
  )

  function flushSave(): void {
    const items = [
      allResponses.value.get(ROWS_KEY),
      allResponses.value.get(PARAMS_KEY),
      allResponses.value.get(CONCLUSION_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function publishImpairmentCalculated(): void {
    const total = totalSummary.value.requiredProvision
    try {
      window.dispatchEvent(new CustomEvent('impairment:calculated', {
        detail: {
          wpCode: 'F2',
          sheetCode: 'F2-47',
          totalRequiredProvision: total,
          rows: enrichedRows.value.map((r) => ({
            itemName: r.itemName,
            requiredProvision: r.requiredProvision,
          })),
        },
      }))
    } catch { /* silent */ }
  }

  function persist(): void {
    allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(rows.value),
    })
    debounceSave()
    publishImpairmentCalculated()
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, emptyRow(rows.value.length + 1)]
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.rowId !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function updateRow(id: string, patch: Partial<ImpairmentTestRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.rowId !== id) return r
      const next = { ...r, ...patch }
      if (patch.qty !== undefined || patch.unitCost !== undefined) {
        next.qty = parseNum(next.qty)
        next.unitCost = parseNum(next.unitCost)
      }
      return next
    })
    persist()
  }

  watch(testConclusion, (val) => {
    if (readonly.value) return
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  watch(samplingNote, (val) => {
    if (readonly.value) return
    allResponses.value.set(PARAMS_KEY, { item_id: PARAMS_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  return {
    activeSegment,
    enrichedRows,
    totalSummary,
    needsConclusionCount,
    testConclusion,
    samplingNote,
    addRow,
    removeRow,
    updateRow,
    publishImpairmentCalculated,
  }
}

export default useF2ImpairmentTest
