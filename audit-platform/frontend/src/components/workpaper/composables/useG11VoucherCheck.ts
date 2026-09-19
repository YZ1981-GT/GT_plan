/**
 * useG11VoucherCheck — G11-5 凭证检查（样本选取 + 三态核对 + 检查比例 + 截止/推送/回填）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum, calcSubtotal } from './useG11FormulaEngine'
import {
  G11_VOUCHER_CHECK_DEFS,
  G11_LOW_INSPECTION_RATIO,
  calcG11SampleAbsAmount,
  calcG11SuggestedSampleSize,
  defaultG11SamplingParams,
  formatG11SamplingMethodLabel,
  g11VoucherInspectionRatio,
  parseG11CheckState,
  parseG11SamplingParams,
  type G11CheckState,
  type G11SamplingParams,
  type G11VoucherCheckKey,
} from './g11VoucherConstants'
import {
  G11A_VOUCHER_MARK_KEY,
  G11A_VOUCHER_PROGRAM_NOS,
  G11_ADJ_KEY,
  buildG11VoucherProcedureSummary,
  buildG11VoucherPushItems,
  isG11QuantitativeVoucherAbnormal,
  markG11AProcedureSteps,
  pushG11VoucherAbnormalToAdjustment,
} from './g11VoucherCross'
import { calcG11AdjPopulationAmount, parseG11AdjStore } from './g11AdjStorage'
import { mapCutoffToG11Voucher, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import { G11_ACCOUNT_CODE } from './g11Constants'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export type G11VoucherTab = 'basic' | 'check' | 'conclusion'
export type { G11CheckState }

export interface G11VoucherCheckRow {
  id: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetail: string
  creditAmount: number
  attachment: string | null
  supportingDocDesc: string
  check1: G11CheckState
  check2: G11CheckState
  check3: G11CheckState
  check4: G11CheckState
  check5: G11CheckState
  indexNo: string
  isAbnormal: boolean
  /** 人工或截止跨期强制异常（与核对项解耦） */
  forceAbnormal: boolean
  abnormalDesc: string
  riskLevel: 'high' | 'medium' | 'low' | ''
  remark: string
  source: string
}

const ITEM_ID_ROWS = 'G11-voucher-rows'
const ITEM_ID_CONCLUSION = 'G11-voucher-conclusion'
export const ITEM_ID_G11_VC_PARAMS = 'G11-vc-params'

function generateId(): string {
  return `g11v-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function recalcG11VoucherAbnormal(row: G11VoucherCheckRow): G11VoucherCheckRow {
  const checks = G11_VOUCHER_CHECK_DEFS.map((d) => row[d.key as G11VoucherCheckKey])
  const checkFailed = checks.some((c) => c === false)
  const isAbnormal = checkFailed || !!row.forceAbnormal
  return { ...row, isAbnormal }
}

export function enrichG11VoucherRow(raw: Partial<G11VoucherCheckRow> & { id?: string; summary?: string; amount?: number; indexRef?: string }, seq: number): G11VoucherCheckRow {
  const base: G11VoucherCheckRow = {
    id: raw.id ?? generateId(),
    seq,
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? raw.summary ?? '',
    counterAccount: raw.counterAccount ?? '',
    counterDetail: raw.counterDetail ?? '',
    creditAmount: parseNum(raw.creditAmount ?? raw.amount),
    attachment: raw.attachment ?? null,
    supportingDocDesc: raw.supportingDocDesc ?? '',
    // 默认未测，避免未核对却显示全✓
    check1: parseG11CheckState(raw.check1),
    check2: parseG11CheckState(raw.check2),
    check3: parseG11CheckState(raw.check3),
    check4: parseG11CheckState(raw.check4),
    check5: parseG11CheckState(raw.check5),
    indexNo: raw.indexNo ?? raw.indexRef ?? '',
    isAbnormal: false,
    forceAbnormal: raw.forceAbnormal === true || raw.forceAbnormal === '是' || raw.forceAbnormal === '✓',
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: (raw.riskLevel as G11VoucherCheckRow['riskLevel']) ?? '',
    remark: raw.remark ?? '',
    source: raw.source ?? '',
  }
  return recalcG11VoucherAbnormal(base)
}

export function computeG11VoucherAnomalyRate(rows: G11VoucherCheckRow[]): number {
  if (!rows.length) return 0
  return (rows.filter((r) => r.isAbnormal).length / rows.length) * 100
}

function parseRows(json: string | null | undefined): G11VoucherCheckRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (Array.isArray(parsed)) return parsed.map((r, i) => enrichG11VoucherRow(r, i + 1))
    const rows = Array.isArray(parsed?.rows) ? parsed.rows : []
    return rows.map((r: any, i: number) => enrichG11VoucherRow(r, i + 1))
  } catch {
    return []
  }
}

/** G11-5 抽样备忘（Markdown） */
export function buildG11VoucherSamplingMemo(input: {
  params: G11SamplingParams
  rows: G11VoucherCheckRow[]
  conclusion: string
  accountCode?: string
}): string {
  const { params, rows, conclusion, accountCode = G11_ACCOUNT_CODE } = input
  const abn = rows.filter((r) => r.isAbnormal)
  const sampleAbs = calcG11SampleAbsAmount(rows)
  const ratio = g11VoucherInspectionRatio(sampleAbs, params.populationAmount)
  const suggested = calcG11SuggestedSampleSize(params)
  const lines: string[] = []

  lines.push('# G11-5 投资收益凭证检查抽样备忘')
  lines.push('')
  lines.push(`生成时间：${new Date().toISOString()}`)
  lines.push(`科目：${accountCode} 投资收益`)
  lines.push('')
  lines.push('## 一、样本选取方法与规模')
  lines.push(`- 测试总体：${params.testPopulation || '—'}`)
  lines.push(`- 特定样本：${params.specificSamples || '—'}`)
  lines.push(`- 抽样总体：${params.samplingPopulation || '—'}`)
  lines.push(`- 抽样方法：${formatG11SamplingMethodLabel(params.samplingMethod)}`)
  lines.push(`- 目标样本量：${params.targetSampleSize || '—'} 笔`)
  lines.push(`- 当前样本量：${rows.length} 笔`)
  lines.push(`- 公式建议样本量：${suggested ?? '—'}`)
  lines.push(`- 本期发生额（总体）：${params.populationAmount ? params.populationAmount.toLocaleString('zh-CN') : '—'}`)
  lines.push(`- 已查样本金额：${sampleAbs.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
  lines.push(`- 检查比例：${ratio == null ? '—' : `${(ratio * 100).toFixed(1)}%`}`)
  if (params.samplingProcess?.trim()) {
    lines.push(`- 抽样过程：${params.samplingProcess.trim()}`)
  }
  lines.push('')
  lines.push('## 二、核对结果汇总')
  lines.push(`- 样本行数：${rows.length}`)
  lines.push(`- 异常：${abn.length} 笔（异常率 ${computeG11VoucherAnomalyRate(rows).toFixed(1)}%）`)
  if (abn.length) {
    lines.push('')
    lines.push('### 异常明细')
    for (const r of abn.slice(0, 50)) {
      lines.push(`- ${r.voucherNo || r.id}｜${r.businessContent || '—'}｜${r.abnormalDesc || '（无说明）'}`)
    }
  }
  lines.push('')
  lines.push('## 三、检查结论')
  lines.push(conclusion?.trim() || '—')
  lines.push('')
  lines.push('## 四、编制说明')
  lines.push('- 五项核对（三态）：①完整②授权③金额④期间⑤账务；「不通过」或强制异常 → 异常；「未测」不计入。')
  lines.push('- 检查比例 = 已查样本贷方合计 ÷ 本期发生额；低于 30% 时应扩大样本或在审计说明中解释。')
  lines.push('- 金额/账务未通过的异常可推送至 G11-3 生成 AJE 草稿并回写 G11-1；截止跨期样本可强制异常。')
  lines.push('')
  return lines.join('\n')
}

export function useG11VoucherCheck(opts: {
  wpId?: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
  year?: Ref<number | null> | ComputedRef<number | null>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G11VoucherCheckRow[]>([])
  const samplingParams = ref<G11SamplingParams>(defaultG11SamplingParams())
  const activeTab = ref<G11VoucherTab>('basic')
  const activeRowIndex = ref(0)
  const conclusion = ref('')
  const aiLoading = ref(false)
  const procedureMarking = ref(false)

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
    () => opts.allResponses.value.get(ITEM_ID_G11_VC_PARAMS)?.remark,
    (json) => { samplingParams.value = parseG11SamplingParams(json) },
    { immediate: true },
  )

  function persistSamplingParams(): void {
    opts.debouncedSave(ITEM_ID_G11_VC_PARAMS, {
      remark: JSON.stringify(samplingParams.value),
    })
  }

  function updateSampling<K extends keyof G11SamplingParams>(
    field: K,
    value: G11SamplingParams[K],
  ): void {
    if (opts.isReadonly.value) return
    samplingParams.value = { ...samplingParams.value, [field]: value }
    persistSamplingParams()
  }

  function applySuggestedSampleSize(): number | null {
    const suggested = calcG11SuggestedSampleSize(samplingParams.value)
    if (!suggested) return null
    updateSampling('targetSampleSize', suggested)
    return suggested
  }

  /** 从 G11-1 未审本期合计带入「本期发生额」 */
  function pullPopulationFromAdjudication(): number {
    if (opts.isReadonly.value) return 0
    const amount = g11AdjPopulationHint.value
    if (amount <= 0.005) {
      ElMessage.warning('G11-1 审定表未审本期合计为 0，请先编制 G11-1 或手工填写本期发生额')
      return 0
    }
    updateSampling('populationAmount', amount)
    if (!samplingParams.value.bookValue) updateSampling('bookValue', amount)
    if (!samplingParams.value.testPopulation?.trim()) {
      updateSampling(
        'testPopulation',
        `科目${G11_ACCOUNT_CODE}本期未审发生额（来自G11-1）合计 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
      )
    }
    ElMessage.success(`已从 G11-1 带入本期发生额 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
    return amount
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (opts.isReadonly.value) return
    const base = rows.value.length
    const mapped = samples.map((v, i) => enrichG11VoucherRow(mapCutoffToG11Voucher(v, base + i + 1), base + i + 1))
    rows.value = mergeByFillMode(
      rows.value,
      mapped,
      fillMode,
      (r) => String(r.voucherNo || '').trim(),
    ).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  /** 抽凭明细为单边贷方，不要求借贷平衡 */
  const isBalanced = computed(() => true)
  const balanceDiff = computed(() => 0)
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)
  const quantitativeAbnormalCount = computed(() =>
    rows.value.filter(isG11QuantitativeVoucherAbnormal).length,
  )
  const untestedCount = computed(() =>
    rows.value.filter((r) =>
      G11_VOUCHER_CHECK_DEFS.some((d) => r[d.key as G11VoucherCheckKey] === null),
    ).length,
  )
  const cutoffAbnormalCount = computed(() =>
    rows.value.filter((r) => r.source === '截止' && (r.forceAbnormal || r.isAbnormal)).length,
  )
  const g11AdjPopulationHint = computed(() => {
    const store = parseG11AdjStore(opts.allResponses.value.get(G11_ADJ_KEY)?.remark)
    return calcG11AdjPopulationAmount(store)
  })

  const sampleAbsAmount = computed(() => calcG11SampleAbsAmount(rows.value))
  const suggestedSampleSize = computed(() => calcG11SuggestedSampleSize(samplingParams.value))
  const inspectionRatio = computed(() =>
    g11VoucherInspectionRatio(sampleAbsAmount.value, samplingParams.value.populationAmount),
  )
  const inspectionRatioPct = computed(() =>
    inspectionRatio.value == null ? null : inspectionRatio.value * 100,
  )
  const lowInspectionRatio = computed(() =>
    inspectionRatio.value != null && inspectionRatio.value < G11_LOW_INSPECTION_RATIO,
  )
  const currentSampleSize = computed(() => rows.value.length)
  const progressPct = computed(() => {
    const target = samplingParams.value.targetSampleSize
    const current = rows.value.length
    if (target <= 0) return current > 0 ? 100 : 0
    return Math.min(100, Math.round((current / target) * 100))
  })
  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G11A_VOUCHER_MARK_KEY)?.remark
    || opts.allResponses.value.get(G11A_VOUCHER_MARK_KEY)?.conclusion === 'completed',
  )

  function updateRow(id: string, patch: Partial<G11VoucherCheckRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? recalcG11VoucherAbnormal(enrichG11VoucherRow({ ...r, ...patch }, r.seq)) : r))
    persist()
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, enrichG11VoucherRow({}, rows.value.length + 1)]
    persist()
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function mergeSample(sample: Partial<G11VoucherCheckRow>): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, enrichG11VoucherRow({ ...sample, source: sample.source ?? '抽凭' }, rows.value.length + 1)]
    persist()
  }

  function loadRows(data: G11VoucherCheckRow[]): void {
    rows.value = data.map((r, i) => enrichG11VoucherRow(r, i + 1))
    persist()
  }

  function reloadFromStore(): void {
    const json = opts.allResponses.value.get(ITEM_ID_ROWS)?.remark
    rows.value = parseRows(json)
    samplingParams.value = parseG11SamplingParams(opts.allResponses.value.get(ITEM_ID_G11_VC_PARAMS)?.remark)
  }

  function setActiveRowIndex(index: number): void {
    activeRowIndex.value = index
  }

  function updateConclusion(value: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g11/ai/voucher-conclusion`, {
        rows: rows.value.filter((r) => r.isAbnormal),
        existingContent: conclusion.value,
        relatedContext: {
          样本量: rows.value.length,
          异常条数: abnormalCount.value,
          检查比例: inspectionRatioPct.value == null ? '—' : `${inspectionRatioPct.value.toFixed(1)}%`,
          抽样方法: formatG11SamplingMethodLabel(samplingParams.value.samplingMethod),
        },
      }, { _silent: true } as any)
      const text = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  function buildMemo(): string {
    return buildG11VoucherSamplingMemo({
      params: samplingParams.value,
      rows: rows.value,
      conclusion: conclusion.value,
    })
  }

  async function pushAbnormalToAdjustment(): Promise<number> {
    if (opts.isReadonly.value) return 0
    const targets = buildG11VoucherPushItems(rows.value)
    if (!targets.length) {
      ElMessage.info('无金额类异常凭证可推送（须异常且金额/账务核对未通过，且贷方金额>0）')
      return 0
    }
    const { pushed, skipped } = pushG11VoucherAbnormalToAdjustment(
      opts.allResponses.value,
      opts.debouncedSave,
      rows.value,
    )
    if (!pushed) {
      ElMessage.info(skipped ? 'G11-3 已存在相同摘要的凭证异常草稿，未重复追加' : '无可推送项')
      return 0
    }
    const skipHint = skipped ? `（跳过 ${skipped} 笔重复）` : ''
    ElMessage.success(`已向 G11-3 推送 ${pushed} 笔凭证异常调整草稿${skipHint}，并回写 G11-1`)
    return pushed
  }

  async function markProcedureComplete(): Promise<{ ok: boolean; message: string }> {
    const projectId = opts.projectId?.value
    if (!projectId || opts.isReadonly.value) {
      return { ok: false, message: '缺少项目或只读，无法回填 G11A' }
    }
    if (!rows.value.length) {
      return { ok: false, message: '请先编制 G11-5 后再回填程序表' }
    }
    procedureMarking.value = true
    try {
      const summary = buildG11VoucherProcedureSummary({
        rowCount: rows.value.length,
        abnormal: abnormalCount.value,
        quantitative: quantitativeAbnormalCount.value,
        inspectionRatioPct: inspectionRatioPct.value,
      })
      const n = await markG11AProcedureSteps({
        projectId,
        year: opts.year?.value ?? undefined,
        programNos: [...G11A_VOUCHER_PROGRAM_NOS],
        linkedWorkpapers: 'G11-5',
        executionSummary: summary,
      })
      opts.debouncedSave(G11A_VOUCHER_MARK_KEY, {
        item_id: G11A_VOUCHER_MARK_KEY,
        conclusion: 'completed',
        remark: summary,
      })
      return {
        ok: n > 0,
        message: n > 0
          ? `已回填 G11A 程序步骤 ${[...G11A_VOUCHER_PROGRAM_NOS].join('/')}（凭证检查）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G11A 查看）',
      }
    } catch {
      return { ok: false, message: '回填 G11A 失败' }
    } finally {
      procedureMarking.value = false
    }
  }

  return {
    rows,
    samplingParams,
    suggestedSampleSize,
    sampleAbsAmount,
    inspectionRatio,
    inspectionRatioPct,
    lowInspectionRatio,
    progressPct,
    currentSampleSize,
    activeTab,
    activeRowIndex,
    conclusion,
    aiLoading,
    creditTotal,
    balanceDiff,
    isBalanced,
    abnormalCount,
    quantitativeAbnormalCount,
    untestedCount,
    cutoffAbnormalCount,
    g11AdjPopulationHint,
    procedureMarking,
    procedureMarked,
    updateRow,
    addRow,
    removeRow,
    mergeSample,
    loadRows,
    reloadFromStore,
    setActiveRowIndex,
    updateSampling,
    applySuggestedSampleSize,
    pullPopulationFromAdjudication,
    applyCutoffResults,
    updateConclusion,
    generateAiConclusion,
    buildMemo,
    pushAbnormalToAdjustment,
    markProcedureComplete,
    formatG11SamplingMethodLabel,
  }
}
