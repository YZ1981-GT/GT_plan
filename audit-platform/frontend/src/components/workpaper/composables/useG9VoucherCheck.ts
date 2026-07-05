/**
 * useG9VoucherCheck — G9-6 凭证检查（6项核对含公允价值+减值）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, isDebitCreditBalanced, calcSubtotal } from './useG9FormulaEngine'
import { mapCutoffToG9Voucher, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'

export type G9VoucherTab = 'basic' | 'check' | 'conclusion'

export interface G9VoucherRow {
  rowId: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  attachmentRef: string
  supportDoc: string
  checkOriginal: boolean
  checkAuthorized: boolean
  checkAccounting: boolean
  checkClassification: boolean
  checkFairValue: boolean
  checkImpairment: boolean
  indexRef: string
  isAbnormal: boolean
  abnormalDesc: string
  riskLevel: string
  suggestion: string
  remark: string
  source?: string
}

const ITEM_ID_ROWS = 'G9-voucher-rows'
const ITEM_ID_CONCLUSION = 'G9-voucher-conclusion'

function genId(): string {
  return `g9v-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function recalcG9VoucherAbnormal(row: G9VoucherRow): G9VoucherRow {
  const checks = [
    row.checkOriginal, row.checkAuthorized, row.checkAccounting,
    row.checkClassification, row.checkFairValue, row.checkImpairment,
  ]
  return { ...row, isAbnormal: checks.some((c) => c === false) || row.isAbnormal }
}

export function enrichG9VoucherRow(raw: Partial<G9VoucherRow> & { rowId?: string; id?: string }, seq: number): G9VoucherRow {
  const base: G9VoucherRow = {
    rowId: raw.rowId ?? raw.id ?? genId(),
    seq,
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? '',
    counterAccount: raw.counterAccount ?? '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    attachmentRef: raw.attachmentRef ?? '',
    supportDoc: raw.supportDoc ?? '',
    checkOriginal: raw.checkOriginal !== false,
    checkAuthorized: raw.checkAuthorized !== false,
    checkAccounting: raw.checkAccounting !== false,
    checkClassification: raw.checkClassification !== false,
    checkFairValue: raw.checkFairValue !== false,
    checkImpairment: raw.checkImpairment !== false,
    indexRef: raw.indexRef ?? '',
    isAbnormal: !!raw.isAbnormal,
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: raw.riskLevel ?? 'low',
    suggestion: raw.suggestion ?? '',
    remark: raw.remark ?? '',
    source: raw.source ?? '',
  }
  return recalcG9VoucherAbnormal(base)
}

/** @deprecated use recalcG9VoucherAbnormal */
export function deriveAbnormal(row: G9VoucherRow): boolean {
  return recalcG9VoucherAbnormal(row).isAbnormal
}

function parseRows(json: string | null | undefined): G9VoucherRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG9VoucherRow(r, i + 1))
  } catch {
    return []
  }
}

export function useG9VoucherCheck(opts: {
  wpId?: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G9VoucherRow[]>([])
  const activeTab = ref<G9VoucherTab>('basic')
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

  const balanceOk = computed(() =>
    isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)),
  )
  const balanceDiff = computed(() =>
    calcSubtotal(rows.value.map((r) => r.debitAmount)) - calcSubtotal(rows.value.map((r) => r.creditAmount)),
  )
  const useVirtualScroll = computed(() => rows.value.length > 50)

  function updateRow(rowId: string, patch: Partial<G9VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) =>
      r.rowId === rowId ? recalcG9VoucherAbnormal(enrichG9VoucherRow({ ...r, ...patch }, r.seq)) : r,
    )
    persist()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入凭证编号', '新增凭证行')
      const no = (value ?? '').trim()
      if (!no) return
      rows.value = [...rows.value, enrichG9VoucherRow({ voucherNo: no }, rows.value.length + 1)]
      persist()
    } catch { /* cancelled */ }
  }

  function mergeSample(sample: Partial<G9VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = [
      ...rows.value,
      enrichG9VoucherRow({ ...sample, source: sample.source ?? '抽凭' }, rows.value.length + 1),
    ]
    persist()
  }

  function reloadFromStore(): void {
    rows.value = parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
  }

  function setActiveRowIndex(idx: number): void {
    activeRowIndex.value = idx
  }

  function updateConclusion(value: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (opts.isReadonly.value || !samples.length) return
    const base = rows.value.length
    const mapped = samples.map((v, i) => enrichG9VoucherRow(mapCutoffToG9Voucher(v, base + i + 1), base + i + 1))
    rows.value = mergeByFillMode(rows.value, mapped, fillMode, (r) => r.voucherNo || r.rowId)
    persist()
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g9/ai/voucher-conclusion`,
        {
          rows: rows.value.filter((r) => r.isAbnormal),
          existingContent: conclusion.value,
        },
        { _silent: true } as any,
      )
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
    balanceOk,
    balanceDiff,
    useVirtualScroll,
    updateRow,
    addRow,
    mergeSample,
    reloadFromStore,
    setActiveRowIndex,
    updateConclusion,
    generateAiConclusion,
    applyCutoffResults,
    riskLevelOptions: [
      { value: 'high', label: '高' },
      { value: 'medium', label: '中' },
      { value: 'low', label: '低' },
    ],
  }
}
