/**
 * useG11VoucherCheck — G11-5 凭证检查（3区段Tab行同步）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, isDebitCreditBalanced, calcSubtotal } from './useG11FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export type G11VoucherTab = 'basic' | 'check' | 'conclusion'

export interface G11VoucherCheckRow {
  id: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetail: string
  creditAmount: number
  attachment: string | null
  supportingDocDesc: string
  check1: boolean
  check2: boolean
  check3: boolean
  check4: boolean
  check5: boolean
  indexNo: string
  isAbnormal: boolean
  abnormalDesc: string
  riskLevel: 'high' | 'medium' | 'low' | ''
  remark: string
  source: string
}

const ITEM_ID_ROWS = 'G11-voucher-rows'

function generateId(): string {
  return `g11v-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function recalcAbnormal(row: G11VoucherCheckRow): G11VoucherCheckRow {
  const checks = [row.check1, row.check2, row.check3, row.check4, row.check5]
  const isAbnormal = checks.some((c) => c === false)
  return { ...row, isAbnormal }
}

function toBoolCheck(v: unknown): boolean {
  if (typeof v === 'boolean') return v
  const s = String(v ?? '').trim()
  return s === '✓' || s === '是' || s === 'true' || s === '1'
}

export function enrichG11VoucherRow(raw: Partial<G11VoucherCheckRow> & { id?: string }, seq: number): G11VoucherCheckRow {
  const base: G11VoucherCheckRow = {
    id: raw.id ?? generateId(),
    seq,
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? raw.summary ?? '',
    counterAccount: raw.counterAccount ?? '',
    counterDetail: raw.counterDetail ?? '',
    creditAmount: parseNum(raw.creditAmount ?? raw.amount),
    attachment: raw.attachment ?? null,
    supportingDocDesc: raw.supportingDocDesc ?? '',
    check1: raw.check1 === undefined ? true : toBoolCheck(raw.check1),
    check2: raw.check2 === undefined ? true : toBoolCheck(raw.check2),
    check3: raw.check3 === undefined ? true : toBoolCheck(raw.check3),
    check4: raw.check4 === undefined ? true : toBoolCheck(raw.check4),
    check5: raw.check5 === undefined ? true : toBoolCheck(raw.check5),
    indexNo: raw.indexNo ?? raw.indexRef ?? '',
    isAbnormal: false,
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: (raw.riskLevel as G11VoucherCheckRow['riskLevel']) ?? '',
    remark: raw.remark ?? '',
    source: raw.source ?? '',
  }
  if (raw.isAbnormal === true || raw.isAbnormal === '是' || raw.isAbnormal === '✓') {
    base.isAbnormal = true
  }
  return recalcAbnormal(base)
}

function parseRows(json: string | null | undefined): G11VoucherCheckRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r, i) => enrichG11VoucherRow(r, i + 1))
  } catch {
    return []
  }
}

export function useG11VoucherCheck(opts: {
  wpId?: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G11VoucherCheckRow[]>([])
  const activeTab = ref<G11VoucherTab>('basic')
  const activeRowIndex = ref(0)
  const conclusion = ref('')
  const aiLoading = ref(false)

  const ITEM_ID_CONCLUSION = 'G11-voucher-conclusion'

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

  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const debitTotal = computed(() => 0)
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => isDebitCreditBalanced(
    rows.value.map(() => 0),
    rows.value.map((r) => r.creditAmount),
  ))
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)

  function updateRow(id: string, patch: Partial<G11VoucherCheckRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? recalcAbnormal(enrichG11VoucherRow({ ...r, ...patch }, r.seq)) : r))
    persist()
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, enrichG11VoucherRow({}, rows.value.length + 1)]
    persist()
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function mergeSample(sample: Partial<G11VoucherCheckRow>): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, enrichG11VoucherRow({ ...sample, source: sample.source ?? '抽凭' }, rows.value.length + 1)]
    persist()
  }

  function loadRows(data: G11VoucherCheckRow[]): void {
    rows.value = data.map((r, i) => enrichG11VoucherRow(r, i + 1))
    persist()
  }

  function reloadFromStore(): void {
    const json = opts.allResponses.value.get(ITEM_ID_ROWS)?.remark
    rows.value = parseRows(json)
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
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g11/ai/voucher-conclusion`, {
        rows: rows.value.filter((r) => r.isAbnormal),
        existingContent: conclusion.value,
      }, { _silent: true } as any)
      const text = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
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
    creditTotal,
    balanceDiff,
    isBalanced,
    abnormalCount,
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
