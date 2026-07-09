/**
 * useH2AdditionCheck — H2-8 增加检查 composable
 *
 * AdditionRow 24列 + 抽样参数 + 汇总统计
 * 集成voucher-sampling-engine + OCR端点
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.10
 * Requirements: 9.1-9.2, 9.5-9.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2AdditionRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 工程名称 */
  name: string
  /** 日期 */
  date: string
  /** 摘要 */
  summary: string
  /** 金额 */
  amount: number
  /** 费用类别 */
  category: '材料' | '人工' | '机械' | '利息' | '其他' | ''
  /** 合同编号 */
  contractNo: string
  /** 发票号 */
  invoiceNo: string
  /** 发票金额 */
  invoiceAmount: number
  /** 付款日期 */
  paymentDate: string
  /** 付款金额 */
  paymentAmount: number
  /** 供应商 */
  supplier: string
  /** 验收单 */
  acceptanceDoc: string
  /** 资本化判断(Y/N) */
  capitalizable: string
  /** 计量确认(Y/N) */
  measurementConfirmed: string
  /** 进度确认(Y/N) */
  progressConfirmed: string
  /** 审批文件(Y/N) */
  approvalDoc: string
  /** 质量证明(Y/N) */
  qualityProof: string
  /** 📎附件路径 */
  attachmentPath: string
  /** OCR结果 */
  ocrResult: string
  /** 审计结论 */
  auditConclusion: string
  /** GtIndexChip索引号 */
  indexRef: string
  /** 抽凭状态 */
  samplingStatus: '待检查' | '已检查' | '已确认' | ''
  /** 备注 */
  remark: string
}

export interface H2SamplingParams {
  /** 测试总体金额 */
  populationAmount: number
  /** 抽样方法 */
  samplingMethod: string
  /** 样本量 */
  sampleSize: number
  /** 覆盖率(%) */
  coverageRate: number
  /** 重要性水平 */
  materialityLevel: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-8-rows'
const PARAMS_KEY = 'H2-8-sampling-params'
const NOTE_KEY = 'H2-8-audit-note'
const CONCLUSION_KEY = 'H2-8-audit-conclusion'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2AdditionCheck(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H2AdditionRow[]>([])
  const samplingParams = ref<H2SamplingParams>({
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

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r: any, i: number) => ({
        rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
        seq: r.seq ?? (i + 1),
        name: r.name ?? '',
        date: r.date ?? '',
        summary: r.summary ?? '',
        amount: Number(r.amount) || 0,
        category: r.category ?? '',
        contractNo: r.contractNo ?? '',
        invoiceNo: r.invoiceNo ?? '',
        invoiceAmount: Number(r.invoiceAmount) || 0,
        paymentDate: r.paymentDate ?? '',
        paymentAmount: Number(r.paymentAmount) || 0,
        supplier: r.supplier ?? '',
        acceptanceDoc: r.acceptanceDoc ?? '',
        capitalizable: r.capitalizable ?? '',
        measurementConfirmed: r.measurementConfirmed ?? '',
        progressConfirmed: r.progressConfirmed ?? '',
        approvalDoc: r.approvalDoc ?? '',
        qualityProof: r.qualityProof ?? '',
        attachmentPath: r.attachmentPath ?? '',
        ocrResult: r.ocrResult ?? '',
        auditConclusion: r.auditConclusion ?? '',
        indexRef: r.indexRef ?? '',
        samplingStatus: r.samplingStatus ?? '',
        remark: r.remark ?? '',
      }))
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

  /** 金额合计 */
  const amountTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.amount)),
  )

  /** 已检查金额 */
  const checkedAmount: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.filter(r => r.samplingStatus === '已检查' || r.samplingStatus === '已确认').map(r => r.amount)),
  )

  /** 覆盖率（自动计算） */
  const actualCoverageRate: ComputedRef<number> = computed(() => {
    if (samplingParams.value.populationAmount <= 0) return 0
    return (checkedAmount.value / samplingParams.value.populationAmount) * 100
  })

  /** 按费用类别统计 */
  const categoryStats: ComputedRef<Record<string, number>> = computed(() => {
    const stats: Record<string, number> = {}
    for (const row of rows.value) {
      const cat = row.category || '未分类'
      stats[cat] = (stats[cat] ?? 0) + row.amount
    }
    return stats
  })

  /** 汇总统计 */
  const summary = computed(() => ({
    totalRows: rows.value.length,
    checkedRows: rows.value.filter(r => r.samplingStatus === '已检查' || r.samplingStatus === '已确认').length,
    pendingRows: rows.value.filter(r => r.samplingStatus === '待检查').length,
    amountTotal: amountTotal.value,
    checkedAmount: checkedAmount.value,
    coverageRate: actualCoverageRate.value,
  }))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1,
      name: '', date: '', summary: '', amount: 0, category: '',
      contractNo: '', invoiceNo: '', invoiceAmount: 0,
      paymentDate: '', paymentAmount: 0, supplier: '',
      acceptanceDoc: '', capitalizable: '', measurementConfirmed: '',
      progressConfirmed: '', approvalDoc: '', qualityProof: '',
      attachmentPath: '', ocrResult: '', auditConclusion: '',
      indexRef: '', samplingStatus: '待检查', remark: '',
    })
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
    const numFields = ['amount', 'invoiceAmount', 'paymentAmount']
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _persist()
  }

  /** OCR结果填入 */
  function mergeOcrResult(rowId: string, ocrData: Record<string, any>): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return
    if (ocrData.amount != null) row.amount = Number(ocrData.amount) || row.amount
    if (ocrData.invoiceNo) row.invoiceNo = ocrData.invoiceNo
    if (ocrData.invoiceAmount != null) row.invoiceAmount = Number(ocrData.invoiceAmount) || row.invoiceAmount
    if (ocrData.supplier) row.supplier = ocrData.supplier
    if (ocrData.date) row.date = ocrData.date
    row.ocrResult = JSON.stringify(ocrData)
    _persist()
  }

  /** 抽凭引擎填入样本 */
  function fillSamplingResults(samples: Array<{ rowId: string; status: string }>): void {
    for (const s of samples) {
      const row = rows.value.find(r => r.rowId === s.rowId)
      if (row) row.samplingStatus = s.status as any
    }
    _persist()
  }

  function updateSamplingParams(params: Partial<H2SamplingParams>): void {
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
      rowId: r.rowId, seq: r.seq, name: r.name, date: r.date,
      summary: r.summary, amount: r.amount, category: r.category,
      contractNo: r.contractNo, invoiceNo: r.invoiceNo, invoiceAmount: r.invoiceAmount,
      paymentDate: r.paymentDate, paymentAmount: r.paymentAmount, supplier: r.supplier,
      acceptanceDoc: r.acceptanceDoc, capitalizable: r.capitalizable,
      measurementConfirmed: r.measurementConfirmed, progressConfirmed: r.progressConfirmed,
      approvalDoc: r.approvalDoc, qualityProof: r.qualityProof,
      attachmentPath: r.attachmentPath, ocrResult: r.ocrResult,
      auditConclusion: r.auditConclusion, indexRef: r.indexRef,
      samplingStatus: r.samplingStatus, remark: r.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, samplingParams, auditNote, auditConclusion,
    amountTotal, checkedAmount, actualCoverageRate, categoryStats, summary,
    addRow, removeRow, updateCell,
    mergeOcrResult, fillSamplingResults, updateSamplingParams,
    saveNote, saveConclusion, initFromAllResponses,
  }
}

export default useH2AdditionCheck
