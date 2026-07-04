/**
 * useF2InspectionCheck — F2-33/34/35 检查表基座
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { calcSubtotal } from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  emptyInspectionRow,
  calcInspectionCoverage,
  readBookTotal,
  type InspectionCheckRow,
} from './useF2InspectionCheckFormulas'
import type { SampledVoucher, FillMode, SamplingMethod } from './useSamplingAlgorithms'

export interface InspectionCheckDef {
  sheetCode: 'F2-33' | 'F2-34' | 'F2-35'
  title: string
  partyLabel: string
  showDaysOutstanding?: boolean
  /** 抽凭引擎：true=借方金额优先(F2-33)，false=贷方(F2-34) */
  samplingPreferDebit?: boolean
}

export function useF2InspectionCheck(
  def: InspectionCheckDef,
  opts: {
    allResponses: Ref<Map<string, ChecklistResponse>>
    isReadonly?: Ref<boolean>
  },
) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const dataKey = `${def.sheetCode}-rows`
  const rows = ref<InspectionCheckRow[]>([emptyInspectionRow(1)])
  const bookTotal = ref(0)
  const auditNote = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(dataKey))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed) && parsed.length) rows.value = parsed
      } catch { /* ignore */ }
    }
    bookTotal.value = readBookTotal(opts.allResponses.value, def.sheetCode)
    auditNote.value = opts.allResponses.value.get(`${def.sheetCode}-note`)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(dataKey)?.remark, load, { immediate: true })

  const checkedTotal = computed(() => calcSubtotal(rows.value.map((r) => r.amount)))
  const coverageRatio = computed(() => calcInspectionCoverage(checkedTotal.value, bookTotal.value))
  const isCoverageLow = computed(() => coverageRatio.value > 0 && coverageRatio.value < 50)

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(dataKey),
      opts.allResponses.value.get(`${def.sheetCode}-book-total`),
      opts.allResponses.value.get(`${def.sheetCode}-note`),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(dataKey, { item_id: dataKey, conclusion: null, remark: JSON.stringify(rows.value) })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateBookTotal(v: number): void {
    if (readonly.value) return
    bookTotal.value = v
    opts.allResponses.value.set(`${def.sheetCode}-book-total`, {
      item_id: `${def.sheetCode}-book-total`, conclusion: null, remark: String(v),
    })
    persist()
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, emptyInspectionRow(rows.value.length + 1)]
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function updateRow(id: string, patch: Partial<InspectionCheckRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  function mapVoucherToRow(v: SampledVoucher, seq: number, method?: SamplingMethod): InspectionCheckRow {
    const debit = v.debitAmount ? parseFloat(v.debitAmount) : 0
    const credit = v.creditAmount ? parseFloat(v.creditAmount) : 0
    const preferDebit = def.samplingPreferDebit !== false
    const amount = preferDebit ? (debit > 0 ? debit : credit) : (credit > 0 ? credit : debit)
    const algo = method ?? (v.remark?.includes('stratified') ? 'stratified' : 'random')
    return {
      ...emptyInspectionRow(seq, `来自抽凭引擎 ${algo}`),
      party: v.counterpartAccount || v.accountName || '',
      docNo: '',
      itemName: v.summary || '',
      amount,
      voucherNo: v.voucherNo || '',
      remark: v.remark || '',
    }
  }

  function fillFromSampling(vouchers: SampledVoucher[], fillMode: FillMode, method?: SamplingMethod): void {
    if (readonly.value || def.samplingPreferDebit === undefined) return
    const mapped = vouchers.map((v, i) => mapVoucherToRow(v, i + 1, method))

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
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(`${def.sheetCode}-note`, { item_id: `${def.sheetCode}-note`, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return {
    ...def,
    rows,
    bookTotal,
    checkedTotal,
    coverageRatio,
    isCoverageLow,
    auditNote,
    addRow,
    removeRow,
    updateRow,
    updateBookTotal,
    fillFromSampling,
  }
}

export function useF2PurchaseInboundCheck(opts: Parameters<typeof useF2InspectionCheck>[1]) {
  return useF2InspectionCheck({
    sheetCode: 'F2-33', title: '采购入库检查', partyLabel: '供应商', samplingPreferDebit: true,
  }, opts)
}

export function useF2MaterialUsageCheck(opts: Parameters<typeof useF2InspectionCheck>[1]) {
  return useF2InspectionCheck({
    sheetCode: 'F2-34', title: '材料领用检查', partyLabel: '领用部门', samplingPreferDebit: false,
  }, opts)
}

export function useF2SubcontractCheck(opts: Parameters<typeof useF2InspectionCheck>[1]) {
  return useF2InspectionCheck({
    sheetCode: 'F2-35', title: '委托加工核查', partyLabel: '委托方', showDaysOutstanding: true,
  }, opts)
}

export default useF2InspectionCheck
