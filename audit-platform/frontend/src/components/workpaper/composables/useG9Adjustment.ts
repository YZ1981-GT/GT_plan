/**
 * useG9Adjustment — G9-3 调整分录（AJE/RJE 回写 G9-1）
 */
import { computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { G9_ACCOUNT_CODE } from './g9Constants'
import {
  aggregateG9AdjustmentAjeRje,
  applyG9AdjustmentWriteback,
  calcG9AdjustmentNet,
  parseG9AdjStore,
} from './g9AdjStorage'
import { mapCutoffToG9Adjustment, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import { parseNum, isDebitCreditBalanced } from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G9AdjustmentEntry {
  rowId: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

const ITEM_ID_ROWS = 'G9-adjustment-rows'
const ITEM_ID_ADJ_ROWS = 'G9-adj-rows'
export const G9_AJE_ADJ_OVERLAY_ID = 'G9-aje-adj-overlay'

function genId(): string {
  return `g9a-${Date.now().toString(36)}`
}

function normalizeEntry(raw: any, idx: number): G9AdjustmentEntry {
  return {
    rowId: raw.rowId || raw.id || genId(),
    seq: raw.seq ?? idx + 1,
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date ?? '',
    summary: raw.summary ?? '',
    accountCode: raw.accountCode ?? G9_ACCOUNT_CODE,
    accountName: raw.accountName ?? '其他非流动金融资产',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy ?? '',
    remark: raw.remark ?? '',
  }
}

function parseRows(json: string | null | undefined): G9AdjustmentEntry[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr.map(normalizeEntry) : []
  } catch {
    return []
  }
}

export function useG9Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  applyAdjustmentToAdjudication?: (aje: number, rje: number) => void
}) {
  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  const balanceOk = computed(() =>
    isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)),
  )

  const balanceDiff = computed(() => {
    const d = rows.value.reduce((s, r) => s + parseNum(r.debitAmount), 0)
    const c = rows.value.reduce((s, r) => s + parseNum(r.creditAmount), 0)
    return d - c
  })

  const adjustmentNet = computed(() => calcG9AdjustmentNet(rows.value))
  const writebackPreview = computed(() => aggregateG9AdjustmentAjeRje(rows.value))

  function persist(list: G9AdjustmentEntry[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
    syncWriteback(list)
  }

  function syncWriteback(list = rows.value): void {
    const wb = aggregateG9AdjustmentAjeRje(list)
    opts.debouncedSave(G9_AJE_ADJ_OVERLAY_ID, { remark: JSON.stringify(wb) })

    const store = parseG9AdjStore(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark)
    const patched = applyG9AdjustmentWriteback(store, wb)
    opts.debouncedSave(ITEM_ID_ADJ_ROWS, { remark: JSON.stringify(patched) })

    opts.applyAdjustmentToAdjudication?.(wb.closingAje, wb.closingRje)
    try {
      window.dispatchEvent(new CustomEvent('g9:adjustment-writeback', { detail: wb }))
    } catch { /* silent */ }
  }

  function updateRow(rowId: string, patch: Partial<G9AdjustmentEntry>): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => (r.rowId === rowId ? normalizeEntry({ ...r, ...patch }, r.seq - 1) : r))
    persist(list)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入摘要', '新增调整分录', { inputPlaceholder: '摘要' })
      const summary = (value ?? '').trim()
      if (!summary) return
      persist([
        ...rows.value,
        {
          rowId: genId(),
          seq: rows.value.length + 1,
          entryType: 'AJE',
          date: '',
          summary,
          accountCode: G9_ACCOUNT_CODE,
          accountName: '其他非流动金融资产',
          debitAmount: 0,
          creditAmount: 0,
          preparedBy: '',
          remark: '',
        },
      ])
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    persist(rows.value.filter((r) => r.rowId !== rowId).map((r, i) => ({ ...r, seq: i + 1 })))
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (opts.isReadonly.value || !samples.length) return
    const base = rows.value.length
    const mapped = samples.map((v, i) => mapCutoffToG9Adjustment(v, base + i + 1))
    const merged = mergeByFillMode(rows.value, mapped, fillMode, (r) => r.remark || `${r.summary}|${r.debitAmount}`)
    persist(merged.map((r, i) => ({ ...r, seq: i + 1 })))
  }

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    () => { /* rows computed */ },
    { immediate: true },
  )

  return {
    rows,
    balanceOk,
    balanceDiff,
    adjustmentNet,
    writebackPreview,
    updateRow,
    addRow,
    removeRow,
    syncWriteback,
    applyCutoffResults,
  }
}
