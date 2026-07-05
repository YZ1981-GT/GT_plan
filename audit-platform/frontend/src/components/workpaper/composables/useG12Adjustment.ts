/**
 * useG12Adjustment — G12-3 调整分录
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { G12_ACCOUNT_CODE } from './g12Constants'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useG12FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G12AdjustmentRow {
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

const ITEM_ID = 'G12-aje-rows'
/** G12-3 → G12-1 审定表调整数 overlay（按 rowKey） */
export const G12_AJE_ADJ_OVERLAY_ID = 'G12-aje-adj-overlay'
function genId() { return `g12a-${Date.now().toString(36)}` }

export function createEmptyG12AdjustmentRow(): G12AdjustmentRow {
  return { rowId: genId(), entryType: 'AJE', date: '', summary: '', accountCode: '6103', accountName: '净敞口套期收益', debitAmount: 0, creditAmount: 0, preparedBy: '', remark: '' }
}

function norm(raw: any): G12AdjustmentRow {
  return {
    rowId: raw.rowId || genId(),
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date || '', summary: raw.summary || raw.description || '',
    accountCode: raw.accountCode || '6103', accountName: raw.accountName || '净敞口套期收益',
    debitAmount: parseNum(raw.debitAmount), creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy || '', remark: raw.remark || '',
  }
}

export function useG12Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  applyAdjustmentOverlay?: (overlay: Record<string, number>) => void
}) {
  const rows = ref<G12AdjustmentRow[]>([])
  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    try { rows.value = j ? JSON.parse(j).map(norm) : [] } catch { rows.value = [] }
  }, { immediate: true })

  function persist() { opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(rows.value) }) }
  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)))

  function addRow() { if (!opts.isReadonly.value) { rows.value = [...rows.value, createEmptyG12AdjustmentRow()]; persist() } }
  function removeRow(id: string) { if (!opts.isReadonly.value) { rows.value = rows.value.filter((r) => r.rowId !== id); persist() } }
  function updateCell(id: string, field: keyof G12AdjustmentRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === id)
    if (idx === -1) return
    const row = { ...rows.value[idx] }
    if (field === 'debitAmount' || field === 'creditAmount') row[field] = parseNum(value)
    else if (field === 'entryType') row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
    else (row as any)[field] = value
    const next = [...rows.value]; next[idx] = row; rows.value = next; persist()
  }

  function syncToAdjudication(): void {
    if (opts.isReadonly.value || !isBalanced.value) return
    const net = rows.value
      .filter((r) => String(r.accountCode).startsWith(G12_ACCOUNT_CODE))
      .reduce((s, r) => s + r.debitAmount - r.creditAmount, 0)
    const overlay: Record<string, number> = { net_hedge: net }
    opts.debouncedSave(G12_AJE_ADJ_OVERLAY_ID, { remark: JSON.stringify(overlay) })
    opts.applyAdjustmentOverlay?.(overlay)
    window.dispatchEvent(new CustomEvent('g12:adjustment-synced', { detail: { netAdjustment: net, overlay } }))
  }

  return {
    rows, debitTotal, creditTotal, balanceDiff, isBalanced,
    addRow, removeRow, updateCell, syncToAdjudication, persist, ITEM_ID,
  }
}
