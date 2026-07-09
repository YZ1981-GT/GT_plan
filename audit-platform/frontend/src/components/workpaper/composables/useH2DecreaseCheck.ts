/**
 * useH2DecreaseCheck — H2-9 减少检查 composable
 *
 * DecreaseRow 27列 + 抽样参数 + 汇总统计
 * 集成voucher-sampling-engine
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.11
 * Requirements: 9.3-9.5, 9.7-9.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2DecreaseRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 工程名称 */
  name: string
  /** 减少日期 */
  decreaseDate: string
  /** 减少原因 */
  decreaseReason: '报废' | '毁损' | '转出' | '其他' | ''
  /** 原账面值 */
  originalValue: number
  /** 残值 */
  residualValue: number
  /** 损失金额 (公式列: 原账面值 - 残值) */
  lossAmount: number
  /** 审批文件(Y/N) */
  approvalDoc: string
  /** 评估报告(Y/N) */
  appraisalReport: string
  /** 保险理赔 */
  insuranceClaim: number
  /** 净损失 (公式列: 损失金额 - 保险理赔) */
  netLoss: number
  /** 减少前进度(%) */
  progressBeforeDecrease: number | null
  /** 技术鉴定(Y/N) */
  technicalAppraisal: string
  /** 处置方式 */
  disposalMethod: string
  /** 处置收入 */
  disposalIncome: number
  /** 处置费用 */
  disposalExpense: number
  /** 处置净收入 (公式列) */
  disposalNetIncome: number
  /** 合同解除协议(Y/N) */
  terminationAgreement: string
  /** 工程结算(Y/N) */
  projectSettlement: string
  /** 税务处理 */
  taxTreatment: string
  /** 会计分录借方 */
  journalDebit: string
  /** 会计分录贷方 */
  journalCredit: string
  /** 审计结论 */
  auditConclusion: string
  /** 索引号 */
  indexRef: string
  /** 抽凭状态 */
  samplingStatus: '待检查' | '已检查' | '已确认' | ''
  /** 📎附件 */
  attachmentPath: string
  /** 备注 */
  remark: string
}

export interface H2DecreaseSamplingParams {
  populationAmount: number
  samplingMethod: string
  sampleSize: number
  coverageRate: number
  materialityLevel: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-9-rows'
const PARAMS_KEY = 'H2-9-sampling-params'
const NOTE_KEY = 'H2-9-audit-note'
const CONCLUSION_KEY = 'H2-9-audit-conclusion'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2DecreaseCheck(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H2DecreaseRow[]>([])
  const samplingParams = ref<H2DecreaseSamplingParams>({
    populationAmount: 0,
    samplingMethod: '货币单元抽样',
    sampleSize: 0,
    coverageRate: 0,
    materialityLevel: 0,
  })
  const auditNote = ref('')
  const auditConclusion = ref('')

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

  function _recalcRow(row: H2DecreaseRow): void {
    row.lossAmount = row.originalValue - row.residualValue
    row.netLoss = row.lossAmount - row.insuranceClaim
    row.disposalNetIncome = row.disposalIncome - row.disposalExpense
  }

  function _normalizeRow(r: any, idx: number): H2DecreaseRow {
    const row: H2DecreaseRow = {
      rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: r.seq ?? (idx + 1),
      name: r.name ?? '',
      decreaseDate: r.decreaseDate ?? '',
      decreaseReason: r.decreaseReason ?? '',
      originalValue: Number(r.originalValue) || 0,
      residualValue: Number(r.residualValue) || 0,
      lossAmount: 0,
      approvalDoc: r.approvalDoc ?? '',
      appraisalReport: r.appraisalReport ?? '',
      insuranceClaim: Number(r.insuranceClaim) || 0,
      netLoss: 0,
      progressBeforeDecrease: r.progressBeforeDecrease != null ? Number(r.progressBeforeDecrease) : null,
      technicalAppraisal: r.technicalAppraisal ?? '',
      disposalMethod: r.disposalMethod ?? '',
      disposalIncome: Number(r.disposalIncome) || 0,
      disposalExpense: Number(r.disposalExpense) || 0,
      disposalNetIncome: 0,
      terminationAgreement: r.terminationAgreement ?? '',
      projectSettlement: r.projectSettlement ?? '',
      taxTreatment: r.taxTreatment ?? '',
      journalDebit: r.journalDebit ?? '',
      journalCredit: r.journalCredit ?? '',
      auditConclusion: r.auditConclusion ?? '',
      indexRef: r.indexRef ?? '',
      samplingStatus: r.samplingStatus ?? '',
      attachmentPath: r.attachmentPath ?? '',
      remark: r.remark ?? '',
    }
    _recalcRow(row)
    return row
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }

    const params = _getJson(PARAMS_KEY)
    if (params && typeof params === 'object') {
      samplingParams.value = {
        populationAmount: Number(params.populationAmount) || 0,
        samplingMethod: params.samplingMethod ?? '货币单元抽样',
        sampleSize: Number(params.sampleSize) || 0,
        coverageRate: Number(params.coverageRate) || 0,
        materialityLevel: Number(params.materialityLevel) || 0,
      }
    }

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const originalTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.originalValue)),
  )

  const lossTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.lossAmount)),
  )

  const netLossTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.netLoss)),
  )

  const checkedAmount: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.filter(r => r.samplingStatus === '已检查' || r.samplingStatus === '已确认').map(r => r.originalValue)),
  )

  /** 按减少原因分类统计 */
  const reasonStats: ComputedRef<Record<string, { count: number; amount: number }>> = computed(() => {
    const stats: Record<string, { count: number; amount: number }> = {}
    for (const row of rows.value) {
      const reason = row.decreaseReason || '未分类'
      if (!stats[reason]) stats[reason] = { count: 0, amount: 0 }
      stats[reason].count++
      stats[reason].amount += row.originalValue
    }
    return stats
  })

  const summary = computed(() => ({
    totalRows: rows.value.length,
    checkedRows: rows.value.filter(r => r.samplingStatus === '已检查' || r.samplingStatus === '已确认').length,
    pendingRows: rows.value.filter(r => r.samplingStatus === '待检查').length,
    originalTotal: originalTotal.value,
    lossTotal: lossTotal.value,
    netLossTotal: netLossTotal.value,
    checkedAmount: checkedAmount.value,
  }))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value.push(_normalizeRow({}, rows.value.length))
    _persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      rows.value.splice(idx, 1)
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      _persist()
    }
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const formulaFields = ['lossAmount', 'netLoss', 'disposalNetIncome']
    if (formulaFields.includes(field)) return

    const numFields = ['originalValue', 'residualValue', 'insuranceClaim', 'disposalIncome', 'disposalExpense', 'progressBeforeDecrease']
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _recalcRow(row)
    _persist()
  }

  function fillSamplingResults(samples: Array<{ rowId: string; status: string }>): void {
    for (const s of samples) {
      const row = rows.value.find(r => r.rowId === s.rowId)
      if (row) row.samplingStatus = s.status as any
    }
    _persist()
  }

  function updateSamplingParams(params: Partial<H2DecreaseSamplingParams>): void {
    if (options.isReadonly.value) return
    Object.assign(samplingParams.value, params)
    options.onSave?.(PARAMS_KEY, samplingParams.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function _persist(): void {
    if (!options.onSave) return
    options.onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId, seq: r.seq, name: r.name, decreaseDate: r.decreaseDate,
      decreaseReason: r.decreaseReason, originalValue: r.originalValue,
      residualValue: r.residualValue, approvalDoc: r.approvalDoc,
      appraisalReport: r.appraisalReport, insuranceClaim: r.insuranceClaim,
      progressBeforeDecrease: r.progressBeforeDecrease,
      technicalAppraisal: r.technicalAppraisal, disposalMethod: r.disposalMethod,
      disposalIncome: r.disposalIncome, disposalExpense: r.disposalExpense,
      terminationAgreement: r.terminationAgreement, projectSettlement: r.projectSettlement,
      taxTreatment: r.taxTreatment, journalDebit: r.journalDebit,
      journalCredit: r.journalCredit, auditConclusion: r.auditConclusion,
      indexRef: r.indexRef, samplingStatus: r.samplingStatus,
      attachmentPath: r.attachmentPath, remark: r.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, samplingParams, auditNote, auditConclusion,
    originalTotal, lossTotal, netLossTotal, checkedAmount, reasonStats, summary,
    addRow, removeRow, updateCell, fillSamplingResults, updateSamplingParams,
    saveNote, saveConclusion, initFromAllResponses,
  }
}

export default useH2DecreaseCheck
