/**
 * useH9Adjustment — H9-5 调整分录 composable（10列+借贷平衡+EventBus）
 *
 * 10列：序号 | 调整事项说明 | 类别(AJE/RJE) | 报表项目 | 科目名称
 *       | 附注项目 | 借方金额 | 贷方金额 | 索引 | 备注
 *
 * 功能：
 * - 动态行CRUD
 * - 借贷平衡校验（Σ借方 === Σ贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步H9-1审定表AJE/RJE
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 3.4
 * Requirements: 5.1
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH9FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H9-5 调整分录行 */
export interface H9AdjustmentRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 调整事项说明 */
  description: string
  /** 类别：AJE审计调整/RJE重分类 */
  category: 'AJE' | 'RJE'
  /** 报表项目 */
  reportItem: string
  /** 科目名称 */
  accountName: string
  /** 附注项目 */
  noteItem: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
  /** 索引 */
  indexRef: string
  /** 备注 */
  remark: string
}

/** 借贷平衡校验结果 */
export interface H9BalanceCheck {
  debitTotal: number
  creditTotal: number
  diff: number
  isBalanced: boolean
  warning: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H9-5-rows'
const AJE_NET_KEY = 'H9-5-aje-net'
const RJE_NET_KEY = 'H9-5-rje-net'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  onPublishAdjustment?: (ajeNet: number, rjeNet: number) => void
}) {
  const { allResponses, onSave, onPublishAdjustment } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H9AdjustmentRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): H9AdjustmentRow {
    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: raw.seq ?? idx + 1,
      description: raw.description ?? '',
      category: raw.category === 'RJE' ? 'RJE' : 'AJE',
      reportItem: raw.reportItem ?? '',
      accountName: raw.accountName ?? '',
      noteItem: raw.noteItem ?? '',
      debitAmount: Number(raw.debitAmount) || 0,
      creditAmount: Number(raw.creditAmount) || 0,
      indexRef: raw.indexRef ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r: any, i: number) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 借贷合计+平衡校验 ──────────────────────────────────────────

  const debitTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.debitAmount)),
  )

  const creditTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.creditAmount)),
  )

  const balanceCheck: ComputedRef<H9BalanceCheck> = computed(() => {
    const diff = debitTotal.value - creditTotal.value
    const isBalanced = Math.abs(diff) < 0.01
    return {
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      diff,
      isBalanced,
      warning: isBalanced ? '' : `借贷不平衡，差额：${diff > 0 ? '+' : ''}${diff.toFixed(2)}元`,
    }
  })

  /** AJE净额（借方-贷方中AJE类型） */
  const ajeNet: ComputedRef<number> = computed(() => {
    const ajeRows = rows.value.filter(r => r.category === 'AJE')
    return calcSubtotal(ajeRows.map(r => r.debitAmount)) - calcSubtotal(ajeRows.map(r => r.creditAmount))
  })

  /** RJE净额 */
  const rjeNet: ComputedRef<number> = computed(() => {
    const rjeRows = rows.value.filter(r => r.category === 'RJE')
    return calcSubtotal(rjeRows.map(r => r.debitAmount)) - calcSubtotal(rjeRows.map(r => r.creditAmount))
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(category: 'AJE' | 'RJE' = 'AJE'): void {
    const seq = rows.value.length + 1
    rows.value.push(_normalizeRow({ seq, category }, seq - 1))
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

    const textFields = ['description', 'reportItem', 'accountName', 'noteItem', 'indexRef', 'remark']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    if (field === 'category') {
      row.category = value === 'RJE' ? 'RJE' : 'AJE'
      _persist()
      return
    }

    const numVal = Number(value) || 0
    if (field === 'debitAmount') row.debitAmount = numVal
    else if (field === 'creditAmount') row.creditAmount = numVal
    else return

    _persist()
  }

  /** 发布调整事件（通知H9-1同步AJE/RJE） */
  function publishAdjustment(): void {
    onPublishAdjustment?.(ajeNet.value, rjeNet.value)
    window.dispatchEvent(new CustomEvent('adjustment:created', {
      detail: { wpCode: 'H9', ajeNet: ajeNet.value, rjeNet: rjeNet.value },
    }))
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId, seq: r.seq, description: r.description,
      category: r.category, reportItem: r.reportItem, accountName: r.accountName,
      noteItem: r.noteItem, debitAmount: r.debitAmount, creditAmount: r.creditAmount,
      indexRef: r.indexRef, remark: r.remark,
    }))
    onSave(ROWS_KEY, toPersist)
    onSave(AJE_NET_KEY, ajeNet.value)
    onSave(RJE_NET_KEY, rjeNet.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, debitTotal, creditTotal, balanceCheck, ajeNet, rjeNet,
    addRow, deleteRow, updateCell, publishAdjustment, save, load,
  }
}

export default useH9Adjustment
