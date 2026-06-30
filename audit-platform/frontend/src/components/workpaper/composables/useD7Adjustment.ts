/**
 * useD7Adjustment — D7-3 调整分录（10列，借贷平衡检查）
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 8.1
 * Requirements: 8.1-8.7, 18.2
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD7FormulaEngine'
import type { ChecklistResponse } from './useD7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjustmentRow {
  rowId: string
  description: string     // 调整事项说明
  category: string        // 类别（报表调整/账项调整/其他）
  reportItem: string      // 报表项目
  accountName: string     // 科目名称
  noteItem: string        // 附注项目
  placeholder: string     // 占位/对应项
  debitAmount: number     // 借方调整金额
  creditAmount: number    // 贷方调整金额
  indexRef: string        // 索引
  remark: string          // 备注
}

export interface UseD7AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D7-3-rows'

export const ADJUSTMENT_CATEGORIES = ['报表调整', '账项调整', '其他'] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `adj-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): AdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): AdjustmentRow {
  return {
    rowId: raw.rowId || generateRowId(),
    description: raw.description || '',
    category: raw.category || '',
    reportItem: raw.reportItem || '',
    accountName: raw.accountName || '',
    noteItem: raw.noteItem || '',
    placeholder: raw.placeholder || '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    indexRef: raw.indexRef || '',
    remark: raw.remark || '',
  }
}

function createEmptyRow(): AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '', category: '', reportItem: '',
    accountName: '', noteItem: '', placeholder: '',
    debitAmount: 0, creditAmount: 0,
    indexRef: '', remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7Adjustment(options: UseD7AdjustmentOptions) {
  const { allResponses, debouncedSave } = options

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<AdjustmentRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => { rows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── Computed ────────────────────────────────────────────────────────

  const debitTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.debitAmount)),
  )

  const creditTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.creditAmount)),
  )

  const isBalanced: ComputedRef<boolean> = computed(() =>
    Math.abs(debitTotal.value - creditTotal.value) <= 0.01,
  )

  const balanceDiff: ComputedRef<number> = computed(() =>
    debitTotal.value - creditTotal.value,
  )

  // ─── Add/Remove/Update ───────────────────────────────────────────────

  function addRow(): void {
    rows.value = [...rows.value, createEmptyRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    rows.value = rows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (field === 'debitAmount' || field === 'creditAmount') {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return updated
    })
    persistRows()
  }

  // ─── publishAdjustment ───────────────────────────────────────────────

  function publishAdjustment(row: AdjustmentRow): void {
    const entryType = row.debitAmount > 0 ? 'AJE' : 'RJE'
    const amount = row.debitAmount > 0 ? row.debitAmount : row.creditAmount
    try {
      window.dispatchEvent(new CustomEvent('adjustment:created', {
        detail: { wpCode: 'D7', entryType, amount, accountCode: '2205' },
      }))
    } catch { /* EventBus failure non-blocking */ }
  }

  // ─── pushToA13 ───────────────────────────────────────────────────────

  function pushToA13(rowIds: string[]): void {
    const selectedRows = rows.value.filter(r => rowIds.includes(r.rowId))
    if (selectedRows.length === 0) return
    try {
      window.dispatchEvent(new CustomEvent('misstatement:push', {
        detail: {
          wpCode: 'D7',
          accountCode: '2205',
          entries: selectedRows.map(r => ({
            description: r.description,
            debitAmount: r.debitAmount,
            creditAmount: r.creditAmount,
            category: r.category,
          })),
        },
      }))
    } catch { /* EventBus failure non-blocking */ }
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    debitTotal,
    creditTotal,
    isBalanced,
    balanceDiff,
    addRow,
    removeRow,
    updateCell,
    publishAdjustment,
    pushToA13,
  }
}

export default useD7Adjustment
