/**
 * useH3Adjustment — H3-3 调整分录 composable
 *
 * H3AdjustmentRow 10列 + debitTotal/creditTotal/isBalanced
 * + addRow/removeRow/updateCell + publishAdjustment + pushToA13
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.8
 * Requirements: 4.1-4.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H3AdjustmentRow {
  rowId: string
  seq: number
  description: string         // 调整事项说明
  entryType: 'AJE' | 'RJE' | ''
  accountCode: string         // 科目代码
  accountName: string         // 科目名称
  summary: string             // 摘要
  debitAmount: number         // 借方金额
  creditAmount: number        // 贷方金额
  indexRef: string            // 索引
  remark: string              // 备注
}

const ITEM_ID = 'H3-3-adj-rows'

export function useH3Adjustment(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params
  const rows = ref<H3AdjustmentRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any, idx?: number): H3AdjustmentRow {
    return {
      rowId: raw.rowId ?? `adj-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      description: raw.description ?? '',
      entryType: raw.entryType ?? '',
      accountCode: raw.accountCode ?? '',
      accountName: raw.accountName ?? '',
      summary: raw.summary ?? '',
      debitAmount: Number(raw.debitAmount) || 0,
      creditAmount: Number(raw.creditAmount) || 0,
      indexRef: raw.indexRef ?? '',
      remark: raw.remark ?? '',
    }
  }

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanced = computed(() => Math.abs(debitTotal.value - creditTotal.value) < 0.01)

  function addRow(): void {
    rows.value.push(_normalize({ seq: rows.value.length + 1, entryType: 'AJE' }))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(index: number, field: keyof H3AdjustmentRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }

  /** 发布调整分录事件（→H3-1 AJE/RJE同步） */
  function publishAdjustment(): void {
    window.dispatchEvent(new CustomEvent('adjustment:created', {
      detail: { wp_code: 'H3', rows: rows.value, debitTotal: debitTotal.value, creditTotal: creditTotal.value },
    }))
  }

  /** 推送错报至A13 */
  function pushToA13(rowIds?: string[]): void {
    const targets = rowIds
      ? rows.value.filter((r) => rowIds.includes(r.rowId))
      : rows.value
    window.dispatchEvent(new CustomEvent('adjustment:push-to-a13', {
      detail: { wp_code: 'H3', entries: targets },
    }))
  }

  function _persist(): void { setValue(ITEM_ID, rows.value) }
  watch(allResponses, () => loadRows(), { immediate: true })

  return { rows, debitTotal, creditTotal, isBalanced: balanced, addRow, removeRow, updateCell, publishAdjustment, pushToA13 }
}

export default useH3Adjustment
