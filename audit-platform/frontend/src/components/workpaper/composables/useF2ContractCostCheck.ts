/**
 * useF2ContractCostCheck — F2-56 合同履约成本检查
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcSubtotal } from './useF2SpecialFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import type { SampledVoucher, FillMode } from './useSamplingAlgorithms'

export interface SamplingParams {
  populationAmount: number
  materiality: number
  tolerableMisstatement: number
  expectedMisstatement: number
  sampleSize: number
  method: string
  scope: string
}

export interface ContractCostCheckRow {
  id: string
  projectName: string
  voucherDate: string
  voucherNo: string
  contractNo: string
  amount: number
  equipmentAmt: number
  constructionAmt: number
  laborAmt: number
  otherAmt: number
  isCorrect: '是' | '否'
  issueDesc: string
  remark: string
}

const PARAMS_KEY = 'F2-56-params'
const ROWS_KEY = 'F2-56-rows'
const NOTE_KEY = 'F2-56-note'

const DEFAULT_PARAMS: SamplingParams = {
  populationAmount: 0,
  materiality: 0,
  tolerableMisstatement: 0,
  expectedMisstatement: 0,
  sampleSize: 0,
  method: '随机',
  scope: '',
}

function emptyRow(id: string): ContractCostCheckRow {
  return {
    id, projectName: '', voucherDate: '', voucherNo: '', contractNo: '',
    amount: 0, equipmentAmt: 0, constructionAmt: 0, laborAmt: 0, otherAmt: 0,
    isCorrect: '是', issueDesc: '', remark: '',
  }
}

function enrichRow(r: ContractCostCheckRow) {
  const categoryTotal = r.equipmentAmt + r.constructionAmt + r.laborAmt + r.otherAmt
  const amountMismatch = Math.abs(categoryTotal - r.amount) > 0.01 && r.amount > 0
  const hasIssue = r.isCorrect === '否' || amountMismatch
  return { ...r, categoryTotal, amountMismatch, hasIssue }
}

export function useF2ContractCostCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const params = ref<SamplingParams>({ ...DEFAULT_PARAMS })
  const rows = ref<ContractCostCheckRow[]>([enrichRow(emptyRow('1'))])
  const auditNote = ref('')

  function load(): void {
    const pRaw = readSpeRowJson(opts.allResponses.value.get(PARAMS_KEY))
    if (pRaw) {
      try { params.value = { ...DEFAULT_PARAMS, ...JSON.parse(pRaw) } } catch { /* ignore */ }
    }
    const rRaw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (rRaw) {
      try {
        const parsed = JSON.parse(rRaw) as ContractCostCheckRow[]
        if (parsed.length) rows.value = parsed.map(enrichRow)
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => [opts.allResponses.value.get(PARAMS_KEY)?.remark, opts.allResponses.value.get(ROWS_KEY)?.remark], load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichRow))
  const checkedTotal = computed(() => calcSubtotal(enrichedRows.value.map((r) => r.amount)))
  const coverageRatio = computed(() =>
    params.value.populationAmount ? (checkedTotal.value / params.value.populationAmount) * 100 : 0,
  )
  const isCoverageLow = computed(() => coverageRatio.value > 0 && coverageRatio.value < 50)
  const issueCount = computed(() => enrichedRows.value.filter((r) => r.hasIssue).length)

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(PARAMS_KEY),
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(PARAMS_KEY, {
      item_id: PARAMS_KEY, conclusion: null, remark: JSON.stringify(params.value),
    })
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateParams(patch: Partial<SamplingParams>): void {
    if (readonly.value) return
    params.value = { ...params.value, ...patch }
    persist()
  }

  function updateRow(id: string, patch: Partial<ContractCostCheckRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }) : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入项目名称', '新增检查样本', {
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

  function mapVoucherToRow(v: SampledVoucher, id: string): ContractCostCheckRow {
    const debit = v.debitAmount ? parseFloat(v.debitAmount) : 0
    const credit = v.creditAmount ? parseFloat(v.creditAmount) : 0
    const amt = debit > 0 ? debit : credit
    return enrichRow({
      ...emptyRow(id),
      projectName: v.summary || v.accountName || '',
      voucherDate: v.voucherDate || '',
      voucherNo: v.voucherNo || '',
      amount: amt,
      remark: v.remark || '来自抽凭引擎',
    })
  }

  function fillFromSampling(vouchers: SampledVoucher[], fillMode: FillMode): void {
    if (readonly.value) return
    const mapped = vouchers.map((v, i) => mapVoucherToRow(v, `${Date.now()}-${i}`))
    if (fillMode === 'replace') {
      rows.value = mapped
    } else if (fillMode === 'merge') {
      const existingNos = new Set(rows.value.map((r) => r.voucherNo).filter(Boolean))
      rows.value = [...rows.value, ...mapped.filter((r) => !r.voucherNo || !existingNos.has(r.voucherNo))]
    } else {
      rows.value = [...rows.value, ...mapped]
    }
    params.value = { ...params.value, sampleSize: rows.value.length, method: '抽凭引擎' }
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
    params, enrichedRows, checkedTotal, coverageRatio, isCoverageLow, issueCount,
    auditNote, updateParams, updateRow, addRow, removeRow, fillFromSampling,
  }
}

export default useF2ContractCostCheck
