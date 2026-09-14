/**
 * useD4Adjustment — D4-4 调整分录 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 6.4
 *
 * 职责：
 * - D4AdjustmentRow 10列 + rows reactive
 * - debitTotal / creditTotal computed
 * - isBalanced computed (debit === credit)
 * - balanceDiff computed
 * - addRow / removeRow / updateCell
 * - publishAdjustment (EventBus 'adjustment:created')
 * - pushToA13 (EventBus 推送选中分录到A13错报汇总)
 *
 * Requirements: 5.1-5.7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum } from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'
import { eventBus } from '@/utils/eventBus'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface D4AdjustmentRow {
  rowId: string
  description: string
  category: string        // 报表调整/账项调整/其他
  reportItem: string
  accountName: string
  noteItem: string
  placeholder: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D4-4-rows'
const BALANCE_TOLERANCE = 0.005

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `d4a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptyRow(): D4AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '',
    category: '账项调整',
    reportItem: '',
    accountName: '',
    noteItem: '',
    placeholder: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: '',
    remark: '',
  }
}

function safeParseRows(jsonStr: string | null | undefined): D4AdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      description: raw.description || '',
      category: raw.category || '账项调整',
      reportItem: raw.reportItem || '',
      accountName: raw.accountName || '',
      noteItem: raw.noteItem || '',
      placeholder: raw.placeholder || '',
      debitAmount: parseNum(raw.debitAmount),
      creditAmount: parseNum(raw.creditAmount),
      indexRef: raw.indexRef || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4Adjustment(options: UseD4BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Reactive State ──────────────────────────────────────────────────

  const rows = ref<D4AdjustmentRow[]>([])

  // ─── Load from allResponses ──────────────────────────────────────────

  function loadRows(): void {
    const resp = allResponses.value.get(STORAGE_KEY)
    rows.value = safeParseRows(resp?.remark)
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => {
      if (rows.value.length === 0) {
        loadRows()
      }
    },
    { immediate: true },
  )

  // ─── Computed: Totals & Balance ──────────────────────────────────────

  const debitTotal: ComputedRef<number> = computed(() => {
    return rows.value.reduce((sum, r) => sum + parseNum(r.debitAmount), 0)
  })

  const creditTotal: ComputedRef<number> = computed(() => {
    return rows.value.reduce((sum, r) => sum + parseNum(r.creditAmount), 0)
  })

  const balanceDiff: ComputedRef<number> = computed(() => {
    return debitTotal.value - creditTotal.value
  })

  const isBalanced: ComputedRef<boolean> = computed(() => {
    return Math.abs(balanceDiff.value) < BALANCE_TOLERANCE
  })

  // ─── Row Operations ──────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    rows.value.push(createEmptyRow())
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const key = field as keyof D4AdjustmentRow
    if (key === 'rowId') return

    if (key === 'debitAmount' || key === 'creditAmount') {
      ;(row as any)[key] = parseNum(value)
    } else {
      ;(row as any)[key] = String(value ?? '')
    }

    // category (dropdown) → immediate save; others → debounce
    if (key === 'category') {
      immediatelySave()
    } else {
      debounceSave()
    }
  }

  // ─── EventBus: publishAdjustment ─────────────────────────────────────

  /**
   * 发布 'adjustment:created' 事件（经 crossWpEventBridge 双通道桥接）
   * payload: { wpCode:'D4', entryType, amount, accountCode, description }
   */
  function publishAdjustment(): void {
    for (const row of rows.value) {
      if (row.debitAmount === 0 && row.creditAmount === 0) continue
      const payload = {
        wpCode: 'D4',
        entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
        amount: Math.max(row.debitAmount, row.creditAmount),
        accountCode: row.accountName,
        description: row.description,
      }
      eventBus.emit('adjustment:created', payload)
    }
  }

  // ─── EventBus: pushToA13 ─────────────────────────────────────────────

  /**
   * 推送选中分录到 A13 错报汇总
   */
  function pushToA13(rowIds: string[]): void {
    const selected = rows.value.filter(r => rowIds.includes(r.rowId))
    if (selected.length === 0) return

    const misstatements = selected.map(row => ({
      wpCode: 'D4',
      entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
      description: row.description,
      reportItem: row.reportItem,
      accountName: row.accountName,
      debitAmount: row.debitAmount,
      creditAmount: row.creditAmount,
      indexRef: row.indexRef,
    }))

    eventBus.emit('a13:push-misstatement', { items: misstatements })
  }

  // ─── Persist / Save ──────────────────────────────────────────────────

  function persistRows(): void {
    const json = JSON.stringify(rows.value)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function immediatelySave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    flushSave()
  }

  function flushSave(): void {
    const json = JSON.stringify(rows.value)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    try {
      window.dispatchEvent(new CustomEvent('d4:save-items', {
        detail: { items: [{ item_id: STORAGE_KEY, conclusion: null, remark: json }] },
      }))
    } catch { /* silent */ }
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

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

export default useD4Adjustment
