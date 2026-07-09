/**
 * useH8DisposalCheck — H8-12 减少检查表 composable（39行28列）
 *
 * 核心公式：终止损益 = 租赁负债余额 - 使用权资产净值
 *
 * 28列含：合同号/终止原因/终止日/剩余期/使用权净值/租赁负债余额/终止损益/审批
 * H9同步：终止时租赁负债也应终止确认
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 7.3-7.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcTerminationGainLoss } from './useH8CAS21Engine'
import { calcSubtotal } from './useH8FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H8-12 减少检查行 */
export interface H8DisposalCheckRow {
  rowId: string
  /** 合同号 */
  contractNo: string
  /** 承租资产 */
  assetName: string
  /** 终止原因 */
  terminationReason: string
  /** 终止日期 */
  terminationDate: string
  /** 剩余租赁期（月） */
  remainingMonths: number
  /** 使用权资产净值 */
  rouNetValue: number
  /** 租赁负债余额 */
  liabilityBalance: number
  /** 终止损益（公式：=负债余额-净值） */
  gainLoss: number
  /** 是否已通知H9同步终止 */
  h9Synced: boolean
  /** 审批状态 */
  approvalStatus: '已审批' | '待审批' | ''
  /** 审批人 */
  approver: string
  /** 备注 */
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H8-12-rows'
const GAIN_LOSS_TOTAL_KEY = 'H8-12-gain-loss-total'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8DisposalCheck(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  onSyncH9?: (contractNo: string, liabilityBalance: number) => void
}) {
  const { allResponses, onSave, onSyncH9 } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H8DisposalCheckRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any): H8DisposalCheckRow {
    const netValue = Number(raw.rouNetValue) || 0
    const liability = Number(raw.liabilityBalance) || 0
    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      contractNo: raw.contractNo ?? '',
      assetName: raw.assetName ?? '',
      terminationReason: raw.terminationReason ?? '',
      terminationDate: raw.terminationDate ?? '',
      remainingMonths: Number(raw.remainingMonths) || 0,
      rouNetValue: netValue,
      liabilityBalance: liability,
      gainLoss: calcTerminationGainLoss(liability, netValue),
      h9Synced: raw.h9Synced ?? false,
      approvalStatus: raw.approvalStatus ?? '',
      approver: raw.approver ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 终止损益合计 */
  const gainLossTotal = computed(() =>
    calcSubtotal(rows.value.map(r => r.gainLoss)),
  )

  /** 收益笔数 */
  const gainCount = computed(() =>
    rows.value.filter(r => r.gainLoss > 0).length,
  )

  /** 损失笔数 */
  const lossCount = computed(() =>
    rows.value.filter(r => r.gainLoss < 0).length,
  )

  /** 未同步H9的行 */
  const unsyncedRows = computed(() =>
    rows.value.filter(r => !r.h9Synced),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(contractNo: string): void {
    if (!contractNo?.trim()) return
    rows.value.push(_normalizeRow({ contractNo: contractNo.trim() }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const textFields = ['contractNo', 'assetName', 'terminationReason', 'terminationDate', 'approvalStatus', 'approver', 'remark']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    if (field === 'h9Synced') {
      row.h9Synced = Boolean(value)
      _persist()
      return
    }

    const numVal = Number(value) || 0
    if (field === 'rouNetValue') row.rouNetValue = numVal
    else if (field === 'liabilityBalance') row.liabilityBalance = numVal
    else if (field === 'remainingMonths') { row.remainingMonths = numVal; _persist(); return }
    else return

    // 重算终止损益
    row.gainLoss = calcTerminationGainLoss(row.liabilityBalance, row.rouNetValue)
    _persist()
  }

  /** 同步终止到H9（通知H9也应终止确认该笔租赁负债） */
  function syncToH9(rowId: string): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return
    row.h9Synced = true
    onSyncH9?.(row.contractNo, row.liabilityBalance)
    // EventBus通知H9
    window.dispatchEvent(new CustomEvent('h8:lease-terminated', {
      detail: { contractNo: row.contractNo, liabilityBalance: row.liabilityBalance },
    }))
    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId, contractNo: r.contractNo, assetName: r.assetName,
      terminationReason: r.terminationReason, terminationDate: r.terminationDate,
      remainingMonths: r.remainingMonths, rouNetValue: r.rouNetValue,
      liabilityBalance: r.liabilityBalance, h9Synced: r.h9Synced,
      approvalStatus: r.approvalStatus, approver: r.approver, remark: r.remark,
    })))
    onSave(GAIN_LOSS_TOTAL_KEY, gainLossTotal.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, gainLossTotal, gainCount, lossCount, unsyncedRows,
    addRow, deleteRow, updateCell, syncToH9, save, load,
  }
}

export default useH8DisposalCheck
