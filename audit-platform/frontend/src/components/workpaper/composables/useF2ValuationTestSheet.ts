/**
 * useF2ValuationTestSheet — F2-38/39/40 计价测试基座（各 sheet 薄封装）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import type { SampledVoucher, FillMode } from './useSamplingAlgorithms'
import {
  emptyValuationTestRow,
  enrichValuationTestRow,
  calcValuationTestTotals,
  countExceeding,
  type ValuationTestRow,
  type ValuationTestMethod,
  type SamplingParams,
} from './useF2ValuationTestFormulas'

export interface ValuationTestSheetDef {
  sheetCode: 'F2-38' | 'F2-39' | 'F2-40'
  method: ValuationTestMethod
  thresholdRate: number
}

export function useF2ValuationTestSheet(
  def: ValuationTestSheetDef,
  opts: {
    allResponses: Ref<Map<string, ChecklistResponse>>
    isReadonly?: Ref<boolean>
  },
) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const rowsKey = `${def.sheetCode}-rows`
  const paramsKey = `${def.sheetCode}-sampling`
  const conclusionKey = `${def.sheetCode}-conclusion`

  const rows = ref<ValuationTestRow[]>([emptyValuationTestRow(1)])
  const samplingParams = ref<SamplingParams>({
    population: '', sampleSize: 0, method: '', confidence: '95%', tolerableError: '5%', conclusion: '',
  })
  const testConclusion = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(rowsKey))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed) && parsed.length) rows.value = parsed
      } catch { /* ignore */ }
    }
    const sp = readValRowJson(opts.allResponses.value.get(paramsKey))
    if (sp) {
      try { samplingParams.value = { ...samplingParams.value, ...JSON.parse(sp) } } catch { /* ignore */ }
    }
    testConclusion.value = opts.allResponses.value.get(conclusionKey)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(rowsKey)?.remark, load, { immediate: true })

  const enrichedRows = computed(() =>
    rows.value.map((r) => enrichValuationTestRow(r, def.method)),
  )

  const exceedCount = computed(() => countExceeding(enrichedRows.value, def.thresholdRate))
  const totals = computed(() => calcValuationTestTotals(enrichedRows.value))

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(rowsKey),
      opts.allResponses.value.get(paramsKey),
      opts.allResponses.value.get(conclusionKey),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(rowsKey, { item_id: rowsKey, conclusion: null, remark: JSON.stringify(rows.value) })
    opts.allResponses.value.set(paramsKey, { item_id: paramsKey, conclusion: null, remark: JSON.stringify(samplingParams.value) })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
    try {
      window.dispatchEvent(new CustomEvent('valuation:tested', {
        detail: { wpCode: 'F2', sheetCode: def.sheetCode, exceedCount: exceedCount.value },
      }))
    } catch { /* silent */ }
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, emptyValuationTestRow(rows.value.length + 1)]
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.rowId !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function updateRow(id: string, patch: Partial<ValuationTestRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.rowId === id ? { ...r, ...patch } : r))
    persist()
  }

  function mapVoucherToRow(v: SampledVoucher, seq: number): ValuationTestRow {
    const debit = v.debitAmount ? parseFloat(v.debitAmount) : 0
    const credit = v.creditAmount ? parseFloat(v.creditAmount) : 0
    const amt = debit > 0 ? debit : credit
    const row = emptyValuationTestRow(seq)
    row.voucherNo = v.voucherNo || ''
    row.itemName = v.summary || ''
    row.inboundAmt = amt
    row.bookIssueAmt = amt
    return row
  }

  function fillFromSampling(vouchers: SampledVoucher[], fillMode: FillMode): void {
    if (readonly.value) return
    const mapped = vouchers.map((v, i) => mapVoucherToRow(v, i + 1))
    if (fillMode === 'replace') {
      rows.value = mapped.map((r, i) => ({ ...r, seq: i + 1 }))
    } else if (fillMode === 'merge') {
      const existingNos = new Set(rows.value.map((r) => r.voucherNo).filter(Boolean))
      const newRows = mapped.filter((r) => !r.voucherNo || !existingNos.has(r.voucherNo))
      const startSeq = rows.value.length
      newRows.forEach((r, i) => { r.seq = startSeq + i + 1 })
      rows.value = [...rows.value, ...newRows]
    } else {
      const startSeq = rows.value.length
      mapped.forEach((r, i) => { r.seq = startSeq + i + 1 })
      rows.value = [...rows.value, ...mapped]
    }
    samplingParams.value = { ...samplingParams.value, sampleSize: rows.value.length, method: '抽凭引擎' }
    persist()
  }

  watch(testConclusion, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(conclusionKey, { item_id: conclusionKey, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  watch(samplingParams, () => {
    if (readonly.value) return
    opts.allResponses.value.set(paramsKey, { item_id: paramsKey, conclusion: null, remark: JSON.stringify(samplingParams.value) })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }, { deep: true })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return {
    sheetCode: def.sheetCode,
    thresholdRate: def.thresholdRate,
    method: def.method,
    enrichedRows,
    samplingParams,
    testConclusion,
    exceedCount,
    totals,
    addRow,
    removeRow,
    updateRow,
    fillFromSampling,
  }
}

export function useF2WeightedAvgTest(opts: Parameters<typeof useF2ValuationTestSheet>[1]) {
  return useF2ValuationTestSheet({ sheetCode: 'F2-38', method: 'weighted-avg', thresholdRate: 1 }, opts)
}

export function useF2FifoTest(opts: Parameters<typeof useF2ValuationTestSheet>[1]) {
  return useF2ValuationTestSheet({ sheetCode: 'F2-39', method: 'fifo', thresholdRate: 1 }, opts)
}

export function useF2StandardCostTest(opts: Parameters<typeof useF2ValuationTestSheet>[1]) {
  return useF2ValuationTestSheet({ sheetCode: 'F2-40', method: 'standard-cost', thresholdRate: 5 }, opts)
}

export default useF2ValuationTestSheet
