/**
 * useD6Adjustment — D6-4 调整分录（10列）
 *
 * 职责：
 *   - 管理调整分录行数据（AJE/RJE）
 *   - 借贷平衡验证：isBalanced = (debitTotal === creditTotal)
 *   - publishAdjustment: EventBus 'adjustment:created' 通知D6-1
 *   - pushToA13: EventBus 推送选中分录至A13错报汇总
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 9.1
 * Requirements: 9.1-9.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjustmentRow {
  rowId: string
  description: string     // 调整事项说明
  category: string        // 类别（AJE/RJE）
  reportItem: string      // 报表项目
  accountName: string     // 科目名称
  noteItem: string        // 附注项目
  placeholder: string     // 预留
  debitAmount: number     // 借方调整金额
  creditAmount: number    // 贷方调整金额
  indexRef: string        // 索引
  remark: string          // 备注
}

export interface UseD6AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D6-4-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
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
    category: raw.category || '账项调整',
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

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6Adjustment(options: UseD6AdjustmentOptions) {
  const { allResponses, debouncedSave } = options

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<AdjustmentRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => {
      rows.value = safeParseRows(jsonStr)
    },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── Computed: Balance ───────────────────────────────────────────────

  const debitTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.debitAmount)),
  )

  const creditTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.creditAmount)),
  )

  const balanceDiff: ComputedRef<number> = computed(() =>
    debitTotal.value - creditTotal.value,
  )

  const isBalanced: ComputedRef<boolean> = computed(() =>
    Math.abs(balanceDiff.value) < 0.01,
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

  const NUMERIC_FIELDS = ['debitAmount', 'creditAmount']

  function updateCell(rowId: string, field: string, value: any): void {
    rows.value = rows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (NUMERIC_FIELDS.includes(field)) {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return updated
    })
    persistRows()
  }

  // ─── EventBus Actions ────────────────────────────────────────────────

  /**
   * 发布 'adjustment:created' 事件（遍历全部行）
   * → D6-1 监听更新 AJE/RJE
   */
  function publishAdjustment(): void {
    for (const row of rows.value) {
      if (row.debitAmount === 0 && row.creditAmount === 0) continue
      const payload = {
        wpCode: 'D6',
        entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
        amount: Math.max(row.debitAmount, row.creditAmount),
        accountCode: row.accountName || '1402',
        description: row.description,
      }
      try {
        window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
      } catch { /* silent */ }
    }
  }

  /**
   * 推送选中分录至 A13 错报汇总
   */
  function pushToA13(rowIds: string[]): void {
    const selected = rows.value.filter(r => rowIds.includes(r.rowId))
    if (selected.length === 0) return

    const misstatements = selected.map(row => ({
      wpCode: 'D6',
      entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
      description: row.description,
      reportItem: row.reportItem,
      accountName: row.accountName,
      debitAmount: row.debitAmount,
      creditAmount: row.creditAmount,
      indexRef: row.indexRef,
    }))

    try {
      window.dispatchEvent(new CustomEvent('a13:push-misstatement', {
        detail: { items: misstatements },
      }))
    } catch { /* silent */ }
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

export default useD6Adjustment
