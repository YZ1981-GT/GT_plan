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
import {
  H23_ROWS_KEY,
  H28_EVIDENCE_GAP_MARKER,
  buildEvidenceGapH23Row,
  evaluateAdditionEvidenceGaps,
  mergeEvidenceGapRowsToH23,
} from './h2EvidenceGapPush'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 增加方式：决定适用证据列（出包/自营/设备） */
export type H2AdditionMethod = '出包' | '自营' | '设备购置' | '其他' | ''

/** 各增加方式下应填写的证据字段；其余应标 N/A */
export const H2_ADDITION_EVIDENCE_FIELDS = {
  contractNo: '合同/协议/订单',
  progressDoc: '监理/进度(出包)',
  materialDoc: '领料单(自营)',
  invoiceNo: '发票/验收(设备)',
  acceptanceDoc: '验收/结算',
  paymentRef: '付款回单',
} as const

export type H2AdditionEvidenceField = keyof typeof H2_ADDITION_EVIDENCE_FIELDS

const EVIDENCE_BY_METHOD: Record<Exclude<H2AdditionMethod, ''>, H2AdditionEvidenceField[]> = {
  出包: ['contractNo', 'progressDoc', 'invoiceNo', 'paymentRef'],
  自营: ['contractNo', 'materialDoc', 'invoiceNo', 'paymentRef'],
  设备购置: ['contractNo', 'invoiceNo', 'acceptanceDoc', 'paymentRef'],
  其他: ['contractNo', 'progressDoc', 'materialDoc', 'invoiceNo', 'acceptanceDoc', 'paymentRef'],
}

/** 某增加方式下该证据字段是否适用 */
export function isEvidenceApplicable(method: H2AdditionMethod, field: H2AdditionEvidenceField): boolean {
  if (!method) return true
  return EVIDENCE_BY_METHOD[method].includes(field)
}

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
  /** 增加方式：出包/自营/设备购置/其他 — 切换适用证据列 */
  additionMethod: H2AdditionMethod
  /** 费用类别 */
  category: '材料' | '人工' | '机械' | '利息' | '其他' | ''
  /** 合同编号（共用） */
  contractNo: string
  /** 监理/进度（出包主证） */
  progressDoc: string
  /** 领料单（自营主证） */
  materialDoc: string
  /** 发票号（设备主证；出包结算发票亦可） */
  invoiceNo: string
  /** 发票金额 */
  invoiceAmount: number
  /** 验收/结算单（设备主证） */
  acceptanceDoc: string
  /** 付款回单号/说明 */
  paymentRef: string
  /** 付款日期 */
  paymentDate: string
  /** 付款金额 */
  paymentAmount: number
  /** 供应商 */
  supplier: string
  /**
   * 是否关联方（供 H2-17 带入）
   * 是 | 否 | ''
   */
  isRelatedParty: string
  /** 关联方名称（供 H2-17 带入） */
  relatedPartyName: string
  /** 关联方关系 */
  relationship: string
  /** 资本化判断(Y/N/N/A) */
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

function emptyRow(seq: number): H2AdditionRow {
  return {
    rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    seq,
    name: '',
    date: '',
    summary: '',
    amount: 0,
    additionMethod: '',
    category: '',
    contractNo: '',
    progressDoc: '',
    materialDoc: '',
    invoiceNo: '',
    invoiceAmount: 0,
    acceptanceDoc: '',
    paymentRef: '',
    paymentDate: '',
    paymentAmount: 0,
    supplier: '',
    isRelatedParty: '',
    relatedPartyName: '',
    relationship: '',
    capitalizable: '',
    measurementConfirmed: '',
    progressConfirmed: '',
    approvalDoc: '',
    qualityProof: '',
    attachmentPath: '',
    ocrResult: '',
    auditConclusion: '',
    indexRef: '',
    samplingStatus: '待检查',
    remark: '',
  }
}

function normalizeRow(r: any, i: number): H2AdditionRow {
  const method = (r.additionMethod ?? '') as H2AdditionMethod
  return {
    rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
    seq: r.seq ?? (i + 1),
    name: r.name ?? '',
    date: r.date ?? '',
    summary: r.summary ?? '',
    amount: Number(r.amount) || 0,
    additionMethod: method,
    category: r.category ?? '',
    contractNo: r.contractNo ?? '',
    progressDoc: r.progressDoc ?? '',
    materialDoc: r.materialDoc ?? '',
    invoiceNo: r.invoiceNo ?? '',
    invoiceAmount: Number(r.invoiceAmount) || 0,
    acceptanceDoc: r.acceptanceDoc ?? '',
    paymentRef: r.paymentRef ?? r.paymentDate ?? '',
    paymentDate: r.paymentDate ?? '',
    paymentAmount: Number(r.paymentAmount) || 0,
    supplier: r.supplier ?? '',
    isRelatedParty: r.isRelatedParty ?? '',
    relatedPartyName: r.relatedPartyName ?? '',
    relationship: r.relationship ?? '',
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
  }
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

/** 切换增加方式时：不适用证据自动填 N/A，适用且原为 N/A 则清空以便填写 */
export function applyEvidenceForMethod(row: H2AdditionRow, method: H2AdditionMethod): void {
  row.additionMethod = method
  const fields = Object.keys(H2_ADDITION_EVIDENCE_FIELDS) as H2AdditionEvidenceField[]
  for (const field of fields) {
    const applicable = isEvidenceApplicable(method, field)
    const cur = String((row as any)[field] ?? '')
    if (!method) continue
    if (!applicable) {
      ;(row as any)[field] = 'N/A'
    } else if (cur === 'N/A') {
      ;(row as any)[field] = ''
    }
  }
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
      rows.value = data.map((r: any, i: number) => normalizeRow(r, i))
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
    evidenceGapCount: evidenceGapCount.value,
  }))

  const evidenceGapCount = computed(() =>
    rows.value.filter(r => evaluateAdditionEvidenceGaps(r).length > 0).length,
  )

  const pushableEvidenceGapRows = computed(() =>
    rows.value
      .map(row => ({ row, gaps: evaluateAdditionEvidenceGaps(row) }))
      .filter(x => x.gaps.length > 0),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value.push(emptyRow(rows.value.length + 1))
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
    if (field === 'additionMethod') {
      applyEvidenceForMethod(row, (value ?? '') as H2AdditionMethod)
      _persist()
      return
    }
    const numFields = ['amount', 'invoiceAmount', 'paymentAmount']
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    // 关联方=否/空时清空名称，避免脏数据带入 H2-17
    if (field === 'isRelatedParty' && value !== '是') {
      row.relatedPartyName = ''
      row.relationship = ''
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

  /**
   * 将增加检查证据缺口推送为 H2-3 索引说明行（类别「其他」，无金额）。
   * 重复推送会先清理旧自动草稿（remark=H2-8-evidence-gap-auto）。
   */
  function pushEvidenceGapsToH23(): {
    ok: boolean
    added: number
    message: string
  } {
    if (options.isReadonly.value) {
      return { ok: false, added: 0, message: '只读模式' }
    }
    const toPush = pushableEvidenceGapRows.value
    if (toPush.length === 0) {
      return { ok: false, added: 0, message: '无可推送项：适用证据列与关键确认项均已填齐' }
    }

    let existing: any[] = []
    const raw = _getJson(H23_ROWS_KEY)
    if (Array.isArray(raw)) existing = raw

    let seq = existing.reduce((m: number, r: any) => Math.max(m, Number(r.seq) || 0), 0) + 1
    const newRows = toPush.map(({ row, gaps }) => {
      const built = buildEvidenceGapH23Row({
        sourceSheet: 'H2-8',
        projectName: row.name || row.summary,
        sampleLabel: `样本#${row.seq}`,
        gaps,
        seq: seq++,
        marker: H28_EVIDENCE_GAP_MARKER,
      })
      if (!row.auditConclusion || row.auditConclusion === '无异常') {
        row.auditConclusion = '存疑'
      }
      return built
    })

    const merged = mergeEvidenceGapRowsToH23(existing, newRows, H28_EVIDENCE_GAP_MARKER)
    options.onSave?.(H23_ROWS_KEY, merged.map((r, i) => ({ ...r, seq: i + 1 })))
    _persist()

    return {
      ok: true,
      added: newRows.length,
      message: `已向 H2-3 推送 ${newRows.length} 条证据缺口说明（索引 H2-8）；重复推送会替换旧自动草稿`,
    }
  }

  function _persist(): void {
    if (!options.onSave) return
    options.onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId, seq: r.seq, name: r.name, date: r.date,
      summary: r.summary, amount: r.amount, additionMethod: r.additionMethod, category: r.category,
      contractNo: r.contractNo, progressDoc: r.progressDoc, materialDoc: r.materialDoc,
      invoiceNo: r.invoiceNo, invoiceAmount: r.invoiceAmount,
      acceptanceDoc: r.acceptanceDoc, paymentRef: r.paymentRef,
      paymentDate: r.paymentDate, paymentAmount: r.paymentAmount, supplier: r.supplier,
      isRelatedParty: r.isRelatedParty, relatedPartyName: r.relatedPartyName, relationship: r.relationship,
      capitalizable: r.capitalizable,
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
    evidenceGapCount, pushableEvidenceGapRows,
    addRow, removeRow, updateCell,
    mergeOcrResult, fillSamplingResults, updateSamplingParams,
    saveNote, saveConclusion, pushEvidenceGapsToH23, initFromAllResponses,
    applyEvidenceForMethod,
  }
}

export default useH2AdditionCheck
