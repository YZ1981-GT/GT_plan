/**
 * useH2Adjustment — H2-3 调整分录 composable
 *
 * 职责：
 * - H2AdjustmentRow 10列 + rows + debitTotal/creditTotal/isBalanced
 * - addRow/removeRow/updateCell + publishAdjustment + pushToA13
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.5
 * Requirements: 4.1-4.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { isBalanced as checkBalanced, calcSubtotal } from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2AdjustmentRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 调整事项说明 */
  description: string
  /** 类别(AJE/RJE) */
  entryType: 'AJE' | 'RJE'
  /** 科目代码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  /** 摘要 */
  summary: string
  /** 借方金额 */
  debit: number
  /** 贷方金额 */
  credit: number
  /** 索引 */
  indexRef: string
  /** 备注 */
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-3-rows'
const NOTE_KEY = 'H2-3-audit-note'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Adjustment(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H2AdjustmentRow[]>([])
  const auditNote = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r: any, i: number) => ({
        rowId: r.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
        seq: r.seq ?? (i + 1),
        description: r.description ?? '',
        entryType: r.entryType === 'RJE' ? 'RJE' : 'AJE',
        accountCode: r.accountCode ?? '',
        accountName: r.accountName ?? '',
        summary: r.summary ?? '',
        debit: Number(r.debit) || 0,
        credit: Number(r.credit) || 0,
        indexRef: r.indexRef ?? '',
        remark: r.remark ?? '',
      }))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const debitTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.debit)),
  )

  const creditTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.credit)),
  )

  const isBalanced: ComputedRef<boolean> = computed(() =>
    checkBalanced(rows.value.map(r => ({ debit: r.debit, credit: r.credit }))),
  )

  const balanceDiff: ComputedRef<number> = computed(() =>
    debitTotal.value - creditTotal.value,
  )

  /** AJE类合计 */
  const ajeTotals = computed(() => {
    const ajeRows = rows.value.filter(r => r.entryType === 'AJE')
    return {
      debit: calcSubtotal(ajeRows.map(r => r.debit)),
      credit: calcSubtotal(ajeRows.map(r => r.credit)),
    }
  })

  /** RJE类合计 */
  const rjeTotals = computed(() => {
    const rjeRows = rows.value.filter(r => r.entryType === 'RJE')
    return {
      debit: calcSubtotal(rjeRows.map(r => r.debit)),
      credit: calcSubtotal(rjeRows.map(r => r.credit)),
    }
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(): void {
    if (options.isReadonly.value) return
    const newRow: H2AdjustmentRow = {
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1,
      description: '',
      entryType: 'AJE',
      accountCode: '',
      accountName: '',
      summary: '',
      debit: 0,
      credit: 0,
      indexRef: '',
      remark: '',
    }
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    // 重新排序
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    switch (field) {
      case 'debit':
        row.debit = Number(value) || 0
        break
      case 'credit':
        row.credit = Number(value) || 0
        break
      case 'entryType':
        row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
        break
      default:
        if (field in row) {
          ;(row as any)[field] = String(value ?? '')
        }
    }
    _persist()
  }

  /** 发布调整分录事件（→H2-1同步+A13） */
  function publishAdjustment(): void {
    if (!options.onPublishEvent) return
    options.onPublishEvent('adjustment:created', {
      wpCode: 'H2',
      entryType: 'mixed',
      ajeTotals: ajeTotals.value,
      rjeTotals: rjeTotals.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
    })
  }

  /** 推送选中分录至A13错报汇总 */
  function pushToA13(rowIds: string[]): void {
    if (!options.onPublishEvent) return
    const selected = rows.value.filter(r => rowIds.includes(r.rowId))
    if (selected.length === 0) return
    options.onPublishEvent('adjustment:push-to-a13', {
      wpCode: 'H2',
      entries: selected.map(r => ({
        description: r.description,
        entryType: r.entryType,
        accountCode: r.accountCode,
        accountName: r.accountName,
        debit: r.debit,
        credit: r.credit,
      })),
    })
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!options.onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      seq: r.seq,
      description: r.description,
      entryType: r.entryType,
      accountCode: r.accountCode,
      accountName: r.accountName,
      summary: r.summary,
      debit: r.debit,
      credit: r.credit,
      indexRef: r.indexRef,
      remark: r.remark,
    }))
    options.onSave(ROWS_KEY, toPersist)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    auditNote,
    debitTotal,
    creditTotal,
    isBalanced,
    balanceDiff,
    ajeTotals,
    rjeTotals,
    addRow,
    removeRow,
    updateCell,
    publishAdjustment,
    pushToA13,
    saveNote,
    initFromAllResponses,
  }
}

export default useH2Adjustment
