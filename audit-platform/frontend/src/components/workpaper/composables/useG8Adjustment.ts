/**
 * useG8Adjustment — G8-3 调整分录（AJE/RJE 回写 G8-1）
 */
import { computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { G8_ACCOUNT_CODE } from './g8Constants'
import {
  aggregateG8AdjustmentWriteback,
  applyG8AdjustmentWriteback,
  calcG8AdjustmentNet,
  parseG8AdjStore,
} from './g8AdjStorage'
import { mapCutoffToG8Adjustment, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import { parseNum, isDebitCreditBalanced } from './useG8FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G8AdjustmentEntry {
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

const ITEM_ID_ROWS = 'G8-adjustment-rows'
const ITEM_ID_ADJ_ROWS = 'G8-adj-rows'
export const G8_ADJ_OVERLAY_ID = 'G8-adj-overlay'

function genId(): string {
  return `g8a-${Date.now().toString(36)}`
}

function normalizeEntry(raw: any, idx: number): G8AdjustmentEntry {
  return {
    rowId: raw.rowId || raw.id || genId(),
    seq: raw.seq ?? idx + 1,
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date ?? '',
    summary: raw.summary ?? '',
    accountCode: raw.accountCode ?? G8_ACCOUNT_CODE,
    accountName: raw.accountName ?? '其他权益工具投资',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy ?? '',
    remark: raw.remark ?? '',
  }
}

function parseRows(json: string | null | undefined): G8AdjustmentEntry[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr.map(normalizeEntry) : []
  } catch {
    return []
  }
}

export function useG8Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  applyAdjustmentToAdjudication?: (closingAdjustment: number) => void
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

  const adjustmentNet = computed(() => calcG8AdjustmentNet(rows.value))
  const writebackPreview = computed(() => aggregateG8AdjustmentWriteback(rows.value))

  function persist(list: G8AdjustmentEntry[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
    syncWriteback(list)
  }

  function syncWriteback(list = rows.value): void {
    const wb = aggregateG8AdjustmentWriteback(list)
    opts.debouncedSave(G8_ADJ_OVERLAY_ID, { remark: JSON.stringify(wb) })

    const store = parseG8AdjStore(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark)
    const patched = applyG8AdjustmentWriteback(store, wb)
    opts.debouncedSave(ITEM_ID_ADJ_ROWS, { remark: JSON.stringify(patched) })

    opts.applyAdjustmentToAdjudication?.(wb.closingAdjustment)
    try {
      window.dispatchEvent(new CustomEvent('g8:adjustment-writeback', { detail: wb }))
    } catch { /* silent */ }
  }

  function updateRow(rowId: string, patch: Partial<G8AdjustmentEntry>): void {
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
          accountCode: G8_ACCOUNT_CODE,
          accountName: '其他权益工具投资',
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
    const mapped = samples.map((v, i) => mapCutoffToG8Adjustment(v, base + i + 1))
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
