/**
 * useH1Adjustment — H1-3 调整分录 composable
 *
 * H1AdjustmentRow 13列 + rows + debitTotal/creditTotal/isBalanced
 * addRow/removeRow/updateCell + publishAdjustment + pushToA13
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.5
 * Requirements: 4.1-4.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H1AdjustmentRow {
  rowId: string
  seq: number                   // 序号
  description: string           // 调整事项说明
  entryType: 'AJE' | 'RJE' | '' // 类别
  reportItem: string            // 报表项目
  accountCode: string           // 科目代码
  accountName: string           // 科目名称
  noteItem: string              // 附注项目
  summary: string               // 摘要
  debitAmount: number           // 借方金额
  creditAmount: number          // 贷方金额
  counterAccount: string        // 对方科目
  indexRef: string              // 索引
  remark: string                // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-3'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Adjustment(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H1AdjustmentRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    const raw = item?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow) : []
    } catch { rows.value = [] }
  }

  function _normalizeRow(raw: any, idx: number): H1AdjustmentRow {
    return {
      rowId: raw.rowId ?? `adj-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      description: raw.description ?? '',
      entryType: raw.entryType ?? '',
      reportItem: raw.reportItem ?? '',
      accountCode: raw.accountCode ?? '',
      accountName: raw.accountName ?? '',
      noteItem: raw.noteItem ?? '',
      summary: raw.summary ?? '',
      debitAmount: Number(raw.debitAmount) || 0,
      creditAmount: Number(raw.creditAmount) || 0,
      counterAccount: raw.counterAccount ?? '',
      indexRef: raw.indexRef ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const isBalanced = computed(() => Math.abs(debitTotal.value - creditTotal.value) < 0.01)
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(): void {
    const newRow: H1AdjustmentRow = {
      rowId: `adj-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1,
      description: '',
      entryType: 'AJE',
      reportItem: '',
      accountCode: '',
      accountName: '',
      noteItem: '',
      summary: '',
      debitAmount: 0,
      creditAmount: 0,
      counterAccount: '',
      indexRef: '',
      remark: '',
    }
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      // 重编序号
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      _persist()
    }
  }

  function updateCell(rowId: string, field: keyof H1AdjustmentRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }

  // ─── publishAdjustment（EventBus → H1-1 AJE/RJE同步）──────────────────────

  function publishAdjustment(): void {
    options?.onPublishEvent?.('adjustment:created', {
      wp_code: 'H1',
      rows: rows.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
    })
  }

  // ─── pushToA13（推送至错报汇总）────────────────────────────────────────────

  function pushToA13(rowIds?: string[]): void {
    const targets = rowIds
      ? rows.value.filter((r) => rowIds.includes(r.rowId))
      : rows.value
    options?.onPublishEvent?.('adjustment:push-to-a13', {
      wp_code: 'H1',
      entries: targets.map((r) => ({
        description: r.description,
        entryType: r.entryType,
        accountCode: r.accountCode,
        accountName: r.accountName,
        debitAmount: r.debitAmount,
        creditAmount: r.creditAmount,
      })),
    })
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

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

export default useH1Adjustment
