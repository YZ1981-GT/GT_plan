/**
 * useG11Adjustment — G11-3 调整分录汇总（回写 G11-1 / G11-2）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useG11FormulaEngine'
import { calcG11AdjustmentNet } from './g11AdjStorage'
import type { ChecklistResponse } from './useF1FormData'

export interface G11AdjustmentRow {
  rowId: string
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

const ITEM_ID_ROWS = 'G11-aje-rows'

function generateRowId(): string {
  return `g11a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function createEmptyG11AdjustmentRow(): G11AdjustmentRow {
  return {
    rowId: generateRowId(),
    entryType: 'AJE',
    date: '',
    summary: '',
    accountCode: '6111',
    accountName: '投资收益',
    debitAmount: 0,
    creditAmount: 0,
    preparedBy: '',
    remark: '',
  }
}

function normalizeRow(raw: any): G11AdjustmentRow {
  return {
    rowId: raw.rowId || raw.id || generateRowId(),
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date || '',
    summary: raw.summary || raw.description || '',
    accountCode: raw.accountCode || '6111',
    accountName: raw.accountName || '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy || '',
    remark: raw.remark || '',
  }
}

function parseRows(json: string | null | undefined): G11AdjustmentRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

export interface UseG11AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  /** 回写 G11-1「其他」行本期调整 */
  applyAdjustmentToAdjudication?: (netAdjustment: number) => void
  /** 回写 G11-2「其他」行本期调整 */
  applyAdjustmentToDetail?: (netAdjustment: number) => void
}

export function useG11Adjustment(opts: UseG11AdjustmentOptions) {
  const rows = ref<G11AdjustmentRow[]>([])

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
    syncWriteback()
  }

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => isDebitCreditBalanced(
    rows.value.map((r) => r.debitAmount),
    rows.value.map((r) => r.creditAmount),
  ))
  const adjustmentNet = computed(() => calcG11AdjustmentNet(rows.value))

  function syncWriteback(): void {
    const net = adjustmentNet.value
    opts.applyAdjustmentToAdjudication?.(net)
    opts.applyAdjustmentToDetail?.(net)
    try {
      window.dispatchEvent(new CustomEvent('g11:adjustment-synced', { detail: { netAdjustment: net } }))
    } catch { /* silent */ }
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, createEmptyG11AdjustmentRow()]
    persist()
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateRow(rowId: string, patch: Partial<G11AdjustmentRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.rowId === rowId ? normalizeRow({ ...r, ...patch }) : r))
    persist()
  }

  function loadRows(data: G11AdjustmentRow[]): void {
    rows.value = data.map(normalizeRow)
    persist()
  }

  return {
    rows,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    adjustmentNet,
    addRow,
    removeRow,
    updateRow,
    loadRows,
    syncWriteback,
    ITEM_ID_ROWS,
  }
}
