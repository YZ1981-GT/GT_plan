/**
 * useF2InspectionCheck — F2-33 采购入库 / F2-34 材料领用（账→单细节测试）
 */
import { ref, computed, watch, onBeforeUnmount, getCurrentInstance, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  emptyPurchaseInboundRow,
  emptyMaterialUsageRow,
  calcInspectionCoverage,
  readBookTotal,
  assessPurchaseAbnormal,
  assessMaterialAbnormal,
  buildCoverageByCategory,
  migrateLegacyInspectionRow,
  calcSubtotal,
  type PurchaseInboundRow,
  type MaterialUsageRow,
  type CoverageLine,
} from './useF2InspectionCheckFormulas'
import type { SampledVoucher, FillMode, SamplingMethod } from './useSamplingAlgorithms'

type Kind = 'purchase' | 'material'

function useInspectionSheet<T extends PurchaseInboundRow | MaterialUsageRow>(
  sheetCode: 'F2-33' | 'F2-34',
  kind: Kind,
  title: string,
  partyLabel: string,
  preferDebit: boolean,
  opts: {
    allResponses: Ref<Map<string, ChecklistResponse>>
    isReadonly?: Ref<boolean>
  },
) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const dataKey = `${sheetCode}-rows`
  const metaKey = `${sheetCode}-meta`
  const coverageKey = `${sheetCode}-coverage-book`

  const rows = ref<T[]>([
    (kind === 'purchase' ? emptyPurchaseInboundRow(1) : emptyMaterialUsageRow(1)) as T,
  ])
  const bookTotal = ref(0)
  const bookByCategory = ref<Record<string, number>>({})
  const auditNote = ref('')
  const meta = ref<Record<string, string>>({
    entityName: '',
    cutoffDate: '',
    populationDesc: '',
    specificSamples: '',
    samplingPopulation: '',
    sampleSize: '',
    samplingMethod: '',
    samplingProcess: '',
  })

  function enrich(r: T): T {
    if (kind === 'purchase') {
      const p = r as PurchaseInboundRow
      return { ...p, isAbnormal: assessPurchaseAbnormal(p) } as T
    }
    const m = r as MaterialUsageRow
    return { ...m, isAbnormal: assessMaterialAbnormal(m) } as T
  }

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(dataKey))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as Record<string, unknown>[]
        if (Array.isArray(parsed) && parsed.length) {
          rows.value = parsed.map((r) => enrich(migrateLegacyInspectionRow(r, kind) as T))
        }
      } catch { /* ignore */ }
    }
    bookTotal.value = readBookTotal(opts.allResponses.value, sheetCode)
    auditNote.value = opts.allResponses.value.get(`${sheetCode}-note`)?.remark || ''
    try {
      const mr = opts.allResponses.value.get(metaKey)?.remark
      if (mr) meta.value = { ...meta.value, ...JSON.parse(mr) }
    } catch { /* ignore */ }
    try {
      const cr = opts.allResponses.value.get(coverageKey)?.remark
      if (cr) bookByCategory.value = JSON.parse(cr) as Record<string, number>
    } catch { /* ignore */ }
  }

  watch(() => opts.allResponses.value.get(dataKey)?.remark, load, { immediate: true })

  const checkedTotal = computed(() => calcSubtotal(rows.value.map((r) => r.amount)))
  const coverageRatio = computed(() => calcInspectionCoverage(checkedTotal.value, bookTotal.value))
  const isCoverageLow = computed(() => coverageRatio.value > 0 && coverageRatio.value < 50)
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)

  const coverageLines = computed((): CoverageLine[] => {
    if (kind === 'purchase') {
      return buildCoverageByCategory(rows.value as PurchaseInboundRow[], bookByCategory.value)
    }
    const checked = checkedTotal.value
    const book = bookTotal.value || Number(bookByCategory.value['原材料贷方'] || 0)
    return [{
      category: '原材料贷方',
      bookAmount: book,
      checkedAmount: checked,
      ratio: calcInspectionCoverage(checked, book),
    }]
  })

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(dataKey),
      opts.allResponses.value.get(`${sheetCode}-book-total`),
      opts.allResponses.value.get(`${sheetCode}-note`),
      opts.allResponses.value.get(metaKey),
      opts.allResponses.value.get(coverageKey),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(dataKey, { item_id: dataKey, conclusion: null, remark: JSON.stringify(rows.value) })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function persistMeta(): void {
    if (readonly.value) return
    opts.allResponses.value.set(metaKey, { item_id: metaKey, conclusion: null, remark: JSON.stringify(meta.value) })
    persist()
  }

  function updateMeta(patch: Record<string, string>): void {
    if (readonly.value) return
    meta.value = { ...meta.value, ...patch }
    persistMeta()
  }

  function updateBookTotal(v: number): void {
    if (readonly.value) return
    bookTotal.value = v
    opts.allResponses.value.set(`${sheetCode}-book-total`, {
      item_id: `${sheetCode}-book-total`, conclusion: null, remark: String(v),
    })
    persist()
  }

  function updateBookByCategory(category: string, amount: number): void {
    if (readonly.value) return
    bookByCategory.value = { ...bookByCategory.value, [category]: amount }
    opts.allResponses.value.set(coverageKey, {
      item_id: coverageKey, conclusion: null, remark: JSON.stringify(bookByCategory.value),
    })
    persist()
  }

  function addRow(): void {
    if (readonly.value) return
    const next = kind === 'purchase'
      ? emptyPurchaseInboundRow(rows.value.length + 1)
      : emptyMaterialUsageRow(rows.value.length + 1)
    rows.value = [...rows.value, next as T]
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function updateRow(id: string, patch: Partial<T>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      return enrich({ ...r, ...patch } as T)
    })
    persist()
  }

  function mapVoucherToRow(v: SampledVoucher, seq: number, method?: SamplingMethod): T {
    const debit = v.debitAmount ? parseFloat(v.debitAmount) : 0
    const credit = v.creditAmount ? parseFloat(v.creditAmount) : 0
    const amount = preferDebit ? (debit > 0 ? debit : credit) : (credit > 0 ? credit : debit)
    const algo = method ?? (v.remark?.includes('stratified') ? 'stratified' : 'random')
    if (kind === 'purchase') {
      return enrich({
        ...emptyPurchaseInboundRow(seq, `来自抽凭引擎 ${algo}`),
        party: v.counterpartAccount || v.accountName || '',
        voucherNo: v.voucherNo || '',
        businessContent: v.summary || '',
        itemName: v.summary || '',
        amount,
        remark: v.remark || '',
      } as T)
    }
    return enrich({
      ...emptyMaterialUsageRow(seq, `来自抽凭引擎 ${algo}`),
      party: v.counterpartAccount || '',
      voucherNo: v.voucherNo || '',
      businessContent: v.summary || '',
      itemName: v.summary || '',
      amount,
      remark: v.remark || '',
    } as T)
  }

  function fillFromSampling(vouchers: SampledVoucher[], fillMode: FillMode, method?: SamplingMethod): void {
    if (readonly.value) return
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
    opts.allResponses.value.set(`${sheetCode}-note`, { item_id: `${sheetCode}-note`, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  if (getCurrentInstance()) {
    onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })
  }

  return {
    sheetCode,
    title,
    partyLabel,
    rows,
    bookTotal,
    bookByCategory,
    meta,
    updateMeta,
    checkedTotal,
    coverageRatio,
    isCoverageLow,
    abnormalCount,
    coverageLines,
    auditNote,
    addRow,
    removeRow,
    updateRow,
    updateBookTotal,
    updateBookByCategory,
    fillFromSampling,
  }
}

export function useF2PurchaseInboundCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  return useInspectionSheet<PurchaseInboundRow>(
    'F2-33', 'purchase', '存货采购入库检查表', '供应商', true, opts,
  )
}

export function useF2MaterialUsageCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  return useInspectionSheet<MaterialUsageRow>(
    'F2-34', 'material', '材料领用检查表', '领用部门', false, opts,
  )
}

export default useF2PurchaseInboundCheck
