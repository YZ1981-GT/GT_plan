/**
 * useH6Check — H6-4 检查表 composable（18列+合规/不合规选择+统计摘要+与H6-2联动）
 *
 * 18列：检查项目/清理审批/资产评估/税务处理/会计处理/收入确认/费用归集/结转时点/核查结论
 * （每个检查项对应H6-2明细表的一个清理项目）
 *
 * 功能：
 * - 对每个检查项提供"合规/不合规/不适用"选择
 * - 存在"不合规"项时顶部红色摘要"发现x项不合规，请关注"
 * - 与H6-2明细表项目联动：每行对应一个清理项目编号
 * - Saves to "H6-4-rows"
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 3.4
 * Requirements: 4.3-4.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 合规性选项 */
export type ComplianceOption = '合规' | '不合规' | '不适用'

/** H6-4 检查表行 */
export interface H6CheckRow {
  rowId: string
  /** 清理项目编号（对应H6-2行的rowId，联动） */
  linkedDetailRowId: string
  /** 清理项目名称（从H6-2关联显示） */
  projectName: string
  /** 清理审批 */
  disposalApproval: ComplianceOption
  /** 资产评估 */
  assetValuation: ComplianceOption
  /** 税务处理 */
  taxTreatment: ComplianceOption
  /** 会计处理 */
  accountingTreatment: ComplianceOption
  /** 收入确认 */
  incomeRecognition: ComplianceOption
  /** 费用归集 */
  expenseAllocation: ComplianceOption
  /** 结转时点 */
  transferTiming: ComplianceOption
  /** 核查结论 */
  conclusion: ComplianceOption
  /** 备注 */
  remark: string
}

/** 检查项字段名（不含基础字段） */
export type CheckField =
  | 'disposalApproval'
  | 'assetValuation'
  | 'taxTreatment'
  | 'accountingTreatment'
  | 'incomeRecognition'
  | 'expenseAllocation'
  | 'transferTiming'
  | 'conclusion'

/** 统计摘要 */
export interface H6CheckSummary {
  /** 合规项数 */
  compliantCount: number
  /** 不合规项数 */
  nonCompliantCount: number
  /** 不适用项数 */
  notApplicableCount: number
  /** 总检查项数（行数 × 检查维度数） */
  totalChecks: number
  /** 是否存在不合规 */
  hasNonCompliant: boolean
  /** 警告文本 */
  warning: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H6-4-rows'
const COMPLIANCE_OPTIONS: ComplianceOption[] = ['合规', '不合规', '不适用']
const CHECK_FIELDS: CheckField[] = [
  'disposalApproval',
  'assetValuation',
  'taxTreatment',
  'accountingTreatment',
  'incomeRecognition',
  'expenseAllocation',
  'transferTiming',
  'conclusion',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6Check(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H6CheckRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeCompliance(val: any): ComplianceOption {
    if (COMPLIANCE_OPTIONS.includes(val as ComplianceOption)) return val as ComplianceOption
    return '不适用'
  }

  function _normalizeRow(raw: any): H6CheckRow {
    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      linkedDetailRowId: raw.linkedDetailRowId ?? '',
      projectName: raw.projectName ?? '',
      disposalApproval: _normalizeCompliance(raw.disposalApproval),
      assetValuation: _normalizeCompliance(raw.assetValuation),
      taxTreatment: _normalizeCompliance(raw.taxTreatment),
      accountingTreatment: _normalizeCompliance(raw.accountingTreatment),
      incomeRecognition: _normalizeCompliance(raw.incomeRecognition),
      expenseAllocation: _normalizeCompliance(raw.expenseAllocation),
      transferTiming: _normalizeCompliance(raw.transferTiming),
      conclusion: _normalizeCompliance(raw.conclusion),
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

  // ─── Computed: 统计摘要 ────────────────────────────────────────────────────

  const summary: ComputedRef<H6CheckSummary> = computed(() => {
    let compliantCount = 0
    let nonCompliantCount = 0
    let notApplicableCount = 0

    for (const row of rows.value) {
      for (const field of CHECK_FIELDS) {
        const val = row[field]
        if (val === '合规') compliantCount++
        else if (val === '不合规') nonCompliantCount++
        else notApplicableCount++
      }
    }

    const totalChecks = rows.value.length * CHECK_FIELDS.length
    const hasNonCompliant = nonCompliantCount > 0

    return {
      compliantCount,
      nonCompliantCount,
      notApplicableCount,
      totalChecks,
      hasNonCompliant,
      warning: hasNonCompliant
        ? `发现${nonCompliantCount}项不合规，请关注`
        : '',
    }
  })

  /** 不合规行列表（高亮用） */
  const nonCompliantRows: ComputedRef<H6CheckRow[]> = computed(() =>
    rows.value.filter(row =>
      CHECK_FIELDS.some(field => row[field] === '不合规'),
    ),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  /** 从H6-2明细表项目创建检查行（联动） */
  function addRowFromDetail(detailRowId: string, projectName: string): void {
    // 避免重复
    if (rows.value.some(r => r.linkedDetailRowId === detailRowId)) return
    rows.value.push(_normalizeRow({
      linkedDetailRowId: detailRowId,
      projectName,
    }))
    _persist()
  }

  function addRow(projectName: string): void {
    if (!projectName?.trim()) return
    rows.value.push(_normalizeRow({ projectName: projectName.trim() }))
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

    if (field === 'projectName') {
      row.projectName = String(value ?? '')
      _persist()
      return
    }

    if (field === 'remark') {
      row.remark = String(value ?? '')
      _persist()
      return
    }

    // 合规性字段
    if (CHECK_FIELDS.includes(field as CheckField)) {
      ;(row as any)[field] = _normalizeCompliance(value)
      _persist()
      return
    }
  }

  /** 批量从H6-2同步检查行（确保每个明细项都有对应检查行） */
  function syncFromDetailRows(detailRows: Array<{ rowId: string; assetName: string }>): void {
    for (const detail of detailRows) {
      if (!rows.value.some(r => r.linkedDetailRowId === detail.rowId)) {
        rows.value.push(_normalizeRow({
          linkedDetailRowId: detail.rowId,
          projectName: detail.assetName,
        }))
      }
    }
    // 更新已有行的项目名称
    for (const row of rows.value) {
      if (row.linkedDetailRowId) {
        const detail = detailRows.find(d => d.rowId === row.linkedDetailRowId)
        if (detail) {
          row.projectName = detail.assetName
        }
      }
    }
    _persist()
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      linkedDetailRowId: r.linkedDetailRowId,
      projectName: r.projectName,
      disposalApproval: r.disposalApproval,
      assetValuation: r.assetValuation,
      taxTreatment: r.taxTreatment,
      accountingTreatment: r.accountingTreatment,
      incomeRecognition: r.incomeRecognition,
      expenseAllocation: r.expenseAllocation,
      transferTiming: r.transferTiming,
      conclusion: r.conclusion,
      remark: r.remark,
    }))
    onSave(ROWS_KEY, toPersist)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    // Computed
    summary,
    nonCompliantRows,
    // Constants (exported for UI binding)
    COMPLIANCE_OPTIONS,
    CHECK_FIELDS,
    // Actions
    addRow,
    addRowFromDetail,
    deleteRow,
    updateCell,
    syncFromDetailRows,
    save,
    load,
  }
}

export default useH6Check
