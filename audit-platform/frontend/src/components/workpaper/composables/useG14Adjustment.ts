/**
 * useG14Adjustment — G14-3 调整分录汇总（与 D3 调整分录模块同构）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useG14FormulaEngine'
import { mapCutoffToG14Adjustment, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'
export interface G14AdjustmentRow {
  rowId: string
  description: string
  category: string
  reportItem: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}

const ITEM_ID_ROWS = 'G14-aje-rows'

function generateRowId(): string {
  return `g14a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function createEmptyG14AdjustmentRow(): G14AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '',
    category: '',
    reportItem: '信用减值损失',
    accountName: '',
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: '',
    remark: '',
  }
}

function normalizeRow(raw: any): G14AdjustmentRow {
  return {
    rowId: raw.rowId || raw.id || generateRowId(),
    description: raw.description || '',
    category: raw.category || '',
    reportItem: raw.reportItem || '信用减值损失',
    accountName: raw.accountName || '',
    noteItem: raw.noteItem || '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    indexRef: raw.indexRef || '',
    remark: raw.remark || '',
  }
}

function parseRows(json: string | null | undefined): G14AdjustmentRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

export interface UseG14AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  /** 账项调整净额回写 G14-2「其他」行调整数 */
  applyAdjustmentToDetail?: (netAdjustment: number) => void
}

export function useG14Adjustment(options: UseG14AdjustmentOptions) {
  const rows = ref<G14AdjustmentRow[]>([])

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
    rows.value = [...rows.value, createEmptyG14AdjustmentRow()]
    persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateCell(rowId: string, field: keyof G14AdjustmentRow, value: unknown): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...rows.value[idx] }
    if (field === 'debitAmount' || field === 'creditAmount') {
      row[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }
    const next = [...rows.value]
    next[idx] = row
    rows.value = next
    persist()
  }

  /** 账项调整借方−贷方净额同步至明细表 */
  function syncToDetail(): void {
    if (!options.applyAdjustmentToDetail) return
    const net = rows.value
      .filter((r) => r.category === '账项调整')
      .reduce((s, r) => s + r.debitAmount - r.creditAmount, 0)
    options.applyAdjustmentToDetail(net)
    window.dispatchEvent(new CustomEvent('g14:adjustment-synced', { detail: { netAdjustment: net } }))
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (options.isReadonly.value || !samples.length) return
    const mapped = samples.map(mapCutoffToG14Adjustment)
    rows.value = mergeByFillMode(rows.value, mapped, fillMode, (r) => r.indexRef || `${r.description}|${r.debitAmount}`)
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