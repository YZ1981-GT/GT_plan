/**
 * useF2LossContract — F2-58 亏损合同预计损失测算
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  isLossContract,
  calcCompletionRate,
  calcExpectedLoss,
  calcSubtotal,
} from './useF2SpecialFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export interface LossContractRow {
  id: string
  projectCode: string
  projectName: string
  estimatedTotalRevenue: number
  estimatedTotalCost: number
  recognizedRevenue: number
  priorRecognizedLoss: number
  managementProvision: number
  remark: string
}

const ROWS_KEY = 'F2-58-rows'
const NOTE_KEY = 'F2-58-note'

function emptyRow(id: string): LossContractRow {
  return {
    id, projectCode: '', projectName: '',
    estimatedTotalRevenue: 0, estimatedTotalCost: 0, recognizedRevenue: 0,
    priorRecognizedLoss: 0, managementProvision: 0, remark: '',
  }
}

function enrichRow(r: LossContractRow) {
  const isLoss = isLossContract(r.estimatedTotalRevenue, r.estimatedTotalCost)
  const lossAmount = isLoss ? Math.max(0, r.estimatedTotalCost - r.estimatedTotalRevenue) : 0
  const completionRate = calcCompletionRate(r.recognizedRevenue, r.estimatedTotalRevenue)
  const rateNum = typeof completionRate === 'number' ? completionRate : 0
  const expectedLoss = calcExpectedLoss(r.estimatedTotalRevenue, r.estimatedTotalCost, rateNum)
  const currentProvision = expectedLoss - r.priorRecognizedLoss
  const difference = currentProvision - r.managementProvision
  const needsAdjust = Math.abs(difference) > 0.01
  return {
    ...r, isLoss, lossAmount, completionRate, rateNum,
    expectedLoss, currentProvision, difference, needsAdjust,
  }
}

export function useF2LossContract(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const rows = ref<LossContractRow[]>([enrichRow(emptyRow('1'))])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as LossContractRow[]
        if (parsed.length) rows.value = parsed.map(enrichRow)
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichRow))
  const lossCount = computed(() => enrichedRows.value.filter((r) => r.isLoss).length)
  const adjustCount = computed(() => enrichedRows.value.filter((r) => r.needsAdjust).length)

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

  function updateRow(id: string, patch: Partial<LossContractRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }) : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入项目名称', '新增亏损合同', {
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
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return { enrichedRows, lossCount, adjustCount, auditNote, updateRow, addRow, removeRow }
}

export default useF2LossContract
