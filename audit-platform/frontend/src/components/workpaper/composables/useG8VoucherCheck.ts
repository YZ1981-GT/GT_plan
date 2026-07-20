/**
 * useG8VoucherCheck — G8-6 凭证检查（5项核对含公允价值+OCI）
 *
 * 核对项三态：null=未测 / true=通过 / false=不通过
 * 异常判定：任一核对项 false → 异常；未测不计入；forceAbnormal 可人工/截止强制
 * 抽样参数：G8-vc-params（对标 D3-vc-params）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, isDebitCreditBalanced, calcSubtotal } from './useG8FormulaEngine'
import { mapCutoffToG8Voucher, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'
import {
  buildG8VoucherCrossSnapshot,
  buildG8VoucherLinkHints,
  deriveG8AbnormalType,
  filterG8VoucherRowsBySource,
  countG8VoucherBySource,
  applyG8LinkHintSuggestions,
  selectG8QuantitativeAbnormals,
  mapG8VoucherToMisstatementBody,
  mapG8VoucherToA13PushItem,
  type G8AbnormalType,
  type G8VoucherSourceFilter,
  type G8VoucherLinkHint,
} from './g8VoucherCross'
import {
  G8A_VOUCHER_MARK_KEY,
  G8A_VOUCHER_PROGRAM_NOS,
  markG8AProcedureSteps,
  buildG8VoucherProcedureSummary,
  dispatchProcedureFocus,
} from './g8CrossHelpers'
import {
  computeG8Projection,
  formatG8ProjectionMemoSection,
  suggestG8ActualMisstatement,
  type G8ProjectionView,
} from './g8VoucherProjection'

export type { G8AbnormalType, G8VoucherSourceFilter, G8VoucherLinkHint }
export type G8VoucherTab = 'basic' | 'check' | 'conclusion'

/** null = 未测；true = 通过；false = 不通过 */
export type G8CheckState = boolean | null

export interface G8VoucherRow {
  rowId: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  attachment: string
  supportingDocDesc: string
  check1OriginalComplete: G8CheckState
  check2Authorization: G8CheckState
  check3Accounting: G8CheckState
  check4FairValueCorrect: G8CheckState
  check5OCICorrect: G8CheckState
  indexNo: string
  /** 由核对项 / forceAbnormal 推导，勿直接持久化覆盖逻辑 */
  isAbnormal: boolean
  /** 人工或截止测试强制标记异常（与核对项解耦，避免粘滞） */
  forceAbnormal: boolean
  /** 异常定性：金额 / 定性 / 混合（由核对项推导） */
  abnormalType: G8AbnormalType
  abnormalDesc: string
  riskLevel: string
  remark: string
  source?: string
  /** 挂接 G8-2 明细行 */
  detailRowId?: string
  /** 被投资单位名称（可与明细同步） */
  investeeName?: string
  /** 审计师录入的该样本实际错报金额（错报推断用） */
  actualMisstatement?: number
  /** MUS 高值层（100%检查，已知错报不外推） */
  isHighValue?: boolean
}

/** 抽样参数（对标 D3 SamplingParams，落库 G8-vc-params） */
export interface G8SamplingParams {
  testPopulation: string
  specificSamples: string
  samplingPopulation: string
  samplingMethod: string
  samplingProcess: string
  targetSampleSize: number
  currentSampleSize: number
  /** 总体笔数（覆盖率分母，可选手工填） */
  populationCount: number
  /** 总体金额（覆盖率分母，可选手工填） */
  populationAmount: number
  /** 可容忍错报（错报推断） */
  tolerableMisstatement: number
  /** 预期错报（可选，备忘用） */
  expectedMisstatement: number
  /** 置信度，默认 0.95 */
  confidenceLevel: number
}

/** 抽凭引擎 SampledVoucher 精简形态（回填用） */
export interface G8SampledVoucherLike {
  voucherNo?: string
  voucherDate?: string
  summary?: string | null
  debitAmount?: string | number | null
  creditAmount?: string | number | null
  counterpartAccount?: string | null
  abnormal?: boolean
  actualMisstatement?: string | number | null
  isHighValue?: boolean
  selectionReason?: string
}

const CHECK_KEYS = [
  'check1OriginalComplete',
  'check2Authorization',
  'check3Accounting',
  'check4FairValueCorrect',
  'check5OCICorrect',
] as const

export type G8CheckKey = (typeof CHECK_KEYS)[number]

const ITEM_ID_ROWS = 'G8-voucher-rows'
const ITEM_ID_CONCLUSION = 'G8-voucher-conclusion'
export const ITEM_ID_G8_VC_PARAMS = 'G8-vc-params'

function genId(): string {
  return `g8v-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function defaultG8SamplingParams(): G8SamplingParams {
  return {
    testPopulation: '',
    specificSamples: '',
    samplingPopulation: '',
    samplingMethod: '',
    samplingProcess: '',
    targetSampleSize: 0,
    currentSampleSize: 0,
    populationCount: 0,
    populationAmount: 0,
    tolerableMisstatement: 0,
    expectedMisstatement: 0,
    confidenceLevel: 0.95,
  }
}

export function parseG8SamplingParams(json: string | null | undefined): G8SamplingParams {
  const defaults = defaultG8SamplingParams()
  if (!json) return defaults
  try {
    const raw = JSON.parse(json)
    if (!raw || typeof raw !== 'object') return defaults
    const conf = Number(raw.confidenceLevel)
    return {
      testPopulation: String(raw.testPopulation ?? ''),
      specificSamples: String(raw.specificSamples ?? ''),
      samplingPopulation: String(raw.samplingPopulation ?? ''),
      samplingMethod: String(raw.samplingMethod ?? ''),
      samplingProcess: String(raw.samplingProcess ?? ''),
      targetSampleSize: Number(raw.targetSampleSize) || 0,
      currentSampleSize: Number(raw.currentSampleSize) || 0,
      populationCount: Number(raw.populationCount) || 0,
      populationAmount: Number(raw.populationAmount) || 0,
      tolerableMisstatement: Number(raw.tolerableMisstatement) || 0,
      expectedMisstatement: Number(raw.expectedMisstatement) || 0,
      confidenceLevel: Number.isFinite(conf) && conf > 0 && conf < 1 ? conf : 0.95,
    }
  } catch {
    return defaults
  }
}

/** 解析核对三态；空/未识别 → null（未测） */
export function parseG8CheckState(v: unknown): G8CheckState {
  if (v === null || v === undefined || v === '') return null
  if (v === true || v === 1) return true
  if (v === false || v === 0) return false
  const s = String(v).trim().toLowerCase()
  if (!s || s === '未测' || s === 'n/a' || s === 'na' || s === '-' || s === '—') return null
  if (s === 'true' || s === '是' || s === 'yes' || s === 'y' || s === '✓' || s === '√' || s === '通过') return true
  if (s === 'false' || s === '否' || s === 'no' || s === 'n' || s === '✗' || s === '×' || s === '不通过') return false
  return null
}

export function formatG8CheckState(v: G8CheckState): string {
  if (v === true) return '✓'
  if (v === false) return '✗'
  return '未测'
}

export function recalcG8VoucherAbnormal(row: G8VoucherRow): G8VoucherRow {
  const checks = CHECK_KEYS.map((k) => row[k])
  const checkFailed = checks.some((c) => c === false)
  const isAbnormal = checkFailed || !!row.forceAbnormal
  const withFlag = { ...row, isAbnormal }
  return { ...withFlag, abnormalType: deriveG8AbnormalType(withFlag) }
}

export function enrichG8VoucherRow(
  raw: Partial<G8VoucherRow> & { rowId?: string; id?: string },
  seq: number,
): G8VoucherRow {
  const base: G8VoucherRow = {
    rowId: raw.rowId ?? raw.id ?? genId(),
    seq,
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? '',
    counterAccount: raw.counterAccount ?? '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    attachment: raw.attachment ?? '',
    supportingDocDesc: raw.supportingDocDesc ?? '',
    check1OriginalComplete: parseG8CheckState(raw.check1OriginalComplete),
    check2Authorization: parseG8CheckState(raw.check2Authorization),
    check3Accounting: parseG8CheckState(raw.check3Accounting),
    check4FairValueCorrect: parseG8CheckState(raw.check4FairValueCorrect),
    check5OCICorrect: parseG8CheckState(raw.check5OCICorrect),
    indexNo: raw.indexNo ?? '',
    isAbnormal: false,
    forceAbnormal: !!raw.forceAbnormal,
    abnormalType: 'none',
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: raw.riskLevel ?? 'low',
    remark: raw.remark ?? '',
    source: raw.source ?? '',
    detailRowId: raw.detailRowId ?? '',
    investeeName: raw.investeeName ?? '',
    actualMisstatement: parseNum(raw.actualMisstatement),
    isHighValue: !!raw.isHighValue,
  }
  return recalcG8VoucherAbnormal(base)
}

/** @deprecated use recalcG8VoucherAbnormal */
export function deriveG8Abnormal(row: G8VoucherRow): boolean {
  return recalcG8VoucherAbnormal(row).isAbnormal
}

/** 五项是否均已测试（非 null） */
export function isG8VoucherFullyChecked(row: G8VoucherRow): boolean {
  return CHECK_KEYS.every((k) => row[k] !== null)
}

export function countG8VoucherUntested(rows: G8VoucherRow[]): number {
  return rows.filter((r) => !isG8VoucherFullyChecked(r)).length
}

export function computeG8AnomalyRate(rows: G8VoucherRow[]): number {
  if (!rows.length) return 0
  const n = rows.filter((r) => r.isAbnormal).length
  return (n / rows.length) * 100
}

/** 样本发生额：按行取 max(借,贷)，避免单边样本被借贷轧差吞掉 */
export function calcG8SampleAbsAmount(rows: Array<{ debitAmount: number; creditAmount: number }>): number {
  return rows.reduce((s, r) => s + Math.max(Math.abs(r.debitAmount || 0), Math.abs(r.creditAmount || 0)), 0)
}

export function calcG8CoverageRates(
  rows: Array<{ debitAmount: number; creditAmount: number; source?: string }>,
  params: Pick<G8SamplingParams, 'targetSampleSize' | 'currentSampleSize' | 'populationCount' | 'populationAmount'>,
): { countPct: number; amountPct: number; sampleAbsAmount: number } {
  const sampleAbsAmount = calcG8SampleAbsAmount(rows)
  const countDenom = params.populationCount > 0
    ? params.populationCount
    : (params.targetSampleSize > 0 ? params.targetSampleSize : 0)
  const countNum = params.currentSampleSize > 0
    ? params.currentSampleSize
    : rows.filter((r) => r.source === '抽凭').length || rows.length
  const countPct = countDenom > 0 ? Math.min(100, (countNum / countDenom) * 100) : 0
  const amountPct = params.populationAmount > 0
    ? Math.min(100, (sampleAbsAmount / params.populationAmount) * 100)
    : 0
  return { countPct, amountPct, sampleAbsAmount }
}

/**
 * 编制完成度（0–100）：
 * 抽样参数 20 + 有样本 25 + 已测完 30 + 结论 15 + 异常已说明 10
 */
export function calcG8VoucherCompletion(input: {
  params: G8SamplingParams
  rows: G8VoucherRow[]
  conclusion: string
}): { pct: number; checklist: Array<{ key: string; label: string; ok: boolean }> } {
  const { params, rows, conclusion } = input
  const hasParams = !!(params.samplingMethod || params.targetSampleSize || params.testPopulation)
  const hasRows = rows.length > 0
  const sampleOk = params.targetSampleSize > 0
    ? params.currentSampleSize >= params.targetSampleSize || rows.length >= params.targetSampleSize
    : hasRows
  const untested = countG8VoucherUntested(rows)
  const allChecked = hasRows && untested === 0
  const hasConclusion = !!(conclusion && conclusion.trim())
  const abnormals = rows.filter((r) => r.isAbnormal)
  const abnormalExplained = hasRows && (
    abnormals.length === 0 || abnormals.every((r) => !!(r.abnormalDesc && r.abnormalDesc.trim()))
  )

  const checklist = [
    { key: 'params', label: '已填抽样参数', ok: hasParams },
    { key: 'sample', label: '样本量达标或已有样本', ok: sampleOk },
    { key: 'checked', label: '样本均已核对（无未测）', ok: allChecked },
    { key: 'conclusion', label: '已填检查结论', ok: hasConclusion },
    { key: 'abnormal', label: '异常均已说明', ok: abnormalExplained },
  ]
  const weights: Record<string, number> = {
    params: 20, sample: 25, checked: 30, conclusion: 15, abnormal: 10,
  }
  const pct = checklist.reduce((s, c) => s + (c.ok ? weights[c.key] : 0), 0)
  return { pct, checklist }
}

/** G8-6 抽样备忘（Markdown，不依赖引擎完整 config） */
export function buildG8VoucherSamplingMemo(input: {
  params: G8SamplingParams
  rows: G8VoucherRow[]
  conclusion: string
  coverage: { countPct: number; amountPct: number; sampleAbsAmount: number }
  accountCode?: string
}): string {
  const { params, rows, conclusion, coverage, accountCode = '1503' } = input
  const abn = rows.filter((r) => r.isAbnormal)
  const quant = abn.filter((r) => r.abnormalType === 'quantitative' || r.abnormalType === 'mixed')
  const lines: string[] = []
  lines.push('# G8-6 凭证检查抽样备忘')
  lines.push('')
  lines.push(`生成时间：${new Date().toISOString()}`)
  lines.push(`科目：${accountCode} 其他权益工具投资`)
  lines.push('')
  lines.push('## 一、抽样参数')
  lines.push(`- 测试总体：${params.testPopulation || '—'}`)
  lines.push(`- 特定样本：${params.specificSamples || '—'}`)
  lines.push(`- 抽样总体：${params.samplingPopulation || '—'}`)
  lines.push(`- 抽样方法：${params.samplingMethod || '—'}`)
  lines.push(`- 目标样本量：${params.targetSampleSize || '—'} 笔`)
  lines.push(`- 当前样本量：${params.currentSampleSize || rows.filter((r) => r.source === '抽凭').length} 笔`)
  lines.push(`- 总体笔数：${params.populationCount || '—'}`)
  lines.push(`- 总体金额：${params.populationAmount ? params.populationAmount.toLocaleString('zh-CN') : '—'}`)
  lines.push(`- 可容忍错报：${params.tolerableMisstatement ? params.tolerableMisstatement.toLocaleString('zh-CN') : '—'}`)
  lines.push(`- 预期错报：${params.expectedMisstatement ? params.expectedMisstatement.toLocaleString('zh-CN') : '—'}`)
  lines.push(`- 置信度：${params.confidenceLevel || 0.95}`)
  lines.push('')
  lines.push('## 二、覆盖率')
  lines.push(`- 笔数覆盖率：${coverage.countPct.toFixed(1)}%`)
  lines.push(`- 金额覆盖率：${coverage.amountPct > 0 ? `${coverage.amountPct.toFixed(1)}%` : '—（请填写总体金额）'}`)
  lines.push(`- 样本发生额合计：${coverage.sampleAbsAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
  lines.push('')
  lines.push('## 三、核对结果')
  lines.push(`- 样本行数：${rows.length}`)
  lines.push(`- 未测：${countG8VoucherUntested(rows)}`)
  lines.push(`- 异常：${abn.length}（其中金额类 ${quant.length}）`)
  lines.push(`- 异常率：${computeG8AnomalyRate(rows).toFixed(1)}%`)
  if (abn.length) {
    lines.push('')
    lines.push('### 异常明细')
    for (const r of abn.slice(0, 50)) {
      lines.push(
        `- ${r.voucherNo || r.rowId}｜${r.investeeName || '—'}｜${r.abnormalType}｜错报${r.actualMisstatement || 0}｜${r.abnormalDesc || '（无说明）'}`,
      )
    }
  }
  lines.push('')
  lines.push('## 四、检查结论')
  lines.push(conclusion?.trim() || '—')
  lines.push('')
  lines.push('## 五、编制说明')
  lines.push('- 样本借贷不必平衡（抽样明细常为单边发生额）。')
  lines.push('- 金额类异常宜进入错报汇总（A13）；定性异常以说明与强制标记留痕。')
  lines.push(params.samplingProcess ? `- 抽样过程：${params.samplingProcess}` : '- 抽样过程：—')
  lines.push('')
  const proj = computeG8Projection({ rows, params, useSuggestedWhenEmpty: false })
  lines.push(formatG8ProjectionMemoSection(proj))
  lines.push('')
  return lines.join('\n')
}

// ─── 行级 OCR（对齐 D3：多字段映射 + 置信度 + 仅填空合并） ─────────────────

/** 低置信度阈值：低于此值需人工复核 */
export const G8_OCR_CONFIDENCE_THRESHOLD = 0.8

export type G8OcrTargetField =
  | 'voucherDate'
  | 'voucherNo'
  | 'businessContent'
  | 'counterAccount'
  | 'debitAmount'
  | 'creditAmount'
  | 'investeeName'
  | 'supportingDocDesc'

/** OCR 识别键 → G8VoucherRow 字段 */
export const G8_OCR_FIELD_MAP: Record<string, G8OcrTargetField> = {
  date: 'voucherDate',
  日期: 'voucherDate',
  凭证日期: 'voucherDate',
  voucher_date: 'voucherDate',
  voucherDate: 'voucherDate',
  signDate: 'voucherDate',
  voucher_no: 'voucherNo',
  voucherNo: 'voucherNo',
  凭证号: 'voucherNo',
  凭证编号: 'voucherNo',
  contractNo: 'voucherNo',
  summary: 'businessContent',
  摘要: 'businessContent',
  business_content: 'businessContent',
  businessContent: 'businessContent',
  业务内容: 'businessContent',
  serviceContent: 'businessContent',
  counter_account: 'counterAccount',
  counterAccount: 'counterAccount',
  对方科目: 'counterAccount',
  debit_amount: 'debitAmount',
  借方金额: 'debitAmount',
  借方: 'debitAmount',
  credit_amount: 'creditAmount',
  贷方金额: 'creditAmount',
  贷方: 'creditAmount',
  // 科目1503 多为借方发生；无借贷方向时默认记入借方
  amount: 'debitAmount',
  金额: 'debitAmount',
  contractAmount: 'debitAmount',
  被投资单位: 'investeeName',
  对方单位: 'investeeName',
  对方名称: 'investeeName',
  investeeName: 'investeeName',
  counterparty: 'investeeName',
  客户名称: 'investeeName',
  支持性文件: 'supportingDocDesc',
  supporting_doc: 'supportingDocDesc',
  supportingDocDesc: 'supportingDocDesc',
}

const G8_OCR_FIELD_LABELS: Record<G8OcrTargetField, string> = {
  voucherDate: '日期',
  voucherNo: '凭证编号',
  businessContent: '业务内容',
  counterAccount: '对方科目',
  debitAmount: '借方金额',
  creditAmount: '贷方金额',
  investeeName: '被投资单位',
  supportingDocDesc: '支持性文件',
}

/**
 * 将 OCR extracted_fields 映射为可 merge 的 G8 行补丁。
 * 支持标量或 `{ value, confidence }`；金额走 parseNum，0 视为无效跳过。
 */
export function mapG8OcrToVoucherFields(
  fields: Record<string, unknown>,
  confidence?: number,
): { patch: Partial<G8VoucherRow>; lowConfidence: G8OcrTargetField[] } {
  const patch: Partial<G8VoucherRow> = {}
  const lowConfidence: G8OcrTargetField[] = []
  if (!fields || typeof fields !== 'object') return { patch, lowConfidence }

  for (const [ocrKey, raw] of Object.entries(fields)) {
    const target = G8_OCR_FIELD_MAP[ocrKey] ?? G8_OCR_FIELD_MAP[ocrKey.toLowerCase()]
    if (!target) continue

    let val: unknown = raw
    let conf: number | undefined = confidence
    if (raw && typeof raw === 'object' && 'value' in (raw as object)) {
      val = (raw as { value?: unknown; confidence?: number }).value
      conf = (raw as { confidence?: number }).confidence ?? confidence
    }
    if (val == null || String(val).trim() === '') continue

    if (target === 'debitAmount' || target === 'creditAmount') {
      const num = parseNum(String(val).replace(/,/g, ''))
      if (num === 0) continue
      ;(patch as Record<string, unknown>)[target] = num
    } else {
      ;(patch as Record<string, unknown>)[target] = String(val).trim()
    }

    if (conf != null && conf < G8_OCR_CONFIDENCE_THRESHOLD && !lowConfidence.includes(target)) {
      lowConfidence.push(target)
    }
  }
  return { patch, lowConfidence }
}

/** 仅填充当前行为空的字段，保留已手工录入值 */
export function computeG8OcrMergePatch(
  row: Pick<G8VoucherRow, G8OcrTargetField>,
  patch: Partial<G8VoucherRow>,
): Partial<G8VoucherRow> {
  const merged: Partial<G8VoucherRow> = {}
  for (const [key, val] of Object.entries(patch)) {
    const cur = (row as Record<string, unknown>)[key]
    const isEmpty = cur == null || cur === '' || (typeof cur === 'number' && cur === 0)
    if (isEmpty) (merged as Record<string, unknown>)[key] = val
  }
  return merged
}

/** 确认弹窗 HTML：字段预览 + 低置信度标注 */
export function renderG8OcrPreview(
  patch: Partial<G8VoucherRow>,
  lowConfidence: G8OcrTargetField[],
  confidence: number,
): string {
  const lines = Object.entries(patch).map(([key, val]) => {
    const label = G8_OCR_FIELD_LABELS[key as G8OcrTargetField] || key
    const low = lowConfidence.includes(key as G8OcrTargetField)
    const tag = low ? '<span style="color:#e6a23c;margin-left:6px">⚠ 需人工复核</span>' : ''
    return `<div style="margin:4px 0"><strong>${label}：</strong>${val}${tag}</div>`
  })
  const confPct = (confidence * 100).toFixed(0)
  const confColor = confidence >= G8_OCR_CONFIDENCE_THRESHOLD ? '#67c23a' : '#e6a23c'
  return `
    <div style="font-size:13px">
      <div style="margin-bottom:8px;color:${confColor}">
        整体置信度：${confPct}%${confidence < G8_OCR_CONFIDENCE_THRESHOLD ? '（建议人工核对）' : ''}
      </div>
      ${lines.length ? lines.join('') : '<div style="color:#909399">未提取到有效字段</div>'}
    </div>
  `.trim()
}

/** 附件类型：仅图片与 PDF */
export function isG8AllowedOcrAttachment(file: File): boolean {
  const type = file.type || ''
  if (type.startsWith('image/') || type === 'application/pdf') return true
  return /\.(jpe?g|png|gif|bmp|webp|pdf)$/i.test(file.name || '')
}

/**
 * 从 OCR 响应体提取 fields + confidence。
 * 兼容 g8/contract-ocr 与 d4/contract-ocr 的多种返回形态。
 */
export function extractG8OcrPayload(resData: unknown): {
  fields: Record<string, unknown>
  confidence: number
} {
  const data = (resData as { data?: unknown })?.data ?? resData ?? {}
  const root = data as Record<string, unknown>
  const extracted = (root.extracted_fields ?? root.fields ?? {}) as Record<string, unknown>
  const fields: Record<string, unknown> = { ...extracted }
  // 部分端点只返回 summary 顶层字段
  if (!Object.keys(fields).length && root.summary) {
    fields.summary = root.summary
  }
  const confidence = typeof root.confidence === 'number' ? root.confidence : 1
  return { fields, confidence }
}

export function mapSampledToG8VoucherRow(s: G8SampledVoucherLike, seq: number): G8VoucherRow {
  const force = !!s.abnormal
  return enrichG8VoucherRow({
    voucherDate: s.voucherDate ?? '',
    voucherNo: s.voucherNo ?? '',
    businessContent: s.summary ?? '',
    counterAccount: s.counterpartAccount ?? '',
    debitAmount: parseNum(s.debitAmount),
    creditAmount: parseNum(s.creditAmount),
    forceAbnormal: force,
    abnormalDesc: force ? (s.selectionReason || '抽凭标记异常') : '',
    riskLevel: force ? 'high' : (s.isHighValue ? 'medium' : 'low'),
    remark: s.isHighValue ? '高值必选' : (s.selectionReason ?? ''),
    source: '抽凭',
    actualMisstatement: parseNum(s.actualMisstatement),
    isHighValue: !!s.isHighValue,
  }, seq)
}

function reseq(rows: G8VoucherRow[]): G8VoucherRow[] {
  return rows.map((r, i) => ({ ...r, seq: i + 1 }))
}

function parseRows(json: string | null | undefined): G8VoucherRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG8VoucherRow(r, i + 1))
  } catch {
    return []
  }
}

export const G8_CHECK_STATE_OPTIONS = [
  { value: null as G8CheckState, label: '未测' },
  { value: true as G8CheckState, label: '通过' },
  { value: false as G8CheckState, label: '不通过' },
]

export function useG8VoucherCheck(opts: {
  wpId?: Ref<string>
  projectId?: Ref<string>
  year?: Ref<number | undefined> | ComputedRef<number | undefined>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G8VoucherRow[]>([])
  const activeTab = ref<G8VoucherTab>('basic')
  const activeRowIndex = ref(0)
  const conclusion = ref('')
  const aiLoading = ref(false)
  const a13Pushing = ref(false)
  const procedureMarking = ref(false)
  const samplingParams = ref<G8SamplingParams>(defaultG8SamplingParams())
  const sourceFilter = ref<G8VoucherSourceFilter>('all')
  /** 行数>50 时默认虚拟速览；切到 false 用可编辑表格 */
  const browseMode = ref(true)

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  watch(
    () => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion,
    (v) => { conclusion.value = v ?? '' },
    { immediate: true },
  )

  watch(
    () => opts.allResponses.value.get(ITEM_ID_G8_VC_PARAMS)?.remark,
    (json) => { samplingParams.value = parseG8SamplingParams(json) },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function persistParams(): void {
    opts.debouncedSave(ITEM_ID_G8_VC_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  const crossSnap = computed(() => buildG8VoucherCrossSnapshot(opts.allResponses.value))
  const detailOptions = computed(() => crossSnap.value.details)
  const sourceCounts = computed(() => countG8VoucherBySource(rows.value))
  const filteredRows = computed(() => filterG8VoucherRowsBySource(rows.value, sourceFilter.value))
  const quantitativeAbnormalCount = computed(() =>
    rows.value.filter((r) => r.abnormalType === 'quantitative' || r.abnormalType === 'mixed').length,
  )
  const quantitativeRows = computed(() => selectG8QuantitativeAbnormals(rows.value))
  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G8A_VOUCHER_MARK_KEY)?.remark
    || opts.allResponses.value.get(G8A_VOUCHER_MARK_KEY)?.conclusion === 'completed',
  )

  function hintsForRow(row: G8VoucherRow): G8VoucherLinkHint[] {
    return buildG8VoucherLinkHints(row.investeeName ?? '', crossSnap.value)
  }

  const balanceOk = computed(() =>
    isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)),
  )
  const balanceDiff = computed(() =>
    calcSubtotal(rows.value.map((r) => r.debitAmount)) - calcSubtotal(rows.value.map((r) => r.creditAmount)),
  )
  const manyRows = computed(() => filteredRows.value.length > 50)
  const useVirtualScroll = computed(() => manyRows.value && browseMode.value)
  const untestedCount = computed(() => countG8VoucherUntested(rows.value))
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)
  const anomalyRate = computed(() => computeG8AnomalyRate(rows.value))
  const cutoffAbnormalCount = computed(() =>
    rows.value.filter((r) => r.source === '截止' && r.isAbnormal).length,
  )
  const coverage = computed(() => calcG8CoverageRates(rows.value, samplingParams.value))
  const completion = computed(() => calcG8VoucherCompletion({
    params: samplingParams.value,
    rows: rows.value,
    conclusion: conclusion.value,
  }))
  const projection = computed((): G8ProjectionView =>
    computeG8Projection({
      rows: rows.value,
      params: samplingParams.value,
      useSuggestedWhenEmpty: false,
    }),
  )
  const progressPct = computed(() => {
    const target = samplingParams.value.targetSampleSize
    if (!target || target <= 0) return 0
    return Math.min(100, Math.round((samplingParams.value.currentSampleSize / target) * 100))
  })
  const lowCoverage = computed(() => {
    const t = samplingParams.value.targetSampleSize
    const countLow = t > 0 && samplingParams.value.currentSampleSize < t
    const amountLow = samplingParams.value.populationAmount > 0 && coverage.value.amountPct < 60
    return countLow || amountLow
  })

  function buildMemo(): string {
    return buildG8VoucherSamplingMemo({
      params: samplingParams.value,
      rows: rows.value,
      conclusion: conclusion.value,
      coverage: coverage.value,
    })
  }

  /** 对金额类异常空白「实际错报」预填建议值（账面发生额） */
  function prefillSuggestedMisstatements(): number {
    if (opts.isReadonly.value) return 0
    let n = 0
    rows.value = rows.value.map((r) => {
      if (!(r.isAbnormal && (r.abnormalType === 'quantitative' || r.abnormalType === 'mixed'))) return r
      if (parseNum(r.actualMisstatement) > 0) return r
      const sug = suggestG8ActualMisstatement(r)
      if (sug <= 0) return r
      n += 1
      return recalcG8VoucherAbnormal(enrichG8VoucherRow({ ...r, actualMisstatement: sug }, r.seq))
    })
    if (n) persist()
    return n
  }

  /** 将推断结论草稿追加到检查结论 */
  function appendProjectionToConclusion(): void {
    if (opts.isReadonly.value) return
    const p = projection.value
    if (!p.canProject || !p.conclusion) return
    const block = [
      '【错报推断】',
      `方法=${p.method}；UML=${p.uml}；可容忍=${p.tolerableMisstatement}`,
      p.conclusion.message,
      p.reason || '',
    ].filter(Boolean).join('\n')
    const next = conclusion.value?.trim()
      ? `${conclusion.value.trim()}\n\n${block}`
      : block
    updateConclusion(next)
  }

  function toggleBrowseMode(): void {
    browseMode.value = !browseMode.value
  }

  function updateSamplingParams(field: keyof G8SamplingParams, value: string | number): void {
    if (opts.isReadonly.value) return
    ;(samplingParams.value as any)[field] = value
    persistParams()
  }

  function updateRow(rowId: string, patch: Partial<G8VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) =>
      r.rowId === rowId ? recalcG8VoucherAbnormal(enrichG8VoucherRow({ ...r, ...patch }, r.seq)) : r,
    )
    persist()
  }

  function linkDetail(rowId: string, detailRowId: string, investeeName: string): void {
    updateRow(rowId, { detailRowId, investeeName })
  }

  function applyLinkHints(rowId: string): void {
    if (opts.isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const hints = hintsForRow(row)
    const patch = applyG8LinkHintSuggestions(row, hints)
    if (Object.keys(patch).length) updateRow(rowId, patch as Partial<G8VoucherRow>)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入凭证编号', '新增凭证行')
      const no = (value ?? '').trim()
      if (!no) return
      rows.value = [
        ...rows.value,
        enrichG8VoucherRow({ voucherNo: no, source: '手工' }, rows.value.length + 1),
      ]
      persist()
    } catch { /* cancelled */ }
  }

  function mergeSample(sample: Partial<G8VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = [
      ...rows.value,
      enrichG8VoucherRow({ ...sample, source: sample.source ?? '抽凭' }, rows.value.length + 1),
    ]
    samplingParams.value.currentSampleSize = rows.value.filter((r) => r.source === '抽凭').length
    persist()
    persistParams()
  }

  /**
   * 抽凭引擎回填：按 fillMode 合并，并回写抽样方法/当前样本量。
   * @returns 净增行数（replace 时为新表行数）
   */
  function fillFromSampling(
    samples: G8SampledVoucherLike[],
    fillMode: FillMode = 'append',
    method?: string,
  ): number {
    if (opts.isReadonly.value || !samples.length) return 0
    const before = rows.value.length
    const mapped = samples.map((s, i) => mapSampledToG8VoucherRow(s, before + i + 1))
    const next = reseq(mergeByFillMode(rows.value, mapped, fillMode, (r) => r.voucherNo || r.rowId))
    const added = fillMode === 'replace' ? next.length : next.length - before
    rows.value = next
    if (method) samplingParams.value.samplingMethod = method
    samplingParams.value.currentSampleSize = rows.value.filter((r) => r.source === '抽凭').length
    if (samplingParams.value.targetSampleSize <= 0) {
      samplingParams.value.targetSampleSize = Math.max(samples.length, samplingParams.value.currentSampleSize)
    }
    persist()
    persistParams()
    return Math.max(0, added)
  }

  function reloadFromStore(): void {
    rows.value = parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
    samplingParams.value = parseG8SamplingParams(opts.allResponses.value.get(ITEM_ID_G8_VC_PARAMS)?.remark)
  }

  function setActiveRowIndex(idx: number): void {
    activeRowIndex.value = idx
  }

  function updateConclusion(value: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (opts.isReadonly.value || !samples.length) return
    const base = rows.value.length
    const mapped = samples.map((v, i) => enrichG8VoucherRow(mapCutoffToG8Voucher(v, base + i + 1), base + i + 1))
    rows.value = reseq(mergeByFillMode(rows.value, mapped, fillMode, (r) => r.voucherNo || r.rowId))
    persist()
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g8/ai/voucher-conclusion`,
        {
          rows: rows.value.filter((r) => r.isAbnormal),
          existingContent: conclusion.value,
          relatedContext: {
            行数: rows.value.length,
            未测: untestedCount.value,
            异常: abnormalCount.value,
            金额异常: quantitativeAbnormalCount.value,
            完成度: `${completion.value.pct}%`,
            抽样方法: samplingParams.value.samplingMethod,
            样本量: `${samplingParams.value.currentSampleSize}/${samplingParams.value.targetSampleSize}`,
          },
        },
        { _silent: true } as any,
      )
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  /** 金额类异常 → 创建错报 + 事件总线推 A13 */
  async function pushQuantitativeToA13(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      const { ElMessage } = await import('element-plus')
      ElMessage.warning('缺少项目 ID，无法推送错报')
      return -1
    }
    const targets = quantitativeRows.value
    if (!targets.length) {
      const { ElMessage } = await import('element-plus')
      ElMessage.info('当前无金额类异常可推送')
      return 0
    }
    const { ElMessageBox, ElMessage } = await import('element-plus')
    try {
      await ElMessageBox.confirm(
        `将把 ${targets.length} 笔金额类异常创建为未更正错报（科目 ${G8_ACCOUNT_CODE}），并通知错报汇总 A13。是否继续？`,
        '推送至 A13',
        { type: 'warning', confirmButtonText: '推送', cancelButtonText: '取消' },
      )
    } catch {
      return -1
    }

    a13Pushing.value = true
    const year = opts.year?.value || new Date().getFullYear()
    let created = 0
    try {
      const { createMisstatement } = await import('@/services/auditPlatformApi')
      const { eventBus } = await import('@/utils/eventBus')
      for (const row of targets) {
        try {
          await createMisstatement(pid, mapG8VoucherToMisstatementBody(row, year, G8_ACCOUNT_CODE))
          created += 1
        } catch { /* per-row */ }
      }
      eventBus.emit('a13:push-misstatement', {
        wpCode: 'G8-6',
        timestamp: Date.now(),
        items: targets.map((r) => mapG8VoucherToA13PushItem(r)),
      })
      ElMessage.success(
        created > 0
          ? `已创建 ${created} 笔未更正错报，并已通知 A13`
          : '已发出 A13 通知（错报创建可能失败，请在错报台账核对）',
      )
    } finally {
      a13Pushing.value = false
    }
    return created
  }

  /** 回填 G8A 程序 6/7/12 为已完成 */
  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      const { ElMessage } = await import('element-plus')
      ElMessage.warning('缺少项目 ID，无法回填 G8A')
      return -1
    }
    if (!rows.value.length) {
      const { ElMessage } = await import('element-plus')
      ElMessage.warning('请先编制 G8-6 样本后再回填程序表')
      return -1
    }
    const { ElMessageBox, ElMessage } = await import('element-plus')
    if (untestedCount.value > 0 || completion.value.pct < 70) {
      try {
        await ElMessageBox.confirm(
          `完成度 ${completion.value.pct}%（未测 ${untestedCount.value} 笔），是否仍标记 G8A 凭证相关程序（6/7/12）为已完成？`,
          '回填 G8A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    procedureMarking.value = true
    try {
      const summary = buildG8VoucherProcedureSummary({
        rowCount: rows.value.length,
        untested: untestedCount.value,
        abnormal: abnormalCount.value,
        quantitative: quantitativeAbnormalCount.value,
        completionPct: completion.value.pct,
        samplingMethod: samplingParams.value.samplingMethod,
      })
      const n = await markG8AProcedureSteps({
        projectId: pid,
        year: opts.year?.value,
        programNos: [...G8A_VOUCHER_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G8-6',
        executionSummary: summary,
      })
      opts.debouncedSave(G8A_VOUCHER_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G8A_VOUCHER_PROGRAM_NOS],
        }),
      })
      dispatchProcedureFocus({
        programNos: [...G8A_VOUCHER_PROGRAM_NOS],
        sheetCode: 'G8A',
      })
      ElMessage.success(
        n > 0
          ? `已回填 G8A 程序步骤 ${[...G8A_VOUCHER_PROGRAM_NOS].join('/')}（凭证检查）为已完成`
          : '已记录完成标记（程序步骤回写可能部分失败）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  return {
    rows,
    filteredRows,
    activeTab,
    activeRowIndex,
    conclusion,
    aiLoading,
    a13Pushing,
    procedureMarking,
    procedureMarked,
    quantitativeRows,
    samplingParams,
    sourceFilter,
    sourceCounts,
    detailOptions,
    quantitativeAbnormalCount,
    browseMode,
    manyRows,
    coverage,
    completion,
    projection,
    balanceOk,
    balanceDiff,
    useVirtualScroll,
    untestedCount,
    abnormalCount,
    anomalyRate,
    cutoffAbnormalCount,
    progressPct,
    lowCoverage,
    updateSamplingParams,
    updateRow,
    linkDetail,
    applyLinkHints,
    hintsForRow,
    addRow,
    mergeSample,
    fillFromSampling,
    reloadFromStore,
    setActiveRowIndex,
    updateConclusion,
    generateAiConclusion,
    applyCutoffResults,
    pushQuantitativeToA13,
    markProcedureComplete,
    buildMemo,
    prefillSuggestedMisstatements,
    appendProjectionToConclusion,
    toggleBrowseMode,
    riskLevelOptions: [
      { value: 'high', label: '高' },
      { value: 'medium', label: '中' },
      { value: 'low', label: '低' },
    ],
    checkStateOptions: G8_CHECK_STATE_OPTIONS,
  }
}
