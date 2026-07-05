/**
 * useG13Adjustment — G13-3 调整分录汇总
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useG13FormulaEngine'
import { mapCutoffToG13Adjustment, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'

export interface G13AdjustmentRow {
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

const ITEM_ID_ROWS = 'G13-aje-rows'

function generateRowId(): string {
  return `g13a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function createEmptyG13AdjustmentRow(): G13AdjustmentRow {
  return {
    rowId: generateRowId(),
    entryType: 'AJE',
    date: '',
    summary: '',
    accountCode: '6101',
    accountName: '公允价值变动收益',
    debitAmount: 0,
    creditAmount: 0,
    preparedBy: '',
    remark: '',
  }
}

function normalizeRow(raw: any): G13AdjustmentRow {
  return {
    rowId: raw.rowId || raw.id || generateRowId(),
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date || '',
    summary: raw.summary || raw.description || '',
    accountCode: raw.accountCode || '6101',
    accountName: raw.accountName || '公允价值变动收益',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy || '',
    remark: raw.remark || '',
  }
}

function parseRows(json: string | null | undefined): G13AdjustmentRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

export interface UseG13AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  applyAdjustmentToDetail?: (netAdjustment: number) => void
}

export function useG13Adjustment(options: UseG13AdjustmentOptions) {
  const rows = ref<G13AdjustmentRow[]>([])

  watch(
    () => options.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  function persist(): void {
    options.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => isDebitCreditBalanced(
    rows.value.map((r) => r.debitAmount),
    rows.value.map((r) => r.creditAmount),
  ))

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value = [...rows.value, createEmptyG13AdjustmentRow()]
    persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateCell(rowId: string, field: keyof G13AdjustmentRow, value: unknown): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...rows.value[idx] }
    if (field === 'debitAmount' || field === 'creditAmount') {
      row[field] = parseNum(value)
    } else if (field === 'entryType') {
      row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
    } else {
      ;(row as any)[field] = value
    }
    const next = [...rows.value]
    next[idx] = row
    rows.value = next
    persist()
  }

  function syncToDetail(): void {
    if (!options.applyAdjustmentToDetail) return
    const net = rows.value.reduce((s, r) => s + r.debitAmount - r.creditAmount, 0)
    options.applyAdjustmentToDetail(net)
    window.dispatchEvent(new CustomEvent('g13:adjustment-synced', { detail: { netAdjustment: net } }))
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (options.isReadonly.value || !samples.length) return
    const mapped = samples.map(mapCutoffToG13Adjustment)
    rows.value = mergeByFillMode(rows.value, mapped, fillMode, (r) => `${r.date}|${r.summary}|${r.debitAmount}|${r.creditAmount}`)
    persist()
  }

  return {
    rows,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    addRow,
    removeRow,
    updateCell,
    syncToDetail,
    applyCutoffResults,
    persist,
    ITEM_ID_ROWS,
  }
}
