/**
 * useF3VoucherCheck — F3-7 借方/贷方检查区
 * Spec: .kiro/specs/f3-notes-payable/ Task 6.5
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal, parseNum } from './useF3FormulaEngine'
import type { ChecklistResponse } from './useF3FormData'
import type { UseF3BaseOptions } from './useF3Adjudication'
import type { SampledVoucher, FillMode } from './useSamplingAlgorithms'

export interface F3VoucherCheckRow {
  rowId: string
  seq: number
  summary: string
  counterAccount: string
  amount: number
  voucherDate: string
  voucherNo: string
  noteType?: string
  acceptor?: string
  purchaseContractCheck?: string
  goodsReceiptCheck?: string
  paymentMethod?: string
  bankReconciliation?: string
  isOverduePayment?: string
  auditConclusion: string
  remark: string
  sampleSource?: string
}

const ITEM_CREDIT = 'F3-7-credit-rows'
const ITEM_DEBIT = 'F3-7-debit-rows'

function generateRowId(): string {
  return `f3v-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number): F3VoucherCheckRow {
  return {
    rowId: generateRowId(), seq, summary: '', counterAccount: '', amount: 0,
    voucherDate: '', voucherNo: '', auditConclusion: '', remark: '',
  }
}

function safeParseRows(jsonStr: string | null | undefined): F3VoucherCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyRow(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      summary: raw.summary || '',
      counterAccount: raw.counterAccount || '',
      amount: parseNum(raw.amount),
      voucherDate: raw.voucherDate || '',
      voucherNo: raw.voucherNo || '',
      noteType: raw.noteType || '',
      acceptor: raw.acceptor || '',
      purchaseContractCheck: raw.purchaseContractCheck || '',
      goodsReceiptCheck: raw.goodsReceiptCheck || '',
      paymentMethod: raw.paymentMethod || '',
      bankReconciliation: raw.bankReconciliation || '',
      isOverduePayment: raw.isOverduePayment || '',
      auditConclusion: raw.auditConclusion || '',
      remark: raw.remark || '',
      sampleSource: raw.sampleSource || '',
    }))
  } catch {
    return []
  }
}

export function useF3VoucherCheck(options: UseF3BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const creditStored = ref<F3VoucherCheckRow[]>([])
  const debitStored = ref<F3VoucherCheckRow[]>([])
  const auditConclusion = ref('')

  function loadRows(): void {
    creditStored.value = safeParseRows(allResponses.value.get(ITEM_CREDIT)?.remark)
    debitStored.value = safeParseRows(allResponses.value.get(ITEM_DEBIT)?.remark)
    if (creditStored.value.length === 0) creditStored.value = [emptyRow(1)]
    if (debitStored.value.length === 0) debitStored.value = [emptyRow(1)]
  }

  watch(() => allResponses.value.get(ITEM_CREDIT)?.remark, () => {
    if (creditStored.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get(ITEM_DEBIT)?.remark, () => {
    if (debitStored.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get('F3-7-conclusion')?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  const creditRows: ComputedRef<F3VoucherCheckRow[]> = computed(() => creditStored.value)
  const debitRows: ComputedRef<F3VoucherCheckRow[]> = computed(() => debitStored.value)

  const creditTotal = computed(() => calcSubtotal(creditRows.value.map((r) => r.amount)))
  const debitTotal = computed(() => calcSubtotal(debitRows.value.map((r) => r.amount)))

  const creditAbnormal = computed(() =>
    creditRows.value.filter((r) => r.auditConclusion && r.auditConclusion !== '无异常').length,
  )
  const debitAbnormal = computed(() =>
    debitRows.value.filter((r) => r.auditConclusion && r.auditConclusion !== '无异常').length,
  )

  function addRow(side: 'credit' | 'debit'): void {
    if (readonly.value) return
    const target = side === 'credit' ? creditStored : debitStored
    target.value.push(emptyRow(target.value.length + 1))
    persistRows()
  }

  function removeRow(side: 'credit' | 'debit', rowId: string): void {
    if (readonly.value) return
    const target = side === 'credit' ? creditStored : debitStored
    if (target.value.length <= 1) return
    const idx = target.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    target.value.splice(idx, 1)
    target.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function updateCell(side: 'credit' | 'debit', rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const target = side === 'credit' ? creditStored : debitStored
    const row = target.value.find((r) => r.rowId === rowId)
    if (!row) return
    const strFields = ['summary', 'counterAccount', 'voucherDate', 'voucherNo', 'noteType', 'acceptor',
      'purchaseContractCheck', 'goodsReceiptCheck', 'paymentMethod', 'bankReconciliation',
      'isOverduePayment', 'auditConclusion', 'remark', 'sampleSource']
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    persistRows()
  }

  /** 抽凭引擎样本填入（Task 9.3 / 10.7） */
  function mergeSamples(samples: Array<{ direction: 'debit' | 'credit'; data: Partial<F3VoucherCheckRow> }>): void {
    if (readonly.value) return
    for (const s of samples) {
      const target = s.direction === 'credit' ? creditStored : debitStored
      target.value.push({
        ...emptyRow(target.value.length + 1),
        ...s.data,
        sampleSource: s.data.sampleSource || '抽凭引擎',
      })
    }
    creditStored.value.forEach((r, i) => { r.seq = i + 1 })
    debitStored.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function mapVoucherToEntries(v: SampledVoucher): Array<{ direction: 'debit' | 'credit'; data: Partial<F3VoucherCheckRow> }> {
    const debit = v.debitAmount ? parseFloat(v.debitAmount) : 0
    const credit = v.creditAmount ? parseFloat(v.creditAmount) : 0
    const base: Partial<F3VoucherCheckRow> = {
      summary: v.summary || '',
      counterAccount: v.counterpartAccount || '',
      voucherDate: v.voucherDate || '',
      voucherNo: v.voucherNo || '',
      sampleSource: '抽凭引擎',
    }
    const entries: Array<{ direction: 'debit' | 'credit'; data: Partial<F3VoucherCheckRow> }> = []
    if (credit > 0) entries.push({ direction: 'credit', data: { ...base, amount: credit } })
    if (debit > 0) entries.push({ direction: 'debit', data: { ...base, amount: debit } })
    if (entries.length === 0) {
      const amount = Math.max(debit, credit)
      entries.push({ direction: credit >= debit ? 'credit' : 'debit', data: { ...base, amount } })
    }
    return entries
  }

  /** GtVoucherSamplingEngine @filled 处理（支持 append/replace/merge） */
  function applySamplingResults(vouchers: SampledVoucher[], fillMode: FillMode): void {
    if (readonly.value) return
    const mapped = vouchers.flatMap(mapVoucherToEntries)

    if (fillMode === 'replace') {
      creditStored.value = mapped
        .filter((m) => m.direction === 'credit')
        .map((m, i) => ({ ...emptyRow(i + 1), ...m.data }))
      debitStored.value = mapped
        .filter((m) => m.direction === 'debit')
        .map((m, i) => ({ ...emptyRow(i + 1), ...m.data }))
      if (creditStored.value.length === 0) creditStored.value = [emptyRow(1)]
      if (debitStored.value.length === 0) debitStored.value = [emptyRow(1)]
    } else if (fillMode === 'merge') {
      const creditNos = new Set(creditStored.value.map((r) => r.voucherNo).filter(Boolean))
      const debitNos = new Set(debitStored.value.map((r) => r.voucherNo).filter(Boolean))
      const deduped = mapped.filter((m) => {
        const no = m.data.voucherNo || ''
        if (!no) return true
        return m.direction === 'credit' ? !creditNos.has(no) : !debitNos.has(no)
      })
      mergeSamples(deduped)
      return
    } else {
      mergeSamples(mapped)
      return
    }

    creditStored.value.forEach((r, i) => { r.seq = i + 1 })
    debitStored.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function persistRows(): void {
    allResponses.value.set(ITEM_CREDIT, { item_id: ITEM_CREDIT, conclusion: null, remark: JSON.stringify(creditStored.value) })
    allResponses.value.set(ITEM_DEBIT, { item_id: ITEM_DEBIT, conclusion: null, remark: JSON.stringify(debitStored.value) })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(ITEM_CREDIT),
      allResponses.value.get(ITEM_DEBIT),
      allResponses.value.get('F3-7-conclusion'),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
  }

  watch(auditConclusion, (val) => {
    allResponses.value.set('F3-7-conclusion', { item_id: 'F3-7-conclusion', conclusion: null, remark: val })
    debounceSave()
  })

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    creditRows, debitRows, creditTotal, debitTotal, creditAbnormal, debitAbnormal,
    auditConclusion, addRow, removeRow, updateCell, mergeSamples, applySamplingResults, mapVoucherToEntries,
  }
}

export default useF3VoucherCheck
