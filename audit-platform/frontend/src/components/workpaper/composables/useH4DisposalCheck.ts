/**
 * useH4DisposalCheck — H4-5 减少检查表 composable
 *
 * 29列分2区块：
 * 基础(序号/物资名/规格/数量/金额/减少原因/日期)
 * 证据(领料单号/领用部门/领用工程项目/审批人/对应H2编号/核查结论/备注/索引)
 *
 * 功能：
 * - 减少原因 dropdown options
 * - H2联动: when reason='领用出库', require H2 ref
 * - Saves to "H4-5-rows"
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 3.4
 * Requirements: 6.1-6.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H4-5 减少检查行 */
export interface H4DisposalCheckRow {
  rowId: string
  /** 序号 */
  seq: number

  // ═══ 区块1: 基础 ═══
  /** 物资名称 */
  name: string
  /** 规格型号 */
  spec: string
  /** 数量 */
  quantity: number
  /** 金额 */
  amount: number
  /** 减少原因 */
  reason: DisposalReason
  /** 减少日期 */
  disposalDate: string

  // ═══ 区块2: 证据 ═══
  /** 领料单号 */
  pickingNo: string
  /** 领用部门 */
  department: string
  /** 领用工程项目 */
  projectName: string
  /** 审批人 */
  approver: string
  /** 对应H2编号（领用出库时必填） */
  h2Ref: string
  /** 抽凭结果 */
  voucherResult: string
  /** 核查结论 */
  conclusion: string
  /** 备注 */
  remark: string
  /** 索引 */
  refIndex: string
}

/** 减少原因枚举 */
export type DisposalReason = '领用出库' | '退货' | '报废' | '盘亏' | '其他' | ''

/** 减少原因下拉选项 */
export const DISPOSAL_REASON_OPTIONS: DisposalReason[] = [
  '领用出库',
  '退货',
  '报废',
  '盘亏',
  '其他',
]

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-5-rows'
const DISPOSAL_TOTAL_KEY = 'H4-5-disposal-total'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4DisposalCheck(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H4DisposalCheckRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): H4DisposalCheckRow {
    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      spec: raw.spec ?? '',
      quantity: Number(raw.quantity) || 0,
      amount: Number(raw.amount) || 0,
      reason: (DISPOSAL_REASON_OPTIONS.includes(raw.reason) ? raw.reason : '') as DisposalReason,
      disposalDate: raw.disposalDate ?? '',
      pickingNo: raw.pickingNo ?? '',
      department: raw.department ?? '',
      projectName: raw.projectName ?? '',
      approver: raw.approver ?? '',
      h2Ref: raw.h2Ref ?? '',
      voucherResult: raw.voucherResult ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      refIndex: raw.refIndex ?? '',
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

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 减少合计金额（供CrossSheet使用） */
  const disposalTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.amount)),
  )

  /** 需要H2关联但未填写的行（领用出库且h2Ref为空） */
  const missingH2Refs: ComputedRef<H4DisposalCheckRow[]> = computed(() =>
    rows.value.filter(r => r.reason === '领用出库' && !r.h2Ref.trim()),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(name: string): void {
    if (!name?.trim()) return
    const seq = rows.value.length + 1
    rows.value.push(_normalizeRow({ name: name.trim(), seq }, seq - 1))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    // 文本字段
    if (['name', 'spec', 'disposalDate', 'pickingNo', 'department', 'projectName', 'approver', 'h2Ref', 'voucherResult', 'conclusion', 'remark', 'refIndex'].includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    // 减少原因（枚举）
    if (field === 'reason') {
      row.reason = (DISPOSAL_REASON_OPTIONS.includes(value as DisposalReason) ? value : '') as DisposalReason
      _persist()
      return
    }

    // 数值字段
    const numVal = Number(value) || 0
    switch (field) {
      case 'quantity': row.quantity = numVal; break
      case 'amount': row.amount = numVal; break
      default: return
    }

    _persist()
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      seq: r.seq,
      name: r.name,
      spec: r.spec,
      quantity: r.quantity,
      amount: r.amount,
      reason: r.reason,
      disposalDate: r.disposalDate,
      pickingNo: r.pickingNo,
      department: r.department,
      projectName: r.projectName,
      approver: r.approver,
      h2Ref: r.h2Ref,
      voucherResult: r.voucherResult,
      conclusion: r.conclusion,
      remark: r.remark,
      refIndex: r.refIndex,
    }))
    onSave(ROWS_KEY, toPersist)
    // 同步写入合计供CrossSheet
    onSave(DISPOSAL_TOTAL_KEY, disposalTotal.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    // Computed
    disposalTotal,
    missingH2Refs,
    // Actions
    addRow,
    deleteRow,
    updateCell,
    save,
    load,
  }
}

export default useH4DisposalCheck
