/**
 * useH4Adjustment — H4-3 调整分录 composable
 *
 * 10列：序号 | 调整事项说明 | 类别(AJE/RJE) | 科目代码 | 科目名称 | 摘要 | 借方金额 | 贷方金额 | 索引 | 备注
 *
 * 功能：
 * - 10-column adjustment entries
 * - 借贷平衡校验：debit合计 === credit合计
 * - EventBus publish 'adjustment:created'
 * - Sync AJE/RJE totals back to H4-1
 * - Saves to "H4-3-rows"
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 3.4
 * Requirements: 4.1-4.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H4-3 调整分录行 */
export interface H4AdjustmentRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 调整事项说明 */
  description: string
  /** 类别：AJE/RJE */
  entryType: 'AJE' | 'RJE'
  /** 科目代码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  /** 摘要 */
  summary: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
  /** 索引 */
  refIndex: string
  /** 备注 */
  remark: string
}

/** 借贷平衡状态 */
export interface BalanceStatus {
  debitTotal: number
  creditTotal: number
  diff: number
  isBalanced: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-3-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const { allResponses, onSave, onPublishEvent } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H4AdjustmentRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): H4AdjustmentRow {
    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: raw.seq ?? idx + 1,
      description: raw.description ?? '',
      entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
      accountCode: raw.accountCode ?? '',
      accountName: raw.accountName ?? '',
      summary: raw.summary ?? '',
      debitAmount: Number(raw.debitAmount) || 0,
      creditAmount: Number(raw.creditAmount) || 0,
      refIndex: raw.refIndex ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 借贷平衡 ────────────────────────────────────────────────────

  const balanceStatus: ComputedRef<BalanceStatus> = computed(() => {
    const debitTotal = calcSubtotal(rows.value.map(r => r.debitAmount))
    const creditTotal = calcSubtotal(rows.value.map(r => r.creditAmount))
    const diff = debitTotal - creditTotal
    return {
      debitTotal,
      creditTotal,
      diff,
      isBalanced: Math.abs(diff) < 0.01,
    }
  })

  /** AJE合计（借方-贷方净额，sync到H4-1） */
  const ajeTotalNet: ComputedRef<number> = computed(() => {
    const ajeRows = rows.value.filter(r => r.entryType === 'AJE')
    return calcSubtotal(ajeRows.map(r => r.debitAmount)) - calcSubtotal(ajeRows.map(r => r.creditAmount))
  })

  /** RJE合计（借方-贷方净额，sync到H4-1） */
  const rjeTotalNet: ComputedRef<number> = computed(() => {
    const rjeRows = rows.value.filter(r => r.entryType === 'RJE')
    return calcSubtotal(rjeRows.map(r => r.debitAmount)) - calcSubtotal(rjeRows.map(r => r.creditAmount))
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(): void {
    const seq = rows.value.length + 1
    rows.value.push(_normalizeRow({ seq }, seq - 1))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    // 重排序号
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    switch (field) {
      case 'description': row.description = String(value ?? ''); break
      case 'entryType': row.entryType = value === 'RJE' ? 'RJE' : 'AJE'; break
      case 'accountCode': row.accountCode = String(value ?? ''); break
      case 'accountName': row.accountName = String(value ?? ''); break
      case 'summary': row.summary = String(value ?? ''); break
      case 'debitAmount': row.debitAmount = Number(value) || 0; break
      case 'creditAmount': row.creditAmount = Number(value) || 0; break
      case 'refIndex': row.refIndex = String(value ?? ''); break
      case 'remark': row.remark = String(value ?? ''); break
      default: return
    }

    _persist()
  }

  /** 发布调整分录事件（保存成功后调用） */
  function publishAdjustmentCreated(): void {
    if (!onPublishEvent) return
    onPublishEvent('adjustment:created', {
      wpCode: 'H4',
      entryType: 'AJE/RJE',
      ajeTotal: ajeTotalNet.value,
      rjeTotal: rjeTotalNet.value,
      count: rows.value.length,
    })
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      seq: r.seq,
      description: r.description,
      entryType: r.entryType,
      accountCode: r.accountCode,
      accountName: r.accountName,
      summary: r.summary,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      refIndex: r.refIndex,
      remark: r.remark,
    }))
    onSave(ROWS_KEY, toPersist)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    // Computed
    balanceStatus,
    ajeTotalNet,
    rjeTotalNet,
    // Actions
    addRow,
    deleteRow,
    updateCell,
    save,
    load,
    publishAdjustmentCreated,
  }
}

export default useH4Adjustment
