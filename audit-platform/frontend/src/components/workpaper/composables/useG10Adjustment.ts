/**
 * useG10Adjustment — G10-3 调整分录（回写 G10-1）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { G10_ACCOUNT_CODE } from './g10Constants'
import { calcG10AdjustmentNet } from './g10AdjStorage'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G10AdjustmentRow {
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

const ITEM_ID_ROWS = 'G10-aje-rows'

function genId(): string {
  return `g10a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function createEmptyG10AdjustmentRow(): G10AdjustmentRow {
  return {
    rowId: genId(),
    entryType: 'AJE',
    date: '',
    summary: '',
    accountCode: G10_ACCOUNT_CODE,
    accountName: '交易性金融负债',
    debitAmount: 0,
    creditAmount: 0,
    preparedBy: '',
    remark: '',
  }
}

function normalize(raw: any): G10AdjustmentRow {
  return {
    rowId: raw.rowId || raw.id || genId(),
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date || '',
    summary: raw.summary || raw.description || '',
    accountCode: raw.accountCode || G10_ACCOUNT_CODE,
    accountName: raw.accountName || '交易性金融负债',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy || '',
    remark: raw.remark || '',
  }
}

export function useG10Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  applyAdjustmentToAdjudication?: (net: number) => void
}) {
  const rows = ref<G10AdjustmentRow[]>([])

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => {
      if (!json) { rows.value = []; return }
      try {
        const parsed = JSON.parse(json)
        rows.value = Array.isArray(parsed) ? parsed.map(normalize) : []
      } catch {
        rows.value = []
      }
    },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
    syncWriteback()
  }

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() =>
    isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)),
  )
  const adjustmentNet = computed(() => calcG10AdjustmentNet(rows.value))

  function syncWriteback(): void {
    const net = adjustmentNet.value
    opts.applyAdjustmentToAdjudication?.(net)
    try {
      window.dispatchEvent(new CustomEvent('g10:adjustment-synced', { detail: { netAdjustment: net } }))
    } catch { /* silent */ }
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, createEmptyG10AdjustmentRow()]
    persist()
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateRow(rowId: string, patch: Partial<G10AdjustmentRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.rowId === rowId ? normalize({ ...r, ...patch }) : r))
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
    syncWriteback,
    ITEM_ID_ROWS,
  }
}
