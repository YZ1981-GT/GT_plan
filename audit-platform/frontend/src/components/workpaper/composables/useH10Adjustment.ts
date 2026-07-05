/**
 * useH10Adjustment — H10-3 调整分录（AJE/RJE 回写 H10-1）
 */
import { computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { H10_ACCOUNT_CODE } from './h10Constants'
import {
  aggregateH10AdjustmentAjeRje,
  applyH10AdjustmentWriteback,
  calcH10AdjustmentNet,
  parseH10AdjStore,
} from './h10AdjStorage'
import { parseNum, isDebitCreditBalanced } from './useH10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface H10AdjustmentEntry {
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

const ITEM_ID_ROWS = 'H10-adjustment-rows'
const ITEM_ID_ADJ_ROWS = 'H10-adj-rows'
export const H10_ADJ_OVERLAY_ID = 'H10-adj-overlay'

function genId(): string {
  return `h10a-${Date.now().toString(36)}`
}

function normalizeEntry(raw: any, idx: number): H10AdjustmentEntry {
  return {
    rowId: raw.rowId || raw.id || genId(),
    seq: raw.seq ?? idx + 1,
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date ?? '',
    summary: raw.summary ?? '',
    accountCode: raw.accountCode ?? H10_ACCOUNT_CODE,
    accountName: raw.accountName ?? '资产处置损益',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy ?? '',
    remark: raw.remark ?? '',
  }
}

function parseRows(json: string | null | undefined): H10AdjustmentEntry[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr.map(normalizeEntry) : []
  } catch {
    return []
  }
}

export function useH10Adjustment(opts: {
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

  const adjustmentNet = computed(() => calcH10AdjustmentNet(rows.value))
  const writebackPreview = computed(() => aggregateH10AdjustmentAjeRje(rows.value))

  function persist(list: H10AdjustmentEntry[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
    syncWriteback(list)
  }

  function syncWriteback(list = rows.value): void {
    const wb = aggregateH10AdjustmentAjeRje(list)
    opts.debouncedSave(H10_ADJ_OVERLAY_ID, { remark: JSON.stringify(wb) })

    const store = parseH10AdjStore(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark)
    const patched = applyH10AdjustmentWriteback(store, wb)
    opts.debouncedSave(ITEM_ID_ADJ_ROWS, { remark: JSON.stringify(patched) })

    opts.applyAdjustmentToAdjudication?.(wb.currentAje, wb.currentRje)
    publishAdjustmentEvents(list)
    try {
      window.dispatchEvent(new CustomEvent('h10:adjustment-writeback', { detail: wb }))
    } catch { /* silent */ }
  }

  function publishAdjustmentEvents(list: H10AdjustmentEntry[]): void {
    const wb = aggregateH10AdjustmentAjeRje(list)
    try {
      if (Math.abs(wb.currentAje) > 0.001) {
        window.dispatchEvent(new CustomEvent('adjustment:created', {
          detail: {
            wpCode: 'H10',
            entryType: 'AJE',
            amount: wb.currentAje,
            accountCode: H10_ACCOUNT_CODE,
          },
        }))
      }
      if (Math.abs(wb.currentRje) > 0.001) {
        window.dispatchEvent(new CustomEvent('adjustment:created', {
          detail: {
            wpCode: 'H10',
            entryType: 'RJE',
            amount: wb.currentRje,
            accountCode: H10_ACCOUNT_CODE,
          },
        }))
      }
    } catch { /* silent */ }
  }

  function updateRow(rowId: string, patch: Partial<H10AdjustmentEntry>): void {
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
          accountCode: H10_ACCOUNT_CODE,
          accountName: '资产处置损益',
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

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    () => { /* rows computed */ },
    { immediate: true },
  )

  return {
    rows,
    balanceOk,
    isBalanced: balanceOk,
    balanceDiff,
    adjustmentNet,
    writebackPreview,
    updateRow,
    addRow,
    removeRow,
    syncWriteback,
    ITEM_ID_ROWS,
  }
}
