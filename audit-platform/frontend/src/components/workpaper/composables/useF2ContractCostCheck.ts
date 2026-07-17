/**
 * useF2ContractCostCheck — F2-56 合同履约成本检查表
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import type { SampledVoucher, FillMode } from './useSamplingAlgorithms'
import {
  defaultContractCostCheckSheet,
  enrichCheckSamples,
  calcCheckStats,
  migrateContractCostCheckSheet,
  emptyCheckSample,
  type ContractCostCheckSheet,
  type ContractCostCheckSample,
  type ContractCostCheckSampling,
} from './useF2ContractCostCheckFormulas'

/** @deprecated 兼容 OCR / 旧引用 */
export type ContractCostCheckRow = ContractCostCheckSample & {
  voucherDate?: string
  contractNo?: string
  amount?: number
  isCorrect?: '是' | '否'
  equipmentAmt?: number
  constructionAmt?: number
  laborAmt?: number
  otherAmt?: number
  remark?: string
}

export type SamplingParams = ContractCostCheckSampling

const PARAMS_KEY = 'F2-56-params'
const ROWS_KEY = 'F2-56-rows'
const NOTE_KEY = 'F2-56-note'
const STAT_KEY = 'F2-56-stat'

export function useF2ContractCostCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<ContractCostCheckSheet>(defaultContractCostCheckSheet())
  const auditNote = ref('')

  function load(): void {
    const pRaw = readSpeRowJson(opts.allResponses.value.get(PARAMS_KEY))
    const rRaw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (rRaw || pRaw) {
      try {
        const parsed = rRaw ? JSON.parse(rRaw) : null
        const migrated = migrateContractCostCheckSheet(parsed, pRaw || undefined)
        if (migrated) sheet.value = migrated
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
    const stat = opts.allResponses.value.get(STAT_KEY)?.remark
    if (stat) sheet.value.statNote = stat
  }

  watch(
    () => [
      opts.allResponses.value.get(PARAMS_KEY)?.remark,
      opts.allResponses.value.get(ROWS_KEY)?.remark,
    ],
    load,
    { immediate: true },
  )

  const enrichedSamples = computed(() => enrichCheckSamples(sheet.value.samples))
  const enrichedRows = enrichedSamples

  const stats = computed(() => calcCheckStats(enrichedSamples.value))

  const params = computed({
    get: () => sheet.value.sampling,
    set: (v: ContractCostCheckSampling) => {
      sheet.value = { ...sheet.value, sampling: v }
      persist()
    },
  })

  const checkedTotal = computed(() => stats.value.testedAmount)
  const coverageRatio = computed(() =>
    sheet.value.sampling.populationAmount
      ? (checkedTotal.value / sheet.value.sampling.populationAmount) * 100
      : 0,
  )
  const isCoverageLow = computed(() => coverageRatio.value > 0 && coverageRatio.value < 50)
  const issueCount = computed(() => stats.value.abnormalCount)

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(PARAMS_KEY),
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
      opts.allResponses.value.get(STAT_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
    }
  }

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(PARAMS_KEY, {
      item_id: PARAMS_KEY,
      conclusion: null,
      remark: JSON.stringify(sheet.value.sampling),
    })
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(sheet.value),
    })
    opts.allResponses.value.set(STAT_KEY, {
      item_id: STAT_KEY,
      conclusion: null,
      remark: sheet.value.statNote,
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function updateSampling(patch: Partial<ContractCostCheckSampling>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      sampling: { ...sheet.value.sampling, ...patch },
    }
    persist()
  }

  function updateParams(patch: Partial<ContractCostCheckSampling>): void {
    updateSampling(patch)
  }

  function updateSample(id: string, patch: Partial<ContractCostCheckSample>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      samples: sheet.value.samples.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    }
    persist()
  }

  function updateRow(id: string, patch: Partial<ContractCostCheckRow>): void {
    const {
      voucherDate,
      contractNo,
      amount,
      isCorrect,
      remark,
      equipmentAmt,
      constructionAmt,
      laborAmt,
      otherAmt,
      ...rest
    } = patch
    void equipmentAmt
    void constructionAmt
    void laborAmt
    void otherAmt
    const mapped: Partial<ContractCostCheckSample> = { ...rest }
    if (contractNo) mapped.contractDateNo = contractNo
    if (voucherDate) mapped.allocMonth = voucherDate
    if (amount != null) mapped.voucherAmount = amount
    if (isCorrect != null) {
      mapped.isAbnormal = isCorrect === '否' ? '是' : isCorrect === '是' ? '否' : ''
    }
    if (remark) mapped.issueDesc = mapped.issueDesc ? `${mapped.issueDesc}; ${remark}` : remark
    updateSample(id, mapped)
  }

  function setStatNote(val: string): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, statNote: val }
    persist()
  }

  function addSample(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      samples: [...sheet.value.samples, emptyCheckSample()],
    }
    persist()
  }

  function addRow(): void {
    addSample()
  }

  function removeSample(id: string): void {
    if (readonly.value || sheet.value.samples.length <= 1) return
    sheet.value = {
      ...sheet.value,
      samples: sheet.value.samples.filter((s) => s.id !== id),
    }
    persist()
  }

  function removeRow(id: string): void {
    removeSample(id)
  }

  function mapVoucherToRow(v: SampledVoucher, id: string): ContractCostCheckSample {
    const debit = v.debitAmount ? parseFloat(v.debitAmount) : 0
    const credit = v.creditAmount ? parseFloat(v.creditAmount) : 0
    const amt = debit > 0 ? debit : credit
    return {
      ...emptyCheckSample(),
      id,
      projectName: v.summary || v.accountName || '',
      accountDetail: v.accountName || '1410 合同履约成本',
      voucherNo: v.voucherNo || '',
      businessContent: v.summary || '',
      voucherAmount: amt,
      allocMonth: v.voucherDate || '',
      indexRef: '抽凭',
    }
  }

  function fillFromSampling(vouchers: SampledVoucher[], fillMode: FillMode): void {
    if (readonly.value) return
    const mapped = vouchers.map((v, i) => mapVoucherToRow(v, `${Date.now()}-${i}`))
    if (fillMode === 'replace') {
      sheet.value = { ...sheet.value, samples: mapped }
    } else if (fillMode === 'merge') {
      const existingNos = new Set(sheet.value.samples.map((r) => r.voucherNo).filter(Boolean))
      sheet.value = {
        ...sheet.value,
        samples: [
          ...sheet.value.samples,
          ...mapped.filter((r) => !r.voucherNo || !existingNos.has(r.voucherNo)),
        ],
      }
    } else {
      sheet.value = { ...sheet.value, samples: [...sheet.value.samples, ...mapped] }
    }
    sheet.value = {
      ...sheet.value,
      sampling: {
        ...sheet.value.sampling,
        sampleSize: sheet.value.samples.length,
        method: '抽凭引擎',
      },
    }
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    persist()
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    sheet,
    params,
    enrichedSamples,
    enrichedRows,
    stats,
    checkedTotal,
    coverageRatio,
    isCoverageLow,
    issueCount,
    auditNote,
    updateSampling,
    updateParams,
    updateSample,
    updateRow,
    setStatNote,
    addSample,
    addRow,
    removeSample,
    removeRow,
    fillFromSampling,
  }
}

export default useF2ContractCostCheck
