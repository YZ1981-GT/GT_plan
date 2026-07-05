/**
 * useG8VoucherCheck — G8-6 凭证检查（5项核对含公允价值+OCI）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, isDebitCreditBalanced, calcSubtotal } from './useG8FormulaEngine'
import { mapCutoffToG8Voucher, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'

export type G8VoucherTab = 'basic' | 'check' | 'conclusion'

export interface G8VoucherRow {
  rowId: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  attachment: string
  supportingDocDesc: string
  check1OriginalComplete: boolean
  check2Authorization: boolean
  check3Accounting: boolean
  check4FairValueCorrect: boolean
  check5OCICorrect: boolean
  indexNo: string
  isAbnormal: boolean
  abnormalDesc: string
  riskLevel: string
  remark: string
  source?: string
}

const ITEM_ID_ROWS = 'G8-voucher-rows'
const ITEM_ID_CONCLUSION = 'G8-voucher-conclusion'

function genId(): string {
  return `g8v-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function recalcG8VoucherAbnormal(row: G8VoucherRow): G8VoucherRow {
  const checks = [
    row.check1OriginalComplete,
    row.check2Authorization,
    row.check3Accounting,
    row.check4FairValueCorrect,
    row.check5OCICorrect,
  ]
  return { ...row, isAbnormal: checks.some((c) => c === false) || row.isAbnormal }
}

export function enrichG8VoucherRow(raw: Partial<G8VoucherRow> & { rowId?: string; id?: string }, seq: number): G8VoucherRow {
  const base: G8VoucherRow = {
    rowId: raw.rowId ?? raw.id ?? genId(),
    seq,
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? '',
    counterAccount: raw.counterAccount ?? '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    attachment: raw.attachment ?? '',
    supportingDocDesc: raw.supportingDocDesc ?? '',
    check1OriginalComplete: raw.check1OriginalComplete !== false,
    check2Authorization: raw.check2Authorization !== false,
    check3Accounting: raw.check3Accounting !== false,
    check4FairValueCorrect: raw.check4FairValueCorrect !== false,
    check5OCICorrect: raw.check5OCICorrect !== false,
    indexNo: raw.indexNo ?? '',
    isAbnormal: !!raw.isAbnormal,
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: raw.riskLevel ?? 'low',
    remark: raw.remark ?? '',
    source: raw.source ?? '',
  }
  return recalcG8VoucherAbnormal(base)
}

/** @deprecated use recalcG8VoucherAbnormal */
export function deriveG8Abnormal(row: G8VoucherRow): boolean {
  return recalcG8VoucherAbnormal(row).isAbnormal
}

function parseRows(json: string | null | undefined): G8VoucherRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG8VoucherRow(r, i + 1))
  } catch {
    return []
  }
}

export function useG8VoucherCheck(opts: {
  wpId?: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G8VoucherRow[]>([])
  const activeTab = ref<G8VoucherTab>('basic')
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

  function updateRow(rowId: string, patch: Partial<G8VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) =>
      r.rowId === rowId ? recalcG8VoucherAbnormal(enrichG8VoucherRow({ ...r, ...patch }, r.seq)) : r,
    )
    persist()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入凭证编号', '新增凭证行')
      const no = (value ?? '').trim()
      if (!no) return
      rows.value = [...rows.value, enrichG8VoucherRow({ voucherNo: no }, rows.value.length + 1)]
      persist()
    } catch { /* cancelled */ }
  }

  function mergeSample(sample: Partial<G8VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = [
      ...rows.value,
      enrichG8VoucherRow({ ...sample, source: sample.source ?? '抽凭' }, rows.value.length + 1),
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
    const mapped = samples.map((v, i) => enrichG8VoucherRow(mapCutoffToG8Voucher(v, base + i + 1), base + i + 1))
    rows.value = mergeByFillMode(rows.value, mapped, fillMode, (r) => r.voucherNo || r.rowId)
    persist()
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g8/ai/voucher-conclusion`,
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
