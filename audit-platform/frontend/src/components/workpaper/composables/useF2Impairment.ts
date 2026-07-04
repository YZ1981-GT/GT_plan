/**
 * useF2Impairment — F2-57 合同履约成本减值准备测算
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcCompletionRate,
  calcRemainingCost,
  calcRecoverableAmount,
  calcImpairment,
  calcSubtotal,
} from './useF2SpecialFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  debouncedPublishF2SpeDisclosureNote,
  publishF2SpeSubstantiveAdjudicated,
} from './useF2SpeEventBus'

export interface ImpairmentRow {
  id: string
  projectCode: string
  projectName: string
  estimatedTotalRevenue: number
  recognizedRevenue: number
  estimatedTotalCost: number
  incurredCost: number
  bookValue: number
  managementProvision: number
  remark: string
}

const ROWS_KEY = 'F2-57-rows'
const NOTE_KEY = 'F2-57-note'

function emptyRow(id: string): ImpairmentRow {
  return {
    id, projectCode: '', projectName: '',
    estimatedTotalRevenue: 0, recognizedRevenue: 0,
    estimatedTotalCost: 0, incurredCost: 0,
    bookValue: 0, managementProvision: 0, remark: '',
  }
}

function enrichRow(r: ImpairmentRow) {
  const completionRate = calcCompletionRate(r.recognizedRevenue, r.estimatedTotalRevenue)
  const rateNum = typeof completionRate === 'number' ? completionRate : 0
  const remainingCost = calcRemainingCost(r.estimatedTotalCost, r.incurredCost)
  const recoverableAmount = calcRecoverableAmount(
    r.recognizedRevenue, r.estimatedTotalRevenue, r.estimatedTotalCost,
  )
  const impairmentAmount = calcImpairment(r.bookValue, recoverableAmount)
  const difference = impairmentAmount - r.managementProvision
  const hasDifference = Math.abs(difference) > 0.01
  return {
    ...r, completionRate, rateNum, remainingCost, recoverableAmount,
    impairmentAmount, difference, hasDifference,
  }
}

export function useF2Impairment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let adjudicatedTimer: ReturnType<typeof setTimeout> | null = null
  const rows = ref<ImpairmentRow[]>([enrichRow(emptyRow('1'))])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as ImpairmentRow[]
        if (parsed.length) rows.value = parsed.map(enrichRow)
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichRow))
  const impairmentTotal = computed(() =>
    calcSubtotal(enrichedRows.value.map((r) => r.impairmentAmount)),
  )
  const diffCount = computed(() => enrichedRows.value.filter((r) => r.hasDifference).length)

  function flushSave(): void {
    const items = [opts.allResponses.value.get(ROWS_KEY), opts.allResponses.value.get(NOTE_KEY)].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateRow(id: string, patch: Partial<ImpairmentRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }) : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入项目名称', '新增减值测算', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      rows.value = [...rows.value, enrichRow({ ...emptyRow(String(Date.now())), projectName: value })]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debouncedPublishF2SpeDisclosureNote('impairment', val)
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  watch(
    impairmentTotal,
    (amount) => {
      if (adjudicatedTimer) clearTimeout(adjudicatedTimer)
      adjudicatedTimer = setTimeout(() => {
        adjudicatedTimer = null
        publishF2SpeSubstantiveAdjudicated({
          wpCode: 'F2-special',
          accountCode: '1405',
          impairmentAmount: amount,
        })
      }, 2000)
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
    if (adjudicatedTimer) clearTimeout(adjudicatedTimer)
  })

  return { enrichedRows, impairmentTotal, diffCount, auditNote, updateRow, addRow, removeRow }
}

export default useF2Impairment
