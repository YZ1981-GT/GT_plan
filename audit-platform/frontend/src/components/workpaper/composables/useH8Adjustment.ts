/**
 * useH8Adjustment — H8-3 调整分录 composable（动态行，借贷平衡校验，EventBus publish）
 *
 * 10列：序号 | 摘要 | 科目编码 | 科目名称 | 借方金额 | 贷方金额 | 调整类型(AJE/RJE)
 *       | 对方科目 | 附件 | 备注
 *
 * 功能：
 * - 动态行CRUD
 * - 借贷平衡校验（借方合计=贷方合计）
 * - EventBus publish 'adjustment:created'
 * - 双向同步H8-1审定表AJE/RJE
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 3.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH8FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H8-3 调整分录行 */
export interface H8AdjustmentRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 摘要 */
  summary: string
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
  /** 调整类型：AJE审计调整/RJE重分类 */
  adjustType: 'AJE' | 'RJE'
  /** 对方科目 */
  counterAccount: string
  /** 附件标识 */
  attachment: string
  /** 备注 */
  remark: string
}

/** 借贷平衡校验结果 */
export interface BalanceCheck {
  debitTotal: number
  creditTotal: number
  diff: number
  isBalanced: boolean
  warning: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H8-3-rows'
const AJE_NET_KEY = 'H8-3-aje-net'
const RJE_NET_KEY = 'H8-3-rje-net'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  onPublishAdjustment?: (ajeNet: number, rjeNet: number) => void
}) {
  const { allResponses, onSave, onPublishAdjustment } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H8AdjustmentRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): H8AdjustmentRow {
    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: raw.seq ?? idx + 1,
      summary: raw.summary ?? '',
      accountCode: raw.accountCode ?? '',
      accountName: raw.accountName ?? '',
      debitAmount: Number(raw.debitAmount) || 0,
      creditAmount: Number(raw.creditAmount) || 0,
      adjustType: raw.adjustType === 'RJE' ? 'RJE' : 'AJE',
      counterAccount: raw.counterAccount ?? '',
      attachment: raw.attachment ?? '',
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

  const balanceCheck: ComputedRef<BalanceCheck> = computed(() => {
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
    const ajeRows = rows.value.filter(r => r.adjustType === 'AJE')
    return calcSubtotal(ajeRows.map(r => r.debitAmount)) - calcSubtotal(ajeRows.map(r => r.creditAmount))
  })

  /** RJE净额 */
  const rjeNet: ComputedRef<number> = computed(() => {
    const rjeRows = rows.value.filter(r => r.adjustType === 'RJE')
    return calcSubtotal(rjeRows.map(r => r.debitAmount)) - calcSubtotal(rjeRows.map(r => r.creditAmount))
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(adjustType: 'AJE' | 'RJE' = 'AJE'): void {
    const seq = rows.value.length + 1
    rows.value.push(_normalizeRow({ seq, adjustType }, seq - 1))
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

    const textFields = ['summary', 'accountCode', 'accountName', 'counterAccount', 'attachment', 'remark']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    if (field === 'adjustType') {
      row.adjustType = value === 'RJE' ? 'RJE' : 'AJE'
      _persist()
      return
    }

    const numVal = Number(value) || 0
    if (field === 'debitAmount') row.debitAmount = numVal
    else if (field === 'creditAmount') row.creditAmount = numVal
    else return

    _persist()
  }

  /** 发布调整事件（通知H8-1同步AJE/RJE） */
  function publishAdjustment(): void {
    onPublishAdjustment?.(ajeNet.value, rjeNet.value)
    // EventBus通知
    window.dispatchEvent(new CustomEvent('adjustment:created', {
      detail: { wpCode: 'H8', ajeNet: ajeNet.value, rjeNet: rjeNet.value },
    }))
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId, seq: r.seq, summary: r.summary,
      accountCode: r.accountCode, accountName: r.accountName,
      debitAmount: r.debitAmount, creditAmount: r.creditAmount,
      adjustType: r.adjustType, counterAccount: r.counterAccount,
      attachment: r.attachment, remark: r.remark,
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

export default useH8Adjustment
