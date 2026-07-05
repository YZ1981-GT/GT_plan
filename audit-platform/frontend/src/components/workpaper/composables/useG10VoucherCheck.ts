/**
 * useG10VoucherCheck — G10-7 凭证检查（贷方侧，4项核对含公允价值）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, isDebitCreditBalanced, calcSubtotal } from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export type G10VoucherTab = 'basic' | 'check' | 'conclusion'

export interface G10VoucherCheckRow {
  id: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  attachment: string | null
  supportingDocDesc: string
  check1OriginalComplete: boolean
  check2Authorization: boolean
  check3Accounting: boolean
  check4FairValueCorrect: boolean
  indexNo: string
  isAbnormal: boolean
  abnormalDesc: string
  riskLevel: 'high' | 'medium' | 'low' | ''
  remark: string
  source: string
}

const ITEM_ID_ROWS = 'G10-voucher-rows'
const ITEM_ID_CONCLUSION = 'G10-voucher-conclusion'

function generateId(): string {
  return `g10v-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function recalcG10VoucherAbnormal(row: G10VoucherCheckRow): G10VoucherCheckRow {
  const checks = [row.check1OriginalComplete, row.check2Authorization, row.check3Accounting, row.check4FairValueCorrect]
  const isAbnormal = checks.some((c) => c === false)
  return { ...row, isAbnormal }
}

function toBoolCheck(v: unknown): boolean {
  if (typeof v === 'boolean') return v
  const s = String(v ?? '').trim()
  return s === '✓' || s === '是' || s === 'true' || s === '1'
}

export function enrichG10VoucherRow(raw: Partial<G10VoucherCheckRow> & { id?: string }, seq: number): G10VoucherCheckRow {
  const base: G10VoucherCheckRow = {
    id: raw.id ?? generateId(),
    seq,
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? raw.summary ?? '',
    counterAccount: raw.counterAccount ?? '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount ?? raw.amount),
    attachment: raw.attachment ?? null,
    supportingDocDesc: raw.supportingDocDesc ?? '',
    check1OriginalComplete: raw.check1OriginalComplete === undefined ? true : toBoolCheck(raw.check1OriginalComplete),
    check2Authorization: raw.check2Authorization === undefined ? true : toBoolCheck(raw.check2Authorization),
    check3Accounting: raw.check3Accounting === undefined ? true : toBoolCheck(raw.check3Accounting),
    check4FairValueCorrect: raw.check4FairValueCorrect === undefined ? true : toBoolCheck(raw.check4FairValueCorrect),
    indexNo: raw.indexNo ?? raw.indexRef ?? '',
    isAbnormal: false,
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: (raw.riskLevel as G10VoucherCheckRow['riskLevel']) ?? '',
    remark: raw.remark ?? '',
    source: raw.source ?? '',
  }
  if (raw.isAbnormal === true || raw.isAbnormal === '是' || raw.isAbnormal === '✓') {
    base.isAbnormal = true
  }
  return recalcG10VoucherAbnormal(base)
}

function parseRows(json: string | null | undefined): G10VoucherCheckRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r, i) => enrichG10VoucherRow(r, i + 1))
  } catch {
    return []
  }
}

export function useG10VoucherCheck(opts: {
  wpId?: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G10VoucherCheckRow[]>([])
  const activeTab = ref<G10VoucherTab>('basic')
  const activeRowIndex = ref(0)
  const conclusion = ref('')
  const aiLoading = ref(false)

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion,
    (v) => { conclusion.value = v ?? '' },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => isDebitCreditBalanced(
    rows.value.map((r) => r.debitAmount),
    rows.value.map((r) => r.creditAmount),
  ))
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)
  const useVirtualScroll = computed(() => rows.value.length > 50)

  function updateRow(id: string, patch: Partial<G10VoucherCheckRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? recalcG10VoucherAbnormal(enrichG10VoucherRow({ ...r, ...patch }, r.seq)) : r))
    persist()
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, enrichG10VoucherRow({}, rows.value.length + 1)]
    persist()
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function mergeSample(sample: Partial<G10VoucherCheckRow>): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, enrichG10VoucherRow({ ...sample, source: sample.source ?? '抽凭' }, rows.value.length + 1)]
    persist()
  }

  function loadRows(data: G10VoucherCheckRow[]): void {
    rows.value = data.map((r, i) => enrichG10VoucherRow(r, i + 1))
    persist()
  }

  function reloadFromStore(): void {
    rows.value = parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
  }

  function setActiveRowIndex(index: number): void {
    activeRowIndex.value = index
  }

  function updateConclusion(value: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g10/ai/voucher-conclusion`, {
        rows: rows.value.filter((r) => r.isAbnormal),
        existingContent: conclusion.value,
      }, { _silent: true } as any)
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  return {
    rows,
    activeTab,
    activeRowIndex,
    conclusion,
    aiLoading,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    abnormalCount,
    useVirtualScroll,
    updateRow,
    addRow,
    removeRow,
    mergeSample,
    loadRows,
    reloadFromStore,
    setActiveRowIndex,
    updateConclusion,
    generateAiConclusion,
  }
}
