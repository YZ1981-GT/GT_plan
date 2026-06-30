/**
 * useD2WriteoffCheck — 转回核销D2-11核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 13.1
 *
 * 职责：
 * - WriteoffRow 类型定义（section:'reversal'|'writeoff', 8列）
 * - reversalRows / writeoffRows reactive
 * - reversalTotal / writeoffTotal computed
 * - reversalConsistencyWarning computed（与D2-3转回列对比）
 * - addRow(section) / removeRow / updateCell
 *
 * Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { parseNum } from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface WriteoffRow {
  rowId: string
  section: 'reversal' | 'writeoff'  // 转回 or 核销
  debtorName: string           // 债务人名称
  amount: number               // 金额
  originalDate: string         // 原确认日期
  reason: string               // 转回/核销原因
  approvalDoc: string          // 审批文件
  isReasonable: string         // 是否合理 (Y/N/'')
  auditorComment: string       // 审计师意见
  indexRef: string             // 索引号
}

// ─── Constants ───────────────────────────────────────────────────────────────

const REVERSAL_KEY = 'D2-writeoff-reversal-rows'
const WRITEOFF_KEY = 'D2-writeoff-writeoff-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `wo-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptyRow(section: 'reversal' | 'writeoff'): WriteoffRow {
  return {
    rowId: generateRowId(),
    section,
    debtorName: '',
    amount: 0,
    originalDate: '',
    reason: '',
    approvalDoc: '',
    isReasonable: '',
    auditorComment: '',
    indexRef: '',
  }
}

function parseRows(jsonStr: string | null | undefined, section: 'reversal' | 'writeoff'): WriteoffRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      section,
      debtorName: raw.debtorName || '',
      amount: parseNum(raw.amount),
      originalDate: raw.originalDate || '',
      reason: raw.reason || '',
      approvalDoc: raw.approvalDoc || '',
      isReasonable: raw.isReasonable || '',
      auditorComment: raw.auditorComment || '',
      indexRef: raw.indexRef || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2WriteoffCheck(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const reversalRows = ref<WriteoffRow[]>([])
  const writeoffRows = ref<WriteoffRow[]>([])
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    const revResp = allResponses.value.get(REVERSAL_KEY)
    reversalRows.value = parseRows(revResp?.remark, 'reversal')

    const woResp = allResponses.value.get(WRITEOFF_KEY)
    writeoffRows.value = parseRows(woResp?.remark, 'writeoff')
  }

  watch(
    () => [
      allResponses.value.get(REVERSAL_KEY)?.remark,
      allResponses.value.get(WRITEOFF_KEY)?.remark,
    ],
    () => {
      if (reversalRows.value.length === 0 && writeoffRows.value.length === 0) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── Totals ────────────────────────────────────────────────────────────

  const reversalTotal: ComputedRef<number> = computed(() => {
    return reversalRows.value.reduce((sum, r) => sum + r.amount, 0)
  })

  const writeoffTotal: ComputedRef<number> = computed(() => {
    return writeoffRows.value.reduce((sum, r) => sum + r.amount, 0)
  })

  // ─── Consistency Warning ───────────────────────────────────────────────

  /**
   * 转回一致性警告：与D2-3坏账准备表的转回列对比
   * 若差异不为0，发出警告
   */
  const reversalConsistencyWarning: ComputedRef<string | null> = computed(() => {
    // Read D2-3 bad debt reversal total from allResponses
    const bdIndJson = allResponses.value.get('D2-bd-individual-rows')?.remark
    const bdAgingJson = allResponses.value.get('D2-bd-aging-rows')?.remark
    const bdCustJson = allResponses.value.get('D2-bd-customer-rows')?.remark

    let bdReversalTotal = 0
    for (const json of [bdIndJson, bdAgingJson, bdCustJson]) {
      if (!json) continue
      try {
        const rows = JSON.parse(json)
        if (Array.isArray(rows)) {
          bdReversalTotal += rows.reduce((sum: number, r: any) => sum + parseNum(r.currentReversal), 0)
        }
      } catch {
        // silent
      }
    }

    if (bdReversalTotal === 0 && reversalTotal.value === 0) return null

    const diff = reversalTotal.value - bdReversalTotal
    if (Math.abs(diff) > 0.005) {
      return `转回检查合计(${reversalTotal.value.toFixed(2)})与D2-3坏账转回(${bdReversalTotal.toFixed(2)})差异${diff.toFixed(2)}元`
    }
    return null
  })

  // ─── Row Management ────────────────────────────────────────────────────

  function addRow(section: 'reversal' | 'writeoff'): void {
    if (isReadonly.value) return
    const newRow = createEmptyRow(section)
    if (section === 'reversal') {
      reversalRows.value.push(newRow)
    } else {
      writeoffRows.value.push(newRow)
    }
    debounceSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return

    let idx = reversalRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      reversalRows.value.splice(idx, 1)
      debounceSave()
      return
    }

    idx = writeoffRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      writeoffRows.value.splice(idx, 1)
      debounceSave()
      return
    }
  }

  // ─── Update Cell ───────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const row = [...reversalRows.value, ...writeoffRows.value].find(r => r.rowId === rowId)
    if (!row) return

    const key = field as keyof WriteoffRow
    if (key === 'rowId' || key === 'section') return

    if (key === 'amount') {
      row.amount = parseNum(value)
    } else {
      ;(row as any)[key] = String(value)
    }

    debounceSave()
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const items = [
      { item_id: REVERSAL_KEY, conclusion: null, remark: JSON.stringify(reversalRows.value) },
      { item_id: WRITEOFF_KEY, conclusion: null, remark: JSON.stringify(writeoffRows.value) },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    dispatchSaveEvent(items)
  }

  function dispatchSaveEvent(items: any[]): void {
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    reversalRows,
    writeoffRows,
    reversalTotal,
    writeoffTotal,
    reversalConsistencyWarning,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useD2WriteoffCheck
