/**
 * useH8LeaseModification — H8-7 租赁变更 composable（动态行，100行11列）
 *
 * 表格型：变更类型 | 原租赁条款 | 新条款 | 重新计量 | 会计处理
 *
 * CAS21第28-30条：
 * - 变更增加范围+价格合理→视为单独租赁
 * - 变更减少范围→按比例终止原租赁
 * - 其他变更→重新计量租赁负债+调整使用权资产
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 4.3, 4.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcRemeasurement } from './useH8CAS21Engine'
import { calcSubtotal } from './useH8FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 变更类型 */
export type H8ModificationType = '单独租赁' | '范围减少' | '其他变更' | ''

/** H8-7 租赁变更行 */
export interface H8LeaseModificationRow {
  rowId: string
  /** 合同号 */
  contractNo: string
  /** 变更日期 */
  modificationDate: string
  /** 变更类型 */
  modificationType: H8ModificationType
  /** 原租赁条款摘要 */
  originalTerms: string
  /** 新条款摘要 */
  newTerms: string
  /** 原使用权资产金额 */
  originalROUAmount: number
  /** 调整额 */
  adjustmentAmount: number
  /** 重新计量后使用权资产 */
  remeasuredROUAmount: number
  /** 会计处理说明 */
  accountingTreatment: string
  /** 结论 */
  conclusion: '是' | '否' | '不适用' | ''
  /** 备注 */
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H8-7-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8LeaseModification(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H8LeaseModificationRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any): H8LeaseModificationRow {
    const origROU = Number(raw.originalROUAmount) || 0
    const adj = Number(raw.adjustmentAmount) || 0
    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      contractNo: raw.contractNo ?? '',
      modificationDate: raw.modificationDate ?? '',
      modificationType: raw.modificationType ?? '',
      originalTerms: raw.originalTerms ?? '',
      newTerms: raw.newTerms ?? '',
      originalROUAmount: origROU,
      adjustmentAmount: adj,
      remeasuredROUAmount: calcRemeasurement(origROU, adj),
      accountingTreatment: raw.accountingTreatment ?? '',
      conclusion: raw.conclusion ?? '',
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

  /** 变更总调整额 */
  const totalAdjustment = computed(() =>
    calcSubtotal(rows.value.map(r => r.adjustmentAmount)),
  )

  /** 按变更类型统计 */
  const typeStats = computed(() => ({
    separateLease: rows.value.filter(r => r.modificationType === '单独租赁').length,
    scopeReduction: rows.value.filter(r => r.modificationType === '范围减少').length,
    otherModification: rows.value.filter(r => r.modificationType === '其他变更').length,
  }))

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

    const textFields = ['contractNo', 'modificationDate', 'modificationType', 'originalTerms', 'newTerms', 'accountingTreatment', 'conclusion', 'remark']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    const numVal = Number(value) || 0
    if (field === 'originalROUAmount') row.originalROUAmount = numVal
    else if (field === 'adjustmentAmount') row.adjustmentAmount = numVal
    else return

    // 重算重新计量后金额
    row.remeasuredROUAmount = calcRemeasurement(row.originalROUAmount, row.adjustmentAmount)
    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId, contractNo: r.contractNo, modificationDate: r.modificationDate,
      modificationType: r.modificationType, originalTerms: r.originalTerms,
      newTerms: r.newTerms, originalROUAmount: r.originalROUAmount,
      adjustmentAmount: r.adjustmentAmount, accountingTreatment: r.accountingTreatment,
      conclusion: r.conclusion, remark: r.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, totalAdjustment, typeStats,
    addRow, deleteRow, updateCell, save, load,
  }
}

export default useH8LeaseModification
