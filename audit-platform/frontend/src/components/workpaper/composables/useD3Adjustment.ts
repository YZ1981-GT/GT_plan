/**
 * useD3Adjustment — D3-3 调整分录汇总表核心逻辑 composable
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 8.1
 *
 * 职责：
 * - 定义 AdjustmentRow 类型（10列）
 * - rows reactive（从D3-aje-rows加载JSON）
 * - debitTotal/creditTotal/isBalanced/balanceDiff computed
 * - addRow/removeRow/updateCell
 * - publishAdjustment（EventBus adjustment:created）
 * - pushToA13（EventBus推送选中分录至A13错报汇总）
 *
 * Requirements: 7.1-7.7, 18.2
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD3FormulaEngine'
import type { ChecklistResponse } from './useD3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjustmentRow {
  rowId: string
  description: string     // 调整事项说明
  category: string        // 类别（报表调整/账项调整/重分类调整/其他）
  reportItem: string      // 报表项目
  accountName: string     // 科目名称
  noteItem: string        // 附注项目
  placeholder: string     // 占位/辅助
  debitAmount: number     // 借方调整金额
  creditAmount: number    // 贷方调整金额
  indexRef: string        // 索引
  remark: string          // 备注
}

export interface UseD3AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D3-aje-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

/** 安全解析 JSON 数组 */
function safeParseRows(jsonStr: string | null | undefined): AdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

/** 规范化行数据，确保所有字段存在且类型正确 */
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

/** 创建空行（所有数值为 0） */
export function createEmptyAdjustmentRow(): AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '',
    category: '',
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

/**
 * 借贷平衡检查（纯函数，方便 PBT 测试）
 *
 * 返回 debitTotal、creditTotal、isBalanced（精确相等）、balanceDiff。
 */
export function checkBalance(rows: { debitAmount: number; creditAmount: number }[]): {
  debitTotal: number
  creditTotal: number
  isBalanced: boolean
  balanceDiff: number
} {
  const debitTotal = calcSubtotal(rows.map(r => r.debitAmount))
  const creditTotal = calcSubtotal(rows.map(r => r.creditAmount))
  const isBalanced = debitTotal === creditTotal
  const balanceDiff = debitTotal - creditTotal
  return { debitTotal, creditTotal, isBalanced, balanceDiff }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD3Adjustment(options: UseD3AdjustmentOptions) {
  const { allResponses, debouncedSave, isReadonly } = options

  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<AdjustmentRow[]>([])

  // Load rows from allResponses
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

  // ─── Computed: debitTotal / creditTotal / isBalanced / balanceDiff ────

  const debitTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.debitAmount)),
  )

  const creditTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.creditAmount)),
  )

  const isBalanced: ComputedRef<boolean> = computed(() =>
    debitTotal.value === creditTotal.value,
  )

  const balanceDiff: ComputedRef<number> = computed(() =>
    debitTotal.value - creditTotal.value,
  )

  // ─── addRow ──────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    const newRow = createEmptyAdjustmentRow()
    rows.value = [...rows.value, newRow]
    persistRows()
  }

  // ─── removeRow ───────────────────────────────────────────────────────

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  // ─── updateCell ──────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    if (field === 'debitAmount' || field === 'creditAmount') {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }

    const newRows = [...rows.value]
    newRows[idx] = row
    rows.value = newRows

    persistRows()
  }

  // ─── publishAdjustment ───────────────────────────────────────────────

  /**
   * 发布 adjustment:created 事件至 EventBus（CustomEvent on window）。
   * payload: { wpCode:'D3', entryType:'AJE'|'RJE', amount, accountCode:'2203' }
   */
  function publishAdjustment(row: AdjustmentRow): void {
    const entryType = row.category === '账项调整' ? 'AJE' : 'RJE'
    const event = new CustomEvent('adjustment:created', {
      detail: {
        wpCode: 'D3',
        entryType,
        amount: row.debitAmount,
        accountCode: '2203',
      },
    })
    window.dispatchEvent(event)
  }

  // ─── pushToA13 ──────────────────────────────────────────────────────

  /**
   * 推送选中分录至 A13 错报汇总（CustomEvent 'misstatement:push'）。
   * payload: { wpCode:'D3', rows: selected AdjustmentRow[] }
   */
  function pushToA13(rowIds: string[]): void {
    const selectedRows = rows.value.filter(r => rowIds.includes(r.rowId))
    if (selectedRows.length === 0) return

    const event = new CustomEvent('misstatement:push', {
      detail: {
        wpCode: 'D3',
        rows: selectedRows.map(r => ({
          description: r.description,
          category: r.category,
          reportItem: r.reportItem,
          accountName: r.accountName,
          debitAmount: r.debitAmount,
          creditAmount: r.creditAmount,
          indexRef: r.indexRef,
        })),
      },
    })
    window.dispatchEvent(event)
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
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

export default useD3Adjustment
