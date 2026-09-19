/**
 * useG12VoucherCheck — G12-6 凭证检查（6项核对 + 抽样参数 + 检查比例）
 *
 * 核对项三态：null=未测 / true=通过 / false=不通过
 * 异常判定：任一核对项 false 或 forceAbnormal → 异常；未测不计入
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum, calcSubtotal } from './useG12FormulaEngine'
import { mapCutoffToG12Voucher, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'
import { G12_ACCOUNT_CODE, G12_RISK_LEVELS } from './g12Constants'
import {
  G12_VOUCHER_CHECK_DEFS,
  G12_LOW_INSPECTION_RATIO,
  calcG12SampleAbsAmount,
  calcG12SuggestedSampleSize,
  defaultG12SamplingParams,
  formatG12SamplingMethodLabel,
  g12VoucherInspectionRatio,
  parseG12CheckState,
  parseG12SamplingParams,
  type G12CheckState,
  type G12SamplingParams,
  type G12VoucherCheckKey,
} from './g12VoucherConstants'
import {
  G12A_VOUCHER_MARK_KEY,
  G12A_VOUCHER_PROGRAM_NOS,
  applyG12NetExposureLinkHints,
  batchCiteG12FvValuation,
  buildG12NetExposureLinkHints,
  buildG12VoucherProcedureSummary,
  buildG12VoucherPushItems,
  calcG12PopulationHint,
  citeG12FvValuationToVoucher,
  formatG12SamplingProcessFromMethodology,
  isG12QuantitativeVoucherAbnormal,
  markG12AProcedureSteps,
  pushG12VoucherAbnormalToAdjustment,
  summarizeG12NetExposureLinks,
  type G12SamplingMethodologyLike,
} from './g12VoucherCross'
import { api } from '@/services/apiProxy'

export type G12VoucherTab = 'basic' | 'check' | 'conclusion'
export type G12VoucherSourceFilter = 'all' | '抽凭' | '截止' | '手工'

export interface G12VoucherRow {
  rowId: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  hedgeRelationId: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  attachment: string
  supportingDocDesc: string
  check1OriginalComplete: G12CheckState
  check2Authorization: G12CheckState
  check3Accounting: G12CheckState
  check4HedgeDesignation: G12CheckState
  check5HedgeAccounting: G12CheckState
  check6FVValuation: G12CheckState
  indexNo: string
  isAbnormal: boolean
  forceAbnormal: boolean
  abnormalDesc: string
  riskLevel: string
  remark: string
  source?: string
}

const CHECK_KEYS = G12_VOUCHER_CHECK_DEFS.map((d) => d.key) as G12VoucherCheckKey[]

const ITEM_ID_ROWS = 'G12-voucher-rows'
const ITEM_ID_CONCLUSION = 'G12-voucher-conclusion'
export const ITEM_ID_G12_VC_PARAMS = 'G12-vc-params'

function genId(): string {
  return `g12v-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function recalcG12VoucherAbnormal(row: G12VoucherRow): G12VoucherRow {
  const checkFailed = CHECK_KEYS.some((k) => row[k] === false)
  const isAbnormal = checkFailed || !!row.forceAbnormal
  return { ...row, isAbnormal }
}

export function enrichG12VoucherRow(
  raw: Partial<G12VoucherRow> & { rowId?: string; id?: string; summary?: string },
  seq: number,
): G12VoucherRow {
  const base: G12VoucherRow = {
    rowId: raw.rowId ?? raw.id ?? genId(),
    seq,
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? raw.summary ?? '',
    hedgeRelationId: raw.hedgeRelationId ?? '',
    counterAccount: raw.counterAccount ?? '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    attachment: raw.attachment ?? '',
    supportingDocDesc: raw.supportingDocDesc ?? '',
    check1OriginalComplete: parseG12CheckState(raw.check1OriginalComplete),
    check2Authorization: parseG12CheckState(raw.check2Authorization),
    check3Accounting: parseG12CheckState(raw.check3Accounting),
    check4HedgeDesignation: parseG12CheckState(raw.check4HedgeDesignation),
    check5HedgeAccounting: parseG12CheckState(raw.check5HedgeAccounting),
    check6FVValuation: parseG12CheckState(
      raw.check6FVValuation ?? (raw as { check5FVValuation?: unknown }).check5FVValuation,
    ),
    indexNo: raw.indexNo ?? '',
    isAbnormal: false,
    forceAbnormal: raw.forceAbnormal === true || raw.forceAbnormal === '是' || raw.forceAbnormal === '✓',
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: raw.riskLevel ?? '',
    remark: raw.remark ?? '',
    source: raw.source ?? '',
  }
  return recalcG12VoucherAbnormal(base)
}

function parseRows(json: string | null | undefined): G12VoucherRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (Array.isArray(parsed)) return parsed.map((r, i) => enrichG12VoucherRow(r, i + 1))
    const rows = Array.isArray(parsed?.rows) ? parsed.rows : []
    return rows.map((r: Partial<G12VoucherRow>, i: number) => enrichG12VoucherRow(r, i + 1))
  } catch {
    return []
  }
}

export function buildG12VoucherSamplingMemo(input: {
  params: G12SamplingParams
  rows: G12VoucherRow[]
  auditNote: string
  auditConclusion: string
  accountCode?: string
}): string {
  const { params, rows, auditNote, auditConclusion, accountCode = G12_ACCOUNT_CODE } = input
  const abn = rows.filter((r) => r.isAbnormal)
  const sampleAbs = calcG12SampleAbsAmount(rows)
  const ratio = g12VoucherInspectionRatio(sampleAbs, params.populationAmount)
  const suggested = calcG12SuggestedSampleSize(params)
  const lines: string[] = []

  lines.push('# G12-6 净敞口套期收益凭证检查抽样备忘')
  lines.push('')
  lines.push(`生成时间：${new Date().toISOString()}`)
  lines.push(`科目：${accountCode} 净敞口套期收益`)
  lines.push('')
  lines.push('## 一、样本选取方法与规模')
  lines.push(`- 测试总体：${params.testPopulation || '—'}`)
  lines.push(`- 特定样本：${params.specificSamples || '—'}`)
  lines.push(`- 抽样总体：${params.samplingPopulation || '—'}`)
  lines.push(`- 抽样方法：${formatG12SamplingMethodLabel(params.samplingMethod)}`)
  lines.push(`- 目标样本量：${params.targetSampleSize || '—'} 笔`)
  lines.push(`- 当前样本量：${rows.length} 笔`)
  lines.push(`- 公式建议样本量：${suggested ?? '—'}`)
  lines.push(`- 本期发生额：${params.populationAmount ? params.populationAmount.toLocaleString('zh-CN') : '—'}`)
  lines.push(`- 已查样本金额：${sampleAbs.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
  lines.push(`- 检查比例：${ratio == null ? '—' : `${(ratio * 100).toFixed(1)}%`}`)
  if (params.samplingProcess?.trim()) {
    lines.push(`- 抽样过程：${params.samplingProcess.trim()}`)
  }
  lines.push('')
  lines.push('## 二、核对结果汇总')
  lines.push(`- 样本行数：${rows.length}`)
  lines.push(`- 异常：${abn.length} 笔`)
  if (abn.length) {
    lines.push('')
    lines.push('### 异常明细')
    for (const r of abn.slice(0, 50)) {
      lines.push(`- ${r.voucherNo || r.rowId}｜${r.hedgeRelationId || '—'}｜${r.abnormalDesc || '（无说明）'}`)
    }
  }
  lines.push('')
  lines.push('## 三、审计说明')
  lines.push(auditNote?.trim() || '—')
  lines.push('')
  lines.push('## 四、审计结论')
  lines.push(auditConclusion?.trim() || '—')
  lines.push('')
  lines.push('## 五、编制说明')
  lines.push('- 六项核对（三态）：①完整②授权③账务④套期指定⑤套期会计⑥公允价值；「不通过」或强制异常 → 异常。')
  lines.push('- 检查比例 = 已查样本发生额 ÷ 本期发生额；低于 30% 时应扩大样本或在审计说明中解释。')
  lines.push('- 套期会计/公允价值不通过属金额类异常，可推送 G12-3；须与 G12-2/G12-4/G12-5 交叉验证。')
  lines.push('')
  return lines.join('\n')
}

export function useG12VoucherCheck(opts: {
  wpId?: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
  year?: Ref<number | null> | ComputedRef<number | null>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G12VoucherRow[]>([])
  const samplingParams = ref<G12SamplingParams>(defaultG12SamplingParams())
  const activeTab = ref<G12VoucherTab>('basic')
  const sourceFilter = ref<G12VoucherSourceFilter>('all')
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const procedureMarking = ref(false)
  const a13Pushing = ref(false)

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion,
    (v) => { auditConclusion.value = v ?? '' },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get('G12-voucher-audit-note')?.remark,
    (v) => { auditNote.value = v ?? '' },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(ITEM_ID_G12_VC_PARAMS)?.remark,
    (json) => { samplingParams.value = parseG12SamplingParams(json) },
    { immediate: true },
  )

  function persistSamplingParams(): void {
    opts.debouncedSave(ITEM_ID_G12_VC_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  function updateSampling<K extends keyof G12SamplingParams>(field: K, value: G12SamplingParams[K]): void {
    if (opts.isReadonly.value) return
    samplingParams.value = { ...samplingParams.value, [field]: value }
    persistSamplingParams()
  }

  function applySuggestedSampleSize(): number | null {
    const suggested = calcG12SuggestedSampleSize(samplingParams.value)
    if (!suggested) return null
    updateSampling('targetSampleSize', suggested)
    return suggested
  }

  function pullPopulationFromHedgeDetail(): number {
    if (opts.isReadonly.value) return 0
    const amount = g12PopulationHint.value
    if (amount <= 0.005) {
      ElMessage.warning('G12-2 套期明细净敞口损益合计为 0，请先编制 G12-2 或手工填写本期发生额')
      return 0
    }
    updateSampling('populationAmount', amount)
    if (!samplingParams.value.bookValue) updateSampling('bookValue', amount)
    if (!samplingParams.value.testPopulation?.trim()) {
      updateSampling(
        'testPopulation',
        `科目${G12_ACCOUNT_CODE}本期套期损益（来自G12-2）合计 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
      )
    }
    ElMessage.success(`已从 G12-2 带入本期发生额 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
    return amount
  }

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  const filteredRows = computed(() => {
    if (sourceFilter.value === 'all') return rows.value
    if (sourceFilter.value === '手工') return rows.value.filter((r) => !r.source || r.source === '手工')
    return rows.value.filter((r) => r.source === sourceFilter.value)
  })

  const sourceCounts = computed(() => ({
    all: rows.value.length,
    抽凭: rows.value.filter((r) => r.source === '抽凭').length,
    截止: rows.value.filter((r) => r.source === '截止').length,
    手工: rows.value.filter((r) => !r.source || r.source === '手工').length,
  }))

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const isBalanced = computed(() => Math.abs(debitTotal.value - creditTotal.value) < 0.01)
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)
  const quantitativeAbnormalCount = computed(() => rows.value.filter(isG12QuantitativeVoucherAbnormal).length)
  const untestedCount = computed(() =>
    rows.value.filter((r) => CHECK_KEYS.some((k) => r[k] === null)).length,
  )
  const cutoffAbnormalCount = computed(() =>
    rows.value.filter((r) => r.source === '截止' && (r.forceAbnormal || r.isAbnormal)).length,
  )
  const g12PopulationHint = computed(() => calcG12PopulationHint(opts.allResponses.value))

  const sampleAbsAmount = computed(() => calcG12SampleAbsAmount(rows.value))
  const suggestedSampleSize = computed(() => calcG12SuggestedSampleSize(samplingParams.value))
  const inspectionRatio = computed(() =>
    g12VoucherInspectionRatio(sampleAbsAmount.value, samplingParams.value.populationAmount),
  )
  const inspectionRatioPct = computed(() =>
    inspectionRatio.value == null ? null : inspectionRatio.value * 100,
  )
  const lowInspectionRatio = computed(() =>
    inspectionRatio.value != null && inspectionRatio.value < G12_LOW_INSPECTION_RATIO,
  )
  const currentSampleSize = computed(() => rows.value.length)
  const progressPct = computed(() => {
    const target = samplingParams.value.targetSampleSize
    const current = rows.value.length
    if (target <= 0) return current > 0 ? 100 : 0
    return Math.min(100, Math.round((current / target) * 100))
  })
  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G12A_VOUCHER_MARK_KEY)?.remark
    || opts.allResponses.value.get(G12A_VOUCHER_MARK_KEY)?.conclusion === 'completed',
  )
  const useVirtualScroll = computed(() => rows.value.length > 50)

  function updateRow(rowId: string, patch: Partial<G12VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) =>
      (r.rowId === rowId ? recalcG12VoucherAbnormal(enrichG12VoucherRow({ ...r, ...patch }, r.seq)) : r),
    )
    persist()
  }

  function updateCell(rowId: string, field: keyof G12VoucherRow, value: unknown): void {
    updateRow(rowId, { [field]: value } as Partial<G12VoucherRow>)
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, enrichG12VoucherRow({ source: '手工' }, rows.value.length + 1)]
    persist()
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function mergeSample(sample: Partial<G12VoucherRow>): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, enrichG12VoucherRow({ ...sample, source: sample.source ?? '抽凭' }, rows.value.length + 1)]
    persist()
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (opts.isReadonly.value || !samples.length) return
    const base = rows.value.length
    const mapped = samples.map((v, i) => mapCutoffToG12Voucher(v, base + i + 1))
    rows.value = mergeByFillMode(rows.value, mapped, fillMode, (r) => r.voucherNo)
      .map((r, i) => enrichG12VoucherRow(r, i + 1))
    persist()
  }

  function reloadFromStore(): void {
    rows.value = parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
    samplingParams.value = parseG12SamplingParams(opts.allResponses.value.get(ITEM_ID_G12_VC_PARAMS)?.remark)
  }

  function updateAuditNote(value: string): void {
    if (opts.isReadonly.value) return
    auditNote.value = value
    opts.debouncedSave('G12-voucher-audit-note', { remark: value })
  }

  function updateAuditConclusion(value: string): void {
    if (opts.isReadonly.value) return
    auditConclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g12/ai/voucher-conclusion`, {
        rows: rows.value.filter((r) => r.isAbnormal),
        existingContent: auditConclusion.value,
        relatedContext: {
          样本量: rows.value.length,
          异常条数: abnormalCount.value,
          检查比例: inspectionRatioPct.value == null ? '—' : `${inspectionRatioPct.value.toFixed(1)}%`,
        },
      }, { _silent: true } as any)
      const text = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (text) updateAuditConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  function buildMemo(): string {
    return buildG12VoucherSamplingMemo({
      params: samplingParams.value,
      rows: rows.value,
      auditNote: auditNote.value,
      auditConclusion: auditConclusion.value,
    })
  }

  async function pushAbnormalToAdjustment(): Promise<number> {
    if (opts.isReadonly.value) return 0
    const targets = buildG12VoucherPushItems(rows.value)
    if (!targets.length) {
      ElMessage.info('无金额类异常凭证可推送（须异常且套期会计/公允价值/账务核对未通过）')
      return 0
    }
    a13Pushing.value = true
    try {
      const { pushed, skipped } = pushG12VoucherAbnormalToAdjustment(
        opts.allResponses.value,
        opts.debouncedSave,
        rows.value,
      )
      if (!pushed) {
        ElMessage.info(skipped ? 'G12-3 已存在相同摘要的凭证异常草稿，未重复追加' : '无可推送项')
        return 0
      }
      const skipHint = skipped ? `（跳过 ${skipped} 笔重复）` : ''
      ElMessage.success(`已向 G12-3 推送 ${pushed} 笔凭证异常调整草稿${skipHint}`)
      return pushed
    } finally {
      a13Pushing.value = false
    }
  }

  async function markProcedureComplete(): Promise<{ ok: boolean; message: string }> {
    const projectId = opts.projectId?.value
    if (!projectId || opts.isReadonly.value) {
      return { ok: false, message: '缺少项目或只读，无法回填 G12A' }
    }
    if (!rows.value.length) {
      return { ok: false, message: '请先编制 G12-6 后再回填程序表' }
    }
    procedureMarking.value = true
    try {
      const summary = buildG12VoucherProcedureSummary({
        rowCount: rows.value.length,
        abnormal: abnormalCount.value,
        quantitative: quantitativeAbnormalCount.value,
        inspectionRatioPct: inspectionRatioPct.value,
      })
      const n = await markG12AProcedureSteps({
        projectId,
        year: opts.year?.value ?? undefined,
        programNos: [...G12A_VOUCHER_PROGRAM_NOS],
        linkedWorkpapers: 'G12-6',
        executionSummary: summary,
      })
      opts.debouncedSave(G12A_VOUCHER_MARK_KEY, {
        item_id: G12A_VOUCHER_MARK_KEY,
        conclusion: 'completed',
        remark: summary,
      })
      return {
        ok: n > 0,
        message: n > 0
          ? `已回填 G12A 程序步骤 ${[...G12A_VOUCHER_PROGRAM_NOS].join('/')}（凭证检查）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G12A 查看）',
      }
    } catch {
      return { ok: false, message: '回填 G12A 失败' }
    } finally {
      procedureMarking.value = false
    }
  }

  /** 抽凭引擎回填：样本行 + 方法学 → 抽样方法/目标量/抽样过程 */
  function applySamplingFill(optsFill: {
    samples: Array<Partial<G12VoucherRow> & {
      summary?: string
      amount?: number
      counterpartAccount?: string
      abnormal?: boolean
      isHighValue?: boolean
      selectionReason?: string
    }>
    method?: string
    fillMode?: 'append' | 'merge' | 'replace'
    methodology?: G12SamplingMethodologyLike
  }): number {
    if (opts.isReadonly.value) return 0
    const samples = optsFill.samples ?? []
    if (!samples.length) return 0

    if (optsFill.method) {
      updateSampling('samplingMethod', optsFill.method === 'mus' ? 'mus' : optsFill.method)
    }
    if (optsFill.methodology) {
      const process = formatG12SamplingProcessFromMethodology({
        ...optsFill.methodology,
        samplingMethod: optsFill.methodology.samplingMethod || optsFill.method,
        sampleSize: optsFill.methodology.sampleSize ?? samples.length,
      })
      updateSampling('samplingProcess', process)
      if (optsFill.methodology.suggestedSampleSize && !samplingParams.value.targetSampleSize) {
        updateSampling('targetSampleSize', optsFill.methodology.suggestedSampleSize)
      }
      if (optsFill.methodology.tolerableMisstatement != null && !samplingParams.value.tolerableMisstatement) {
        updateSampling('tolerableMisstatement', optsFill.methodology.tolerableMisstatement)
      }
      if (optsFill.methodology.expectedMisstatement != null && !samplingParams.value.expectedMisstatement) {
        updateSampling('expectedMisstatement', optsFill.methodology.expectedMisstatement)
      }
      if (optsFill.methodology.confidenceLevel != null) {
        const cl = optsFill.methodology.confidenceLevel
        const risk: 1 | 5 | 10 = cl >= 0.99 ? 1 : cl >= 0.95 ? 5 : 10
        updateSampling('riskOfIncorrectAcceptance', risk)
      }
    } else if (optsFill.method) {
      updateSampling(
        'samplingProcess',
        formatG12SamplingProcessFromMethodology({
          samplingMethod: optsFill.method,
          sampleSize: samples.length,
        }),
      )
    }
    if (!samplingParams.value.targetSampleSize) {
      updateSampling('targetSampleSize', samples.length)
    }

    const mode = optsFill.fillMode ?? 'append'
    if (mode === 'replace') {
      rows.value = samples.map((s, i) => enrichG12VoucherRow({
        voucherDate: s.voucherDate,
        voucherNo: s.voucherNo,
        businessContent: s.businessContent ?? s.summary,
        counterAccount: s.counterAccount ?? s.counterpartAccount,
        debitAmount: s.debitAmount ?? s.amount,
        creditAmount: s.creditAmount,
        forceAbnormal: !!s.abnormal,
        abnormalDesc: s.abnormal ? (s.selectionReason || '抽凭标记异常') : '',
        riskLevel: s.abnormal ? 'high' : (s.isHighValue ? 'medium' : 'low'),
        remark: s.isHighValue ? '高值必选' : (s.selectionReason ?? ''),
        source: '抽凭',
      }, i + 1))
      persist()
      return samples.length
    }

    let added = 0
    for (const s of samples) {
      const no = String(s.voucherNo || '').trim()
      if (mode === 'merge' && no && rows.value.some((r) => r.voucherNo === no)) continue
      mergeSample({
        voucherDate: s.voucherDate,
        voucherNo: s.voucherNo,
        businessContent: s.businessContent ?? s.summary,
        counterAccount: s.counterAccount ?? s.counterpartAccount,
        debitAmount: s.debitAmount ?? s.amount,
        creditAmount: s.creditAmount,
        forceAbnormal: !!s.abnormal,
        abnormalDesc: s.abnormal ? (s.selectionReason || '抽凭标记异常') : '',
        riskLevel: s.abnormal ? 'high' : (s.isHighValue ? 'medium' : ''),
        remark: s.isHighValue ? '高值必选' : (s.selectionReason ?? ''),
        source: '抽凭',
      })
      added += 1
    }
    return added
  }

  const netExposureHints = computed(() =>
    buildG12NetExposureLinkHints(rows.value, opts.allResponses.value),
  )
  const netExposureSummary = computed(() => summarizeG12NetExposureLinks(netExposureHints.value))

  /** 按套期关系编号勾稽 G12-5，并回写核对⑤（仅未测行） */
  function syncFromNetExposure(): number {
    if (opts.isReadonly.value) return 0
    const hints = buildG12NetExposureLinkHints(rows.value, opts.allResponses.value)
    const { updated, rows: next } = applyG12NetExposureLinkHints(rows.value, hints)
    if (updated) {
      rows.value = next.map((r, i) => enrichG12VoucherRow(r, i + 1))
      persist()
    }
    return updated
  }

  /** 单行引用 G12-4 估值依据 → 支持性文件 + 核对⑥ */
  function citeFvForRow(rowId: string): { ok: boolean; message: string } {
    if (opts.isReadonly.value) return { ok: false, message: '只读' }
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return { ok: false, message: '行不存在' }
    const res = citeG12FvValuationToVoucher(row, opts.allResponses.value)
    if (res.ok && res.patch) {
      updateRow(rowId, res.patch)
    }
    return { ok: res.ok, message: res.message }
  }

  /** 批量引用 G12-4 估值依据 */
  function batchCiteFv(): number {
    if (opts.isReadonly.value) return 0
    const { cited, rows: next } = batchCiteG12FvValuation(rows.value, opts.allResponses.value)
    if (cited) {
      rows.value = next.map((r, i) => enrichG12VoucherRow(r, i + 1))
      persist()
    }
    return cited
  }

  return {
    rows,
    filteredRows,
    samplingParams,
    activeTab,
    sourceFilter,
    sourceCounts,
    auditNote,
    auditConclusion,
    useVirtualScroll,
    debitTotal,
    creditTotal,
    isBalanced,
    abnormalCount,
    quantitativeAbnormalCount,
    untestedCount,
    cutoffAbnormalCount,
    g12PopulationHint,
    sampleAbsAmount,
    suggestedSampleSize,
    inspectionRatio,
    inspectionRatioPct,
    lowInspectionRatio,
    currentSampleSize,
    progressPct,
    procedureMarked,
    procedureMarking,
    a13Pushing,
    aiLoading,
    netExposureHints,
    netExposureSummary,
    updateSampling,
    applySuggestedSampleSize,
    pullPopulationFromHedgeDetail,
    updateRow,
    updateCell,
    addRow,
    removeRow,
    mergeSample,
    applyCutoffResults,
    applySamplingFill,
    syncFromNetExposure,
    citeFvForRow,
    batchCiteFv,
    reloadFromStore,
    updateAuditNote,
    updateAuditConclusion,
    generateAiConclusion,
    buildMemo,
    pushAbnormalToAdjustment,
    markProcedureComplete,
    persist,
    ITEM_ID: ITEM_ID_ROWS,
    G12_RISK_LEVELS,
  }
}

export { ITEM_ID_ROWS as G12_VOUCHER_ROWS_KEY }
