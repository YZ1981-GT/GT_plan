/**
 * useG9VoucherCheck — G9-6 凭证检查（6项核对：原始/授权/账务/分类/公允价值/减值）
 *
 * 核对项三态：null=未测 / true=通过 / false=不通过
 * 异常判定：任一核对项 false → 异常；未测不计入；forceAbnormal 可人工/截止强制
 * 抽样参数：G9-vc-params（对标 G8/D3，落实 Excel 模板「抽样总体/样本量」区）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, isDebitCreditBalanced, calcSubtotal } from './useG9FormulaEngine'
import { mapCutoffToG9Voucher, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'
import { G9_ACCOUNT_CODE, G9_RISK_LEVEL_OPTIONS } from './g9Constants'
import {
  buildG9VoucherCrossSnapshot,
  buildG9VoucherLinkHints,
  applyG9LinkHintSuggestions,
  selectG9QuantitativeAbnormals,
  mapG9VoucherToMisstatementBody,
  mapG9VoucherToA13PushItem,
  type G9VoucherLinkHint,
} from './g9VoucherCross'
import {
  G9A_VOUCHER_MARK_KEY,
  G9A_PROCEDURE_SHEET,
} from './g9FvCrossHelpers'

export { G9A_VOUCHER_MARK_KEY, G9A_PROCEDURE_SHEET }

export type { G9VoucherLinkHint }
export type G9VoucherTab = 'basic' | 'check' | 'conclusion'
/** null = 未测；true = 通过；false = 不通过 */
export type G9CheckState = boolean | null
export type G9AbnormalType = 'none' | 'quantitative' | 'qualitative' | 'mixed'
export type G9VoucherSourceFilter = 'all' | '抽凭' | '截止' | '手工'

export interface G9VoucherRow {
  rowId: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  attachmentRef: string
  supportDoc: string
  checkOriginal: G9CheckState
  checkAuthorized: G9CheckState
  checkAccounting: G9CheckState
  checkClassification: G9CheckState
  checkFairValue: G9CheckState
  checkImpairment: G9CheckState
  indexRef: string
  /** 由核对项 / forceAbnormal 推导 */
  isAbnormal: boolean
  /** 人工或截止测试强制标记异常（与核对项解耦，避免粘滞） */
  forceAbnormal: boolean
  /** 异常定性：金额 / 定性 / 混合 */
  abnormalType: G9AbnormalType
  abnormalDesc: string
  riskLevel: string
  suggestion: string
  remark: string
  source?: string
  /** 挂接 G9-2 明细行 */
  detailRowId?: string
  /** 资产名称（可与明细同步） */
  assetName?: string
}

/** 抽样参数（落库 G9-vc-params，对齐 Excel 方法论区） */
export interface G9SamplingParams {
  testPopulation: string
  specificSamples: string
  samplingPopulation: string
  samplingMethod: string
  samplingProcess: string
  targetSampleSize: number
  currentSampleSize: number
  populationCount: number
  populationAmount: number
}

export interface G9SampledVoucherLike {
  voucherNo?: string
  voucherDate?: string
  summary?: string | null
  debitAmount?: string | number | null
  creditAmount?: string | number | null
  amount?: string | number | null
  counterpartAccount?: string | null
  abnormal?: boolean
  isHighValue?: boolean
  selectionReason?: string
}

const CHECK_KEYS = [
  'checkOriginal',
  'checkAuthorized',
  'checkAccounting',
  'checkClassification',
  'checkFairValue',
  'checkImpairment',
] as const

export type G9CheckKey = (typeof CHECK_KEYS)[number]

const ITEM_ID_ROWS = 'G9-voucher-rows'
const ITEM_ID_CONCLUSION = 'G9-voucher-conclusion'
export const ITEM_ID_G9_VC_PARAMS = 'G9-vc-params'

/** 完整 G9A 模板：新增(6)/处置(7) 追查原始凭证；关联方(12) 常依赖凭证检查 */
export const G9A_VOUCHER_PROGRAM_NOS = [6, 7, 12] as const

export const G9_SAMPLING_METHOD_OPTIONS = [
  { value: 'random', label: '随机抽样' },
  { value: 'systematic', label: '系统抽样' },
  { value: 'judgmental', label: '判断抽样' },
  { value: 'mus', label: '货币单位抽样(MUS)' },
  { value: 'full', label: '全部项目检查' },
] as const

export function formatG9SamplingMethodLabel(value: string): string {
  const s = String(value ?? '').trim()
  if (!s) return '—'
  const hit = G9_SAMPLING_METHOD_OPTIONS.find((o) => o.value === s || o.label === s)
  if (hit) return hit.label
  return s
}

function normalizeG9SamplingMethod(raw: unknown): string {
  const s = String(raw ?? '').trim()
  if (!s) return ''
  const exact = G9_SAMPLING_METHOD_OPTIONS.find((o) => o.value === s || o.label === s)
  if (exact) return exact.value
  if (/随机/.test(s)) return 'random'
  if (/系统/.test(s)) return 'systematic'
  if (/判断|特定/.test(s)) return 'judgmental'
  if (/MUS|货币单位/i.test(s)) return 'mus'
  if (/全部|全查/.test(s)) return 'full'
  return s
}

function genId(): string {
  return `g9v-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function defaultG9SamplingParams(): G9SamplingParams {
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
  }
}

export function parseG9SamplingParams(json: string | null | undefined): G9SamplingParams {
  const defaults = defaultG9SamplingParams()
  if (!json) return defaults
  try {
    const raw = JSON.parse(json)
    if (!raw || typeof raw !== 'object') return defaults
    return {
      testPopulation: String(raw.testPopulation ?? ''),
      specificSamples: String(raw.specificSamples ?? ''),
      samplingPopulation: String(raw.samplingPopulation ?? ''),
      samplingMethod: normalizeG9SamplingMethod(raw.samplingMethod),
      samplingProcess: String(raw.samplingProcess ?? ''),
      targetSampleSize: Number(raw.targetSampleSize) || 0,
      currentSampleSize: Number(raw.currentSampleSize) || 0,
      populationCount: Number(raw.populationCount) || 0,
      populationAmount: Number(raw.populationAmount) || 0,
    }
  } catch {
    return defaults
  }
}

/** 解析核对三态；空/未识别 → null（未测） */
export function parseG9CheckState(v: unknown): G9CheckState {
  if (v === null || v === undefined || v === '') return null
  if (v === true || v === 1) return true
  if (v === false || v === 0) return false
  const s = String(v).trim().toLowerCase()
  if (!s || s === '未测' || s === 'n/a' || s === 'na' || s === '-' || s === '—') return null
  if (s === 'true' || s === '是' || s === 'yes' || s === 'y' || s === '✓' || s === '√' || s === '通过') return true
  if (s === 'false' || s === '否' || s === 'no' || s === 'n' || s === '✗' || s === '×' || s === '不通过') return false
  return null
}

export function formatG9CheckState(v: G9CheckState): string {
  if (v === true) return '✓'
  if (v === false) return '✗'
  return '未测'
}

export function deriveG9AbnormalType(row: Pick<G9VoucherRow, G9CheckKey | 'isAbnormal' | 'forceAbnormal'>): G9AbnormalType {
  if (!row.isAbnormal) return 'none'
  const quantitative = row.checkFairValue === false || row.checkImpairment === false
  const qualitative =
    row.forceAbnormal
    || row.checkOriginal === false
    || row.checkAuthorized === false
    || row.checkAccounting === false
    || row.checkClassification === false
  if (quantitative && qualitative) return 'mixed'
  if (quantitative) return 'quantitative'
  if (qualitative) return 'qualitative'
  return 'qualitative'
}

export function formatG9AbnormalType(t: G9AbnormalType): string {
  switch (t) {
    case 'quantitative': return '金额'
    case 'qualitative': return '定性'
    case 'mixed': return '混合'
    default: return '—'
  }
}

export function recalcG9VoucherAbnormal(row: G9VoucherRow): G9VoucherRow {
  const checks = CHECK_KEYS.map((k) => row[k])
  const checkFailed = checks.some((c) => c === false)
  const isAbnormal = checkFailed || !!row.forceAbnormal
  const withFlag = { ...row, isAbnormal }
  return { ...withFlag, abnormalType: deriveG9AbnormalType(withFlag) }
}

export function enrichG9VoucherRow(
  raw: Partial<G9VoucherRow> & { rowId?: string; id?: string },
  seq: number,
): G9VoucherRow {
  const base: G9VoucherRow = {
    rowId: raw.rowId ?? raw.id ?? genId(),
    seq,
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? '',
    counterAccount: raw.counterAccount ?? '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    attachmentRef: raw.attachmentRef ?? '',
    supportDoc: raw.supportDoc ?? '',
    checkOriginal: parseG9CheckState(raw.checkOriginal),
    checkAuthorized: parseG9CheckState(raw.checkAuthorized),
    checkAccounting: parseG9CheckState(raw.checkAccounting),
    checkClassification: parseG9CheckState(raw.checkClassification),
    checkFairValue: parseG9CheckState(raw.checkFairValue),
    checkImpairment: parseG9CheckState(raw.checkImpairment),
    indexRef: raw.indexRef ?? '',
    isAbnormal: false,
    forceAbnormal: !!raw.forceAbnormal,
    abnormalType: 'none',
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: raw.riskLevel ?? 'low',
    suggestion: raw.suggestion ?? '',
    remark: raw.remark ?? '',
    source: raw.source ?? '',
    detailRowId: raw.detailRowId ?? '',
    assetName: raw.assetName ?? '',
  }
  return recalcG9VoucherAbnormal(base)
}

/** @deprecated use recalcG9VoucherAbnormal */
export function deriveAbnormal(row: G9VoucherRow): boolean {
  return recalcG9VoucherAbnormal(row).isAbnormal
}

export function isG9VoucherFullyChecked(row: G9VoucherRow): boolean {
  return CHECK_KEYS.every((k) => row[k] !== null)
}

export function countG9VoucherUntested(rows: G9VoucherRow[]): number {
  return rows.filter((r) => !isG9VoucherFullyChecked(r)).length
}

export function computeG9AnomalyRate(rows: G9VoucherRow[]): number {
  if (!rows.length) return 0
  return (rows.filter((r) => r.isAbnormal).length / rows.length) * 100
}

export function calcG9SampleAbsAmount(rows: Array<{ debitAmount: number; creditAmount: number }>): number {
  return rows.reduce((s, r) => s + Math.max(Math.abs(r.debitAmount || 0), Math.abs(r.creditAmount || 0)), 0)
}

export function calcG9CoverageRates(
  rows: Array<{ debitAmount: number; creditAmount: number; source?: string }>,
  params: Pick<G9SamplingParams, 'targetSampleSize' | 'currentSampleSize' | 'populationCount' | 'populationAmount'>,
): { countPct: number; amountPct: number; sampleAbsAmount: number } {
  const sampleAbsAmount = calcG9SampleAbsAmount(rows)
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

export function calcG9VoucherCompletion(input: {
  params: G9SamplingParams
  rows: G9VoucherRow[]
  conclusion: string
}): { pct: number; checklist: Array<{ key: string; label: string; ok: boolean }> } {
  const { params, rows, conclusion } = input
  const hasParams = !!(params.samplingMethod || params.targetSampleSize || params.testPopulation)
  const hasRows = rows.length > 0
  const sampleOk = params.targetSampleSize > 0
    ? params.currentSampleSize >= params.targetSampleSize || rows.length >= params.targetSampleSize
    : hasRows
  const untested = countG9VoucherUntested(rows)
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

export function filterG9VoucherRowsBySource<T extends { source?: string }>(
  rows: T[],
  filter: G9VoucherSourceFilter,
): T[] {
  if (filter === 'all') return rows
  if (filter === '手工') return rows.filter((r) => !r.source || r.source === '手工')
  return rows.filter((r) => r.source === filter)
}

export function countG9VoucherBySource(rows: Array<{ source?: string }>): Record<G9VoucherSourceFilter, number> {
  return {
    all: rows.length,
    抽凭: rows.filter((r) => r.source === '抽凭').length,
    截止: rows.filter((r) => r.source === '截止').length,
    手工: rows.filter((r) => !r.source || r.source === '手工').length,
  }
}

export function buildG9VoucherSamplingMemo(input: {
  params: G9SamplingParams
  rows: G9VoucherRow[]
  conclusion: string
  coverage: { countPct: number; amountPct: number; sampleAbsAmount: number }
  accountCode?: string
}): string {
  const { params, rows, conclusion, coverage, accountCode = G9_ACCOUNT_CODE } = input
  const abn = rows.filter((r) => r.isAbnormal)
  const quant = abn.filter((r) => r.abnormalType === 'quantitative' || r.abnormalType === 'mixed')
  const lines: string[] = []
  lines.push('# G9-6 凭证检查抽样备忘')
  lines.push('')
  lines.push(`生成时间：${new Date().toISOString()}`)
  lines.push(`科目：${accountCode} 其他非流动金融资产`)
  lines.push('')
  lines.push('## 一、抽样参数')
  lines.push(`- 测试总体：${params.testPopulation || '—'}`)
  lines.push(`- 特定样本：${params.specificSamples || '—'}`)
  lines.push(`- 抽样总体：${params.samplingPopulation || '—'}`)
  lines.push(`- 抽样方法：${formatG9SamplingMethodLabel(params.samplingMethod)}`)
  lines.push(`- 目标样本量：${params.targetSampleSize || '—'} 笔`)
  lines.push(`- 当前样本量：${params.currentSampleSize || rows.filter((r) => r.source === '抽凭').length} 笔`)
  lines.push(`- 总体笔数：${params.populationCount || '—'}`)
  lines.push(`- 总体金额：${params.populationAmount ? params.populationAmount.toLocaleString('zh-CN') : '—'}`)
  lines.push('')
  lines.push('## 二、覆盖率')
  lines.push(`- 笔数覆盖率：${coverage.countPct.toFixed(1)}%`)
  lines.push(`- 金额覆盖率：${coverage.amountPct > 0 ? `${coverage.amountPct.toFixed(1)}%` : '—（请填写总体金额）'}`)
  lines.push(`- 样本发生额合计：${coverage.sampleAbsAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
  lines.push('')
  lines.push('## 三、核对结果')
  lines.push(`- 样本行数：${rows.length}`)
  lines.push(`- 未测：${countG9VoucherUntested(rows)}`)
  lines.push(`- 异常：${abn.length}（其中金额类 ${quant.length}）`)
  lines.push(`- 异常率：${computeG9AnomalyRate(rows).toFixed(1)}%`)
  if (abn.length) {
    lines.push('')
    lines.push('### 异常明细')
    for (const r of abn.slice(0, 50)) {
      lines.push(
        `- ${r.voucherNo || r.rowId}｜${r.assetName || '—'}｜${formatG9AbnormalType(r.abnormalType)}｜${r.abnormalDesc || '（无说明）'}`,
      )
    }
  }
  lines.push('')
  lines.push('## 四、检查结论')
  lines.push(conclusion?.trim() || '—')
  lines.push('')
  lines.push('## 五、编制说明')
  lines.push('- 六项核对（原始/授权/账务/分类/公允价值/减值）为三态；仅「不通过」计入异常。')
  lines.push('- 样本借贷不必平衡（抽样明细常为单边发生额）。')
  lines.push('- 公允价值/减值不通过属金额类异常，宜进入错报评估；其余为定性异常。')
  lines.push(params.samplingProcess ? `- 抽样过程：${params.samplingProcess}` : '- 抽样过程：—')
  lines.push('')
  return lines.join('\n')
}

export function mapSampledToG9VoucherRow(s: G9SampledVoucherLike, seq: number): G9VoucherRow {
  const force = !!s.abnormal
  const debit = parseNum(s.debitAmount ?? s.amount)
  const credit = parseNum(s.creditAmount)
  return enrichG9VoucherRow({
    voucherDate: s.voucherDate ?? '',
    voucherNo: s.voucherNo ?? '',
    businessContent: s.summary ?? '',
    counterAccount: s.counterpartAccount ?? '',
    debitAmount: debit,
    creditAmount: credit,
    forceAbnormal: force,
    abnormalDesc: force ? (s.selectionReason || '抽凭标记异常') : '',
    riskLevel: force ? 'high' : (s.isHighValue ? 'medium' : 'low'),
    remark: s.isHighValue ? '高值必选' : (s.selectionReason ?? ''),
    source: '抽凭',
  }, seq)
}

export function buildG9VoucherProcedureSummary(input: {
  rowCount: number
  untested: number
  abnormal: number
  quantitative: number
  completionPct: number
  samplingMethod?: string
}): string {
  const parts = [
    `G9-6 凭证检查已编制：${input.rowCount} 笔`,
    `完成度 ${input.completionPct}%`,
    `未测 ${input.untested}`,
    `异常 ${input.abnormal}（金额类 ${input.quantitative}）`,
  ]
  if (input.samplingMethod) parts.push(`方法 ${formatG9SamplingMethodLabel(input.samplingMethod)}`)
  return parts.join('；')
}

async function markG9AProcedureSteps(opts: {
  projectId: string
  year?: number
  programNos: readonly number[]
  status?: string
  linkedWorkpapers?: string
  executionSummary?: string
}): Promise<number> {
  if (!opts.projectId || !opts.programNos.length) return 0
  const { api } = await import('@/services/apiProxy')
  const year = opts.year || new Date().getFullYear()
  const scope = `procedure_table:${G9A_PROCEDURE_SHEET}`
  const status = opts.status || 'completed'
  let n = 0
  for (const programNo of opts.programNos) {
    const fields: Array<{ field: string; value: unknown }> = [
      { field: 'status', value: status },
    ]
    if (opts.linkedWorkpapers) fields.push({ field: 'linked_workpapers', value: opts.linkedWorkpapers })
    if (opts.executionSummary) fields.push({ field: 'execution_summary', value: opts.executionSummary })
    for (const f of fields) {
      try {
        await api.post('/api/workpapers/field-overrides', {
          project_id: opts.projectId,
          year,
          scope,
          item_key: String(programNo),
          field: f.field,
          value: f.value,
        }, { _silent: true } as any)
        if (f.field === 'status') n += 1
      } catch { /* silent */ }
    }
  }
  try {
    window.dispatchEvent(new CustomEvent('g9:procedure-marked', {
      detail: { programNos: [...opts.programNos], status, timestamp: Date.now() },
    }))
  } catch { /* silent */ }
  return n
}

function reseq(rows: G9VoucherRow[]): G9VoucherRow[] {
  return rows.map((r, i) => ({ ...r, seq: i + 1 }))
}

function parseRows(json: string | null | undefined): G9VoucherRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG9VoucherRow(r, i + 1))
  } catch {
    return []
  }
}

export const G9_CHECK_STATE_OPTIONS = [
  { value: 'null', label: '未测' },
  { value: 'true', label: '通过' },
  { value: 'false', label: '不通过' },
]

export function useG9VoucherCheck(opts: {
  wpId?: Ref<string>
  projectId?: Ref<string>
  year?: Ref<number | undefined> | ComputedRef<number | undefined>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G9VoucherRow[]>([])
  const activeTab = ref<G9VoucherTab>('basic')
  const activeRowIndex = ref(0)
  const conclusion = ref('')
  const aiLoading = ref(false)
  const a13Pushing = ref(false)
  const procedureMarking = ref(false)
  const samplingParams = ref<G9SamplingParams>(defaultG9SamplingParams())
  const sourceFilter = ref<G9VoucherSourceFilter>('all')
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
    () => opts.allResponses.value.get(ITEM_ID_G9_VC_PARAMS)?.remark,
    (json) => { samplingParams.value = parseG9SamplingParams(json) },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function persistParams(): void {
    opts.debouncedSave(ITEM_ID_G9_VC_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  const crossSnap = computed(() => buildG9VoucherCrossSnapshot(opts.allResponses.value))
  const detailOptions = computed(() => crossSnap.value.details)
  const sourceCounts = computed(() => countG9VoucherBySource(rows.value))
  const filteredRows = computed(() => filterG9VoucherRowsBySource(rows.value, sourceFilter.value))
  const quantitativeAbnormalCount = computed(() =>
    rows.value.filter((r) => r.abnormalType === 'quantitative' || r.abnormalType === 'mixed').length,
  )
  const quantitativeRows = computed(() => selectG9QuantitativeAbnormals(rows.value))
  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G9A_VOUCHER_MARK_KEY)?.remark
    || opts.allResponses.value.get(G9A_VOUCHER_MARK_KEY)?.conclusion === 'completed',
  )

  function hintsForRow(row: G9VoucherRow): G9VoucherLinkHint[] {
    return buildG9VoucherLinkHints(row.assetName ?? '', crossSnap.value)
  }

  const balanceOk = computed(() =>
    isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)),
  )
  const balanceDiff = computed(() =>
    calcSubtotal(rows.value.map((r) => r.debitAmount)) - calcSubtotal(rows.value.map((r) => r.creditAmount)),
  )
  const manyRows = computed(() => filteredRows.value.length > 50)
  const useVirtualScroll = computed(() => manyRows.value && browseMode.value)
  const untestedCount = computed(() => countG9VoucherUntested(rows.value))
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)
  const anomalyRate = computed(() => computeG9AnomalyRate(rows.value))
  const cutoffAbnormalCount = computed(() =>
    rows.value.filter((r) => r.source === '截止' && r.isAbnormal).length,
  )
  const coverage = computed(() => calcG9CoverageRates(rows.value, samplingParams.value))
  const completion = computed(() => calcG9VoucherCompletion({
    params: samplingParams.value,
    rows: rows.value,
    conclusion: conclusion.value,
  }))
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
    return buildG9VoucherSamplingMemo({
      params: samplingParams.value,
      rows: rows.value,
      conclusion: conclusion.value,
      coverage: coverage.value,
    })
  }

  function toggleBrowseMode(): void {
    browseMode.value = !browseMode.value
  }

  function updateSamplingParams(field: keyof G9SamplingParams, value: string | number): void {
    if (opts.isReadonly.value) return
    ;(samplingParams.value as any)[field] = value
    persistParams()
  }

  function updateRow(rowId: string, patch: Partial<G9VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) =>
      r.rowId === rowId ? recalcG9VoucherAbnormal(enrichG9VoucherRow({ ...r, ...patch }, r.seq)) : r,
    )
    persist()
  }

  function linkDetail(rowId: string, detailRowId: string, assetName: string): void {
    updateRow(rowId, { detailRowId, assetName })
  }

  function applyLinkHints(rowId: string): void {
    if (opts.isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const hints = hintsForRow(row)
    const patch = applyG9LinkHintSuggestions(row, hints)
    if (Object.keys(patch).length) updateRow(rowId, patch as Partial<G9VoucherRow>)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入凭证编号', '新增凭证行')
      const no = (value ?? '').trim()
      if (!no) return
      rows.value = [
        ...rows.value,
        enrichG9VoucherRow({ voucherNo: no, source: '手工' }, rows.value.length + 1),
      ]
      persist()
    } catch { /* cancelled */ }
  }

  function mergeSample(sample: Partial<G9VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = [
      ...rows.value,
      enrichG9VoucherRow({ ...sample, source: sample.source ?? '抽凭' }, rows.value.length + 1),
    ]
    samplingParams.value.currentSampleSize = rows.value.filter((r) => r.source === '抽凭').length
    persist()
    persistParams()
  }

  function fillFromSampling(
    samples: G9SampledVoucherLike[],
    fillMode: FillMode = 'append',
    method?: string,
  ): number {
    if (opts.isReadonly.value || !samples.length) return 0
    const before = rows.value.length
    const mapped = samples.map((s, i) => mapSampledToG9VoucherRow(s, before + i + 1))
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
    samplingParams.value = parseG9SamplingParams(opts.allResponses.value.get(ITEM_ID_G9_VC_PARAMS)?.remark)
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
    const mapped = samples.map((v, i) => enrichG9VoucherRow(mapCutoffToG9Voucher(v, base + i + 1), base + i + 1))
    rows.value = reseq(mergeByFillMode(rows.value, mapped, fillMode, (r) => r.voucherNo || r.rowId))
    persist()
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g9/ai/voucher-conclusion`,
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
      const text = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

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
        `将把 ${targets.length} 笔金额类异常创建为未更正错报（科目 ${G9_ACCOUNT_CODE}），并通知错报汇总 A13。是否继续？`,
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
          await createMisstatement(pid, mapG9VoucherToMisstatementBody(row, year, G9_ACCOUNT_CODE))
          created += 1
        } catch { /* per-row */ }
      }
      eventBus.emit('a13:push-misstatement', {
        wpCode: 'G9-6',
        timestamp: Date.now(),
        items: targets.map((r) => mapG9VoucherToA13PushItem(r)),
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

  async function markProcedureComplete(): Promise<{ ok: boolean; message: string }> {
    const projectId = opts.projectId?.value
    if (!projectId || opts.isReadonly.value) {
      return { ok: false, message: '缺少项目或只读，无法回填 G9A' }
    }
    procedureMarking.value = true
    try {
      const summary = buildG9VoucherProcedureSummary({
        rowCount: rows.value.length,
        untested: untestedCount.value,
        abnormal: abnormalCount.value,
        quantitative: quantitativeAbnormalCount.value,
        completionPct: completion.value.pct,
        samplingMethod: samplingParams.value.samplingMethod,
      })
      const n = await markG9AProcedureSteps({
        projectId,
        year: opts.year?.value,
        programNos: G9A_VOUCHER_PROGRAM_NOS,
        linkedWorkpapers: 'G9-6',
        executionSummary: summary,
      })
      opts.debouncedSave(G9A_VOUCHER_MARK_KEY, {
        item_id: G9A_VOUCHER_MARK_KEY,
        conclusion: 'completed',
        remark: summary,
      })
      return {
        ok: n > 0,
        message: n > 0
          ? `已回填 G9A 程序步骤 ${[...G9A_VOUCHER_PROGRAM_NOS].join('/')}（凭证检查）为已完成`
          : '回填请求已发送，请到 G9A 确认步骤状态',
      }
    } catch {
      return { ok: false, message: '回填 G9A 失败' }
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
    samplingParams,
    sourceFilter,
    sourceCounts,
    detailOptions,
    browseMode,
    balanceOk,
    balanceDiff,
    manyRows,
    useVirtualScroll,
    untestedCount,
    abnormalCount,
    quantitativeAbnormalCount,
    cutoffAbnormalCount,
    anomalyRate,
    coverage,
    completion,
    progressPct,
    lowCoverage,
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
    updateSamplingParams,
    toggleBrowseMode,
    buildMemo,
    markProcedureComplete,
    pushQuantitativeToA13,
    riskLevelOptions: [...G9_RISK_LEVEL_OPTIONS],
  }
}
