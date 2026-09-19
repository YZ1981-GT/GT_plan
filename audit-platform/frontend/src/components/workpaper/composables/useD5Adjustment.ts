/**
 * useD5Adjustment — D5-3 调整分录汇总表核心逻辑 composable
 *
 * Spec: .kiro/specs/d5-receivables-financing/
 * Task: 9.1
 *
 * 职责：
 * - 定义 AdjustmentRow 类型（10列）
 * - rows reactive（从D5-3-rows加载JSON）
 * - debitTotal/creditTotal/isBalanced/balanceDiff computed
 * - addRow/removeRow/updateCell
 * - publishAdjustment（EventBus adjustment:created，payload含wpCode='D5'/entryType/amount）
 * - pushToA13（EventBus推送选中分录至A13错报汇总）
 *
 * Requirements: 7.1-7.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD5FormulaEngine'
import type { ChecklistResponse } from './useD5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjustmentRow {
  rowId: string
  description: string     // 调整事项说明
  category: string        // 类别（报表调整/账项调整/其他）
  reportItem: string      // 报表项目
  accountName: string     // 科目名称
  noteItem: string        // 附注项目
  placeholder: string     // 占位/辅助
  debitAmount: number     // 借方调整金额
  creditAmount: number    // 贷方调整金额
  indexRef: string        // 索引
  remark: string          // 备注
}

export interface UseD5AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D5-3-rows'

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
 * 返回 debitTotal、creditTotal、isBalanced（浮点精度: Math.abs(diff) < 0.01）、balanceDiff。
 */
export function checkBalance(rows: { debitAmount: number; creditAmount: number }[]): {
  debitTotal: number
  creditTotal: number
  isBalanced: boolean
  balanceDiff: number
} {
  const debitTotal = calcSubtotal(rows.map(r => r.debitAmount))
  const creditTotal = calcSubtotal(rows.map(r => r.creditAmount))
  const balanceDiff = debitTotal - creditTotal
  const isBalanced = Math.abs(balanceDiff) < 0.01
  return { debitTotal, creditTotal, isBalanced, balanceDiff }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD5Adjustment(options: UseD5AdjustmentOptions) {
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

  const balanceDiff: ComputedRef<number> = computed(() =>
    debitTotal.value - creditTotal.value,
  )

  const isBalanced: ComputedRef<boolean> = computed(() =>
    Math.abs(balanceDiff.value) < 0.01,
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
   * payload: { wpCode:'D5', entryType:'AJE'|'RJE', amount, accountCode:'1124' }
   *
   * entryType 判定：category === '账项调整' → 'AJE'，否则 → 'RJE'
   */
  function publishAdjustment(row: AdjustmentRow): void {
    const entryType = row.category === '账项调整' ? 'AJE' : 'RJE'
    const event = new CustomEvent('adjustment:created', {
      detail: {
        wpCode: 'D5',
        entryType,
        amount: row.debitAmount - row.creditAmount,
        accountCode: '1124',
      },
    })
    window.dispatchEvent(event)
  }

  // ─── pushToA13 ──────────────────────────────────────────────────────

  /**
   * 推送选中分录至 A13 错报汇总（CustomEvent 'a13:push-misstatement'）。
   * payload: { wpCode:'D5', rows: selected AdjustmentRow[] }
   */
  function pushToA13(rowIds: string[]): void {
    const selectedRows = rows.value.filter(r => rowIds.includes(r.rowId))
    if (selectedRows.length === 0) return

    const event = new CustomEvent('a13:push-misstatement', {
      detail: {
        wpCode: 'D5',
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

export default useD5Adjustment
